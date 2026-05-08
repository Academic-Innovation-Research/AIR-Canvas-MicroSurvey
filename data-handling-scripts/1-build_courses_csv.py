#!/usr/bin/env python3
"""
Create a CSV of course metadata from Notes.md.

Outputs columns:
  CanvasID, CourseName, Instructor, URL, TermCode, CourseSISID, CntStudents, InstructorID

Usage:
  python3 1-build_courses_csv.py --root . --outfile courses.csv
"""

import csv
import sys
from pathlib import Path
import argparse
from typing import List, Dict

from pipeline import find_notes, parse_notes_md


def _to_csv_rows(notes: dict) -> List[Dict[str, str]]:
    return [
        {
            "CanvasID":     str(c["canvas_id"]),
            "CourseName":   c["course_name"],
            "Instructor":   "",
            "URL":          c["url"],
            "TermCode":     c["term_code"],
            "CourseSISID":  c["sis_id"],
            "CntStudents":  "",
            "InstructorID": "",
        }
        for c in notes.values()
    ]


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
    ap.add_argument("--root",    default=".", help="Directory to search for Notes.md")
    ap.add_argument("--outfile", default="courses.csv", help="Output CSV file")
    ap.add_argument("--quiet",   action="store_true", help="Suppress progress messages")
    args = ap.parse_args(argv)

    root       = Path(args.root).expanduser().resolve()
    notes_path = find_notes(root)
    out_path   = root / args.outfile

    notes = parse_notes_md(notes_path)
    if not notes:
        if not args.quiet:
            print("No valid course entries found. Check Notes.md formatting.", file=sys.stderr)
        return 2

    rows = _to_csv_rows(notes)
    write_csv(rows, out_path)
    if not args.quiet:
        print(f"✅ Wrote {len(rows)} rows to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
