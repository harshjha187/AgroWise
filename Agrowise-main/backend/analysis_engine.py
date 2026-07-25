"""
AgroWise — Analysis Engine (v2, with Soil Moisture)
============================================================
IoT-Based Smart Soil Health Analysis, Barren Land Detection
and Automated Recovery Recommendation System

Implements the updated ESP32 pseudocode pipeline:

    Read (N, P, K, Moisture, pH, Temp) -> Validate ->
    Filter Noise -> Calculate Weighted Soil Health Score ->
    Classify (FERTILE >= 80, MODERATE >= 50, else BARREN) ->
    Analyze Moisture / NPK / pH -> Generate Fertilizer +
    Irrigation + Soil Treatment recommendations ->
    Barren Recovery Plan -> Alerts.
"""

from __future__ import annotations

import time
from typing import Optional

# ------------------------------------------------------------------
# Agronomic configuration
#   min/max  : sub-score falls to 0 at these bounds
#   lo/hi    : optimal band (sub-score = 100 inside it)
#   clamp    : physical sensor range — outside it the packet is invalid
#   w        : weight in the overall Soil Health Score (must sum to 1.0)
# ------------------------------------------------------------------
PARAMS: dict[str, dict] = {
    "n":  {"label": "Nitrogen",     "unit": "mg/kg", "min": 0.0,  "lo": 80.0,  "hi": 160.0, "max": 320.0, "clamp": (0.0, 1999.0), "w": 0.15, "dp": 1},
    "p":  {"label": "Phosphorus",   "unit": "mg/kg", "min": 0.0,  "lo": 20.0,  "hi": 50.0,  "max": 140.0, "clamp": (0.0, 1999.0), "w": 0.15, "dp": 1},
    "k":  {"label": "Potassium",    "unit": "mg/kg", "min": 0.0,  "lo": 110.0, "hi": 250.0, "max": 500.0, "clamp": (0.0, 1999.0), "w": 0.15, "dp": 1},
    "m":  {"label": "Soil Moisture","unit": "%",     "min": 0.0,  "lo": 20.0,  "hi": 45.0,  "max": 75.0,  "clamp": (0.0, 100.0),  "w": 0.20, "dp": 1},
    "ph": {"label": "Soil pH",      "unit": "",      "min": 3.5,  "lo": 6.0,   "hi": 7.5,   "max": 9.5,   "clamp": (0.0, 14.0),   "w": 0.20, "dp": 2},
    "t":  {"label": "Temperature",  "unit": "°C",    "min": 2.0,  "lo": 18.0,  "hi": 32.0,  "max": 48.0,  "clamp": (-10.0, 60.0), "w": 0.15, "dp": 1},
}
KEYS = ("n", "p", "k", "m", "ph", "t")

EMA_ALPHA = 0.45           # weight of the newest sample in the noise filter
RAMP_POWER = 1.6           # deficiency/excess penalized progressively harder
CLASS_FERTILE = 80         # score >= 80  -> FERTILE  (updated pseudocode)
CLASS_MODERATE = 50        # score >= 50  -> MODERATE (updated pseudocode)
COMBINED_BARREN_SUB = 35   # if N, P and K sub-scores are ALL below this -> BARREN


# ------------------------------------------------------------------
# Pipeline step 1 — Validate Sensor Data
# ------------------------------------------------------------------
def validate(raw: dict) -> tuple[bool, dict | str]:
    """Return (True, clean_values) or (False, reason)."""
    clean = {}
    for key in KEYS:
        value = raw.get(key)
        try:
            value = float(value)
        except (TypeError, ValueError):
            return False, f"{PARAMS[key]['label']} is missing / not a number"
        lo, hi = PARAMS[key]["clamp"]
        if not (lo <= value <= hi):
            return False, f"{PARAMS[key]['label']} out of sensor range ({value})"
        clean[key] = value
    return True, clean


