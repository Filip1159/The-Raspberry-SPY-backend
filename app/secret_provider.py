from app.config import KEY_PRIVATE_PATH, KEY_PUBLIC_PATH


def get_keys():
    if not (KEY_PRIVATE_PATH.exists() and KEY_PUBLIC_PATH.exists()):
        raise FileNotFoundError('Cannot find private_key.pem or public_key.pem file')

    with open(KEY_PRIVATE_PATH, 'rb') as f:
        private_pem = f.read()

    with open(KEY_PUBLIC_PATH, 'rb') as f:
        public_pem = f.read()

    return private_pem, public_pem
