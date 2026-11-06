import json
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event, Lock, Thread

from app.config import ALARMS_FILE
from app.melody_player import MelodyPlayer

DAY_TO_INT = {
    'monday': 0,
    'tuesday': 1,
    'wednesday': 2,
    'thursday': 3,
    'friday': 4,
    'saturday': 5,
    'sunday': 6,
}


def load_schedule(alarms_file: Path) -> list[dict]:
    if not alarms_file.exists():
        raise FileNotFoundError("Alarms config file doesn't exist")

    with open(alarms_file) as f:
        return json.load(f)


class AlarmManager:
    def __init__(self, player: MelodyPlayer, alarms_file: Path = ALARMS_FILE):
        self.__alarms_file = alarms_file
        self.__waiting_thread: Thread | None = None
        # `__reload_lock` serializes reloads (and may be held while waiting for the old thread to finish);
        # `__lock` only guards the schedule and is never held for long, because the waiting thread needs it after every alarm.
        # Joining the old thread while holding `__lock` used to deadlock when a reload coincided with an alarm ringing.
        self.__reload_lock = Lock()
        self.__lock = Lock()
        self.__stop_event = Event()
        self.schedule: list[dict] = []
        self.player = player
        self.reload()

    def reload(self):
        with self.__reload_lock:
            self.__stop_current_thread()

            with self.__lock:
                self.schedule = load_schedule(self.__alarms_file)
                upcoming = self.__find_next_run(self.schedule)

            if upcoming is None:
                # Nothing is switched on: no thread has to wait. The next reload (saving an alarm) starts one.
                self.__waiting_thread = None
                return

            # every thread gets its own event, so a late old thread can never be revived by the next generation
            self.__stop_event = Event()
            self.__waiting_thread = Thread(target=self.__run_and_reschedule, args=(self.__stop_event, *upcoming), daemon=True)
            self.__waiting_thread.start()

    def save_day(self, new_alarm: dict):
        self.schedule = list(map(lambda alarm: new_alarm if alarm['day'] == new_alarm['day'] else alarm, self.schedule))
        with open(self.__alarms_file, 'w', encoding='utf-8') as file:
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

    def __run_and_reschedule(self, stop_event: Event, run_at: datetime, alarm: dict):
        while not stop_event.is_set():
            delay = (run_at - datetime.now()).total_seconds()

            if delay > 0:
                stopped = stop_event.wait(timeout=delay)
                if stopped:
                    return

            self.player.play(alarm['melody'])

            with self.__lock:
                if stop_event.is_set():
                    return
                upcoming = self.__find_next_run(self.schedule)

            if upcoming is None:
                return
            run_at, alarm = upcoming

    def __stop_current_thread(self):
        self.__stop_event.set()
        if self.__waiting_thread and self.__waiting_thread.is_alive():
            self.__waiting_thread.join()
