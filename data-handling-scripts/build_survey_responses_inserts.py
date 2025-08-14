#!/usr/bin/env python3

"""
Build INSERT statements for Survey_Responses from survey.csv.

CSV → MySQL mapping:
  Response_ID        <= ResponseId
  Survey_ID          <= constant (default: 'ERAU_ASIA')
  IPAddress          <= IPAddress
  Progress           <= Progress
  Duration           <= Duration
  Finished           <= Finished           (coerced to 1/0)
  RecordedDate       <= RecordedDate
  LocationLatitude   <= LocationLatitude
  LocationLongitude  <= LocationLongitude
  UserLanguage       <= UserLanguage
  CanvasID           <= last digits from 'Course' URL (e.g., .../3517134/)
  Created_At         <= EndDate

Outputs batched INSERTs with:
  ON DUPLICATE KEY UPDATE Response_ID = Response_ID
(If you want this to no-op on duplicates, ensure Response_ID is UNIQUE in DB.)

Usage:
cd /Users/robert/Downloads/Canvas

# Basic
python3 build_survey_responses_inserts.py --csv survey.csv --outfile survey_responses_inserts.sql

# If you want the script to also add a unique index on Response_ID (once):
python3 build_survey_responses_inserts.py --csv survey.csv --outfile survey_responses_inserts.sql --emit-unique

"""


#!/usr/bin/env python3
import csv, re, sys
from pathlib import Path
import argparse
from typing import Optional, List, Dict
from datetime import datetime

LAST_NUMBER_RE = re.compile(r".*?(\d+)\D*$")  # last run of digits
JSON_META_RE = re.compile(r'^\s*\{.*"ImportId".*\}\s*$', re.IGNORECASE)

# ------- helpers (unchanged except where noted) -------
def esc_str(val: Optional[str]) -> str:
    if val is None: return "NULL"
    s = val.replace("\u00A0"," ").replace("\r\n","\n").replace("\r","\n").strip()
    if s == "": return "NULL"
    s = s.replace("\n"," ").replace("\t"," ").replace("\\","\\\\").replace("'","\\'")
    return f"'{s}'"

def to_int(val: Optional[str]) -> str:
    if val is None: return "NULL"
    v = val.strip()
    if v == "": return "NULL"
    try: return str(int(float(v)))
    except: return "NULL"

def to_float(val: Optional[str]) -> str:
    if val is None: return "NULL"
    v = val.strip()
    if v == "": return "NULL"
    try: return str(float(v))
    except: return "NULL"

def to_bool01(val: Optional[str]) -> str:
    if val is None: return "NULL"
    v = val.strip().lower()
    if v in {"1","true","t","yes","y"}: return "1"
    if v in {"0","false","f","no","n"}: return "0"
    try: return "1" if int(v) != 0 else "0"
    except: return "NULL"

_DT_FMTS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y %I:%M %p",
    "%m/%d/%y %H:%M",
    "%m/%d/%y %I:%M %p",
]
def to_dt_literal(val: Optional[str]) -> str:
    if not val: return "NULL"
    s = val.strip()
    if s == "": return "NULL"
    for fmt in _DT_FMTS:
        try:
            dt = datetime.strptime(s, fmt)
            return f"'{dt.strftime('%Y-%m-%d %H:%M:%S')}'"
        except:
            pass
    try:
        s2 = re.sub(r"([+-]\d{2}):?(\d{2})$", r"\1\2", s)  # normalize TZ colon
        dt = datetime.strptime(s2, "%Y-%m-%dT%H:%M:%S%z")
        return f"'{dt.strftime('%Y-%m-%d %H:%M:%S')}'"
    except:
        return esc_str(s)

def last_digits(s: Optional[str]) -> Optional[str]:
    if not s: return None
    m = LAST_NUMBER_RE.match(s.strip())
    return m.group(1) if m else None

# ----- NEW: detectors for pre-data rows -----
def is_label_row(row: Dict[str,str]) -> bool:
    hints = {
        "ResponseId": {"Response ID"},
        "IPAddress": {"IP Address"},
        "Progress": {"Progress"},
        "Duration": {"Duration (in seconds)","Duration"},
        "Finished": {"Finished"},
        "RecordedDate": {"Recorded Date"},
        "EndDate": {"End Date"},
        "LocationLatitude": {"Location Latitude","Latitude"},
        "LocationLongitude": {"Location Longitude","Longitude"},
        "UserLanguage": {"User Language"},
        "Course": {"Course"},
    }
    hits = 0
    for k, labels in hints.items():
        v = (row.get(k) or "").strip()
        if v in labels: hits += 1
    return hits >= 2

