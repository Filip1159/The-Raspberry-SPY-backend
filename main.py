"""The backend: FastAPI + Socket.IO served by uvicorn.

python main.py [--fake]     # :8080 (PORT env to change); --fake simulates the hardware (any machine)

The previous Flask implementation is kept for a while as a fallback: `python main_flask.py`.
"""

import logging

import uvicorn

from app.config import PORT

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

if __name__ == '__main__':
    # DO NOT enable reload=True: it starts the hardware twice (GPIO is exclusive, see the comment in app/server.py)
    uvicorn.run('app.api.main:asgi_app', host='0.0.0.0', port=PORT)
