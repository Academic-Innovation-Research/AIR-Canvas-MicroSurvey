#!/usr/bin/env python3
"""
Create a CSV of course metadata from Notes.md.

Outputs columns:
  CanvasID, CourseName, Instructor, URL, TermCode, CourseSISID, CntStudents, InstructorID

Notes.md is expected to contain repeating blocks like:
  2899_S3_ACCT_210_2672923A_W411
  https://erau.instructure.com/courses/190626/

Blank lines and unrelated text are ignored safely.

Rules:
- TermCode:        first token before the first underscore (e.g., "2899")
- CourseName:      tokens after the 2nd underscore; for your examples, "ACCT 210"
                   (constructed as token[2] + " " + token[3] if both exist; else join token[2:])
- CourseSISID:     the full SIS string line (e.g., "2899_S3_ACCT_210_2672923A_W411")
- URL:             the url line following the SIS line
- CanvasID:        last segment of the URL (e.g., 190626)
- Instructor:      empty (not provided)
- CntStudents:     empty (not provided)
- InstructorID:    empty (not provided)

Usage:
cd /Users/robert/Downloads/Canvas
python3 build_courses_csv.py --root . --outfile courses.csv
open courses.csv

"""

import csv
import re
import sys
from pathlib import Path
import argparse
from typing import List, Dict

URL_RE = re.compile(r"https?://[^/]+/courses/(\d+)/?", re.IGNORECASE)

def looks_like_sis_id(line: str) -> bool:
    """
    Heuristic: must contain at least two underscores and start with digits (TermCode),
    e.g., '2899_S3_ACCT_210_2672923A_W411'
    """
    parts = line.strip()
    if not parts or "_" not in parts:
        return False
    segs = parts.split("_")
    if len(segs) < 3:
        return False
    return segs[0].isdigit()

def parse_canvas_id(url: str):
    m = URL_RE.search(url.strip())
    return int(m.group(1)) if m else None

def derive_course_name_from_sis(sis: str) -> str:
    segs = sis.split("_")
    # By your rule: the grouping after the 2nd underscore is CourseName.
    # Your examples show it's typically two tokens like "ACCT" "210".
    if len(segs) >= 4:
        # Prefer two tokens when available
        name_tokens = [segs[2]]
        if len(segs) >= 4 and segs[3]:
            name_tokens.append(segs[3])
        return " ".join(name_tokens)
    elif len(segs) >= 3:
        return segs[2]
    return sis  # fallback

def parse_notes_md(notes_path: Path) -> List[Dict[str, str]]:
    """
    Scan Notes.md and collect (SIS line + URL line) pairs.
    Ignores lines that don't match the expected patterns.
    """
    rows: List[Dict[str, str]] = []
    if not notes_path.exists():
        print(f"✖ Notes.md not found at {notes_path}", file=sys.stderr)
        return rows

    # Read non-empty lines, preserve order
    lines = [ln.strip() for ln in notes_path.read_text(encoding="utf-8").splitlines()]

    i = 0
    while i < len(lines):
        sis_line = lines[i].strip()
        if looks_like_sis_id(sis_line):
            # Find the next non-empty line to act as URL
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            url_line = lines[j].strip() if j < len(lines) else ""
            canvas_id = parse_canvas_id(url_line)
            if canvas_id is not None:
                term_code = sis_line.split("_", 1)[0]
                course_name = derive_course_name_from_sis(sis_line)
                rows.append({
                    "CanvasID": str(canvas_id),
                    "CourseName": course_name,
                    "Instructor": "",
                    "URL": url_line.strip(),
                    "TermCode": term_code,
                    "CourseSISID": sis_line,
                    "CntStudents": "",
                    "InstructorID": "",
                })
                i = j + 1
                continue
            else:
                # URL didn't parse; skip gracefully
                i = j + 1
                continue
        i += 1
    return rows

def write_csv(rows: List[Dict[str, str]], out_path: Path) -> None:
    headers = ["CanvasID", "CourseName", "Instructor", "URL",
               "TermCode", "CourseSISID", "CntStudents", "InstructorID"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow(r)

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build courses CSV from Notes.md")
    ap.add_argument("--root", default=".", help="Directory containing Notes.md")
    ap.add_argument("--notes", default="Notes.md", help="Notes file name")
    ap.add_argument("--outfile", default="courses.csv", help="Output CSV file")
    ap.add_argument("--quiet", action="store_true", help="Suppress progress messages")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    notes_path = root / args.notes
    out_path = root / args.outfile

    rows = parse_notes_md(notes_path)
    if not rows:
        if not args.quiet:
            print("No valid course entries found. Check Notes.md formatting.", file=sys.stderr)
        return 2

    write_csv(rows, out_path)
    if not args.quiet:
        print(f"✅ Wrote {len(rows)} rows to {out_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
