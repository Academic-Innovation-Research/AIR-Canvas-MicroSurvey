#!/usr/bin/env python3
"""
Master script to run all course-related scripts in sequence.

Order:
1. 1-build_courses_csv.py                -> courses.csv
2. 2-enrich_courses_csv.py               -> courses_enriched.csv (adds instructor + student count)
3. 3-build_courses_inserts.py            -> courses_inserts.sql (and Terms inserts; prompts for term)
4. 4-build_people_inserts_positional.py  -> people_inserts.sql
5. 5-build_enrollment_inserts.py         -> enrollment_inserts.sql

Usage:
cd data-handling-scripts
python3 run_all_course_scripts.py

"""

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(".").resolve()
ENROLL_DIR = ROOT_DIR / "Enrollment"
SQL_DIR = ROOT_DIR / "sql"

COURSES_CSV = ROOT_DIR / "courses.csv"
COURSES_ENRICHED_CSV = ROOT_DIR / "courses_enriched.csv"
COURSES_INSERTS = SQL_DIR / "courses_inserts.sql"
PEOPLE_INSERTS = SQL_DIR / "people_inserts.sql"
ENROLLMENT_INSERTS = SQL_DIR / "enrollment_inserts.sql"

def run_cmd(cmd_list, description=None):
    if description:
        print(f"\n=== {description} ===")
    try:
        subprocess.run(cmd_list, check=True)
    except subprocess.CalledProcessError as e:
        print(f"✖ Error running {cmd_list[0]}: {e}", file=sys.stderr)
        sys.exit(e.returncode)

def main():
    SQL_DIR.mkdir(exist_ok=True)

    run_cmd(
        ["python3", "1-build_courses_csv.py", "--root", str(ROOT_DIR), "--outfile", str(COURSES_CSV)],
        "Step 1: Building courses.csv from Notes.md"
    )

    run_cmd(
        [
            "python3", "2-enrich_courses_csv.py",
            "--infile", str(COURSES_CSV),
            "--enroll-dir", str(ENROLL_DIR),
            "--outfile", str(COURSES_ENRICHED_CSV),
        ],
        "Step 2: Enriching courses.csv with instructor + student count"
    )

    run_cmd(
        ["python3", "3-build_courses_inserts.py", "--csv", str(COURSES_ENRICHED_CSV), "--outfile", str(COURSES_INSERTS)],
        "Step 3: Building courses_inserts.sql (will prompt for Term value)"
    )

    run_cmd(
        ["python3", "4-build_people_inserts_positional.py", "--root", str(ENROLL_DIR), "--outfile", str(PEOPLE_INSERTS)],
        "Step 4: Building people_inserts.sql"
    )

    run_cmd(
        ["python3", "5-build_enrollment_inserts.py", "--root", str(ENROLL_DIR), "--outfile", str(ENROLLMENT_INSERTS)],
        "Step 5: Building enrollment_inserts.sql"
    )

    print("\n✅ All steps completed successfully.")
    print(f"  Courses CSV:      {COURSES_CSV}")
    print(f"  Courses Inserts:  {COURSES_INSERTS}")
    print(f"  People Inserts:   {PEOPLE_INSERTS}")
    print(f"  Enrollment SQL:   {ENROLLMENT_INSERTS}")

if __name__ == "__main__":
    main()
