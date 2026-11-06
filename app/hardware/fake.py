import logging
import random
from collections.abc import Callable
from datetime import datetime
from threading import Event, Thread
from time import sleep

from app.hardware import Hardware

logger = logging.getLogger('hardware.fake')

LCD_ROWS = 4
LCD_COLUMNS = 20


class FakePwmChannel:
    def __init__(self, name: str):
        self.name = name
        self.duty_cycle: float | None = None

    def start(self, duty_cycle: float) -> None:
        self.duty_cycle = duty_cycle

    def change_duty_cycle(self, duty_cycle: float) -> None:
        self.duty_cycle = duty_cycle
        logger.debug('%s servo duty cycle -> %.2f', self.name, duty_cycle)


class FakeLight:
    def __init__(self):
        self._value = 0.0

    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, value: float) -> None:
        self._value = value
        logger.info('Camera light -> %.0f%%', value * 100)


class FakeLcd:
    """Keeps what would be on the 4x20 display; `lines()` returns it for debugging and tests"""

    def __init__(self):
        self.backlight_enabled = True
        self.cursor_pos = (0, 0)
        self._rows = [' ' * LCD_COLUMNS for _ in range(LCD_ROWS)]

    def clear(self) -> None:
        self._rows = [' ' * LCD_COLUMNS for _ in range(LCD_ROWS)]
        self.cursor_pos = (0, 0)

    def write_string(self, value: str) -> None:
        row, column = self.cursor_pos
        if row >= LCD_ROWS:
            return
        current = self._rows[row]
        self._rows[row] = (current[:column] + value + current[column + len(value) :])[:LCD_COLUMNS]
        self.cursor_pos = (row, min(column + len(value), LCD_COLUMNS))

    def lines(self) -> list[str]:
        return list(self._rows)


class FakeRotaryEncoder:
    def __init__(self):
        self.steps = 0


class FakePushButton:
    def __init__(self):
        self.when_pressed: Callable[[], None] | None = None

    def press(self) -> None:
        if self.when_pressed:
            self.when_pressed()


class FakeBuzzer:
    def play_tone(self, frequency: int, duration: float) -> None:
        sleep(duration)


class FakeStatusLed:
    def take_control(self) -> None:
        logger.debug('ACT LED: taking control')

    def set(self, on: bool) -> None:
        logger.debug('ACT LED -> %s', 'on' if on else 'off')

    def release(self) -> None:
        logger.debug('ACT LED: released')


class FakeClimateSensor:
    """Produces plausible readings (small random walk) every few seconds so the UI has moving data"""

    def __init__(self, interval_seconds: float = 5.0):
        self.humidity: float | None = None
        self.temperature: float | None = None
        self.voltage: float | None = None
        self.last_updated: datetime | None = None
        self._interval = interval_seconds
        self._stop = Event()

    def start(self) -> None:
        self._update()
        Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self._update()

    def _update(self) -> None:
        self.humidity = round(min(80.0, max(20.0, (self.humidity or 45.0) + random.uniform(-0.5, 0.5))), 1)
        self.temperature = round(min(30.0, max(15.0, (self.temperature or 22.0) + random.uniform(-0.2, 0.2))), 1)
        self.voltage = round(max(2.2, (self.voltage or 3.0) - random.uniform(0, 0.001)), 2)
        self.last_updated = datetime.now()


def create_hardware() -> Hardware:
    logger.info('Running with simulated hardware (no Raspberry GPIO/I2C/BLE)')
    return Hardware(
        vertical_servo=FakePwmChannel('vertical'),
        horizontal_servo=FakePwmChannel('horizontal'),
        camera_light=FakeLight(),
        lcd=FakeLcd(),
        encoder=FakeRotaryEncoder(),
        button=FakePushButton(),
        buzzer=FakeBuzzer(),
        status_led=FakeStatusLed(),
        climate_sensor=FakeClimateSensor(),
    )
