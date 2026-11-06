import asyncio
import logging
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.allowed_origins import ALLOWED_ORIGINS
from app.api.errors import ApiError, api_error_handler
from app.api.routers import alarms, auth, greetings, health
from app.api.sockets import broadcast_stats_forever, sio
from app.config import API_DOCS_ENABLED, USERS_FILE
from app.hardware import get_hardware
from app.local_interface import start_local_interface
from app.users import migrate_plaintext_passwords
from app.websocket_manager import websocket_manager

MAX_BODY_BYTES = 64 * 1024  # the API only receives small JSON bodies


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_hardware().climate_sensor.start()
    websocket_manager.start()
    start_local_interface()
    stats_task = asyncio.create_task(broadcast_stats_forever())
    yield
    stats_task.cancel()


class BodyLimitMiddleware:
    """Answers 413 for bodies announcing more than MAX_BODY_BYTES"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            length = dict(scope['headers']).get(b'content-length', b'0')
            if length.isdigit() and int(length) > MAX_BODY_BYTES:
                await send({'type': 'http.response.start', 'status': 413, 'headers': [(b'content-type', b'application/json')]})
                await send({'type': 'http.response.body', 'body': b'{"error":"Request body too large"}'})
                return
        await self.app(scope, receive, send)


def create_app() -> FastAPI:
    migrate_plaintext_passwords(USERS_FILE)

    api = FastAPI(
        title='The Raspberry SPY',
        lifespan=lifespan,
        docs_url='/docs' if API_DOCS_ENABLED else None,
        redoc_url=None,
        openapi_url='/openapi.json' if API_DOCS_ENABLED else None,
    )
    api.add_exception_handler(ApiError, api_error_handler)
    api.add_middleware(BodyLimitMiddleware)
    # Added last = outermost: errors (429, 401, 413) must carry the CORS headers too, otherwise the browser cannot read them
    api.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=['*'], allow_headers=['*'])
    for router in (alarms.router, auth.router, greetings.router, health.router):
        api.include_router(router)
    return api


fastapi_app = create_app()

# The ASGI application to serve: Socket.IO on /socket.io, everything else goes to FastAPI
asgi_app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)

logging.getLogger('uvicorn.error').setLevel(logging.INFO)
