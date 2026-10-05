"""Build cascade/data/examples.json: judged HW7 monitor traces + oracle verdicts.

Run from the repository root: uv run python cascade/scripts/build_examples.py
Read-only against Langfuse; makes no model calls. The oracle verdicts are the
frozen unsupported_policy_claim-v3 scores that the HW7 monitor posted.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from observability.instrument import load_env

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "cascade" / "data" / "examples.json"
MODE = "unsupported_policy_claim"


def oracle_scores() -> dict[str, dict[str, int]]:
    """trace_id -> {score name -> 0/1}, read from the monitor's Langfuse scores."""
    from analysis.helpers.langfuse_io import _client

    client = _client()
    scores: dict[str, dict[str, int]] = defaultdict(dict)
    for name in (f"{MODE}_verdict", f"{MODE}_risk_verdict"):
        page, seen = 1, 0
        while True:
            response = client.api.score_v_2.get(name=name, page=page, limit=100)
            if not response.data:
                break
            for score in response.data:
                scores[score.trace_id][name] = int(score.value)
            seen += len(response.data)
            page += 1
            if seen >= response.meta.total_items:
                break
    return scores


def main() -> None:
    load_env()
    from monitoring.run import prepare_period

    scores = oracle_scores()
    examples, conflicts, unscored = [], [], []
    for period in ("before", "after"):
        _, _, plan, _ = prepare_period(period)
        random_ids = {t["id"] for t in plan["random"]}
        for trace in plan["to_judge"]:
            found = scores.get(trace["id"], {})
            if not found:
                unscored.append(trace["id"])
                continue
            verdicts = set(found.values())
            if len(verdicts) > 1:
                conflicts.append(trace["id"])
            examples.append({
                "trace_id": trace["id"],
                "period": period,
                "scenario_id": trace["scenario_id"],
                "sample": "random" if trace["id"] in random_ids else "risk",
                "oracle_verdict": max(verdicts),  # 1 = fail (failure present)
                "text": trace["text"],
            })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(examples, indent=1))
    fails = sum(e["oracle_verdict"] for e in examples)
    print(f"Saved {OUT}")
    print(f"examples={len(examples)} oracle_fail={fails} oracle_pass={len(examples) - fails}")
    print(f"by period: { {p: sum(e['period'] == p for e in examples) for p in ('before', 'after')} }")
    print(f"judged traces with no Langfuse score: {len(unscored)}; conflicting scores: {len(conflicts)}")
    print(f"empty text: {sum(not e['text'].strip() for e in examples)}; unique scenarios: {len({e['scenario_id'] for e in examples})}")


if __name__ == "__main__":
    main()
