"""Manage the users that may log in (resources/users.json on the Raspberry, .dev-data/users.json in fake mode).

python scripts/manage_users.py list
python scripts/manage_users.py add <username>        # adds the user or changes the password (asks for it)
python scripts/manage_users.py migrate               # hashes plain-text passwords of an old users.json
"""

import getpass
import sys
from pathlib import Path

MIN_PASSWORD_LENGTH = 10


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from app.config import USERS_FILE
    from app.refresh_tokens import revoke_all
    from app.users import load_users, migrate_plaintext_passwords, set_password

    command = argv[1] if len(argv) > 1 else ''

    if command == 'list':
        for user in load_users(USERS_FILE):
            print(user.get('username'), '(password hashed)' if user.get('password_hash') else '(PLAIN-TEXT password, run migrate)')
        return 0

    if command == 'migrate':
        print(f'Migrated {migrate_plaintext_passwords(USERS_FILE)} user(s) in {USERS_FILE}')
        return 0

    if command == 'add' and len(argv) == 3:
        password = getpass.getpass('Password: ')
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f'The password must have at least {MIN_PASSWORD_LENGTH} characters')
            return 1
        if password != getpass.getpass('Repeat the password: '):
            print('The passwords do not match')
            return 1
        created = set_password(USERS_FILE, argv[2], password)
        print(f'{"Added" if created else "Updated"} {argv[2]} in {USERS_FILE}')
        if not created:
            print(f'Signed {argv[2]} out of {revoke_all(argv[2])} browser session(s); access tokens expire within 30 minutes')
        return 0

    print(__doc__)
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
