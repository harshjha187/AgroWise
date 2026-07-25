# AgroWise — Architecture

Companion to [PRD.md](PRD.md) (what & why) and [README.md](../README.md) (how to run it). This document covers **how the system is built**: app flow, component architecture, folder/file structure, and tech stack.

---

## 1. High-Level Architecture

```
 ┌──────────────┐   30 s cycle    ┌──────────────────────────────┐
 │    ESP32     │  HTTP POST JSON │      Flask REST backend      │
 │ NPK·M·pH·T   │ ───────────────▶│  validate → EMA filter →     │
 │  (firmware/) │  X-API-Key hdr  │  score → classify →          │
 └──────────────┘                 │  recommend → alert           │
        ▲                         │            │                 │
        │ (no hardware?           │            ▼                 │
        │  simulator.py)          │     SQLite database           │
        │                         │  readings + alerts tables    │
 ┌──────┴───────┐                 └───────┬──────────────┬───────┘
 │ simulator.py │                         │ REST / JSON  │
 └──────────────┘                         │ (X-API-Key)  │
                              ┌───────────▼──┐   ┌────────▼─────┐
                              │ Web dashboard│   │  Mobile app  │
                              │  (browser)   │   │  (PWA)       │
                              └──────────────┘   └──────────────┘
```

One Flask process is the entire backend surface: it serves the API (`/api/*`), the web dashboard (`/`), and the mobile PWA (`/mobile/*`). There is no separate frontend server, build step, or bundler — every frontend is a single static HTML file with inline CSS/JS, served directly by Flask via `send_from_directory`.

---

## 2. App Flow (the analysis pipeline)

Every reading — whether from real hardware, `simulator.py`, or a manual entry in either app — goes through the same server-side pipeline, exactly once, in `analysis_engine.analyze()`:

```
Sensor packet (n, p, k, m, ph, temp)
        │
        ▼
1. VALIDATE      — numeric? within physical sensor clamp range? (analysis_engine.validate)
        │  reject → HTTP 400 with reason
        ▼
2. FILTER NOISE  — exponential moving average, α = 0.45, blended with the previous filtered reading
        │
        ▼
3. SCORE         — each of 6 params → 0–100 sub-score (100 inside optimal band, power-curve falloff outside it)
        │           weighted sum → overall 0–100 Soil Health Score
        ▼
4. CLASSIFY      — FERTILE (≥80) / MODERATE (≥50) / BARREN (else)
        │           + combined-threshold override: N, P, K all critically low → forced BARREN
        ▼
5. RECOMMEND     — per-parameter deficiency/excess → dosed fertilizer / irrigation / soil-treatment advice
        │           BARREN → additional structured 4-step recovery plan
        ▼
6. ALERT         — critical/warning/ok entries for out-of-range params or a classification change
        │
        ▼
7. PERSIST       — INSERT into SQLite (readings, alerts tables)
        │
        ▼
Response: { reading, recommendations, alerts }  →  polled/read by dashboard & mobile app
```

This pipeline is defined once in `backend/analysis_engine.py` and is the single source of truth — the web dashboard also ships a **client-side copy of the same logic** (same weights, thresholds, EMA) purely as an offline fallback when it can't reach the backend; it is not a second source of truth, just a degraded-mode mirror.

### Request flow per client

- **ESP32 firmware** — reads sensors every 30s → builds a JSON packet → `HTTPClient.POST` to `/api/readings` with `X-API-Key` header → blinks status LED on success/failure. Stateless; no local storage or retry queue.
- **`simulator.py`** — same POST contract as firmware, driven by `--scenario`/`--interval`/`--api-key` CLI flags, for hardware-free demos.
- **Web dashboard** — polls `/api/readings/latest` + `/api/alerts` on an interval while "live"; falls back to a client-side scoring engine + `localStorage` persistence if the backend is unreachable.
- **Mobile app (PWA)** — same polling/fallback shape as the dashboard, tuned for a phone screen; installable via a Web App Manifest + service worker (offline app-shell caching only, not offline data).

---

## 3. Component Architecture

