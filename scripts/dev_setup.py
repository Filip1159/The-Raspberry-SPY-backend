"""Prepares the data directory for running the backend without a Raspberry: python scripts/dev_setup.py"""

import sys
from pathlib import Path


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from app.config import DATA_DIR, HARDWARE_MODE
    from app.dev_data import ensure_dev_data

    created = ensure_dev_data(DATA_DIR)
    print(f'Data directory: {DATA_DIR} (hardware mode: {HARDWARE_MODE})')
    print(f'Created: {", ".join(created)}' if created else 'Nothing to create, all files already exist')
    print("Login with username 'demo' and password 'demo' (see users.json)")


if __name__ == '__main__':
    main()
