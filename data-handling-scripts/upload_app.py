#!/usr/bin/env python3
"""
Canvas Enrollment Drag-and-Drop Import Tool

Zero external dependencies — uses Python stdlib only.
Imports into MySQL via `docker exec` (mysql-container must be running).

Populates all four tables in dependency order:
  Terms → Courses → People → Enrollment

Course metadata (SIS ID, URL, term code) is read from Notes.md in the
same directory. Roster CSVs supply instructor name/ID, student count,
and the People + Enrollment rows.

Usage:
    python3 upload_app.py
    # open http://localhost:5001
"""

import json
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pipeline import (
    find_notes, parse_notes_md,
    canvas_id_from_filename, parse_roster_content,
    instructor, student_count, esc,
)

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
PORT             = int(os.environ.get("UPLOAD_PORT", 5001))

# ── SQL generation ─────────────────────────────────────────────────────────────

def build_sql(courses_data: List[Dict], term_label: str) -> str:
    """
    courses_data entries have keys:
      canvas_id, rows, notes (optional — course metadata from Notes.md)
    term_label is the human-readable term string (e.g. "Spring 2026").
    """
    lines = [f"USE `{DB_NAME}`;", "SET NAMES utf8mb4;", ""]

    # ── Terms ──────────────────────────────────────────────────────────────────
    term_codes = {
        c["notes"]["term_code"]
        for c in courses_data
        if c.get("notes") and term_label
    }
    if term_codes and term_label:
        vals = ", ".join(f"({esc(tc)}, {esc(term_label)})" for tc in sorted(term_codes))
        lines += [
            "INSERT INTO `Terms` (TermCode, Term) VALUES",
            f"  {vals}",
            "ON DUPLICATE KEY UPDATE Term = VALUES(Term);",
            "",
        ]

    # ── Courses ────────────────────────────────────────────────────────────────
    course_vals = []
    for c in courses_data:
        if not c.get("notes"):
            continue
        n          = c["notes"]
        instr_name, _ = instructor(c["rows"])
        cnt        = student_count(c["rows"])
        course_vals.append(
            f"({esc(n['canvas_id'])}, {esc(n['course_name'])}, {esc(instr_name)}, "
            f"{esc(n['url'])}, {esc(n['term_code'])}, {esc(n['sis_id'])}, {cnt})"
        )
    if course_vals:
        cols = "(CanvasID, CourseName, Instructor, URL, TermCode, CourseSISID, CntStudents)"
        lines += [
            f"INSERT INTO `Courses` {cols} VALUES",
            "  " + ",\n  ".join(course_vals),
            "ON DUPLICATE KEY UPDATE "
            "CourseName=VALUES(CourseName), Instructor=VALUES(Instructor), "
            "CntStudents=VALUES(CntStudents);",
            "",
        ]

    # ── People + Enrollment ────────────────────────────────────────────────────
    for c in courses_data:
        canvas_id = c["canvas_id"]
        rows      = c["rows"]
        if not rows:
            continue

        # People (PK = EMPL_ID — safe to upsert)
        pvals = [
            f"({esc(r['name'])}, {esc(r['login'])}, {esc(r['empl'])}, {esc(r['role'])})"
            for r in rows
        ]
        lines += [
            "INSERT INTO `People` (Name, Login_ID, EMPL_ID, Role) VALUES",
            "  " + ",\n  ".join(pvals),
            "ON DUPLICATE KEY UPDATE Name=VALUES(Name), Login_ID=VALUES(Login_ID), Role=VALUES(Role);",
            "",
        ]

        # Enrollment — DELETE + INSERT so re-imports don't create duplicate rows
        # (Enrollment has no unique constraint on CanvasID+Empl_ID, only auto-increment PK)
        if c.get("notes"):
            evals = [
                f"({canvas_id}, {esc(r['empl'])}, {esc(r['role'])})"
                for r in rows
            ]
            lines += [
                f"DELETE FROM `Enrollment` WHERE CanvasID = {canvas_id};",
                "INSERT INTO `Enrollment` (CanvasID, Empl_ID, Role) VALUES",
                "  " + ",\n  ".join(evals),
                ";",
                "",
            ]

    return "\n".join(lines)

