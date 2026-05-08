#!/usr/bin/env python3
"""
Qualtrics Survey Import Tool

Zero external dependencies — Python stdlib only.
Imports Qualtrics CSV exports into MySQL via docker exec.

Auto-detects both Qualtrics export formats:
  "Use Values/IDs" (numeric codes, e.g. Q1=1)
  "Use Labels"     (text labels,  e.g. Q1="Extremely satisfied")

Duplicate Response_IDs already in the DB are silently skipped, so
recurring surveys can be safely re-imported each term.

Usage:
    python3 survey_upload_app.py
    # open http://localhost:5002
"""

import csv
import io
import json
import os
import re
import subprocess
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ── Config ─────────────────────────────────────────────────────────────────────

def _load_dotenv(path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env

_HERE   = Path(__file__).parent
_dotenv = _load_dotenv(_HERE.parent / "Metabase" / ".env")

def _cfg(key: str, fallback: str) -> str:
    return os.environ.get(key) or _dotenv.get(key) or fallback

MYSQL_CONTAINER  = _cfg("MYSQL_CONTAINER", "mysql-container")
DB_ROOT_PASSWORD = _cfg("DB_PASSWORD",     "password")
DB_NAME          = _cfg("DB_NAME",         "Micro-Surveys")
PORT             = int(os.environ.get("SURVEY_UPLOAD_PORT", 5002))

# ── MySQL helpers ──────────────────────────────────────────────────────────────

def _mysql_cmd(sql: str) -> Tuple[bool, str]:
    cmd = ["docker", "exec", "-i", MYSQL_CONTAINER,
           "mysql", "-uroot", f"-p{DB_ROOT_PASSWORD}", DB_NAME]
    try:
        r = subprocess.run(cmd, input=sql.encode("utf-8"),
                           capture_output=True, timeout=30)
        return (True, r.stdout.decode(errors="replace")) if r.returncode == 0 \
               else (False, r.stderr.decode(errors="replace"))
    except FileNotFoundError:
        return False, "docker not found — is Docker running?"
    except subprocess.TimeoutExpired:
        return False, "MySQL query timed out"
    except Exception as e:
        return False, str(e)

def _mysql_query(sql: str) -> Tuple[bool, List[List[str]]]:
    cmd = ["docker", "exec", "-i", MYSQL_CONTAINER,
           "mysql", "--batch", "--skip-column-names",
           "-uroot", f"-p{DB_ROOT_PASSWORD}", DB_NAME]
    try:
        r = subprocess.run(cmd, input=sql.encode("utf-8"),
                           capture_output=True, timeout=15)
        if r.returncode != 0:
            return False, []
        rows = [
            line.split("\t")
            for line in r.stdout.decode(errors="replace").splitlines()
            if line.strip()
        ]
        return True, rows
    except Exception:
        return False, []

def _container_running() -> Tuple[bool, str]:
    try:
        r = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", MYSQL_CONTAINER],
            capture_output=True, timeout=5)
        if r.returncode != 0:
            return False, f"Container '{MYSQL_CONTAINER}' not found"
        return (True, f"{MYSQL_CONTAINER} running") if r.stdout.decode().strip() == "true" \
               else (False, f"Container '{MYSQL_CONTAINER}' not running")
    except FileNotFoundError:
        return False, "docker command not found"
    except Exception as e:
        return False, str(e)

# ── SQL value helpers ──────────────────────────────────────────────────────────

def esc(val) -> str:
    if val is None:
        return "NULL"
    s = (str(val)
         .replace(" ", " ")
         .replace("\r\n", "\n")
         .replace("\r", "\n")
         .strip())
    if not s:
        return "NULL"
    s = s.replace("\n", " ").replace("\t", " ")
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"

def to_int(val) -> str:
    if val is None:
        return "NULL"
    v = str(val).strip()
    if not v:
        return "NULL"
    try:
        return str(int(float(v)))
    except Exception:
        return "NULL"

def to_bool01(val) -> str:
    if val is None:
        return "NULL"
    v = str(val).strip().lower()
    if v in {"1", "true", "t", "yes", "y"}:
        return "1"
    if v in {"0", "false", "f", "no", "n"}:
        return "0"
    return "NULL"

def to_float(val) -> str:
    if val is None:
        return "NULL"
    v = str(val).strip()
    if not v or v == "*******":
        return "NULL"
    try:
        return str(float(v))
    except Exception:
        return "NULL"

_DT_FMTS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y %I:%M %p",
]

def to_dt(val) -> str:
    if not val:
        return "NULL"
    s = str(val).strip()
    if not s:
        return "NULL"
    for fmt in _DT_FMTS:
        try:
            dt = datetime.strptime(s, fmt)
            return f"'{dt.strftime('%Y-%m-%d %H:%M:%S')}'"
        except ValueError:
            pass
    return esc(s)

_COURSE_ID_RE = re.compile(r"/courses/(\d+)")
_JSON_META_RE = re.compile(r'^\s*\{.*"ImportId".*\}\s*$', re.IGNORECASE)
_QCOL_RE      = re.compile(r"^Q(\d+)$", re.IGNORECASE)
_SCALE_TYPES  = {"satisfaction_scale", "satisfaction_scale_with_comment"}

