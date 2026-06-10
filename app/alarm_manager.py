from datetime import datetime, timedelta
import json
from os import path
from threading import Event, Lock, Thread
from time import sleep
from typing import List, Dict

from app.melody_player import melody_player


ALARMS_FILE = '/home/fwisn/Documents/camera-app/resources/alarms.json'

DAY_TO_INT = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def load_schedule() -> List[Dict]:
    if not path.exists(ALARMS_FILE):
        raise FileNotFoundError("Alarms config file doesn't exist")

    with open(ALARMS_FILE, "r") as f:
        return json.load(f)


class AlarmManager:
    def __init__(self):
        self.__waiting_thread: Thread | None = None
        self.__lock = Lock()
        self.__stop_event = Event()
        self.schedule: List[Dict] = []
        self.player = melody_player
        self.reload()


    def reload(self):
        with self.__lock:
            self.__stop_current_thread()
        
            self.schedule = load_schedule()
            next_run, alarm = self.__find_next_run(self.schedule)
            self.__stop_event.clear()

            self.__waiting_thread = Thread(
                target=self.__run_and_reschedule,
                args=(next_run, alarm, ),
                daemon=True
            )
            self.__waiting_thread.start()

    
    def save_day(self, new_alarm: Dict):
        self.schedule = list(map(
            lambda alarm: new_alarm if alarm['day'] == new_alarm['day'] else alarm,
            self.schedule
        ))
        with open(ALARMS_FILE, "w", encoding="utf-8") as file:
            json.dump(self.schedule, file, ensure_ascii=False, indent=2)
        self.reload()


    def __find_next_run(self, schedule: List[Dict]) -> (datetime, Dict):
        now = datetime.now()
        candidates = []

        for entry in schedule:
            target_weekday = DAY_TO_INT[entry["day"]]
            target_time = now.replace(
                hour=entry["hour"],
                minute=entry["minute"],
                second=0,
                microsecond=0,
            )

            days_ahead = (target_weekday - now.weekday()) % 7
            run_time = target_time + timedelta(days=days_ahead)

            if run_time <= now:
                run_time += timedelta(days=7)

            candidates.append((run_time, entry))

        return min(candidates, key = lambda t: t[0])


    def __run_and_reschedule(self, run_at: datetime, alarm: Dict):
        while not self.__stop_event.is_set():
            delay = (run_at - datetime.now()).total_seconds()

            if delay > 0:
                stopped = self.__stop_event.wait(timeout=delay)
                if stopped:
                    return

            self.player.play(alarm['melody'])

            with self.__lock:
                run_at, alarm = self.__find_next_run(self.schedule)


    def __stop_current_thread(self):
        if self.__waiting_thread and self.__waiting_thread.is_alive():
            self.__stop_event.set()
            self.__waiting_thread.join()


alarm_manager = AlarmManager()
