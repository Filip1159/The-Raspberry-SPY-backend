"""Stream tokens: short-lived, read cam1 only, and useless for the API"""

import jwt
import pytest

from app.api.security import decode_token


@pytest.fixture()
def stream_token(client, auth_headers):
    return client.post('/stream-token', headers={**auth_headers, 'CF-Connecting-IP': '10.7.0.1'}).json()['stream_token']


def test_a_token_is_needed(client):
    assert client.post('/stream-token').status_code == 401


def test_the_token_reads_the_camera_and_nothing_else(client, auth_headers, stream_token):
    claims = jwt.decode(stream_token, options={'verify_signature': False})
    header = jwt.get_unverified_header(stream_token)

    assert claims['mediamtx_permissions'] == [{'action': 'read', 'path': 'cam1'}]
    assert claims['scope'] == 'stream'
    assert claims['sub'] == 'demo'
    assert claims['exp'] - claims['iat'] == 120
    assert header['alg'] == 'RS256'
    assert header['kid'] == client.get('/.well-known/jwks.json').json()['keys'][0]['kid']


def test_the_answer_tells_when_it_expires(client, auth_headers):
    body = client.post('/stream-token', headers={**auth_headers, 'CF-Connecting-IP': '10.7.0.2'}).json()

    assert set(body) == {'stream_token', 'expires_at'}


@pytest.mark.parametrize('method,path', [('get', '/alarms'), ('get', '/greetings'), ('get', '/stats/history'), ('post', '/stream-token')])
def test_the_api_refuses_a_stream_token(client, stream_token, method, path):
    response = getattr(client, method)(path, headers={'Authorization': f'Bearer {stream_token}'})

    assert response.status_code == 401
    assert response.json() == {'msg': 'Invalid token'}


def test_the_socket_refuses_a_stream_token(stream_token):
    with pytest.raises(jwt.PyJWTError):
        decode_token(stream_token)


def test_the_login_token_still_works_for_the_api(client, auth_headers):
    assert client.get('/alarms', headers=auth_headers).status_code == 200


def test_renewals_are_rate_limited(client, auth_headers):
    headers = {**auth_headers, 'CF-Connecting-IP': '10.7.0.3'}

    statuses = [client.post('/stream-token', headers=headers).status_code for _ in range(21)]

    assert statuses == [200] * 20 + [429]
