#!/usr/bin/env bash
# Updates the backend on the Raspberry: git pull, install changed dependencies, restart the service, check /health.
#   scripts/deploy.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
PYTHON="python3"
[ -x bin/python ] && PYTHON="bin/python"
[ -x .venv/bin/python ] && PYTHON=".venv/bin/python"

before="$(git rev-parse HEAD)"
git pull --ff-only
after="$(git rev-parse HEAD)"

if [ "$before" != "$after" ] && ! git diff --quiet "$before" "$after" -- requirements.txt requirements-raspberry.txt; then
    echo "Dependencies changed, installing..."
    "$PYTHON" -m pip install -r requirements-raspberry.txt
fi

if [ "$before" != "$after" ] && ! git diff --quiet "$before" "$after" -- configs/default; then
    echo "NOTE: configs/default (nginx) changed. Apply it: sudo cp configs/default /etc/nginx/sites-available/default && sudo nginx -t && sudo systemctl reload nginx"
fi

sudo systemctl restart raspberry-spy.service

for _ in $(seq 1 20); do
    if curl -fsS http://localhost:8080/health > /dev/null 2>&1; then
        echo "Deployed $(git rev-parse --short HEAD): the backend is healthy."
        exit 0
    fi
    sleep 1
done
echo "The backend did not answer /health within 20 s. Check: journalctl -u raspberry-spy -n 50" >&2
exit 1
