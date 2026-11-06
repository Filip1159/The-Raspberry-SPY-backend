import logging
from datetime import datetime
from os import environ

logger = logging.getLogger('climate')

# A reading older than this is "stale": the battery-powered sensor is silent (out of range, empty battery)
STALE_AFTER_SECONDS = int(environ.get('CLIMATE_STALE_SECONDS', 300))

# Plausible values of the DHT22 and the battery; anything else is a corrupted packet
_LIMITS = {'H': (0.0, 100.0), 'T': (-40.0, 80.0), 'V': (0.0, 6.0)}


def parse_reading(text: str) -> tuple[float, float, float] | None:
    """Parses what the sensor sends, 'H=45.2;T=22.1;V=3.00' -> (humidity, temperature, voltage).
    BLE packets arrive truncated or garbled now and then: returns None instead of raising."""
    try:
        values = {}
        for part in text.strip().split(';'):
            key, _, number = part.partition('=')
            low, high = _LIMITS[key]
            value = float(number)
            if not low <= value <= high:
                return None
            values[key] = value
        return values['H'], values['T'], values['V']
    except (KeyError, ValueError):
        return None


class ClimateReadings:
    """The latest values of the climate sensor, shared by the real (BLE) and the simulated sensor"""

    def __init__(self):
        self.humidity: float | None = None
        self.temperature: float | None = None
        self.voltage: float | None = None
        self.last_updated: datetime | None = None

    def apply_text(self, text: str) -> bool:
        """Stores a reading received as text; a bad packet is logged and the previous values are kept"""
        reading = parse_reading(text)
        if reading is None:
            logger.warning('Ignoring a malformed climate reading: %r', text[:40])
            return False
        self.humidity, self.temperature, self.voltage = reading
        self.last_updated = datetime.now()
        return True

    @property
    def stale(self) -> bool:
        """True when there is no reading yet or the last one is older than STALE_AFTER_SECONDS"""
        if self.last_updated is None:
            return True
        return (datetime.now() - self.last_updated).total_seconds() > STALE_AFTER_SECONDS
