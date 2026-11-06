import logging
from pathlib import Path

logger = logging.getLogger('hardware.led')

LED_TRIGGER = Path('/sys/class/leds/ACT/trigger')
LED_BRIGHTNESS = Path('/sys/class/leds/ACT/brightness')


class ActLed:
    """The Raspberry's on-board ACT LED, driven through sysfs without sudo.

    The files are root-only by default; configs/99-act-led.rules (udev) makes them writable for the `gpio` group, which the
    service user belongs to. Without that permission the LED is simply left alone, with one warning in the log.
    """

    def __init__(self, trigger: Path = LED_TRIGGER, brightness: Path = LED_BRIGHTNESS):
        self.__trigger = trigger
        self.__brightness = brightness
        self.__usable = True

    def take_control(self) -> None:
        self.__write(self.__trigger, 'none')

    def set(self, on: bool) -> None:
        self.__write(self.__brightness, '1' if on else '0')

    def release(self) -> None:
        self.__write(self.__trigger, 'default-off')

    def __write(self, path: Path, value: str) -> None:
        if not self.__usable:
            return
        try:
            path.write_text(value)
        except OSError as e:
            self.__usable = False
            logger.warning('Cannot write to %s (%s); the ACT LED stays as it is. See configs/99-act-led.rules', path, e)
