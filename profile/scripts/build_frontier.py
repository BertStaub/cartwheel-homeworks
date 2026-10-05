"""Build profile/results/frontier.csv from saved development runs.

Run from the repository root: uv run python profile/scripts/build_frontier.py
Offline. Uses the HW8 dominance rule (optimize.workflow.mark_dominated): a row
is dominated when another has an equal or higher score and an equal or lower
cost, and is strictly better on at least one of the two.
"""

from __future__ import annotations

import csv
import glob
import json
from pathlib import Path

from optimize.workflow import mark_dominated

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "optimize" / "results"
OUT = ROOT / "profile" / "results" / "frontier.csv"

# (candidate label, file glob). The first row is the HW8 final run.
RUNS = [
    ("hw8-final", "development-final-gemini*.json"),
    ("fewer-tokens", "development-fewer-tokens-*.json"),
    ("cache-before", "development-cache-before-*.json"),
    ("cache-after", "development-cache-after-gpt*.json"),
    ("cache-after-rerun1", "development-cache-after-rerun1-*.json"),
    ("cache-after-rerun2", "development-cache-after-rerun2-*.json"),
]
FIELDS = ["candidate", "model", "development_score", "write_pass_5",
          "cost_per_100_conversations_usd", "median_latency_seconds", "frontier_status"]


def main() -> None:
    configurations = []
    for number, (label, pattern) in enumerate(RUNS, start=1):
        matches = sorted(glob.glob(str(RESULTS / pattern)))
        if len(matches) != 1:
            raise SystemExit(f"{label}: expected one file for {pattern}, found {len(matches)}")
        run = json.loads(Path(matches[0]).read_text())
        configurations.append({
            "configuration": number,
            "candidate": label,
            "model": run["model"],
            "score": run["score"],
            "write_pass_5": run["write_pass_5"],
            "cost_per_100_conversations_usd": run["cost_per_100_conversations_usd"],
            "median_latency_seconds": run["median_latency_seconds"],
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in mark_dominated(configurations):
            writer.writerow({
                "candidate": row["candidate"],
                "model": row["model"],
                "development_score": row["score"],
                "write_pass_5": "" if row["write_pass_5"] is None else row["write_pass_5"],
                "cost_per_100_conversations_usd": row["cost_per_100_conversations_usd"],
                "median_latency_seconds": row["median_latency_seconds"],
                "frontier_status": "dominated" if row["dominated"] else "frontier",
            })
    print(f"Saved {OUT}")
    print(OUT.read_text())


if __name__ == "__main__":
    main()