def _extract_canvas_id(course_url: str) -> str:
    """Extract Canvas course ID from /courses/<id>/... URL. Returns 0 if not found."""
    if not course_url:
        return "0"
    m = _COURSE_ID_RE.search(course_url)
    return str(int(m.group(1))) if m else "0"

def _db_null(s: str) -> bool:
    return s in ("NULL", "\\N", "")

# ── Qualtrics CSV parser ────────────────────────────────────────────────────────

def _is_json_meta_row(row: Dict[str, str]) -> bool:
    return sum(1 for v in row.values() if v and _JSON_META_RE.match(v)) >= 2

def _is_label_row(row: Dict[str, str]) -> bool:
    # Row 2 of every Qualtrics export has human-readable column names.
    # Detect it by checking for a cluster of well-known label values.
    hints = {
        "ResponseId":   {"Response ID"},
        "IPAddress":    {"IP Address"},
        "Finished":     {"Finished"},
        "RecordedDate": {"Recorded Date"},
        "UserLanguage": {"User Language"},
    }
    return sum(1 for k, v in hints.items() if (row.get(k) or "").strip() in v) >= 2


def parse_qualtrics(content: str) -> Dict:
    """
    Parse a Qualtrics 3-row-header CSV export.

    Returns:
        questions  {col_name: label_text}  e.g. {"Q1": "How satisfied…"}
        q_cols     ["Q1", "Q2", …]  in CSV order
        has_labels True when Q answers are text labels; False when numeric
        rows       list of clean data dicts (header rows stripped)
        error      str or None
    """
    try:
        reader = csv.DictReader(io.StringIO(content))
        fieldnames = list(reader.fieldnames or [])
    except Exception as e:
        return {"error": f"CSV parse error: {e}",
                "questions": {}, "q_cols": [], "has_labels": False, "rows": []}

    q_cols: List[str] = [c for c in fieldnames if _QCOL_RE.match(c)]
    questions: Dict[str, str] = {}
    data_rows: List[Dict[str, str]] = []

    for row in reader:
        if _is_label_row(row):
            for qc in q_cols:
                label = (row.get(qc) or "").strip()
                if label:
                    questions[qc] = label
            continue
        if _is_json_meta_row(row):
            continue
        rid = (row.get("ResponseId") or "").strip()
        if not rid:
            continue
        data_rows.append(dict(row))

    # Detect format: "with labels" if Q1 value isn't purely numeric
    has_labels = False
    if data_rows and q_cols:
        q1_val = (data_rows[0].get(q_cols[0]) or "").strip()
        has_labels = bool(q1_val) and not re.match(r"^\d+$", q1_val)

    return {
        "questions":  questions,
        "q_cols":     q_cols,
        "has_labels": has_labels,
        "rows":       data_rows,
        "error":      None,
    }

# ── DB query helpers ───────────────────────────────────────────────────────────

def _get_surveys() -> List[Dict]:
    ok, rows = _mysql_query(
        "SELECT Survey_ID, Title, Description, Status FROM `Surveys` ORDER BY Title;"
    )
    if not ok:
        return []
    return [
        {"id": r[0], "title": r[1],
         "description": r[2] if len(r) > 2 and not _db_null(r[2]) else "",
         "status":      r[3] if len(r) > 3 and not _db_null(r[3]) else ""}
        for r in rows
    ]

def _get_question_types() -> List[Dict]:
    ok, rows = _mysql_query(
        "SELECT Type_ID, Type_Name FROM `Question_Types` ORDER BY Type_ID;"
    )
    if not ok:
        return []
    return [{"id": r[0], "name": r[1] if len(r) > 1 else r[0]} for r in rows]

def _get_questions(survey_id: str) -> Dict[str, Dict]:
    """Return {question_number_str: {id, type}} for the given survey."""
    ok, rows = _mysql_query(
        f"SELECT Question_Number, Question_ID, Question_Type "
        f"FROM `Survey_Questions` WHERE Survey_ID = {esc(survey_id)} ORDER BY Question_Order;"
    )
    if not ok:
        return {}
    result: Dict[str, Dict] = {}
    for r in rows:
        if len(r) < 2:
            continue
        qtype = "" if (len(r) < 3 or _db_null(r[2])) else r[2]
        result[r[0]] = {"id": int(r[1]), "type": qtype}
    return result

def _get_existing_ids(survey_id: str) -> Set[str]:
    ok, rows = _mysql_query(
        f"SELECT Response_ID FROM `Survey_Responses` WHERE Survey_ID = {esc(survey_id)};"
    )
    if not ok:
        return set()
    return {r[0] for r in rows if r}

# ── SQL builders ───────────────────────────────────────────────────────────────

def _build_create_survey_sql(survey_id: str, title: str, description: str,
                              questions: List[Dict]) -> str:
    lines = [f"USE `{DB_NAME}`;", "SET NAMES utf8mb4;", ""]
    lines += [
        "INSERT INTO `Surveys` (Survey_ID, Title, Description, Status) VALUES",
        f"  ({esc(survey_id)}, {esc(title)}, {esc(description or '')}, 'Active')",
        "ON DUPLICATE KEY UPDATE Title = VALUES(Title), Description = VALUES(Description);",
        "",
    ]
    if questions:
        qvals = []
        for q in questions:
            qtype = esc(q["type"]) if q.get("type") else "NULL"
            qvals.append(
                f"({esc(survey_id)}, {esc(str(q['number']))}, {esc(q['text'])}, "
                f"{qtype}, {int(q['order'])})"
            )
        lines += [
            "INSERT INTO `Survey_Questions`"
            " (Survey_ID, Question_Number, Question_Text, Question_Type, Question_Order)"
            " VALUES",
            "  " + ",\n  ".join(qvals),
            "ON DUPLICATE KEY UPDATE"
            " Question_Text = VALUES(Question_Text),"
            " Question_Type = VALUES(Question_Type);",
            "",
        ]
    return "\n".join(lines)


