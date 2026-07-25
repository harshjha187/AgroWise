# AgroWise — Project Phases

A phase-by-phase breakdown of building AgroWise from invention disclosure to field-ready prototype. Companion to [PRD.md](PRD.md) (what & why), [ARCHITECTURE.md](ARCHITECTURE.md) (how it's built), and [rules.md](rules.md) (guardrails per area). Status reflects the actual current repository state, not aspiration.

Per the invention disclosure (§9): prototype not yet physically built, estimated cost ₹10,000, estimated timeline 2 months. The phases below map that estimate onto concrete engineering work — Phases 0–4 (software) are complete; Phases 5–8 (hardware → field validation) are the remaining ~2-month path.

---

## Phase 0 — Research & Problem Definition ✅ Complete

**Goal:** Establish the problem, prior art, and novelty before writing any code.

- Literature review of existing IoT soil-monitoring systems and their limitations (raw-data-only, no unified scoring, no barren detection, no recovery guidance) — invention disclosure §4.
- Identified the combined-threshold barren-detection rule and structured recovery engine as the specific novelty to build around — invention disclosure §3.1.
- Defined target users and market segments — PRD §4.

**Output:** Invention disclosure form (CBS-CGC IPR submission).

---

## Phase 1 — Backend Foundation ✅ Complete

**Goal:** A working analysis pipeline and persistence layer, independent of any UI or hardware.

- `analysis_engine.py` — validate → EMA filter → weighted score → classify → recommend → alert, with its own self-test suite.
- `database.py` — SQLite schema (`readings`, `alerts`), auto-migration for older schemas, CRUD functions.
- `server.py` — Flask app wiring the two together behind a REST API (`/api/readings`, `/api/readings/latest`, `/api/alerts`, `/api/summary`, `/api/export/csv`, `/api/health`).

**Output:** A backend that can ingest a sensor packet and return a full scored, classified, recommended, alerted result — testable via `curl` with zero hardware.

---

## Phase 2 — Hardware-Free Demo Path ✅ Complete

**Goal:** Make the whole system demonstrable before any physical sensor exists.

- `simulator.py` — posts realistic packets across five named scenarios (fertile / moderate / dry / waterlogged / barren) plus a random-walk "drift" mode.
- `firmware/AgroWise_ESP32.ino` written with `SIMULATE_SENSORS = true` so the full WiFi → backend chain can be tested on real ESP32 hardware without any sensors wired up yet.

**Output:** Anyone can run `python server.py` + `python simulator.py` and see the entire pipeline working end to end, matching the PRD goal of "runnable in 5 minutes, no hardware needed."

---

## Phase 3 — Frontend Development ✅ Complete

**Goal:** Human-usable interfaces over the REST API.

- **Web dashboard** (`web-dashboard/index.html`) — stat cards, Soil Health Score gauge, classification card, recommendations, trend chart, reading history, CSV/PDF/XLSX export, offline local-mode fallback engine.
- **Mobile app** (`mobile-app/index.html` + manifest + service worker) — installable PWA with Home / History / Add / Setup pages.
- Both built as single self-contained HTML files with no build step, per the project's zero-tooling constraint (ARCHITECTURE §8).
- Later iteration: full multi-page navigation for the dashboard (Dashboard / Live Data / History / Recommendations / Alerts / Reports / Settings / About), each backed by real content instead of decorative nav.
- Later iteration: mouse-tracked 3D tilt system + press animations across both apps' interactive elements.

**Output:** A dashboard and mobile app that both talk to the live backend and degrade gracefully to local-only mode if it's unreachable.

---

## Phase 4 — Security Hardening ✅ Complete

**Goal:** Prevent unauthorized read/write access and abuse of the API.

- `X-API-Key` requirement on every `/api/*` route, auto-generated per install, `hmac.compare_digest` comparison.
- CORS locked to same-origin by default (`AGROWISE_ALLOWED_ORIGINS` opt-in for cross-origin).
- Rate limiting (flask-limiter): 120/min default, 40/min ingest, 5/min on the destructive `DELETE`.
- Baseline security response headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`).
- Key threaded through every caller: firmware `API_KEY` constant, `simulator.py --api-key`, both frontends' Settings/Setup pages.

**Output:** No endpoint reachable or destructible without the shared secret; documented in README § Security and enforced by rules.md § 2.

---

## Phase 5 — Documentation ✅ Complete

**Goal:** Make the project's requirements, architecture, and constraints legible to anyone picking it up.

- `README.md` — setup, run instructions, full API reference, troubleshooting.
- `PRD.md` — problem, goals, target users, features, non-functional requirements, known limitations, prototype status.
- `ARCHITECTURE.md` — app flow, component architecture, security layering, data model, folder structure, tech stack, key decisions.
- `rules.md` — do/avoid guardrails per area, tied back to specific novelty claims and past decisions.

**Output:** This set of five documents (including this one).

---

## Phase 6 — Hardware Procurement & Assembly ⏳ Pending

**Goal:** Physical components in hand and wired per the firmware's pin-out.

- Procure: ESP32 dev board, JXCT-style RS485 NPK sensor + MAX485 transceiver, capacitive soil moisture probe, analog pH probe, DS18B20 temperature sensor, status LED, power supply.
- Wire per `firmware/AgroWise_ESP32.ino`'s documented pin-out (RS485 on GPIO16/17/4, moisture on GPIO35, pH on GPIO34, DS18B20 on GPIO5).
- Estimated cost: ₹10,000 (invention disclosure §9.2).

**Blocked on:** none — can start immediately; independent of Phases 0–5.

---

## Phase 7 — Firmware Integration & Calibration ⏳ Pending

**Goal:** Real sensor data flowing into the already-working backend, replacing simulated data.

- Flip `SIMULATE_SENSORS` to `false` in the firmware.
- Two-point pH calibration (`PH_NEUTRAL_VOLTAGE`, `PH_VOLTS_PER_PH` against pH 4.0/7.0 buffers).
- Moisture calibration (`MOIST_AIR_ADC`, `MOIST_WATER_ADC` — dry air vs. submerged readings).
- Verify NPK sensor Modbus register addresses against the specific sensor's datasheet (the shipped frame addresses are JXCT-typical defaults, not guaranteed universal).
- Set real `WIFI_SSID`/`WIFI_PASS`/`SERVER_URL`/`API_KEY` and confirm end-to-end delivery against the live backend (not the simulator).

**Blocked on:** Phase 6 (hardware must be assembled first).

**Known risk (per invention disclosure §7.2):** sensor degradation, miscalibration, or extreme soil conditions (high salinity, waterlogging, compacted/rocky terrain) can produce unreliable readings — validate against a known-reference soil sample before trusting field data.

---

## Phase 8 — Field Testing & Validation ⏳ Pending

**Goal:** Confirm the system behaves correctly outside a controlled bench setup.

- Deploy in a real field/plot; run the 30-second read cycle over an extended period (days, not minutes) to catch drift, connectivity drop-outs, and power issues the bench setup won't surface.
- Cross-check AgroWise's Soil Health Score and classification against a lab soil test on the same sample, to validate the scoring model isn't just internally consistent but externally accurate.
- Confirm recommendation doses are agronomically reasonable for the actual crop/soil type in the test plot — the invention disclosure explicitly flags dosages as indicative pending validation with a local KVK/soil-testing laboratory.
- Stress-test the offline/local-mode fallback and the WiFi reconnect behavior under real network conditions (not localhost).

**Blocked on:** Phase 7 (needs real calibrated sensor data to validate against).

**Output:** A field-validated prototype ready to demonstrate as a complete invention, closing out the "Prototype ready: No" status from the invention disclosure.

---

## Status Summary

| Phase | Area | Status |
|---|---|---|
| 0 | Research & problem definition | ✅ Complete |
| 1 | Backend foundation | ✅ Complete |
| 2 | Hardware-free demo path | ✅ Complete |
| 3 | Frontend development | ✅ Complete |
| 4 | Security hardening | ✅ Complete |
| 5 | Documentation | ✅ Complete |
| 6 | Hardware procurement & assembly | ⏳ Pending |
| 7 | Firmware integration & calibration | ⏳ Pending |
| 8 | Field testing & validation | ⏳ Pending |

Everything software-side (Phases 0–5) is done and testable today with zero hardware, per Phase 2's design goal. What remains (Phases 6–8) is entirely physical: buy parts, wire and calibrate them, and validate in a real field — the ~2-month estimate from the invention disclosure.
