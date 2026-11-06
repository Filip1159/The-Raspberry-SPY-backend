"""app/hardware/raspberry.py with the Raspberry-only libraries replaced by mocks (they cannot be installed anywhere else)"""

import asyncio
import importlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

PI_LIBRARIES = ['bleak', 'gpiozero', 'rpi_hardware_pwm', 'RPLCD', 'RPLCD.i2c']


@pytest.fixture()
def raspberry(monkeypatch):
    for name in PI_LIBRARIES:
        monkeypatch.setitem(sys.modules, name, MagicMock())
    monkeypatch.delitem(sys.modules, 'app.hardware.raspberry', raising=False)
    module = importlib.import_module('app.hardware.raspberry')
    yield module
    sys.modules.pop('app.hardware.raspberry', None)


def test_the_hardware_is_wired_to_the_documented_pins(raspberry):
    hardware = raspberry.create_hardware()

    raspberry.HardwarePWM.assert_any_call(pwm_channel=0, hz=50, chip=0)
    raspberry.HardwarePWM.assert_any_call(pwm_channel=1, hz=50, chip=0)
    raspberry.PWMLED.assert_called_once_with(14)
    raspberry.RotaryEncoder.assert_called_once_with(a=17, b=27, max_steps=0)
    raspberry.Button.assert_called_once_with(22, pull_up=True)
    raspberry.CharLCD.assert_called_once_with('PCF8574', 0x27, backlight_enabled=True)
    raspberry.GpioBuzzer.assert_called_once_with(15)
    assert hardware.climate_sensor.stale


def test_the_buzzer_toggles_the_pin_at_the_requested_frequency(raspberry, monkeypatch):
    sleeps = []
    monkeypatch.setattr(raspberry, 'sleep', sleeps.append)
    buzzer = raspberry.BitBangedBuzzer(15)

    buzzer.play_tone(frequency=100, duration=0.05)  # 5 waves

    pin = raspberry.GpioBuzzer.return_value
    assert pin.on.call_count == pin.off.call_count == 5
    assert sleeps == [1 / 200] * 10


def _sensor_with_device(raspberry, notifications):
    """A BleClimateSensor whose BLE client answers with the given notification payloads"""

    class Client:
        def __init__(self, _address):
            self.handler = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def start_notify(self, _uuid, handler):
            self.handler = handler

        async def write_gatt_char(self, *_args, **_kwargs):
            for payload in notifications:
                self.handler(None, bytearray(payload))

        async def stop_notify(self, _uuid):
            return None

    raspberry.BleakClient = Client
    return raspberry.BleClimateSensor()


def test_a_valid_notification_updates_the_readings(raspberry):
    sensor = _sensor_with_device(raspberry, [b'H=41.5;T=20.5;V=2.99\n'])

    asyncio.run(sensor._connect_and_receive(SimpleNamespace(address='AA:BB')))

    assert (sensor.humidity, sensor.temperature, sensor.voltage) == (41.5, 20.5, 2.99)
    assert not sensor.stale


def test_garbage_notifications_neither_raise_nor_change_the_readings(raspberry):
    sensor = _sensor_with_device(raspberry, [b'\xff\xfe\x00', b'H=4', b'OK+CONN'])

    asyncio.run(sensor._connect_and_receive(SimpleNamespace(address='AA:BB')))

    assert sensor.humidity is None
    assert sensor.stale


def test_the_scan_loop_survives_bluetooth_errors(raspberry, monkeypatch):
    sensor = raspberry.BleClimateSensor()
    attempts = []

    async def failing_scan(timeout):
        attempts.append(timeout)
        if len(attempts) == 3:
            raise asyncio.CancelledError  # ends the test; BaseException is not swallowed by the loop
        raise OSError('Bluetooth adapter is switched off')

    sensor._scan_for_device = failing_scan
    monkeypatch.setattr(raspberry, 'RETRY_SECONDS', 0)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(sensor._scanner_loop())

    assert len(attempts) == 3


def test_a_device_is_found_by_its_name(raspberry):
    sensor = raspberry.BleClimateSensor()
    other, wanted = SimpleNamespace(name='Headphones'), SimpleNamespace(name='BT05-1234')
    raspberry.BleakScanner.discover = AsyncMock(return_value=[SimpleNamespace(name=None), other, wanted])

    assert asyncio.run(sensor._scan_for_device(timeout=0.1)) is wanted
    raspberry.BleakScanner.discover = AsyncMock(return_value=[other])
    assert asyncio.run(sensor._scan_for_device(timeout=0.1)) is None
