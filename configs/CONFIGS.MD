# MediaMTX

Download the MediaMTX v1.15.3. The config file format may differ between versions, so let's stick to this one. All commands should be run at `/`

```bash
sudo wget https://github.com/bluenviron/mediamtx/releases/download/v1.15.3/mediamtx_v1.15.3_linux_armv7.tar.gz
```

Extract files to `/mediamtx` directory

```bash
sudo tar xzvf mediamtx_v1.15.3_linux_armv7.tar.gz
```

Update the `mediamtx.yml` config file with the contents provided in this directory.

Run `./mediamtx` once by hand to check that there are no warnings in the logs, then stop it and run it as a service (it starts on boot and restarts after a crash; the `rpicam-vid | ffmpeg` pipeline of the `cam1` path stops and starts with it):

```bash
scripts/install_mediamtx_service.sh   # from the backend checkout: copies configs/mediamtx.yml to /mediamtx, installs and starts the unit
journalctl -u mediamtx -f             # logs
```

After a change of `configs/mediamtx.yml` `scripts/deploy.sh` copies it to `/mediamtx` and restarts MediaMTX by itself. Run `install_mediamtx_service.sh` only when `configs/mediamtx.service` changed.

# Nginx

Install the Nginx v1.22.1 using `apt`

```bash
sudo apt install nginx
```

Update the `/etc/nginx/sites-available/default` file with the contents provided in this directory.

Make Nginx run on boot

```bash
sudo systemctl enable nginx
```

# Backend service (systemd)

The backend (`python main.py`) runs as the `raspberry-spy` systemd service: it starts on boot, restarts 5 s after a crash and logs to the journal. `cloudflared`, nginx and MediaMTX are services as well (see the sections around this one).

```bash
# once, from the checkout, as the user that ran the backend until now (it must be in the gpio, i2c and bluetooth groups
# and have passwordless sudo: the ACT LED is switched with `sudo tee`)
pkill -f 'main.py'                  # stop a hand-started backend, it holds port 8080 and the GPIO pins
scripts/install_service.sh          # fills in the user / checkout / python of this machine, enables and starts the unit
scripts/install_service.sh --print  # just show the unit

# every deployment afterwards
scripts/deploy.sh                   # git pull --ff-only, pip install if the requirements changed, apply changed nginx/MediaMTX configs, restart, wait for /health

journalctl -u raspberry-spy -f      # logs
sudo systemctl status raspberry-spy
sudo systemctl restart raspberry-spy
```

The python used is `<checkout>/.venv/bin/python` (create it with `scripts/setup_venv.sh`), else `python3`.

## Automatic deployment (GitHub Actions)

The `deploy` job in `.github/workflows/ci.yml` runs `scripts/deploy.sh` on the Pi after lint and tests passed, for pushes to `master` only. It needs a self-hosted runner on the Pi (outbound connections only, so the Cloudflare Tunnel is not involved). When the Pi is off the job waits for the runner (GitHub gives up after 24 h).

Setup, once:

1. Repo -> Settings -> Actions -> Runners -> New self-hosted runner (Linux, ARM64). Follow the commands on that page on the Pi as the user that owns the checkout, give it the extra label `raspberry-spy` (`./config.sh ... --labels raspberry-spy`), then `sudo ./svc.sh install && sudo ./svc.sh start`.
2. Repo -> Settings -> Secrets and variables -> Actions -> Variables: `BACKEND_DIR` = absolute path of the checkout on the Pi.
3. The runner user needs passwordless sudo for `systemctl restart raspberry-spy.service` / `mediamtx.service`, `systemctl reload nginx`, `nginx -t` and `cp` to the two config files (the default Raspberry Pi OS user has it already).
4. Repo -> Settings -> Actions -> General: "Require approval for all outside collaborators" for workflows from forks. The runner executes workflow code on the Pi, so never run it for pull requests.

If nginx rejects a changed `configs/default`, the old file is restored and the job fails before the backend restarts. There is no automatic rollback otherwise: fix forward or `git reset --hard <sha>` on the Pi and run `scripts/deploy.sh` (it then does not see a diff, so restart services by hand if configs changed).

## Old committed virtualenv

