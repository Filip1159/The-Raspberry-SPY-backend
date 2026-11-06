# The Raspberry SPY – backend

Python/Flask backend running **on a Raspberry Pi 5** (home network). It drives the hardware (camera pan/tilt servos, camera light, buzzer, 20x4 LCD + rotary encoder), schedules alarms, reads a BLE climate sensor, and issues the JWTs the frontend and MediaMTX use. Frontend repo: `../The-Raspberry-SPY-frontend` (Angular, on GitHub Pages at `https://filipwisniewski.pl`). The shared backlog is `BACKLOG.md` in the **frontend** repo.

## Runtime topology (all on the Pi)

```
browser ──HTTPS──> Cloudflare ──tunnel──> cloudflared ──> nginx :5000 ──┬─ /flask/*     -> Flask + Socket.IO :8080  (prefix stripped)
                                                                         ├─ /socket.io   -> Flask-SocketIO :8080 (websocket upgrade)
                                                                         └─ /cam1/*      -> MediaMTX HLS :8888
```

- Public hostname `api.filipwisniewski.pl` (Cloudflare Tunnel configured in the Cloudflare dashboard, no config file on the Pi). Setup notes: `configs/CONFIGS.MD`.
- nginx (`configs/default`) only proxies; it does not serve the frontend or add CORS headers.
- MediaMTX (`configs/mediamtx.yml`, v1.15.3) captures the camera with `rpicam-vid | ffmpeg` into path `cam1`, serves HLS, and authenticates readers with a JWT (`?jwt=` query) verified against Flask's `/.well-known/jwks.json` (`mediamtx_permissions` claim).
- Port `8765` runs a plain `websockets` server for an Arduino Uno R4 (`app/websocket_manager.py`, draft – only logs messages).

## Run / develop

```bash
source bin/activate            # the venv is checked into the repo directory (bin/, lib64, pyvenv.cfg)
pip install -r requirements.txt
python main.py                 # Flask+SocketIO on 0.0.0.0:8080 – DO NOT enable debug=True (breaks GPIO, see comment in server.py)
bin/ruff check . && bin/ruff format .
```

- **Only runs on the Pi.** `app/gpio/*` creates `gpiozero`/`RPLCD`/hardware-PWM objects at import time, so importing most modules on a laptop fails. Don't try to run the server locally; verify with `ruff` and by reading code, and ask the user to test on the Pi.
- There are no automated tests.
- Deploy = `git pull` on the Pi (checkout at `/home/fwisn/Documents/camera-app`), then restart Flask (and nginx/MediaMTX if their configs changed; copy `configs/default` to `/etc/nginx/sites-available/default`, `configs/mediamtx.yml` to `/mediamtx/mediamtx.yml`).

## Layout

```
main.py                     # starts BLE + Arduino websocket threads, 5 s Timer loop emitting 'ble_update' / 'system_stats_update', then run_server()
app/server.py               # Flask app, JWT (RS256, public key), CORS, blueprints, SocketIO
app/allowed_origins.py      # CORS/Socket.IO origin allow-list (+ EXTRA_ALLOWED_ORIGINS env for dev)
app/controller/
  auth_controller.py        # POST /login (users.json), GET /.well-known/jwks.json; token: 30 min, claims sub + mediamtx_permissions
  alarms_controller.py      # GET/POST /alarms, POST /alarms/play (JWT required)
  greetings_controller.py   # GET/POST /greetings (public)
  health_controller.py      # GET /health (public liveness probe, used by the frontend's offline detection)
  socket_controller.py      # Socket.IO: JWT required in handshake `auth.token` (else refused as 'unauthorized'); 'message' -> servo direction name or 'LED<0-255>'
app/alarm_manager.py        # background thread waits for next weekly alarm, plays melody; alarms.json is source of truth
app/melody_player.py        # buzzer melodies (MELODIES dict) played in a thread
app/gpio/gpio.py            # PWM camera light (GPIO14), LCD (I2C 0x27), rotary encoder, button; LCD backlight/ACT LED auto-off
app/gpio/navigation.py      # LCD menu state machine (hello/menu/camera/alarms/alarm_details/stats/climate)
app/gpio/servos_controller.py  # pan/tilt via hardware PWM (needs dtoverlay in /boot/firmware/config.txt, see CONFIGS.MD)
app/bluetooth_manager.py    # BLE client (HM-10 'BT05') polling temperature/humidity/voltage over bleak
app/system_stats.py         # CPU %, CPU temperature, RAM %
resources/                  # alarms.json, greetings.json (tracked); users.json, *.pem are gitignored and live only on the Pi
configs/                    # nginx, MediaMTX, setup docs
```

## Conventions

- Ruff: line length 140, single quotes, space indent, rules E/F/I/B/UP (`pyproject.toml`). Match the existing style: blueprints per resource, module-level singletons (`alarm_manager`, `melody_player`, `servos_controller`, `ble_manager`), threads with `daemon=True`.
- Persistence is plain JSON files; there is no database.
- Secrets/files that must exist on the Pi but are not in git: `resources/users.json` (list of `{username,password}`), `resources/private_key.pem`, `resources/public_key.pem` (RS256 pair; the public key is also published as JWKS).
- Keep CORS origins in `app/allowed_origins.py` and `hlsAllowOrigin` in `mediamtx.yml` in sync with the frontend domain.

## Gotchas / known weak spots (see BACKLOG.md)

- Absolute paths are hardcoded (`/home/fwisn/Documents/camera-app/resources/...` in `auth_controller.py`, `alarm_manager.py`, `secret_provider.py`) while `greetings_controller.py` uses a path relative to the working directory.
- Socket.IO sessions stay connected after their JWT expires (the `message` handler then disconnects them) and still receive the 5 s stats broadcast until the client disconnects.
- `users.json` stores plaintext passwords; `/login` and `/greetings` have no rate limiting; `GET /greetings` is public and returns everything ever sent.
- `POST /alarms/play` doesn't validate the melody name; a bad value raises inside the handler.
- `os.system('... sudo tee ...')` is used to control the ACT LED; Flask must run with passwordless sudo for that to work.
- The checked-in venv (`bin/`, `lib64`, `pyvenv.cfg`) is Python 3.11 while `pyproject.toml` targets py313.
