from time import time

from flask import request
from flask_jwt_extended import decode_token
from flask_jwt_extended.exceptions import JWTExtendedException
from flask_socketio import ConnectionRefusedError, SocketIO, disconnect, send
from jwt import PyJWTError

from app.allowed_origins import ALLOWED_ORIGINS
from app.gpio.gpio import camera_light
from app.gpio.servos_controller import servos_controller

socketio = SocketIO(cors_allowed_origins=ALLOWED_ORIGINS)

# Socket.IO session id -> expiration time (epoch seconds) of the JWT presented on connect
session_expirations: dict[str, int] = {}


@socketio.on('connect')
def handle_connect(auth=None):
    token = auth.get('token') if isinstance(auth, dict) else None
    if not isinstance(token, str) or not token:
        raise ConnectionRefusedError('unauthorized')

    try:
        claims = decode_token(token)
    except (JWTExtendedException, PyJWTError) as e:
        raise ConnectionRefusedError('unauthorized') from e

    session_expirations[request.sid] = claims['exp']
    send('Connected')


@socketio.on('disconnect')
def handle_disconnect(*_):
    session_expirations.pop(request.sid, None)


@socketio.on('message')
def handle_message(msg):
    if session_expirations.get(request.sid, 0) <= time():
        disconnect()
        return

    if not isinstance(msg, str):
        return

    if msg.startswith('LED'):
        print(float(msg[3:]) / 255)
        camera_light.value = float(msg[3:]) / 255
    else:
        servos_controller.move(msg)
