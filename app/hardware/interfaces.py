from collections.abc import Callable
from datetime import datetime
from typing import Protocol


class PwmChannel(Protocol):
    def start(self, duty_cycle: float) -> None: ...

    def change_duty_cycle(self, duty_cycle: float) -> None: ...


class Light(Protocol):
    value: float


class Lcd(Protocol):
    backlight_enabled: bool
    cursor_pos: tuple[int, int]

    def clear(self) -> None: ...

    def write_string(self, value: str) -> None: ...


class RotaryEncoder(Protocol):
    steps: int


class PushButton(Protocol):
    when_pressed: Callable[[], None] | None


class Buzzer(Protocol):
    def play_tone(self, frequency: int, duration: float) -> None: ...


class StatusLed(Protocol):
    """The Raspberry's on-board ACT LED, which is switched off to hide the device at night"""

    def take_control(self) -> None: ...

    def set(self, on: bool) -> None: ...

    def release(self) -> None: ...


class ClimateSensor(Protocol):
    humidity: float | None
    temperature: float | None
    voltage: float | None
    last_updated: datetime | None

    def start(self) -> None: ...
