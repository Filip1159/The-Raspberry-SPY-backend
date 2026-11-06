from dataclasses import dataclass
from functools import cache

from app.config import HARDWARE_MODE
from app.hardware.interfaces import Buzzer, ClimateSensor, Lcd, Light, PushButton, PwmChannel, RotaryEncoder, StatusLed


@dataclass
class Hardware:
    vertical_servo: PwmChannel
    horizontal_servo: PwmChannel
    camera_light: Light
    lcd: Lcd
    encoder: RotaryEncoder
    button: PushButton
    buzzer: Buzzer
    status_led: StatusLed
    climate_sensor: ClimateSensor


@cache
def get_hardware() -> Hardware:
    """Single place that decides between the real Raspberry hardware and the simulated one.

    The Raspberry-only libraries (gpiozero, RPLCD, bleak, ...) are imported only in 'raspberry' mode.
    """
    if HARDWARE_MODE == 'raspberry':
        from app.hardware.raspberry import create_hardware
    else:
        from app.hardware.fake import create_hardware

    return create_hardware()