# ------------------------------------------------------------------
# Pipeline step 2 — Filter Noise (exponential moving average)
# ------------------------------------------------------------------
def filter_noise(raw: dict, prev_filtered: Optional[dict]) -> dict:
    if not prev_filtered:
        return {k: round(raw[k], 2) for k in KEYS}
    return {
        k: round(EMA_ALPHA * raw[k] + (1.0 - EMA_ALPHA) * prev_filtered[k], 2)
        for k in KEYS
    }


# ------------------------------------------------------------------
# Pipeline step 3 — Calculate Soil Health Score
# ------------------------------------------------------------------
def sub_score(key: str, value: float) -> int:
    """0-100 per-parameter score with a power-curve ramp outside the
    optimal band, so severe deficiency/excess is penalized harder."""
    c = PARAMS[key]
    if value <= c["min"] or value >= c["max"]:
        return 0
    if c["lo"] <= value <= c["hi"]:
        return 100
    if value < c["lo"]:
        frac = (value - c["min"]) / (c["lo"] - c["min"])
    else:
        frac = (c["max"] - value) / (c["max"] - c["hi"])
    return round((frac ** RAMP_POWER) * 100)


def compute_score(filtered: dict) -> tuple[dict, int]:
    subs = {k: sub_score(k, filtered[k]) for k in KEYS}
    score = round(sum(subs[k] * PARAMS[k]["w"] for k in KEYS))
    return subs, score


# ------------------------------------------------------------------
# Pipeline step 4 — Classify Land
# ------------------------------------------------------------------
def classify(score: int, subs: dict) -> str:
    # Novelty from the invention disclosure: combined multi-parameter
    # barren detection — if all three nutrients are critically low the
    # land is barren regardless of the aggregate score.
    if all(subs[k] < COMBINED_BARREN_SUB for k in ("n", "p", "k")):
        return "BARREN"
    if score >= CLASS_FERTILE:
        return "FERTILE"
    if score >= CLASS_MODERATE:
        return "MODERATE"
    return "BARREN"


def status_of(key: str, value: float) -> str:
    c = PARAMS[key]
    if value < c["lo"]:
        return "LOW"
    if value > c["hi"]:
        return "HIGH"
    return "OK"


def moisture_status(m: float) -> str:
    """Per the pseudocode: LOW / OPTIMAL / HIGH."""
    if m < PARAMS["m"]["lo"]:
        return "LOW"
    if m > PARAMS["m"]["hi"]:
        return "HIGH"
    return "OPTIMAL"


