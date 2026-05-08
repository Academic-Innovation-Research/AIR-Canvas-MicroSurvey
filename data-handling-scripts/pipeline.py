#!/usr/bin/env python3
"""
Shared domain logic for the Canvas enrollment data pipeline.

Imported by upload_app.py and the numbered CLI scripts (1, 4, 5).
No external dependencies — Python 3.10+ stdlib only.
"""

import csv
import io
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Constants ──────────────────────────────────────────────────────────────────

URL_RE       = re.compile(r"https?://[^/]+/courses/(\d+)/?", re.IGNORECASE)
CANVAS_ID_RE = re.compile(r"(?<!\d)(\d{4,})(?!\d)")

# Canvas People-page CSV column positions (0-based)
# Profile Pic | Name | Login ID | SIS ID | Section | Role | ...
IDX_NAME, IDX_LOGIN, IDX_EMPL, IDX_ROLE = 1, 2, 3, 5
EXPECTED_HEADER = {"name", "login id", "sis id", "role"}

# ── Notes.md ──────────────────────────────────────────────────────────────────

def find_notes(root: Path) -> Path:
    """
    Return the first Notes.md found under root, checking:
      1. root/Notes.md
      2. root/Enrollment/Notes.md
      3. root/Notes-src.md  (committed fallback/template)
    Returns root/Notes.md even if nothing exists — caller handles missing file.
    """
    candidates = [
        root / "Notes.md",
        root / "Enrollment" / "Notes.md",
        root / "Notes-src.md",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def _looks_like_sis(line: str) -> bool:
    parts = line.strip().split("_")
    return len(parts) >= 3 and parts[0].isdigit()


def _course_name_from_sis(sis: str) -> str:
    segs = sis.split("_")
    if len(segs) >= 4:
        return f"{segs[2]} {segs[3]}"
    return segs[2] if len(segs) >= 3 else sis


def parse_notes_md(path: Path) -> Dict[int, Dict]:
    """
    Return {canvas_id: {canvas_id, sis_id, url, term_code, course_name}}
    for every course entry in the file.

    Entries must be separated by blank lines. Within each block the URL
    and SIS ID can appear in any order; description lines are ignored.

    Supported formats:

        # URL first:
        https://erau.instructure.com/courses/201288/
        2963_S3_ECON_211_2382668A_W411

        # SIS first:
        2963_S3_ECON_211_2382668A_W411
        https://erau.instructure.com/courses/201288/

        # Human-readable (description line is ignored):
        1) ECON 211 - Jack Patel
        https://erau.instructure.com/courses/201288/
        2963_S3_ECON_211_2382668A_W411
    """
    courses: Dict[int, Dict] = {}
    if not path.exists():
        return courses
    text = path.read_text(encoding="utf-8").strip()
    for block in re.split(r"\n\s*\n", text):
        url: Optional[str] = None
        canvas_id: Optional[int] = None
        sis: Optional[str] = None
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            m = URL_RE.search(line)
            if m and canvas_id is None:
                canvas_id = int(m.group(1))
                url = line.rstrip("/")
            if _looks_like_sis(line) and sis is None:
                sis = line
        if url and sis and canvas_id:
            tc = sis.split("_", 1)[0]
            courses[canvas_id] = {
                "canvas_id":   canvas_id,
                "sis_id":      sis,
                "url":         url,
                "term_code":   tc,
                "course_name": _course_name_from_sis(sis),
            }
    return courses


# ── Roster CSV ─────────────────────────────────────────────────────────────────

def canvas_id_from_filename(name: str) -> Optional[int]:
    """Extract Canvas course ID from a filename stem (e.g. '201288.csv' → 201288)."""
    m = CANVAS_ID_RE.search(Path(name).stem)
    return int(m.group(1)) if m else None


def _norm_header(cell: str) -> str:
    return (cell or "").strip().strip('"').strip("'").lstrip("﻿").casefold()


def _is_roster_header(cols: List[str]) -> bool:
    return EXPECTED_HEADER.issubset({_norm_header(c) for c in cols if c})


def _parse_rows(reader) -> List[Dict]:
    """Consume a csv.reader whose header row has already been validated."""
    rows: List[Dict] = []
    for cols in reader:
        if len(cols) <= max(IDX_EMPL, IDX_ROLE):
            continue
        name  = (cols[IDX_NAME]  or "").strip() or None
        login = (cols[IDX_LOGIN] or "").strip() or None
        empl  = (cols[IDX_EMPL]  or "").strip()
        role  = (cols[IDX_ROLE]  or "").strip()
        if empl and role:
            rows.append({"name": name, "login": login, "empl": empl, "role": role})
    return rows


def parse_roster_content(content: str) -> List[Dict]:
    """
    Parse a Canvas People-page CSV from a string (e.g. received via HTTP upload).
    Returns list of {name, login, empl, role} dicts.
    Returns [] if the content does not look like a Canvas roster.
    """
    reader = csv.reader(io.StringIO(content))
    try:
        header = next(reader)
    except StopIteration:
        return []
    if not _is_roster_header(header):
        return []
    return _parse_rows(reader)


def parse_roster_path(path: Path) -> List[Dict]:
    """
    Parse a Canvas People-page CSV from a file path.
    Tries UTF-8-sig first, falls back to latin-1 for files with encoding issues.
    Returns [] if the file does not look like a Canvas roster.
    """
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with path.open("r", encoding=enc, newline="") as f:
                reader = csv.reader(f)
                try:
                    header = next(reader)
                except StopIteration:
                    return []
                if not _is_roster_header(header):
                    return []
                return _parse_rows(reader)
        except UnicodeDecodeError:
            continue
        except Exception as e:
            raise RuntimeError(f"Could not read roster {path}: {e}") from e
    return []


def discover_roster_csvs(root: Path) -> List[Path]:
    """Return sorted list of CSV files under root (handles both .csv and .CSV)."""
    return sorted({p for pat in ("*.csv", "*.CSV") for p in root.rglob(pat) if p.is_file()})


def instructor(rows: List[Dict]) -> Tuple[Optional[str], Optional[str]]:
    """Return (name, empl_id) of the first teacher row, or (None, None)."""
    for r in rows:
        if "teacher" in (r["role"] or "").lower():
            return r["name"], r["empl"]
    return None, None


def student_count(rows: List[Dict]) -> int:
    return sum(1 for r in rows if "student" in (r["role"] or "").lower())


# ── SQL escaping ───────────────────────────────────────────────────────────────

def esc(val) -> str:
    """Escape a value for use as a MySQL string literal, or return NULL."""
    if val is None:
        return "NULL"
    s = (str(val)
         .replace(" ", " ")   # non-breaking space → regular space
         .replace("\r\n", "\n")
         .replace("\r", "\n")
         .strip())
    s = s.replace("\n", " ").replace("\t", " ")
    if not s:
        return "NULL"
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"
