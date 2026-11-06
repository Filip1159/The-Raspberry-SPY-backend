from collections import deque
from threading import Lock

# One sample every 5 s: 120 samples are the last 10 minutes, twice what the dashboard draws
HISTORY_LENGTH = 120


class StatsHistory:
    """The most recent stats samples, so a page reload can redraw the charts. Kept in memory only"""

    def __init__(self, length: int = HISTORY_LENGTH):
        self.__samples: deque[dict] = deque(maxlen=length)
        self.__lock = Lock()

    def add(self, sample: dict) -> None:
        with self.__lock:
            self.__samples.append(sample)

    def samples(self) -> list[dict]:
        """Oldest first"""
        with self.__lock:
            return list(self.__samples)


stats_history = StatsHistory()
