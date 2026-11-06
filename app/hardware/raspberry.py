import asyncio
import os
from datetime import datetime
from threading import Thread
from time import sleep

from bleak import BleakClient, BleakScanner
from gpiozero import PWMLED, Button, RotaryEncoder
from gpiozero import Buzzer as GpioBuzzer
from rpi_hardware_pwm import HardwarePWM
from RPLCD.i2c import CharLCD

from app.hardware import Hardware

LED_TRIGGER = '/sys/class/leds/ACT/trigger'
LED_BRIGHTNESS = '/sys/class/leds/ACT/brightness'

HM10_NAME = 'BT05'
CHAR_UUID = '0000ffe1-0000-1000-8000-00805f9b34fb'


class BitBangedBuzzer:
    def __init__(self, pin: int):
        self.__buzzer = GpioBuzzer(pin)

    def play_tone(self, frequency: int, duration: float) -> None:
        half_wave_time = 1 / (frequency * 2)
        waves = int(duration * frequency)
        for _ in range(waves):
            self.__buzzer.on()
            sleep(half_wave_time)
            self.__buzzer.off()
            sleep(half_wave_time)


class ActLed:
    def take_control(self) -> None:
        os.system(f'echo none | sudo tee {LED_TRIGGER} > /dev/null')

    def set(self, on: bool) -> None:
        os.system(f'echo {1 if on else 0} | sudo tee {LED_BRIGHTNESS} > /dev/null')

    def release(self) -> None:
        os.system(f'echo default-off | sudo tee {LED_TRIGGER} > /dev/null')


class BleClimateSensor:
    """Polls the HM-10 BLE module of the battery-powered temperature/humidity sensor"""

    def __init__(self):
        self.humidity: float | None = None
        self.temperature: float | None = None
        self.voltage: float | None = None
        self.last_updated: datetime | None = None
        self._thread: Thread | None = None

    def start(self) -> None:
        self._thread = Thread(target=lambda: asyncio.run(self._scanner_loop()), daemon=True)
        self._thread.start()

    async def _scanner_loop(self):
        while True:
            device = await self._scan_for_device(timeout=5.0)
            if device is None:
                continue

            try:
                await self._connect_and_receive(device)
            except Exception as e:
                print(f'[HM10] Connection error: {e}')

    async def _scan_for_device(self, timeout: float):
        devices = await BleakScanner.discover(timeout=timeout)
        for d in devices:
            if d.name and HM10_NAME in d.name:
                return d
        return None

    async def _connect_and_receive(self, device):
        async with BleakClient(device.address) as client:
            response_event = asyncio.Event()

            def notification_handler(_, data: bytearray):
                try:
                    text = data.decode('utf-8').strip()
                except UnicodeDecodeError:
                    text = repr(data)

                self.__parse_response(text)
                response_event.set()

            await client.start_notify(CHAR_UUID, notification_handler)

            await client.write_gatt_char(CHAR_UUID, b'READ\n', response=False)

            try:
                await asyncio.wait_for(response_event.wait(), timeout=2.0)
            except TimeoutError:
                print('[HM10] Error: No response')

            await client.stop_notify(CHAR_UUID)

    def __parse_response(self, data: str):
        data_split = data.split(';')  # H=xx.x;T=xx.x;V=x.xx format
        self.humidity = float(data_split[0][2:])
        self.temperature = float(data_split[1][2:])
        self.voltage = float(data_split[2][2:])
        self.last_updated = datetime.now()


def create_hardware() -> Hardware:
    return Hardware(
        vertical_servo=HardwarePWM(pwm_channel=0, hz=50, chip=0),
        horizontal_servo=HardwarePWM(pwm_channel=1, hz=50, chip=0),
        camera_light=PWMLED(14),
        lcd=CharLCD('PCF8574', 0x27, backlight_enabled=True),
        encoder=RotaryEncoder(a=17, b=27, max_steps=0),
        button=Button(22, pull_up=True),
        buzzer=BitBangedBuzzer(15),
        status_led=ActLed(),
        climate_sensor=BleClimateSensor(),
    )
