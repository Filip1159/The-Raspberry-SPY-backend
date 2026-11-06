"""The FastAPI version must answer exactly like the Flask one (tests/test_api.py and tests/test_security.py)"""

import itertools

import pytest

from app.api.routers import greetings as greetings_router
from app.config import GREETINGS_FILE
from app.json_store import read_json, write_json
from app.validation import MAX_GREETING_LENGTH

ORIGIN = {'Origin': 'https://filipwisniewski.pl'}
_ips = itertools.count(1)


def from_ip(ip: str, **headers):
    return {'CF-Connecting-IP': ip, **headers}


def test_health(fastapi_client):
    response = fastapi_client.get('/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_login_returns_a_token(fastapi_client):
    body = fastapi_client.post('/login', json={'username': 'demo', 'password': 'demo'}).json()

    assert body['access_token']
    assert body['expires_at']


@pytest.mark.parametrize(
    'payload', [{'username': 'demo', 'password': 'wrong'}, {'username': 'nobody', 'password': 'x'}, {}, [], 'text', None]
)
def test_login_rejects_bad_credentials(fastapi_client, payload):
    response = fastapi_client.post('/login', json=payload, headers=from_ip(f'10.1.0.{next(_ips)}'))

    assert response.status_code == 401
    assert response.json() == {'msg': 'bad credentials'}


def test_login_with_a_body_that_is_not_json(fastapi_client):
    response = fastapi_client.post('/login', content='nope', headers=from_ip('10.1.1.1', **{'Content-Type': 'text/plain'}))

    assert response.status_code == 401


def test_jwks_is_published(fastapi_client):
    keys = fastapi_client.get('/.well-known/jwks.json').json()['keys']

    assert len(keys) == 1
    assert keys[0]['kty'] == 'RSA'
    assert 'd' not in keys[0]


def test_token_matches_what_mediamtx_expects(fastapi_client, api_token):
    import jwt

    header = jwt.get_unverified_header(api_token)
    claims = jwt.decode(api_token, options={'verify_signature': False})

    assert header['alg'] == 'RS256'
    assert header['kid'] == fastapi_client.get('/.well-known/jwks.json').json()['keys'][0]['kid']
    assert {'action': 'read', 'path': 'cam1'} in claims['mediamtx_permissions']
    assert claims['exp'] - claims['iat'] == 30 * 60


# ---- authentication of the protected endpoints ----


@pytest.mark.parametrize('method,path', [('get', '/alarms'), ('post', '/alarms'), ('post', '/alarms/play'), ('get', '/greetings')])
def test_protected_endpoints_need_a_token(fastapi_client, method, path):
    assert getattr(fastapi_client, method)(path).status_code == 401


def test_garbage_and_foreign_tokens_are_refused(fastapi_client):
    import time

    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    now = int(time.time())
    foreign = jwt.encode({'sub': 'demo', 'exp': now + 600}, other_key, algorithm='RS256')
    unsigned = jwt.encode({'sub': 'demo', 'exp': now + 600}, None, algorithm='none')

    for token in ['abc', 'a.b.c', foreign, unsigned]:
        assert fastapi_client.get('/alarms', headers={'Authorization': f'Bearer {token}'}).status_code == 401, token
    assert fastapi_client.get('/alarms', headers={'Authorization': 'Basic abc'}).status_code == 401


def test_expired_token_is_refused(fastapi_client):
    import time

    import jwt

    from app.api.security import private_pem

    expired = jwt.encode({'sub': 'demo', 'exp': int(time.time()) - 10}, private_pem, algorithm='RS256')
    response = fastapi_client.get('/alarms', headers={'Authorization': f'Bearer {expired}'})

    assert response.status_code == 401
    assert response.json() == {'msg': 'Token has expired'}


# ---- alarms ----


def test_alarms_roundtrip(fastapi_client, api_headers):
    alarms = [{'day': 'monday', 'hour': 6, 'minute': 30, 'melody': 'Nokia', 'enabled': True}]

    response = fastapi_client.post('/alarms', json=alarms, headers=api_headers)
    assert response.status_code == 201
    assert response.content == b''
    assert fastapi_client.get('/alarms', headers=api_headers).json() == alarms


INVALID_ALARMS = [
    {'not': 'a list'},
    [1],
    [{'day': 'funday', 'hour': 6, 'minute': 0, 'melody': 'Nokia', 'enabled': True}],
    [{'day': 'monday', 'hour': 24, 'minute': 0, 'melody': 'Nokia', 'enabled': True}],
    [{'day': 'monday', 'hour': True, 'minute': 0, 'melody': 'Nokia', 'enabled': True}],
    [{'day': 'monday', 'hour': 6, 'minute': 60, 'melody': 'Nokia', 'enabled': True}],
    [{'day': 'monday', 'hour': 6, 'minute': 0, 'melody': 'Nope', 'enabled': True}],
    [{'day': 'monday', 'hour': 6, 'minute': 0, 'melody': 'Nokia', 'enabled': 'yes'}],
]


@pytest.mark.parametrize('payload', INVALID_ALARMS)
def test_invalid_alarms_are_rejected(fastapi_client, api_headers, payload):
    response = fastapi_client.post('/alarms', json=payload, headers=api_headers)

    assert response.status_code == 400
    assert 'error' in response.json()


def test_saving_alarms_reloads_the_scheduler(fastapi_client, api_headers, monkeypatch):
    from app.alarm_manager import alarm_manager

    reloads = []
    monkeypatch.setattr(alarm_manager, 'reload', lambda: reloads.append(1))
    fastapi_client.post('/alarms', json=[], headers=api_headers)

    assert reloads == [1]


def test_play_validates_the_melody(fastapi_client, api_headers, monkeypatch):
    from app.alarm_manager import alarm_manager

    played = []
    monkeypatch.setattr(alarm_manager.player, 'play', played.append)

    assert fastapi_client.post('/alarms/play', json={'melody': 'Nokia'}, headers=api_headers).status_code == 204
    assert played == ['Nokia']
    for payload in [{'melody': 'Nope'}, {'melody': 5}, {}, []]:
        assert fastapi_client.post('/alarms/play', json=payload, headers=api_headers).status_code == 400


# ---- greetings ----


def test_greetings_roundtrip(fastapi_client, api_headers):
    write_json(GREETINGS_FILE, [])
    response = fastapi_client.post('/greetings', json={'text': '  Hello from FastAPI  '}, headers=from_ip('10.1.2.1'))

    assert response.status_code == 201
    stored = fastapi_client.get('/greetings', headers=api_headers).json()
    assert [g['text'] for g in stored] == ['Hello from FastAPI']
    assert stored[0]['timestamp']


INVALID_GREETINGS = [
    {'text': ''},
    {'text': '   '},
    {'text': 123},
    {'nope': 'x'},
    ['text'],
    'text',
    None,
    {'text': 'x' * (MAX_GREETING_LENGTH + 1)},
]


@pytest.mark.parametrize('index', range(len(INVALID_GREETINGS)))
def test_invalid_greetings_are_rejected(fastapi_client, index):
    response = fastapi_client.post('/greetings', json=INVALID_GREETINGS[index], headers=from_ip(f'10.1.3.{index}'))

    assert response.status_code == 400
    assert 'error' in response.json()


def test_greetings_are_capped(fastapi_client, api_headers, monkeypatch):
    monkeypatch.setattr(greetings_router, 'MAX_STORED_GREETINGS', 2)
    write_json(GREETINGS_FILE, [])
    for index in range(3):
        assert fastapi_client.post('/greetings', json={'text': f'm{index}'}, headers=from_ip(f'10.1.4.{index}')).status_code == 201

    assert [g['text'] for g in read_json(GREETINGS_FILE)] == ['m1', 'm2']


# ---- rate limits, CORS, body size ----


def test_failed_logins_are_rate_limited(fastapi_client):
    attempt = lambda ip: fastapi_client.post('/login', json={'username': 'demo', 'password': 'wrong'}, headers=from_ip(ip, **ORIGIN))  # noqa: E731

    assert [attempt('10.1.5.1').status_code for _ in range(5)] == [401] * 5
    blocked = attempt('10.1.5.1')

    assert blocked.status_code == 429
    assert blocked.json() == {'error': 'Too many requests, please try again later'}
    assert int(blocked.headers['Retry-After']) >= 1
    # the browser must be able to read the error, otherwise the UI would treat it as "the Raspberry is offline"
    assert blocked.headers['Access-Control-Allow-Origin'] == 'https://filipwisniewski.pl'
    assert attempt('10.1.5.2').status_code == 401


def test_successful_logins_do_not_count(fastapi_client):
    login = lambda: fastapi_client.post('/login', json={'username': 'demo', 'password': 'demo'}, headers=from_ip('10.1.6.1'))  # noqa: E731

    assert [login().status_code for _ in range(10)] == [200] * 10


def test_greetings_are_rate_limited(fastapi_client):
    send = lambda: fastapi_client.post('/greetings', json={'text': 'spam'}, headers=from_ip('10.1.7.1'))  # noqa: E731

    assert [send().status_code for _ in range(3)] == [201] * 3
    assert send().status_code == 429


def test_cors_preflight_and_origins(fastapi_client):
    preflight = fastapi_client.options(
        '/alarms',
        headers={**ORIGIN, 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'authorization,content-type'},
    )
    assert preflight.status_code == 200
    assert preflight.headers['Access-Control-Allow-Origin'] == 'https://filipwisniewski.pl'
    assert 'authorization' in preflight.headers['Access-Control-Allow-Headers'].lower()

    foreign = fastapi_client.get('/health', headers={'Origin': 'https://evil.example'})
    assert 'Access-Control-Allow-Origin' not in foreign.headers


def test_huge_bodies_are_refused(fastapi_client):
    response = fastapi_client.post(
        '/greetings', content=b'x' * (70 * 1024), headers=from_ip('10.1.8.1', **{'Content-Type': 'application/json'})
    )

    assert response.status_code == 413
