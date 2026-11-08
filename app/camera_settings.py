"""Settings of the camera stream: stored in camera.json and applied to MediaMTX (path cam1, native rpiCamera source).

The settings are patched into the running MediaMTX through its API, which restarts the stream for a few seconds. They are not
written to mediamtx.yml, so after a restart of MediaMTX the values of that file apply again until `sync()` puts the saved ones back.
"""

import json
import logging
import math
import urllib.error
import urllib.request
from pathlib import Path
from threading import Lock

from app.config import CAMERA_SETTINGS_FILE, MEDIAMTX_API_URL, MEDIAMTX_CAMERA_PATH
from app.json_store import read_json, write_json

logger = logging.getLogger('camera')

RESOLUTIONS = {'1920x1080': (1920, 1080), '1280x720': (1280, 720), '854x480': (854, 480), '640x360': (640, 360)}
EXPOSURES = ('normal', 'short', 'long')
AWB_MODES = ('auto', 'incandescent', 'tungsten', 'fluorescent', 'indoor', 'daylight', 'cloudy')
# Inclusive ranges of the numeric settings (bitrate in kbit/s)
NUMBER_LIMITS = {
    'fps': (5, 30),
    'bitrate': (500, 10000),
    'brightness': (-1, 1),
    'contrast': (0, 4),
    'saturation': (0, 4),
    'sharpness': (0, 8),
}
INTEGER_SETTINGS = ('fps', 'bitrate')

# Keep in sync with the cam1 path of configs/mediamtx.yml (tests/test_camera_settings.py checks it): MediaMTX starts with those values
DEFAULTS = {
    'resolution': '1280x720',
    'fps': 30,
    'bitrate': 4000,
    'hFlip': False,
    'vFlip': False,
    'brightness': 0,
    'contrast': 1,
    'saturation': 1,
    'sharpness': 1,
    'exposure': 'normal',
    'awb': 'auto',
}

API_TIMEOUT_SECONDS = 3


def _is_number(value) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def validate_camera_settings(data) -> str | None:
    """Returns the error message for invalid settings (all of them are required, nothing else is allowed), or None when it is fine"""
    if not isinstance(data, dict):
        return 'Body must be an object'
    if set(data) != set(DEFAULTS):
        return 'Expected exactly these settings: ' + ', '.join(DEFAULTS)

    if data['resolution'] not in RESOLUTIONS:
        return f'Invalid resolution (one of {", ".join(RESOLUTIONS)})'
    for key in ('hFlip', 'vFlip'):
        if not isinstance(data[key], bool):
            return f'Invalid {key} value'
    for key, (low, high) in NUMBER_LIMITS.items():
        value = data[key]
        if not _is_number(value) or not low <= value <= high or (key in INTEGER_SETTINGS and not isinstance(value, int)):
            return f'Invalid {key} (between {low} and {high})'
    if data['exposure'] not in EXPOSURES:
        return f'Invalid exposure (one of {", ".join(EXPOSURES)})'
    if data['awb'] not in AWB_MODES:
        return f'Invalid awb (one of {", ".join(AWB_MODES)})'
    return None


def to_mediamtx(settings: dict) -> dict:
    """The path parameters of MediaMTX (rpiCamera*) for a set of settings"""
    width, height = RESOLUTIONS[settings['resolution']]
    return {
        'rpiCameraWidth': width,
        'rpiCameraHeight': height,
        'rpiCameraFPS': settings['fps'],
        # A keyframe every half second: HLS segments can only start at keyframes, so this bounds the latency of the stream
        'rpiCameraIDRPeriod': max(1, settings['fps'] // 2),
        'rpiCameraBitrate': settings['bitrate'] * 1000,
        'rpiCameraHFlip': settings['hFlip'],
        'rpiCameraVFlip': settings['vFlip'],
        'rpiCameraBrightness': settings['brightness'],
        'rpiCameraContrast': settings['contrast'],
        'rpiCameraSaturation': settings['saturation'],
        'rpiCameraSharpness': settings['sharpness'],
        'rpiCameraExposure': settings['exposure'],
        'rpiCameraAWB': settings['awb'],
    }


def _same(wanted, actual) -> bool:
    if isinstance(wanted, bool) or isinstance(actual, bool) or not isinstance(wanted, int | float):
        return wanted == actual
    return isinstance(actual, int | float) and math.isclose(wanted, actual, abs_tol=1e-6)


class CameraSettings:
    def __init__(self, file: Path = CAMERA_SETTINGS_FILE, api_url: str = MEDIAMTX_API_URL, path: str = MEDIAMTX_CAMERA_PATH):
        self.__file = file
        self.__api_url = api_url
        self.__path = path
        # Applying restarts the stream: the sync loop and a request must not do it at the same time
        self.__apply_lock = Lock()

    @property
    def manages_mediamtx(self) -> bool:
        return bool(self.__api_url)

    def get(self) -> dict:
        """The saved settings, the defaults when nothing was saved yet (or the file is not usable)"""
        try:
            stored = read_json(self.__file)
        except FileNotFoundError:
            return dict(DEFAULTS)
        except (OSError, ValueError):
            logger.warning('%s is not readable, using the default camera settings', self.__file, exc_info=True)
            return dict(DEFAULTS)

        settings = {**DEFAULTS, **stored} if isinstance(stored, dict) else None
        if validate_camera_settings(settings) is not None:
            logger.warning('%s holds invalid camera settings, using the defaults', self.__file)
            return dict(DEFAULTS)
        return settings

    def save(self, settings: dict) -> None:
        write_json(self.__file, settings)

    def apply(self, settings: dict) -> bool:
        """Patches the settings into MediaMTX. True when MediaMTX took them; without a MediaMTX to talk to there is nothing to apply"""
        if not self.manages_mediamtx:
            return True
        with self.__apply_lock:
            ok = self.__request('PATCH', f'/v3/config/paths/patch/{self.__path}', to_mediamtx(settings)) is not None
        if not ok:
            logger.warning('MediaMTX did not accept the camera settings (is it running with `api: yes`?)')
        return ok

    def is_applied(self, settings: dict) -> bool:
        if not self.manages_mediamtx:
            return True
        current = self.__current_parameters()
        return current is not None and self.__differences(settings, current) == []

    def sync(self, settings: dict | None = None) -> bool:
        """Applies the saved settings when MediaMTX runs with other values (it was restarted). Never raises; False while unreachable"""
        if not self.manages_mediamtx:
            return True
        settings = settings or self.get()
        current = self.__current_parameters()
        if current is None:
            return False
        differences = self.__differences(settings, current)
        if not differences:
            return True
        logger.info('MediaMTX runs with other camera settings (%s), applying the saved ones', ', '.join(differences))
        return self.apply(settings)

    def __differences(self, settings: dict, current: dict) -> list[str]:
        return [key for key, wanted in to_mediamtx(settings).items() if not _same(wanted, current.get(key))]

    def __current_parameters(self) -> dict | None:
        return self.__request('GET', f'/v3/config/paths/get/{self.__path}')

    def __request(self, method: str, endpoint: str, body: dict | None = None) -> dict | None:
        """The JSON answer of the MediaMTX API, or None when the call failed"""
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f'{self.__api_url}{endpoint}', data=data, method=method, headers={'Content-Type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
                content = response.read()
            return json.loads(content) if content else {}
        except (urllib.error.URLError, OSError, ValueError) as error:
            logger.debug('MediaMTX API %s %s failed: %s', method, endpoint, error)
            return None