```
┌───────────────────────────── backend/ (Flask process) ─────────────────────────────┐
│                                                                                      │
│  server.py            HTTP routing, auth (API key), CORS policy, rate limiting,     │
│                        security headers, static file hosting for both frontends     │
│         │                                                                            │
│         ├──▶ analysis_engine.py   validate → filter → score → classify →            │
│         │                          recommend → alert  (pure functions, no I/O)      │
│         │                                                                            │
│         └──▶ database.py          SQLite access layer: schema init/migration,       │
│                                    insert_reading, insert_alerts, get_readings,      │
│                                    get_latest, get_alerts, get_summary, clear_all    │
│                                                                                      │
│  simulator.py          standalone CLI script, talks to server.py only over HTTP     │
│                         (not imported by server.py — a separate client process)     │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

`server.py` is intentionally the only component that knows about HTTP, auth, or persistence *wiring* — `analysis_engine.py` is pure computation (easy to unit-test, has its own `if __name__ == "__main__"` self-test suite), and `database.py` is the only file that touches SQL.

---

## 4. Security Architecture

Layered in `server.py`, applied to every `/api/*` route (static pages are exempt — no sensitive data there):

```
Request
  │
  ▼
[CORS check]        flask-cors, same-origin only by default
                     (opt-in cross-origin via AGROWISE_ALLOWED_ORIGINS)
  │
  ▼
[Rate limiter]       flask-limiter, per-client-IP
                     120/min default · 40/min on ingest · 5/min on destructive DELETE
  │
  ▼
[API key check]      before_request hook, hmac.compare_digest against
                     a per-install secret (env var or auto-generated .api_key file)
                     → 401 on missing/invalid key
  │
  ▼
[Route handler]      analysis_engine + database
  │
  ▼
[Security headers]   after_request hook: X-Content-Type-Options, X-Frame-Options,
                     Referrer-Policy on every response
```

Both frontends store the API key client-side (localStorage) and attach it as `X-API-Key` on every request; the firmware and `simulator.py` do the same via a constant / CLI flag. See [README.md § Security](../README.md#security) for the full threat-model writeup and the plain-HTTP/TLS tradeoff.

---

## 5. Data Model (SQLite — `backend/agrowise.db`)

Two tables, created and forward-migrated automatically by `database.init_db()` on startup:

**`readings`** — one row per analyzed packet
```
id, ts (epoch ms),
n_raw, p_raw, k_raw, m_raw, ph_raw, t_raw,        -- as received
n, p, k, m, ph, t,                                -- EMA-filtered
sub_n, sub_p, sub_k, sub_m, sub_ph, sub_t,        -- per-param 0-100 sub-scores
score, cls,                                       -- overall score + FERTILE/MODERATE/BARREN
m_status,                                         -- LOW/OPTIMAL/HIGH
source,                                           -- ESP32/SIM/MANUAL/MOBILE
device_id                                         -- distinguishes multiple physical devices; defaults to `source`
```

`device_id` scopes more than display: `database.get_latest()`, the EMA noise filter, and BARREN-transition alert detection all key off "the previous reading" for a device, so with multiple physical units posting concurrently, "previous" must mean that same device's previous reading — not whichever device happened to post most recently overall. `database.get_distinct_devices()` backs the `/api/devices` endpoint used to populate device filters/selectors in the frontends.

**`alerts`** — one row per generated alert
```
id, ts, level (critical/warning/ok), message
```

The database file is created on first run; an older pre-moisture (v1) schema is migrated in-place via `ALTER TABLE`.

---

## 6. Folder & File Structure

```
AgroWise_Project/
├── README.md                 Setup, run instructions, REST API reference, security notes
├── .gitignore                Excludes backend/.venv, backend/.api_key, backend/agrowise.db, ios/android build state
├── Dockerfile                 Production image: gunicorn serving server.py (see deploy/DEPLOY.md)
├── docker-compose.yml         gunicorn + redis (shared rate-limit storage) + nginx + certbot stack
├── .env.example                Template for docker-compose's required env vars (copy to .env, gitignored)
├── package.json                Capacitor CLI/core devDependencies (native app wrapping only —
│                               the running product itself needs none of this, see note below)
├── capacitor.config.json       appId com.agrowise.field, webDir mobile-app
├── ios/App/                    Generated Xcode project (deploy/NATIVE_WRAPPING.md)
├── android/                    Generated Android Studio/Gradle project (deploy/NATIVE_WRAPPING.md)
│
├── .github/workflows/
│   └── ci.yml                 pytest + engine self-test + frontend syntax/duplicate-id checks
│
├── deploy/
│   ├── DEPLOY.md               Step-by-step production deployment (domain → DNS → Docker → TLS)
│   ├── nginx.conf               Reverse proxy + Let's Encrypt config referenced by docker-compose.yml
│   ├── STORE_LISTING.md         App Store/Play Store listing copy + submission checklist
│   ├── PRIVACY_POLICY.md        Draft privacy policy (must be hosted at a real URL before submission)
│   ├── push-notifications.md    Web Push (buildable now) vs native FCM/APNs (needs store accounts) plan
│   └── NATIVE_WRAPPING.md       Capacitor native-wrapping status + what's left before a submittable build
│
├── backend/
│   ├── server.py             Flask app: routes, auth, CORS, rate limiting, logging, static hosting
│   ├── analysis_engine.py    Validate → filter → score → classify → recommend → alert
│   ├── database.py           SQLite schema, migrations, CRUD for readings + alerts
│   ├── simulator.py          CLI: posts realistic ESP32-shaped packets for hardware-free demos
│   ├── requirements.txt      flask, flask-cors, flask-limiter
│   ├── requirements-dev.txt   requirements.txt + pytest
│   ├── pytest.ini             pytest config (testpaths=tests)
│   ├── tests/                 32 pytest tests: server routes, database layer, analysis engine
│   ├── .api_key               (generated at runtime, gitignored) per-install API secret
│   ├── agrowise.db            (generated at runtime, gitignored) SQLite database file
│   ├── PRD.md                 Product requirements: problem, goals, users, features
│   ├── ARCHITECTURE.md        This file
│   ├── rules.md                Do/avoid guardrails per area of the codebase
│   ├── phases.md               Project roadmap: 0-5 complete (software), 6-8 pending (hardware)
│   ├── design.md               Color/theme/typography reference for both frontends (+ dark mode)
│   └── memory.md               File-by-file knowledge index + "currently active file" pointer
│
├── web-dashboard/
│   └── index.html             Single-file dashboard: Dashboard / Live Data / History /
│                               Recommendations / Alerts / Reports / Settings / About pages,
│                               3D-tilt UI, Chart.js trends, jsPDF/SheetJS export, local-mode
│                               fallback engine, dark mode toggle, onboarding overlay,
│                               accessibility pass, i18n scaffold
│
├── mobile-app/
│   ├── index.html             Single-file installable PWA: Home / History / Add / Setup pages,
│   │                           dark mode toggle, offline reading queue, onboarding overlay
│   ├── manifest.json          Web App Manifest (install metadata, icons, theme color)
│   ├── sw.js                  Service worker — app-shell caching for instant/offline open
│   └── icons/
│       ├── icon-192.png
│       └── icon-512.png
│
└── firmware/
    └── AgroWise_ESP32.ino     Arduino firmware: WiFi, sensor reads (or SIMULATE_SENSORS mode),
                                JSON packet build, HTTPClient POST with X-API-Key
```

**Design pattern to note:** the web dashboard and mobile app are each a *single self-contained HTML file* (markup + CSS + JS inline, no build tooling, no npm dependency tree) that talks to the backend purely over the documented REST API. **The running product itself still needs nothing but `pip install -r requirements.txt && python server.py`** — no Node/webpack/bundler step in that path, unchanged. The `package.json`/`node_modules`/`ios/`/`android/` additions are an *optional, separate* layer purely for wrapping `mobile-app/` as a native app for store submission (`deploy/NATIVE_WRAPPING.md`) — they don't run, build, or get touched by the normal dev/deploy loop at all.

---

## 7. Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| **Hardware** | ESP32 · RS485 NPK sensor (JXCT-style, Modbus) · capacitive soil moisture probe · analog pH probe · DS18B20 temperature sensor | `SIMULATE_SENSORS` flag lets the firmware run without any of this wired up |
| **Firmware** | Arduino C++ — `WiFi.h`, `HTTPClient.h`, `OneWire`, `DallasTemperature` | Sensor reads + JSON POST only; zero analysis logic on-device |
| **Backend** | Python 3 · Flask · flask-cors · flask-limiter · SQLite (stdlib `sqlite3`) | Single-process dev server (`app.run`), no external DB/services required |
| **Backend auth/security** | `hmac`, `secrets` (stdlib) | Constant-time API key comparison, cryptographically random key generation |
| **Web dashboard** | HTML/CSS/JS (vanilla, no framework) · Chart.js (trend charts) · jsPDF + jspdf-autotable (PDF reports) · SheetJS/xlsx (Excel export) | All three JS libs loaded via CDN `<script>` tags |
| **Mobile app** | Progressive Web App — vanilla HTML/CSS/JS, Web App Manifest, Service Worker | Installable ("Add to Home Screen"), no native code, no app-store build |
| **Data interchange** | JSON over HTTP, REST conventions (`GET`/`POST`/`DELETE`) | See README for the full endpoint table |
| **Persistence** | SQLite single-file database | Auto-created, auto-migrated, zero external setup |

---

## 8. Key Architectural Decisions (and why)

- **All intelligence lives on the backend, not the firmware.** The ESP32 only reads sensors and POSTs raw values — validation, filtering, scoring, classification and recommendations all run in `analysis_engine.py`. This keeps the firmware small/battery-friendly and means the scoring logic can be fixed/tuned without re-flashing hardware.
- **No frontend build step.** Both UIs are single static HTML files server directly by Flask. This trades some code-reuse/tooling convenience for zero-install simplicity — matches the project's "runnable in 5 minutes, no hardware needed" goal from the PRD.
- **Client-side fallback engine, not client-side source of truth.** The dashboard's local-mode scoring exists only so the UI stays usable when the backend is down; the backend's `analysis_engine.py` is the canonical implementation both are meant to agree with.
- **Combined-threshold BARREN rule lives in the classify step, not the score.** This was a deliberate invention-disclosure novelty: a good aggregate score must not be able to mask critically-low N+P+K, so that check is a hard override rather than baked into the weighted average.
- **Security applied uniformly, not selectively.** Every `/api/*` route (including `/api/health`, which reveals farm-level summary stats) requires the API key — only the static HTML pages are public, since they carry no data of their own.
