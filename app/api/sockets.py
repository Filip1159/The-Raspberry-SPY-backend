import asyncio
import logging
from time import time

import jwt
import socketio
from socketio.exceptions import ConnectionRefusedError

from app.allowed_origins import ALLOWED_ORIGINS
from app.api.security import decode_token
from app.hardware import get_hardware
from app.services import get_services
from app.stats_history import stats_history
from app.system_stats import get_cpu_percent, get_cpu_temperature, get_ram_usage

logger = logging.getLogger('sockets')

camera_light = get_hardware().camera_light

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins=ALLOWED_ORIGINS)

# Socket.IO session id -> expiration time (epoch seconds) of the JWT presented on connect
session_expirations: dict[str, int] = {}


@sio.event
async def connect(sid, environ, auth=None):
    token = auth.get('token') if isinstance(auth, dict) else None
    if not isinstance(token, str) or not token:
        raise ConnectionRefusedError('unauthorized')

    try:
        claims = decode_token(token)
    except jwt.PyJWTError as e:
        raise ConnectionRefusedError('unauthorized') from e

    session_expirations[sid] = claims['exp']
    await sio.send('Connected', to=sid)


@sio.event
async def disconnect(sid, *_):
    session_expirations.pop(sid, None)


@sio.on('message')
async def handle_message(sid, msg):
    if session_expirations.get(sid, 0) <= time():
        await sio.disconnect(sid)
        return

    if not isinstance(msg, str):
        return

    # The hardware calls block (PWM, GPIO): keep them off the event loop
    await asyncio.to_thread(_control_hardware, msg)


def _control_hardware(msg: str) -> None:
    try:
        if msg.startswith('LED'):
            camera_light.value = min(1.0, max(0.0, float(msg[3:]) / 255))
        else:
            get_services().servos_controller.move(msg)
    except (ValueError, KeyError):
        logger.warning('Ignoring unknown camera command %r', msg[:20])


async def broadcast_stats_forever(interval: float = 5) -> None:
    """Pushes the climate and system values to every connected (signed-in) client"""
    climate_sensor = get_hardware().climate_sensor
    while True:
        await asyncio.sleep(interval)
        last = climate_sensor.last_updated
        climate = {
            'humidity': climate_sensor.humidity,
            'temperature': climate_sensor.temperature,
            'voltage': climate_sensor.voltage,
            'lastUpdated': last.strftime('%H:%M:%S') if last is not None else None,
            'stale': climate_sensor.stale,
        }
        system = {'cpuUsage': get_cpu_percent(), 'cpuTemperature': get_cpu_temperature(), 'ramUsage': get_ram_usage()}
        stats_history.add({**system, 'humidity': climate['humidity'], 'temperature': climate['temperature'], 'timestamp': int(time())})
        await sio.emit('ble_update', climate)
        await sio.emit('system_stats_update', system)
