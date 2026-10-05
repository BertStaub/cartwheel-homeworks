"""Write cascade/results/thresholds.csv and check.json from the saved proxy runs.

Run from the repository root: uv run python cascade/scripts/make_cascade_results.py
Offline: reads saved results only. The oracle's cost per verdict is an ESTIMATE
taken from profile/results/costs.csv, because its token counts were never saved.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASCADE = ROOT / "cascade"
PROXY_PRICES = (0.75, 3.75)  # gemini/gemini-3.8-flash, USD per million tokens
LOCKED = json.loads((CASCADE / "results" / "locked.json").read_text())
ORACLE = json.loads((CASCADE / "data" / "split.json").read_text())["oracle_verdict"]


def load(split: str) -> dict:
    return json.loads((CASCADE / "results" / f"proxy_{split}.json").read_text())


def oracle_cost_per_verdict() -> float:
    with (ROOT / "profile" / "results" / "costs.csv").open() as handle:
        for row in csv.DictReader(handle):
            if "unsupported_policy_claim judge v3" in row["call_site"]:
                return float(row["cost_usd"]) / int(row["calls"])
    raise ValueError("no unsupported_policy_claim v3 row in costs.csv")


def proxy_cost_per_verdict(results: dict) -> float:
    tokens_in = sum(r["input_tokens"] for r in results.values())
    tokens_out = sum(r["output_tokens"] for r in results.values())
    return (tokens_in * PROXY_PRICES[0] + tokens_out * PROXY_PRICES[1]) / 1_000_000 / len(results)


def evaluate(results: dict, threshold: float, oracle_cost: float) -> dict:
    n = len(results)
    kept = {k: v for k, v in results.items() if v["confidence"] >= threshold}
    disagreements = sum(v["verdict"] != ORACLE[k] for k, v in kept.items())
    share = len(kept) / n
    # The proxy always runs; the oracle runs on the examples the proxy does not keep.
    cost = 1000 * (proxy_cost_per_verdict(results) + (1 - share) * oracle_cost)
    return {"n": n, "proxy_share": share, "disagreements": disagreements,
            "agreement": 1 - disagreements / n, "cost_per_1000": cost}


def main() -> None:
    oracle_cost = oracle_cost_per_verdict()
    development = load("development")
    out = CASCADE / "results" / "thresholds.csv"
    with out.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["threshold", "agreement_with_oracle", "agreement_with_human_labels",
                         "proxy_share", "cost_per_1000_verdicts_usd"])
        for threshold in (0.5, 0.8, 0.9, 0.95, 1.0, 1.01):
            r = evaluate(development, threshold, oracle_cost)
            writer.writerow([threshold, round(r["agreement"], 4), "not measured",
                             round(r["proxy_share"], 4), round(r["cost_per_1000"], 2)])
    print(f"Saved {out} (development split, gemini/gemini-3.8-flash; 1.01 means every example goes to the oracle)")

    locked = LOCKED["threshold"]
    test = evaluate(load("test"), locked, oracle_cost)
    oracle_fails = sum(ORACLE[k] for k in load("test"))
    check = {
        "split": "test",
        "proxy_model": LOCKED["proxy_model"],
        "oracle": LOCKED["oracle"],
        "threshold": locked,
        "minimum_agreement_with_oracle": LOCKED["minimum_agreement_with_oracle"],
        "examples": test["n"],
        "oracle_failures_in_split": oracle_fails,
        "agreement_with_oracle": round(test["agreement"], 4),
        "disagreements": test["disagreements"],
        "proxy_share": round(test["proxy_share"], 4),
        "cost_per_1000_verdicts_usd": round(test["cost_per_1000"], 2),
        "cost_note": ("proxy cost measured from token counts; oracle cost per verdict "
                      f"(${oracle_cost:.4f}) is an estimate from costs.csv"),
        "agreement_with_human_labels": "not measured (no human labels)",
        "decision": "rejected",
        "reason": ("Test agreement met the minimum, but the test split has only "
                   f"{oracle_fails} oracle failures, too few to give a usable signal. "
                   "Rejected on sample size, not on a failed threshold. Not ready for CI or monitoring."),
        "rejected_before_test": LOCKED["rejected_before_test"],
    }
    path = CASCADE / "results" / "check.json"
    path.write_text(json.dumps(check, indent=2))
    print(f"Saved {path}")
    print(json.dumps({k: check[k] for k in ("agreement_with_oracle", "disagreements", "proxy_share", "cost_per_1000_verdicts_usd")}))


if __name__ == "__main__":
    main()
