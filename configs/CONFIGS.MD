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

Run `./mediamtx`. Make sure that there are no warnings in the logs


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

# Cloudflare Tunnel

The frontend is hosted on GitHub Pages (`https://filipwisniewski.pl`). The Raspberry only exposes the API, websocket and HLS stream at `https://api.filipwisniewski.pl` through a Cloudflare Tunnel. The domain's DNS must be managed by Cloudflare (nameservers changed at the registrar; the domain itself can stay registered elsewhere).

The GitHub Pages DNS records (`A` for `@`, `CNAME` for `www`) must be set to **DNS only** (grey cloud), otherwise GitHub cannot issue the HTTPS certificate.

The tunnel is managed from the Cloudflare dashboard, so there is no config file on the Raspberry:

1. Zero Trust -> Networks -> Tunnels -> Create a tunnel -> Cloudflared. Name it `raspberry-spy`.
2. Choose Debian / arm64 and run the displayed commands on the Raspberry. The last one is `sudo cloudflared service install <token>`, which installs and enables the systemd service.
3. Add a public hostname: subdomain `api`, domain `filipwisniewski.pl`, service `HTTP`, URL `localhost:5000`. The DNS record is created automatically.

Check: `curl -i https://api.filipwisniewski.pl/flask/.well-known/jwks.json`

Allowed browser origins are set in `app/allowed_origins.py` (Flask, Socket.IO) and `hlsAllowOrigin` in `mediamtx.yml`. For local development set `EXTRA_ALLOWED_ORIGINS=http://localhost:4200`.

# Python dependencies

On the Raspberry install `requirements-raspberry.txt` (core + hardware libraries). `requirements.txt` alone is enough to run the backend with simulated hardware (`python main.py --fake`) on any machine, see `AGENTS.md`.

# Hardware PWM

Required for servos to work. Hardware PWM provides smooth movement, in contrast to the software PWM which causes much jitter.

Add the following line at the end of the `/boot/firmware/config.txt` file:

```
dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4
```
