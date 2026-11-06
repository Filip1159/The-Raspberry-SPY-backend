import os
import tempfile
from pathlib import Path

import pytest

# The app reads its configuration at import time, so the test environment must be set up before importing it
os.environ['HARDWARE'] = 'fake'
DATA_DIR = Path(tempfile.mkdtemp(prefix='raspberry-spy-tests-'))
os.environ['DATA_DIR'] = str(DATA_DIR)

from app.dev_data import ensure_dev_data  # noqa: E402

ensure_dev_data(DATA_DIR)


@pytest.fixture(scope='session')
def client():
    """The FastAPI version of the API (no lifespan: hardware threads and the stats broadcast are not started)"""
    from fastapi.testclient import TestClient

    from app.api.main import fastapi_app

    return TestClient(fastapi_app)


@pytest.fixture()
def token(client):
    return client.post('/login', json={'username': 'demo', 'password': 'demo'}).json()['access_token']


@pytest.fixture()
def auth_headers(token):
    return {'Authorization': f'Bearer {token}'}
