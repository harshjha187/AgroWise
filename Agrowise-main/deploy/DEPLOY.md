# AgroWise — Production Deployment Guide

Takes AgroWise from "runs on my laptop via `python server.py`" to a real HTTPS domain anyone can reach. Everything in this guide is scaffolded and validated (`docker compose config` passes, the image builds, the stack runs locally) — the parts only you can do are buying a domain, pointing DNS, and choosing/paying for a host. See `rules.md` § 2 for why plain HTTP was the deliberate local-dev default; this guide is what closes that gap for real deployment.

---

## What you'll need (the parts I can't do for you)

1. **A server** — any VPS works (DigitalOcean, Hetzner, Linode, a spare machine, etc.), Linux, with Docker installed. Needs public IPv4, and ports 80/443 open.
2. **A domain name** — bought from any registrar (Namecheap, Google Domains, etc.).
3. **DNS access** — to point that domain's `A` record at your server's IP.

Everything after that — the containers, TLS, process management — is already written and tested in this repo.

---

## 1. Point DNS at your server

In your domain registrar's DNS settings, add an **A record**:

```
Type: A
Name: @  (or a subdomain like "agrowise")
Value: <your server's public IP>
TTL: default
```

Wait for it to propagate (`dig +short yourdomain.com` should return your server's IP — usually a few minutes, sometimes longer).

## 2. Get the code onto the server

```bash
git clone <your-repo-url> agrowise
cd agrowise
```

(This repo is git-initialized locally already — push it to a remote you control first if you haven't.)

## 3. Fill in real config

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # generate a real key
```

Paste that key into `.env` as `AGROWISE_API_KEY=`. Then replace **every** `YOUR_DOMAIN` in `deploy/nginx.conf` with your actual domain.

## 4. First-time TLS certificate (chicken-and-egg step)

nginx's config expects certs to already exist before it can even start with the `443` block active. Bootstrap it in two steps:

```bash
# Step A: bring up nginx on port 80 only, to serve the ACME challenge
docker compose up -d nginx

# Step B: ask Let's Encrypt for a real cert (replace domain + add a real email)
docker compose run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d yourdomain.com \
  --email you@example.com --agree-tos --no-eff-email

# Step C: now bring up everything (nginx will pick up the new cert)
docker compose up -d --build
```

The `certbot` service in `docker-compose.yml` then auto-renews every 12 hours (a no-op unless the cert is close to expiry — Let's Encrypt certs last 90 days).

## 5. Verify

```bash
curl -s -H "X-API-Key: $(grep AGROWISE_API_KEY .env | cut -d= -f2)" https://yourdomain.com/api/health
```

Should return the same JSON health payload you've seen locally. Then point the mobile app / firmware at `https://yourdomain.com` instead of a LAN IP — and note the ESP32 firmware's `HTTPClient` doesn't do TLS well (per `rules.md` § 2), so the physical device likely still needs to stay on plain-HTTP LAN access to this same backend, or you use `WiFiClientSecure` (more firmware work, not yet done — see `phases.md` Phase 7).

---

## What's different from local dev, and why

| | Local dev (`python server.py`) | Production (this stack) |
|---|---|---|
| WSGI server | Flask's built-in dev server (explicitly not for production) | gunicorn, 2 workers |
| Rate-limit storage | In-memory (fine — single process) | Redis (required — see below) |
| TLS | None (plain HTTP, LAN only) | nginx + Let's Encrypt, auto-renewing |
| Client IP for rate limiting | `request.remote_addr` directly | `ProxyFix`-corrected (`AGROWISE_BEHIND_PROXY=1`) — without this every request would appear to come from nginx's own IP |
| Database file location | `backend/agrowise.db` | `/data/agrowise.db` inside a named Docker volume (`AGROWISE_DB_PATH`), so it survives container rebuilds |

**Why Redis is required with `--workers 2`:** flask-limiter's default in-memory store is per-process. With 2 gunicorn workers each holding their own counter, a client bouncing between workers could get roughly 2× the intended rate limit — silently defeating the 5/min DELETE protection in particular. `docker-compose.yml` wires `AGROWISE_RATELIMIT_STORAGE=redis://redis:6379` to fix this; don't remove it if you keep multiple workers.

## Updating

```bash
git pull
docker compose up -d --build
```

## Logs

```bash
docker compose logs -f backend   # structured request logs (see server.py's logging setup)
```
