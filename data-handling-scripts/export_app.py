#!/usr/bin/env python3
"""
Term Data Export Tool  —  port 5003

Zero external dependencies — Python stdlib only.
Queries MySQL via docker exec and builds a portable SQL INSERT script
for all enrollment and survey data belonging to selected terms.

The generated SQL is idempotent: safe to run on a fresh target database
or one that already has some of the data.

Usage:
    python3 export_app.py
    # open http://localhost:5003
"""

import json
import os
import re
import subprocess
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
PORT             = int(os.environ.get("EXPORT_PORT", 5003))

# ── MySQL helpers ──────────────────────────────────────────────────────────────

def _mysql_query(sql: str) -> Tuple[bool, List[List[str]]]:
    """Run a SELECT; return (ok, rows) where each row is a list of strings.
    MySQL NULL cells arrive as the two-character literal '\\N'."""
    cmd = [
        "docker", "exec", "-i", MYSQL_CONTAINER,
        "mysql", "--batch", "--skip-column-names",
        "-uroot", f"-p{DB_ROOT_PASSWORD}", DB_NAME,
    ]
    try:
        r = subprocess.run(cmd, input=sql.encode("utf-8"),
                           capture_output=True, timeout=30)
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
            capture_output=True, timeout=5,
        )
        if r.returncode != 0:
            return False, f"Container '{MYSQL_CONTAINER}' not found"
        running = r.stdout.decode().strip() == "true"
        return (True, f"{MYSQL_CONTAINER} running") if running \
               else (False, f"Container '{MYSQL_CONTAINER}' not running")
    except FileNotFoundError:
        return False, "docker not found — is Docker running?"
    except Exception as e:
        return False, str(e)

# ── SQL value formatting ───────────────────────────────────────────────────────

_NULL = r"\N"  # MySQL --batch NULL sentinel (backslash + N, 2 chars)

def _s(v: str) -> str:
    """Format a mysql --batch cell as a SQL string literal, or NULL.

    MySQL --batch represents NULL as '\\N' per the spec, but MySQL 8 on ARM
    (and some other builds) outputs the literal word 'NULL' instead.
    We handle both. MySQL also escapes special characters in string values:
      \\  → backslash,  \\n → newline,  \\t → tab,  \\r → CR,  \\0 → NUL
    We must un-escape those before re-escaping for a SQL string literal.
    """
    if v == _NULL or v == "NULL":
        return "NULL"
    # Un-escape MySQL --batch output sequences to recover the actual string.
    # Use a placeholder so we don't double-process the backslash character.
    actual = (v
        .replace("\\\\", "\x00")   # escaped backslash  → temp placeholder
        .replace("\\n",  "\n")     # escaped newline
        .replace("\\r",  "\r")     # escaped carriage return
        .replace("\\t",  "\t")     # escaped tab
        .replace("\\0",  "\x00")   # escaped NUL (rare; will survive below)
        .replace("\x00", "\\")     # restore backslash from placeholder
    )
    # Re-escape for a MySQL SQL string literal.
    escaped = actual.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"

def _n(v: str) -> str:
    """Format a numeric cell (int/decimal), or NULL."""
    if v == _NULL or v == "NULL" or v.strip() == "":
        return "NULL"
    return v.strip()

def _in_list(values: List[str]) -> str:
    """Build a SQL IN list of string literals from a list of plain strings."""
    return ", ".join(_s(v) for v in values)

# ── SQL generation (one function per table) ────────────────────────────────────