def _build_import_sql(
    data_rows: List[Dict],
    survey_id: str,
    q_cols: List[str],
    question_info: Dict[str, Dict],
    existing_ids: Set[str],
) -> Tuple[str, int, int]:
    """
    Build INSERT SQL for responses not already in DB.
    Returns (sql, new_count, skipped_count).
    """
    new_rows = [
        r for r in data_rows
        if (r.get("ResponseId") or "").strip() not in existing_ids
    ]
    skipped = len(data_rows) - len(new_rows)

    if not new_rows:
        return "", 0, skipped

    BATCH = 500
    lines = [f"USE `{DB_NAME}`;", "SET NAMES utf8mb4;", ""]

    # Survey_Responses
    resp_cols = (
        "(Response_ID, Survey_ID, StartDate, EndDate, Status, IPAddress, "
        "Progress, Duration, Finished, RecordedDate, LocationLatitude, "
        "LocationLongitude, DistributionChannel, UserLanguage, CanvasID)"
    )
    resp_vals = [
        f"({esc(r.get('ResponseId'))}, {esc(survey_id)}, "
        f"{to_dt(r.get('StartDate'))}, {to_dt(r.get('EndDate'))}, "
        f"{esc(r.get('Status'))}, {esc(r.get('IPAddress'))}, "
        f"{to_int(r.get('Progress'))}, {to_int(r.get('Duration') or r.get('Duration (in seconds)'))}, "
        f"{to_bool01(r.get('Finished'))}, {to_dt(r.get('RecordedDate'))}, "
        f"{to_float(r.get('LocationLatitude'))}, {to_float(r.get('LocationLongitude'))}, "
        f"{esc(r.get('DistributionChannel'))}, {esc(r.get('UserLanguage'))}, "
        f"{_extract_canvas_id(r.get('Course', ''))})"
        for r in new_rows
    ]
    for i in range(0, len(resp_vals), BATCH):
        chunk = resp_vals[i:i + BATCH]
        lines += [
            f"INSERT INTO `Survey_Responses` {resp_cols} VALUES",
            "  " + ",\n  ".join(chunk),
            "ON DUPLICATE KEY UPDATE Response_ID = Response_ID;",
            "",
        ]

    # Survey_Answers — only for questions that have a DB entry
    ans_vals: List[str] = []
    for r in new_rows:
        rid = (r.get("ResponseId") or "").strip()
        for qc in q_cols:
            m = _QCOL_RE.match(qc)
            if not m:
                continue
            qnum = m.group(1)
            info = question_info.get(qnum)
            if info is None:
                continue  # no Survey_Questions row for this column — skip
            db_qid = info["id"]
            qtype  = (info.get("type") or "").lower()
            qval   = (r.get(qc) or "").strip()
            if qtype in _SCALE_TYPES:
                selected, answer_text = esc(qval) if qval else "NULL", "NULL"
            else:
                selected, answer_text = "NULL", esc(qval) if qval else "NULL"
            ans_vals.append(f"({esc(rid)}, {db_qid}, {selected}, {answer_text})")

    if ans_vals:
        ans_cols = "(Response_ID, Question_ID, Selected_Option, Answer_Text)"
        for i in range(0, len(ans_vals), BATCH):
            chunk = ans_vals[i:i + BATCH]
            lines += [
                f"INSERT INTO `Survey_Answers` {ans_cols} VALUES",
                "  " + ",\n  ".join(chunk),
                ";",
                "",
            ]

    return "\n".join(lines), len(new_rows), skipped

# ── Multipart helpers ──────────────────────────────────────────────────────────

def _parse_multipart(data: bytes, content_type: str) -> List[Tuple[str, str]]:
    m = re.search(r'boundary=([^\s;]+)', content_type)
    if not m:
        return []
    boundary = m.group(1).strip('"').encode()
    results: List[Tuple[str, str]] = []
    for part in data.split(b"--" + boundary)[1:]:
        if part.startswith(b"--"):
            break
        if b"\r\n\r\n" not in part:
            continue
        raw_headers, body = part.split(b"\r\n\r\n", 1)
        body = body.rstrip(b"\r\n")
        headers_text = raw_headers.decode("utf-8", errors="replace")
        cd = re.search(r'filename="([^"]+)"', headers_text, re.IGNORECASE)
        if not cd:
            continue
        ct = re.search(r'charset=([\w-]+)', headers_text, re.IGNORECASE)
        enc = ct.group(1) if ct else "utf-8-sig"
        try:
            content = body.decode(enc, errors="replace")
        except LookupError:
            content = body.decode("utf-8-sig", errors="replace")
        results.append((cd.group(1), content))
    return results

