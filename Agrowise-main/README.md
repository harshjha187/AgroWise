# AgroWise

**IoT-Based Smart Soil Health Analysis, Barren Land Detection and Automated Recovery Recommendation System**

Inventors: Harsh Kumar Jha, Hridyanshu Sharma, Ujjawal Dahiya

---

## Abstract

AgroWise is an end-to-end IoT system that continuously measures six soil parameters — Nitrogen, Phosphorus, Potassium, **Soil Moisture**, pH and Temperature — on a 30-second cycle using an ESP32. Every packet is validated, noise-filtered (exponential moving average), scored on a weighted 0–100 Soil Health Score, classified as **FERTILE (≥ 80) / MODERATE (≥ 50) / BARREN**, and converted into actionable **fertilizer, irrigation and soil-treatment** recommendations with indicative dosages. All readings are persisted in a SQLite database and served over a REST API to a web dashboard and an installable mobile app.

A key novelty is the **combined-threshold barren detection rule**: if the N, P and K sub-scores are *all* critically low, the land is classified BARREN regardless of the aggregate score, so nutrient-dead soil can never hide behind good pH and temperature.

---

## System architecture

```
 ┌──────────────┐   30 s cycle    ┌──────────────────────────────┐
 │    ESP32     │  HTTP POST JSON │      Flask REST backend      │
 │ NPK·M·pH·T   │ ───────────────▶│  validate → EMA filter →     │
 │  (firmware/) │   WiFi / BT     │  score → classify →          │
 └──────────────┘                 │  recommend → alert           │
        ▲                         │            │                 │
        │ (no hardware?           │            ▼                 │
        │  simulator.py)          │     SQLite database          │
        │                         │  readings + alerts tables    │
 ┌──────┴───────┐                 └───────┬──────────────┬───────┘
 │ simulator.py │                         │ REST / JSON  │
 └──────────────┘                         ▼              ▼
                              ┌──────────────┐   ┌──────────────┐
                              │ Web dashboard│   │  Mobile app  │
                              │  (browser)   │   │  (PWA)       │
                              └──────────────┘   └──────────────┘
```

The analysis pipeline mirrors the project pseudocode exactly:
**Read (NPK · Moisture · pH · Temp) → Validate → Filter Noise → Calculate Soil Health Score → Classify Land → Analyze Moisture / NPK / pH → Generate Fertilizer + Irrigation + Treatment Recommendations → Send Data → Update Dashboard → Display Alerts → Wait 30 s.**

---

## Repository structure

```
AgroWise_Project/
├── README.md                      ← you are here
├── backend/
│   ├── server.py                  Flask REST API + hosts both frontends
│   ├── analysis_engine.py         validation, EMA filter, scoring, classification, recommendations
│   ├── database.py                SQLite layer (agrowise.db auto-created)
│   ├── simulator.py               posts realistic ESP32 packets for hardware-free demos
│   └── requirements.txt           flask, flask-cors, flask-limiter
├── web-dashboard/
│   └── index.html                 professional dashboard (API-connected, offline fallback)
├── mobile-app/
│   ├── index.html                 AgroWise Field — installable mobile app (PWA)
│   ├── manifest.json              install metadata
│   ├── sw.js                      service worker (instant open / offline shell)
│   └── icons/                     192 px & 512 px app icons
└── firmware/
    └── AgroWise_ESP32.ino        complete Arduino firmware (RS485 NPK, pH ADC, DS18B20)
```

---

## Quick start (5 minutes, no hardware needed)

**1. Start the backend** (Python 3.10+):

```bash
cd backend
pip install -r requirements.txt
python server.py
```

On first run this generates a random **API key** (saved to `backend/.api_key`, gitignored) and prints it to the console — every `/api/*` request must include it. Copy it now; you'll paste it into the dashboard/mobile app's Settings page in step 2.

**2. Open the web dashboard** → http://localhost:5000/
Go to **Settings** and paste the API key printed above, then **Reconnect**. The badge shows **BACKEND · SQLITE** when connected.

**3. Feed it data** — either switch the dashboard to the *Simulate ESP32* tab, or run the standalone simulator in a second terminal:

```bash
cd backend
python simulator.py --scenario moderate    --interval 3 --api-key <the-key-server.py-printed>
python simulator.py --scenario dry         --interval 3 --api-key <key>   # low moisture -> irrigation reco
python simulator.py --scenario waterlogged --interval 3 --api-key <key>   # excess moisture warning
python simulator.py --scenario barren      --interval 3 --api-key <key>   # watch it flip to BARREN
```

`--api-key` can be skipped if you `export AGROWISE_API_KEY=<key>` first.

**4. Mobile app** — find your PC's LAN IP (`ipconfig` on Windows, `ifconfig`/`ip a` on Linux/Mac), then on a phone connected to the **same WiFi** open:

```
http://<your-pc-ip>:5000/mobile/
```

