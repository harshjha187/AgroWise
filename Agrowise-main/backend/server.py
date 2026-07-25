"""
AgroWise — REST API Server (Flask + SQLite)
============================================================
IoT-Based Smart Soil Health Analysis, Barren Land Detection
and Automated Recovery Recommendation System

Run:
    pip install -r requirements.txt
    python server.py

Then open:
    Web dashboard : http://localhost:5000/
    Mobile app    : http://<your-pc-ip>:5000/mobile/   (from the phone)

The ESP32 firmware POSTs sensor packets to:
    POST http://<your-pc-ip>:5000/api/readings
    body: {"n": 85, "p": 24, "k": 150, "m": 28, "ph": 6.5, "temp": 27,
           "device_id": "ESP32-01"}   # optional — defaults to "source" if omitted

API reference
-------------
GET    /api/health                        server + database status
POST   /api/readings                      ingest a raw packet -> full analysis
GET    /api/readings?limit=200            reading history (oldest -> newest)
GET    /api/readings?device_id=ESP32-01   ...scoped to one device
GET    /api/readings/latest               latest reading + recommendations
GET    /api/readings/latest?device_id=... ...scoped to one device
GET    /api/devices                       every device_id seen so far
GET    /api/alerts?limit=30               recent alerts (newest first)
GET    /api/summary                       totals, average score, class + moisture counts
GET    /api/export/csv                    download the entire dataset as CSV
DELETE /api/readings                      wipe all stored data
"""

from __future__ import annotations

import csv
import hmac
import io
import logging
import os
import secrets
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException

import analysis_engine as engine
import database as db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [agrowise] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("agrowise")

BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web-dashboard"
MOBILE_DIR = BASE_DIR / "mobile-app"
API_KEY_FILE = BACKEND_DIR / ".api_key"


def _load_or_create_api_key() -> str:
    """Load AGROWISE_API_KEY from the environment, or fall back to a
    per-install secret persisted in .api_key (generated on first run,
    never hardcoded / never committed to source)."""
    env_key = os.environ.get("AGROWISE_API_KEY")
    if env_key:
        return env_key
    if API_KEY_FILE.exists():
        return API_KEY_FILE.read_text().strip()
    key = secrets.token_urlsafe(32)
    API_KEY_FILE.write_text(key)
    try:
        API_KEY_FILE.chmod(0o600)
    except OSError:
        pass
    return key


API_KEY = _load_or_create_api_key()
# Cross-origin access is denied by default (dashboard/mobile app are served
# by this same process, so they never need CORS). Only set this if you open
# the frontend from a different origin against a remote backend.
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("AGROWISE_ALLOWED_ORIGINS", "").split(",") if o.strip()]

app = Flask(__name__)
if ALLOWED_ORIGINS:
    CORS(app, resources={r"/api/*": {"origins": ALLOWED_ORIGINS}})
db.init_db()

# Set only when actually deployed behind a reverse proxy (see deploy/DEPLOY.md).
# Without this, every request behind nginx would appear to come from nginx's
# own IP, silently defeating per-client rate limiting.
if os.environ.get("AGROWISE_BEHIND_PROXY"):
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # type: ignore[method-assign]

# "memory://" (default) matches prior behavior for local/single-process dev.
# Set AGROWISE_RATELIMIT_STORAGE=redis://<host>:6379 for multi-worker
# deployments (see docker-compose.yml) — an in-memory store isn't shared
# across gunicorn workers, so each worker would enforce its own separate
# quota, effectively multiplying the real limit by the worker count.
limiter = Limiter(
    key_func=get_remote_address, app=app, default_limits=["120 per minute"],
    storage_uri=os.environ.get("AGROWISE_RATELIMIT_STORAGE", "memory://"),
)


@app.before_request
def _log_request_start():
    request._agrowise_start = time.monotonic()  # noqa: SLF001


@app.before_request
def _require_api_key():
    if request.method == "OPTIONS" or not request.path.startswith("/api/"):
        return  # static pages + CORS preflight need no key
    supplied = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(supplied, API_KEY):
        return jsonify({"ok": False, "error": "Unauthorized — missing or invalid API key"}), 401


@app.after_request
def _security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@app.after_request
def _log_request_end(resp):
    started = getattr(request, "_agrowise_start", None)
    duration_ms = (time.monotonic() - started) * 1000 if started else -1
    logger.info(
        "%s %s -> %d (%.1fms) from %s",
        request.method, request.path, resp.status_code, duration_ms, request.remote_addr,
    )
    if resp.status_code == 401:
        logger.warning("Unauthorized request: %s %s from %s", request.method, request.path, request.remote_addr)
    elif resp.status_code == 429:
        logger.warning("Rate limit exceeded: %s %s from %s", request.method, request.path, request.remote_addr)
    return resp


@app.errorhandler(Exception)
def _handle_unexpected_error(exc):
    if isinstance(exc, HTTPException):
        return exc  # let Flask's normal 404/405/etc. handling through unchanged
    logger.exception("Unhandled exception during %s %s", request.method, request.path)
    return jsonify({"ok": False, "error": "Internal server error"}), 500


# ==================================================================
# Frontend hosting
# ==================================================================
@app.get("/")
def serve_dashboard():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/mobile")
@app.get("/mobile/")
def serve_mobile_index():
    return send_from_directory(MOBILE_DIR, "index.html")