# ------------------------------------------------------------------
# Pipeline step 5 — Generate Recovery Recommendations
# ------------------------------------------------------------------
def recommend(f: dict, subs: dict, cls: str) -> list[dict]:
    recos: list[dict] = []
    sev = lambda k: "critical" if subs[k] < 35 else "warning"

    # ---- Nutrients (fertilizer recommendations) ----
    if f["n"] < PARAMS["n"]["lo"]:
        dose = min(110, max(25, round((PARAMS["n"]["hi"] - f["n"]) / PARAMS["n"]["hi"] * 110)))
        recos.append({
            "severity": sev("n"), "title": "Nitrogen deficiency",
            "dose": f"Urea (46-0-0) ≈ {dose} kg/acre, in 2 split doses",
            "body": ("Available nitrogen is below the optimal band. Apply nitrogen "
                     "fertilizer; splitting the dose (basal + top dressing) reduces "
                     "leaching losses."),
        })
    if f["p"] < PARAMS["p"]["lo"]:
        dose = min(75, max(20, round((PARAMS["p"]["hi"] - f["p"]) / PARAMS["p"]["hi"] * 75)))
        recos.append({
            "severity": sev("p"), "title": "Phosphorus deficiency",
            "dose": f"DAP (18-46-0) ≈ {dose} kg/acre at sowing",
            "body": ("Phosphorus supports root development and flowering. Apply DAP "
                     "or SSP near the root zone at sowing for best uptake."),
        })
    if f["k"] < PARAMS["k"]["lo"]:
        dose = min(60, max(15, round((PARAMS["k"]["hi"] - f["k"]) / PARAMS["k"]["hi"] * 60)))
        recos.append({
            "severity": sev("k"), "title": "Potassium deficiency",
            "dose": f"MOP (0-0-60) ≈ {dose} kg/acre",
            "body": ("Low potassium weakens stress tolerance and grain filling. Apply "
                     "muriate of potash and incorporate into moist soil."),
        })

    # ---- Moisture (irrigation recommendations) ----
    m_status = moisture_status(f["m"])
    if m_status == "LOW":
        # dose scales with how far below optimal
        deficit = max(0, PARAMS["m"]["lo"] - f["m"])
        mm = round(20 + deficit * 1.5)
        recos.append({
            "severity": "critical" if f["m"] < 10 else "warning",
            "title": "Soil moisture low — irrigation recommended",
            "dose": f"Irrigate ≈ {mm} mm/acre; target 25–35 % VWC after wetting",
            "body": ("Soil moisture is below the safe root-zone threshold. Irrigate "
                     "in the early morning or evening to reduce evaporation losses "
                     "and re-check moisture 6–8 hours after wetting."),
        })
    elif m_status == "HIGH":
        recos.append({
            "severity": "warning",
            "title": "Excess soil moisture — reduce irrigation",
            "dose": "Halt irrigation for 3–5 days; inspect drainage",
            "body": ("Soil moisture is above the safe range — over-watering starves "
                     "roots of oxygen and promotes fungal disease. Improve drainage, "
                     "add organic matter, and delay the next irrigation cycle."),
        })

    # ---- pH (soil treatment recommendations) ----
    if f["ph"] < PARAMS["ph"]["lo"]:
        dose = round(150 + (PARAMS["ph"]["lo"] - f["ph"]) * 180)
        recos.append({
            "severity": "critical" if f["ph"] < 5.2 else "warning",
            "title": "Acidic soil — pH below ideal range",
            "dose": f"Agricultural lime ≈ {dose} kg/acre, re-test after 3–4 weeks",
            "body": ("Acidity locks nutrients and harms microbes. Broadcast lime evenly "
                     "and mix into the topsoil; avoid applying with nitrogen fertilizer "
                     "on the same day."),
        })
    if f["ph"] > PARAMS["ph"]["hi"]:
        dose = round(120 + (f["ph"] - PARAMS["ph"]["hi"]) * 160)
        recos.append({
            "severity": "critical" if f["ph"] > 8.6 else "warning",
            "title": "Alkaline soil — pH above ideal range",
            "dose": f"Gypsum ≈ {dose} kg/acre + organic compost",
            "body": ("Alkaline/sodic conditions reduce micronutrient availability. Apply "
                     "gypsum, add organic matter, and irrigate to leach salts."),
        })

    # ---- Temperature (environmental advisory) ----
    if f["t"] < PARAMS["t"]["lo"] or f["t"] > PARAMS["t"]["hi"]:
        hot = f["t"] > PARAMS["t"]["hi"]
        recos.append({
            "severity": "info",
            "title": "Environmental warning — soil temperature outside ideal range",
            "dose": ("Mulch the surface & irrigate early morning / evening" if hot
                     else "Delay sowing until soil warms; use raised beds"),
            "body": (f"Soil temperature is {f['t']:.1f} °C (ideal 18–32 °C). Extreme "
                     "temperature slows germination and microbial activity."),
        })

    # ---- BARREN structured recovery plan ----
    if cls == "BARREN":
        recos.append({
            "severity": "critical",
            "title": "Barren land detected — structured recovery plan",
            "dose": "Re-test soil after 30 days of treatment",
            "body": ("1) Add farmyard compost ≈ 2 t/acre and mix well. "
                     "2) Grow a green-manure crop (dhaincha / sunhemp) for 40–45 days "
                     "and plough it in. 3) Apply the staged NPK corrections above. "
                     "4) Maintain steady soil moisture (25–35 % VWC) with light "
                     "irrigation every 5–7 days to activate soil biology."),
        })

    if not recos:
        recos.append({
            "severity": "good",
            "title": "Soil parameters within optimal range",
            "dose": "Maintain current practices",
            "body": ("No corrective action required. Continue periodic monitoring; "
                     "re-check after the next irrigation or rainfall event."),
        })
    return recos


