"""Direct tests of the SQLite persistence layer, independent of Flask/HTTP."""
from __future__ import annotations

import analysis_engine as engine


def _make_reading(source="TEST"):
    result = engine.analyze(
        {"n": 120, "p": 30, "k": 180, "m": 30, "ph": 6.8, "t": 26}, source=source
    )
    assert result["ok"]
    return result["reading"], result["alerts"]


def test_insert_and_get_latest(app_module):
    import database as db
    reading, alerts = _make_reading()
    reading["id"] = db.insert_reading(reading)
    db.insert_alerts(alerts)

    latest = db.get_latest()
    assert latest is not None
    assert latest["cls"] == reading["cls"]
    assert latest["source"] == "TEST"


def test_get_readings_oldest_first(app_module):
    import database as db
    for i in range(3):
        reading, _ = _make_reading(source=f"SRC{i}")
        db.insert_reading(reading)

    rows = db.get_readings(limit=10)
    assert len(rows) == 3
    # oldest -> newest: sources should appear in insertion order
    assert [r["source"] for r in rows] == ["SRC0", "SRC1", "SRC2"]


def test_clear_all_empties_both_tables(app_module):
    import database as db
    reading, alerts = _make_reading()
    db.insert_reading(reading)
    db.insert_alerts(alerts or [{"ts": 0, "level": "ok", "message": "test"}])

    db.clear_all()
    assert db.get_readings(10) == []
    assert db.get_alerts(10) == []
    assert db.get_latest() is None


def test_get_latest_scoped_to_device_id(app_module):
    import database as db
    reading_a, _ = _make_reading(source="A")
    reading_a["device_id"] = "A"
    db.insert_reading(reading_a)
    reading_b, _ = _make_reading(source="B")
    reading_b["device_id"] = "B"
    db.insert_reading(reading_b)

    assert db.get_latest(device_id="A")["device_id"] == "A"
    assert db.get_latest(device_id="B")["device_id"] == "B"
    assert db.get_latest()["device_id"] == "B"  # most recent overall, unscoped


def test_get_readings_filtered_by_device_id(app_module):
    import database as db
    for dev in ("A", "B", "A"):
        reading, _ = _make_reading(source=dev)
        reading["device_id"] = dev
        db.insert_reading(reading)

    rows = db.get_readings(limit=10, device_id="A")
    assert len(rows) == 2
    assert all(r["device_id"] == "A" for r in rows)


def test_get_distinct_devices(app_module):
    import database as db
    for dev in ("A", "B", "A"):
        reading, _ = _make_reading(source=dev)
        reading["device_id"] = dev
        db.insert_reading(reading)

    assert db.get_distinct_devices() == ["A", "B"]


def test_get_summary_counts_classifications(app_module):
    import database as db
    fertile_reading = engine.analyze(
        {"n": 120, "p": 34, "k": 190, "m": 32, "ph": 6.8, "t": 26}, source="A"
    )["reading"]
    barren_reading = engine.analyze(
        {"n": 22, "p": 6, "k": 48, "m": 8, "ph": 8.4, "t": 39}, source="B"
    )["reading"]

    db.insert_reading(fertile_reading)
    db.insert_reading(barren_reading)

    summary = db.get_summary()
    assert summary["total_readings"] == 2
    assert summary["class_counts"]["FERTILE"] >= 1
    assert summary["class_counts"]["BARREN"] >= 1
    assert summary["avg_score"] is not None
