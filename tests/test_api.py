import json


def test_health(client):
    response = client.get('/health')

    assert response.status_code == 200
    assert response.get_json() == {'status': 'ok'}


def test_login_returns_a_token(client):
    response = client.post('/login', json={'username': 'demo', 'password': 'demo'})

    assert response.status_code == 200
    assert response.get_json()['access_token']


def test_login_rejects_bad_credentials(client):
    response = client.post('/login', json={'username': 'demo', 'password': 'wrong'})

    assert response.status_code == 401


def test_jwks_is_published(client):
    keys = client.get('/.well-known/jwks.json').get_json()['keys']

    assert len(keys) == 1
    assert keys[0]['kty'] == 'RSA'
    assert 'd' not in keys[0]  # never expose the private part


def test_alarms_require_a_token(client):
    assert client.get('/alarms').status_code == 401
    assert client.post('/alarms', json=[]).status_code == 401


def test_alarms_roundtrip(client, auth_headers):
    alarms = [{'day': 'monday', 'hour': 6, 'minute': 30, 'melody': 'Nokia', 'enabled': True}]

    assert client.post('/alarms', json=alarms, headers=auth_headers).status_code == 201
    # the endpoint returns the stored file as is (content type text/html), so parse the body manually
    assert json.loads(client.get('/alarms', headers=auth_headers).get_data(as_text=True)) == alarms


def test_alarms_validation(client, auth_headers):
    invalid_hour = [{'day': 'monday', 'hour': 24, 'minute': 0, 'melody': 'Nokia', 'enabled': True}]

    assert client.post('/alarms', json=invalid_hour, headers=auth_headers).status_code == 400
    assert client.post('/alarms', json={'not': 'a list'}, headers=auth_headers).status_code == 400


def test_greetings_roundtrip(client):
    assert client.post('/greetings', json={'text': 'Hello from the tests'}).status_code == 201
    assert client.post('/greetings', json={'text': ''}).status_code == 400

    greetings = json.loads(client.get('/greetings').get_data(as_text=True))
    assert greetings[-1]['text'] == 'Hello from the tests'


def test_cors_allows_only_known_origins(client):
    allowed = client.get('/health', headers={'Origin': 'https://filipwisniewski.pl'})
    unknown = client.get('/health', headers={'Origin': 'https://evil.example'})

    assert allowed.headers.get('Access-Control-Allow-Origin') == 'https://filipwisniewski.pl'
    assert 'Access-Control-Allow-Origin' not in unknown.headers
