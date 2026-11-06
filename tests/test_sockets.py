import asyncio
import time
from unittest.mock import AsyncMock

import pytest
from socketio.exceptions import ConnectionRefusedError

from app.api import sockets
from app.hardware import get_hardware
from app.services import get_services


def make_token(expires_in: int) -> str:
    import jwt

    from app.api.security import private_pem

    now = int(time.time())
    return jwt.encode({'sub': 'demo', 'iat': now, 'exp': now + expires_in}, private_pem, algorithm='RS256')


@pytest.fixture()
def sio(monkeypatch):
    monkeypatch.setattr(sockets.sio, 'send', AsyncMock())
    monkeypatch.setattr(sockets.sio, 'disconnect', AsyncMock())
    sockets.session_expirations.clear()
    return sockets.sio


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize('auth', [None, {}, {'token': ''}, {'token': 'abc.def.ghi'}, {'token': 123}, 'token'])
def test_connection_without_a_valid_token_is_refused(sio, auth):
    with pytest.raises(ConnectionRefusedError, match='unauthorized'):
        run(sockets.connect('sid1', {}, auth))
    assert 'sid1' not in sockets.session_expirations


def test_expired_token_is_refused(sio):
    with pytest.raises(ConnectionRefusedError, match='unauthorized'):
        run(sockets.connect('sid1', {}, {'token': make_token(-10)}))


def test_valid_token_connects_and_is_forgotten_on_disconnect(sio):
    run(sockets.connect('sid1', {}, {'token': make_token(600)}))
    assert sockets.session_expirations['sid1'] > time.time()
    sio.send.assert_awaited_once()

    run(sockets.disconnect('sid1'))
    assert 'sid1' not in sockets.session_expirations


def test_signed_in_client_controls_the_camera(sio):
    run(sockets.connect('sid1', {}, {'token': make_token(600)}))

    run(sockets.handle_message('sid1', 'LED255'))
    assert get_hardware().camera_light.value == 1.0

    servos_controller = get_services().servos_controller
    before = servos_controller.vertical_servo_angle
    run(sockets.handle_message('sid1', 'DOWN'))
    assert servos_controller.vertical_servo_angle == before + 1 or servos_controller.vertical_servo_angle == 30
    run(sockets.handle_message('sid1', 'CENTER'))


def test_unknown_or_malformed_commands_are_ignored(sio):
    run(sockets.connect('sid1', {}, {'token': make_token(600)}))

    for message in ['NOPE', 'LEDabc', 'LED', 123, None, {'a': 1}]:
        run(sockets.handle_message('sid1', message))
    sio.disconnect.assert_not_awaited()


def test_led_value_is_clamped(sio):
    run(sockets.connect('sid1', {}, {'token': make_token(600)}))

    run(sockets.handle_message('sid1', 'LED9999'))
    assert get_hardware().camera_light.value == 1.0


def test_session_with_an_expired_token_is_disconnected_and_cannot_control(sio):
    run(sockets.connect('sid1', {}, {'token': make_token(600)}))
    sockets.session_expirations['sid1'] = int(time.time()) - 1
    get_hardware().camera_light.value = 0.0

    run(sockets.handle_message('sid1', 'LED255'))

    sio.disconnect.assert_awaited_once_with('sid1')
    assert get_hardware().camera_light.value == 0.0


def test_unknown_session_cannot_control(sio):
    get_hardware().camera_light.value = 0.0
    run(sockets.handle_message('ghost', 'LED255'))

    assert get_hardware().camera_light.value == 0.0
    sio.disconnect.assert_awaited_once_with('ghost')


def test_stats_are_broadcast_to_everyone(sio, monkeypatch):
    emitted = []
    monkeypatch.setattr(sockets.sio, 'emit', AsyncMock(side_effect=lambda event, data: emitted.append((event, data))))

    async def one_round():
        task = asyncio.create_task(sockets.broadcast_stats_forever(interval=0.01))
        await asyncio.sleep(0.1)
        task.cancel()

    run(one_round())

    events = {event for event, _ in emitted}
    assert events == {'ble_update', 'system_stats_update'}
    assert set(dict(emitted)['system_stats_update']) == {'cpuUsage', 'cpuTemperature', 'ramUsage'}
    assert set(dict(emitted)['ble_update']) == {'humidity', 'temperature', 'voltage', 'lastUpdated', 'stale'}


def test_every_broadcast_is_remembered_for_the_history(sio, monkeypatch):
    from app.stats_history import stats_history

    monkeypatch.setattr(sockets.sio, 'emit', AsyncMock())
    before = len(stats_history.samples())

    async def one_round():
        task = asyncio.create_task(sockets.broadcast_stats_forever(interval=0.01))
        await asyncio.sleep(0.1)
        task.cancel()

    run(one_round())

    samples = stats_history.samples()
    assert len(samples) > before or len(samples) == 120
    assert set(samples[-1]) == {'cpuUsage', 'cpuTemperature', 'ramUsage', 'humidity', 'temperature', 'timestamp'}
