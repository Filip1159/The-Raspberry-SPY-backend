import json
import threading

from app.config import USERS_FILE
from app.json_store import read_json, update_json, write_json
from app.users import migrate_plaintext_passwords, set_password, verify_credentials

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
