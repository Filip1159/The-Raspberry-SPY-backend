"""FastAPI version of the backend (work in progress, see AGENTS.md). Flask stays the default: `python main.py`.

python main_fastapi.py [--fake]     # uvicorn on :8080 (PORT env to change)
"""

import logging

import uvicorn

from app.config import PORT

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

if __name__ == '__main__':
    # DO NOT enable reload=True: it starts the hardware twice (GPIO is exclusive, see the comment in app/server.py)
    uvicorn.run('app.api.main:asgi_app', host='0.0.0.0', port=PORT)
