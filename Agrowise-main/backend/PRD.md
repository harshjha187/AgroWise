# AgroWise — Product Requirements Document

**IoT-Based Smart Soil Health Analysis, Barren Land Detection and Automated Recovery Recommendation System**

Inventors: Harsh Kumar Jha, Hridyanshu Sharma, Ujjawal Dahiya
Status: Working prototype (software complete; hardware integration pending — see [Prototype Status](#prototype-status))

---

## 1. Summary

AgroWise is an end-to-end IoT system that continuously measures six soil parameters — **Nitrogen, Phosphorus, Potassium, Soil Moisture, pH and Temperature** — on a 30-second cycle using an ESP32. Every reading is validated, noise-filtered, scored into a single 0–100 **Soil Health Score**, classified as **FERTILE / MODERATE / BARREN**, and converted into actionable fertilizer, irrigation and soil-treatment recommendations. Data is served over a REST API to a web dashboard and an installable mobile app (PWA).

## 2. Problem Statement

Farmers largely rely on manual soil testing or experience-based decisions, leading to improper crop selection, inefficient fertilizer use, and reduced productivity. Existing IoT soil-monitoring systems only expose **raw parameter values** — they don't fuse multiple parameters into a single decision-usable metric, don't automatically detect barren land, and don't tell the user what to actually *do* about it.

## 3. Goals

- Replace raw sensor dumps with a single, interpretable **Soil Health Score**.
- Automatically detect barren/degraded land using **combined multi-parameter logic**, not just an aggregate score (so nutrient-dead soil can't hide behind good pH/temperature).
- Turn a diagnosis into a **structured, actionable recovery plan** (fertilizer type + dose, irrigation guidance, soil treatment) instead of leaving interpretation to the user.
- Make the system usable **hardware-free** (built-in simulator) for demos, and cheap/scalable enough for small and medium-scale farmers, not just commercial operations.

## 4. Target Users

| Segment | Need |
|---|---|
| **Small/medium-scale farmers** | Low-cost, low-expertise soil health monitoring without lab testing |
| **Commercial/large-scale farms** | Real-time, continuous monitoring across fields for yield optimization |
| **Government / agricultural agencies** | Soil quality assessment and land-mapping at scale for policy planning |
| **Agricultural researchers / educational institutions** | A reference platform for studying soil behavior and IoT-driven decision systems |
| **Agri-tech platforms / precision-agriculture startups** | An integratable scoring + recommendation engine rather than building one from scratch |

## 5. Core Features

### 5.1 Sensing & data pipeline
- ESP32 firmware reads NPK (RS485 Modbus), soil moisture (capacitive analog), pH (analog probe), and temperature (DS18B20) every 30 seconds, and POSTs a JSON packet over WiFi.
- Backend pipeline, run per packet: **Validate → Filter noise (EMA, α=0.45) → Compute weighted 0–100 score → Classify land → Generate recommendations → Generate alerts → Persist.**
- A **hardware-free simulator** (`simulator.py`) posts realistic packets across five named scenarios (fertile / moderate / dry / waterlogged / barren) plus a random-walk "drift" mode, so the whole system can be demoed without any physical sensors.

### 5.2 Soil Health Score & classification
- Each of the 6 parameters gets a 0–100 sub-score (100 inside its optimal band, falling off along a power curve outside it — so severe deficiency is penalized harder than mild deficiency).
- Weighted sum → overall score. **FERTILE ≥ 80 · MODERATE ≥ 50 · else BARREN.**
- **Novelty rule:** if Nitrogen, Phosphorus *and* Potassium sub-scores are all critically low, the land is forced to BARREN regardless of the aggregate score.

### 5.3 Automated recovery recommendations
- Per-parameter deficiency/excess triggers a specific, dosed recommendation: urea for low N, DAP for low P, MOP for low K, irrigation-mm guidance for low moisture, drainage guidance for excess moisture, lime for acidic pH, gypsum for alkaline pH, and an environmental advisory for out-of-range temperature.
- BARREN classification additionally triggers a **4-step structured recovery plan**: compost → green manure cover crop → staged NPK correction → maintenance irrigation, with a 30-day re-test recommendation.

### 5.4 Alerts
- Every analyzed reading can generate alerts (critical/warning/ok) for out-of-range parameters and on any land-classification change (e.g. flips to BARREN).

### 5.5 Web dashboard
- Real-time stat cards, Soil Health Score gauge, land-classification card, full recommendations list, parameter trend chart, and recent-readings table.
- Dedicated pages: **Dashboard, Live Data** (raw vs. filtered readings), **History** (full reading log), **Recommendations**, **Alerts**, **Reports** (summary stats + CSV/PDF/XLSX export), **Settings** (backend URL + API key), **About**.
- Works standalone via a built-in local scoring engine if the backend is unreachable ("local mode" fallback).

### 5.6 Mobile app (PWA)
- Installable (Add to Home Screen), offline-shell via service worker.
- Home (score + recommendations), History (sparkline + log), Add reading (manual entry), Setup (backend URL + API key).

### 5.7 REST API
- `POST /api/readings` (ingest), `GET /api/readings`, `GET /api/readings/latest`, `GET /api/alerts`, `GET /api/summary`, `GET /api/export/csv`, `DELETE /api/readings`, `GET /api/health`.
- SQLite persistence (`readings` + `alerts` tables), auto-migrating schema.

### 5.8 Security
- Every `/api/*` route requires an `X-API-Key` header (auto-generated per install, constant-time compared).
- CORS restricted to same-origin by default (opt-in allowlist via env var).
- Rate limiting per client IP (tighter on the destructive `DELETE`).
- Baseline security response headers on every request.

## 6. Non-Functional Requirements

- **Cost-effective**: target prototype cost ≈ ₹10,000 (per invention disclosure), using commodity sensors and an ESP32.
- **Battery/network-friendly firmware**: all scoring/classification/recommendation logic runs server-side; the firmware only reads sensors and POSTs JSON.
- **Resilience**: dashboard/mobile app degrade gracefully to local-only operation if the backend is unreachable, rather than becoming unusable.
- **Data integrity**: server-side range validation on every ingested parameter; EMA filtering to reduce sensor noise before scoring.

## 7. Out of Scope (current version)

- Actuator control (automated irrigation pump / fertilizer dispenser triggering) — noted in the invention disclosure as an optional future enhancement, not implemented.
- Laboratory-grade soil analysis for highly specialized crops.
- Operation in regions with no power or network connectivity (remote monitoring specifically requires both).
- TLS/HTTPS transport (currently plain HTTP over LAN, matching ESP32 `HTTPClient` constraints — see README **Security** section for the tradeoff and mitigation path).

## 8. Known Limitations

- Sensor accuracy degrades in extreme conditions: highly saline soil, waterlogged ground, highly compacted/rocky terrain.
- Requires periodic sensor calibration (pH two-point calibration, moisture air/water calibration) — accuracy drifts without it.
- A single ESP32 failure or connectivity loss halts data collection for that node; no redundancy/failover across nodes is built in.

## 9. Prototype Status

- **Software**: complete and working — backend (Flask + SQLite), analysis engine, web dashboard, mobile PWA, hardware simulator, and API security are all implemented and tested.
- **Hardware**: firmware (`firmware/AgroWise_ESP32.ino`) is written and ships with `SIMULATE_SENSORS=true` for testing the full chain without wiring sensors; physical NPK/pH/moisture sensor integration and calibration is the remaining step before field deployment.
- Per the invention disclosure: prototype not yet physically built; estimated cost ₹10,000, estimated timeline 2 months.

## 10. Prior Art & Differentiation

The invention disclosure identifies the closest prior art as IoT soil-monitoring systems that expose raw NPK/pH/moisture values (e.g. patents US20190234567A1, US20180123456A1, US20200345678A1, US20210198765A1) without a unified scoring system, automated barren-land detection, or recovery recommendations. AgroWise's differentiation is the **combination** of multi-parameter fusion into one score, combined-threshold barren detection, and a structured, dosed recommendation engine in a single system — not any one piece in isolation.

## 11. References

Full literature review and prior-art citations are maintained in the original invention disclosure form (CBS-CGC IPR submission); see that document for the complete bibliography.
