#!/usr/bin/env bash
#
# Replace this machine's Metabase application database with one from production.
#
# The application database holds EVERYTHING Metabase knows that is not in your
# data warehouse: dashboards, questions, collections, users, permissions,
# settings, and the data-source connection definitions. Replacing it replicates
# production's Metabase wholesale.
#
# Metabase is stopped before the swap — H2 holds file locks and a hot copy is
# silently corruptible. The existing app DB is kept, and automatically rolled
# back if the new one fails to boot.
#
# Usage:
#   ./ops/import-metabase-h2.sh <metabase.db.mv.db from production>
#
# AFTER IMPORTING, read the warning this script prints about re-pointing the
# data source. The imported app DB points at PRODUCTION's database.

set -euo pipefail

SRC="${1:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MB_DIR="$REPO_ROOT/Metabase"
LIVE="$MB_DIR/metabase.db.mv.db"
CONTAINER="${METABASE_CONTAINER:-metabase-container}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ -z "$SRC" ]]; then
  echo "✖  Usage: $0 <metabase.db.mv.db>" >&2
  exit 1
fi
if [[ ! -f "$SRC" ]]; then
  echo "✖  No such file: $SRC" >&2
  exit 1
fi

# H2's MVStore format opens with a plain-text header beginning "H:2,". Checking
# for it positively catches every wrong-file case at once — an HTML error page, a
# still-gzipped download, a .sql dump, or a truncated transfer — rather than
# surfacing as an unexplained Metabase boot failure after the swap.
MAGIC=$(head -c 4 "$SRC" 2>/dev/null || true)
if [[ "$MAGIC" != "H:2," ]]; then
  echo "✖  $SRC is not an H2 database file." >&2
  echo "   Expected it to begin with 'H:2,' — got: $(head -c 16 "$SRC" | tr -c '[:print:]' '.')" >&2
  echo "   If it is still compressed, decompress it first." >&2
  exit 1
fi

SIZE=$(wc -c < "$SRC" | tr -d ' ')
if [[ "$SIZE" -lt 100000 ]]; then
  echo "✖  $SRC is only ${SIZE} bytes — too small to be a real Metabase app DB." >&2
  exit 1
fi

# The H2 header sits in the first bytes, so a truncated transfer still looks
# valid above. Only comparing against the source proves the file is whole.
# On the production host:
#     stat -c %s <file>        # size
#     sha256sum <file>         # checksum
# then pass them here as EXPECT_SIZE / EXPECT_SHA256.
if [[ -n "${EXPECT_SIZE:-}" ]]; then
  if [[ "$SIZE" != "$EXPECT_SIZE" ]]; then
    echo "✖  Size mismatch — the transfer is incomplete." >&2
    echo "   expected : $EXPECT_SIZE bytes" >&2
    echo "   got      : $SIZE bytes ($(( SIZE * 100 / EXPECT_SIZE ))%)" >&2
    exit 1
  fi
  echo "✔  Size matches source ($SIZE bytes)."
fi

if [[ -n "${EXPECT_SHA256:-}" ]]; then
  ACTUAL=$(shasum -a 256 "$SRC" | cut -d' ' -f1)
  if [[ "$ACTUAL" != "$EXPECT_SHA256" ]]; then
    echo "✖  Checksum mismatch — the file differs from the source." >&2
    echo "   expected : $EXPECT_SHA256" >&2
    echo "   got      : $ACTUAL" >&2
    exit 1
  fi
  echo "✔  Checksum matches source."
elif [[ -z "${EXPECT_SIZE:-}" ]]; then
  echo "⚠  No EXPECT_SIZE or EXPECT_SHA256 given — a truncated file cannot be"
  echo "   detected from its contents alone. A partial H2 file keeps a valid"
  echo "   header and may boot with silently missing dashboards."
  echo
fi

LOCAL_VERSION=$(curl -s --max-time 5 http://localhost:3000/api/session/properties 2>/dev/null \
  | sed -n 's/.*"tag":"\([^"]*\)".*/\1/p' | head -1 || true)

echo "Import Metabase application database"
echo "  source        : $SRC ($(du -h "$SRC" | cut -f1))"
echo "  target        : $LIVE"
echo "  container     : $CONTAINER"
echo "  local version : ${LOCAL_VERSION:-unknown}"
echo
echo "⚠  The source MUST come from the same Metabase version as this instance."
echo "   A newer app DB will not boot on an older Metabase. An older one is"
echo "   silently upgraded in place and cannot be moved back."
echo
read -r -p "Proceed? [y/N] " reply
case "$reply" in
  [yY]|[yY][eE][sS]) ;;
  *) echo "Aborted."; exit 0 ;;
esac

echo
echo "[1/4] Stopping Metabase…"
docker stop "$CONTAINER" >/dev/null
echo "      stopped."

echo "[2/4] Preserving current app DB…"
BACKUP=""
if [[ -f "$LIVE" ]]; then
  BACKUP="$MB_DIR/metabase.db.mv.db.pre-import-$STAMP"
  cp "$LIVE" "$BACKUP"
  echo "      saved → $(basename "$BACKUP")"
else
  echo "      none present (fresh install)"
fi

echo "[3/4] Installing production app DB…"
cp "$SRC" "$LIVE"
# A trace log from the previous database is meaningless against the new one and
# only confuses later debugging.
rm -f "$MB_DIR/metabase.db.trace.db"
echo "      installed."

echo "[4/4] Starting Metabase…"
docker start "$CONTAINER" >/dev/null
printf "      waiting for it to come up"
UP=0
for _ in $(seq 1 60); do
  sleep 3
  printf "."
  CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://localhost:3000/api/health 2>/dev/null || echo 000)
  if [[ "$CODE" == "200" ]]; then UP=1; break; fi
done
echo

if [[ $UP -ne 1 ]]; then
  echo
  echo "✖  Metabase did not become healthy within 3 minutes."
  echo "   Logs:  docker logs $CONTAINER --tail 50"
  if [[ -n "$BACKUP" ]]; then
    echo
    read -r -p "Roll back to the previous app DB? [Y/n] " rb
    case "$rb" in
      [nN]|[nN][oO]) echo "Left in place for debugging." ;;
      *) docker stop "$CONTAINER" >/dev/null 2>&1 || true
         cp "$BACKUP" "$LIVE"
         docker start "$CONTAINER" >/dev/null
         echo "✔  Rolled back. The imported file did not replace your previous state." ;;
    esac
  fi
  exit 1
fi

NEW_VERSION=$(curl -s --max-time 5 http://localhost:3000/api/session/properties 2>/dev/null \
  | sed -n 's/.*"tag":"\([^"]*\)".*/\1/p' | head -1 || true)

echo
echo "✔  Metabase is up on the imported application database."
echo "   version : ${NEW_VERSION:-unknown}"
echo "   rollback: ${BACKUP:-none saved}"
echo
echo "───────────────────────────────────────────────────────────────────"
echo "⚠  BEFORE YOU BROWSE ANY DASHBOARD — re-point the data source."
echo
echo "   The imported app DB carries PRODUCTION's connection settings. If"
echo "   production's database is reachable from this machine, your local"
echo "   Metabase is now querying PRODUCTION, not your local copy."
echo
echo "   Fix it now:  http://localhost:3000/admin/databases"
echo "     host     → db          (the container name on the compose network)"
echo "     port     → 3306"
echo "     database → Micro-Surveys"
echo
echo "   Log in with your PRODUCTION Metabase credentials — local accounts"
echo "   were replaced by production's user table."
echo "───────────────────────────────────────────────────────────────────"
