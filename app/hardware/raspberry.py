import asyncio
import logging
from threading import Thread
from time import sleep

from bleak import BleakClient, BleakScanner
from gpiozero import PWMLED, Button, RotaryEncoder
from gpiozero import Buzzer as GpioBuzzer
from rpi_hardware_pwm import HardwarePWM
from RPLCD.i2c import CharLCD

from app.climate import ClimateReadings
from app.hardware import Hardware
from app.hardware.sysfs_led import ActLed

logger = logging.getLogger('hardware.ble')

# The delay before the next attempt after a failure (no Bluetooth adapter, device out of range, ...)
RETRY_SECONDS = 5

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


class BleClimateSensor(ClimateReadings):
    """Polls the HM-10 BLE module of the battery-powered temperature/humidity sensor"""

    def __init__(self):
        super().__init__()
        self._thread: Thread | None = None

    def start(self) -> None:
        self._thread = Thread(target=lambda: asyncio.run(self._scanner_loop()), daemon=True)
        self._thread.start()

    async def _scanner_loop(self):
        # Whatever goes wrong (adapter switched off, bluez restarting, a packet the parser dislikes), this thread must not die
        while True:
            try:
                device = await self._scan_for_device(timeout=5.0)
                if device is not None:
                    await self._connect_and_receive(device)
                    continue
            except Exception:
                logger.exception('BLE climate sensor failed, retrying in %s s', RETRY_SECONDS)
            await asyncio.sleep(RETRY_SECONDS)

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
                text = data.decode('utf-8', errors='replace')
                if self.apply_text(text):
                    response_event.set()

            await client.start_notify(CHAR_UUID, notification_handler)

            await client.write_gatt_char(CHAR_UUID, b'READ\n', response=False)

            try:
                await asyncio.wait_for(response_event.wait(), timeout=2.0)
            except TimeoutError:
                logger.warning('No (valid) response from the sensor')

            await client.stop_notify(CHAR_UUID)


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
