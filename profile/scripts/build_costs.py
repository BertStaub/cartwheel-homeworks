"""Build profile/results/costs.csv: one row per model call site.

Run from the repository root: uv run python profile/scripts/build_costs.py
Offline: reads saved files only and makes no model calls.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "profile" / "results" / "costs.csv"
CHARS_PER_TOKEN = 4  # rough rule for English text; used only for estimates
ASSUMED_JUDGE_OUTPUT_TOKENS = 100  # judge runs did not save output tokens
FIELDS = ["cost_category", "call_site", "purpose", "model", "calls",
          "input_tokens", "output_tokens", "cost_usd"]


def load(path: str):
    return json.loads((ROOT / path).read_text())


def prices(model: str) -> tuple[float, float]:
    table = load("optimize/config.json")["prices_per_million_tokens_usd"]
    p = table[model]
    return p["input"], p["output"]


def conversation_rows() -> list[dict]:
    """Token counts and cost come from Langfuse (what the export recorded)."""
    sites: dict[tuple[str, str], dict] = {}
    for trace in load("traces/support_traces.json")["traces"]:
        for obs in trace["observations"]:
            if obs["type"] != "GENERATION":
                continue
            usage = obs.get("usage") or {}
            row = sites.setdefault((obs["name"], obs["model"]), dict(calls=0, i=0, o=0, cost=0.0))
            row["calls"] += 1
            row["i"] += usage.get("input", 0) or 0
            row["o"] += usage.get("output", 0) or 0
            row["cost"] += obs.get("calculatedTotalCost") or 0.0
    return [
        dict(cost_category="customer_conversation",
             call_site=f"agent model call ({name}), traces/support_traces.json",
             purpose="Agent answers a user (token counts and cost from Langfuse export)",
             model=model, calls=r["calls"], input_tokens=r["i"], output_tokens=r["o"],
             cost_usd=round(r["cost"], 6))
        for (name, model), r in sites.items()
    ]


def judge_row(site, purpose, model, calls, prompt_chars, text_chars) -> dict:
    """Judge input = judge prompt + judged text. Tokens are ESTIMATES (chars / 4)."""
    in_price, out_price = prices(model)
    per_call_in = (prompt_chars + text_chars) / CHARS_PER_TOKEN
    tokens_in = round(per_call_in * calls)
    tokens_out = ASSUMED_JUDGE_OUTPUT_TOKENS * calls
    cost = (tokens_in * in_price + tokens_out * out_price) / 1_000_000
    return dict(cost_category="judge", call_site=site,
                purpose=f"{purpose} (ESTIMATED tokens: chars/4, output assumed {ASSUMED_JUDGE_OUTPUT_TOKENS}/call)",
                model=model, calls=calls, input_tokens=tokens_in,
                output_tokens=tokens_out, cost_usd=round(cost, 6))


def judge_rows() -> list[dict]:
    rows = []
    traces = load("traces/support_traces.json")["traces"]
    mean_trace_chars = sum(len(json.dumps(t["input"])) + len(json.dumps(t["output"])) for t in traces) / len(traces)

    # HW5 dispute judges: the judged text is in analysis/state/hw5_trace_inputs.json.
    inputs = {r["trace_id"]: len(json.dumps(r["trace"])) for r in load("analysis/state/hw5_trace_inputs.json")}
    mean_dispute_chars = sum(inputs.values()) / len(inputs)
    dispute_model = "gemini/gemini-3.8-flash"  # judge alias "gemini-flash"; priced as this model
    for version in ("v0", "v1"):
        j = load(f"analysis/state/judges/dispute_window_not_checked_against_current_date-{version}.json")
        calls = sum(len(p) for p in j["predictions"].values())
        rows.append(judge_row(
            f"analysis/run_judges.py: dispute_window judge {version}",
            f"HW5 judge run, {calls} verdicts", dispute_model, calls,
            len(j["prompt_text"]), mean_dispute_chars))

    # HW5 validation of the reference judge: 600 verdicts, judged text not saved.
    j = load("analysis/state/judges/unsupported_policy_claim-v3.json")
    calls = sum(len(p) for p in j["predictions"].values())
    rows.append(judge_row(
        "analysis/run_judges.py: unsupported_policy_claim judge v3",
        f"HW5 judge validation, {calls} verdicts; judged text size assumed = mean export trace",
        j["model"], calls, len(j["prompt_text"]), mean_trace_chars))

    # HW7 monitor: one verdict per selected trace, in two periods.
    config = load("monitoring/config.json")
    for r in (json.loads(l) for l in (ROOT / "monitoring" / "history.jsonl").read_text().splitlines()):
        rows.append(judge_row(
            f"monitoring/run.py: unsupported_policy_claim monitor ({r['label']})",
            f"HW7 monitor run, {r['trace_count']} traces; judged text size assumed = mean export trace",
            config["model"], r["trace_count"], len(j["prompt_text"]), mean_trace_chars))
    return rows


def main() -> None:
    rows = conversation_rows() + judge_rows()
    rows.sort(key=lambda r: (r["cost_category"], -r["cost_usd"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {OUT}")
    for r in rows:
        print(f'{r["cost_category"]:<22} {r["calls"]:>5} calls  ${r["cost_usd"]:>9.4f}  {r["call_site"]}')


if __name__ == "__main__":
    main()
