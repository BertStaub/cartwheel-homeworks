"""Split the cascade examples by scenario and write the blank labeling sheet.

Run from the repository root: uv run python cascade/scripts/make_label_sheet.py
Offline. The sheet has the conversation text but neither the oracle verdict
nor the split, so neither can anchor your labels. Both are saved in
cascade/data/split.json.
"""

from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "cascade" / "data"
SEED = 9


def split_by_scenario(examples: list[dict]) -> dict[str, str]:
    """scenario_id -> 'development' | 'test'. Both periods of a scenario stay together.

    Scenarios with an oracle fail are dealt out alternately first, so each side
    gets some failures. The rest fill whichever side is further below half.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for example in examples:
        groups[example["scenario_id"]].append(example)
    rng = random.Random(SEED)
    failing = sorted(s for s, g in groups.items() if any(e["oracle_verdict"] for e in g))
    passing = sorted(s for s in groups if s not in failing)
    rng.shuffle(failing)
    rng.shuffle(passing)
    side: dict[str, str] = {}
    counts = {"development": 0, "test": 0}
    for scenario in failing:
        # give the next failing scenario to the side with fewer oracle fails
        fails = {name: sum(e["oracle_verdict"] for s, n in side.items() if n == name for e in groups[s])
                 for name in counts}
        name = min(counts, key=lambda n: (fails[n], counts[n]))
        side[scenario] = name
        counts[name] += len(groups[scenario])
    for scenario in passing:
        name = min(counts, key=lambda n: counts[n])
        side[scenario] = name
        counts[name] += len(groups[scenario])
    return side


def main() -> None:
    examples = json.loads((DATA / "examples.json").read_text())
    side = split_by_scenario(examples)
    split = {e["trace_id"]: side[e["scenario_id"]] for e in examples}
    (DATA / "split.json").write_text(json.dumps({
        "seed": SEED,
        "split": split,
        "oracle_verdict": {e["trace_id"]: e["oracle_verdict"] for e in examples},
    }, indent=1))

    rows = [{"example_id": f"ex-{i:02d}", "trace_id": e["trace_id"], "text": e["text"]}
            for i, e in enumerate(random.Random(SEED + 1).sample(examples, len(examples)))]
    with (DATA / "label_sheet.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["example_id", "trace_id", "text", "human_label", "notes"])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "human_label": "", "notes": ""})

    for name in ("development", "test"):
        members = [e for e in examples if split[e["trace_id"]] == name]
        print(f"{name:<12} examples={len(members)} scenarios={len({e['scenario_id'] for e in members})} "
              f"oracle_fail={sum(e['oracle_verdict'] for e in members)}")
    print(f"longest text: {max(len(r['text']) for r in rows)} characters (Excel cell limit is 32,767)")
    print(f"Saved {DATA / 'label_sheet.csv'} and {DATA / 'split.json'}")


if __name__ == "__main__":
    main()
