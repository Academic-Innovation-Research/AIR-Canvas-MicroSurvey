#!/usr/bin/env python3
"""
Enrich courses.csv with Instructor, CntStudents, InstructorID using course roster CSVs
found in Enrollment/ directory.

Assumptions:
- Each roster file name contains the CanvasID (digits), e.g.:
    Enrollment/196025.csv
    Enrollment/course_roster_196025.csv
- Roster columns include: "Name", "SIS ID", "Role" (as in your example)
- Teacher rows have Role == "Teacher" (or contain "teacher")
- Student rows have Role == "Student" (or contain "student")

Usage:
  python3 2-enrich_courses_csv.py --infile courses.csv --enroll-dir Enrollment --outfile courses_enriched.csv
"""

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

CANVAS_ID_RE = re.compile(r"(?<!\d)(\d{4,})(?!\d)")  # grab a digit chunk, usually Canvas IDs are 5-7 digits

def norm(s: str) -> str:
    return (s or "").strip()

def role_is(role_value: str, needle: str) -> bool:
    r = norm(role_value).lower()
    return r == needle or needle in r  # tolerate variants like "TeacherEnrollment"

def extract_canvas_id_from_filename(path: Path) -> Optional[str]:
    m = CANVAS_ID_RE.search(path.stem)
    return m.group(1) if m else None

def parse_roster(path: Path) -> Tuple[str, str, int]:
    """
    Returns: (teacher_name, teacher_sis_id, student_count)
    If multiple teachers exist, concatenates with " | ".
    """
    teacher_names: List[str] = []
    teacher_ids: List[str] = []
    student_count = 0

    # Try UTF-8 first, fall back to latin-1 if needed
    encodings = ["utf-8-sig", "utf-8", "latin-1"]

    last_err = None
    for enc in encodings:
        try:
            with path.open("r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                # Validate expected headers exist (best effort)
                headers = [h.lower() for h in (reader.fieldnames or [])]
                if not reader.fieldnames:
                    return ("", "", 0)

                # Flexible key lookup
                def get(row, key):
                    for k in row.keys():
                        if k and k.strip().lower() == key:
                            return row.get(k, "")
                    return ""

                for row in reader:
                    role = get(row, "role")
                    if role_is(role, "teacher"):
                        name = norm(get(row, "name"))
                        sis  = norm(get(row, "sis id"))
                        if name:
                            teacher_names.append(name)
                        if sis:
                            teacher_ids.append(sis)
                    elif role_is(role, "student"):
                        student_count += 1
            break
        except Exception as e:
            last_err = e
            continue
    else:
        raise RuntimeError(f"Could not read roster {path}: {last_err}")

    teacher_name = " | ".join(dict.fromkeys(teacher_names))  # de-dupe, preserve order
    teacher_sis  = " | ".join(dict.fromkeys(teacher_ids))
    return (teacher_name, teacher_sis, student_count)

def build_roster_index(enroll_dir: Path) -> Dict[str, Tuple[str, str, int, str]]:
    """
    Map CanvasID -> (teacher_name, teacher_sis, student_count, roster_filename)
    """
    idx: Dict[str, Tuple[str, str, int, str]] = {}
    for p in sorted(enroll_dir.glob("*.csv")):
        canvas_id = extract_canvas_id_from_filename(p)
        if not canvas_id:
            continue
        teacher_name, teacher_sis, student_count = parse_roster(p)
        idx[canvas_id] = (teacher_name, teacher_sis, student_count, p.name)
    return idx

def enrich_courses(infile: Path, outfile: Path, roster_idx: Dict[str, Tuple[str, str, int, str]]) -> int:
    with infile.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print("✖ courses.csv has no headers", file=sys.stderr)
            return 2

        fieldnames = reader.fieldnames
        rows = list(reader)

    updated = 0
    missing = 0

    for r in rows:
        canvas_id = norm(r.get("CanvasID", ""))
        if not canvas_id:
            continue

        if canvas_id not in roster_idx:
            missing += 1
            continue

        teacher_name, teacher_sis, student_count, _src = roster_idx[canvas_id]

        # Update fields
        if teacher_name:
            r["Instructor"] = teacher_name
        if teacher_sis:
            r["InstructorID"] = teacher_sis
        r["CntStudents"] = str(student_count)

        updated += 1

    outfile.parent.mkdir(parents=True, exist_ok=True)
    with outfile.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ Updated {updated} course rows.")
    if missing:
        print(f"⚠️ No matching roster file found for {missing} CanvasIDs (filename must contain CanvasID digits).")
    return 0

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Enrich courses.csv using Enrollment roster CSVs")
    ap.add_argument("--infile", default="courses.csv", help="Input courses CSV")
    ap.add_argument("--enroll-dir", default="Enrollment", help="Directory of roster CSVs")
    ap.add_argument("--outfile", default="courses_enriched.csv", help="Output enriched courses CSV")
    args = ap.parse_args(argv)

    infile = Path(args.infile).expanduser().resolve()
    enroll_dir = Path(args.enroll_dir).expanduser().resolve()
    outfile = Path(args.outfile).expanduser().resolve()

    if not infile.exists():
        print(f"✖ Input not found: {infile}", file=sys.stderr)
        return 2
    if not enroll_dir.exists():
        print(f"✖ Enrollment dir not found: {enroll_dir}", file=sys.stderr)
        return 2

    roster_idx = build_roster_index(enroll_dir)
    if not roster_idx:
        print(f"✖ No roster CSVs indexed from {enroll_dir}. Ensure filenames contain CanvasID.", file=sys.stderr)
        return 2

    return enrich_courses(infile, outfile, roster_idx)

if __name__ == "__main__":
    raise SystemExit(main())

