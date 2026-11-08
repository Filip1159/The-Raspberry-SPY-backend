"""Camera stream settings: validation, storage, the MediaMTX calls and the REST endpoints"""

import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import pytest

from app.camera_settings import DEFAULTS, CameraSettings, to_mediamtx, validate_camera_settings
from app.config import BASE_DIR

PATH_CONFIG = {'name': 'cam1', 'source': 'rpiCamera', **to_mediamtx(DEFAULTS)}


class FakeMediaMtx:
    """Answers the two calls of the MediaMTX Control API that the backend uses"""

    def __init__(self, config: dict | None = None, status: int = 200):
        self.config = dict(config if config is not None else PATH_CONFIG)
        self.status = status
        self.patches: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self, body: dict):
                self.send_response(outer.status)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

            def do_GET(self):  # noqa: N802
                self._answer(outer.config)

            def do_PATCH(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                outer.patches.append(body)
                if outer.status == 200:
                    outer.config.update(body)
                self._answer({})

            def log_message(self, *_):
                pass

        self.server = HTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture()
def mediamtx():
    server = FakeMediaMtx()
    yield server
    server.close()


def camera(tmp_path: Path, api_url: str = '') -> CameraSettings:
    return CameraSettings(tmp_path / 'camera.json', api_url)


def changed(**values) -> dict:
    return {**DEFAULTS, **values}


# ---- validation ----


def test_defaults_are_valid():
    assert validate_camera_settings(DEFAULTS) is None


@pytest.mark.parametrize(
    'settings',
    [
        changed(resolution='3840x2160'),
        changed(fps=31),
        changed(fps=4),
        changed(fps=24.5),
        changed(bitrate=499),
        changed(bitrate=10001),
        changed(hFlip='yes'),
        changed(vFlip=1),
        changed(brightness=1.5),
        changed(brightness=True),
        changed(brightness=float('nan')),
        changed(contrast=-0.1),
        changed(saturation=4.1),
        changed(sharpness='high'),
        changed(exposure='custom'),
        changed(awb='custom'),
        {key: value for key, value in DEFAULTS.items() if key != 'fps'},
        {**DEFAULTS, 'runOnInit': 'rm -rf /'},
        [],
        None,
        'text',
    ],
)
def test_invalid_settings_are_rejected(settings):
    assert validate_camera_settings(settings) is not None


@pytest.mark.parametrize(
    'settings',
    [
        changed(resolution='640x360', fps=5, bitrate=500),
        changed(brightness=-1, contrast=4, saturation=0, sharpness=8),
        changed(brightness=0.25),
    ],
)
def test_boundaries_and_decimals_are_valid(settings):
    assert validate_camera_settings(settings) is None


# ---- mapping and the MediaMTX file ----


def test_mediamtx_parameters():
    parameters = to_mediamtx(changed(resolution='1920x1080', bitrate=2500, hFlip=True, awb='daylight'))

    assert parameters['rpiCameraWidth'] == 1920
    assert parameters['rpiCameraHeight'] == 1080
    assert parameters['rpiCameraBitrate'] == 2_500_000
    assert parameters['rpiCameraHFlip'] is True
    assert parameters['rpiCameraAWB'] == 'daylight'


@pytest.mark.parametrize('fps,keyframe_every', [(30, 15), (25, 12), (10, 5), (5, 2)])
def test_a_keyframe_comes_every_half_second_at_any_frame_rate(fps, keyframe_every):
    assert to_mediamtx(changed(fps=fps))['rpiCameraIDRPeriod'] == keyframe_every


def test_mediamtx_yml_starts_with_the_default_settings():
    cam1 = (BASE_DIR / 'configs' / 'mediamtx.yml').read_text().split('\n  cam1:\n')[1]
    in_file = {key: value.strip() for key, value in re.findall(r'^    (rpiCamera\w+): (.+)$', cam1, re.MULTILINE)}
    expected = {key: str(value).lower() for key, value in to_mediamtx(DEFAULTS).items()}

    assert in_file == expected
    assert re.search(r'^    source: rpiCamera$', cam1, re.MULTILINE)


def test_the_camera_runs_only_while_somebody_watches():
    config = (BASE_DIR / 'configs' / 'mediamtx.yml').read_text()
    cam1 = config.split('\n  cam1:\n')[1]

    assert re.search(r'^    sourceOnDemand: yes$', cam1, re.MULTILINE)
    # an always-running HLS muxer is a reader of the path: it would keep the camera on
    assert re.search(r'^hlsAlwaysRemux: no$', config, re.MULTILINE)


# ---- storage ----


def test_defaults_until_something_is_saved(tmp_path):
    assert camera(tmp_path).get() == DEFAULTS


def test_saved_settings_are_returned(tmp_path):
    settings = changed(fps=15, vFlip=True)
    store = camera(tmp_path)

    store.save(settings)

    assert camera(tmp_path).get() == settings


@pytest.mark.parametrize('content', ['not json', '[]', json.dumps({'fps': 500}), ''])
def test_an_unusable_file_falls_back_to_the_defaults(tmp_path, content):
    (tmp_path / 'camera.json').write_text(content)

    assert camera(tmp_path).get() == DEFAULTS


def test_settings_missing_from_an_older_file_get_their_defaults(tmp_path):
    (tmp_path / 'camera.json').write_text(json.dumps({'fps': 20}))

    assert camera(tmp_path).get() == changed(fps=20)


# ---- talking to MediaMTX ----


def test_without_mediamtx_there_is_nothing_to_apply(tmp_path):
    store = camera(tmp_path)

    assert store.apply(DEFAULTS) is True
    assert store.is_applied(changed(fps=10)) is True
    assert store.sync() is True


def test_apply_patches_the_path(tmp_path, mediamtx):
    settings = changed(resolution='640x360', fps=15)

    assert camera(tmp_path, mediamtx.url).apply(settings) is True
    assert mediamtx.patches == [to_mediamtx(settings)]


def test_apply_fails_when_mediamtx_refuses(tmp_path):
    server = FakeMediaMtx(status=500)
    try:
        assert camera(tmp_path, server.url).apply(DEFAULTS) is False
    finally:
        server.close()


def test_apply_fails_when_mediamtx_is_down(tmp_path):
    assert camera(tmp_path, 'http://127.0.0.1:1').apply(DEFAULTS) is False


def test_is_applied_compares_with_the_running_path(tmp_path, mediamtx):
    store = camera(tmp_path, mediamtx.url)

    assert store.is_applied(DEFAULTS) is True
    assert store.is_applied(changed(brightness=0.2)) is False
    assert camera(tmp_path, 'http://127.0.0.1:1').is_applied(DEFAULTS) is False


def test_sync_leaves_matching_settings_alone(tmp_path, mediamtx):
    store = camera(tmp_path, mediamtx.url)

    assert store.sync() is True
    assert mediamtx.patches == []  # a patch restarts the stream, so it must not happen without a reason


def test_sync_restores_the_saved_settings_after_a_mediamtx_restart(tmp_path, mediamtx):
    store = camera(tmp_path, mediamtx.url)
    store.save(changed(fps=15, brightness=0.3))

    assert store.sync() is True
    assert mediamtx.patches == [to_mediamtx(changed(fps=15, brightness=0.3))]
    assert store.sync() is True
    assert len(mediamtx.patches) == 1


def test_sync_reports_an_unreachable_mediamtx(tmp_path):
    assert camera(tmp_path, 'http://127.0.0.1:1').sync() is False


# ---- REST ----


@pytest.fixture()
def saved_settings():
    """The endpoints share the file of the app: put it back afterwards"""
    from app.config import CAMERA_SETTINGS_FILE

    yield
    CAMERA_SETTINGS_FILE.unlink(missing_ok=True)


def test_camera_endpoints_need_a_token(client):
    assert client.get('/camera/settings').status_code == 401
    assert client.put('/camera/settings', json=DEFAULTS).status_code == 401


def test_settings_default_view(client, auth_headers, saved_settings):
    body = client.get('/camera/settings', headers=auth_headers).json()

    assert body == {'settings': DEFAULTS, 'defaults': DEFAULTS, 'applied': True}


def test_settings_roundtrip(client, auth_headers, saved_settings):
    settings = changed(resolution='1920x1080', fps=24, bitrate=6000, hFlip=True, brightness=0.1)

    response = client.put('/camera/settings', json=settings, headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {'settings': settings, 'defaults': DEFAULTS, 'applied': True}
    assert client.get('/camera/settings', headers=auth_headers).json()['settings'] == settings


@pytest.mark.parametrize('payload', [changed(fps=99), changed(resolution='huge'), {'fps': 20}, [], 'nope'])
def test_invalid_settings_answer_400_and_are_not_saved(client, auth_headers, saved_settings, payload):
    response = client.put('/camera/settings', json=payload, headers=auth_headers)

    assert response.status_code == 400
    assert response.json()['error']
    assert client.get('/camera/settings', headers=auth_headers).json()['settings'] == DEFAULTS


def test_applied_settings_make_every_viewer_reconnect(client, auth_headers, saved_settings, monkeypatch):
    from unittest.mock import AsyncMock

    from app.api.routers import camera as camera_router

    emit = AsyncMock()
    monkeypatch.setattr(camera_router.sio, 'emit', emit)

    client.put('/camera/settings', json=changed(fps=20), headers=auth_headers)

    emit.assert_awaited_once_with('camera_stream_restart', {'reason': 'settings'})


def test_settings_that_were_not_applied_do_not_restart_the_viewers(client, auth_headers, saved_settings, monkeypatch):
    from unittest.mock import AsyncMock

    from app.api.routers import camera as camera_router
    from app.services import get_services

    emit = AsyncMock()
    monkeypatch.setattr(camera_router.sio, 'emit', emit)
    monkeypatch.setattr(get_services().camera_settings, 'apply', lambda _settings: False)

    response = client.put('/camera/settings', json=changed(fps=20), headers=auth_headers)

    assert response.json()['applied'] is False
    emit.assert_not_awaited()


def test_settings_changes_are_rate_limited(client, auth_headers, saved_settings):
    statuses = [
        client.put('/camera/settings', json=DEFAULTS, headers={**auth_headers, 'CF-Connecting-IP': '10.9.9.9'}).status_code
        for _ in range(11)
    ]

    assert statuses == [200] * 10 + [429]