Older checkouts have a virtualenv in the root of the repository (`bin/`, `lib/`, `lib64`, `pyvenv.cfg`, created for `/home/fwisn/Documents/camera-app`). It is no longer tracked or used: the service runs from `.venv`. After the `git pull` that stopped tracking it, remove what is left: `rm -rf bin lib lib64 pyvenv.cfg` (check first that `systemctl status raspberry-spy` shows `.venv/bin/python`).

# Cloudflare Tunnel

The frontend is hosted on GitHub Pages (`https://filipwisniewski.pl`). The Raspberry only exposes the API, websocket and HLS stream at `https://api.filipwisniewski.pl` through a Cloudflare Tunnel. The domain's DNS must be managed by Cloudflare (nameservers changed at the registrar; the domain itself can stay registered elsewhere).

The GitHub Pages DNS records (`A` for `@`, `CNAME` for `www`) must be set to **DNS only** (grey cloud), otherwise GitHub cannot issue the HTTPS certificate.

The tunnel is managed from the Cloudflare dashboard, so there is no config file on the Raspberry:

1. Zero Trust -> Networks -> Tunnels -> Create a tunnel -> Cloudflared. Name it `raspberry-spy`.
2. Choose Debian / arm64 and run the displayed commands on the Raspberry. The last one is `sudo cloudflared service install <token>`, which installs and enables the systemd service.
3. Add a public hostname: subdomain `api`, domain `filipwisniewski.pl`, service `HTTP`, URL `localhost:5000`. The DNS record is created automatically.

Check: `curl -i https://api.filipwisniewski.pl/api/.well-known/jwks.json`

Allowed browser origins are set in `app/allowed_origins.py` (FastAPI, Socket.IO) and `hlsAllowOrigin` in `mediamtx.yml`. For local development set `EXTRA_ALLOWED_ORIGINS=http://localhost:4200`.

# Users and passwords

`resources/users.json` holds `{"username": ..., "password_hash": ...}` entries (scrypt hashes). Manage them on the Raspberry:

```bash
python scripts/manage_users.py list
python scripts/manage_users.py add <username>   # asks for the password; also changes it for an existing user
python scripts/manage_users.py migrate          # only for an old file with plain-text "password" fields
```

An old `users.json` with plain-text passwords is migrated automatically the first time the new backend starts (the log says "Replaced N plain-text password(s)"). No restart is needed after adding a user.

# Rate limiting

The on-board ACT LED (switched off at night) is written through sysfs without `sudo`: install the udev rule once with `sudo cp configs/99-act-led.rules /etc/udev/rules.d/ && sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=leds` (the service user must be in the `gpio` group, which is the default for the first user). Without the rule the LED just stays as it is, with one warning in the log.

The experimental Arduino websocket (port 8765, no authentication) is off; set `ARDUINO_WEBSOCKET=1` in the service environment to enable it on a trusted network.

Local development with a real HLS picture: `docker compose -f docker-compose.dev.yml up` (MediaMTX + an ffmpeg test pattern, see the header of that file).

Refresh tokens (`resources/refresh_tokens.json`, gitignored, created on first login) keep the browser signed in for 7 days (`REFRESH_TOKEN_DAYS`). The cookie is `Secure`, so it only works through the HTTPS tunnel; set `COOKIE_SECURE=0` only for plain-http tests. Deleting the file signs everybody out. Deploy the backend before the frontend: the new UI calls `/api/refresh`.

The backend limits failed `POST /login` attempts (5/minute, 20/hour per visitor) and `POST /greetings` (3/minute, 20/hour per visitor), answering `429`. Visitors are told apart by the `CF-Connecting-IP` header that Cloudflare adds (nginx passes it on). As a second layer, add a rate limiting rule in Cloudflare (Security -> WAF -> Rate limiting rules; the free plan allows one rule):

- If incoming requests match: `(http.host eq "api.filipwisniewski.pl" and http.request.uri.path in {"/api/login" "/api/greetings"})`
- Same characteristics: IP, rate: 10 requests per 10 seconds, action: Block for 10 seconds

# Python dependencies

On the Raspberry install `requirements-raspberry.txt` (core + hardware libraries). `requirements.txt` alone is enough to run the backend with simulated hardware (`python main.py --fake`) on any machine, see `AGENTS.md`.

# Hardware PWM

Required for servos to work. Hardware PWM provides smooth movement, in contrast to the software PWM which causes much jitter.

Add the following line at the end of the `/boot/firmware/config.txt` file:

```
dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4
```
