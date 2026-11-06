import random
from pathlib import Path

import psutil

THERMAL_ZONE = Path('/sys/class/thermal/thermal_zone0/temp')

_simulated_temperature = 45.0


def get_cpu_percent():
    return int(psutil.cpu_percent())


def get_cpu_temperature():
    try:
        return int(int(THERMAL_ZONE.read_text()) / 1000)
    except (OSError, ValueError):
        # No thermal sensor (not a Raspberry): simulate a plausible, slowly changing value
        global _simulated_temperature
        _simulated_temperature = min(75.0, max(35.0, _simulated_temperature + random.uniform(-1, 1)))
        return int(_simulated_temperature)


def get_ram_usage():
    return int(psutil.virtual_memory().percent)
