from flask_socketio import SocketIO, send

from app.allowed_origins import ALLOWED_ORIGINS
from app.gpio.gpio import camera_light
from app.gpio.servos_controller import servos_controller

socketio = SocketIO(cors_allowed_origins=ALLOWED_ORIGINS)


@socketio.on('connect')
def handle_connect():
    send('Connected')


@socketio.on('message')
def handle_message(msg):
    if msg.startswith('LED'):
        print(float(msg[3:]) / 255)
        camera_light.value = float(msg[3:]) / 255
    else:
        servos_controller.move(msg)
