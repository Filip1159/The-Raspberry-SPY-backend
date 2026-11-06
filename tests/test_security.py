import json
import threading

import pytest

from app.alarm_manager import alarm_manager
from app.config import GREETINGS_FILE, USERS_FILE
from app.controller import greetings_controller
from app.json_store import read_json, update_json, write_json
from app.melody_player import melody_player
from app.users import migrate_plaintext_passwords, set_password, verify_credentials

ORIGIN = {'Origin': 'https://filipwisniewski.pl'}


def from_ip(ip: str, **headers):
    return {'CF-Connecting-IP': ip, **headers}


# ---- passwords ----


def test_stored_passwords_are_hashed():
    users = read_json(USERS_FILE)

    assert users and all('password' not in user and user['password_hash'] for user in users)
    assert 'demo' not in json.dumps(users).replace('"demo"', '')  # only the username may contain it


def test_verify_credentials(tmp_path):
    users_file = tmp_path / 'users.json'
    set_password(users_file, 'filip', 'a long enough password')

    assert verify_credentials(users_file, 'filip', 'a long enough password')
    assert not verify_credentials(users_file, 'filip', 'wrong')
    assert not verify_credentials(users_file, 'nobody', 'a long enough password')
    assert not verify_credentials(users_file, None, None)
    assert not verify_credentials(users_file, 'filip', ['a long enough password'])
    assert not verify_credentials(tmp_path / 'missing.json', 'filip', 'whatever')


def test_set_password_adds_and_updates(tmp_path):
    users_file = tmp_path / 'users.json'

    assert set_password(users_file, 'filip', 'first password') is True
    assert set_password(users_file, 'filip', 'second password') is False

    assert len(read_json(users_file)) == 1
    assert not verify_credentials(users_file, 'filip', 'first password')
    assert verify_credentials(users_file, 'filip', 'second password')


def test_plaintext_passwords_are_migrated(tmp_path):
    users_file = tmp_path / 'users.json'
    users_file.write_text(json.dumps([{'username': 'old', 'password': 'plain secret'}, {'username': 'new', 'password_hash': 'x'}]))

    assert migrate_plaintext_passwords(users_file) == 1

    assert 'plain secret' not in users_file.read_text()
    assert verify_credentials(users_file, 'old', 'plain secret')
    assert migrate_plaintext_passwords(users_file) == 0


# ---- rate limiting ----


def test_failed_logins_are_rate_limited(client):
    attempt = lambda ip: client.post('/login', json={'username': 'demo', 'password': 'wrong'}, headers=from_ip(ip, **ORIGIN))  # noqa: E731

    assert [attempt('10.0.1.1').status_code for _ in range(5)] == [401] * 5
    blocked = attempt('10.0.1.1')

    assert blocked.status_code == 429
    assert blocked.get_json() == {'error': 'Too many requests, please try again later'}
    assert blocked.headers.get('Retry-After')
    # the browser must be able to read the error, otherwise the UI would treat it as "the Raspberry is offline"
    assert blocked.headers.get('Access-Control-Allow-Origin') == 'https://filipwisniewski.pl'
    # other visitors are not affected, even the correct password of the blocked address is refused only while blocked
    assert attempt('10.0.1.2').status_code == 401


def test_successful_logins_do_not_count(client):
    login = lambda: client.post('/login', json={'username': 'demo', 'password': 'demo'}, headers=from_ip('10.0.2.1'))  # noqa: E731

    assert [login().status_code for _ in range(10)] == [200] * 10


def test_greetings_are_rate_limited(client):
    send = lambda: client.post('/greetings', json={'text': 'spam'}, headers=from_ip('10.0.3.1'))  # noqa: E731

    assert [send().status_code for _ in range(3)] == [201] * 3
    assert send().status_code == 429


# ---- greetings ----


def test_greetings_can_only_be_read_with_a_token(client):
    assert client.get('/greetings').status_code == 401


INVALID_GREETINGS = [
    {'text': ''},
    {'text': '   '},
    {'text': 123},
    {'nope': 'x'},
    ['text'],
    'text',
    None,
    {'text': 'x' * (greetings_controller.MAX_GREETING_LENGTH + 1)},
]


@pytest.mark.parametrize('index', range(len(INVALID_GREETINGS)))
def test_invalid_greetings_are_rejected(client, index):
    # every case uses its own address, because invalid requests count towards the rate limit too
    response = client.post('/greetings', json=INVALID_GREETINGS[index], headers=from_ip(f'10.0.4.{index}'))

    assert response.status_code == 400


def test_greeting_that_is_not_json_is_rejected(client):
    response = client.post('/greetings', data='not json', content_type='text/plain', headers=from_ip('10.0.4.2'))

    assert response.status_code == 400


def test_greetings_are_trimmed_and_capped(client, auth_headers, monkeypatch):
    monkeypatch.setattr(greetings_controller, 'MAX_STORED_GREETINGS', 3)
    write_json(GREETINGS_FILE, [])

    for i in range(5):
        assert client.post('/greetings', json={'text': f'  hello {i}  '}, headers=from_ip(f'10.0.5.{i}')).status_code == 201

    assert [g['text'] for g in client.get('/greetings', headers=auth_headers).get_json()] == ['hello 2', 'hello 3', 'hello 4']


# ---- alarms ----


@pytest.mark.parametrize('body', [{'melody': 'No such melody'}, {'melody': 5}, {'melody': ['Nokia']}, {}, ['Nokia'], None])
def test_unknown_melodies_are_rejected(client, auth_headers, body):
    assert client.post('/alarms/play', json=body, headers=auth_headers).status_code == 400


def test_known_melody_is_played(client, auth_headers):
    assert client.post('/alarms/play', json={'melody': 'Nokia'}, headers=auth_headers).status_code == 204
    melody_player.stop()


def test_saving_alarms_reloads_the_scheduler(client, auth_headers, monkeypatch):
    reloaded = []
    monkeypatch.setattr(alarm_manager, 'reload', lambda: reloaded.append(True))
    alarms = [{'day': 'friday', 'hour': 8, 'minute': 15, 'melody': 'Panic', 'enabled': True}]

    assert client.post('/alarms', json=alarms, headers=auth_headers).status_code == 201

    assert reloaded == [True]


def test_alarms_body_must_be_json(client, auth_headers):
    response = client.post('/alarms', data='nope', content_type='text/plain', headers=auth_headers)

    assert response.status_code == 400


# ---- request size ----


def test_huge_request_bodies_are_refused(client):
    response = client.post('/greetings', json={'text': 'x' * 200_000}, headers=from_ip('10.0.6.1'))

    assert response.status_code == 413


# ---- JSON files ----


def test_json_writes_are_atomic_and_leave_no_temp_files(tmp_path):
    target = tmp_path / 'data.json'

    write_json(target, {'a': 1})
    write_json(target, {'a': 2})

    assert read_json(target) == {'a': 2}
    assert [p.name for p in tmp_path.iterdir()] == ['data.json']


def test_concurrent_updates_are_not_lost(tmp_path):
    target = tmp_path / 'data.json'
    write_json(target, [])

    threads = [threading.Thread(target=lambda i=i: update_json(target, lambda items: [*items, i])) for i in range(40)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert sorted(read_json(target)) == list(range(40))
