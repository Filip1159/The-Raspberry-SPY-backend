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

After a change of `configs/mediamtx.yml` run the script again (`scripts/deploy.sh` reminds you).

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
scripts/deploy.sh                   # git pull --ff-only, pip install if the requirements changed, restart, wait for /health

journalctl -u raspberry-spy -f      # logs
sudo systemctl status raspberry-spy
sudo systemctl restart raspberry-spy
```

The python used is `<checkout>/.venv/bin/python` (create it with `scripts/setup_venv.sh`), else the legacy `<checkout>/bin/python`, else `python3`.

## Moving to `.venv` (one-time)

Until now the virtualenv was **committed to git** (`bin/`, `lib64`, `pyvenv.cfg` at the root of the checkout, created for `/home/fwisn/Documents/camera-app`). It is being replaced by an untracked `.venv`. Order matters: removing the old one from git makes `git pull` delete `bin/`, so the service has to be on `.venv` first.

```bash
git pull                                # brings scripts/setup_venv.sh (the old venv is still tracked and untouched)
scripts/setup_venv.sh                   # creates .venv and installs requirements-raspberry.txt (a few minutes on the Pi)
.venv/bin/python -c "import gpiozero, bleak, RPLCD, fastapi"   # sanity check
scripts/install_service.sh              # re-renders the unit: it now points at .venv/bin/python
sudo systemctl status raspberry-spy     # healthy? then the old venv is no longer needed
```

If `pip` fails to build `lgpio`/`rpi-lgpio`, install the build tools first: `sudo apt install python3-dev swig liblgpio-dev`.

Only after that is the old virtualenv removed from the repository (a separate commit; after it `git pull` deletes `bin/`, `lib64` and `pyvenv.cfg` on the Pi, and the untracked `lib/` can be deleted by hand).

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
