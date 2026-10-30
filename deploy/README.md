# Agentimo live deploy (fresh Hetzner Ubuntu host)

This deploys the first screens behind HTTPS with Caddy. The app runs
as an unprivileged `agentimo` user from `/opt/agentimo`, stores its
database in `/var/lib/agentimo` (outside the checkout, so updates
never touch data), and reads the model key from
`/etc/agentimo/env` (root-owned, mode 0600). The key never appears
in the repo, the unit or the logs: a missing or refused key is
reported on the move scenario page by name (`META_API_KEY`) and
changes nothing stored.

## 1. Packages

```sh
sudo apt update
sudo apt install -y python3 caddy ufw
```

## 2. User, checkout and data directory

```sh
sudo useradd --system --home /opt/agentimo --shell /usr/sbin/nologin agentimo
sudo mkdir -p /opt/agentimo /var/lib/agentimo
sudo git clone <repo-url> /opt/agentimo
sudo chown -R agentimo:agentimo /opt/agentimo /var/lib/agentimo
sudo chmod 0750 /var/lib/agentimo
```

## 3. Model key (owner creates, root only)

```sh
sudo mkdir -p /etc/agentimo
sudo sh -c 'printf "META_API_KEY=%s\n" "PASTE_KEY_HERE" > /etc/agentimo/env'
sudo chown root:root /etc/agentimo/env
sudo chmod 0600 /etc/agentimo/env
```

Optional: append `META_API_BASE_URL=https://api.meta.ai/v1` on its own
line to point at another compatible endpoint.

## 4. Systemd unit

```sh
sudo cp /opt/agentimo/deploy/agentimo.service /etc/systemd/system/agentimo.service
sudo systemctl daemon-reload
sudo systemctl enable --now agentimo
sudo systemctl status agentimo
```

The unit runs `python3 -m app.server` from `/opt/agentimo` as the
`agentimo` user, restarts on failure, binds `APP_HOST=127.0.0.1`,
and sets `APP_PORT=8000` with `APP_DB_PATH=/var/lib/agentimo/agentimo.db`.
Logs: `journalctl -u agentimo -e`.

## 5. Caddy (HTTPS reverse proxy)

Edit the placeholder domain in `deploy/Caddyfile`, then install it:

```sh
sudo sed -i 's/agentimo.example.com/<your-domain>/' /opt/agentimo/deploy/Caddyfile
sudo cp /opt/agentimo/deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Point the domain's DNS A record at the host first so Caddy can issue
the certificate.

## 6. Firewall

```sh
sudo ufw allow OpenSSH
sudo ufw allow 80,443/tcp
sudo ufw enable
```

The app itself listens only on `127.0.0.1`; the firewall exposes
only SSH, HTTP (certificate issuance) and HTTPS.

## 7. Smoke test (issue #16)

```sh
cd /opt/agentimo
BASE=https://<your-domain> python3 deploy/smoke.py "$BASE"
```

The script checks `/`, `/deals/new`, `/settings` and
`/scenarios/move` load, then posts `Move the Benfica payment to
January` and requires a before/after forecast naming Benfica, the
source month and the target month. It exits non-zero on failure.

## 8. Updates

```sh
cd /opt/agentimo
sudo -u agentimo git pull
sudo systemctl restart agentimo
BASE=https://<your-domain> python3 deploy/smoke.py "$BASE"
```

Data stays in `/var/lib/agentimo/agentimo.db`, untouched by updates.
