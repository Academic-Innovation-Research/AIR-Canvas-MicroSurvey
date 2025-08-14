#!/usr/bin/env python3
"""
Enrich courses.csv using roster CSVs named <CourseSISID>.csv.

For each row in courses.csv:
  - Open <CourseSISID>.csv in the same directory (unless --rosters dir is set).
  - Find the SIS ID for the row where Role == "Teacher" (case-insensitive).
    -> write to InstructorID.
  - Count rows where Role == "Student" (case-insensitive).
    -> write to CntStudents.

Supports both headered CSVs and positional parsing:
  - Preferred headers: "SIS ID", "Role"
  - Positional fallback: SIS ID @ index 3, Role @ index 5
  
Usage:
cd /Users/robert/Downloads/Canvas
# overwrite in place
python3 enrich_courses_from_rosters.py --courses courses.csv --rosters .
# or write to a new file
python3 enrich_courses_from_rosters.py --courses courses.csv --rosters . --outfile courses_enriched.csv
open courses.csv

"""

import csv
import sys
from pathlib import Path
import argparse
from typing import Optional, Tuple

# Fallback positional indices (0-based) for roster CSVs
IDX_EMPL = 3
IDX_ROLE = 5

def read_teacher_and_student_count(roster_path: Path) -> Tuple[Optional[str], int]:
    """
    Returns (teacher_sis_id, cnt_students) from a roster CSV.
    """
    teacher_id: Optional[str] = None
    cnt_students = 0

    try:
        with roster_path.open("r", encoding="utf-8-sig", newline="") as f:
            # Try headered read first
            sniff = f.read(8192)
            f.seek(0)
            reader = csv.reader(f)
            rows = list(reader)
            if not rows:
                return (None, 0)

            header = [h.strip() for h in rows[0]] if rows else []
            def normalize(s: str) -> str:
                return (s or "").strip().casefold()

            def role_is_student(s: str) -> bool:
                return normalize(s) == "student"

            def role_is_teacher(s: str) -> bool:
                return normalize(s) == "teacher"

            # Headered mode?
            if header and ("SIS ID" in header or "Role" in header):
                # DictReader for convenience
                f.seek(0)
                dict_reader = csv.DictReader(f)
                for r in dict_reader:
                    sis = (r.get("SIS ID") or "").strip()
                    role = (r.get("Role") or "").strip()
                    if role_is_student(role):
                        cnt_students += 1
                    elif role_is_teacher(role) and teacher_id is None and sis:
                        teacher_id = sis
                return (teacher_id, cnt_students)

            # Positional fallback (skip header row we already read as rows[0])
            for cols in rows[1:]:
                if len(cols) <= max(IDX_EMPL, IDX_ROLE):
                    continue
                sis = (cols[IDX_EMPL] or "").strip()
                role = (cols[IDX_ROLE] or "").strip()
                if role_is_student(role):
                    cnt_students += 1
                elif role_is_teacher(role) and teacher_id is None and sis:
                    teacher_id = sis
            return (teacher_id, cnt_students)

    except FileNotFoundError:
        # Caller will log
        return (None, 0)
    except Exception as e:
        print(f"✖ Error reading {roster_path}: {e}", file=sys.stderr)
        return (None, 0)

def enrich_courses(courses_csv: Path, rosters_dir: Path, outfile: Optional[Path]) -> Path:
    """
    Reads courses_csv, enriches InstructorID and CntStudents,
    writes to outfile (or overwrites courses_csv if outfile is None).
    """
    out_path = outfile or courses_csv

    # Read all rows
    with courses_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        required = ["CanvasID","CourseName","Instructor","URL","TermCode",
                    "CourseSISID","CntStudents","InstructorID"]
        # Ensure all headers exist (add missing ones in-memory)
        write_headers = list(headers)
        for h in required:
            if h not in write_headers:
                write_headers.append(h)

        rows = list(reader)

    # Process rows
    for r in rows:
        sis = (r.get("CourseSISID") or "").strip()
        if not sis:
            continue
        roster_path = rosters_dir / f"{sis}.csv"
        teacher_id, cnt_students = read_teacher_and_student_count(roster_path)

        if teacher_id:
            r["InstructorID"] = teacher_id
        # Always set CntStudents (including 0)
        r["CntStudents"] = str(cnt_students)

    # Write output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=write_headers)
        writer.writeheader()
        for r in rows:
            # Fill missing keys with empty strings to avoid KeyError
            for h in write_headers:
                if h not in r:
                    r[h] = ""
            writer.writerow(r)

    return out_path

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Enrich courses.csv with InstructorID and CntStudents from roster CSVs.")
    ap.add_argument("--courses", default="courses.csv", help="Path to courses.csv")
    ap.add_argument("--rosters", default=".", help="Directory containing <CourseSISID>.csv roster files")
    ap.add_argument("--outfile", default=None, help="Output CSV path; if omitted, overwrite courses.csv")
    args = ap.parse_args(argv)

    courses_csv = Path(args.courses).expanduser().resolve()
    rosters_dir = Path(args.rosters).expanduser().resolve()
    outfile = Path(args.outfile).expanduser().resolve() if args.outfile else None

    if not courses_csv.exists():
        print(f"✖ courses.csv not found at {courses_csv}", file=sys.stderr)
        return 2

    out_path = enrich_courses(courses_csv, rosters_dir, outfile)
    print(f"✅ Updated {out_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
