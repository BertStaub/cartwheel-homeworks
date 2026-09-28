"""Fetch, validate, sample, and judge one monitoring period.

Wires together the three holes (`select_traces` in `sample.py`,
`corrected_mode_prevalence` in `correct.py`, `build_score_records` in
`write_scores.py`) against real Langfuse traces for one period named in
`monitoring/config.json`.

The judge call is the only paid step. It only runs when invoked with
`--confirm`; without it, this prints the plan (selected trace count, judge
call count) and stops, so `uv run python -m monitoring.run --period before`
is always safe to run first.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent.agent import LITELLM_COURSE_MODELS
from analysis.helpers.langfuse_io import fetch_traces
from monitoring.correct import corrected_mode_prevalence
from monitoring.sample import DEFAULT_RISK_GROUPS, select_traces
from monitoring.write_scores import build_score_records

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "monitoring" / "config.json"
SCENARIOS_PATH = REPO_ROOT / "scenarios" / "monitoring_scenarios.jsonl"
HISTORY_PATH = REPO_ROOT / "monitoring" / "history.jsonl"


class PeriodError(ValueError):
    """A period's traces failed validation before any judge call is made."""


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_monitoring_scenario_ids() -> set[str]:
    ids: set[str] = set()
    with SCENARIOS_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                ids.add(json.loads(line)["id"])
    return ids


def get_period(config: dict[str, Any], label: str) -> dict[str, Any]:
    for period in config["periods"]:
        if period["label"] == label:
            return period
    raise ValueError(f"no period named {label!r} in monitoring/config.json")


def _tool_names(trace: dict[str, Any]) -> list[str]:
    return [
        str(message["name"])
        for message in trace.get("trace", [])
        if message.get("role") == "tool_call" and message.get("name")
    ]


def _user_turns(trace: dict[str, Any]) -> int:
    return sum(1 for message in trace.get("trace", []) if message.get("role") == "user")


def build_conversation_records(
    traces: list[dict[str, Any]], group_by: str = "scenario_id"
) -> list[dict[str, Any]]:
    """Group normalized traces into one conversation record per group key.

    A trace with no final output (``output`` is ``None``) is a dead attempt
    -- dropped whenever a later trace in the same group actually completed,
    so a stale retry never gets concatenated into the conversation text next
    to the real one. The record id is the LAST kept trace's id, so Langfuse
    receives the score on a trace that still exists in the conversation.
    """
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trace in traces:
        key = trace.get("meta", {}).get(group_by)
        if key:
            groups[key].append(trace)

    records: list[dict[str, Any]] = []
    for key, group in groups.items():
        group.sort(key=lambda t: t.get("timestamp") or "")
        completed = [t for t in group if t.get("output") is not None]
        kept = completed if completed else group

        tools: list[str] = []
        turn_count = 0
        text_parts: list[str] = []
        models: list[str] = []
        for trace in kept:
            tools.extend(_tool_names(trace))
            turn_count += _user_turns(trace)
            text_parts.append(str(trace.get("text", "")))
            for model in trace.get("models", []):
                if model not in models:
                    models.append(model)

        records.append(
            {
                "id": kept[-1]["id"],
                "scenario_id": key,
                "tools": sorted(set(tools)),
                "turn_count": turn_count,
                "text": "\n".join(text_parts),
                "models": models,
            }
        )
    # Sorted by scenario_id so list position is stable across periods --
    # select_traces samples by position, and each period's traces come back
    # from Langfuse sorted by trace_id (a fresh random id every run), so an
    # unsorted return would let the same seed pick a *different* subset of
    # scenarios each period instead of tracking the same ones across time.
    records.sort(key=lambda record: record["scenario_id"])
    return records


def validate_records(
    records: list[dict[str, Any]], expected_ids: set[str], expected_model: str
) -> None:
    litellm_model = LITELLM_COURSE_MODELS.get(expected_model, expected_model)
    found_ids = {record["scenario_id"] for record in records}

    missing = expected_ids - found_ids
    if missing:
        raise PeriodError(f"period is missing scenario ids: {sorted(missing)[:5]}")
    unexpected = found_ids - expected_ids
    if unexpected:
        raise PeriodError(f"period has unexpected scenario ids: {sorted(unexpected)[:5]}")
    if len(records) != len(expected_ids):
        raise PeriodError(
            f"expected exactly {len(expected_ids)} conversation records, got {len(records)}"
        )

    bad_model = sorted(
        record["scenario_id"]
        for record in records
        if any(model != litellm_model for model in record["models"])
    )
    if bad_model:
        raise PeriodError(
            f"traces used a different model than {expected_model!r}: {bad_model[:5]}"
        )


