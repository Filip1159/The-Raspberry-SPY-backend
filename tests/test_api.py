"""The REST API: authentication, validation, rate limits, CORS"""

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


def test_health(client):
    response = client.get('/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_login_returns_a_token(client):
    body = client.post('/login', json={'username': 'demo', 'password': 'demo'}).json()

    assert body['access_token']
    assert body['expires_at']


@pytest.mark.parametrize(
    'payload', [{'username': 'demo', 'password': 'wrong'}, {'username': 'nobody', 'password': 'x'}, {}, [], 'text', None]
)
def test_login_rejects_bad_credentials(client, payload):
    response = client.post('/login', json=payload, headers=from_ip(f'10.1.0.{next(_ips)}'))

    assert response.status_code == 401
    assert response.json() == {'msg': 'bad credentials'}


def test_login_with_a_body_that_is_not_json(client):
    response = client.post('/login', content='nope', headers=from_ip('10.1.1.1', **{'Content-Type': 'text/plain'}))

    assert response.status_code == 401


def test_jwks_is_published(client):
    keys = client.get('/.well-known/jwks.json').json()['keys']

    assert len(keys) == 1
    assert keys[0]['kty'] == 'RSA'
    assert 'd' not in keys[0]


def test_token_matches_what_mediamtx_expects(client, token):
    import jwt

    header = jwt.get_unverified_header(token)
    claims = jwt.decode(token, options={'verify_signature': False})

    assert header['alg'] == 'RS256'
    assert header['kid'] == client.get('/.well-known/jwks.json').json()['keys'][0]['kid']
    assert {'action': 'read', 'path': 'cam1'} in claims['mediamtx_permissions']
    assert claims['exp'] - claims['iat'] == 30 * 60


# ---- authentication of the protected endpoints ----


@pytest.mark.parametrize('method,path', [('get', '/alarms'), ('post', '/alarms'), ('post', '/alarms/play'), ('get', '/greetings')])
def test_protected_endpoints_need_a_token(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_garbage_and_foreign_tokens_are_refused(client):
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
        assert client.get('/alarms', headers={'Authorization': f'Bearer {token}'}).status_code == 401, token
    assert client.get('/alarms', headers={'Authorization': 'Basic abc'}).status_code == 401


def test_expired_token_is_refused(client):
    import time

    import jwt

    from app.api.security import private_pem

    expired = jwt.encode({'sub': 'demo', 'exp': int(time.time()) - 10}, private_pem, algorithm='RS256')
    response = client.get('/alarms', headers={'Authorization': f'Bearer {expired}'})

    assert response.status_code == 401
    assert response.json() == {'msg': 'Token has expired'}


# ---- alarms ----


def test_alarms_roundtrip(client, auth_headers):
    alarms = [{'day': 'monday', 'hour': 6, 'minute': 30, 'melody': 'Nokia', 'enabled': True}]

    response = client.post('/alarms', json=alarms, headers=auth_headers)
    assert response.status_code == 201
    assert response.content == b''
    assert client.get('/alarms', headers=auth_headers).json() == alarms


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
def test_invalid_alarms_are_rejected(client, auth_headers, payload):
    response = client.post('/alarms', json=payload, headers=auth_headers)

    assert response.status_code == 400
    assert 'error' in response.json()


def test_saving_alarms_reloads_the_scheduler(client, auth_headers, monkeypatch):
    from app.alarm_manager import alarm_manager

    reloads = []
    monkeypatch.setattr(alarm_manager, 'reload', lambda: reloads.append(1))
    client.post('/alarms', json=[], headers=auth_headers)

    assert reloads == [1]


def test_play_validates_the_melody(client, auth_headers, monkeypatch):
    from app.alarm_manager import alarm_manager

    played = []
    monkeypatch.setattr(alarm_manager.player, 'play', played.append)

    assert client.post('/alarms/play', json={'melody': 'Nokia'}, headers=auth_headers).status_code == 204
    assert played == ['Nokia']
    for payload in [{'melody': 'Nope'}, {'melody': 5}, {}, []]:
        assert client.post('/alarms/play', json=payload, headers=auth_headers).status_code == 400


# ---- greetings ----


def test_greetings_roundtrip(client, auth_headers):
    write_json(GREETINGS_FILE, [])
    response = client.post('/greetings', json={'text': '  Hello from FastAPI  '}, headers=from_ip('10.1.2.1'))

    assert response.status_code == 201
    stored = client.get('/greetings', headers=auth_headers).json()
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
def test_invalid_greetings_are_rejected(client, index):
    response = client.post('/greetings', json=INVALID_GREETINGS[index], headers=from_ip(f'10.1.3.{index}'))

    assert response.status_code == 400
    assert 'error' in response.json()


def test_greetings_are_capped(client, auth_headers, monkeypatch):
    monkeypatch.setattr(greetings_router, 'MAX_STORED_GREETINGS', 2)
    write_json(GREETINGS_FILE, [])
    for index in range(3):
        assert client.post('/greetings', json={'text': f'm{index}'}, headers=from_ip(f'10.1.4.{index}')).status_code == 201

    assert [g['text'] for g in read_json(GREETINGS_FILE)] == ['m1', 'm2']


# ---- rate limits, CORS, body size ----


def test_failed_logins_are_rate_limited(client):
    attempt = lambda ip: client.post('/login', json={'username': 'demo', 'password': 'wrong'}, headers=from_ip(ip, **ORIGIN))  # noqa: E731

    assert [attempt('10.1.5.1').status_code for _ in range(5)] == [401] * 5
    blocked = attempt('10.1.5.1')

    assert blocked.status_code == 429
    assert blocked.json() == {'error': 'Too many requests, please try again later'}
    assert int(blocked.headers['Retry-After']) >= 1
    # the browser must be able to read the error, otherwise the UI would treat it as "the Raspberry is offline"
    assert blocked.headers['Access-Control-Allow-Origin'] == 'https://filipwisniewski.pl'
    assert attempt('10.1.5.2').status_code == 401


def test_successful_logins_do_not_count(client):
    login = lambda: client.post('/login', json={'username': 'demo', 'password': 'demo'}, headers=from_ip('10.1.6.1'))  # noqa: E731

    assert [login().status_code for _ in range(10)] == [200] * 10


def test_greetings_are_rate_limited(client):
    send = lambda: client.post('/greetings', json={'text': 'spam'}, headers=from_ip('10.1.7.1'))  # noqa: E731

    assert [send().status_code for _ in range(3)] == [201] * 3
    assert send().status_code == 429


def test_cors_preflight_and_origins(client):
    preflight = client.options(
        '/alarms',
        headers={**ORIGIN, 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'authorization,content-type'},
    )
    assert preflight.status_code == 200
    assert preflight.headers['Access-Control-Allow-Origin'] == 'https://filipwisniewski.pl'
    assert 'authorization' in preflight.headers['Access-Control-Allow-Headers'].lower()

    foreign = client.get('/health', headers={'Origin': 'https://evil.example'})
    assert 'Access-Control-Allow-Origin' not in foreign.headers


def test_huge_bodies_are_refused(client):
    response = client.post('/greetings', content=b'x' * (70 * 1024), headers=from_ip('10.1.8.1', **{'Content-Type': 'application/json'}))

    assert response.status_code == 413


# ---- malformed bodies ----


@pytest.mark.parametrize('body', [{'melody': 'No such melody'}, {'melody': 5}, {'melody': ['Nokia']}, {}, ['Nokia'], None])
def test_unknown_melodies_are_rejected(client, auth_headers, body):
    assert client.post('/alarms/play', json=body, headers=auth_headers).status_code == 400


def test_alarms_body_must_be_json(client, auth_headers):
    response = client.post('/alarms', content='nope', headers={**auth_headers, 'Content-Type': 'text/plain'})

    assert response.status_code == 400


def test_greeting_that_is_not_json_is_rejected(client):
    response = client.post('/greetings', content='not json', headers=from_ip('10.1.9.1', **{'Content-Type': 'text/plain'}))

    assert response.status_code == 400
