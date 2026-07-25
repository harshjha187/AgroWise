"""
AgroWise — ESP32 Hardware Simulator
============================================================
Posts realistic sensor packets (now including soil moisture)
to the backend exactly like the real ESP32 firmware does, so
the entire system can be demoed without any hardware.

Examples:
    python simulator.py
    python simulator.py --scenario barren --interval 3
    python simulator.py --scenario waterlogged --count 5
    python simulator.py --scenario drift --count 50 --server http://192.168.1.5:5000
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
import urllib.error
import urllib.request

# key: (center, jitter) per parameter — includes moisture (m, % VWC)
# calibrated for the updated 80/50 classification thresholds
SCENARIOS = {
    "fertile":     {"n": (122, 18), "p": (34, 6),  "k": (190, 26), "m": (32, 4.5), "ph": (6.8, 0.22), "temp": (26, 2.4)},
    "moderate":    {"n": (55, 10),  "p": (14, 3),  "k": (95, 15),  "m": (18, 3.5), "ph": (5.7, 0.25), "temp": (33.5, 2.5)},
    "dry":         {"n": (95, 12),  "p": (26, 4),  "k": (160, 18), "m": (10, 2.5), "ph": (6.6, 0.2),  "temp": (34, 2.4)},
    "waterlogged": {"n": (110, 14), "p": (30, 5),  "k": (170, 20), "m": (62, 4.5), "ph": (6.4, 0.25), "temp": (24, 2)},
    "barren":      {"n": (22, 8),   "p": (6, 2.4), "k": (48, 13),  "m": (8, 3),    "ph": (8.4, 0.3),  "temp": (39, 3.2)},
}

BOUNDS = {
    "n":    (1, 400),
    "p":    (1, 160),
    "k":    (2, 600),
    "m":    (0, 95),          # % VWC (0-100 clamp)
    "ph":   (3.8, 9.6),
    "temp": (5, 48),
}


def jitter(amp: float) -> float:
    """Roughly gaussian noise in [-amp, amp]."""
    return (random.random() + random.random() + random.random() - 1.5) / 1.5 * amp


def make_packet(scenario: str, drift_state: dict) -> dict:
    if scenario == "drift":
        step = {"n": 9, "p": 2.4, "k": 11, "m": 3, "ph": 0.14, "temp": 1.1}
        packet = {}
        for key, (lo, hi) in BOUNDS.items():
            value = drift_state[key] + jitter(step[key])
            packet[key] = round(min(hi, max(lo, value)), 2)
        drift_state.update(packet)
        return packet
    spec = SCENARIOS[scenario]
    return {
        key: round(max(BOUNDS[key][0], min(BOUNDS[key][1], center + jitter(amp))), 2)
        for key, (center, amp) in spec.items()
    }


def post_packet(server: str, packet: dict, api_key: str, device_id: str = "") -> tuple[int, dict]:
    body_dict = {**packet, "source": "SIM"}
    if device_id:
        body_dict["device_id"] = device_id
    body = json.dumps(body_dict).encode()
    req = urllib.request.Request(
        server.rstrip("/") + "/api/readings",
        data=body,
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode())


def main() -> None:
    parser = argparse.ArgumentParser(description="AgroWise ESP32 simulator")
    parser.add_argument("--server", default="http://localhost:5000",
                        help="backend base URL (default: http://localhost:5000)")
    parser.add_argument("--scenario", default="moderate",
                        choices=[*SCENARIOS.keys(), "drift"],
                        help="fertile | moderate | dry | waterlogged | barren | drift")
    parser.add_argument("--interval", type=float, default=30.0,
                        help="seconds between packets (default 30, use 3 for demos)")
    parser.add_argument("--count", type=int, default=0,
                        help="number of packets to send (0 = run forever)")
    parser.add_argument("--api-key", default=os.environ.get("AGROWISE_API_KEY", ""),
                        help="backend API key (or set AGROWISE_API_KEY env var); "
                             "printed by server.py on startup")
    parser.add_argument("--device-id", default="",
                        help="distinguish this simulated device from others (e.g. 'SIM-Field2'); "
                             "defaults to just 'SIM' if omitted, same as before this flag existed")
    args = parser.parse_args()

    if not args.api_key:
        print("[SIM] no --api-key given (and AGROWISE_API_KEY not set) — "
              "requests will be rejected with 401. Copy the key server.py printed on startup.")

    drift_state = {"n": 70.0, "p": 18.0, "k": 110.0, "m": 22.0, "ph": 6.2, "temp": 28.0}
    sent = 0
    print(f"[SIM] scenario={args.scenario}  interval={args.interval}s  -> {args.server}")

    while args.count == 0 or sent < args.count:
        packet = make_packet(args.scenario, drift_state)
        try:
            status, data = post_packet(args.server, packet, args.api_key, args.device_id)
            reading = data.get("reading", {})
            print(f"[SIM] #{sent + 1:03d} HTTP {status}  "
                  f"N={packet['n']:<6} P={packet['p']:<6} K={packet['k']:<6} "
                  f"M={packet['m']:<5}% pH={packet['ph']:<5} T={packet['temp']:<5} "
                  f"-> score {reading.get('score')} {reading.get('cls')} "
                  f"[moisture: {reading.get('moisture_status')}]")
        except urllib.error.URLError as exc:
            print(f"[SIM] backend unreachable ({exc.reason}) — is server.py running?")
        sent += 1
        if args.count == 0 or sent < args.count:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
