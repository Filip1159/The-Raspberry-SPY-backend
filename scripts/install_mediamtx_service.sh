#!/usr/bin/env bash
# Installs MediaMTX (already extracted to /mediamtx, see configs/CONFIGS.MD) as a systemd service and copies its config.
#   scripts/install_mediamtx_service.sh            # copy configs/mediamtx.yml, install the unit, enable on boot, (re)start
#   scripts/install_mediamtx_service.sh --print    # only print the unit
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="${SERVICE_USER:-$(id -un)}"
UNIT="$(sed -e "s|__USER__|$SERVICE_USER|g" "$WORKDIR/configs/mediamtx.service")"

if [ "${1:-}" = "--print" ]; then
    echo "$UNIT"
    exit 0
fi

if [ ! -x /mediamtx/mediamtx ]; then
    echo "/mediamtx/mediamtx not found: download and extract MediaMTX first (configs/CONFIGS.MD)" >&2
    exit 1
fi

# a MediaMTX started by hand holds the ports 8554/8888 and the camera
if ! systemctl is-active --quiet mediamtx.service && pgrep -x mediamtx > /dev/null; then
    echo "MediaMTX is running outside systemd. Stop it (Ctrl+C in its terminal or: sudo pkill mediamtx) and run this script again." >&2
    exit 1
fi

sudo cp "$WORKDIR/configs/mediamtx.yml" /mediamtx/mediamtx.yml
echo "$UNIT" | sudo tee /etc/systemd/system/mediamtx.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable mediamtx.service
sudo systemctl restart mediamtx.service
echo "Started. Logs: journalctl -u mediamtx -f"
