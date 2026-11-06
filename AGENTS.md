# The Raspberry SPY – backend

Python backend (**FastAPI** + python-socketio on uvicorn; the old Flask version is kept as a fallback) running **on a Raspberry Pi 5** (home network). It drives the hardware (camera pan/tilt servos, camera light, buzzer, 20x4 LCD + rotary encoder), schedules alarms, reads a BLE climate sensor, and issues the JWTs the frontend and MediaMTX use. Frontend repo: `../The-Raspberry-SPY-frontend` (Angular, on GitHub Pages at `https://filipwisniewski.pl`). The shared backlog is `BACKLOG.md` in the **frontend** repo.

## Runtime topology (all on the Pi)

```
browser ──HTTPS──> Cloudflare ──tunnel──> cloudflared ──> nginx :5000 ──┬─ /flask/*     -> Flask + Socket.IO :8080  (prefix stripped)
                                                                         ├─ /socket.io   -> Socket.IO (same process) :8080 (websocket upgrade)
                                                                         └─ /cam1/*      -> MediaMTX HLS :8888
```

- Public hostname `api.filipwisniewski.pl` (Cloudflare Tunnel configured in the Cloudflare dashboard, no config file on the Pi). Setup notes: `configs/CONFIGS.MD`.
- nginx (`configs/default`) only proxies; it does not serve the frontend or add CORS headers.
- MediaMTX (`configs/mediamtx.yml`, v1.15.3) captures the camera with `rpicam-vid | ffmpeg` into path `cam1`, serves HLS, and authenticates readers with a JWT (`?jwt=` query) verified against Flask's `/.well-known/jwks.json` (`mediamtx_permissions` claim).
- Port `8765` runs a plain `websockets` server for an Arduino Uno R4 (`app/websocket_manager.py`, draft – only logs messages).

## Run / develop

The backend runs on a Raspberry (real hardware) **or on any machine with simulated hardware**. The mode comes from `app/config.py`: `--fake` argument, else `HARDWARE=raspberry|fake`, else auto-detection from `/proc/device-tree/model`.

```bash
# any machine (macOS / Linux / Windows), simulated hardware
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/dev_setup.py        # creates .dev-data/: RS256 keys, users.json (demo/demo), alarms.json, greetings.json
python main.py --fake              # FastAPI+Socket.IO on :8080 (PORT env to change); /docs is the Swagger UI; CORS also allows http://localhost:4200
python -m pytest                   # tests run against the simulated hardware (add --cov=app for coverage)
ruff check . && ruff format .

# Raspberry Pi
pip install -r requirements-raspberry.txt
python main.py                     # DO NOT enable reload (starts the hardware twice, breaks GPIO). Rollback: python main_flask.py
```

- The Raspberry-only libraries (`gpiozero`, `RPLCD`, `rpi_hardware_pwm`, `bleak`, ...) are listed only in `requirements-raspberry.txt` and imported only by `app/hardware/raspberry.py`. Never import them elsewhere – that would break fake mode and CI.
- Data directory (`DATA_DIR` env): `resources/` on the Pi, `.dev-data/` (gitignored) in fake mode, so local runs never touch tracked files.
- The frontend can be pointed at a fake-mode backend with its `mock` Angular configuration (`localhost:8080`).
- CI (`.github/workflows/ci.yml`): ruff + pytest with a coverage report on Ubuntu with the core requirements only. Dependabot proposes weekly dependency updates (pip, Actions).
- Deploy = `git pull` on the Pi (the checkout must contain `resources/users.json` and the keys, or set `DATA_DIR`), `pip install -r requirements-raspberry.txt` when dependencies changed, then restart the backend (and nginx/MediaMTX if their configs changed; copy `configs/default` to `/etc/nginx/sites-available/default`, `configs/mediamtx.yml` to `/mediamtx/mediamtx.yml`).

## FastAPI (default) and the Flask fallback

`python main.py` runs the FastAPI implementation; the Flask one (`main_flask.py`, `app/server.py`, `app/controller/`, `app/rate_limit.py`) stays in the repo only as a rollback while the new one proves itself on the Pi. Both must stay contract-identical (the frontend and its mock server depend on it) until the Flask code is deleted.