# ------------------------------------------------------------------
# Pipeline step 6 — Display Alerts
# ------------------------------------------------------------------
def build_alerts(f: dict, subs: dict, cls: str, prev_cls: Optional[str]) -> list[dict]:
    ts = int(time.time() * 1000)
    alerts: list[dict] = []
    add = lambda level, msg: alerts.append({"ts": ts, "level": level, "message": msg})

    for key in ("n", "p", "k"):
        if status_of(key, f[key]) == "LOW":
            level = "critical" if subs[key] < 35 else "warning"
            add(level, f"Low {PARAMS[key]['label']} — {f[key]:.1f} mg/kg "
                       f"(optimal {PARAMS[key]['lo']:.0f}–{PARAMS[key]['hi']:.0f})")
    m_status = moisture_status(f["m"])
    if m_status == "LOW":
        add("critical" if f["m"] < 10 else "warning",
            f"Low soil moisture {f['m']:.1f} % — irrigation recommended")
    elif m_status == "HIGH":
        add("warning", f"High soil moisture {f['m']:.1f} % — reduce irrigation, check drainage")
    if f["ph"] < PARAMS["ph"]["lo"]:
        add("warning", f"Acidic soil — pH {f['ph']:.2f} (lime recommended)")
    if f["ph"] > PARAMS["ph"]["hi"]:
        add("warning", f"Alkaline soil — pH {f['ph']:.2f} (gypsum recommended)")
    if f["t"] > PARAMS["t"]["hi"]:
        add("warning", f"High soil temperature {f['t']:.1f} °C")
    if f["t"] < PARAMS["t"]["lo"]:
        add("warning", f"Low soil temperature {f['t']:.1f} °C")
    if cls != prev_cls:
        level = "critical" if cls == "BARREN" else "ok" if cls == "FERTILE" else "warning"
        add(level, f"Land classified {cls}")
    return alerts


# ------------------------------------------------------------------
# Full pipeline entry point
# ------------------------------------------------------------------
def analyze(raw: dict, prev_filtered: Optional[dict] = None,
            prev_cls: Optional[str] = None, source: str = "unknown",
            device_id: str = "default") -> dict:
    """Run one packet through the entire pipeline.

    Returns {"ok": False, "error": ...} for invalid packets, otherwise a
    complete analyzed reading with recommendations and alerts.
    """
    ok, result = validate(raw)
    if not ok:
        return {"ok": False, "error": result}

    clean = result
    filtered = filter_noise(clean, prev_filtered)
    subs, score = compute_score(filtered)
    cls = classify(score, subs)

    return {
        "ok": True,
        "reading": {
            "ts": int(time.time() * 1000),
            "raw": {k: round(clean[k], 2) for k in KEYS},
            "f": filtered,
            "subs": subs,
            "score": score,
            "cls": cls,
            "moisture_status": moisture_status(filtered["m"]),
            "source": source,
            "device_id": device_id,
        },
        "recommendations": recommend(filtered, subs, cls),
        "alerts": build_alerts(filtered, subs, cls, prev_cls),
    }


