#!/usr/bin/env bash
#
# Restore a production dump into the LOCAL Docker MySQL container.
#
# DESTRUCTIVE LOCALLY. mysqldump emits DROP TABLE IF EXISTS before each CREATE,
# so every table in the target database is replaced. Production is never
# contacted by this script.
#
# Usage:
#   ./ops/restore-local-mysql.sh backups/Micro-Surveys-20260812T125700Z.sql.gz
#   ./ops/restore-local-mysql.sh -y <file>     # skip the confirmation prompt
#
# Optional overrides:
#   LOCAL_CONTAINER   local MySQL container name   (default: mysql-container)

set -euo pipefail

LOCAL_CONTAINER="${LOCAL_CONTAINER:-mysql-container}"
ASSUME_YES=0
FORCE=0

while [[ "${1:-}" == -* ]]; do
  case "$1" in
    -y) ASSUME_YES=1; shift ;;
    -f) FORCE=1;      shift ;;
    *)  echo "✖  Unknown option: $1" >&2
        echo "   Usage: $0 [-y] [-f] <dump.sql.gz>" >&2
        exit 1 ;;
  esac
done

DUMP_FILE="${1:-}"

if [[ -z "$DUMP_FILE" ]]; then
  echo "✖  No dump file given." >&2
  echo "   Usage: $0 [-y] <dump.sql.gz>" >&2
  exit 1
fi

if [[ ! -f "$DUMP_FILE" ]]; then
  echo "✖  No such file: $DUMP_FILE" >&2
  exit 1
fi

if ! docker inspect --format '{{.State.Running}}' "$LOCAL_CONTAINER" >/dev/null 2>&1; then
  echo "✖  Container '$LOCAL_CONTAINER' is not running." >&2
  echo "   Start the stack first: cd data-handling-scripts && python3 start.py" >&2
  exit 1
fi

# Refuse to restore a file that failed to transfer completely — a truncated
# dump would drop the existing tables and then stop partway through reloading.
if ! gzip -t "$DUMP_FILE" 2>/dev/null; then
  echo "✖  Corrupt gzip archive: $DUMP_FILE" >&2
  exit 1
fi
# Completeness marker. Each dump tool signs off differently, and a missing
# sign-off is the signature of a transfer that died partway through:
#   mysqldump  →  "-- Dump completed on <date>"
#   Adminer    →  a bare "-- <ISO timestamp>" as the final line
#   extract-database.sh → "-- Extract complete"
TAIL=$(gzip -dc "$DUMP_FILE" | tail -5)
if ! grep -qE "Dump completed|Extract complete|^-- [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}" <<<"$TAIL"; then
  if [[ $FORCE -eq 1 ]]; then
    echo "⚠  No completeness marker found — proceeding because -f was given." >&2
  else
    echo "✖  No completeness marker found — the dump may be truncated." >&2
    echo "   Refusing to restore. Re-run with -f if you have verified this file yourself." >&2
    exit 1
  fi
fi

TARGET_DB=$(gzip -dc "$DUMP_FILE" | grep -m1 -oE '^USE `[^`]+`' | sed 's/^USE `//; s/`$//' || true)
TARGET_DB="${TARGET_DB:-unknown}"

# Report what is about to be destroyed, so the prompt is an informed one.
EXISTING=$(docker exec "$LOCAL_CONTAINER" sh -c \
  "MYSQL_PWD=\"\$MYSQL_ROOT_PASSWORD\" mysql -uroot --batch --skip-column-names \
   -e 'SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=\"$TARGET_DB\"'" \
  2>/dev/null || echo "0")

echo "Restore to LOCAL MySQL"
echo "  file      : $DUMP_FILE"
echo "  container : $LOCAL_CONTAINER"
echo "  database  : $TARGET_DB"
echo "  existing  : $EXISTING table(s) — these will be dropped and replaced"
echo

if [[ $ASSUME_YES -eq 0 ]]; then
  read -r -p "Proceed? [y/N] " reply
  case "$reply" in
    [yY]|[yY][eE][sS]) ;;
    *) echo "Aborted."; exit 0 ;;
  esac
fi

echo "Restoring…"
# Adminer (and mysqldump without --databases) emits a bare `CREATE DATABASE`,
# which fails with ERROR 1007 because docker-compose already created the database
# via MYSQL_DATABASE. Relax it to IF NOT EXISTS so the restore is idempotent. The
# dump's own DROP TABLE IF EXISTS statements still replace the contents.
# The pattern only matches a bare form — an existing IF NOT EXISTS has a letter,
# not a backtick, after "CREATE DATABASE ".
#
# Adminer dumps each VIEW twice: first a CREATE TABLE stub so that dependent
# objects resolve, then later a DROP TABLE followed by the real CREATE VIEW.
# When it cannot introspect a view's columns it emits an empty stub —
# `CREATE TABLE `x` ();` — which is not valid SQL and aborts the restore.
# Giving the stub one throwaway column makes it parse; the DROP TABLE that
# precedes the real view definition discards it moments later.
gzip -dc "$DUMP_FILE" \
  | sed -E 's/^CREATE DATABASE (`)/CREATE DATABASE IF NOT EXISTS \1/' \
  | sed -E 's/^CREATE TABLE (`[^`]+`) \(\);/CREATE TABLE \1 (`_adminer_view_placeholder` int);/' \
  | docker exec -i "$LOCAL_CONTAINER" sh -c \
      'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot'

echo
echo "✔  Restore complete. Row counts:"
docker exec "$LOCAL_CONTAINER" sh -c \
  "MYSQL_PWD=\"\$MYSQL_ROOT_PASSWORD\" mysql -uroot --table -e '
     SELECT table_name AS \"Table\", table_rows AS \"~Rows\"
     FROM information_schema.tables
     WHERE table_schema=\"$TARGET_DB\"
     ORDER BY table_name'"

echo
echo "Note: ~Rows is InnoDB's estimate. For exact counts, query the table directly."