@app.get("/mobile/<path:filename>")
def serve_mobile_assets(filename: str):
    return send_from_directory(MOBILE_DIR, filename)


# ==================================================================
# API
# ==================================================================
@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "service": "agrowise-backend",
        "version": "2.0-moisture",
        "time": int(datetime.now().timestamp() * 1000),
        "summary": db.get_summary(),
    })


@app.post("/api/readings")
@limiter.limit("40 per minute")
def ingest_reading():
    """Full pipeline: validate -> filter -> score -> classify ->
    recommend -> alert -> store."""
    payload = request.get_json(silent=True) or {}
    raw = {
        "n":  payload.get("n"),
        "p":  payload.get("p"),
        "k":  payload.get("k"),
        # accept "m", "moisture" or "moist"
        "m":  payload.get("m", payload.get("moisture", payload.get("moist"))),
        "ph": payload.get("ph"),
        # accept both "temp" (firmware) and "t"
        "t":  payload.get("temp", payload.get("t")),
    }
    source = str(payload.get("source", "ESP32"))[:16].upper()
    # Defaults to the source label (e.g. "ESP32") when not given, so a
    # single-device setup needs no configuration — multi-device setups set
    # a real device_id (e.g. "ESP32-Field2") to keep their data distinct.
    device_id = str(payload.get("device_id", source))[:32]

    prev = db.get_latest(device_id=device_id)
    result = engine.analyze(
        raw,
        prev_filtered=prev["f"] if prev else None,
        prev_cls=prev["cls"] if prev else None,
        source=source,
        device_id=device_id,
    )
    if not result["ok"]:
        return jsonify({"ok": False, "error": result["error"]}), 400

    reading = result["reading"]
    reading["id"] = db.insert_reading(reading)
    db.insert_alerts(result["alerts"])

    return jsonify({
        "ok": True,
        "reading": reading,
        "recommendations": result["recommendations"],
        "alerts": result["alerts"],
    }), 201


@app.get("/api/readings")
def list_readings():
    limit = max(1, min(1000, request.args.get("limit", default=200, type=int)))
    device_id = request.args.get("device_id")
    return jsonify({"ok": True, "readings": db.get_readings(limit, device_id=device_id)})


@app.get("/api/readings/latest")
def latest_reading():
    device_id = request.args.get("device_id")
    reading = db.get_latest(device_id=device_id)
    if not reading:
        return jsonify({"ok": True, "reading": None, "recommendations": []})
    recos = engine.recommend(reading["f"], reading["subs"], reading["cls"])
    return jsonify({"ok": True, "reading": reading, "recommendations": recos})


@app.get("/api/devices")
def list_devices():
    """Every device_id seen so far, for populating a device filter/selector
    in either frontend."""
    return jsonify({"ok": True, "devices": db.get_distinct_devices()})


@app.get("/api/alerts")
def list_alerts():
    limit = max(1, min(200, request.args.get("limit", default=30, type=int)))
    return jsonify({"ok": True, "alerts": db.get_alerts(limit)})


@app.get("/api/summary")
def summary():
    return jsonify({"ok": True, **db.get_summary()})


@app.delete("/api/readings")
@limiter.limit("5 per minute")
def clear_data():
    db.clear_all()
    return jsonify({"ok": True, "message": "All readings and alerts deleted."})


@app.get("/api/export/csv")
def export_csv():
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "id", "timestamp_iso",
        "N_raw", "P_raw", "K_raw", "moisture_raw", "pH_raw", "temp_raw",
        "N", "P", "K", "moisture_pct", "pH", "temp",
        "score", "classification", "moisture_status", "source", "device_id",
    ])
    for row in db.all_rows_for_export():
        writer.writerow([
            row["id"],
            datetime.fromtimestamp(row["ts"] / 1000).isoformat(sep=" ", timespec="seconds"),
            row["n_raw"], row["p_raw"], row["k_raw"], row["m_raw"], row["ph_raw"], row["t_raw"],
            row["n"], row["p"], row["k"], row["m"], row["ph"], row["t"],
            row["score"], row["cls"], row["m_status"] or "", row["source"], row["device_id"] or "",
        ])
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition":
                 f"attachment; filename=AgroWise_Data_{datetime.now():%Y-%m-%d}.csv"},
    )


# ==================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  AgroWise backend v2 (with moisture)")
    print("  Dashboard : http://localhost:5000/")
    print("  Mobile    : http://<this-pc-ip>:5000/mobile/")
    print("  API       : http://<this-pc-ip>:5000/api/readings")
    print("-" * 60)
    print("  Every /api/* request requires header:  X-API-Key: <key>")
    print(f"  API key: {API_KEY}")
    print("  Enter it in the dashboard/mobile app's Settings page,")
    print("  and in firmware/simulator.py --api-key (or AGROWISE_API_KEY env var).")
    if not ALLOWED_ORIGINS:
        print("  CORS: same-origin only. Set AGROWISE_ALLOWED_ORIGINS=https://foo,https://bar to allow others.")
    print("=" * 60)
    # host 0.0.0.0 -> reachable by the ESP32 and phones on the same WiFi
    app.run(host="0.0.0.0", port=5000, debug=False)
