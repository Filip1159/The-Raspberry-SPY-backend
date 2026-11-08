# The Raspberry SPY – backend

Python backend (**FastAPI** + python-socketio on uvicorn) running **on a Raspberry Pi 5** (home network). It drives the hardware (camera pan/tilt servos, camera light, buzzer, 20x4 LCD + rotary encoder), schedules alarms, reads a BLE climate sensor, and issues the JWTs the frontend and MediaMTX use. Frontend repo: `../The-Raspberry-SPY-frontend` (Angular, on GitHub Pages at `https://filipwisniewski.pl`). The shared backlog is `BACKLOG.md` in the **frontend** repo.

## Runtime topology (all on the Pi)

```
browser ──HTTPS──> Cloudflare ──tunnel──> cloudflared ──> nginx :5000 ──┬─ /api/*       -> FastAPI :8080  (prefix stripped)
                                                                         ├─ /socket.io   -> Socket.IO (same process) :8080 (websocket upgrade)
                                                                         └─ /cam1/*      -> MediaMTX HLS :8888
```

- Public hostname `api.filipwisniewski.pl` (Cloudflare Tunnel configured in the Cloudflare dashboard, no config file on the Pi). Setup notes: `configs/CONFIGS.MD`.
- nginx (`configs/default`) only proxies; it does not serve the frontend or add CORS headers.
- MediaMTX (`configs/mediamtx.yml`, v1.15.3) reads the camera itself (`source: rpiCamera` on path `cam1`, no `rpicam-vid | ffmpeg` pipeline), serves HLS, and authenticates readers with a JWT (`?jwt=` query) verified against the backend's `/.well-known/jwks.json` (`mediamtx_permissions` claim).
- Port `8765` can run a plain `websockets` server for an Arduino Uno R4 (`app/websocket_manager.py`, experimental, **off** unless `ARDUINO_WEBSOCKET=1`, no authentication; it logs messages and `send()` works).

## Run / develop

The backend runs on a Raspberry (real hardware) **or on any machine with simulated hardware**. The mode comes from `app/config.py`: `--fake` argument, else `HARDWARE=raspberry|fake`, else auto-detection from `/proc/device-tree/model`.

```bash
# any machine (macOS / Linux / Windows), simulated hardware
scripts/setup_venv.sh --dev && source .venv/bin/activate   # = python3 -m venv .venv + pip install -r requirements-dev.txt
python scripts/dev_setup.py        # creates .dev-data/: RS256 keys, users.json (demo/demo), alarms.json, greetings.json
python main.py --fake              # FastAPI+Socket.IO on :8080 (PORT env to change); /docs is the Swagger UI; CORS also allows http://localhost:4200
python -m pytest                   # tests run against the simulated hardware (add --cov=app for coverage)
ruff check . && ruff format .

# Raspberry Pi
scripts/setup_venv.sh              # .venv + requirements-raspberry.txt
.venv/bin/python main.py                     # DO NOT enable reload (starts the hardware twice, breaks GPIO).
```

- The Raspberry-only libraries (`gpiozero`, `RPLCD`, `rpi_hardware_pwm`, `bleak`, ...) are listed only in `requirements-raspberry.txt` and imported only by `app/hardware/raspberry.py`. Never import them elsewhere – that would break fake mode and CI.
- Data directory (`DATA_DIR` env): `resources/` on the Pi, `.dev-data/` (gitignored) in fake mode, so local runs never touch tracked files.
- The frontend can be pointed at a fake-mode backend with its `mock` Angular configuration (`localhost:8080`).
- CI (`.github/workflows/ci.yml`): ruff + pytest with a coverage report on Ubuntu with the core requirements only. Dependabot proposes weekly dependency updates (pip, Actions).
- Deploy: the backend runs as the `raspberry-spy` systemd service (`configs/raspberry-spy.service`, installed once with `scripts/install_service.sh`). Update with `scripts/deploy.sh` on the Pi (`git pull --ff-only`, `pip install -r requirements-raspberry.txt` when the requirements changed, `systemctl restart`, waits for `/health`; it copies a changed `configs/default` to `/etc/nginx/sites-available/default` (`nginx -t` first, the old file is restored when the test fails, then reload) and a changed `configs/mediamtx.yml` to `/mediamtx/mediamtx.yml` (restarts MediaMTX)). The `deploy` job of `.github/workflows/ci.yml` runs this script on a self-hosted runner on the Pi after lint and tests pass, only for pushes to `master` (label `raspberry-spy`, working directory from the repo variable `BACKEND_DIR`). The checkout must contain `resources/users.json` and the keys, or set `DATA_DIR`. Logs: `journalctl -u raspberry-spy -f`. MediaMTX is a service too (`configs/mediamtx.service`, `scripts/install_mediamtx_service.sh`; `journalctl -u mediamtx -f`).

