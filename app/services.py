from dataclasses import dataclass
from functools import cache

from app.alarm_manager import AlarmManager
from app.gpio.servos_controller import ServosController
from app.hardware import get_hardware
from app.melody_player import MelodyPlayer


@dataclass
class Services:
    melody_player: MelodyPlayer
    alarm_manager: AlarmManager
    servos_controller: ServosController


@cache
def get_services() -> Services:
    """The long-lived objects that drive the hardware, created on first use (the app's lifespan does it at startup)
    instead of as a side effect of importing a module. Tests build their own instances of the classes."""
    hardware = get_hardware()
    melody_player = MelodyPlayer(hardware.buzzer)
    return Services(
        melody_player=melody_player,
        alarm_manager=AlarmManager(melody_player),
        servos_controller=ServosController(hardware.vertical_servo, hardware.horizontal_servo),
    )
