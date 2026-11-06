import json
from datetime import datetime, timedelta
from os import path
from threading import Event, Lock, Thread

from app.config import ALARMS_FILE
from app.melody_player import melody_player

DAY_TO_INT = {
    'monday': 0,
    'tuesday': 1,
    'wednesday': 2,
    'thursday': 3,
    'friday': 4,
    'saturday': 5,
    'sunday': 6,
}


def load_schedule() -> list[dict]:
    if not path.exists(ALARMS_FILE):
        raise FileNotFoundError("Alarms config file doesn't exist")

    with open(ALARMS_FILE) as f:
        return json.load(f)


class AlarmManager:
    def __init__(self):
        self.__waiting_thread: Thread | None = None
        self.__lock = Lock()
        self.__stop_event = Event()
        self.schedule: list[dict] = []
        self.player = melody_player
        self.reload()

    def reload(self):
        with self.__lock:
            self.__stop_current_thread()

            self.schedule = load_schedule()
            self.__stop_event.clear()

            upcoming = self.__find_next_run(self.schedule)
            if upcoming is None:
                # Nothing is switched on: no thread has to wait. The next reload (saving an alarm) starts one.
                self.__waiting_thread = None
                return

            self.__waiting_thread = Thread(target=self.__run_and_reschedule, args=upcoming, daemon=True)
            self.__waiting_thread.start()

    def save_day(self, new_alarm: dict):
        self.schedule = list(map(lambda alarm: new_alarm if alarm['day'] == new_alarm['day'] else alarm, self.schedule))
        with open(ALARMS_FILE, 'w', encoding='utf-8') as file:
            json.dump(self.schedule, file, ensure_ascii=False, indent=2)
        self.reload()

    def __find_next_run(self, schedule: list[dict]) -> tuple[datetime, dict] | None:
        """The next time an enabled alarm should ring, or None when no alarm is enabled"""
        now = datetime.now()
        candidates = []

        for entry in schedule:
            # entries without the flag (older alarms.json files) keep ringing
            if not entry.get('enabled', True):
                continue

            target_weekday = DAY_TO_INT[entry['day']]
            target_time = now.replace(
                hour=entry['hour'],
                minute=entry['minute'],
                second=0,
                microsecond=0,
            )

            days_ahead = (target_weekday - now.weekday()) % 7
            run_time = target_time + timedelta(days=days_ahead)

            if run_time <= now:
                run_time += timedelta(days=7)

            candidates.append((run_time, entry))

        return min(candidates, key=lambda t: t[0]) if candidates else None

    def __run_and_reschedule(self, run_at: datetime, alarm: dict):
        while not self.__stop_event.is_set():
            delay = (run_at - datetime.now()).total_seconds()

            if delay > 0:
                stopped = self.__stop_event.wait(timeout=delay)
                if stopped:
                    return

            self.player.play(alarm['melody'])

            with self.__lock:
                upcoming = self.__find_next_run(self.schedule)

            if upcoming is None:
                return
            run_at, alarm = upcoming

    def __stop_current_thread(self):
        if self.__waiting_thread and self.__waiting_thread.is_alive():
            self.__stop_event.set()
            self.__waiting_thread.join()


alarm_manager = AlarmManager()
