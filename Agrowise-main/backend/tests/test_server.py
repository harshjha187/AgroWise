"""Route-level tests: auth enforcement, rate limiting, and the ingest pipeline
wired end-to-end through Flask (not just analysis_engine in isolation)."""
from __future__ import annotations

VALID_PACKET = {"n": 85, "p": 24, "k": 150, "m": 28, "ph": 6.5, "temp": 27, "source": "TEST"}


# ---------------------------------------------------------------- static pages
def test_dashboard_served_without_api_key(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"AgroWise" in r.data


def test_mobile_app_served_without_api_key(client):
    r = client.get("/mobile/")
    assert r.status_code == 200


# ---------------------------------------------------------------- auth
def test_api_requires_key(client):
    r = client.get("/api/health")
    assert r.status_code == 401
    assert r.get_json()["ok"] is False


def test_api_rejects_wrong_key(client):
    r = client.get("/api/health", headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401


def test_api_accepts_correct_key(client, auth_headers):
    r = client.get("/api/health", headers=auth_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["service"] == "agrowise-backend"


def test_options_preflight_bypasses_auth(client):
    r = client.options("/api/health")
    assert r.status_code != 401


# ---------------------------------------------------------------- security headers
def test_security_headers_present(client, auth_headers):
    r = client.get("/api/health", headers=auth_headers)
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"


# ---------------------------------------------------------------- ingest pipeline
def test_ingest_valid_packet(client, auth_headers):
    r = client.post("/api/readings", json=VALID_PACKET, headers=auth_headers)
    assert r.status_code == 201
    body = r.get_json()
    assert body["ok"] is True
    assert body["reading"]["cls"] in ("FERTILE", "MODERATE", "BARREN")
    assert "id" in body["reading"]
    assert isinstance(body["recommendations"], list)
    assert isinstance(body["alerts"], list)


def test_ingest_rejects_invalid_packet(client, auth_headers):
    bad = {**VALID_PACKET, "ph": 99}  # outside sensor clamp range
    r = client.post("/api/readings", json=bad, headers=auth_headers)
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_ingest_rejects_missing_field(client, auth_headers):
    bad = {k: v for k, v in VALID_PACKET.items() if k != "n"}
    r = client.post("/api/readings", json=bad, headers=auth_headers)
    assert r.status_code == 400


def test_latest_reading_after_ingest(client, auth_headers):
    client.post("/api/readings", json=VALID_PACKET, headers=auth_headers)
    r = client.get("/api/readings/latest", headers=auth_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["reading"] is not None
    assert body["reading"]["source"] == "TEST"


def test_latest_reading_when_empty(client, auth_headers):
    r = client.get("/api/readings/latest", headers=auth_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["reading"] is None
    assert body["recommendations"] == []


def test_readings_history_respects_limit(client, auth_headers):
    for _ in range(5):
        client.post("/api/readings", json=VALID_PACKET, headers=auth_headers)
    r = client.get("/api/readings?limit=2", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.get_json()["readings"]) == 2


def test_alerts_list(client, auth_headers):
    client.post("/api/readings", json=VALID_PACKET, headers=auth_headers)
    r = client.get("/api/alerts", headers=auth_headers)
    assert r.status_code == 200
    assert "alerts" in r.get_json()


def test_summary_reflects_ingested_data(client, auth_headers):
    client.post("/api/readings", json=VALID_PACKET, headers=auth_headers)
    r = client.get("/api/summary", headers=auth_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["total_readings"] >= 1


def test_csv_export(client, auth_headers):
    client.post("/api/readings", json=VALID_PACKET, headers=auth_headers)
    r = client.get("/api/export/csv", headers=auth_headers)
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert b"N_raw" in r.data  # header row present


# ---------------------------------------------------------------- device_id
def test_device_id_defaults_to_source_when_omitted(client, auth_headers):
    r = client.post("/api/readings", json=VALID_PACKET, headers=auth_headers)
    assert r.get_json()["reading"]["device_id"] == "TEST"  # VALID_PACKET's source


def test_device_id_explicit_value_is_kept(client, auth_headers):
    packet = {**VALID_PACKET, "device_id": "ESP32-Field2"}
    r = client.post("/api/readings", json=packet, headers=auth_headers)
    assert r.get_json()["reading"]["device_id"] == "ESP32-Field2"


def test_devices_endpoint_lists_distinct_ids(client, auth_headers):
    client.post("/api/readings", json={**VALID_PACKET, "device_id": "A"}, headers=auth_headers)
    client.post("/api/readings", json={**VALID_PACKET, "device_id": "B"}, headers=auth_headers)
    client.post("/api/readings", json={**VALID_PACKET, "device_id": "A"}, headers=auth_headers)
    r = client.get("/api/devices", headers=auth_headers)
    assert r.status_code == 200
    assert sorted(r.get_json()["devices"]) == ["A", "B"]


def test_readings_filtered_by_device_id(client, auth_headers):
    client.post("/api/readings", json={**VALID_PACKET, "device_id": "A"}, headers=auth_headers)
    client.post("/api/readings", json={**VALID_PACKET, "device_id": "B"}, headers=auth_headers)
    client.post("/api/readings", json={**VALID_PACKET, "device_id": "A"}, headers=auth_headers)
    r = client.get("/api/readings?device_id=A", headers=auth_headers)
    readings = r.get_json()["readings"]
    assert len(readings) == 2
    assert all(x["device_id"] == "A" for x in readings)


def test_latest_reading_filtered_by_device_id(client, auth_headers):
    client.post("/api/readings", json={**VALID_PACKET, "device_id": "A", "n": 50}, headers=auth_headers)
    client.post("/api/readings", json={**VALID_PACKET, "device_id": "B", "n": 200}, headers=auth_headers)
    r = client.get("/api/readings/latest?device_id=A", headers=auth_headers)
    reading = r.get_json()["reading"]
    assert reading["device_id"] == "A"


def test_ema_filter_is_scoped_per_device_not_blended_across_devices(client, auth_headers):
    """The EMA noise filter blends a new reading with "the previous reading" —
    that must be the same device's previous reading. Post very different N
    values from two devices interleaved; each device's second reading should
    filter against its OWN first reading, not the other device's."""
    client.post("/api/readings", json={**VALID_PACKET, "device_id": "A", "n": 100}, headers=auth_headers)
    client.post("/api/readings", json={**VALID_PACKET, "device_id": "B", "n": 300}, headers=auth_headers)
    rA = client.post("/api/readings", json={**VALID_PACKET, "device_id": "A", "n": 100}, headers=auth_headers)
    # If correctly scoped, device A's filtered N stays near 100 (both its own
    # readings are 100) regardless of device B's very different 300 in between.
    assert abs(rA.get_json()["reading"]["f"]["n"] - 100) < 5


# ---------------------------------------------------------------- delete + rate limit
def test_delete_wipes_data_then_rate_limits_after_five_per_minute(client, auth_headers):
    """Single test covering both behaviors of DELETE /api/readings so the
    5/minute quota (@limiter.limit('5 per minute')) isn't split across test
    functions in a way that makes the count depend on execution order.
    Must run last in this file — it exhausts the bucket for the rest of the
    session (in-memory limiter storage, per rules.md § 2)."""
    client.post("/api/readings", json=VALID_PACKET, headers=auth_headers)
    r = client.delete("/api/readings", headers=auth_headers)
    assert r.status_code == 200
    r2 = client.get("/api/readings/latest", headers=auth_headers)
    assert r2.get_json()["reading"] is None

    # 4 more DELETEs (5 total this test) should still succeed; the 6th call
    # in this same minute must be rejected.
    statuses = [client.delete("/api/readings", headers=auth_headers).status_code for _ in range(5)]
    assert statuses[:4] == [200] * 4
    assert statuses[4] == 429
