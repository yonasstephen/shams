# Shams — Quick Start

Choose your setup:

- [CLI](#cli-setup) — Terminal interface, Python only
- [Web App](#web-app-setup) — Full UI, requires Docker
- [Production Deployment](#production-deployment) — Self-hosted deployment

## Prerequisites

**All setups:** Yahoo Developer credentials ([get them here](https://developer.yahoo.com/apps/)) — Consumer Key and Consumer Secret

**Web app / Production:** Docker with Compose

### Installing Docker (macOS — Colima recommended)

```bash
brew install colima docker docker-compose
colima start
docker ps   # verify it's working
```

If Colima fails to start:
```bash
colima stop --force && colima start
```

**Linux:**
```bash
sudo apt-get install docker.io docker-compose-plugin   # Ubuntu/Debian
# or
sudo dnf install docker docker-compose && sudo systemctl enable --now docker   # Fedora/RHEL
```

**Alternative:** [Docker Desktop](https://www.docker.com/products/docker-desktop/)

---

## CLI Setup

```bash
git clone <repository-url> && cd shams
pipenv install
cp .env.example .env   # set YAHOO_CONSUMER_KEY and YAHOO_CONSUMER_SECRET
pipenv run ./shams
```

On first run, Yahoo OAuth opens in your browser. Enter the verification code when prompted. Tokens are saved to `~/.shams/yahoo/` for future runs.

---

## Web App Setup

**1. Configure environment**

```bash
cp .env.example .env
```

Edit `.env` with at minimum:

```env
YAHOO_CONSUMER_KEY=your_consumer_key
YAHOO_CONSUMER_SECRET=your_consumer_secret
SESSION_SECRET=any_random_string_for_development
```

**2. Start**

```bash
./scripts/dev.sh
# or: docker-compose up
```

**3. Access**

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs

**4. Login**

Click **Login with Yahoo** and authorize the app. You'll be redirected back automatically.

### Yahoo App Redirect URI

In your Yahoo Developer App settings, add:
```
http://localhost:8000/api/auth/callback
```

### Stopping

```bash
docker-compose down
```

---

## Production Deployment

```bash
./scripts/prod.sh
# or: docker-compose -f docker-compose.prod.yml up -d
```

### Production Environment

Generate a strong session secret:

```bash
openssl rand -hex 32
```

Required `.env` settings for production:

```env
YAHOO_CONSUMER_KEY=your_consumer_key
YAHOO_CONSUMER_SECRET=your_consumer_secret
SESSION_SECRET=<output from openssl above>
ALLOWED_YAHOO_EMAILS=your.email@yahoo.com
COOKIE_SECURE=true
BACKEND_URL=https://your-domain.com
FRONTEND_URL=https://your-domain.com
DEBUG=False
```

### Yahoo App Redirect URI (Production)

In your Yahoo Developer App settings, set:
```
https://your-domain.com/api/auth/callback
```

### HTTPS / Reverse Proxy

Yahoo OAuth requires HTTPS redirect URLs. Options:

- **Reverse proxy** (nginx, Nginx Proxy Manager) — recommended
- **Cloudflare Tunnel** — free SSL, works behind NAT
- **Let's Encrypt** — free certificates with certbot (auto-renewal)

Example nginx reverse proxy config:

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:80;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://localhost:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Cookie $http_cookie;
    }
}
```

### Production Security Checklist

- [ ] `SESSION_SECRET` is random (≥32 chars), not the default
- [ ] `ALLOWED_YAHOO_EMAILS` lists only your email(s)
- [ ] `COOKIE_SECURE=true`
- [ ] `BACKEND_URL` and `FRONTEND_URL` use `https://`
- [ ] `DEBUG=False`

---

## Troubleshooting

**Port already in use:**
```bash
lsof -i :8000
lsof -i :5173
```

**Docker not running (macOS):**
```bash
colima status
colima start
```

**"Access denied" after Yahoo login:**
- Check your email is in `ALLOWED_YAHOO_EMAILS`
- Email comparison is case-insensitive

**Logged out after backend restart:**
- `SESSION_SECRET` changed between runs; log in again
- Check file permissions on `~/.shams/yahoo/`

**Cache not shared with CLI:**
- Verify the Docker volume in `docker-compose.yml` maps to `~/.shams/`
- Run `/refresh` in the CLI to populate the cache first

**Build errors:**
```bash
docker-compose down -v
docker-compose build --no-cache
docker-compose up
```

**Behind a corporate proxy:**
```bash
HTTP_PROXY=http://proxy:port HTTPS_PROXY=http://proxy:port \
  docker-compose -f docker-compose.prod.yml build
```
