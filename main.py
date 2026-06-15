from threading import Timer

from app.bluetooth_manager import ble_manager
from app.controller.socket_controller import socketio
from app.server import run_server
from app.system_stats import get_cpu_percent, get_cpu_temperature, get_ram_usage
from app.websocket_manager import websocket_manager

ble_manager.start()
websocket_manager.start()


def socket_update_loop():
    Timer(5, socket_update_loop).start()
    last_updated_formatted = ble_manager.last_updated.strftime('%H:%M:%S') if ble_manager.last_updated is not None else None
    socketio.emit(
        'ble_update',
        {
            'humidity': ble_manager.humidity,
            'temperature': ble_manager.temperature,
            'voltage': ble_manager.voltage,
            'lastUpdated': last_updated_formatted,
        },
    )
    socketio.emit(
        'system_stats_update', {'cpuUsage': get_cpu_percent(), 'cpuTemperature': get_cpu_temperature(), 'ramUsage': get_ram_usage()}
    )


socket_update_loop()
run_server()
