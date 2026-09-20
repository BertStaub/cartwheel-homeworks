"""HW5, Part B onward: judge inputs, splits, and judge runs for one failure
mode (Homework 5, `homework/module-2/hw5.md`).

Chosen mode: ``dispute_window_not_checked_against_current_date`` (HW4 Part A
boundary and rationale are recorded in ``analysis/state/patterns.json``).

Run:
    uv run python -m analysis.run_judges prepare
    uv run python -m analysis.run_judges split
    uv run python -m analysis.run_judges dev --prompt analysis/prompts/<mode>-v0.txt
    uv run python -m analysis.run_judges test --judge-id <judge_id>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from analysis.helpers import _state

MODE = "dispute_window_not_checked_against_current_date"
TRACE_INPUTS_PATH = _state.state_path("hw5_trace_inputs.json")
REPORT_DIR = _state.state_root().parent / "report"
# The handout names gpt-4o-mini; this project uses gemini-flash instead
# (an alias the course's own scale.py already maps to LiteLLM), because no
# working OpenAI key was available -- noted here and in the report so the
# substitution is never silently assumed to be the handout's exact model.
JUDGE_MODEL = "gemini-flash"


# ---------------------------------------------------------------------------
# Part B: prepare inputs
# ---------------------------------------------------------------------------


def _labeled_trace_ids(mode: str) -> list[str]:
    """Every trace id with a live (non-superseded) HW5 label for ``mode``."""
    rows = _state.read_jsonl(_state.state_path("hw5_labels", f"{mode}.jsonl"))
    live: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("superseded_by"):
            continue
        live[row["trace_id"]] = row
    return sorted(live)


def prepare_inputs(mode: str = MODE) -> list[dict[str, Any]]:
    """Export judge-ready inputs for every labeled trace to a fixed file.

    Reads full conversations live from Langfuse (session-merged, so a
    multi-turn conversation is one record), keeps only ``role`` and each
    message's text or tool data, and drops everything else -- no human
    labels, annotations, or review notes reach the judge. Writes the export
    once; later prompt versions reuse the same file via
    ``CARTWHEEL_JUDGE_TRACE_SOURCE`` so no trace is re-fetched.
    """
    from observability.instrument import load_env

    load_env()
    from analysis.review_app.server import _fetch_all_traces

    trace_ids = set(_labeled_trace_ids(mode))
    traces = _fetch_all_traces()
    by_id = {t["trace_id"]: t for t in traces}

    missing = trace_ids - set(by_id)
    if missing:
        raise ValueError(f"labeled trace ids missing from Langfuse: {sorted(missing)[:5]}")

    records = []
    for tid in sorted(trace_ids):
        trace = by_id[tid]
        messages = []
        # The judge has no tool access and no wall-clock; a computed deadline
        # is meaningless without today's date at request time to compare it
        # against. This is the one piece of context the reference messages
        # do not already carry, so it is added explicitly (the same way the
        # handout's own example adds the refund tool result for a different
        # mode's evidence).
        if trace.get("timestamp"):
            messages.append({"role": "observation", "label": "request_timestamp", "text": trace["timestamp"]})
        for m in trace["trace"]:
            role = m.get("role")
            if role in ("user", "assistant", "observation"):
                messages.append({"role": role, "text": m.get("text")})
            elif role == "tool_call":
                messages.append({"role": "tool_call", "name": m.get("name"), "arguments": m.get("arguments")})
            elif role == "tool_result":
                messages.append({"role": "tool_result", "name": m.get("name"), "content": m.get("content")})
        records.append({"trace_id": tid, "trace": messages})

    _state.write_json(TRACE_INPUTS_PATH, records)
    print(f"[run_judges] wrote {len(records)} judge-input records to {TRACE_INPUTS_PATH}")
    print(f"[run_judges] labeled traces: {len(trace_ids)}, input records: {len(records)}")
    assert len(records) == len(trace_ids), "one input record per eligible label"
    return records


# ---------------------------------------------------------------------------
# Part B: split
# ---------------------------------------------------------------------------


def split_data(mode: str = MODE) -> dict[str, list[str]]:
    """Train/dev/test split via the provided ``split_labels`` helper.

    20% train (few-shot source), 40% dev (iterative refinement), 40% test
    (touched once, after freezing), per the HW5 handout.
    """
    from analysis.helpers import split_labels

    records = json.loads(Path(TRACE_INPUTS_PATH).read_text())
    eligible_ids = [record["trace_id"] for record in records]

    splits = split_labels(
        mode,
        fractions=(0.20, 0.40, 0.40),
        seed=7,
        min_per_class=10,
        eligible_trace_ids=eligible_ids,
    )

    labels_by_id = {
        row["trace_id"]: row["label"]
        for row in _state.read_jsonl(_state.state_path("hw5_labels", f"{mode}.jsonl"))
    }
    for split_name, ids in splits.items():
        fail = sum(1 for tid in ids if labels_by_id[tid] == 0)
        passc = sum(1 for tid in ids if labels_by_id[tid] == 1)
        print(f"[run_judges] {split_name}: {len(ids)} total (Pass={passc}, Fail={fail})")
    return splits


# ---------------------------------------------------------------------------
# Part C: draft and refine
# ---------------------------------------------------------------------------


def _existing_version(mode: str, prompt_hash: str) -> str | None:
    """A previously registered judge id with this exact (prompt, model)."""
    history = _state.read_json(
        _state.state_path("judges", f"_history_{mode}.json"), default={"versions": []}
    )
    for entry in history["versions"]:
        if entry.get("prompt_hash") == prompt_hash:
            return entry["judge_id"]
    return None


def run_development(mode: str, prompt_path: str, judge_model: str = JUDGE_MODEL) -> dict[str, Any]:
    """Register ``prompt_path`` as a new judge version and score it on dev.

    Reuses an existing version instead of registering a new one when this
    exact (prompt, model) pair was already registered, so a rerun after an
    infrastructure failure (rate limit, network error) does not manufacture
    a spurious "revision" that never changed the prompt.
    """
    from observability.instrument import load_env

    load_env()
    from analysis.helpers import judge_alignment, register_judge, run_judge
    from analysis.helpers.tools import _prompt_hash

    prompt_text = Path(prompt_path).read_text()
    prompt_hash = _prompt_hash(prompt_text, judge_model)
    judge_id = _existing_version(mode, prompt_hash) or register_judge(
        mode=mode, prompt_text=prompt_text, judge_model=judge_model
    )["judge_id"]
    run_judge(judge_id, split="dev", batch_size=10)
    development = judge_alignment(judge_id, split="dev")
    _state.write_json(REPORT_DIR / f"dev-{judge_id}.json", development)
    print(f"[run_judges] {judge_id} dev: {json.dumps(development, indent=2)}")
    return {"judge_id": judge_id, **development}


# ---------------------------------------------------------------------------
# Part D: freeze and test
# ---------------------------------------------------------------------------


def run_test(judge_id: str) -> dict[str, Any]:
    """Freeze ``judge_id`` and score it once on the held-out test split."""
    from observability.instrument import load_env

    load_env()
    from analysis.helpers import freeze_judge, judge_alignment, run_judge

    freeze_judge(judge_id)
    run_judge(judge_id, split="test", batch_size=10)
    test = judge_alignment(judge_id, split="test")
    _state.write_json(REPORT_DIR / f"test-{judge_id}.json", test)
    print(f"[run_judges] {judge_id} test: {json.dumps(test, indent=2)}")
    return test


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    sub.add_parser("split")
    dev_parser = sub.add_parser("dev")
    dev_parser.add_argument("--prompt", required=True)
    test_parser = sub.add_parser("test")
    test_parser.add_argument("--judge-id", required=True)
    args = parser.parse_args()

    if args.command == "prepare":
        prepare_inputs()
    elif args.command == "split":
        split_data()
    elif args.command == "dev":
        run_development(MODE, args.prompt)
    elif args.command == "test":
        run_test(args.judge_id)


if __name__ == "__main__":
    main()
