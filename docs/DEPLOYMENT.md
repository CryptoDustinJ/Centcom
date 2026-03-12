# Star Office UI - Production Deployment Guide

This guide covers deploying Star Office UI in a production environment with high availability, security, and observability.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Systemd Service](#systemd-service)
5. [Nginx Reverse Proxy](#nginx-reverse-proxy)
6. [TLS/SSL](#tls-ssl)
7. [Cloudflare Tunnel](#cloudflare-tunnel)
8. [Monitoring](#monitoring)
9. [Backup & Restore](#backup--restore)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Linux server (Ubuntu 22.04+ recommended)
- Python 3.10 or newer
- Git
- Nginx (for reverse proxy, optional but recommended)
- SSL certificate (Let's Encrypt) if exposing publicly
- Optional: Redis server (for rate limiting and future RQ tasks)
- Optional: Prometheus for metrics scraping

## Installation

```bash
# 1) Clone repository
git clone https://github.com/ringhyacinth/Star-Office-UI.git
cd Star-Office-UI

# 2) Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3) Install Python dependencies
pip install --upgrade pip
pip install -r backend/requirements.txt

# 4) Create required directories
mkdir -p logs assets/bg-history assets/home-favorites memory

# 5) Copy sample configuration files
cp state.sample.json state.json
cp join-keys.sample.json join-keys.json
cp runtime-config.sample.json runtime-config.json  # if using Gemini

# 6) Set environment variables (create .env file)
cat > .env <<EOF
FLASK_SECRET_KEY=<generate a strong random 32+ char hex>
STAR_OFFICE_ENV=production
ASSET_DRAWER_PASS=<strong password>
GEMINI_API_KEY=<your Gemini API key if using AI backgrounds>
REDIS_URL=redis://localhost:6379/0  # optional
EOF
chmod 600 .env
```

## Configuration

Key configuration files:

- `state.json` – main agent state
- `agents-state.json` – multi-agent registry (auto-managed)
- `join-keys.json` – agent invite keys
- `runtime-config.json` – Gemini settings (auto-created with chmod 600)
- `asset-positions.json` – custom asset coordinates
- `asset-defaults.json` – default asset selections

Environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `FLASK_SECRET_KEY` | Yes (prod) | Random 24+ character secret for session signing |
| `STAR_OFFICE_ENV` | No | Set to `production` to enable security checks |
| `ASSET_DRAWER_PASS` | No | Password to access asset editor (default `1234`) |
| `GEMINI_API_KEY` | Optional | Google Gemini API key for AI background generation |
| `REDIS_URL` | Optional | Redis connection for rate limiting and future task queue |
| `STAR_BACKEND_PORT` | No | Override port (default 19000) |
| `LOG_LEVEL` | No | Logging level (INFO, DEBUG, WARNING) |

**Important**: In production, `FLASK_SECRET_KEY` must be at least 24 characters and not contain "change-me", "dev", etc. `ASSET_DRAWER_PASS` should be at least 8 characters and not be `1234`.

## Systemd Service

Create a systemd user unit to manage the backend service:

`~/.config/systemd/user/star-office.service`:

```ini
[Unit]
Description=Star Office UI Backend
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/youruser/Star-Office-UI
Environment="PATH=/home/youruser/Star-Office-UI/.venv/bin"
EnvironmentFile=/home/youruser/Star-Office-UI/.env
ExecStart=/home/youruser/Star-Office-UI/.venv/bin/python -m gunicorn \
  --workers 3 \
  --worker-class sync \
  --bind 127.0.0.1:19000 \
  --timeout 120 \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  --preload \
  backend.app:create_app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now star-office.service
systemctl --user status star-office
```

Note: If using `runtime` as the service name `star-office`, adjust. You can also use a system-level service (`/etc/systemd/system/`) if preferred.

## Nginx Reverse Proxy

Configure Nginx to serve the backend and frontend via a single upstream:

`/etc/nginx/sites-available/star-office`:

```nginx
upstream star_office_backend {
    server 127.0.0.1:19000;
    keepalive 32;
}

server {
    listen 80;
    server_name office.yourdomain.com;

    # Redirect HTTP to HTTPS (if using TLS)
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name office.yourdomain.com;

    # SSL certificates (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/office.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/office.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Security headers
    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Frontend static assets - long cache
    location /static/ {
        alias /home/youruser/Star-Office-UI/frontend/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Assets upload directory (protected)
    location /assets/ {
        alias /home/youruser/Star-Office-UI/frontend/;
        # Require password for modifications (handled by app)
        # Only allow GET for public assets
        limit_except GET {
            deny all;
        }
    }

    # Proxy to backend for dynamic routes
    location / {
        proxy_pass http://star_office_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (if needed in future)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_connect_timeout 5s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Health check endpoint for monitoring
    location /health {
        access_log off;
        proxy_pass http://star_office_backend;
    }

    # Prometheus metrics endpoint (if enabled)
    location /metrics {
        allow 127.0.0.1;  # restrict to localhost or monitoring network
        deny all;
        proxy_pass http://star_office_backend;
    }
}
```

Enable site:

```bash
ln -s /etc/nginx/sites-available/star-office /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

## TLS/SSL

Use Let's Encrypt with certbot:

```bash
sudo certbot --nginx -d office.yourdomain.com
```

Certbot will auto-configure SSL and set up renewal.

## Cloudflare Tunnel (Alternative to Nginx)

If you don't want to open ports or manage Nginx, Cloudflare Tunnel is the easiest way to expose the service securely:

```bash
cloudflared tunnel --url http://127.0.0.1:19000
```

It will give you a `*.trycloudflare.com` URL. For a custom domain, set up a tunnel with your Cloudflare-managed DNS.

## Monitoring

### Logs

Structured JSON logs are written to `logs/star-office.log` with rotation (10 MB, keep 10). Also stdout logs are captured by systemd (`journalctl -u star-office -f`).

### Audit Trail

All critical actions (agent join/leave, state changes, approvals) are appended to `audit.log` in the project root. This file is append-only and can be shipped to a SIEM.

### Metrics (Prometheus)

If `prometheus-client` is installed, the `/metrics` endpoint exposes:

- `staroffice_http_requests_total` (counter by method, endpoint, status)
- `staroffice_http_request_duration_seconds` (histogram)
- `staroffice_agents_total` (gauge by state)
- `staroffice_stale_agents_total` (gauge)
- `staroffice_json_write_duration_seconds` (histogram by operation)
- `staroffice_asset_uploads_total` (counter by extension)
- `staroffice_gemini_generation_total` (counter by status)

Configure Prometheus to scrape `https://office.yourdomain.com/metrics` (ensure access is restricted via firewall or nginx `allow/deny`).

### Health Checks

- Endpoint: `GET /health`
- Returns JSON with status of state file, agents file, frontend, disk space, Redis, Gemini environment.
- HTTP status: 200 healthy, 503 unhealthy.

Use in monitoring systems (e.g., Uptime Kuma, Grafana, systemd watchdog).

## Backup & Restore

### What to backup

- Entire project directory (contains config files, state, assets, logs)
- Specifically: `state.json`, `agents-state.json`, `join-keys.json`, `runtime-config.json`, `audit.log`
- Optional: `asset-positions.json`, `asset-defaults.json`
- Optional: `memory/` directory if you care about yesterday's memo entries

### Automated backup script example

`/home/youruser/Star-Office-UI/scripts/backup.sh`:

```bash
#!/bin/bash
set -euo pipefail
BACKUP_DIR="/backup/star-office"
DATE=$(date +%Y%m%d_%H%M%S)
tar -czf "$BACKUP_DIR/star-office-$DATE.tar.gz" \
  state.json agents-state.json join-keys.json runtime-config.json audit.log \
  asset-positions.json asset-defaults.json \
  memory/ assets/bg-history/ assets/home-favorites/
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +7 -delete
```

Add to crontab (`crontab -e`):

```
0 2 * * * /home/youruser/Star-Office-UI/scripts/backup.sh
```

### Restore

```bash
# Stop service
systemctl --user stop star-office

# Extract backup to directory
tar -xzf star-office-20260311_020000.tar.gz -C /home/youruser/Star-Office-UI/

# Ensure correct permissions
chmod 600 runtime-config.json
chown -R youruser:youruser /home/youruser/Star-Office-UI

# Restart
systemctl --user start star-office
```

## Troubleshooting

### Service won't start

Check logs:

```bash
journalctl --user -u star-office -n 50
# or
tail -f logs/star-office.log
```

Common issues:
- `FLASK_SECRET_KEY` missing or weak (length <24, contains "dev")
- `ASSET_DRAWER_PASS` is `1234` in production (update it)
- Port 19000 already in use
- Directories not writable by service user

### 502 Bad Gateway

If using Nginx, the upstream may be down. Check service status:

```bash
systemctl --user status star-office
```

### Agents not appearing / stale

Check that the join key matches and the agent's push is reaching the backend. Verify `agents-state.json` exists and is writable. The `/health` endpoint should show `agents_file: ok`.

### Gemini generation fails

Ensure the `gemini-image-generate` skill is installed in your OpenClaw workspace (or provide the script in `skills/gemini-image-generate/scripts/gemini_image_generate.py` with Python venv at `skills/gemini-image-generate/.venv/bin/python`). The API key must be set in `runtime-config.json` or `GEMINI_API_KEY` env.

### Rate limiting too strict

Adjust the limits in `backend/rate_limit.py` or use Redis for distributed limits. You can also set `USE_REDIS` env.

---

Next steps: See OPERATIONS.md for day-to-day operations.
