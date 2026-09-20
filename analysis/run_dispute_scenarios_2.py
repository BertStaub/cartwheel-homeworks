"""Second targeted-scenario batch for HW5 label collection (see
``run_dispute_scenarios.py`` for the full rationale). Batch 1 hit a ~46% Fail
rate (11/24), well above the organic ~10% base rate, but left the mode's
label pool at 23 Fail -- 7 short of the 30 minimum. This batch adds 15 more
scenarios grounded in different real orders to close the gap with a buffer.

Requires the Cartwheel server running locally.

Run:
    uv run python -m analysis.run_dispute_scenarios_2
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

SERVER = "http://localhost:8010"
OUT_PATH = Path(__file__).resolve().parent / "state" / "dispute_scenario_results_2.json"

SCENARIOS: list[tuple[str, str, int, str]] = [
    ("dispute2-0001", "shopper", 124, "I want to dispute the charge for my desk lamp order from Pocket Arcade."),
    ("dispute2-0002", "shopper", 471, "Can I still dispute the charge on my hot sauce order from Saltbox Pantry?"),
    ("dispute2-0003", "shopper", 453, "I'd like to dispute the charge for the USB-C hub I bought, it stopped working almost right away."),
    ("dispute2-0004", "shopper", 55, "I need to dispute my olive oil order from Saltbox Pantry, it arrived spoiled."),
    ("dispute2-0005", "shopper", 8, "Is it too late to dispute the charge on my novel order from Paper Lantern Press?"),
    ("dispute2-0006", "shopper", 177, "I want to dispute the charge for my trekking poles from Trailhead Supply."),
    ("dispute2-0007", "shopper", 303, "can i dispute the jam trio order, never got what i actually ordered"),
    ("dispute2-0008", "shopper", 114, "I'd like to dispute the charge for my mechanical keyboard order from Cascade Audio."),
    ("dispute2-0009", "shopper", 344, "Can I dispute the charge on my trekking poles order from Meridian Cycles?"),
    ("dispute2-0010", "shopper", 415, "I want to dispute my face serum order from Fern & Fog, it caused a reaction."),
    ("dispute2-0011", "shopper", 373, "Is it still possible to dispute the charge on my coffee beans order from Saltbox Pantry?"),
    ("dispute2-0012", "merchant", 9011, "A customer wants to dispute the charge on their plush fox order, can you tell me if that's still open?"),
    ("dispute2-0013", "merchant", 9020, "One of our customers is asking to dispute their notebook order charge, is that still something they can do?"),
    ("dispute2-0014", "support", 9501, "Customer on order 7494 wants to dispute their charge for a bluetooth speaker, can you confirm the dispute window status?"),
    ("dispute2-0015", "support", 9501, "I have a customer asking to dispute the charge on order 5252, a dry bag -- is the dispute window still open?"),
]


def main() -> None:
    results = []
    with httpx.Client(timeout=60.0) as client:
        for scenario_id, role, user_id, message in SCENARIOS:
            session_resp = client.post(
                f"{SERVER}/sessions", json={"user_id": user_id, "role": role}
            )
            session_resp.raise_for_status()
            session = session_resp.json()
            session_id = session["session_id"]
            token = session["token"]

            msg_resp = client.post(
                f"{SERVER}/sessions/{session_id}/messages",
                json={"message": message, "scenario_id": scenario_id},
                headers={"Authorization": f"Bearer {token}"},
            )
            msg_resp.raise_for_status()
            body = msg_resp.json()

            print(f"[{scenario_id}] ({role}, user {user_id}) -> {body['reply'][:120]!r}")
            results.append(
                {
                    "scenario_id": scenario_id,
                    "role": role,
                    "user_id": user_id,
                    "message": message,
                    "session_id": session_id,
                    "reply": body["reply"],
                }
            )
            time.sleep(0.2)

    OUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {len(results)} results to {OUT_PATH}")


if __name__ == "__main__":
    main()
