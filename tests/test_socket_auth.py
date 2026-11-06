import time

import jwt
import pytest

from app.config import KEY_PRIVATE_PATH
from app.controller.socket_controller import session_expirations, socketio
from app.gpio.servos_controller import servos_controller
from app.hardware import get_hardware


@pytest.fixture()
def connect(flask_app):
    def _connect(auth):
        return socketio.test_client(flask_app, auth=auth)

    return _connect


def make_token(expires_in: int, key: bytes | None = None) -> str:
    now = int(time.time())
    claims = {'sub': 'demo', 'iat': now, 'exp': now + expires_in}
    return jwt.encode(claims, key or KEY_PRIVATE_PATH.read_bytes(), algorithm='RS256')


@pytest.mark.parametrize('auth', [None, {}, {'token': ''}, {'token': 'abc.def.ghi'}, {'token': 123}])
def test_connection_without_a_valid_token_is_refused(connect, auth):
    assert not connect(auth).is_connected()


def test_expired_token_is_refused(connect):
    assert not connect({'token': make_token(-10)}).is_connected()


def test_token_signed_with_another_key_is_refused(connect):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )

    assert not connect({'token': make_token(600, other_key)}).is_connected()


def test_valid_token_can_control_the_camera(connect, token):
    client = connect({'token': token})
    assert client.is_connected()

    client.emit('message', 'LED255')
    assert get_hardware().camera_light.value == 1.0

    angle_before = servos_controller.vertical_servo_angle
    client.emit('message', 'DOWN')
    assert servos_controller.vertical_servo_angle == angle_before + 1
    client.emit('message', 'CENTER')
    assert servos_controller.vertical_servo_angle == 0


def test_messages_from_an_expired_session_are_dropped(connect, token):
    client = connect({'token': token})
    for sid in session_expirations:
        session_expirations[sid] = int(time.time()) - 1

    client.emit('message', 'LED0')

    assert not client.is_connected()
    assert get_hardware().camera_light.value == 1.0  # LED0 was not applied
