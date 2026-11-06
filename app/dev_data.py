import json
import shutil
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from werkzeug.security import generate_password_hash

from app.config import BASE_DIR

DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']


def ensure_dev_data(data_dir: Path) -> list[str]:
    """Creates the files that normally live only on the Raspberry (keys, users) plus empty alarms/greetings.

    Existing files are never overwritten. Returns the names of the files that were created.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    created = []

    private_key_path = data_dir / 'private_key.pem'
    public_key_path = data_dir / 'public_key.pem'
    if not (private_key_path.exists() and public_key_path.exists()):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_key_path.write_bytes(
            key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        )
        public_key_path.write_bytes(
            key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        )
        created += [private_key_path.name, public_key_path.name]

    users_path = data_dir / 'users.json'
    if not users_path.exists():
        users_path.write_text(json.dumps([{'username': 'demo', 'password_hash': generate_password_hash('demo')}], indent=2))
        created.append(users_path.name)

    alarms_path = data_dir / 'alarms.json'
    if not alarms_path.exists():
        repo_alarms = BASE_DIR / 'resources' / 'alarms.json'
        if repo_alarms.exists():
            shutil.copy(repo_alarms, alarms_path)
        else:
            default_alarms = [{'day': day, 'hour': 7, 'minute': 0, 'enabled': False, 'melody': 'Nokia'} for day in DAYS]
            alarms_path.write_text(json.dumps(default_alarms, indent=2))
        created.append(alarms_path.name)

    greetings_path = data_dir / 'greetings.json'
    if not greetings_path.exists():
        greetings_path.write_text('[]')
        created.append(greetings_path.name)

    return created