```bash
python main.py --fake                    # uvicorn on :8080 (PORT env), simulated hardware; Swagger UI on /docs in fake mode (API_DOCS=1 elsewhere)
python main_flask.py --fake              # the Flask fallback
uvicorn app.api.main:asgi_app            # same, with HARDWARE=fake set in the environment instead of --fake
```

- `app/api/main.py`: `fastapi_app` (REST) and `asgi_app` = `socketio.ASGIApp(sio, other_asgi_app=fastapi_app)`, the thing to serve. The `lifespan` starts what `main.py` starts for Flask (climate sensor, Arduino websocket, LCD interface) plus the 5 s stats broadcast task. Hardware is **not** started on import, so tests can import the app.
- `app/api/routers/` (health, auth, alarms, greetings), `app/api/security.py` (RS256 verification with the public key, `current_user` dependency, 401 bodies `{'msg': ...}`), `app/api/rate_limit.py` (the `limits` library, same limits and `CF-Connecting-IP` key; the login only counts failed attempts), `app/api/sockets.py` (python-socketio `AsyncServer`: handshake JWT, expiry per session, `message` -> servos/LED run in a thread, broadcast loop), `app/api/errors.py` (`ApiError` keeps the Flask error bodies: `{'error': ...}` 400/429, `{'msg': ...}` 401; 413 for bodies > 64 kB).
- Request validation lives in `app/validation.py` and is used by **both** implementations. Endpoints read the JSON body themselves instead of Pydantic models on purpose: invalid input must give the same 400 + message as Flask, not FastAPI's 422.
- CPU-heavy or blocking work (scrypt password check, JSON file writes, scheduler reload, GPIO) goes through `run_in_threadpool` / `asyncio.to_thread`; never block the event loop.
- Tests: `tests/test_fastapi_api.py` (mirrors `test_api.py` + `test_security.py` with Starlette's `TestClient`) and `tests/test_fastapi_sockets.py` (calls the Socket.IO handlers directly). A real-client check was done with the JavaScript `socket.io-client` (websocket-only, like the Angular app); python-socketio's own client + `websocket-client` is rejected by uvicorn's handshake and is not a good test tool here.
- Dependencies: `requirements-fastapi.txt` (on top of `requirements.txt` for now); `requirements-raspberry.txt` includes it.
- **Deployed with the cutover** (see `BACKLOG.md` E5 in the frontend repo): nginx serves the API under `/api` (and still `/flask`), the frontend calls `/api`. Rollback = `python main_flask.py` instead of `python main.py` (nginx needs no change). After a quiet period delete the Flask code, `main_flask.py`, the Flask requirements and the Flask test files.
- Same port 8080 and `/socket.io` path; websocket upgrade works through uvicorn. The nginx `/api` prefix is new: copy `configs/default` to the Pi and reload nginx (see Deploy).

## Layout

```
main.py                     # uvicorn serving app.api.main:asgi_app (the lifespan starts the climate sensor, Arduino websocket, LCD interface and the 5 s stats broadcast)
main_flask.py               # fallback: the same startup for the Flask app (5 s Timer loop, run_server())
app/config.py               # hardware mode, data dir and file paths, port (all from env/argv with defaults)
app/users.py + scripts/manage_users.py  # users.json: scrypt hashes (werkzeug), constant-time verify with a dummy hash for unknown users, startup migration of plain-text passwords
app/rate_limit.py           # Flask-Limiter (in-memory), key = CF-Connecting-IP (the real visitor behind Cloudflare/nginx)
app/json_store.py           # locked, atomic read/write/update of the JSON data files
app/hardware/               # interfaces.py (Protocols), raspberry.py (real: gpiozero/RPLCD/PWM/BLE), fake.py (simulated), __init__.py = get_hardware() composition root
app/local_interface.py      # LCD + rotary encoder UI loop (backlight/ACT LED auto-off); started from main.py
app/dev_data.py + scripts/dev_setup.py  # generate keys/users/alarms/greetings for fake mode and tests
tests/                      # pytest, simulated hardware, temp data dir (tests/conftest.py); alarm scheduler tests freeze `datetime` in app.alarm_manager
app/server.py               # Flask app, JWT (RS256, public key), CORS, blueprints, SocketIO
app/allowed_origins.py      # CORS/Socket.IO origin allow-list (+ EXTRA_ALLOWED_ORIGINS env for dev)
app/controller/
  auth_controller.py        # POST /login (users.json, hashed passwords, 5 failed attempts/min per visitor), GET /.well-known/jwks.json; token: 30 min, claims sub + mediamtx_permissions
  alarms_controller.py      # GET/POST /alarms (POST reloads the scheduler), POST /alarms/play (melody validated); JWT required
  greetings_controller.py   # POST /greetings (public, max 500 chars, 3/min and 20/h per visitor, last 1000 kept), GET /greetings (JWT required)
  health_controller.py      # GET /health (public liveness probe, used by the frontend's offline detection)
  socket_controller.py      # Socket.IO: JWT required in handshake `auth.token` (else refused as 'unauthorized'); 'message' -> servo direction name or 'LED<0-255>'
app/alarm_manager.py        # background thread waits for the next ENABLED weekly alarm (none enabled = no thread), plays the melody; alarms.json is source of truth. `reload()` serializes on `__reload_lock` and joins the old thread without holding `__lock` (the thread needs it after every alarm: joining under it deadlocked)
app/melody_player.py        # melodies (MELODIES dict) played in a thread through the Buzzer interface
app/gpio/navigation.py      # LCD menu state machine (hello/menu/camera/alarms/alarm_details/stats/climate)
app/gpio/servos_controller.py  # pan/tilt logic on top of two PwmChannel objects (real PWM needs a dtoverlay in /boot/firmware/config.txt, see CONFIGS.MD)
app/system_stats.py         # CPU %, CPU temperature (thermal zone, simulated when missing), RAM %
resources/                  # alarms.json, greetings.json (tracked); users.json, *.pem are gitignored and live only on the Pi
configs/                    # nginx, MediaMTX, setup docs
```

## Conventions

- Ruff: line length 140, single quotes, space indent, rules E/F/I/B/UP (`pyproject.toml`). Match the existing style: blueprints per resource, module-level singletons (`alarm_manager`, `melody_player`, `servos_controller`) built from `get_hardware()`, threads with `daemon=True`. Hardware access always goes through the interfaces in `app/hardware/interfaces.py`; add a fake implementation whenever you add a real one.
- Persistence is plain JSON files; there is no database.
- Secrets/files that must exist on the Pi but are not in git (fake mode generates throwaway ones): `resources/users.json` (list of `{username,password_hash}`, managed with `scripts/manage_users.py`; a legacy file with plain `password` fields is hashed automatically on startup), `resources/private_key.pem`, `resources/public_key.pem` (RS256 pair; the public key is also published as JWKS).
- Keep CORS origins in `app/allowed_origins.py` and `hlsAllowOrigin` in `mediamtx.yml` in sync with the frontend domain.

## Gotchas / known weak spots (see BACKLOG.md)

- Socket.IO sessions stay connected after their JWT expires (the `message` handler then disconnects them) and still receive the 5 s stats broadcast until the client disconnects.
- The ACT LED is controlled with `os.system('... sudo tee ...')` in `app/hardware/raspberry.py`; Flask must run with passwordless sudo for that to work.
- Singletons are still created at import time (through `get_hardware()`); a full dependency-injection container is a possible follow-up (BACKLOG E4).
- The checked-in venv (`bin/`, `lib64`, `pyvenv.cfg`) is Python 3.11 while `pyproject.toml` targets py313; CI uses 3.11.
- Rate-limit counters live in memory (one Flask process): they reset on restart and are keyed by the `CF-Connecting-IP` header, which someone with direct access to nginx/Flask on the home network could forge. A Cloudflare rate-limiting rule in front of the tunnel is the second layer (see `configs/CONFIGS.MD`).
- Tokens last 30 minutes and cannot be refreshed; Socket.IO sessions are only checked for expiry when a message arrives.
- Adding a user: `python scripts/manage_users.py add <name>` on the Pi (minimum 10 characters); no restart needed, `users.json` is read on every login.
