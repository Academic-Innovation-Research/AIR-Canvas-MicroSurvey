#!/usr/bin/env python3
"""
Generate SQL INSERT statements for Enrollment table
from Canvas roster CSVs, using CanvasID from roster filenames.

Roster CSV expected structure (Canvas export):
Headers include at least: Name, Login ID, SIS ID, Role
And column positions (0-based) match:
0 Profile Picture | 1 Name | 2 Login ID | 3 SIS ID | 4 Section | 5 Role | ...

Filename expectation:
- Roster files are named by CanvasID (recommended): Enrollment/196025.csv
  OR contain CanvasID digits somewhere: Enrollment/course_roster_196025.csv

Output:
INSERT INTO `Enrollment` (CanvasID, Empl_ID, Role) ... ON DUPLICATE KEY UPDATE ...

Usage:
cd /Users/robert/Downloads/Canvas
python3 build_enrollment_inserts.py --root Enrollment --outfile enrollment_inserts.sql --verbose
open enrollment_inserts.sql
"""

import csv
import sys
import re
from pathlib import Path
import argparse
from typing import List, Tuple, Optional

# CSV column positions (0-based)
IDX_EMPL = 3
IDX_ROLE = 5

# CanvasID pattern (grab a digit chunk, typically 5-7 digits, but allow 4+)
CANVAS_ID_RE = re.compile(r"(?<!\d)(\d{4,})(?!\d)")

# Minimal roster header signature (case-insensitive)
EXPECTED_HEADER = {"name", "login id", "sis id", "role"}

def log(msg: str, verbose: bool):
    if verbose:
        print(msg)

def escape_mysql_literal(val: str) -> str:
    if val is None:
        return "NULL"
    s = val.replace("\u00A0", " ").replace("\r\n", "\n").replace("\r", "\n").strip()
    s = s.replace("\n", " ").replace("\t", " ")
    s = s.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{s}'"

def _normalize_header_cell(cell: str) -> str:
    s = (cell or "").strip().strip('"').strip("'").strip()
    s = s.lstrip("\ufeff")  # BOM
    return s.casefold()

def _is_roster_header(cols: List[str]) -> bool:
    normalized = {_normalize_header_cell(c) for c in cols if c is not None}
    return EXPECTED_HEADER.issubset(normalized)

def extract_canvas_id_from_filename(path: Path) -> Optional[int]:
    """
    Extract CanvasID from filename stem. Examples:
      196025.csv -> 196025
      course_roster_196025.csv -> 196025
    """
    m = CANVAS_ID_RE.search(path.stem)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None

def discover_csvs(root: Path, verbose: bool) -> List[Path]:
    found = sorted({p for pat in ("*.csv", "*.CSV") for p in root.rglob(pat) if p.is_file()})
    if not found:
        print("No CSV files found under:", root, file=sys.stderr)
    else:
        log(f"Found {len(found)} CSV file(s) under {root}", verbose)
    return list(found)

def read_csv_rows_roster_only(path: Path, verbose: bool) -> List[Tuple[str, str]]:
    """
    Return list of (Empl_ID, Role) from a roster CSV (positional parsing),
    but only if the header matches a Canvas roster signature.
    """
    rows: List[Tuple[str, str]] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)

            # Read header row and validate
            try:
                header_cols = next(reader)
            except StopIteration:
                log(f"⚠ Skipping empty CSV: {path.name}", verbose)
                return []

            if not _is_roster_header(header_cols):
                log(f"⚠ Skipping non-roster CSV: {path.name}", verbose)
                return []

            for cols in reader:
                if len(cols) <= max(IDX_EMPL, IDX_ROLE):
                    continue
                empl = (cols[IDX_EMPL] or "").strip()
                role = (cols[IDX_ROLE] or "").strip()
                if empl and role:
                    rows.append((empl, role))

    except Exception as e:
        print(f"✖ Error reading {path}: {e}", file=sys.stderr)

    return rows

def batch_insert_values(canvas_id: int, rows: List[Tuple[str, str]], batch_size: int = 500) -> List[str]:
    stmts: List[str] = []
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        values_sql = [
            f"({canvas_id}, {escape_mysql_literal(empl)}, {escape_mysql_literal(role)})"
            for empl, role in chunk
        ]
        stmt = (
            "INSERT INTO `Enrollment` (CanvasID, Empl_ID, Role)\nVALUES\n  "
            + ",\n  ".join(values_sql)
            + "\nON DUPLICATE KEY UPDATE Empl_ID = Empl_ID;"
        )
        stmts.append(stmt)
    return stmts

def main() -> int:
    ap = argparse.ArgumentParser(description="Generate Enrollment INSERT SQL from roster CSVs (CanvasID from filename).")
    ap.add_argument("--root", default=".", help="Directory to scan recursively for roster CSVs")
    ap.add_argument("--outfile", default="enrollment_inserts.sql", help="Output .sql file")
    ap.add_argument("--stdout", action="store_true", help="Print SQL to stdout instead of writing file")
    ap.add_argument("--dbname", default="Micro-Surveys", help="DB name for USE `<db>`;")
    ap.add_argument("--no-use", action="store_true", help="Do not emit USE `<db>`;")
    ap.add_argument("--batch", type=int, default=500, help="Rows per INSERT batch")
    ap.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    csv_files = discover_csvs(root, args.verbose)
    if not csv_files:
        return 1

    sql_lines: List[str] = []
    sql_lines.append("-- Generated by build_enrollment_inserts.py (CanvasID from filename)")
    sql_lines.append("SET NAMES utf8mb4;")
    if not args.no_use and args.dbname:
        sql_lines.append(f"USE `{args.dbname}`;")
    sql_lines.append("")

    emitted_courses = 0
    emitted_rows = 0

    for csv_path in csv_files:
        canvas_id = extract_canvas_id_from_filename(csv_path)
        if canvas_id is None:
            log(f"⚠ Skipping CSV with no CanvasID in filename: {csv_path.name}", args.verbose)
            continue

        rows = read_csv_rows_roster_only(csv_path, args.verbose)
        if not rows:
            log(f"⚠ No valid roster rows in {csv_path.name} (or not a roster CSV).", args.verbose)
            continue

        sql_lines.extend(batch_insert_values(canvas_id, rows, batch_size=args.batch))
        sql_lines.append("")
        emitted_courses += 1
        emitted_rows += len(rows)
        log(f"✔ {csv_path.name}: CanvasID={canvas_id}, rows={len(rows)}", args.verbose)

    if emitted_rows == 0:
        print("No enrollment rows emitted. Check roster filenames (CanvasID) and CSV header format.", file=sys.stderr)
        # Still write header if you want; returning non-zero makes failures obvious
        if args.stdout:
            print("\n".join(sql_lines))
        else:
            outpath = Path(args.outfile).expanduser().resolve()
            outpath.parent.mkdir(parents=True, exist_ok=True)
            outpath.write_text("\n".join(sql_lines), encoding="utf-8")
            print(f"⚠ Wrote header-only SQL to {outpath}", file=sys.stderr)
        return 2

    sql_text = "\n".join(sql_lines)
    if args.stdout:
        print(sql_text)
    else:
        outpath = Path(args.outfile).expanduser().resolve()
        outpath.parent.mkdir(parents=True, exist_ok=True)
        outpath.write_text(sql_text, encoding="utf-8")
        print(f"✅ Wrote {emitted_rows} enrollment rows across {emitted_courses} course roster file(s) to {outpath}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
