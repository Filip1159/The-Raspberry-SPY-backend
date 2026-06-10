from os import path


KEY_PRIVATE_PATH = "/home/fwisn/Documents/camera-app/resources/private_key.pem"
KEY_PUBLIC_PATH = "/home/fwisn/Documents/camera-app/resources/public_key.pem"


def get_keys():
    if not (path.exists(KEY_PRIVATE_PATH) and path.exists(KEY_PUBLIC_PATH)):
        raise FileNotFoundError("Cannot find private_key.pem or public_key.pem file")

    with open(KEY_PRIVATE_PATH, "rb") as f:
        private_pem = f.read()

    with open(KEY_PUBLIC_PATH, "rb") as f:
        public_pem = f.read()

    return private_pem, public_pem
