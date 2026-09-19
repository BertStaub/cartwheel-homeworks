"""Apply the final HW4 taxonomy to every reviewed trace (Homework 4, Part E).

For each *confirmed* mode in ``analysis/state/patterns.json`` (candidate-status
modes are excluded -- they haven't cleared the 3-instance minimum), every
trace in ``analysis/state/sample_manifest.json`` gets a present/absent label:
present (1) if the trace is in that mode's ``example_trace_ids``, absent (0)
otherwise. This default-absent convention is a deliberate methodology choice,
not a claim that every pair was individually re-verified -- every trace
already received at least one open-coding read, and several modes were
checked against the full 250-scenario corpus during depth search.

Each label is:
  - appended to analysis/state/labels/<mode>.jsonl (the Artifact L label
    format read by analysis/helpers/tools.py's _load_labels), and
  - written to Langfuse as a score named after the mode, via
    analysis.helpers.langfuse_io.write_label_score.

Run:
    uv run python -m analysis.build_labels
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from analysis.helpers import _state, langfuse_io

MANIFEST_PATH = _state.state_path("sample_manifest.json")
PATTERNS_PATH = _state.state_path("patterns.json")


def main() -> None:
    from observability.instrument import load_env

    load_env()

    manifest = _state.read_json(MANIFEST_PATH, default={"traces": []})
    patterns = _state.read_json(PATTERNS_PATH, default={"modes": []})

    all_trace_ids = sorted({t["trace_id"] for t in manifest["traces"]})
    confirmed_modes = [m for m in patterns["modes"] if m.get("status") == "confirmed"]

    print(f"[build_labels] {len(all_trace_ids)} traces x {len(confirmed_modes)} modes")

    client = langfuse_io._client()
    now = datetime.now(timezone.utc).isoformat()

    for mode in confirmed_modes:
        name = mode["name"]
        positives = set(mode["example_trace_ids"])
        labels_path = _state.state_path("labels", f"{name}.jsonl")

        written = 0
        for trace_id in all_trace_ids:
            label = 1 if trace_id in positives else 0
            record = {
                "trace_id": trace_id,
                "label": label,
                "source": "human",
                "ts": now,
                "label_id": f"{trace_id}#{uuid.uuid4().hex[:8]}",
            }
            _state.append_jsonl(labels_path, record)
            langfuse_io.write_label_score(
                trace_id=trace_id, mode=name, label=label, client=client
            )
            written += 1

        fail_count = sum(1 for tid in all_trace_ids if tid in positives)
        print(
            f"[build_labels] {name}: {written} labels written "
            f"({fail_count} present / {written - fail_count} absent)"
        )

    print("[build_labels] done")


if __name__ == "__main__":
    main()
