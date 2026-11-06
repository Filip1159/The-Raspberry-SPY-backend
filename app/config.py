import sys
from os import environ
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _detect_hardware_mode() -> str:
    """'raspberry' drives the real GPIO/I2C/BLE hardware, 'fake' simulates it so the app runs on any machine"""
    if '--fake' in sys.argv:
        return 'fake'

    requested = environ.get('HARDWARE', '').strip().lower()
    if requested in ('raspberry', 'fake'):
        return requested

    try:
        model = Path('/proc/device-tree/model').read_text(errors='ignore')
    except OSError:
        return 'fake'
    return 'raspberry' if 'Raspberry Pi' in model else 'fake'


HARDWARE_MODE = _detect_hardware_mode()

# Fake mode keeps its data away from the tracked files in resources/ (see scripts/dev_setup.py)
DATA_DIR = Path(environ.get('DATA_DIR') or BASE_DIR / ('.dev-data' if HARDWARE_MODE == 'fake' else 'resources'))
USERS_FILE = DATA_DIR / 'users.json'
ALARMS_FILE = DATA_DIR / 'alarms.json'
GREETINGS_FILE = DATA_DIR / 'greetings.json'
KEY_PRIVATE_PATH = DATA_DIR / 'private_key.pem'
KEY_PUBLIC_PATH = DATA_DIR / 'public_key.pem'

PORT = int(environ.get('PORT', 8080))

# Rate limits on /login and /greetings; the switch exists for load tests and debugging, keep it on in production
RATE_LIMITS_ENABLED = environ.get('RATE_LIMITS_ENABLED', '1') != '0'

# FastAPI only: the interactive API docs (/docs) are public through the tunnel, so they are off on the Raspberry by default
API_DOCS_ENABLED = environ.get('API_DOCS', '1' if HARDWARE_MODE == 'fake' else '0') == '1'