def is_json_metadata_row(row: Dict[str,str]) -> bool:
    """
    Qualtrics sometimes adds a JSON settings row right after labels.
    Consider it metadata if >=2 fields look like {"ImportId": ...}.
    """
    matches = 0
    for v in row.values():
        if v and JSON_META_RE.match(v):
            matches += 1
            if matches >= 2:
                return True
    return False

def load_rows(csv_path: Path) -> List[Dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            if is_label_row(r):         # skip label row
                continue
            if is_json_metadata_row(r): # skip JSON metadata row
                continue
            rows.append(r)
        return rows

def build_insert_chunks(rows: List[Dict[str, str]], survey_id: str, batch_size: int) -> List[str]:
    cols = ("(Response_ID, Survey_ID, IPAddress, Progress, Duration, Finished, "
            "RecordedDate, LocationLatitude, LocationLongitude, UserLanguage, CanvasID, Created_At)")
    stmts: List[str] = []
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i+batch_size]
        values_sql = []
        for r in chunk:
            response_id  = esc_str(r.get("ResponseId"))
            survey_id_l  = esc_str(survey_id)
            ip           = esc_str(r.get("IPAddress"))
            progress     = to_int(r.get("Progress"))
            duration     = to_int(r.get("Duration"))
            finished     = to_bool01(r.get("Finished"))
            recorded     = to_dt_literal(r.get("RecordedDate"))
            lat          = to_float(r.get("LocationLatitude"))
            lon          = to_float(r.get("LocationLongitude"))
            lang         = esc_str(r.get("UserLanguage"))
            canvas_id    = to_int(last_digits(r.get("Course")))
            created_at   = to_dt_literal(r.get("EndDate"))
            values_sql.append(
                f"({response_id}, {survey_id_l}, {ip}, {progress}, {duration}, {finished}, "
                f"{recorded}, {lat}, {lon}, {lang}, {canvas_id}, {created_at})"
            )
        stmt = (
            "INSERT INTO `Survey_Responses` "
            f"{cols}\nVALUES\n  " + ",\n  ".join(values_sql) +
            "\nON DUPLICATE KEY UPDATE Response_ID = Response_ID;"
        )
        stmts.append(stmt)
    return stmts

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build INSERT SQL for Survey_Responses from survey.csv")
    ap.add_argument("--csv", default="survey.csv", help="Path to survey.csv")
    ap.add_argument("--outfile", default="survey_responses_inserts.sql", help="Output .sql file")
    ap.add_argument("--stdout", action="store_true", help="Write SQL to stdout instead of file")
    ap.add_argument("--dbname", default="Micro-Surveys", help="DB name for USE `<db>`;")
    ap.add_argument("--no-use", action="store_true", help="Do not emit USE `<db>`;")
    ap.add_argument("--survey-id", default="ERAU_ASIA", help="Constant Survey_ID value")
    ap.add_argument("--batch", type=int, default=500, help="Rows per INSERT batch")
    ap.add_argument("--emit-unique", action="store_true",
                    help="Emit CREATE UNIQUE INDEX on Survey_Responses(Response_ID)")
    args = ap.parse_args(argv)

    csv_path = Path(args.csv).expanduser().resolve()
    if not csv_path.exists():
        print(f"✖ CSV not found: {csv_path}", file=sys.stderr)
        return 2

    rows = load_rows(csv_path)
    if not rows:
        print("No rows found in CSV after skipping label/metadata rows.", file=sys.stderr)
        return 3

    header = ["-- Generated by build_survey_responses_inserts.py", "SET NAMES utf8mb4;"]
    if not args.no_use and args.dbname:
        header.append(f"USE `{args.dbname}`;")
    if args.emit_unique:
        header.append("CREATE UNIQUE INDEX `uniq_survey_responses_resp_id` "
                      "ON `Survey_Responses` (`Response_ID`);")
    header.append("")

    inserts = build_insert_chunks(rows, args.survey_id, args.batch)
    sql_text = "\n".join(header + inserts) + "\n"

    if args.stdout:
        print(sql_text, end="")
    else:
        out = Path(args.outfile).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            f.write(sql_text)
        print(f"✅ Wrote SQL to {out}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
