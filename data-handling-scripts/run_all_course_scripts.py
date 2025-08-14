#!/usr/bin/env python3
"""
Master script to run all course-related scripts in sequence.

Order:
1. build_courses_csv.py                -> courses.csv
2. enrich_courses_from_rosters.py      -> updates courses.csv with InstructorID + CntStudents
3. build_courses_inserts.py            -> courses_inserts.sql (and Terms inserts)
4. build_people_inserts_positional.py  -> people_inserts.sql
5. build_enrollment_inserts.py         -> enrollment_inserts.sql

Usage:
cd /Users/robert/Downloads/Canvas
python3 run_all_course_scripts.py

"""

import subprocess
import sys
from pathlib import Path

# Default file/directory paths
ROOT_DIR = Path(".").resolve()
COURSES_CSV = ROOT_DIR / "courses.csv"
COURSES_ENRICHED_CSV = COURSES_CSV  # overwritten in place
COURSES_INSERTS = ROOT_DIR / "courses_inserts.sql"
PEOPLE_INSERTS = ROOT_DIR / "people_inserts.sql"
ENROLLMENT_INSERTS = ROOT_DIR / "enrollment_inserts.sql"

def run_cmd(cmd_list, description=None):
    """Run a command and exit if it fails."""
    if description:
        print(f"\n=== {description} ===")
    try:
        subprocess.run(cmd_list, check=True)
    except subprocess.CalledProcessError as e:
        print(f"✖ Error running {cmd_list[0]}: {e}", file=sys.stderr)
        sys.exit(e.returncode)

def main():
    # 1. Build courses.csv from Notes.md
    run_cmd(
        ["python3", "build_courses_csv.py", "--root", str(ROOT_DIR), "--outfile", str(COURSES_CSV)],
        "Step 1: Building courses.csv from Notes.md"
    )

    # 2. Enrich courses.csv with InstructorID and CntStudents
    run_cmd(
        ["python3", "enrich_courses_from_rosters.py", "--courses", str(COURSES_CSV), "--rosters", str(ROOT_DIR)],
        "Step 2: Enriching courses.csv with InstructorID and CntStudents"
    )

    # 3. Build courses_inserts.sql (this will prompt for Terms)
    run_cmd(
        ["python3", "build_courses_inserts.py", "--csv", str(COURSES_ENRICHED_CSV), "--outfile", str(COURSES_INSERTS)],
        "Step 3: Building courses_inserts.sql (will prompt for Term values)"
    )

    # 4. Build people_inserts.sql from rosters
    run_cmd(
        ["python3", "build_people_inserts_positional.py", "--root", str(ROOT_DIR), "--outfile", str(PEOPLE_INSERTS)],
        "Step 4: Building people_inserts.sql"
    )

    # 5. Build enrollment_inserts.sql from rosters + Notes.md
    run_cmd(
        ["python3", "build_enrollment_inserts.py", "--root", str(ROOT_DIR), "--outfile", str(ENROLLMENT_INSERTS)],
        "Step 5: Building enrollment_inserts.sql"
    )

    print("\n✅ All steps completed successfully.")
    print(f"  Courses CSV:      {COURSES_CSV}")
    print(f"  Courses Inserts:  {COURSES_INSERTS}")
    print(f"  People Inserts:   {PEOPLE_INSERTS}")
    print(f"  Enrollment SQL:   {ENROLLMENT_INSERTS}")

if __name__ == "__main__":
    main()
