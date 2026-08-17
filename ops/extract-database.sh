#!/usr/bin/env bash
#
# Extract a single database out of a multi-database SQL dump.
#
# Full-server dumps (Adminer's "all databases", mysqldump --all-databases) include
# MySQL's internal `mysql` and `sys` schemas alongside your data. Restoring those
# overwrites the target server's user accounts, passwords, and grants — which can
# lock you out of your own container. They also carry sibling projects you may not
# want locally.
#
# This pulls out exactly one database, plus the dump's header preamble (charset and
# foreign-key settings), and nothing else.
#
# Usage:
#   ./ops/extract-database.sh <dump.sql.gz> <DatabaseName> [output.sql.gz]
#
# Example:
#   ./ops/extract-database.sh backups/db.sql.gz Micro-Surveys

set -euo pipefail

SRC="${1:-}"
DB="${2:-}"

if [[ -z "$SRC" || -z "$DB" ]]; then
  echo "✖  Usage: $0 <dump.sql.gz> <DatabaseName> [output.sql.gz]" >&2
  exit 1
fi

if [[ ! -f "$SRC" ]]; then
  echo "✖  No such file: $SRC" >&2
  exit 1
fi

OUT="${3:-$(dirname "$SRC")/${DB}-only-$(date -u +%Y%m%dT%H%M%SZ).sql.gz}"

# Decompress once to a temp file — the source is scanned several times and
# re-running gunzip per pass is wasteful on large dumps.
TMP=$(mktemp -t extractdb)
cleanup() { rm -f "$TMP"; }
trap cleanup EXIT

if [[ "$SRC" == *.gz ]]; then
  gzip -dc "$SRC" > "$TMP"
else
  cp "$SRC" "$TMP"
fi

# Portable array fill: macOS ships bash 3.2, which has no `mapfile`.
BOUNDS=()
while IFS= read -r n; do
  BOUNDS+=("$n")
done < <(grep -nE '^CREATE DATABASE `' "$TMP" | cut -d: -f1)

if [[ ${#BOUNDS[@]} -eq 0 ]]; then
  echo "✖  No CREATE DATABASE statements found — is this a full-server dump?" >&2
  exit 1
fi

START=$(grep -nE "^CREATE DATABASE \`${DB}\`" "$TMP" | head -1 | cut -d: -f1 || true)

if [[ -z "$START" ]]; then
  echo "✖  Database '$DB' not found in $SRC." >&2
  echo "   Databases present:" >&2
  grep -oE '^CREATE DATABASE `[^`]+`' "$TMP" | sed 's/CREATE DATABASE /     /' >&2
  exit 1
fi

# The section runs until the next CREATE DATABASE, or to EOF if this is the last.
END=""
for line in "${BOUNDS[@]}"; do
  if [[ "$line" -gt "$START" ]]; then
    END=$((line - 1))
    break
  fi
done
TOTAL=$(wc -l < "$TMP")
END="${END:-$TOTAL}"

# The preamble before the first CREATE DATABASE carries SET NAMES / sql_mode /
# foreign_key_checks, which the section's own statements depend on.
HEADER_END=$((BOUNDS[0] - 1))

{
  sed -n "1,${HEADER_END}p" "$TMP"
  sed -n "${START},${END}p" "$TMP"
  echo
  echo "-- Extract complete: database '$DB' from $(basename "$SRC")"
} | gzip -c > "$OUT"

TABLES=$(sed -n "${START},${END}p" "$TMP" | grep -c '^CREATE TABLE' || true)
ROWS=$(sed -n "${START},${END}p" "$TMP" | grep -c '^INSERT INTO' || true)

echo "✔  Extracted '$DB'"
echo "   source      : $SRC"
echo "   lines       : ${START}–${END} (of $TOTAL)"
echo "   tables      : $TABLES"
echo "   INSERT stmts: $ROWS"
echo "   output      : $OUT  ($(du -h "$OUT" | cut -f1))"
echo
echo "Excluded from the source dump:"
grep -oE '^CREATE DATABASE `[^`]+`' "$TMP" | sed 's/CREATE DATABASE `//; s/`$//' \
  | grep -vx "$DB" | sed 's/^/   - /'