def risk_group_predicates(names: list[str]) -> dict[str, Any]:
    unknown = set(names) - set(DEFAULT_RISK_GROUPS)
    if unknown:
        raise ValueError(f"unknown risk group(s): {sorted(unknown)}")
    return {name: DEFAULT_RISK_GROUPS[name] for name in names}


def fetch_period_records(
    period: dict[str, Any], scenario_ids: set[str]
) -> tuple[list[dict[str, Any]], int]:
    from_ts = _parse_ts(period["from"])
    to_ts = _parse_ts(period["to"])
    traces = fetch_traces(limit=5000)
    windowed = [
        trace
        for trace in traces
        if trace.get("meta", {}).get("scenario_id") in scenario_ids
        and trace.get("timestamp")
        and from_ts <= _parse_ts(trace["timestamp"]) <= to_ts
    ]
    return build_conversation_records(windowed, group_by="scenario_id"), len(windowed)


def plan_sample(
    records: list[dict[str, Any]], config: dict[str, Any]
) -> dict[str, Any]:
    risk_groups = risk_group_predicates(config["risk_groups"])
    return select_traces(records, config["random_rate"], risk_groups, seed=7)


def fetch_recent_traces(from_ts: datetime, to_ts: datetime) -> list[dict[str, Any]]:
    """Every trace in [from_ts, to_ts], regardless of scenario metadata.

    Unlike ``fetch_traces`` (which keeps only Module 1 scenario traces),
    live server traffic carries no ``scenario_id`` -- this pulls everything
    in the window so ``build_conversation_records(..., group_by="session_id")``
    can group it.
    """
    from analysis.helpers.langfuse_io import _client
    from analysis.helpers.normalization import normalize_trace

    client = _client()
    collected: list[Any] = []
    page = 1
    while True:
        resp = client.api.trace.list(
            from_timestamp=from_ts, to_timestamp=to_ts, page=page, limit=100
        )
        batch = list(resp.data or [])
        collected.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    traces: list[dict[str, Any]] = []
    for summary in collected:
        full = client.api.trace.get(summary.id)
        traces.append(normalize_trace(full))
    return traces


def prepare_period(
    label: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], int]:
    """Steps 1-6: load config, fetch traces, validate, build records, plan the sample."""
    config = load_config()
    period = get_period(config, label)
    scenario_ids = load_monitoring_scenario_ids()
    records, trace_count = fetch_period_records(period, scenario_ids)
    validate_records(records, scenario_ids, config["model"])
    plan = plan_sample(records, config)
    return config, records, plan, trace_count


def _print_plan(label: str, plan: dict[str, Any]) -> None:
    n_random = len(plan["random"])
    n_risk = {name: len(traces) for name, traces in plan["risk_groups"].items()}
    n_to_judge = len(plan["to_judge"])
    print(f"period={label!r}")
    print(f"  random sample:  {n_random}")
    for name, count in n_risk.items():
        print(f"  risk group {name!r}: {count}")
    print(f"  traces to judge (union, 1 judge_sample call): {n_to_judge}")


def _append_history(record: dict[str, Any]) -> None:
    with HISTORY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def _risk_union_ids(plan: dict[str, Any]) -> set[str]:
    return {trace["id"] for group in plan["risk_groups"].values() for trace in group}