Go to **Setup**, confirm the server URL, paste the **API key**, tap **Save & connect**. To install it like a native app: Chrome menu → **Add to Home screen**.

**5. Real hardware** — open `firmware/AgroWise_ESP32.ino` in Arduino IDE, set your WiFi credentials, `SERVER_URL` to `http://<your-pc-ip>:5000/api/readings`, and `API_KEY` to the key `server.py` printed on startup, then flash. Ships with `SIMULATE_SENSORS true` so you can test the full chain before wiring sensors; set it to `false` once the NPK (RS485), pH (ADC) and DS18B20 probes are connected. Running more than one physical ESP32 against the same backend (e.g. separate fields)? Give each unit a distinct `DEVICE_ID` in the firmware's config block — see [Multiple devices](#multiple-devices) below.

---

## REST API reference

Base URL: `http://<server>:5000`

**Every `/api/*` route requires an `X-API-Key` header** (see [Security](#security) below). Static pages (`/`, `/mobile/*`) don't.

| Method | Endpoint              | Description                                        | Rate limit |
|--------|-----------------------|----------------------------------------------------|------------|
| GET    | `/api/health`         | Server + database status                           | 120/min    |
| POST   | `/api/readings`       | Ingest `{n,p,k,ph,temp,source,device_id}` → full analysis | 40/min |
| GET    | `/api/readings?limit=200&device_id=` | Reading history (oldest → newest), optionally scoped to one device | 120/min |
| GET    | `/api/readings/latest?device_id=`| Latest reading + recommendations, optionally scoped to one device | 120/min |
| GET    | `/api/devices`        | Every distinct `device_id` seen so far             | 120/min    |
| GET    | `/api/alerts?limit=30`| Recent alerts (newest first)                       | 120/min    |
| GET    | `/api/summary`        | Totals, average score, class counts                | 120/min    |
| GET    | `/api/export/csv`     | Download the whole dataset as CSV (includes `device_id` column) | 120/min |
| DELETE | `/api/readings`       | Wipe all stored data                               | 5/min      |

Example ingest:

```bash
curl -X POST http://localhost:5000/api/readings \
     -H "Content-Type: application/json" \
     -H "X-API-Key: <the-key-server.py-printed>" \
     -d '{"n":85,"p":24,"k":150,"m":28,"ph":6.5,"temp":27,"source":"ESP32","device_id":"ESP32-Field2"}'
```

### Multiple devices

`device_id` distinguishes readings from separate physical ESP32 units posting to the same backend (e.g. one per field). It's optional and fully backward-compatible: if omitted, it defaults to the packet's `source` value, so a single-device setup needs zero configuration changes.

- **Firmware**: set `DEVICE_ID` in `firmware/AgroWise_ESP32.ino`'s config block (default `"ESP32-01"`).
- **Simulator**: pass `--device-id SIM-Field2` to `simulator.py` (defaults to just `"SIM"` if omitted).
- **Why it matters beyond display**: the EMA noise filter and BARREN-transition alert logic both key off "the previous reading" — scoping by `device_id` keeps each device's history independent instead of blending readings from different physical units together.
- **Viewing per-device data**: the web dashboard's History page has a device filter dropdown (populated from `GET /api/devices`); the mobile app shows the originating device in its status line.

---

## Security

- **API key required on every `/api/*` request.** `server.py` generates a random key on first run (`secrets.token_urlsafe(32)`), persists it to `backend/.api_key` (never commit this file — it's gitignored), and prints it on startup. Send it as the `X-API-Key` header; requests without a valid key get `401 Unauthorized`. Override with the `AGROWISE_API_KEY` environment variable to pin a fixed key (e.g. in a deployment config) instead of the auto-generated one. The comparison uses `hmac.compare_digest` to avoid timing attacks.
- **CORS is same-origin only by default.** The dashboard and mobile app are served by this same Flask process, so they never need cross-origin requests. If you host the frontend elsewhere and point it at a remote backend, set `AGROWISE_ALLOWED_ORIGINS=https://your-frontend.example` (comma-separated for multiple origins) on the backend — without it, browsers block the cross-origin calls entirely.
- **Rate limiting** (Flask-Limiter, per client IP) caps abuse and brute-force key guessing — see the table above. `DELETE /api/readings` is capped hardest (5/min) since it's destructive.
- **Security headers** (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`) are set on every response.
- **Transport is plain HTTP** (matches the ESP32/Arduino `HTTPClient`, which doesn't do TLS well on this hardware). On a trusted home/lab WiFi this is the standard tradeoff for local IoT setups; anyone with access to that WiFi network can still observe traffic at the packet level even with the API key in place. If you need encryption in transit (e.g. on an untrusted network), put the Flask app behind a reverse proxy (nginx/Caddy) terminating TLS, and update `SERVER_URL` / the dashboard & mobile "Backend URL" accordingly — the ESP32 firmware would then need a TLS-capable HTTP client and the proxy's certificate.
- Inputs are still validated/range-checked server-side (`analysis_engine.validate()`) and all SQL uses parameterized queries — this was already true before this hardening pass and still holds.

---

## Scoring methodology

Each parameter earns a 0–100 sub-score: **100 inside its optimal band**, falling along a power curve (exponent 1.6) toward 0 at the agronomic limits — so severe deficiency is penalized progressively harder than mild deficiency.

| Parameter      | Optimal band  | Zero at        | Weight |
|----------------|---------------|----------------|--------|
| Nitrogen       | 80–160 mg/kg  | 0 / 320 mg/kg  | 15 %   |
| Phosphorus     | 20–50 mg/kg   | 0 / 140 mg/kg  | 15 %   |
| Potassium      | 110–250 mg/kg | 0 / 500 mg/kg  | 15 %   |
| Soil Moisture  | 20–45 % VWC   | 0 / 75 %       | 20 %   |
| Soil pH        | 6.0–7.5       | 3.5 / 9.5      | 20 %   |
| Temperature    | 18–32 °C      | 2 / 48 °C      | 15 %   |

**Noise filter:** exponential moving average, α = 0.45 (new sample weight).

**Classification:** score ≥ 80 → FERTILE · score ≥ 50 → MODERATE · else BARREN.
**Combined-threshold rule (novelty):** if N, P *and* K sub-scores are all < 35 → **BARREN**, regardless of aggregate score.

**Recommendation engine:** low N → urea (split doses) · low P → DAP at sowing · low K → MOP · **moisture < 20 % → irrigation dose scales with deficit** · **moisture > 45 % → halt irrigation, check drainage** · pH < 6.0 → agricultural lime · pH > 7.5 → gypsum + compost · temperature out of range → environmental advisory · BARREN → 4-step structured recovery plan (compost → green manure → staged NPK → light irrigation, re-test in 30 days). Dosages scale with the measured deficit.

> Dosages are indicative for demonstration. Validate with the local KVK / soil-testing laboratory before field application.

---

## Database schema (SQLite — `backend/agrowise.db`)

**readings** — one row per analyzed packet
`id, ts (epoch ms), n_raw p_raw k_raw m_raw ph_raw t_raw, n p k m ph t (filtered), sub_n sub_p sub_k sub_m sub_ph sub_t, score, cls, m_status (LOW/OPTIMAL/HIGH), source`

**alerts** — one row per generated alert
`id, ts, level (critical/warning/ok), message`

The file is created automatically on first run. If an older v1 database (without moisture columns) is present, it is migrated in-place via `ALTER TABLE`. Delete it (or `DELETE /api/readings`) to reset.

---

## Tech stack

| Layer     | Technology                                                        |
|-----------|-------------------------------------------------------------------|
| Hardware  | ESP32 · JXCT-style RS485 NPK sensor · capacitive moisture probe · analog pH probe · DS18B20 |
| Firmware  | Arduino C++ (WiFi, HTTPClient, OneWire, DallasTemperature)        |
| Backend   | Python 3 · Flask · flask-cors · flask-limiter · SQLite            |
| Dashboard | HTML/CSS/JS · Chart.js · jsPDF · SheetJS (Excel export)           |
| Mobile    | Progressive Web App (installable, service-worker cached)          |

---

## Troubleshooting

- **Dashboard says OFFLINE · LOCAL MODE** — the backend isn't reachable, or the API key is missing/wrong. Start `python server.py`, confirm the API URL *and* API key on the **Settings** page, press **Reconnect**. (The dashboard still works standalone using its built-in engine.)
- **401 Unauthorized / "Invalid API key"** — the `X-API-Key` header is missing or doesn't match. Copy the key `server.py` printed on startup (or `cat backend/.api_key`) into the dashboard/mobile Settings page, `simulator.py --api-key`, or the firmware's `API_KEY` constant.
- **429 Too Many Requests** — you've hit a rate limit (see the API table above); this is intentional abuse protection. Wait a minute, or raise the limits in `server.py` if you have a legitimate high-frequency use case.
- **Phone can't connect** — phone and PC must be on the same WiFi; use the PC's LAN IP, not `localhost`; allow Python through the OS firewall (the server listens on `0.0.0.0:5000`).
- **ESP32 POST fails** — same-network check, correct `SERVER_URL` IP, and note the backend is plain HTTP on the LAN.
- **Wrapping the mobile app as an Android APK** — the PWA can be wrapped in a WebView/TWA. Because the backend runs over LAN HTTP, add `android:usesCleartextTraffic="true"` to the `<application>` tag in `AndroidManifest.xml`, or Android will silently block the requests.
- **NPK sensor returns –1 / timeouts** — check MAX485 wiring (DE+RE → GPIO4), A/B lines not swapped, 9600 baud, and verify the Modbus register addresses against your sensor's datasheet.

---

*Academic project. Built as a working prototype of the invention disclosure.*
# Agrowise
