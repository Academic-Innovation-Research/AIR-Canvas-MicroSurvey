#!/usr/bin/env bash
#
# Back up the Metabase application database — every dashboard, question,
# collection, user, and permission.
#
# This is the payoff of migrating off H2. The old procedure was: stop Metabase,
# copy a 12 MB binary blob, hope it was consistent, with no way to inspect or
# partially restore it. Now it is a plain pg_dump that runs against a live
# instance with no downtime, and the output is readable SQL.
#
# Safe to run any time. Metabase stays up; PostgreSQL provides a consistent
# snapshot without blocking readers or writers.
#
# Usage:
#   ./ops/backup-metabase-appdb.sh [output-directory]
#
# Restore with:
#   gzip -dc <file> | docker exec -i metabase-postgres psql -U <user> -d <db>

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$REPO_ROOT/backups}"
CONTAINER="${MB_APP_DB_CONTAINER:-metabase-postgres}"

# Credentials live in Metabase/.env alongside the compose file that uses them.
ENV_FILE="$REPO_ROOT/Metabase/.env"
_cfg() {
  local key="$1" default="${2:-}"
  local val
  val=$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- || true)
  echo "${val:-$default}"
}

DB_NAME=$(_cfg MB_APP_DB_NAME metabase_app)
DB_USER=$(_cfg MB_APP_DB_USER metabase)

if ! docker inspect --format '{{.State.Running}}' "$CONTAINER" >/dev/null 2>&1; then
  echo "✖  Container '$CONTAINER' is not running." >&2
  echo "   Start the stack: cd Metabase && docker compose up -d" >&2
  exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="$OUT_DIR/metabase-appdb-${STAMP}.sql.gz"
mkdir -p "$OUT_DIR"

echo "Backing up Metabase application database"
echo "  container : $CONTAINER"
echo "  database  : $DB_NAME"
echo "  output    : $OUT_FILE"
echo

set +e
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --clean --if-exists \
  | gzip -c > "$OUT_FILE"
STATUS=${PIPESTATUS[0]}
set -e

if [[ $STATUS -ne 0 ]]; then
  echo "✖  pg_dump failed (exit $STATUS). Removing partial file." >&2
  rm -f "$OUT_FILE"
  exit $STATUS
fi

# A dump that cannot be decompressed, or that stops before PostgreSQL's own
# end marker, is a truncated file wearing a backup's name.
if ! gzip -t "$OUT_FILE" 2>/dev/null; then
  echo "✖  Corrupt gzip archive — backup is NOT usable." >&2
  exit 1
fi
if ! gzip -dc "$OUT_FILE" | tail -5 | grep -q "PostgreSQL database dump complete"; then
  echo "✖  Missing completion marker — the dump was truncated." >&2
  exit 1
fi

# Report what was actually captured, so an empty-but-valid dump is obvious.
DASH=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A \
        -c "SELECT COUNT(*) FROM report_dashboard WHERE NOT archived" 2>/dev/null || echo "?")
CARDS=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A \
        -c "SELECT COUNT(*) FROM report_card WHERE NOT archived" 2>/dev/null || echo "?")
USERS=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A \
        -c "SELECT COUNT(*) FROM core_user WHERE is_active" 2>/dev/null || echo "?")

echo "✔  Backup verified."
echo "   file       : $OUT_FILE ($(du -h "$OUT_FILE" | cut -f1))"
echo "   dashboards : $DASH"
echo "   questions  : $CARDS"
echo "   users      : $USERS"
echo
echo "Restore:"
echo "   gzip -dc \"$OUT_FILE\" | docker exec -i $CONTAINER psql -U $DB_USER -d $DB_NAME"
