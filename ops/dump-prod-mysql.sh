#!/usr/bin/env bash
#
# Dump the production Micro-Surveys MySQL database to this machine.
#
# READ-ONLY on production. Runs mysqldump inside the prod container and streams
# the result back over SSH — nothing is written to the production filesystem and
# no schema, data, or config is modified.
#
# The MySQL root password is read from MYSQL_ROOT_PASSWORD *inside* the
# container, so it never appears in your shell history, in the ssh command, or
# in the process list on either host.
#
# Usage:
#   PROD_SSH=user@host ./ops/dump-prod-mysql.sh
#
# Optional overrides:
#   PROD_CONTAINER   name of the MySQL container on prod   (default: mysql-container)
#   PROD_DB          database to dump                      (default: Micro-Surveys)
#   OUT_DIR          where to write the dump               (default: ./backups)

set -euo pipefail

PROD_SSH="${PROD_SSH:-}"
PROD_CONTAINER="${PROD_CONTAINER:-mysql-container}"
PROD_DB="${PROD_DB:-Micro-Surveys}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${OUT_DIR:-$REPO_ROOT/backups}"

if [[ -z "$PROD_SSH" ]]; then
  echo "✖  PROD_SSH is not set." >&2
  echo "   Usage: PROD_SSH=user@host $0" >&2
  exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="$OUT_DIR/${PROD_DB}-${STAMP}.sql.gz"
mkdir -p "$OUT_DIR"

echo "Dumping production MySQL"
echo "  host      : $PROD_SSH"
echo "  container : $PROD_CONTAINER"
echo "  database  : $PROD_DB"
echo "  output    : $OUT_FILE"
echo

# --single-transaction  consistent InnoDB snapshot without locking prod tables
# --routines/--triggers/--events  capture stored programs, not just data
# --set-gtid-purged=OFF  omit GTID state, which would break restore elsewhere
# --databases  emit CREATE DATABASE + USE so the restore is self-contained
#
# gzip runs on the remote side so only compressed bytes cross the network.
REMOTE_CMD=$(cat <<REMOTE
docker exec "$PROD_CONTAINER" sh -c '
  MYSQL_PWD="\$MYSQL_ROOT_PASSWORD" mysqldump -uroot \
    --single-transaction \
    --routines --triggers --events \
    --set-gtid-purged=OFF \
    --databases "$PROD_DB"
' | gzip -c
REMOTE
)

# Preserve the pipeline's exit status: ssh failing must not be masked by a
# successful local write.
set +e
ssh "$PROD_SSH" "$REMOTE_CMD" > "$OUT_FILE"
SSH_STATUS=$?
set -e

if [[ $SSH_STATUS -ne 0 ]]; then
  echo "✖  Dump failed (ssh/mysqldump exit $SSH_STATUS)." >&2
  echo "   Partial file removed: $OUT_FILE" >&2
  rm -f "$OUT_FILE"
  exit $SSH_STATUS
fi

echo "Verifying…"

# 1. The gzip stream must be intact end-to-end.
if ! gzip -t "$OUT_FILE" 2>/dev/null; then
  echo "✖  Corrupt gzip archive — dump is NOT usable." >&2
  exit 1
fi

# 2. mysqldump writes this marker last. Its presence proves the dump ran to
#    completion rather than being truncated by a dropped connection.
if ! gzip -dc "$OUT_FILE" | tail -5 | grep -q "Dump completed"; then
  echo "✖  Missing 'Dump completed' marker — the dump was truncated." >&2
  echo "   Do NOT treat this file as a backup." >&2
  exit 1
fi

TABLES=$(gzip -dc "$OUT_FILE" | grep -c "^CREATE TABLE" || true)
SIZE=$(du -h "$OUT_FILE" | cut -f1)

echo
echo "✔  Dump verified."
echo "   file   : $OUT_FILE"
echo "   size   : $SIZE"
echo "   tables : $TABLES"
echo
echo "Load it into your local stack with:"
echo "   ./ops/restore-local-mysql.sh \"$OUT_FILE\""