def _parse_form_field(data: bytes, content_type: str, field_name: str) -> str:
    m = re.search(r'boundary=([^\s;]+)', content_type)
    if not m:
        return ""
    boundary = m.group(1).strip('"').encode()
    for part in data.split(b"--" + boundary)[1:]:
        if part.startswith(b"--"):
            break
        if b"\r\n\r\n" not in part:
            continue
        raw_headers, body = part.split(b"\r\n\r\n", 1)
        headers_text = raw_headers.decode("utf-8", errors="replace")
        cd = re.search(r'name="([^"]+)"', headers_text, re.IGNORECASE)
        if cd and cd.group(1) == field_name:
            return body.rstrip(b"\r\n").decode("utf-8", errors="replace").strip()
    return ""

# ── HTML ───────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Qualtrics Survey Import</title>
<style>
*, *::before, *::after { box-sizing: border-box; }
body { font-family: system-ui,-apple-system,sans-serif; max-width: 980px; margin: 40px auto; padding: 0 24px; color: #1a1a2e; background: #f8f9fa; }
h1   { font-size: 1.5rem; margin-bottom: 4px; }
.sub { color: #555; font-size: .9rem; margin-bottom: 24px; line-height: 1.5; }
code { background: #e8eaed; padding: 1px 5px; border-radius: 3px; font-size: .85em; }
a    { color: #0d6efd; }

/* status */
#db-status { font-size: .85rem; margin-bottom: 20px; }
.dot { display:inline-block; width:9px; height:9px; border-radius:50%; background:#aaa; margin-right:6px; vertical-align:middle; }
.dot.ok  { background:#28a745; }
.dot.err { background:#dc3545; }

/* survey selector */
.row { display:flex; align-items:center; gap:12px; margin-bottom:16px; flex-wrap:wrap; }
.row label { font-size:.9rem; font-weight:600; white-space:nowrap; }
select, input[type=text], textarea {
  border:1px solid #ced4da; border-radius:5px; padding:7px 10px;
  font-size:.9rem; background:#fff; color:#1a1a2e;
}
select { min-width:300px; cursor:pointer; }
.survey-desc { font-size:.8rem; color:#666; margin-top:2px; }

/* create-survey panel */
#create-panel {
  background:#fff; border:1px solid #dee2e6; border-radius:8px;
  padding:20px 24px; margin-bottom:20px;
}
#create-panel h2 { font-size:1rem; margin:0 0 14px; }
.form-row { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:12px; }
.form-row.full { grid-template-columns:1fr; }
.form-row label { font-size:.82rem; font-weight:600; display:block; margin-bottom:3px; }
.form-row input, .form-row textarea { width:100%; }
.form-row textarea { height:58px; resize:vertical; }

/* questions table inside create panel */
#q-table { width:100%; border-collapse:collapse; margin:12px 0; font-size:.84rem; }
#q-table th { background:#f1f3f5; padding:6px 10px; text-align:left; border-bottom:1px solid #dee2e6; }
#q-table td { padding:5px 8px; border-bottom:1px solid #f0f0f0; vertical-align:middle; }
#q-table input { width:100%; border:1px solid #e0e0e0; border-radius:4px; padding:4px 6px; font-size:.83rem; }
#q-table select { width:100%; font-size:.83rem; padding:4px 6px; }
.q-add-row { text-align:right; }

/* drop zone */
#drop-zone { border:3px dashed #adb5bd; border-radius:10px; padding:44px 24px; text-align:center; cursor:pointer; transition:border-color .15s,background .15s; background:#fff; margin-bottom:18px; }
#drop-zone.over      { border-color:#0d6efd; background:#e7f1ff; }
#drop-zone.has-file  { border-color:#198754; background:#f0fff4; }
#drop-zone p { margin:4px 0; color:#666; }
#drop-zone strong { color:#333; font-size:1.05rem; }
#file-input { display:none; }
.file-info { margin-top:10px; font-size:.85rem; display:flex; gap:8px; justify-content:center; align-items:center; flex-wrap:wrap; }

/* badges */
.badge { font-size:.72rem; font-weight:600; padding:2px 9px; border-radius:10px; }
.b-green  { background:#d1e7dd; color:#0f5132; }
.b-yellow { background:#fff3cd; color:#856404; }
.b-blue   { background:#cfe2ff; color:#084298; }
.b-grey   { background:#dee2e6; color:#495057; }
.b-orange { background:#ffe5d0; color:#7c3000; }

/* preview */
#preview-stats { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin-bottom:14px; }
.stat { font-size:.88rem; }

/* table */
table { width:100%; border-collapse:collapse; font-size:.82rem; background:#fff; border-radius:6px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.07); }
th { background:#f1f3f5; text-align:left; padding:6px 10px; border-bottom:1px solid #dee2e6; }
td { padding:5px 10px; border-bottom:1px solid #f0f0f0; }
tr:last-child td { border-bottom:none; }
.dup-row td { opacity:.45; }

/* buttons */
.btn { padding:8px 22px; border-radius:5px; border:none; font-size:.9rem; font-weight:600; cursor:pointer; }
.btn-primary   { background:#0d6efd; color:#fff; }
.btn-primary:disabled { background:#a0b4d0; cursor:not-allowed; }
.btn-secondary { background:#e9ecef; color:#333; }
.btn-success   { background:#198754; color:#fff; }
.btn-sm        { padding:5px 14px; font-size:.82rem; }

.actions { display:flex; gap:10px; align-items:center; margin-top:8px; }
#status  { font-size:.85rem; color:#555; margin:6px 0; min-height:1.2em; }

.result { margin-top:14px; padding:12px 16px; border-radius:6px; font-size:.9rem; line-height:1.6; }
.res-ok  { background:#d1e7dd; color:#0f5132; border:1px solid #badbcc; }
.res-err { background:#f8d7da; color:#842029; border:1px solid #f5c2c7; }
</style>
</head>
<body>

<h1>Qualtrics Survey Import</h1>
<p class="sub">
  Imports Qualtrics survey CSVs into <strong>Survey_Responses + Survey_Answers</strong>.<br>
  Both <em>Use Values</em> and <em>Use Labels</em> export formats are auto-detected.
  Duplicate <code>Response_ID</code>s already in the database are silently skipped.
</p>

<div id="db-status"><span class="dot" id="db-dot"></span><span id="db-lbl">Checking MySQL…</span></div>

<!-- ── Survey selector ──────────────────────────────────────────────────── -->
<div class="row">
  <label for="survey-select">Survey:</label>
  <div>
    <select id="survey-select">
      <option value="">— select a survey —</option>
    </select>
    <div id="survey-desc" class="survey-desc"></div>
  </div>
</div>

<!-- ── Create new survey panel ──────────────────────────────────────────── -->
<div id="create-panel" hidden>
  <h2>Create New Survey</h2>
  <div class="form-row">
    <div>
      <label for="new-id">Survey ID <span style="color:#dc3545">*</span>
        <span style="font-weight:normal;color:#888;">(unique key, no spaces)</span>
      </label>
      <input type="text" id="new-id" placeholder="e.g. ASIA_SP2026">
    </div>
    <div>
      <label for="new-title">Title <span style="color:#dc3545">*</span></label>
      <input type="text" id="new-title" placeholder="e.g. Asia Institute Spring 2026">
    </div>
  </div>
  <div class="form-row full">
    <div>
      <label for="new-desc">Description <span style="font-weight:normal;color:#888;">(optional)</span></label>
      <textarea id="new-desc" placeholder="Brief description of this survey…"></textarea>
    </div>
  </div>

  <label style="font-size:.85rem;font-weight:600;">Questions
    <span style="font-weight:normal;color:#888;">(auto-detected from uploaded file — edit as needed)</span>
  </label>
  <table id="q-table">
    <thead>
      <tr>
        <th style="width:44px">#</th>
        <th>Question Text</th>
        <th style="width:230px">Type</th>
        <th style="width:36px"></th>
      </tr>
    </thead>
    <tbody id="q-tbody"></tbody>
  </table>
  <div class="q-add-row">
    <button class="btn btn-secondary btn-sm" onclick="addQuestionRow()">+ Add question</button>
  </div>

  <div class="actions" style="margin-top:16px;">
    <button class="btn btn-success" id="btn-create" onclick="createSurvey()">Create Survey</button>
    <button class="btn btn-secondary btn-sm" onclick="cancelCreate()">Cancel</button>
    <span id="create-status" style="font-size:.85rem;color:#555;"></span>
  </div>
</div>

<!-- ── Drop zone ────────────────────────────────────────────────────────── -->
<div id="drop-zone" onclick="document.getElementById('file-input').click()">
  <input type="file" id="file-input" accept=".csv,.CSV">
  <p><strong>Drop Qualtrics CSV here</strong></p>
  <p style="font-size:.83rem;">or click to browse — both "Use Values" and "Use Labels" exports accepted</p>
  <div id="file-info" class="file-info"></div>
</div>

<!-- ── Preview ──────────────────────────────────────────────────────────── -->
<div id="preview-wrap" hidden>
  <div id="preview-stats"></div>
  <div id="preview-table"></div>
</div>

<!-- ── Actions ──────────────────────────────────────────────────────────── -->
<div class="actions">
  <button class="btn btn-primary" id="btn-import" disabled>Import to MySQL</button>
  <button class="btn btn-secondary" id="btn-clear">Clear</button>
</div>
<div id="status"></div>
<div id="result"></div>

<script>
const dropZone   = document.getElementById('drop-zone');
const fileInput  = document.getElementById('file-input');
const surveySelect = document.getElementById('survey-select');
const createPanel  = document.getElementById('create-panel');
const btnImport  = document.getElementById('btn-import');
const statusEl   = document.getElementById('status');
const resultEl   = document.getElementById('result');

let selectedFile   = null;
let surveyId       = '';     // '' | 'new' | 'SURVEY_ID_STR'
let previewData    = null;
let questionTypes  = [];
let surveyMap      = {};     // id → {title, description, status}
let detectedQs     = {};     // {Q1: label, Q2: label, …} from latest preview
let qRowCounter    = 0;

// ── Startup ───────────────────────────────────────────────────────────────────
fetch('/db-status').then(r=>r.json()).then(d=>{
  document.getElementById('db-dot').className = 'dot ' + (d.ok ? 'ok' : 'err');
  document.getElementById('db-lbl').textContent = d.ok
    ? `MySQL ready: ${d.db} @ ${d.container}`
    : `MySQL unavailable: ${d.error}`;
}).catch(()=>{ document.getElementById('db-lbl').textContent='Could not check MySQL'; });

Promise.all([fetch('/surveys').then(r=>r.json()), fetch('/question-types').then(r=>r.json())])
  .then(([surveys, qtypes]) => {
    questionTypes = qtypes;
    populateSurveys(surveys);
  }).catch(()=>{});

function populateSurveys(surveys) {
  surveyMap = {};
  const sel = surveySelect;
  // clear everything except the placeholder
  while (sel.options.length > 1) sel.remove(1);
  surveys.forEach(s => {
    surveyMap[s.id] = s;
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = `${s.title}  [${s.id}]`;
    sel.appendChild(opt);
  });
  const newOpt = document.createElement('option');
  newOpt.value = 'new';
  newOpt.textContent = '➕  Create new survey…';
  sel.appendChild(newOpt);
}

function refreshSurveys(autoSelectId) {
  fetch('/surveys').then(r=>r.json()).then(surveys => {
    populateSurveys(surveys);
    if (autoSelectId) {
      surveySelect.value = autoSelectId;
      surveySelect.dispatchEvent(new Event('change'));
    }
  }).catch(()=>{});
}

// ── Survey select ─────────────────────────────────────────────────────────────
surveySelect.addEventListener('change', () => {
  surveyId = surveySelect.value;
  const s  = surveyMap[surveyId];
  document.getElementById('survey-desc').textContent = s ? s.description || '' : '';
  createPanel.hidden = (surveyId !== 'new');
  if (surveyId === 'new' && Object.keys(detectedQs).length) {
    populateCreateForm(detectedQs);
  }
  if (surveyId && surveyId !== 'new' && selectedFile) doPreview();
  updateImportBtn();
});

// ── Create survey form ────────────────────────────────────────────────────────
function populateCreateForm(qs) {
  const tbody = document.getElementById('q-tbody');
  tbody.innerHTML = '';
  qRowCounter = 0;
  Object.entries(qs).forEach(([col, label], i) => {
    const m = col.match(/^Q(\d+)$/i);
    const num = m ? parseInt(m[1]) : (i + 1);
    // Auto-assign type: satisfaction_scale for Q1-Q3, null for Q4+
    const defaultType = num <= 3 ? 'satisfaction_scale' : '';
    addQuestionRow(num, label, defaultType);
  });
}

function addQuestionRow(num, text, type) {
  qRowCounter++;
  const tbody = document.getElementById('q-tbody');
  const tr    = document.createElement('tr');
  const qnum  = num || qRowCounter;
  const qtext = text || '';
  const qtype = type !== undefined ? type : '';
  const typeOptions = questionTypes.map(t =>
    `<option value="${t.id}"${qtype===t.id?' selected':''}>${t.name}</option>`
  ).join('');
  tr.dataset.num = qnum;
  tr.innerHTML = `
    <td><input type="number" value="${qnum}" min="1" style="width:44px;text-align:center;" onchange="this.closest('tr').dataset.num=this.value"></td>
    <td><input type="text" value="${escHtml(qtext)}" placeholder="Question text…"></td>
    <td>
      <select>
        <option value=""${!qtype?' selected':''}>— text / free response —</option>
        ${typeOptions}
      </select>
    </td>
    <td><span style="cursor:pointer;color:#aaa;font-size:1.1rem;" title="Remove" onclick="this.closest('tr').remove()">✕</span></td>
  `;
  tbody.appendChild(tr);
}

function cancelCreate() {
  createPanel.hidden = true;
  surveySelect.value = '';
  surveyId = '';
  updateImportBtn();
}

async function createSurvey() {
  const sid   = document.getElementById('new-id').value.trim();
  const title = document.getElementById('new-title').value.trim();
  const desc  = document.getElementById('new-desc').value.trim();
  const statusSpan = document.getElementById('create-status');
  if (!sid)   { statusSpan.textContent = '⚠ Survey ID is required.'; return; }
  if (!title) { statusSpan.textContent = '⚠ Title is required.'; return; }

  const questions = [];
  document.querySelectorAll('#q-tbody tr').forEach((tr, i) => {
    const inputs  = tr.querySelectorAll('input, select');
    const num     = parseInt(tr.dataset.num) || (i + 1);
    const text    = inputs[1] ? inputs[1].value.trim() : '';
    const type    = inputs[2] ? inputs[2].value : '';
    if (text) questions.push({ number: num, text, type: type || null, order: num });
  });

  statusSpan.textContent = 'Creating…';
  document.getElementById('btn-create').disabled = true;
  try {
    const res = await fetch('/survey/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ survey_id: sid, title, description: desc, questions }),
    }).then(r => r.json());

    if (res.error) {
      statusSpan.textContent = '✖ ' + res.error;
    } else {
      statusSpan.textContent = '✔ Survey created.';
      createPanel.hidden = true;
      refreshSurveys(sid);
    }
  } catch(e) {
    statusSpan.textContent = '✖ Network error.';
  }
  document.getElementById('btn-create').disabled = false;
}

// ── File handling ─────────────────────────────────────────────────────────────
dropZone.addEventListener('dragover',  e => { e.preventDefault(); dropZone.classList.add('over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('over');
  const f = e.dataTransfer.files[0];
  if (f) setFile(f);
});
fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) setFile(fileInput.files[0]);
  fileInput.value = '';
});

function setFile(f) {
  if (!f.name.match(/\.csv$/i)) {
    statusEl.textContent = '⚠ Please drop a .csv file.';
    return;
  }
  selectedFile = f;
  dropZone.classList.add('has-file');
  document.getElementById('file-info').innerHTML =
    `<strong>${escHtml(f.name)}</strong> <span style="color:#888;">(${(f.size/1024).toFixed(1)} KB)</span>`;
  if (surveyId && surveyId !== 'new') doPreview();
  updateImportBtn();
}

// ── Preview ───────────────────────────────────────────────────────────────────
async function doPreview() {
  if (!selectedFile) return;
  statusEl.textContent = 'Parsing file…';
  document.getElementById('preview-wrap').hidden = true;
  btnImport.disabled = true;
  resultEl.innerHTML = '';

  const fd = new FormData();
  fd.append('file', selectedFile, selectedFile.name);
  if (surveyId && surveyId !== 'new') fd.append('survey_id', surveyId);

  let d;
  try {
    d = await fetch('/preview', { method: 'POST', body: fd }).then(r => r.json());
  } catch(e) {
    statusEl.textContent = '✖ Preview request failed.';
    return;
  }
  if (d.error) { statusEl.textContent = '✖ ' + d.error; return; }

  previewData  = d;
  detectedQs   = d.questions || {};

  // If "create new" selected, populate questions from preview
  if (surveyId === 'new' && Object.keys(detectedQs).length) {
    populateCreateForm(detectedQs);
  }

  // Stats bar
  const fmt = d.has_labels ? '📝 With Labels' : '🔢 Numeric Values';
  const fmtBadge = `<span class="badge b-blue">${fmt}</span>`;
  const newBadge = `<span class="badge b-green">✚ ${d.new_count} new</span>`;
  const skipBadge = d.skipped > 0
    ? `<span class="badge b-orange">⟳ ${d.skipped} already imported</span>` : '';
  const totalBadge = `<span class="badge b-grey">${d.total} total</span>`;
  document.getElementById('preview-stats').innerHTML =
    `<span class="stat">${fmtBadge}</span>
     <span class="stat">${totalBadge}</span>
     <span class="stat">${newBadge}</span>
     <span class="stat">${skipBadge}</span>`;

  // Sample table
  const qCols = d.q_cols || [];
  const qHeaders = qCols.map(q => `<th title="${escHtml(detectedQs[q]||q)}">${q}</th>`).join('');
  const rows = (d.sample || []).map(r => {
    const isDup = r._dup;
    const qCells = qCols.map(q => `<td>${escHtml((r[q]||'').substring(0,35))}</td>`).join('');
    return `<tr class="${isDup?'dup-row':''}">
      <td><code>${escHtml(r.ResponseId||'')}</code></td>
      <td>${escHtml((r.RecordedDate||'').substring(0,10))}</td>
      <td>${r._canvas||''}</td>
      ${qCells}
      <td>${isDup?'<span class="badge b-grey">skip</span>':'<span class="badge b-green">new</span>'}</td>
    </tr>`;
  }).join('');

  document.getElementById('preview-table').innerHTML = `
    <table>
      <tr><th>Response ID</th><th>Date</th><th>Canvas ID</th>${qHeaders}<th>Status</th></tr>
      ${rows}
      ${d.total > d.sample.length ? `<tr><td colspan="${4+qCols.length}" style="text-align:center;color:#888;">…${d.total - d.sample.length} more rows</td></tr>` : ''}
    </table>`;
  document.getElementById('preview-wrap').hidden = false;
  statusEl.textContent = '';
  updateImportBtn();
}

function updateImportBtn() {
  btnImport.disabled = !(selectedFile && surveyId && surveyId !== 'new' && previewData && previewData.new_count > 0);
}

// ── Import ────────────────────────────────────────────────────────────────────
btnImport.addEventListener('click', async () => {
  btnImport.disabled = true;
  resultEl.innerHTML = '';
  statusEl.textContent = 'Importing…';

  const fd = new FormData();
  fd.append('file', selectedFile, selectedFile.name);
  fd.append('survey_id', surveyId);

  let d;
  try {
    d = await fetch('/import', { method: 'POST', body: fd }).then(r => r.json());
  } catch(e) {
    statusEl.textContent = '';
    resultEl.innerHTML = '<div class="result res-err">✖ Network error during import.</div>';
    btnImport.disabled = false;
    return;
  }
  statusEl.textContent = '';
  if (d.error) {
    resultEl.innerHTML = `<div class="result res-err">✖ ${escHtml(d.error)}</div>`;
  } else {
    resultEl.innerHTML = `<div class="result res-ok">
      ✔ Import complete<br>
      Responses inserted: <strong>${d.responses}</strong> &nbsp;|&nbsp;
      Answers inserted: <strong>${d.answers}</strong> &nbsp;|&nbsp;
      Skipped (already in DB): <strong>${d.skipped}</strong>
    </div>`;
    // Refresh preview to reflect updated DB state
    setTimeout(() => doPreview(), 300);
  }
  btnImport.disabled = false;
});

// ── Clear ─────────────────────────────────────────────────────────────────────
document.getElementById('btn-clear').addEventListener('click', () => {
  selectedFile = null;
  previewData  = null;
  detectedQs   = {};
  dropZone.classList.remove('has-file');
  document.getElementById('file-info').innerHTML = '';
  document.getElementById('preview-wrap').hidden = true;
  document.getElementById('preview-stats').innerHTML = '';
  document.getElementById('preview-table').innerHTML = '';
  statusEl.textContent = '';
  resultEl.innerHTML   = '';
  btnImport.disabled   = true;
});

// ── Utilities ─────────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
</script>
</body>
</html>
"""

# ── HTTP handler ───────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send_json(self, data: dict, code: int = 200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def do_GET(self):
        if self.path == "/":
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/db-status":
            ok, msg = _container_running()
            self._send_json({"ok": ok, "container": MYSQL_CONTAINER,
                             "db": DB_NAME, "error": msg if not ok else ""})

        elif self.path == "/surveys":
            self._send_json(_get_surveys())

        elif self.path == "/question-types":
            self._send_json(_get_question_types())

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        ct   = self.headers.get("Content-Type", "")
        data = self._read_body()

        # ── Create survey (JSON body) ─────────────────────────────────────────
        if self.path == "/survey/create":
            try:
                body = json.loads(data.decode("utf-8"))
            except Exception:
                self._send_json({"error": "Invalid JSON"}, 400)
                return
            sid   = (body.get("survey_id") or "").strip()
            title = (body.get("title") or "").strip()
            desc  = (body.get("description") or "").strip()
            qs    = body.get("questions") or []
            if not sid:
                self._send_json({"error": "survey_id is required"})
                return
            if not title:
                self._send_json({"error": "title is required"})
                return
            sql = _build_create_survey_sql(sid, title, desc, qs)
            ok, msg = _mysql_cmd(sql)
            if not ok:
                self._send_json({"error": f"MySQL error: {msg}"})
                return
            self._send_json({"ok": True, "survey_id": sid})
            return

        # ── Multipart routes ──────────────────────────────────────────────────
        if "multipart/form-data" not in ct:
            self._send_json({"error": "Expected multipart/form-data"}, 400)
            return

        parts = _parse_multipart(data, ct)
        if not parts:
            self._send_json({"error": "No file found in upload"})
            return
        filename, content = parts[0]

        parsed = parse_qualtrics(content)
        if parsed["error"]:
            self._send_json({"error": parsed["error"]})
            return
        if not parsed["rows"]:
            self._send_json({"error": "No data rows found in CSV — "
                             "check that this is a Qualtrics export."})
            return

        survey_id = _parse_form_field(data, ct, "survey_id").strip()

        # ── Preview ───────────────────────────────────────────────────────────
        if self.path == "/preview":
            rows = parsed["rows"]
            existing: Set[str] = _get_existing_ids(survey_id) if survey_id else set()

            SAMPLE_N = 10
            sample = []
            for r in rows[:SAMPLE_N + len(existing)]:
                rid  = (r.get("ResponseId") or "").strip()
                is_dup = rid in existing
                entry  = {k: v for k, v in r.items()}
                entry["_dup"]    = is_dup
                entry["_canvas"] = _extract_canvas_id(r.get("Course", ""))
                sample.append(entry)
                if len([x for x in sample if not x["_dup"]]) >= SAMPLE_N and len(sample) >= SAMPLE_N:
                    break

            new_count = sum(1 for r in rows if (r.get("ResponseId") or "").strip() not in existing)
            self._send_json({
                "total":      len(rows),
                "new_count":  new_count,
                "skipped":    len(rows) - new_count,
                "questions":  parsed["questions"],
                "q_cols":     parsed["q_cols"],
                "has_labels": parsed["has_labels"],
                "sample":     sample,
            })

        # ── Import ────────────────────────────────────────────────────────────
        elif self.path == "/import":
            if not survey_id:
                self._send_json({"error": "No survey_id provided"})
                return

            existing     = _get_existing_ids(survey_id)
            question_info = _get_questions(survey_id)

            sql, new_count, skipped = _build_import_sql(
                parsed["rows"], survey_id,
                parsed["q_cols"], question_info, existing,
            )
            if not sql:
                self._send_json({"responses": 0, "answers": 0, "skipped": skipped})
                return

            ok, msg = _mysql_cmd(sql)
            if not ok:
                self._send_json({"error": f"MySQL error: {msg}"})
                return

            # Count answers inserted (estimate: new_count × matched questions)
            matched_qs = sum(
                1 for qc in parsed["q_cols"]
                if (m := _QCOL_RE.match(qc)) and m.group(1) in question_info
            )
            ans_count = new_count * matched_qs
            self._send_json({
                "responses": new_count,
                "answers":   ans_count,
                "skipped":   skipped,
            })

        else:
            self.send_response(404)
            self.end_headers()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ok, msg    = _container_running()
    surveys    = _get_surveys()
    print(f"Qualtrics Survey Import → http://localhost:{PORT}")
    print(f"MySQL  : {MYSQL_CONTAINER} ({'running' if ok else 'NOT RUNNING — ' + msg})")
    print(f"DB     : {DB_NAME}")
    print(f"Surveys: {len(surveys)} in database")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
