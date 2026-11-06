from flask import request
from flask_limiter import Limiter


def client_ip() -> str:
    """The real visitor address: the app sits behind nginx and a Cloudflare Tunnel, so remote_addr is always localhost.

    CF-Connecting-IP is set by Cloudflare; the header could be forged by someone who reaches nginx/Flask directly on the
    home network, which only lets them dodge their own limit.
    """
    return request.headers.get('CF-Connecting-IP') or request.remote_addr or 'unknown'


# In-memory counters: enough for a single Flask process (they reset on restart)
limiter = Limiter(key_func=client_ip, storage_uri='memory://', headers_enabled=True)
