#!/usr/bin/env bash
#
# Run the four web tools as systemd services so they survive logout and reboot,
# replacing `python3 start.py` on a server. start.py remains the way to run
# them on a laptop.
#
#   dashboard           :5010      survey_upload_app   :5002
#   upload_app          :5001      export_app          :5003
#
# Usage:
#   sudo ./ops/install-services.sh              # install, enable, start
#   sudo ./ops/install-services.sh --uninstall
#
# Logs:    journalctl -u 'microsurvey@*' -f
# Status:  systemctl status 'microsurvey@*'

set -euo pipefail

TOOLS=(dashboard upload_app survey_upload_app export_app)
UNIT=/etc/systemd/system/microsurvey@.service
REPO="$(cd "$(dirname "$0")/.." && pwd)"
# The tools read Metabase/.env (chmod 600), so they must run as its owner.
RUN_AS="$(stat -c %U "$REPO/Metabase/.env")"

if [[ $EUID -ne 0 ]]; then
  echo "✖  Needs root to write $UNIT. Re-run with sudo." >&2
  exit 1
fi

if [[ "${1:-}" == "--uninstall" ]]; then
  for t in "${TOOLS[@]}"; do systemctl disable --now "microsurvey@$t" 2>/dev/null || true; done
  rm -f "$UNIT"
  systemctl daemon-reload
  echo "✔  Removed."
  exit 0
fi

if ! id -nG "$RUN_AS" | grep -qw docker; then
  echo "✖  $RUN_AS is not in the docker group; the tools could not reach MySQL." >&2
  exit 1
fi

# Re-running reinstalls: stop our own instances first, or the check below
# would find them holding the ports and refuse.
for t in "${TOOLS[@]}"; do systemctl stop "microsurvey@$t" 2>/dev/null || true; done

# A start.py left running holds the ports and the services would crash-loop.
for port in 5010 5001 5002 5003; do
  if ss -ltnH "sport = :$port" | grep -q .; then
    echo "✖  Port $port is already in use — stop start.py (or whatever holds it) first." >&2
    exit 1
  fi
done

sed -e "s|@REPO@|$REPO|g" -e "s|@USER@|$RUN_AS|g" \
  "$REPO/ops/systemd/microsurvey@.service" > "$UNIT"
systemctl daemon-reload
for t in "${TOOLS[@]}"; do systemctl enable --now "microsurvey@$t"; done

sleep 2
systemctl --no-pager --lines=0 status "microsurvey@*" | grep -E "●|Active:"
echo
echo "✔  Installed for $RUN_AS from $REPO"
echo "   Logs: journalctl -u 'microsurvey@*' -f"

# The tools run on the host, so unlike Docker's published ports (which bypass
# ufw) they are subject to it. Without a rule, other machines time out while
# every test run on this box passes. Not opened automatically: the tools have
# no auth and write as MySQL root, so the source range is a deliberate choice.
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  echo
  echo "⚠  ufw is active and will block other machines. Open the ports to your LAN only, e.g.:"
  echo "   sudo ufw allow from 192.168.1.0/24 to any port 5001:5003,5010 proto tcp comment 'MicroSurvey tools (LAN only)'"
fi
