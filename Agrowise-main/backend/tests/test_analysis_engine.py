"""pytest-style coverage for analysis_engine.py so `pytest` alone covers the
whole backend. analysis_engine.py also has its own `if __name__` self-test
(run via `python analysis_engine.py`) — keep both; they check the same
invariants from two different harnesses, which is intentional per rules.md."""
from __future__ import annotations

import analysis_engine as engine


def test_weights_sum_to_one():
    assert abs(sum(p["w"] for p in engine.PARAMS.values()) - 1.0) < 0.001


def test_validate_rejects_non_numeric():
    ok, _ = engine.validate({"n": "abc", "p": 1, "k": 1, "m": 25, "ph": 6, "t": 20})
    assert ok is False


def test_validate_rejects_out_of_sensor_range():
    ok, _ = engine.validate({"n": 50, "p": 20, "k": 120, "m": 25, "ph": 16, "t": 20})
    assert ok is False


def test_validate_accepts_valid_packet():
    ok, _ = engine.validate({"n": 50, "p": 20, "k": 120, "m": 25, "ph": 6, "t": 20})
    assert ok is True


def test_fertile_classification():
    subs, score = engine.compute_score({"n": 120, "p": 34, "k": 190, "m": 32, "ph": 6.8, "t": 26})
    assert score >= 80
    assert engine.classify(score, subs) == "FERTILE"


def test_barren_by_low_score():
    subs, score = engine.compute_score({"n": 22, "p": 6, "k": 48, "m": 8, "ph": 8.4, "t": 39})
    assert score < 50
    assert engine.classify(score, subs) == "BARREN"


def test_combined_npk_low_forces_barren_even_at_decent_score():
    """The invention's core novelty: N+P+K all critically low overrides the
    aggregate score. Must never be diluted into the weighted average."""
    subs, score = engine.compute_score({"n": 20, "p": 5, "k": 40, "m": 30, "ph": 6.8, "t": 25})
    assert engine.classify(score, subs) == "BARREN"


def test_moisture_status_thresholds():
    assert engine.moisture_status(10) == "LOW"
    assert engine.moisture_status(30) == "OPTIMAL"
    assert engine.moisture_status(60) == "HIGH"


def test_recommend_fires_all_categories_for_stressed_soil():
    low = {"n": 30, "p": 8, "k": 60, "m": 12, "ph": 5.0, "t": 40}
    subs, score = engine.compute_score(low)
    titles = " | ".join(r["title"] for r in engine.recommend(low, subs, "BARREN"))
    assert "Nitrogen" in titles
    assert "Phosphorus" in titles
    assert "Potassium" in titles
    assert "irrigation recommended" in titles
    assert "Acidic" in titles
    assert "recovery plan" in titles


def test_full_pipeline_end_to_end():
    result = engine.analyze({"n": 120, "p": 30, "k": 180, "m": 30, "ph": 6.8, "t": 26}, source="test")
    assert result["ok"] is True
    assert result["reading"]["cls"] == "FERTILE"
    assert result["reading"]["moisture_status"] == "OPTIMAL"


def test_analyze_device_id_defaults_and_passthrough():
    default_result = engine.analyze({"n": 120, "p": 30, "k": 180, "m": 30, "ph": 6.8, "t": 26})
    assert default_result["reading"]["device_id"] == "default"

    tagged_result = engine.analyze(
        {"n": 120, "p": 30, "k": 180, "m": 30, "ph": 6.8, "t": 26}, device_id="ESP32-Field2"
    )
    assert tagged_result["reading"]["device_id"] == "ESP32-Field2"


def test_full_pipeline_rejects_invalid_input():
    result = engine.analyze({"n": "bad", "p": 30, "k": 180, "m": 30, "ph": 6.8, "t": 26})
    assert result["ok"] is False
    assert "error" in result
