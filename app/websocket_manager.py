import asyncio
import logging
from threading import Thread

import websockets

from app.config import ARDUINO_WEBSOCKET_ENABLED, ARDUINO_WEBSOCKET_PORT

logger = logging.getLogger('arduino')


class WebsocketManager:
    """Accepts the websocket of an Arduino Uno R4 on the local network. Experimental and disabled unless ARDUINO_WEBSOCKET=1"""

    def __init__(self, enabled: bool = ARDUINO_WEBSOCKET_ENABLED, port: int = ARDUINO_WEBSOCKET_PORT):
        self.enabled = enabled
        self.port = port
        self.connected_device = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self):
        if not self.enabled:
            return
        self._thread = Thread(target=self.run_websocket_thread, daemon=True)
        self._thread.start()

    def run_websocket_thread(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self.connect())
        except Exception:
            logger.exception('The Arduino websocket server stopped')

    async def connect(self):
        async with websockets.serve(self.listen, '0.0.0.0', self.port):
            logger.info('Waiting for the Arduino on port %s', self.port)
            await asyncio.Future()

    async def send(self, message: str) -> bool:
        """Sends a text to the connected Arduino; False when none is connected"""
        device = self.connected_device
        if device is None:
            return False
        await device.send(message)
        return True

    def send_threadsafe(self, message: str) -> bool:
        """For callers outside the manager's event loop (request handlers, the LCD thread)"""
        if self._loop is None or self.connected_device is None:
            return False
        asyncio.run_coroutine_threadsafe(self.send(message), self._loop)
        return True

    async def listen(self, websocket):
        logger.info('Arduino connected: %s', websocket.remote_address)
        self.connected_device = websocket

        try:
            async for message in websocket:
                logger.info('Received from the Arduino: %s', message)
        except websockets.ConnectionClosed:
            logger.info('Arduino disconnected: %s', websocket.remote_address)
        finally:
            self.connected_device = None


websocket_manager = WebsocketManager()
