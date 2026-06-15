import asyncio
from datetime import datetime
from threading import Event, Thread

from bleak import BleakClient, BleakScanner

HM10_NAME = 'BT05'
CHAR_UUID = '0000ffe1-0000-1000-8000-00805f9b34fb'


class BluetoothManager:
    def __init__(self, stop_event: Event):
        self.stop_event = stop_event
        self.humidity = None
        self.temperature = None
        self.voltage = None
        self.last_updated = None
        self._thread = None

    def start(self):
        self._thread = Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()

    def _run_event_loop(self):
        asyncio.run(self._scanner_loop())

    async def _scanner_loop(self):
        while not self.stop_event.is_set():
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


stop_event = Event()
ble_manager = BluetoothManager(stop_event)