# ── Docker / MySQL helpers ─────────────────────────────────────────────────────

def _mysql_cmd(sql: str) -> Tuple[bool, str]:
    cmd = [
        "docker", "exec", "-i", MYSQL_CONTAINER,
        "mysql", "-uroot", f"-p{DB_ROOT_PASSWORD}", DB_NAME,
    ]
    try:
        result = subprocess.run(cmd, input=sql.encode("utf-8"),
                                capture_output=True, timeout=30)
        if result.returncode == 0:
            return True, result.stdout.decode(errors="replace")
        return False, result.stderr.decode(errors="replace")
    except FileNotFoundError:
        return False, "docker not found — is Docker installed and running?"
    except subprocess.TimeoutExpired:
        return False, "MySQL query timed out"
    except Exception as e:
        return False, str(e)

def _mysql_query(sql: str) -> Tuple[bool, List[List[str]]]:
    cmd = [
        "docker", "exec", "-i", MYSQL_CONTAINER,
        "mysql", "--batch", "--skip-column-names",
        "-uroot", f"-p{DB_ROOT_PASSWORD}", DB_NAME,
    ]
    try:
        result = subprocess.run(cmd, input=sql.encode("utf-8"),
                                capture_output=True, timeout=15)
        if result.returncode != 0:
            return False, []
        rows = [
            line.split("\t")
            for line in result.stdout.decode(errors="replace").splitlines()
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
        return (True, f"{MYSQL_CONTAINER} running") if r.stdout.decode().strip() == "true" \
               else (False, f"Container '{MYSQL_CONTAINER}' not running")
    except FileNotFoundError:
        return False, "docker command not found"
    except Exception as e:
        return False, str(e)

# ── Multipart parser (stdlib) ──────────────────────────────────────────────────

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
        results.append((cd.group(1), body.decode(ct.group(1) if ct else "utf-8-sig", errors="replace")))
    return results

def _parse_form_field(data: bytes, content_type: str, field_name: str) -> str:
    """Extract a plain text form field value from multipart data."""
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
<title>Canvas Enrollment Import</title>
<style>
*, *::before, *::after { box-sizing: border-box; }
body { font-family: system-ui,-apple-system,sans-serif; max-width: 960px; margin: 40px auto; padding: 0 24px; color: #1a1a2e; background: #f8f9fa; }
h1   { font-size: 1.5rem; margin-bottom: 4px; }
.sub { color: #555; font-size: .9rem; margin-bottom: 24px; line-height: 1.5; }
code { background: #e8eaed; padding: 1px 5px; border-radius: 3px; font-size: .85em; }
a    { color: #0d6efd; }

/* status bar */
#db-status { font-size: .85rem; margin-bottom: 8px; }
#notes-status { font-size: .85rem; margin-bottom: 16px; }
.dot { display:inline-block; width:9px; height:9px; border-radius:50%; background:#aaa; margin-right:6px; vertical-align:middle; }
.dot.ok  { background:#28a745; }
.dot.err { background:#dc3545; }
.dot.warn { background:#ffc107; }

/* drop zone */
#drop-zone { border:3px dashed #adb5bd; border-radius:10px; padding:48px 24px; text-align:center; cursor:pointer; transition:border-color .15s,background .15s; background:#fff; }
#drop-zone.over      { border-color:#0d6efd; background:#e7f1ff; }
#drop-zone.has-files { border-color:#198754; background:#f0fff4; }
#drop-zone p { margin:4px 0; color:#666; }
#drop-zone strong { color:#333; font-size:1.05rem; }
#file-input { display:none; }
#file-chips { margin-top:12px; display:flex; flex-wrap:wrap; gap:6px; justify-content:center; }
.chip { display:inline-flex; align-items:center; gap:5px; border-radius:20px; padding:3px 10px; font-size:.78rem; }
.chip-ok   { background:#d1e7dd; color:#0f5132; }
.chip-warn { background:#fff3cd; color:#856404; }
.chip-err  { background:#f8d7da; color:#842029; }
.chip .rm  { cursor:pointer; color:#888; font-size:1rem; }
.chip .rm:hover { color:#333; }

/* options */
.opts { display:flex; gap:20px; align-items:flex-end; margin:20px 0; flex-wrap:wrap; }
.field label { display:block; font-size:.85rem; font-weight:600; margin-bottom:4px; }
.field input { border:1px solid #ced4da; border-radius:5px; padding:7px 10px; font-size:.9rem; width:200px; }
.field .hint { font-size:.75rem; color:#888; margin-top:3px; }

/* buttons */
.btn { padding:8px 22px; border-radius:5px; border:none; font-size:.9rem; font-weight:600; cursor:pointer; }
.btn-primary  { background:#0d6efd; color:#fff; }
.btn-primary:disabled { background:#a0b4d0; cursor:not-allowed; }
.btn-secondary { background:#e9ecef; color:#333; }

#status { font-size:.88rem; color:#555; margin:8px 0; min-height:1.2em; }

/* preview tables */
.sec { margin-top:16px; }
.sec h3 { font-size:.92rem; margin:0 0 6px; display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
.badge { font-size:.72rem; font-weight:600; padding:2px 8px; border-radius:10px; }
.b-green { background:#d1e7dd; color:#0f5132; }
.b-yellow{ background:#fff3cd; color:#856404; }
.b-orange{ background:#ffe5d0; color:#7c3000; }
.b-grey  { background:#dee2e6; color:#495057; }
table { width:100%; border-collapse:collapse; font-size:.82rem; background:#fff; border-radius:6px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.07); }
th { background:#f1f3f5; text-align:left; padding:6px 10px; border-bottom:1px solid #dee2e6; }
td { padding:5px 10px; border-bottom:1px solid #f0f0f0; }
tr:last-child td { border-bottom:none; }
.rs { background:#cfe2ff; color:#084298; padding:1px 6px; border-radius:10px; font-size:.72rem; font-weight:600; }
.rt { background:#d1e7dd; color:#0f5132; padding:1px 6px; border-radius:10px; font-size:.72rem; font-weight:600; }
.ro { background:#e9ecef; color:#495057; padding:1px 6px; border-radius:10px; font-size:.72rem; font-weight:600; }

/* result */
.result { margin-top:16px; padding:12px 16px; border-radius:6px; font-size:.9rem; line-height:1.6; }
.res-ok  { background:#d1e7dd; color:#0f5132; border:1px solid #badbcc; }
.res-err { background:#f8d7da; color:#842029; border:1px solid #f5c2c7; }
</style>
</head>
<body>

<h1>Canvas Enrollment Import</h1>
<p class="sub">
  Populates <strong>Terms → Courses → People → Enrollment</strong> in one step.<br>
  Requires <code>Notes.md</code> in the same folder for course metadata.
  Roster CSVs must be named with the Canvas course ID, e.g. <code>196025.csv</code>.
</p>

<div id="db-status"><span class="dot" id="db-dot"></span><span id="db-lbl">Checking MySQL…</span></div>
<div id="notes-status"><span class="dot" id="notes-dot"></span><span id="notes-lbl">Checking Notes.md…</span></div>

<div id="drop-zone" onclick="document.getElementById('file-input').click()">
  <input type="file" id="file-input" multiple accept=".csv,.CSV">
  <p><strong>Drop roster CSV files here</strong></p>
  <p style="font-size:.83rem;">or click to browse — multiple files OK</p>
  <div id="file-chips"></div>
</div>

<div class="opts">
  <div class="field">
    <label for="term-input">Term label <span style="font-weight:normal;color:#888;">(required)</span></label>
    <input type="text" id="term-input" placeholder="e.g. Spring 2026 or 2026-01">
    <div class="hint">Written to the Terms table alongside the term code from the SIS ID.</div>
  </div>
  <div style="align-self:flex-end; display:flex; gap:8px;">
    <button class="btn btn-primary"   id="btn-import" disabled>Import to MySQL</button>
    <button class="btn btn-secondary" id="btn-clear">Clear</button>
  </div>
</div>

<div id="status"></div>
<div id="preview"></div>
<div id="result"></div>

<script>
const zone    = document.getElementById('drop-zone');
const finput  = document.getElementById('file-input');
const btnImp  = document.getElementById('btn-import');
const statusEl= document.getElementById('status');
const previewEl=document.getElementById('preview');
const resultEl= document.getElementById('result');
const chipsEl = document.getElementById('file-chips');
const termInp = document.getElementById('term-input');

let files = [];
let notesIndex = {};       // canvas_id (str key) -> course info from Notes.md
let enrollmentCounts = {}; // canvas_id (str key) -> existing row count in Enrollment table

// ── Startup checks ────────────────────────────────────────────────────────────
fetch('/db-status').then(r=>r.json()).then(d=>{
  document.getElementById('db-dot').className='dot '+(d.ok?'ok':'err');
  document.getElementById('db-lbl').textContent = d.ok
    ? `MySQL ready: ${d.db} @ ${d.container}`
    : `MySQL unavailable: ${d.error}`;
}).catch(()=>{ document.getElementById('db-lbl').textContent='Could not check MySQL'; });

fetch('/notes-status').then(r=>r.json()).then(d=>{
  document.getElementById('notes-dot').className='dot '+(d.found?(d.count>0?'ok':'warn'):'err');
  document.getElementById('notes-lbl').textContent = d.found
    ? `Notes.md found — ${d.count} course(s) indexed`
    : 'Notes.md not found in script directory — Courses/Enrollment tables will be skipped';
  notesIndex = d.index || {};
}).catch(()=>{ document.getElementById('notes-lbl').textContent='Could not read Notes.md status'; });

fetch('/enrollment-status').then(r=>r.json()).then(d=>{
  enrollmentCounts = d.counts || {};
}).catch(()=>{});

// ── File handling ─────────────────────────────────────────────────────────────
zone.addEventListener('dragover',e=>{ e.preventDefault(); zone.classList.add('over'); });
zone.addEventListener('dragleave',()=>zone.classList.remove('over'));
zone.addEventListener('drop',e=>{ e.preventDefault(); zone.classList.remove('over'); addFiles(Array.from(e.dataTransfer.files)); });
finput.addEventListener('change',()=>{ addFiles(Array.from(finput.files)); finput.value=''; });

function stemOf(n){ return n.replace(/\.[^/.]+$/, ''); }
function cidFrom(n){ const m=stemOf(n).match(/(?<!\d)(\d{4,})(?!\d)/); return m?parseInt(m[1]):null; }

function addFiles(incoming){
  incoming.filter(f=>f.name.match(/\.csv$/i)).forEach(f=>{
    if(!files.find(e=>e.file.name===f.name))
      files.push({ file:f, cid:cidFrom(f.name) });
  });
  renderChips();
  if(files.length) doPreview();
}

function renderChips(){
  chipsEl.innerHTML = files.map((e,i)=>{
    const inNotes = e.cid && notesIndex[e.cid];
    const existing = e.cid ? enrollmentCounts[e.cid] : 0;
    const cls  = !e.cid ? 'chip-err' : inNotes ? 'chip-ok' : 'chip-warn';
    const note = !e.cid ? '⚠ no Canvas ID'
               : inNotes ? `✔ ${notesIndex[e.cid].course_name}`
               : '⚠ not in Notes.md';
    const repNote = existing ? ` — ↺ replaces ${existing} rows` : '';
    return `<span class="chip ${cls}">${e.file.name} — ${note}${repNote}
      <span class="rm" onclick="removeFile(${i})">&#x2715;</span></span>`;
  }).join('');
  zone.classList.toggle('has-files', files.length > 0);
}

function removeFile(i){
  files.splice(i,1); renderChips();
  if(!files.length){ previewEl.innerHTML=''; statusEl.textContent=''; btnImp.disabled=true; }
  else doPreview();
}

// ── Preview ───────────────────────────────────────────────────────────────────
async function doPreview(){
  statusEl.textContent='Parsing files…'; previewEl.innerHTML=''; btnImp.disabled=true;
  const fd=new FormData();
  files.forEach(e=>fd.append('files', e.file, e.file.name));
  const d = await fetch('/preview',{method:'POST',body:fd}).then(r=>r.json());
  if(d.error){ statusEl.textContent='✖ '+d.error; return; }

  let html='', totalPeople=0;
  for(const c of d.courses){
    totalPeople += c.rows.length;
    const inNotes = c.canvas_id && notesIndex[c.canvas_id];
    const idBadge = c.canvas_id
      ? `<code>${c.canvas_id}</code>`
      : `<span class="badge b-yellow">⚠ No Canvas ID — skipped</span>`;
    const notesBadge = c.canvas_id
      ? (inNotes
          ? `<span class="badge b-green">✔ ${notesIndex[c.canvas_id].course_name} — all 4 tables</span>`
          : `<span class="badge b-yellow">⚠ Not in Notes.md — People only, Enrollment skipped</span>`)
      : '';
    const existingCount = c.canvas_id ? enrollmentCounts[c.canvas_id] : 0;
    const existingBadge = existingCount
      ? `<span class="badge b-orange">↺ replaces ${existingCount} existing rows</span>`
      : '';
    html += `<div class="sec">
      <h3>${c.filename} → ${idBadge} ${notesBadge} ${existingBadge}
        <span class="badge b-grey">${c.rows.length} people</span>
      </h3>
      <table>
        <tr><th>Name</th><th>EMPL ID</th><th>Login</th><th>Role</th></tr>
        ${c.rows.slice(0,12).map(r=>`<tr>
          <td>${r.name||''}</td><td><code>${r.empl}</code></td><td>${r.login||''}</td>
          <td><span class="${rc(r.role)}">${r.role}</span></td>
        </tr>`).join('')}
        ${c.rows.length>12?`<tr><td colspan="4" style="color:#888;text-align:center;">…${c.rows.length-12} more</td></tr>`:''}
      </table>
    </div>`;
  }
  statusEl.innerHTML=`<strong>${files.length}</strong> file(s) — <strong>${totalPeople}</strong> people rows.`;
  previewEl.innerHTML=html;
  btnImp.disabled=false;
}

function rc(r){ r=(r||'').toLowerCase(); return r.includes('teacher')?'rt':r.includes('student')?'rs':'ro'; }

// ── Import ────────────────────────────────────────────────────────────────────
btnImp.addEventListener('click', async()=>{
  const term = termInp.value.trim();
  if(!term){
    resultEl.innerHTML='<div class="result res-err">⚠ Please enter a Term label before importing.</div>';
    return;
  }
  btnImp.disabled=true; resultEl.innerHTML=''; statusEl.textContent='Importing…';
  const fd=new FormData();
  files.forEach(e=>fd.append('files', e.file, e.file.name));
  fd.append('term', term);
  const d = await fetch('/import',{method:'POST',body:fd}).then(r=>r.json());
  if(d.error){
    resultEl.innerHTML=`<div class="result res-err">✖ ${d.error}</div>`;
  } else {
    const w = d.warnings.length ? `<br><strong>Warnings:</strong> ${d.warnings.join(' | ')}` : '';
    resultEl.innerHTML=`<div class="result res-ok">
      ✔ Import complete<br>
      Terms: <strong>${d.terms}</strong> &nbsp;|&nbsp;
      Courses: <strong>${d.courses}</strong> &nbsp;|&nbsp;
      People: <strong>${d.people}</strong> &nbsp;|&nbsp;
      Enrollment: <strong>${d.enrollment}</strong>${w}
    </div>`;
    fetch('/enrollment-status').then(r=>r.json()).then(data=>{
      enrollmentCounts = data.counts || {};
      renderChips();
    }).catch(()=>{});
  }
  statusEl.textContent=''; btnImp.disabled=false;
});

document.getElementById('btn-clear').addEventListener('click',()=>{
  files=[]; chipsEl.innerHTML=''; zone.classList.remove('has-files');
  statusEl.textContent=''; previewEl.innerHTML=''; resultEl.innerHTML=''; btnImp.disabled=true;
});
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

        elif self.path == "/notes-status":
            notes_path = find_notes(_HERE)
            notes = parse_notes_md(notes_path)
            index = {str(k): {"course_name": v["course_name"],
                               "sis_id":      v["sis_id"],
                               "term_code":   v["term_code"]}
                     for k, v in notes.items()}
            self._send_json({"found": notes_path.exists(),
                             "count": len(notes), "index": index})

        elif self.path == "/enrollment-status":
            ok, rows = _mysql_query(
                "SELECT CanvasID, COUNT(*) FROM `Enrollment` GROUP BY CanvasID;"
            )
            counts = {row[0]: int(row[1]) for row in rows if len(row) == 2} if ok else {}
            self._send_json({"ok": ok, "counts": counts})

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        ct   = self.headers.get("Content-Type", "")
        data = self._read_body()
        if "multipart/form-data" not in ct:
            self._send_json({"error": "Expected multipart/form-data"}, 400)
            return

        parts = _parse_multipart(data, ct)

        if self.path == "/preview":
            courses = []
            for filename, content in parts:
                canvas_id = canvas_id_from_filename(filename)
                rows = parse_roster_content(content)
                courses.append({"filename": filename, "canvas_id": canvas_id, "rows": rows})
            self._send_json({"courses": courses})

        elif self.path == "/import":
            term_label = _parse_form_field(data, ct, "term")
            notes      = parse_notes_md(find_notes(_HERE))
            warnings:  List[str] = []
            courses_data: List[Dict] = []

            for filename, content in parts:
                canvas_id = canvas_id_from_filename(filename)
                rows = parse_roster_content(content)
                if canvas_id is None:
                    warnings.append(f"{filename}: no Canvas ID in filename — skipped")
                    continue
                if not rows:
                    warnings.append(f"{filename}: no valid roster rows — skipped")
                    continue
                entry: Dict = {"canvas_id": canvas_id, "rows": rows,
                               "notes": notes.get(canvas_id)}
                if not entry["notes"]:
                    warnings.append(
                        f"Canvas ID {canvas_id}: not in Notes.md — "
                        "People inserted, Enrollment skipped (no Courses row)"
                    )
                courses_data.append(entry)

            if not courses_data:
                self._send_json({"error": "No importable courses found."})
                return

            sql = build_sql(courses_data, term_label)
            ok, msg = _mysql_cmd(sql)
            if not ok:
                self._send_json({"error": f"MySQL error: {msg}"})
                return

            term_codes  = {c["notes"]["term_code"] for c in courses_data if c.get("notes")}
            with_notes  = [c for c in courses_data if c.get("notes")]
            all_people  = sum(len(c["rows"]) for c in courses_data)
            all_enroll  = sum(len(c["rows"]) for c in with_notes)

            self._send_json({
                "terms":      len(term_codes),
                "courses":    len(with_notes),
                "people":     all_people,
                "enrollment": all_enroll,
                "warnings":   warnings,
            })
        else:
            self.send_response(404)
            self.end_headers()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ok, msg    = _container_running()
    notes_path = find_notes(_HERE)
    notes      = parse_notes_md(notes_path)
    print(f"Canvas Enrollment Import → http://localhost:{PORT}")
    print(f"MySQL : {MYSQL_CONTAINER} ({'running' if ok else 'NOT RUNNING — ' + msg})")
    print(f"DB    : {DB_NAME}")
    print(f"Notes : {len(notes)} course(s) indexed from {notes_path.name}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
