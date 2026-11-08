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
REFRESH_TOKENS_FILE = DATA_DIR / 'refresh_tokens.json'
KEY_PRIVATE_PATH = DATA_DIR / 'private_key.pem'
KEY_PUBLIC_PATH = DATA_DIR / 'public_key.pem'

PORT = int(environ.get('PORT', 8080))

# Rate limits on /login and /greetings; the switch exists for load tests and debugging, keep it on in production
RATE_LIMITS_ENABLED = environ.get('RATE_LIMITS_ENABLED', '1') != '0'

# The Arduino Uno R4 websocket manager (app/websocket_manager.py) is an unfinished experiment: off unless asked for, because
# it listens on all interfaces without any authentication
ARDUINO_WEBSOCKET_ENABLED = environ.get('ARDUINO_WEBSOCKET', '0') == '1'
ARDUINO_WEBSOCKET_PORT = int(environ.get('ARDUINO_WEBSOCKET_PORT', 8765))

# FastAPI only: the interactive API docs (/docs) are public through the tunnel, so they are off on the Raspberry by default
API_DOCS_ENABLED = environ.get('API_DOCS', '1' if HARDWARE_MODE == 'fake' else '0') == '1'

# Refresh tokens (httpOnly cookie) let the UI renew the 30 minute access token without a new login
REFRESH_TOKEN_DAYS = int(environ.get('REFRESH_TOKEN_DAYS', 7))
# The cookie is only sent over HTTPS (Cloudflare terminates TLS); plain http is for local development
COOKIE_SECURE = environ.get('COOKIE_SECURE', '0' if HARDWARE_MODE == 'fake' else '1') == '1'

# Camera stream settings chosen in the UI. They are applied to MediaMTX through its API, which listens on localhost only
# (`apiAddress` in configs/mediamtx.yml). Fake mode has no MediaMTX: the settings are only stored (set MEDIAMTX_API_URL to try it).
CAMERA_SETTINGS_FILE = DATA_DIR / 'camera.json'
MEDIAMTX_API_URL = environ.get('MEDIAMTX_API_URL', '' if HARDWARE_MODE == 'fake' else 'http://127.0.0.1:9997').rstrip('/')
MEDIAMTX_CAMERA_PATH = 'cam1'
