import json
from datetime import datetime

import pytest

from app import alarm_manager as alarm_module
from app.alarm_manager import AlarmManager


def alarm(day: str, hour: int, minute: int, enabled: bool = True, melody: str = 'Nokia') -> dict:
    return {'day': day, 'hour': hour, 'minute': minute, 'enabled': enabled, 'melody': melody}


def freeze(monkeypatch, moment: datetime):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment

    monkeypatch.setattr(alarm_module, 'datetime', FrozenDatetime)


@pytest.fixture()
def manager(tmp_path, monkeypatch):
    """An AlarmManager working on its own (empty) schedule file"""
    schedule_file = tmp_path / 'alarms.json'
    schedule_file.write_text('[]')
    monkeypatch.setattr(alarm_module, 'ALARMS_FILE', schedule_file)
    instance = AlarmManager()
    yield instance
    instance._AlarmManager__stop_current_thread()


def next_run(manager: AlarmManager, schedule: list[dict]):
    return manager._AlarmManager__find_next_run(schedule)


# 6 November 2026 is a Friday
FRIDAY_10_00 = datetime(2026, 11, 6, 10, 0)


def test_picks_the_next_alarm_later_today(manager, monkeypatch):
    freeze(monkeypatch, FRIDAY_10_00)

    run_at, chosen = next_run(manager, [alarm('friday', 9, 0), alarm('friday', 11, 30), alarm('saturday', 7, 0)])

    assert run_at == datetime(2026, 11, 6, 11, 30)
    assert chosen['hour'] == 11


def test_an_alarm_that_already_rang_today_waits_for_next_week(manager, monkeypatch):
    freeze(monkeypatch, FRIDAY_10_00)

    run_at, _ = next_run(manager, [alarm('friday', 9, 0)])

    assert run_at == datetime(2026, 11, 13, 9, 0)


def test_an_alarm_right_now_waits_for_next_week(manager, monkeypatch):
    freeze(monkeypatch, FRIDAY_10_00)

    run_at, _ = next_run(manager, [alarm('friday', 10, 0)])

    assert run_at == datetime(2026, 11, 13, 10, 0)


def test_the_week_wraps_around(manager, monkeypatch):
    freeze(monkeypatch, datetime(2026, 11, 8, 23, 0))  # Sunday evening

    run_at, chosen = next_run(manager, [alarm('monday', 6, 15), alarm('sunday', 7, 0)])

    assert run_at == datetime(2026, 11, 9, 6, 15)
    assert chosen['day'] == 'monday'


def test_disabled_alarms_are_ignored(manager, monkeypatch):
    freeze(monkeypatch, FRIDAY_10_00)

    run_at, chosen = next_run(manager, [alarm('friday', 10, 30, enabled=False), alarm('saturday', 8, 0)])

    assert (run_at, chosen['day']) == (datetime(2026, 11, 7, 8, 0), 'saturday')


def test_alarms_without_the_enabled_flag_still_ring(manager, monkeypatch):
    freeze(monkeypatch, FRIDAY_10_00)
    legacy = {'day': 'friday', 'hour': 12, 'minute': 0, 'melody': 'Nokia'}

    run_at, _ = next_run(manager, [legacy])

    assert run_at == datetime(2026, 11, 6, 12, 0)


def test_no_next_run_when_every_alarm_is_disabled(manager, monkeypatch):
    freeze(monkeypatch, FRIDAY_10_00)

    assert next_run(manager, [alarm('friday', 11, 0, enabled=False)]) is None
    assert next_run(manager, []) is None


def test_no_thread_waits_when_every_alarm_is_disabled(manager, tmp_path):
    (tmp_path / 'alarms.json').write_text(json.dumps([alarm('friday', 11, 0, enabled=False)]))

    manager.reload()

    assert manager._AlarmManager__waiting_thread is None


def test_a_thread_waits_for_the_next_enabled_alarm(manager, tmp_path):
    (tmp_path / 'alarms.json').write_text(json.dumps([alarm('monday', 6, 0), alarm('tuesday', 6, 0, enabled=False)]))

    manager.reload()

    assert manager._AlarmManager__waiting_thread.is_alive()


def test_switching_the_last_alarm_off_stops_the_waiting_thread(manager, tmp_path):
    (tmp_path / 'alarms.json').write_text(json.dumps([alarm('monday', 6, 0)]))
    manager.reload()
    thread = manager._AlarmManager__waiting_thread
    assert thread.is_alive()

    manager.save_day(alarm('monday', 6, 0, enabled=False))

    assert not thread.is_alive()
    assert manager._AlarmManager__waiting_thread is None


def test_save_day_replaces_only_that_day_and_persists_it(manager, tmp_path):
    schedule_file = tmp_path / 'alarms.json'
    schedule_file.write_text(json.dumps([alarm('monday', 6, 0), alarm('tuesday', 7, 0)]))
    manager.reload()

    manager.save_day(alarm('tuesday', 8, 45, melody='Panic'))

    saved = json.loads(schedule_file.read_text())
    assert saved == [alarm('monday', 6, 0), alarm('tuesday', 8, 45, melody='Panic')]
    assert manager.schedule == saved


def test_reloading_while_an_alarm_is_ringing_does_not_deadlock(manager, tmp_path, monkeypatch):
    """The waiting thread needs the schedule lock right after play(); reload used to hold it while joining that thread"""
    import threading

    schedule_file = tmp_path / 'alarms.json'
    schedule_file.write_text(json.dumps([alarm('friday', 10, 0)]))
    # 0.3 s before the alarm: the thread starts ringing almost immediately
    freeze(monkeypatch, datetime(2026, 11, 6, 9, 59, 59, 700000))
    ringing, let_play_return = threading.Event(), threading.Event()

    def slow_play(_melody):
        ringing.set()
        let_play_return.wait(5)

    monkeypatch.setattr(manager.player, 'play', slow_play)
    manager.reload()
    assert ringing.wait(5)

    reloader = threading.Thread(target=manager.reload, daemon=True)
    reloader.start()
    let_play_return.set()  # play() returns; the old thread now wants the lock the reload used to hold

    reloader.join(timeout=5)
    assert not reloader.is_alive(), 'reload() is stuck'