def _judge_and_persist(
    label: str, config: dict[str, Any], plan: dict[str, Any]
) -> dict[str, Any]:
    """Steps 8-9 plus Part C: judge the union once, correct, and persist.

    Shared by both entry points (a named period, or a live --last-hours
    window) so the paid call and the scoring/history logic exist in one
    place.
    """
    from monitoring.run_judges import judge_sample, judge_test_data

    verdicts = judge_sample(config["judge_id"], plan["to_judge"])
    random_ids = {trace["id"] for trace in plan["random"]}
    risk_ids = _risk_union_ids(plan)
    random_verdicts = {tid: verdicts[tid] for tid in verdicts if tid in random_ids}
    risk_verdicts = {tid: verdicts[tid] for tid in verdicts if tid in risk_ids}

    test_labels, test_preds = judge_test_data(config["judge_id"])
    estimate = corrected_mode_prevalence(
        list(random_verdicts.values()), test_labels, test_preds
    )

    score_records = build_score_records(
        config["judge_mode"], random_verdicts, risk_verdicts, estimate, label
    )
    from analysis.helpers import langfuse_io

    if langfuse_io.is_configured():
        from monitoring.write_scores import post_scores

        posted = post_scores(score_records)
        print(f"  posted {posted} scores to Langfuse")
    else:
        print("  Langfuse not configured; scores built but not posted")

    print(
        f"  raw={estimate['raw']} corrected={estimate['corrected']} "
        f"ci=[{estimate['ci_low']}, {estimate['ci_high']}]"
    )
    return {
        "random_verdicts": random_verdicts,
        "risk_verdicts": risk_verdicts,
        "estimate": estimate,
        "score_records": score_records,
    }


def _history_record(
    label: str,
    config: dict[str, Any],
    trace_count: int,
    conversation_count: int,
    random_count: int,
    risk_count: int,
    estimate: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "label": label,
        "judge_id": config["judge_id"],
        "model": config["model"],
        "trace_count": trace_count,
        "conversation_count": conversation_count,
        "random_count": random_count,
        "risk_count": risk_count,
        "raw": estimate["raw"] if estimate else None,
        "corrected": estimate["corrected"] if estimate else None,
        "ci_low": estimate["ci_low"] if estimate else None,
        "ci_high": estimate["ci_high"] if estimate else None,
        "confidence": estimate["confidence"] if estimate else None,
        "failure_sensitivity": estimate["failure_sensitivity"] if estimate else None,
        "pass_specificity": estimate["pass_specificity"] if estimate else None,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def run_period(label: str, confirm: bool) -> dict[str, Any] | None:
    config, records, plan, trace_count = prepare_period(label)
    _print_plan(label, plan)
    if not confirm:
        print("Dry run only (pass --confirm to call the judge).")
        return None

    result = _judge_and_persist(label, config, plan)
    _append_history(
        _history_record(
            label,
            config,
            trace_count,
            len(records),
            len(plan["random"]),
            len(_risk_union_ids(plan)),
            result["estimate"],
        )
    )
    return {"config": config, "records": records, "plan": plan, **result}


def run_last_hours(hours: float, confirm: bool) -> dict[str, Any] | None:
    """Live window (Part D): group by session_id, skip the judge if empty."""
    config = load_config()
    label = f"last-{hours}h"
    to_ts = datetime.now(timezone.utc)
    from_ts = to_ts - timedelta(hours=hours)

    raw_traces = fetch_recent_traces(from_ts, to_ts)
    records = build_conversation_records(raw_traces, group_by="session_id")

    if not records:
        print(
            f"period={label!r}: 0 eligible conversations in the last {hours} "
            "hours; recording a zero count, no judge call"
        )
        _append_history(
            _history_record(label, config, len(raw_traces), 0, 0, 0, None)
        )
        return None

    plan = plan_sample(records, config)
    _print_plan(label, plan)
    if not confirm:
        print("Dry run only (pass --confirm to call the judge).")
        return None

    result = _judge_and_persist(label, config, plan)
    _append_history(
        _history_record(
            label,
            config,
            len(raw_traces),
            len(records),
            len(plan["random"]),
            len(_risk_union_ids(plan)),
            result["estimate"],
        )
    )
    return {"config": config, "records": records, "plan": plan, **result}


def main() -> None:
    parser = argparse.ArgumentParser()
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--period", choices=["before", "after"])
    target.add_argument("--last-hours", type=float)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="actually call the frozen judge (a paid call); omit to preview only",
    )
    args = parser.parse_args()
    if args.period:
        run_period(args.period, confirm=args.confirm)
    else:
        run_last_hours(args.last_hours, confirm=args.confirm)


if __name__ == "__main__":
    main()
