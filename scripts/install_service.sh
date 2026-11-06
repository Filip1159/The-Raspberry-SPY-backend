#!/usr/bin/env bash
# Installs and starts the backend as a systemd service on the Raspberry (run it from the checkout, as the user that runs the backend).
#   scripts/install_service.sh            # install, enable on boot, start
#   scripts/install_service.sh --print    # only print the unit that would be installed
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="${SERVICE_USER:-$(id -un)}"

# the virtualenv created by scripts/setup_venv.sh, else the system python
if [ -x "$WORKDIR/.venv/bin/python" ]; then PYTHON="$WORKDIR/.venv/bin/python"
else PYTHON="$(command -v python3)"
fi

UNIT="$(sed -e "s|__USER__|$SERVICE_USER|g" -e "s|__WORKDIR__|$WORKDIR|g" -e "s|__PYTHON__|$PYTHON|g" "$WORKDIR/configs/raspberry-spy.service")"

if [ "${1:-}" = "--print" ]; then
    echo "$UNIT"
    exit 0
fi

echo "Installing raspberry-spy.service (user $SERVICE_USER, $PYTHON, $WORKDIR)"
echo "$UNIT" | sudo tee /etc/systemd/system/raspberry-spy.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable raspberry-spy.service

# a backend that was started by hand holds the GPIO pins and port 8080: stop it first
if ! systemctl is-active --quiet raspberry-spy.service && pgrep -f "python.* main.py" > /dev/null; then
    echo "Another 'python main.py' is running. Stop it (Ctrl+C in its terminal or pkill -f 'main.py'), then run: sudo systemctl start raspberry-spy"
    exit 1
fi
sudo systemctl restart raspberry-spy.service
echo "Started. Logs: journalctl -u raspberry-spy -f"
