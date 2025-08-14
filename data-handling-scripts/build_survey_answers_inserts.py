#!/usr/bin/env python3
"""
Generate INSERT statements for Survey_Answers from survey.csv.

Rules per row:
- Emit 4 inserts: Q1, Q2, Q3, Q4
- Response_ID       = ResponseId
- Question_ID       = number from 'Q1'/'Q2'/'Q3'/'Q4' (1..4)
- Selected_Option   = value of Q1/Q2/Q3 (for Q4 -> NULL)
- Answer_Text       = NULL for Q1/Q2/Q3 (for Q4 -> value of Q4)

Skips Qualtrics label row and JSON "ImportId" metadata row.

Usage:

cd /Users/robert/Downloads/Canvas

# Basic:
python3 build_survey_answers_inserts.py --csv survey.csv --outfile survey_answers_inserts.sql

# If you want to add a unique key for idempotency:
python3 build_survey_answers_inserts.py --csv survey.csv --outfile survey_answers_inserts.sql --emit-unique

open survey_answers_inserts.sql

"""

import csv, re, sys, argparse
from pathlib import Path
from typing import Dict, List, Optional

JSON_META_RE = re.compile(r'^\s*\{.*"ImportId".*\}\s*$', re.IGNORECASE)
QNUM_RE = re.compile(r"^Q(\d+)$", re.IGNORECASE)

QUESTIONS = ["Q1", "Q2", "Q3", "Q4"]

def esc_str(val: Optional[str]) -> str:
    """Return single-quoted, escaped MySQL literal, or NULL for blank."""
    if val is None: return "NULL"
    s = val.replace("\u00A0"," ").replace("\r\n","\n").replace("\r","\n").strip()
    if s == "": return "NULL"
    s = s.replace("\n"," ").replace("\t"," ")
    s = s.replace("\\","\\\\").replace("'","\\'")
    return f"'{s}'"

def is_label_row(row: Dict[str,str]) -> bool:
    # Heuristic: if multiple fields look like labels rather than data
    hints = {
        "ResponseId": {"Response ID"},
        "Q1": {"Q1"},
        "Q2": {"Q2"},
        "Q3": {"Q3"},
        "Q4": {"Q4"},
    }
    hits = 0
    for k, labels in hints.items():
        v = (row.get(k) or "").strip()
        if v in labels: hits += 1
    return hits >= 2

def is_json_metadata_row(row: Dict[str,str]) -> bool:
    # Qualtrics sometimes includes a JSON mapping row after labels
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

def build_answer_values(r: Dict[str,str]) -> List[str]:
    """
    Build up to 4 VALUES tuples for one response row.
    Returns list of strings like: (Response_ID, Question_ID, Selected_Option, Answer_Text)
    """
    vals: List[str] = []
    response_id = (r.get("ResponseId") or "").strip()
    if not response_id:
        return vals  # skip if no response id

    for q in QUESTIONS:
        qval_raw = r.get(q)
        # Determine Question_ID integer
        m = QNUM_RE.match(q)
        if not m:
            continue
        qid = m.group(1)
        qid_lit = qid  # numeric literal

        if q in ("Q1","Q2","Q3"):
            selected = esc_str(qval_raw)
            answer_text = "NULL"
        else:  # Q4
            selected = "NULL"
            answer_text = esc_str(qval_raw)

        tup = f"({esc_str(response_id)}, {qid_lit}, {selected}, {answer_text})"
        vals.append(tup)

    return vals

def build_insert_chunks(rows: List[Dict[str,str]], batch_size: int) -> List[str]:
    """
    Build batched INSERT statements. We omit Answer_ID to allow AUTO_INCREMENT.
    """
    stmts: List[str] = []
    cols = "(Response_ID, Question_ID, Selected_Option, Answer_Text)"

    # Flatten all values first so batching is consistent across rows
    all_values: List[str] = []
    for r in rows:
        all_values.extend(build_answer_values(r))

    for i in range(0, len(all_values), batch_size):
        chunk = all_values[i:i+batch_size]
        if not chunk:
            continue
        stmt = (
            "INSERT INTO `Survey_Answers` " + cols + "\nVALUES\n  " +
            ",\n  ".join(chunk) + ";"
        )
        stmts.append(stmt)
    return stmts

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build INSERT SQL for Survey_Answers from survey.csv")
    ap.add_argument("--csv", default="survey.csv", help="Path to survey.csv")
    ap.add_argument("--outfile", default="survey_answers_inserts.sql", help="Output .sql file")
    ap.add_argument("--stdout", action="store_true", help="Write SQL to stdout instead of file")
    ap.add_argument("--dbname", default="Micro-Surveys", help="DB name for USE `<db>`;")
    ap.add_argument("--no-use", action="store_true", help="Do not emit USE `<db>`;")
    ap.add_argument("--batch", type=int, default=1000, help="Answer rows per INSERT batch")
    ap.add_argument("--emit-unique", action="store_true",
                    help="Emit a UNIQUE key on (Response_ID, Question_ID) so reruns don't duplicate")
    args = ap.parse_args(argv)

    csv_path = Path(args.csv).expanduser().resolve()
    if not csv_path.exists():
        print(f"✖ CSV not found: {csv_path}", file=sys.stderr)
        return 2

    rows = load_rows(csv_path)
    if not rows:
        print("No data rows found after skipping Qualtrics header/metadata.", file=sys.stderr)
        return 3

    header = ["-- Generated by build_survey_answers_inserts.py", "SET NAMES utf8mb4;"]
    if not args.no_use and args.dbname:
        header.append(f"USE `{args.dbname}`;")

    if args.emit_unique:
        # Add a UNIQUE key so re-running inserts won't duplicate per (Response_ID, Question_ID)
        # No IF NOT EXISTS to stay compatible; remove if already present.
        header.append(
            "ALTER TABLE `Survey_Answers` "
            "ADD UNIQUE KEY `uniq_resp_qid` (`Response_ID`,`Question_ID`);"
        )
    header.append("")

    inserts = build_insert_chunks(rows, args.batch)
    sql_text = "\n".join(header + inserts) + ("\n" if inserts else "")

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
