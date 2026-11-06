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

from app.server import app  # noqa: E402


@pytest.fixture(scope='session')
def flask_app():
    return app


@pytest.fixture()
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture()
def token(client):
    response = client.post('/login', json={'username': 'demo', 'password': 'demo'})
    return response.get_json()['access_token']


@pytest.fixture()
def auth_headers(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture(scope='session')
def fastapi_client():
    """The FastAPI version of the API (no lifespan: hardware threads and the stats broadcast are not started)"""
    from fastapi.testclient import TestClient

    from app.api.main import fastapi_app

    return TestClient(fastapi_app)


@pytest.fixture()
def api_token(fastapi_client):
    return fastapi_client.post('/login', json={'username': 'demo', 'password': 'demo'}).json()['access_token']


@pytest.fixture()
def api_headers(api_token):
    return {'Authorization': f'Bearer {api_token}'}
