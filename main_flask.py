"""Fallback: the previous Flask implementation of the backend (the default is the FastAPI app in main.py).

python main_flask.py [--fake]
"""

import logging
from threading import Timer

from app.controller.socket_controller import socketio
from app.hardware import get_hardware
from app.local_interface import start_local_interface
from app.server import run_server
from app.system_stats import get_cpu_percent, get_cpu_temperature, get_ram_usage
from app.websocket_manager import websocket_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

climate_sensor = get_hardware().climate_sensor
climate_sensor.start()
websocket_manager.start()
start_local_interface()


def socket_update_loop():
    Timer(5, socket_update_loop).start()
    last_updated_formatted = climate_sensor.last_updated.strftime('%H:%M:%S') if climate_sensor.last_updated is not None else None
    socketio.emit(
        'ble_update',
        {
            'humidity': climate_sensor.humidity,
            'temperature': climate_sensor.temperature,
            'voltage': climate_sensor.voltage,
            'lastUpdated': last_updated_formatted,
        },
    )
    socketio.emit(
        'system_stats_update', {'cpuUsage': get_cpu_percent(), 'cpuTemperature': get_cpu_temperature(), 'ramUsage': get_ram_usage()}
    )


socket_update_loop()
run_server()
