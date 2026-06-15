import asyncio
from threading import Thread

import websockets


class WebsocketManager:
    connected_device = None

    def start(self):
        self._thread = Thread(target=self.run_websocket_thread, daemon=True)
        self._thread.start()

    def run_websocket_thread(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.connect())
        except Exception as e:
            print(e)

    async def connect(self):
        async with websockets.serve(self.listen, '0.0.0.0', 8765):
            await asyncio.Future()

    async def send(self):
        message = 'TOGGLE_LED'
        self.connected_device.send(message)

    async def listen(self, websocket):
        print(f'Arduino połączone: {websocket.remote_address}')

        self.connected_device = websocket

        try:
            async for message in websocket:
                print(f'Otrzymano od Arduino: {message}')
                # Tutaj standardowa obsługa wiadomości przychodzących (jeśli potrzebna)

        except websockets.ConnectionClosed:
            print(f'Arduino rozłączone: {websocket.remote_address}')
        finally:
            # Pamiętamy o usunięciu połączenia, gdy Arduino się rozłączy!
            self.connected_device = None


websocket_manager = WebsocketManager()
