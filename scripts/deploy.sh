#!/usr/bin/env bash
# Updates the backend on the Raspberry: git pull, install changed dependencies, apply changed nginx/MediaMTX configs,
# restart the service, check /health. Also run by the `deploy` job of .github/workflows/ci.yml (self-hosted runner).
#   scripts/deploy.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
PYTHON="python3"
[ -x .venv/bin/python ] && PYTHON=".venv/bin/python"

before="$(git rev-parse HEAD)"
git pull --ff-only
after="$(git rev-parse HEAD)"

if [ "$before" != "$after" ] && ! git diff --quiet "$before" "$after" -- requirements.txt requirements-raspberry.txt; then
    echo "Dependencies changed, installing..."
    "$PYTHON" -m pip install -r requirements-raspberry.txt
fi

if [ "$before" != "$after" ] && ! git diff --quiet "$before" "$after" -- configs/default; then
    echo "configs/default (nginx) changed, applying..."
    NGINX_SITE=/etc/nginx/sites-available/default
    sudo cp "$NGINX_SITE" "$NGINX_SITE.bak"
    sudo cp configs/default "$NGINX_SITE"
    if sudo nginx -t; then
        sudo systemctl reload nginx
    else
        echo "nginx rejected the new config, restoring the previous one." >&2
        sudo cp "$NGINX_SITE.bak" "$NGINX_SITE"
        exit 1
    fi
fi

if [ "$before" != "$after" ] && ! git diff --quiet "$before" "$after" -- configs/mediamtx.yml; then
    echo "configs/mediamtx.yml changed, applying (the stream restarts)..."
    sudo cp configs/mediamtx.yml /mediamtx/mediamtx.yml
    sudo systemctl restart mediamtx.service
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
