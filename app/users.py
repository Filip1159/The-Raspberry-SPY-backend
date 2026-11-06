import logging

from werkzeug.security import check_password_hash, generate_password_hash

from app.json_store import read_json, update_json, write_json

logger = logging.getLogger('users')

# Checked when the username is unknown, so the response time does not reveal which usernames exist
_DUMMY_HASH = generate_password_hash('not-a-real-password')


def load_users(users_file) -> list[dict]:
    if not users_file.exists():
        logger.warning('Users file %s does not exist, nobody can log in', users_file)
        return []
    return read_json(users_file)


def verify_credentials(users_file, username, password) -> bool:
    if not isinstance(username, str) or not isinstance(password, str):
        return False

    user = next((u for u in load_users(users_file) if u.get('username') == username and u.get('password_hash')), None)
    # check_password_hash compares in constant time
    password_ok = check_password_hash(user['password_hash'] if user else _DUMMY_HASH, password)
    return user is not None and password_ok


def migrate_plaintext_passwords(users_file) -> int:
    """Older users.json files stored `password` in plain text. Replaces it with a salted `password_hash`."""
    if not users_file.exists():
        return 0

    migrated = 0

    def migrate(users: list[dict]) -> list[dict]:
        nonlocal migrated
        for user in users:
            if 'password' in user:
                if not user.get('password_hash'):
                    user['password_hash'] = generate_password_hash(user['password'])
                del user['password']
                migrated += 1
        return users

    if any('password' in user for user in read_json(users_file)):
        update_json(users_file, migrate)
        logger.warning('Replaced %d plain-text password(s) in %s with hashes', migrated, users_file)
    return migrated


def set_password(users_file, username: str, password: str) -> bool:
    """Adds the user or changes the password. Returns True when a new user was created."""
    users = read_json(users_file) if users_file.exists() else []
    created = True
    for user in users:
        if user.get('username') == username:
            user['password_hash'] = generate_password_hash(password)
            user.pop('password', None)
            created = False
    if created:
        users.append({'username': username, 'password_hash': generate_password_hash(password)})
    write_json(users_file, users)
    return created