def _chunked(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

BATCH = 500


def _gen_question_types(rows: List[List[str]]) -> List[str]:
    if not rows:
        return []
    out = ["-- Question_Types"]
    for chunk in _chunked(rows, BATCH):
        vals = ",\n  ".join(
            f"({_s(r[0])}, {_s(r[1])}, {_s(r[2])})"
            for r in chunk
        )
        out.append(
            f"INSERT IGNORE INTO `Question_Types` (Type_ID, Type_Name, Description)\nVALUES\n  {vals};"
        )
    return out


def _gen_terms(rows: List[List[str]]) -> List[str]:
    if not rows:
        return []
    out = ["-- Terms"]
    for chunk in _chunked(rows, BATCH):
        vals = ",\n  ".join(
            f"({_s(r[0])}, {_s(r[1])}, {_s(r[2])}, {_s(r[3])})"
            for r in chunk
        )
        out.append(
            "INSERT INTO `Terms` (TermCode, Term, StartDate, EndDate)\nVALUES\n  "
            + vals
            + "\nON DUPLICATE KEY UPDATE Term=VALUES(Term), StartDate=VALUES(StartDate), EndDate=VALUES(EndDate);"
        )
    return out


def _gen_courses(rows: List[List[str]]) -> List[str]:
    if not rows:
        return []
    out = ["-- Courses"]
    for chunk in _chunked(rows, BATCH):
        vals = ",\n  ".join(
            f"({_n(r[0])}, {_s(r[1])}, {_s(r[2])}, {_s(r[3])}, {_s(r[4])}, {_s(r[5])}, {_s(r[6])}, {_n(r[7])})"
            for r in chunk
        )
        out.append(
            "INSERT INTO `Courses` (CanvasID, CourseName, Instructor, URL, Course, TermCode, CourseSISID, CntStudents)\nVALUES\n  "
            + vals
            + "\nON DUPLICATE KEY UPDATE CourseName=VALUES(CourseName), Instructor=VALUES(Instructor),"
              " URL=VALUES(URL), Course=VALUES(Course), CourseSISID=VALUES(CourseSISID), CntStudents=VALUES(CntStudents);"
        )
    return out


def _gen_people(rows: List[List[str]]) -> List[str]:
    if not rows:
        return []
    out = ["-- People"]
    for chunk in _chunked(rows, BATCH):
        vals = ",\n  ".join(
            f"({_s(r[0])}, {_s(r[1])}, {_s(r[2])}, {_s(r[3])})"
            for r in chunk
        )
        out.append(
            "INSERT INTO `People` (EMPL_ID, Name, Login_ID, Role)\nVALUES\n  "
            + vals
            + "\nON DUPLICATE KEY UPDATE Name=VALUES(Name), Login_ID=VALUES(Login_ID), Role=VALUES(Role);"
        )
    return out


def _gen_enrollment(canvas_ids: List[str], rows: List[List[str]]) -> List[str]:
    if not canvas_ids:
        return []
    out = ["-- Enrollment  (DELETE + INSERT per course — full replacement)"]
    id_list = ", ".join(canvas_ids)
    out.append(f"DELETE FROM `Enrollment` WHERE CanvasID IN ({id_list});")
    for chunk in _chunked(rows, BATCH):
        vals = ",\n  ".join(
            f"({_n(r[0])}, {_s(r[1])}, {_s(r[2])})"
            for r in chunk
        )
        out.append(
            f"INSERT INTO `Enrollment` (CanvasID, Empl_ID, Role)\nVALUES\n  {vals};"
        )
    return out


def _gen_surveys(rows: List[List[str]]) -> List[str]:
    if not rows:
        return []
    out = ["-- Surveys"]
    for chunk in _chunked(rows, BATCH):
        vals = ",\n  ".join(
            f"({_s(r[0])}, {_s(r[1])}, {_s(r[2])}, {_s(r[3])}, {_s(r[4])}, {_n(r[5])})"
            for r in chunk
        )
        out.append(
            "INSERT INTO `Surveys` (Survey_ID, Title, Description, Created_At, Status, CanvasID)\nVALUES\n  "
            + vals
            + "\nON DUPLICATE KEY UPDATE Title=VALUES(Title), Status=VALUES(Status);"
        )
    return out


def _gen_survey_questions(rows: List[List[str]]) -> List[str]:
    if not rows:
        return []
    out = ["-- Survey_Questions  (INSERT IGNORE preserves existing question definitions)"]
    for chunk in _chunked(rows, BATCH):
        vals = ",\n  ".join(
            f"({_n(r[0])}, {_s(r[1])}, {_s(r[2])}, {_s(r[3])}, {_s(r[4])}, {_n(r[5])}, {_s(r[6])}, {_s(r[7])})"
            for r in chunk
        )
        out.append(
            "INSERT IGNORE INTO `Survey_Questions`"
            " (Question_ID, Survey_ID, Question_Number, Question_Text, Question_Type, Question_Order, Created_At, Updated_At)\n"
            f"VALUES\n  {vals};"
        )
    return out


def _gen_survey_responses(rows: List[List[str]]) -> List[str]:
    if not rows:
        return []
    out = ["-- Survey_Responses  (INSERT IGNORE skips already-imported responses)"]
    cols = (
        "Response_ID, Survey_ID, StartDate, EndDate, Status, IPAddress, "
        "Progress, Duration, Finished, RecordedDate, "
        "LocationLatitude, LocationLongitude, DistributionChannel, "
        "UserLanguage, CanvasID, Created_At"
    )
    for chunk in _chunked(rows, BATCH):
        vals = ",\n  ".join(
            f"({_s(r[0])}, {_s(r[1])}, {_s(r[2])}, {_s(r[3])}, {_s(r[4])}, "
            f"{_s(r[5])}, {_n(r[6])}, {_n(r[7])}, {_n(r[8])}, {_s(r[9])}, "
            f"{_n(r[10])}, {_n(r[11])}, {_s(r[12])}, {_s(r[13])}, {_n(r[14])}, {_s(r[15])})"
            for r in chunk
        )
        out.append(
            f"INSERT IGNORE INTO `Survey_Responses` ({cols})\nVALUES\n  {vals};"
        )
    return out


def _gen_survey_answers(rows: List[List[str]]) -> List[str]:
    """Answers are inserted only for Response_IDs not already in Survey_Answers,
    preventing double-counting if the script is run more than once."""
    if not rows:
        return []
    out = [
        "-- Survey_Answers  (skips any Response_ID already present in target)"
    ]
    # Build per-chunk INSERT … SELECT … WHERE r NOT IN (existing)
    for chunk in _chunked(rows, BATCH):
        # Collect unique response_ids in this chunk for the NOT IN guard
        response_ids = list(dict.fromkeys(r[0] for r in chunk))
        rid_list = _in_list(response_ids)

        union_rows = "\n  UNION ALL SELECT ".join(
            f"{_s(r[0])}, {_n(r[1])}, {_s(r[2])}, {_s(r[3])}"
            for r in chunk
        )
        out.append(
            "INSERT INTO `Survey_Answers` (Response_ID, Question_ID, Selected_Option, Answer_Text)\n"
            "SELECT v.r, v.q, v.s, v.t FROM (\n"
            f"  SELECT {union_rows}\n"
            ") AS v (r, q, s, t)\n"
            f"WHERE v.r NOT IN (SELECT DISTINCT Response_ID FROM `Survey_Answers` WHERE Response_ID IN ({rid_list}));"
        )
    return out

# ── Schema guards ─────────────────────────────────────────────────────────────
# ADD COLUMN IF NOT EXISTS is MariaDB-only. For standard MySQL we use
# PREPARE/EXECUTE against information_schema, which works on MySQL 5.7+/8.x.

_SCHEMA_GUARD_COLS = [
    # (table, column, SQL definition)
    ("Terms",            "StartDate",           "date NULL"),
    ("Terms",            "EndDate",             "date NULL"),
    ("Courses",          "CourseName",          "varchar(50) NULL"),
    ("Courses",          "Instructor",          "varchar(100) NULL"),
    ("Courses",          "URL",                 "varchar(255) NULL"),
    ("Courses",          "Course",              "varchar(255) NULL"),
    ("Courses",          "CourseSISID",         "varchar(100) NULL"),
    ("Courses",          "CntStudents",         "int NULL"),
    ("People",           "Name",                "varchar(100) NULL"),
    ("People",           "Login_ID",            "varchar(50) NULL"),
    ("People",           "Role",                "varchar(50) NULL"),
    ("Surveys",          "Description",         "text NULL"),
    ("Surveys",          "Created_At",          "datetime NULL"),
    ("Surveys",          "Status",              "varchar(20) NULL"),
    ("Surveys",          "CanvasID",            "int NULL"),
    ("Survey_Questions", "Question_Type",       "varchar(50) NULL"),
    ("Survey_Questions", "Question_Order",      "int NULL"),
    ("Survey_Questions", "Created_At",          "datetime NULL"),
    ("Survey_Questions", "Updated_At",          "datetime NULL"),
    ("Survey_Responses", "StartDate",           "datetime NULL"),
    ("Survey_Responses", "EndDate",             "datetime NULL"),
    ("Survey_Responses", "Status",              "varchar(50) NULL"),
    ("Survey_Responses", "IPAddress",           "varchar(50) NULL"),
    ("Survey_Responses", "Progress",            "int NULL"),
    ("Survey_Responses", "Duration",            "int NULL"),
    ("Survey_Responses", "Finished",            "tinyint(1) NULL"),
    ("Survey_Responses", "RecordedDate",        "datetime NULL"),
    ("Survey_Responses", "LocationLatitude",    "decimal(10,7) NULL"),
    ("Survey_Responses", "LocationLongitude",   "decimal(10,7) NULL"),
    ("Survey_Responses", "DistributionChannel", "varchar(50) NULL"),
    ("Survey_Responses", "UserLanguage",        "varchar(10) NULL"),
    ("Survey_Responses", "CanvasID",            "int NULL"),
    ("Survey_Responses", "Created_At",          "datetime NULL"),
    ("Survey_Answers",   "Selected_Option",     "varchar(255) NULL"),
    ("Survey_Answers",   "Answer_Text",         "text NULL"),
]


def _gen_schema_guards() -> List[str]:
    """For each column in _SCHEMA_GUARD_COLS, emit a PREPARE/EXECUTE block that
    adds the column only when it does not already exist in the target schema."""
    out = [
        "-- Schema guards — adds any columns missing on the target schema.",
        "-- Uses information_schema + PREPARE/EXECUTE (MySQL 5.7+ / 8.x compatible).",
    ]
    for table, col, defn in _SCHEMA_GUARD_COLS:
        alter = f"ALTER TABLE `{table}` ADD COLUMN `{col}` {defn}"
        out.append(
            f"SET @_q = (SELECT IF(COUNT(*) = 0, '{alter}', 'SELECT 1')"
            f" FROM information_schema.COLUMNS"
            f" WHERE TABLE_SCHEMA = DATABASE()"
            f" AND TABLE_NAME = '{table}'"
            f" AND COLUMN_NAME = '{col}');"
        )
        out.append("PREPARE _s FROM @_q;")
        out.append("EXECUTE _s;")
        out.append("DEALLOCATE PREPARE _s;")
    return out


# ── Main export builder ────────────────────────────────────────────────────────

def build_export_sql(term_codes: List[str]) -> Tuple[bool, str]:
    """Query the database for all data belonging to term_codes and return SQL."""
    if not term_codes:
        return False, "No terms selected."

    tc_list = _in_list(term_codes)

    # ── 1. Terms ───────────────────────────────────────────────────────────────
    ok, term_rows = _mysql_query(
        f"SELECT TermCode, Term, StartDate, EndDate "
        f"FROM `Terms` WHERE TermCode IN ({tc_list}) ORDER BY TermCode;"
    )
    if not ok:
        return False, "Failed to query Terms."
    if not term_rows:
        return False, f"No terms found for codes: {', '.join(term_codes)}"

    # ── 2. Courses ─────────────────────────────────────────────────────────────
    ok, course_rows = _mysql_query(
        f"SELECT CanvasID, CourseName, Instructor, URL, Course, TermCode, CourseSISID, CntStudents "
        f"FROM `Courses` WHERE TermCode IN ({tc_list}) ORDER BY CanvasID;"
    )
    if not ok:
        return False, "Failed to query Courses."

    canvas_ids = [r[0] for r in course_rows]  # raw numeric strings

    # ── 3. Enrollment ──────────────────────────────────────────────────────────
    enroll_rows: List[List[str]] = []
    people_rows: List[List[str]] = []
    if canvas_ids:
        cid_list = ", ".join(canvas_ids)
        ok, enroll_rows = _mysql_query(
            f"SELECT CanvasID, Empl_ID, Role FROM `Enrollment` WHERE CanvasID IN ({cid_list}) ORDER BY CanvasID;"
        )
        if not ok:
            return False, "Failed to query Enrollment."

        # ── 4. People (only those enrolled in these courses) ───────────────────
        empl_ids = list(dict.fromkeys(r[1] for r in enroll_rows))
        if empl_ids:
            eid_list = _in_list(empl_ids)
            ok, people_rows = _mysql_query(
                f"SELECT EMPL_ID, Name, Login_ID, Role "
                f"FROM `People` WHERE EMPL_ID IN ({eid_list}) ORDER BY EMPL_ID;"
            )
            if not ok:
                return False, "Failed to query People."

    # ── 5. Survey_Responses ────────────────────────────────────────────────────
    response_rows: List[List[str]] = []
    answer_rows:   List[List[str]] = []
    survey_rows:   List[List[str]] = []
    question_rows: List[List[str]] = []
    qtype_rows:    List[List[str]] = []

    if canvas_ids:
        cid_list = ", ".join(canvas_ids)
        ok, response_rows = _mysql_query(
            f"SELECT Response_ID, Survey_ID, StartDate, EndDate, Status, IPAddress, "
            f"Progress, Duration, Finished, RecordedDate, "
            f"LocationLatitude, LocationLongitude, DistributionChannel, UserLanguage, "
            f"CanvasID, Created_At "
            f"FROM `Survey_Responses` WHERE CanvasID IN ({cid_list}) ORDER BY Response_ID;"
        )
        if not ok:
            return False, "Failed to query Survey_Responses."

    # ── 6. Survey_Answers ──────────────────────────────────────────────────────
    if response_rows:
        resp_ids = list(dict.fromkeys(r[0] for r in response_rows))
        rid_list = _in_list(resp_ids)
        ok, answer_rows = _mysql_query(
            f"SELECT sa.Response_ID, sa.Question_ID, sa.Selected_Option, sa.Answer_Text "
            f"FROM `Survey_Answers` sa "
            f"WHERE sa.Response_ID IN ({rid_list}) ORDER BY sa.Response_ID, sa.Question_ID;"
        )
        if not ok:
            return False, "Failed to query Survey_Answers."

        # ── 7. Surveys ─────────────────────────────────────────────────────────
        survey_ids = list(dict.fromkeys(r[1] for r in response_rows if r[1] != _NULL))
        if survey_ids:
            sid_list = _in_list(survey_ids)
            ok, survey_rows = _mysql_query(
                f"SELECT Survey_ID, Title, Description, Created_At, Status, CanvasID "
                f"FROM `Surveys` WHERE Survey_ID IN ({sid_list}) ORDER BY Survey_ID;"
            )
            if not ok:
                return False, "Failed to query Surveys."

            # ── 8. Survey_Questions ────────────────────────────────────────────
            ok, question_rows = _mysql_query(
                f"SELECT Question_ID, Survey_ID, Question_Number, Question_Text, "
                f"Question_Type, Question_Order, Created_At, Updated_At "
                f"FROM `Survey_Questions` WHERE Survey_ID IN ({sid_list}) ORDER BY Survey_ID, Question_Order;"
            )
            if not ok:
                return False, "Failed to query Survey_Questions."

            # ── 9. Question_Types ──────────────────────────────────────────────
            qtypes = list(dict.fromkeys(
                r[4] for r in question_rows if r[4] != _NULL
            ))
            if qtypes:
                qt_list = _in_list(qtypes)
                ok, qtype_rows = _mysql_query(
                    f"SELECT Type_ID, Type_Name, Description "
                    f"FROM `Question_Types` WHERE Type_ID IN ({qt_list}) ORDER BY Type_ID;"
                )
                if not ok:
                    return False, "Failed to query Question_Types."

    # ── Assemble SQL ───────────────────────────────────────────────────────────
    term_labels = ", ".join(r[1] for r in term_rows)
    generated   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sections: List[str] = [
        f"-- AIR Canvas MicroSurvey — Term Data Export",
        f"-- Generated : {generated}",
        f"-- Terms     : {term_labels}",
        f"-- TermCodes : {', '.join(term_codes)}",
        f"--",
        f"-- Tables included (dependency order):",
        f"--   Question_Types → Terms → Courses → People → Enrollment",
        f"--   Surveys → Survey_Questions → Survey_Responses → Survey_Answers",
        f"--",
        f"-- Idempotency:",
        f"--   Terms / Courses / People / Surveys : ON DUPLICATE KEY UPDATE",
        f"--   Survey_Questions / Question_Types  : INSERT IGNORE",
        f"--   Enrollment                         : DELETE + INSERT (full replacement per course)",
        f"--   Survey_Responses                   : INSERT IGNORE (skip existing Response_IDs)",
        f"--   Survey_Answers                     : skip Response_IDs already in target",
        f"",
        f"USE `{DB_NAME}`;",
        f"SET NAMES utf8mb4;",
        f"SET foreign_key_checks = 0;",
        f"",
        f"-- {'─' * 70}",
    ] + _gen_schema_guards() + [
        f"",
    ]

    def _section(label: str, lines: List[str]) -> None:
        if lines:
            sections.append(f"-- {'─' * 70}")
            sections.extend(lines)
            sections.append("")

    _section("Question_Types", _gen_question_types(qtype_rows))
    _section("Terms",           _gen_terms(term_rows))
    _section("Courses",         _gen_courses(course_rows))
    _section("People",          _gen_people(people_rows))
    _section("Enrollment",      _gen_enrollment(canvas_ids, enroll_rows))
    _section("Surveys",         _gen_surveys(survey_rows))
    _section("Survey_Questions",_gen_survey_questions(question_rows))
    _section("Survey_Responses",_gen_survey_responses(response_rows))
    _section("Survey_Answers",  _gen_survey_answers(answer_rows))

    sections.append("SET foreign_key_checks = 1;")

    summary_lines = [
        f"--",
        f"-- Export summary:",
        f"--   Terms             : {len(term_rows)}",
        f"--   Courses           : {len(course_rows)}",
        f"--   People            : {len(people_rows)}",
        f"--   Enrollment rows   : {len(enroll_rows)}",
        f"--   Surveys           : {len(survey_rows)}",
        f"--   Survey_Questions  : {len(question_rows)}",
        f"--   Survey_Responses  : {len(response_rows)}",
        f"--   Survey_Answers    : {len(answer_rows)}",
    ]
    sections.extend(["", ""] + summary_lines)

    return True, "\n".join(sections) + "\n"

# ── HTML ───────────────────────────────────────────────────────────────────────

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SQL Export — AIR Canvas MicroSurvey</title>
<style>
  :root {
    --bg:      #0f1117;
    --surface: #1a1d27;
    --border:  #2a2d3a;
    --accent:  #4f8ef7;
    --accent2: #38c97d;
    --danger:  #e05c5c;
    --text:    #e2e4ec;
    --muted:   #7a7f9a;
    --radius:  10px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 40px 20px 60px;
  }
  header { text-align: center; margin-bottom: 36px; }
  header h1 { font-size: 1.7rem; font-weight: 700; letter-spacing: -0.5px; }
  header p  { color: var(--muted); margin-top: 6px; font-size: 0.9rem; }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 28px 32px;
    width: 100%;
    max-width: 680px;
    margin-bottom: 20px;
  }
  .card-title {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--muted);
    margin-bottom: 16px;
  }

  /* Term list */
  #term-list { display: flex; flex-direction: column; gap: 10px; }
  .term-item {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 14px 16px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    cursor: pointer;
    transition: border-color .15s, background .15s;
    user-select: none;
  }
  .term-item:hover { border-color: var(--accent); background: #161923; }
  .term-item.selected { border-color: var(--accent); background: rgba(79,142,247,.07); }

  .term-item input[type=checkbox] {
    width: 18px; height: 18px; accent-color: var(--accent);
    cursor: pointer; flex-shrink: 0;
  }
  .term-label { flex: 1; }
  .term-name  { font-weight: 600; font-size: 0.95rem; }
  .term-code  { font-size: 0.78rem; color: var(--muted); margin-top: 2px; }
  .term-stats {
    font-size: 0.78rem; color: var(--muted);
    text-align: right; white-space: nowrap;
  }
  .term-stats span { display: block; }
  .stat-hi { color: var(--text); }

  .ctrl-row {
    display: flex; gap: 10px; margin-top: 14px;
  }
  .btn-link {
    font-size: 0.82rem; color: var(--accent);
    background: none; border: none; cursor: pointer; padding: 0;
    text-decoration: underline;
  }
  .btn-link:hover { color: #82b4ff; }

  /* Export button */
  .export-btn {
    display: flex; align-items: center; justify-content: center; gap: 10px;
    width: 100%; padding: 15px;
    background: var(--accent);
    color: #fff; font-size: 1rem; font-weight: 600;
    border: none; border-radius: 8px; cursor: pointer;
    transition: background .15s, opacity .15s;
    margin-top: 4px;
  }
  .export-btn:hover:not(:disabled) { background: #6fa3ff; }
  .export-btn:disabled { opacity: .45; cursor: not-allowed; }

  /* Includes list */
  .includes {
    display: grid; grid-template-columns: 1fr 1fr; gap: 6px 20px;
    margin-top: 2px;
  }
  .inc-item { font-size: 0.83rem; color: var(--muted); display: flex; align-items: center; gap: 6px; }
  .inc-item::before { content: "●"; color: var(--accent); font-size: 0.5rem; }

  /* Status */
  #status {
    width: 100%; max-width: 680px;
    padding: 12px 16px; border-radius: 8px;
    font-size: 0.88rem; font-weight: 500;
    display: none;
  }
  #status.ok    { background: rgba(56,201,125,.12); border: 1px solid rgba(56,201,125,.3); color: var(--accent2); }
  #status.error { background: rgba(224, 92, 92,.12); border: 1px solid rgba(224,92,92,.3); color: var(--danger); }
  #status.info  { background: rgba(79,142,247,.10); border: 1px solid rgba(79,142,247,.25); color: var(--accent); }

  .spinner {
    width: 18px; height: 18px;
    border: 2px solid rgba(255,255,255,.3);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin .7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .empty { color: var(--muted); font-size: 0.9rem; text-align: center; padding: 20px 0; }
  .db-offline { color: var(--danger); font-size: 0.88rem; }
</style>
</head>
<body>

<header>
  <h1>SQL Export Tool</h1>
  <p>Select terms to download enrollment and survey data as portable SQL</p>
</header>

<div class="card">
  <div class="card-title">Select Terms</div>
  <div id="term-list"><div class="empty">Loading terms…</div></div>
  <div class="ctrl-row">
    <button class="btn-link" onclick="selectAll()">Select all</button>
    <button class="btn-link" onclick="clearAll()">Clear all</button>
  </div>
</div>

<div class="card">
  <div class="card-title">Export</div>
  <button class="export-btn" id="export-btn" onclick="doExport()" disabled>
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="7 10 12 15 17 10"/>
      <line x1="12" y1="15" x2="12" y2="3"/>
    </svg>
    Download SQL Export
  </button>
  <div class="card-title" style="margin-top:22px; margin-bottom:10px">Includes (in dependency order)</div>
  <div class="includes">
    <div class="inc-item">Question_Types</div>
    <div class="inc-item">Survey_Responses</div>
    <div class="inc-item">Terms</div>
    <div class="inc-item">Survey_Answers</div>
    <div class="inc-item">Courses</div>
    <div class="inc-item">Surveys</div>
    <div class="inc-item">People</div>
    <div class="inc-item">Survey_Questions</div>
    <div class="inc-item">Enrollment</div>
  </div>
  <p style="margin-top:14px; font-size:0.8rem; color:var(--muted);">
    All INSERT statements are idempotent — safe to run on a target database that already has some of this data.
  </p>
</div>

<div id="status"></div>

<script>
let allTerms = [];

async function loadTerms() {
  try {
    const r = await fetch('/terms');
    const data = await r.json();
    if (!data.ok) {
      document.getElementById('term-list').innerHTML =
        '<div class="db-offline">⚠ ' + data.error + '</div>';
      return;
    }
    allTerms = data.terms;
    renderTerms();
  } catch (e) {
    document.getElementById('term-list').innerHTML =
      '<div class="db-offline">⚠ Could not reach the export server.</div>';
  }
}

function renderTerms() {
  const el = document.getElementById('term-list');
  if (!allTerms.length) {
    el.innerHTML = '<div class="empty">No terms found in the database.</div>';
    return;
  }
  el.innerHTML = allTerms.map(t => `
    <label class="term-item" id="item-${t.code}">
      <input type="checkbox" value="${t.code}" onchange="onCheck(this)">
      <div class="term-label">
        <div class="term-name">${t.label}</div>
        <div class="term-code">${t.code}</div>
      </div>
      <div class="term-stats">
        <span><span class="stat-hi">${t.courses}</span> courses</span>
        <span><span class="stat-hi">${t.enrollments}</span> enrollments</span>
        <span><span class="stat-hi">${t.responses}</span> survey responses</span>
      </div>
    </label>
  `).join('');
}

function onCheck(cb) {
  const item = cb.closest('.term-item');
  item.classList.toggle('selected', cb.checked);
  updateExportBtn();
}

function updateExportBtn() {
  const any = document.querySelectorAll('#term-list input:checked').length > 0;
  document.getElementById('export-btn').disabled = !any;
}

function selectAll() {
  document.querySelectorAll('#term-list input[type=checkbox]').forEach(cb => {
    cb.checked = true;
    cb.closest('.term-item').classList.add('selected');
  });
  updateExportBtn();
}

function clearAll() {
  document.querySelectorAll('#term-list input[type=checkbox]').forEach(cb => {
    cb.checked = false;
    cb.closest('.term-item').classList.remove('selected');
  });
  updateExportBtn();
}

function setStatus(msg, type) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = type;
  el.style.display = 'block';
}

async function doExport() {
  const codes = Array.from(
    document.querySelectorAll('#term-list input:checked')
  ).map(cb => cb.value);

  if (!codes.length) return;

  const btn = document.getElementById('export-btn');
  const origHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner"></div> Generating…';
  setStatus('Querying database — this may take a few seconds…', 'info');

  try {
    const r = await fetch('/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ term_codes: codes }),
    });

    if (!r.ok) {
      const err = await r.text();
      setStatus('Error: ' + err, 'error');
      return;
    }

    // Trigger file download from the response blob
    const blob = await r.blob();
    const cd    = r.headers.get('Content-Disposition') || '';
    const match = cd.match(/filename="([^"]+)"/);
    const fname = match ? match[1] : 'export.sql';

    const url = URL.createObjectURL(blob);
    const a   = document.createElement('a');
    a.href     = url;
    a.download = fname;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    const labels = codes.map(c => {
      const t = allTerms.find(x => x.code === c);
      return t ? t.label : c;
    }).join(', ');
    setStatus('Downloaded: ' + fname + ' (' + labels + ')', 'ok');
  } catch (e) {
    setStatus('Network error: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = origHtml;
  }
}

loadTerms();
</script>
</body>
</html>
"""

# ── HTTP handler ───────────────────────────────────────────────────────────────

class ExportHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, status: int = 200) -> None:
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    # GET /
    def _handle_root(self) -> None:
        body = _HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # GET /terms
    def _handle_terms(self) -> None:
        ok, msg = _container_running()
        if not ok:
            self._send_json({"ok": False, "error": msg})
            return

        ok, rows = _mysql_query(
            "SELECT t.TermCode, t.Term, "
            "COUNT(DISTINCT c.CanvasID) AS courses, "
            "COUNT(DISTINCT e.ID) AS enrollments, "
            "COUNT(DISTINCT sr.Response_ID) AS responses "
            "FROM `Terms` t "
            "LEFT JOIN `Courses` c ON c.TermCode = t.TermCode "
            "LEFT JOIN `Enrollment` e ON e.CanvasID = c.CanvasID "
            "LEFT JOIN `Survey_Responses` sr ON sr.CanvasID = c.CanvasID "
            "GROUP BY t.TermCode, t.Term "
            "ORDER BY t.TermCode DESC;"
        )
        if not ok:
            self._send_json({"ok": False, "error": "Failed to query terms."})
            return

        terms = [
            {
                "code":        r[0],
                "label":       r[1],
                "courses":     r[2],
                "enrollments": r[3],
                "responses":   r[4],
            }
            for r in rows
        ]
        self._send_json({"ok": True, "terms": terms})

    # POST /export
    def _handle_export(self) -> None:
        try:
            body = json.loads(self._read_body())
        except Exception:
            self._send_text("Invalid JSON body.", 400)
            return

        term_codes: List[str] = body.get("term_codes", [])
        if not term_codes:
            self._send_text("No term_codes provided.", 400)
            return

        # Sanitise: term codes should be short alphanumeric strings
        safe = re.compile(r'^[A-Za-z0-9_\-]+$')
        term_codes = [tc for tc in term_codes if safe.match(str(tc))]
        if not term_codes:
            self._send_text("Invalid term codes.", 400)
            return

        ok, sql = build_export_sql(term_codes)
        if not ok:
            self._send_text(sql, 500)  # sql contains the error message
            return

        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        codes_str = "-".join(sorted(term_codes))
        filename = f"export_{codes_str}_{ts}.sql"

        body_bytes = sql.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/":
            self._handle_root()
        elif path == "/terms":
            self._handle_terms()
        else:
            self._send_text("Not found.", 404)

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        if path == "/export":
            self._handle_export()
        else:
            self._send_text("Not found.", 404)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    server = HTTPServer(("", PORT), ExportHandler)
    print(f"\n  SQL Export Tool running at http://localhost:{PORT}")
    print(f"  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