# ------------------------------------------------------------------
# Self-test:  python analysis_engine.py
# ------------------------------------------------------------------
if __name__ == "__main__":
    # verify weights sum to 1.0
    total_w = sum(p["w"] for p in PARAMS.values())
    assert abs(total_w - 1.0) < 0.001, f"weights sum to {total_w}, not 1.0"
    print(f"ok  - parameter weights sum to 1.0 (6 params)")

    checks = 1

    def expect(cond: bool, msg: str):
        global checks
        assert cond, "FAIL: " + msg
        checks += 1
        print("ok  -", msg)

    ok, _ = validate({"n": "abc", "p": 1, "k": 1, "m": 25, "ph": 6, "t": 20})
    expect(ok is False, "rejects non-numeric input")
    ok, _ = validate({"n": 50, "p": 20, "k": 120, "m": 25, "ph": 16, "t": 20})
    expect(ok is False, "rejects pH outside sensor range")
    ok, _ = validate({"n": 50, "p": 20, "k": 120, "m": 150, "ph": 6, "t": 20})
    expect(ok is False, "rejects moisture > 100 %")
    ok, _ = validate({"n": 50, "p": 20, "k": 120, "m": 25, "ph": 6, "t": 20})
    expect(ok, "accepts fully valid packet incl. moisture")

    # Fertile
    subs, score = compute_score({"n": 120, "p": 34, "k": 190, "m": 32, "ph": 6.8, "t": 26})
    expect(score >= 80 and classify(score, subs) == "FERTILE",
           f"fertile field -> FERTILE with new 80 threshold ({score})")

    # Barren by score
    subs, score = compute_score({"n": 22, "p": 6, "k": 48, "m": 8, "ph": 8.4, "t": 39})
    expect(score < 50 and classify(score, subs) == "BARREN",
           f"degraded land -> BARREN ({score})")

    # Moderate mid-range
    subs, score = compute_score({"n": 48, "p": 11, "k": 85, "m": 15, "ph": 5.5, "t": 33.5})
    expect(50 <= score < 80 and classify(score, subs) == "MODERATE",
           f"mid-range field -> MODERATE with new 50-80 band ({score})")

    # Combined-NPK-low rule overrides otherwise-decent score
    subs, score = compute_score({"n": 20, "p": 5, "k": 40, "m": 30, "ph": 6.8, "t": 25})
    expect(classify(score, subs) == "BARREN",
           f"combined NPK-low rule forces BARREN even at score {score}")

    # EMA filter
    f = filter_noise({"n": 140, "p": 30, "k": 200, "m": 30, "ph": 6.5, "t": 25},
                     {"n": 100, "p": 30, "k": 200, "m": 20, "ph": 6.5, "t": 25})
    expect(abs(f["n"] - (0.45 * 140 + 0.55 * 100)) < 0.01, f"EMA filter blends N ({f['n']})")
    expect(abs(f["m"] - (0.45 * 30 + 0.55 * 20)) < 0.01, f"EMA filter blends moisture ({f['m']})")

    # Moisture status
    expect(moisture_status(10) == "LOW",     "moisture 10% -> LOW")
    expect(moisture_status(30) == "OPTIMAL", "moisture 30% -> OPTIMAL")
    expect(moisture_status(60) == "HIGH",    "moisture 60% -> HIGH")

    # Recommendations fire in all categories
    low = {"n": 30, "p": 8, "k": 60, "m": 12, "ph": 5.0, "t": 40}
    subs, score = compute_score(low)
    titles = " | ".join(r["title"] for r in recommend(low, subs, "BARREN"))
    expect("Nitrogen" in titles, "nitrogen fertilizer recommendation")
    expect("Phosphorus" in titles, "phosphorus fertilizer recommendation")
    expect("Potassium" in titles, "potassium fertilizer recommendation")
    expect("irrigation recommended" in titles, "irrigation recommendation for low moisture")
    expect("Acidic" in titles, "lime recommendation for acidic pH")
    expect("Environmental" in titles, "temperature environmental warning")
    expect("recovery plan" in titles, "BARREN -> structured recovery plan")

    # High moisture reco
    high_m = {"n": 100, "p": 30, "k": 180, "m": 65, "ph": 6.8, "t": 25}
    subs, score = compute_score(high_m)
    titles = " | ".join(r["title"] for r in recommend(high_m, subs, "MODERATE"))
    expect("Excess soil moisture" in titles, "excess moisture -> reduce irrigation reco")

    # Full pipeline
    result = analyze({"n": 120, "p": 30, "k": 180, "m": 30, "ph": 6.8, "t": 26}, source="test")
    expect(result["ok"] and result["reading"]["cls"] == "FERTILE",
           "full analyze() pipeline works with 6 params")
    expect(result["reading"]["moisture_status"] == "OPTIMAL",
           "moisture_status attached to reading")

    print(f"\nALL {checks} ENGINE TESTS PASSED")
