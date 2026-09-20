"""One-off runner: targeted dispute-window scenarios for HW5 label collection.

The organic label pool for ``dispute_window_not_checked_against_current_date``
plateaued at 12 confirmed Fail instances after exhausting the semantic-neighbor
search over the unreviewed trace pool (HW5 handout's documented fallback:
"generate targeted scenarios and run them through Cartwheel"). Every delivered
order in the seeded database is already past the 60-day dispute window (the
same seeding-staleness root cause documented for TOOL-11), so any real order
grounds a scenario that raises the dispute topic -- the open question per
conversation is only how the agent's reply resolves it, not whether the
window has passed.

Requires the Cartwheel server running locally (``uv run uvicorn server.app:app
--port 8010``).

Run:
    uv run python -m analysis.run_dispute_scenarios
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

SERVER = "http://localhost:8010"
OUT_PATH = Path(__file__).resolve().parent / "state" / "dispute_scenario_results.json"

# Each row: (scenario_id, role, user_id, message). Grounded in real seeded
# orders (product/store names pulled from the DB); no dates or window
# language stated, since a real caller would not know those facts.
SCENARIOS: list[tuple[str, str, int, str]] = [
    ("dispute-0001", "shopper", 393, "I want to dispute the charge for the desk lamp I ordered, it's been a while and I never got a resolution."),
    ("dispute-0002", "shopper", 388, "I'd like to challenge the charge for my bath salts order from Clover Field Naturals."),
    ("dispute-0003", "shopper", 132, "Can I still dispute the charge on the poetry collection I bought from Northwind Books?"),
    ("dispute-0004", "shopper", 199, "I need to dispute the charge for my headphones, they showed up broken and nobody ever helped me."),
    ("dispute-0005", "shopper", 497, "hey, i want to dispute my utility knife order, can someone look into that"),
    ("dispute-0006", "shopper", 330, "Is it too late for me to dispute the charge on the scarf I ordered from Second Stitch?"),
    ("dispute-0007", "shopper", 181, "I'd like to file a dispute for the daypack I got from Meridian Cycles, it was never what I expected."),
    ("dispute-0008", "shopper", 232, "Can you tell me if I can still dispute the charge for the field guide from Northwind Books?"),
    ("dispute-0009", "shopper", 433, "I want to dispute my water bottle purchase, it's honestly been sitting in a closet since it arrived broken."),
    ("dispute-0010", "shopper", 63, "This is ridiculous, I still haven't disputed the charge for my poetry collection order and I want to now."),
    ("dispute-0011", "shopper", 382, "Can I dispute the charge on my vase order from Blue Heron Ceramics? It arrived cracked."),
    ("dispute-0012", "shopper", 210, "I'd like to dispute the shampoo bar order, I never actually got what I paid for."),
    ("dispute-0013", "shopper", 270, "trekking poles order - want to dispute the charge, is that possible still"),
    ("dispute-0014", "shopper", 306, "I need to dispute my bath salts charge from Fern & Fog, can you help with that?"),
    ("dispute-0015", "shopper", 203, "Is it possible to dispute the charge for my teapot from Juniper Home Goods?"),
    ("dispute-0016", "shopper", 120, "I want to dispute the headphones order, it's an old order but I never got it resolved."),
    ("dispute-0017", "shopper", 441, "Can I dispute the serving bowl order from Juniper Home Goods? Never should have paid for that."),
    ("dispute-0018", "shopper", 165, "I'd like to dispute the notebook charge from Atlas Stationery if that's still possible."),
    ("dispute-0019", "merchant", 9008, "A customer is saying they want to dispute their charge for a journal order from a while back -- do we still need to worry about that?"),
    ("dispute-0020", "merchant", 9013, "One of our customers is asking to dispute the charge on their coffee beans order, is that something they can still do?"),
    ("dispute-0021", "merchant", 9004, "A customer wants to dispute the charge for their tape measure order, can you check if that's still open?"),
    ("dispute-0022", "support", 9501, "Customer on order 393 wants to dispute their charge for a level, can you confirm whether that's still within the dispute window?"),
    ("dispute-0023", "support", 9501, "I have a customer asking to dispute the charge on order 2774, a beanie -- is the dispute window still open for that one?"),
    ("dispute-0024", "support", 9501, "Following up on order 6205, a rain shell -- the customer wants to dispute the charge, can you tell me if they still can?"),
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
            time.sleep(0.2)  # gentle pacing, not a rate-limit workaround

    OUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {len(results)} results to {OUT_PATH}")


if __name__ == "__main__":
    main()
