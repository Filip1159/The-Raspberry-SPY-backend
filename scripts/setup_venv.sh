#!/usr/bin/env bash
# Creates (or updates) the virtualenv of the backend in <checkout>/.venv and installs the requirements.
#   scripts/setup_venv.sh            # Raspberry: requirements-raspberry.txt (core + GPIO/LCD/BLE libraries)
#   scripts/setup_venv.sh --dev      # any machine: requirements-dev.txt (core + pytest + ruff), simulated hardware
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

REQUIREMENTS="requirements-raspberry.txt"
[ "${1:-}" = "--dev" ] && REQUIREMENTS="requirements-dev.txt"

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "Python 3.11 or newer is required, found: $(python3 --version)" >&2
    exit 1
fi

[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r "$REQUIREMENTS"

echo "Done: .venv ($(.venv/bin/python --version)), installed $REQUIREMENTS"