## FastAPI

`python main.py` serves `app.api.main:asgi_app` with uvicorn (the Flask implementation was removed after the cutover; it is in the git history before the commit "Remove the Flask implementation").

```bash
python main.py --fake                    # uvicorn on :8080 (PORT env), simulated hardware; Swagger UI on /docs in fake mode (API_DOCS=1 elsewhere)
uvicorn app.api.main:asgi_app            # same, with HARDWARE=fake set in the environment instead of --fake
```

- `app/api/main.py`: `fastapi_app` (REST) and `asgi_app` = `socketio.ASGIApp(sio, other_asgi_app=fastapi_app)`, the thing to serve. The `lifespan` starts the climate sensor, the Arduino websocket and the LCD interface, plus the 5 s stats broadcast task. Hardware is **not** started on import, so tests can import the app.
- `app/api/routers/` (health, auth incl. `/refresh` and `/logout`, alarms, greetings, stats), `app/refresh_tokens.py` (opaque random tokens, only SHA-256 hashes in `refresh_tokens.json`, 7 days, rotated on use with a 30 s grace period, set as httpOnly SameSite=Strict cookie; `COOKIE_SECURE`/`REFRESH_TOKEN_DAYS` env, Secure is off in fake mode; CORS allows credentials), `app/api/security.py` (RS256 verification with the public key, `current_user` dependency, 401 bodies `{'msg': ...}`), `app/api/rate_limit.py` (the `limits` library, same limits and `CF-Connecting-IP` key; the login only counts failed attempts), `app/api/sockets.py` (python-socketio `AsyncServer`: handshake JWT, expiry per session, `message` -> servos/LED run in a thread, broadcast loop), `app/api/errors.py` (`ApiError` produces the bodies the frontend expects: `{'error': ...}` 400/429, `{'msg': ...}` 401; 413 for bodies > 64 kB).
- Request validation lives in `app/validation.py`. Endpoints read the JSON body themselves instead of Pydantic models on purpose: invalid input must give a 400 + `{'error': ...}` (what the frontend and its mock server expect), not FastAPI's 422. Switching to Pydantic models would be a contract change for both repos.
- CPU-heavy or blocking work (scrypt password check, JSON file writes, scheduler reload, GPIO) goes through `run_in_threadpool` / `asyncio.to_thread`; never block the event loop.
- Tests: `tests/test_api.py` (Starlette's `TestClient`: auth, validation, rate limits, CORS, body size), `tests/test_sockets.py` (calls the Socket.IO handlers directly), `tests/test_security.py` (password hashing, JSON store). A real-client check was done with the JavaScript `socket.io-client` (websocket-only, like the Angular app); python-socketio's own client + `websocket-client` is rejected by uvicorn's handshake and is not a good test tool here.
- Dependencies: `requirements.txt` (direct dependencies only; `Werkzeug` stays solely for the password hashes in `users.json`), `requirements-raspberry.txt` adds the hardware libraries.
- nginx serves the API under `/api` and strips the prefix; `/socket.io` goes to the same process. Same port 8080.

## Layout

```
main.py                     # uvicorn serving app.api.main:asgi_app (the lifespan starts the climate sensor, Arduino websocket, LCD interface and the 5 s stats broadcast)
app/config.py               # hardware mode, data dir and file paths, port (all from env/argv with defaults)
app/users.py + scripts/manage_users.py  # users.json: scrypt hashes (werkzeug), constant-time verify with a dummy hash for unknown users, startup migration of plain-text passwords
app/json_store.py           # locked, atomic read/write/update of the JSON data files
app/hardware/               # interfaces.py (Protocols), raspberry.py (real: gpiozero/RPLCD/PWM/BLE), fake.py (simulated), __init__.py = get_hardware() composition root
app/local_interface.py      # LCD + rotary encoder UI loop (backlight/ACT LED auto-off); started from main.py
app/dev_data.py + scripts/dev_setup.py  # generate keys/users/alarms/greetings for fake mode and tests
tests/                      # pytest, simulated hardware, temp data dir (tests/conftest.py); alarm scheduler tests freeze `datetime` in app.alarm_manager and build their own `AlarmManager(player, file)`; `tests/test_raspberry_hardware.py` runs `app/hardware/raspberry.py` against mocked gpiozero/bleak/RPLCD
app/allowed_origins.py      # CORS/Socket.IO origin allow-list (+ EXTRA_ALLOWED_ORIGINS env for dev)
app/api/                    # the FastAPI app (see above): main.py (app, lifespan, CORS, body limit), security.py, rate_limit.py (CF-Connecting-IP key), errors.py, sockets.py, routers/
  routers/auth.py           # POST /login (users.json, hashed passwords, only failed attempts count: 5/min and 20/h per visitor), GET /.well-known/jwks.json; token: 30 min, claims sub + mediamtx_permissions; POST /stream-token (JWT required, 20/min): a 2 minute token with only `read cam1` and `scope: stream` for the video URLs, which `decode_token` refuses for the API and the socket (the UI renews it while the stream plays)
  routers/alarms.py         # GET/POST /alarms (POST reloads the scheduler), POST /alarms/play (melody validated); JWT required
  routers/camera.py         # GET/PUT /camera/settings (JWT required, PUT 10/min): stream settings from the UI -> `app/camera_settings.py`; an applied PUT broadcasts the socket event `camera_stream_restart` `{reason: 'settings'}` so every open viewer reconnects
  routers/stats.py          # GET /stats/history (JWT required): the last 120 broadcast samples (10 min, in memory, `app/stats_history.py`), oldest first
  routers/greetings.py      # POST /greetings (public, max 500 chars, 3/min and 20/h per visitor, last 1000 kept), GET /greetings (JWT required)
  routers/health.py         # GET /health (public liveness probe, used by the frontend's offline detection)
  sockets.py                # Socket.IO: JWT required in handshake `auth.token` (else refused as 'unauthorized'); 'message' -> servo direction name or 'LED<0-255>'
app/validation.py           # request validation shared by the routers
app/camera_settings.py     # camera stream settings (incl. focus: `afMode` continuous|manual, `lensPosition` 0-10 dioptres): allowlist + ranges (validate_camera_settings), camera.json (DATA_DIR, gitignored), mapping to the rpiCamera* path parameters and `PATCH /v3/config/paths/patch/cam1` on the MediaMTX Control API (127.0.0.1:9997, enabled in mediamtx.yml, unauthenticated because it is localhost-only). A patch restarts the stream (a few seconds). MediaMTX forgets patched values when it restarts, so the lifespan runs `sync()` every 30 s (patches only when the running values differ). Fake mode has no MediaMTX (`MEDIAMTX_API_URL` empty): settings are just stored, `applied` is true. The keyframe interval follows the frame rate (`rpiCameraIDRPeriod` = fps/2, a keyframe every 0.5 s) and `hlsSegmentDuration` is 500ms: HLS segments start at keyframes, so these set the stream latency. `cam1` is an on-demand source (`sourceOnDemand: yes`, so `hlsAlwaysRemux` must stay `no`): the camera starts with the first HLS request and stops ~25 s after the last viewer left. The cam1 values in mediamtx.yml must equal DEFAULTS (a test checks it)
app/alarm_manager.py        # background thread waits for the next ENABLED weekly alarm (none enabled = no thread), plays the melody; alarms.json is source of truth. `reload()` serializes on `__reload_lock` and joins the old thread without holding `__lock` (the thread needs it after every alarm: joining under it deadlocked)
app/services.py            # get_services(): MelodyPlayer + AlarmManager + ServosController, created on first use
app/climate.py             # parse_reading() (never raises, validates ranges), ClimateReadings (shared by the BLE and the fake sensor), `stale` after CLIMATE_STALE_SECONDS (default 300); `ble_update` carries `stale`
app/hardware/sysfs_led.py  # ACT LED through sysfs without sudo (needs configs/99-act-led.rules); permission errors are logged once, the LED is left alone
app/melody_player.py        # melodies (MELODIES dict) played in a thread through the Buzzer interface
app/gpio/navigation.py      # LCD menu state machine (hello/menu/camera/alarms/alarm_details/stats/climate)
app/gpio/servos_controller.py  # pan/tilt logic on top of two PwmChannel objects (real PWM needs a dtoverlay in /boot/firmware/config.txt, see CONFIGS.MD)
app/system_stats.py         # CPU %, CPU temperature (thermal zone, simulated when missing), RAM %
resources/                  # alarms.json, greetings.json (tracked); users.json, *.pem are gitignored and live only on the Pi
configs/                    # nginx, MediaMTX, setup docs
```

## Conventions

- Ruff: line length 140, single quotes, space indent, rules E/F/I/B/UP (`pyproject.toml`). Match the existing style: blueprints per resource, the long-lived objects (`MelodyPlayer`, `AlarmManager`, `ServosController`) are created lazily by `get_services()` in `app/services.py` (the lifespan calls it at startup); classes take their dependencies as constructor arguments, so tests build isolated instances, threads with `daemon=True`. Hardware access always goes through the interfaces in `app/hardware/interfaces.py`; add a fake implementation whenever you add a real one.
- Persistence is plain JSON files; there is no database.
- Secrets/files that must exist on the Pi but are not in git (fake mode generates throwaway ones): `resources/users.json` (list of `{username,password_hash}`, managed with `scripts/manage_users.py`; a legacy file with plain `password` fields is hashed automatically on startup), `resources/private_key.pem`, `resources/public_key.pem` (RS256 pair; the public key is also published as JWKS).
- Keep CORS origins in `app/allowed_origins.py` and `hlsAllowOrigin` in `mediamtx.yml` in sync with the frontend domain.

## Gotchas / known weak spots (see BACKLOG.md)

- Socket.IO sessions stay connected after their JWT expires (the `message` handler then disconnects them) and still receive the 5 s stats broadcast until the client disconnects.
- The ACT LED is controlled with `os.system('... sudo tee ...')` in `app/hardware/raspberry.py`; the backend must run with passwordless sudo for that to work.
- Singletons are still created at import time (through `get_hardware()`); a full dependency-injection container is a possible follow-up (BACKLOG E4).
- Python 3.11 everywhere (Raspberry Pi OS, CI, `pyproject.toml` target). The virtualenv is `.venv` (`scripts/setup_venv.sh`, gitignored). The old virtualenv that used to be committed (`bin/`, `lib64`, `pyvenv.cfg`) is gitignored and no longer tracked; a Pi that still has it can delete it (`rm -rf bin lib lib64 pyvenv.cfg`).
- Rate-limit counters live in memory (one uvicorn process): they reset on restart and are keyed by the `CF-Connecting-IP` header, which someone with direct access to nginx/Flask on the home network could forge. A Cloudflare rate-limiting rule in front of the tunnel is the second layer (see `configs/CONFIGS.MD`).
- Tokens last 30 minutes and cannot be refreshed; Socket.IO sessions are only checked for expiry when a message arrives.
- Adding a user: `python scripts/manage_users.py add <name>` on the Pi (minimum 10 characters); no restart needed, `users.json` is read on every login.

