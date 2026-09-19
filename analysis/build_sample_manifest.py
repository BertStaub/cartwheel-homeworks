"""Build ``analysis/state/sample_manifest.json`` for Homework 4, Part B.

Part B ("review at least 100 traces") asks for four distinct selection
batches, each covering the trace collection a different way, with no trace
counted toward more than one batch (see ``homework/module-2/hw4.md``). This
script builds that manifest incrementally, one batch at a time, reusing the
sampling machinery the starter repository already provides in
``analysis/helpers/selection.py`` rather than re-implementing clustering.

Only the 250 Homework 3 support scenarios (``support-*``) are in scope. The
30 pilot scenarios (``pilot-*``, from Homework 1/2) are excluded by request.

Run:
    uv run python -m analysis.build_sample_manifest --batch 1
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Any

from analysis.helpers._state import read_json, state_path, write_json
from analysis.helpers.selection import next_candidates, select
from analysis.review_app.server import _fetch_all_traces

MANIFEST_PATH = state_path("sample_manifest.json")

# Fixed so re-running a batch (or building the next one) picks up
# deterministically rather than reshuffling everything already sampled.
SEED = 7


def _load_support_traces() -> list[dict[str, Any]]:
    """Live, session-merged traces for the 250 support scenarios only."""
    traces = _fetch_all_traces()
    return [
        t
        for t in traces
        if (t["meta"].get("scenario_id") or "").startswith("support-")
    ]


def _load_manifest() -> dict[str, Any]:
    return read_json(
        MANIFEST_PATH,
        default={
            "scenario_pool": "support_scenarios.jsonl (250; pilot scenarios excluded)",
            "seed": SEED,
            "batches": [],
            "traces": [],
        },
    )


def _already_sampled(manifest: dict[str, Any]) -> set[str]:
    """Trace ids (Langfuse hashes) already used in an earlier batch.

    ``select()``'s ``exclude_ids`` matches on ``t["id"]`` (the trace id), so
    exclusion must be keyed the same way -- not on the human-readable
    ``scenario_id`` also stored in the manifest for readability.
    """
    return {rec["trace_id"] for rec in manifest["traces"]}


def _append_batch(
    manifest: dict[str, Any],
    batch_number: int,
    sub_batch: str,
    method: str,
    picks: list[dict[str, str]],
    scenario_id_by_trace_id: dict[str, str],
) -> None:
    """Record one sub-batch: its method (for the report) and its picks.

    ``select()`` identifies picks by ``t["id"]``, which for a merged trace
    record is the Langfuse trace id (a 32-hex hash), not the human-readable
    scenario id (``support-0123``). ``scenario_id_by_trace_id`` translates
    back so the manifest is readable and joins cleanly against the scenario
    JSONL files.
    """
    manifest["batches"].append(
        {
            "batch": batch_number,
            "sub_batch": sub_batch,
            "method": method,
            "count": len(picks),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    for pick in picks:
        trace_id = pick["trace_id"]
        manifest["traces"].append(
            {
                "scenario_id": scenario_id_by_trace_id[trace_id],
                "trace_id": trace_id,
                "batch": batch_number,
                "sub_batch": sub_batch,
                "reason": pick["reason"],
            }
        )


def build_batch_1(manifest: dict[str, Any]) -> None:
    """15 uniformly sampled traces + 15 cluster representatives.

    Clustering runs on the five structural features ``normalize_trace``
    already computes (turn_count, tool_call_count, distinct_tools,
    has_retrieval, tokens) -- a different axis of diversity than the
    product-dimension stratification in batch 2.
    """
    traces = _load_support_traces()
    scenario_id_by_trace_id = {t["id"]: t["meta"]["scenario_id"] for t in traces}
    exclude = _already_sampled(manifest)

    uniform = select(traces, k=15, strategy="random", exclude_ids=exclude, seed=SEED)
    _append_batch(
        manifest,
        batch_number=1,
        sub_batch="uniform_random",
        method="selection.select(strategy='random', k=15)",
        picks=uniform,
        scenario_id_by_trace_id=scenario_id_by_trace_id,
    )

    exclude |= {pick["trace_id"] for pick in uniform}
    # Ask for more than 15: select()'s "diversity" strategy blends cluster
    # representatives (2/3 of k) with a random fill (1/3 of k), and only the
    # cluster-tagged 2/3 belongs in this sub-batch. k=24 -> 16 cluster picks,
    # a safe margin above the 15 we need after slicing.
    diversity = select(traces, k=24, strategy="diversity", exclude_ids=exclude, seed=SEED)
    cluster_reps = [pick for pick in diversity if pick["reason"].startswith("cluster")][:15]
    _append_batch(
        manifest,
        batch_number=1,
        sub_batch="cluster_representative",
        method=(
            "selection.select(strategy='diversity', k=24) on "
            "[turn_count, tool_call_count, distinct_tools, has_retrieval, tokens], "
            "keeping only the cluster-tagged picks"
        ),
        picks=cluster_reps,
        scenario_id_by_trace_id=scenario_id_by_trace_id,
    )


ROLES = ("shopper", "merchant", "support")


def build_batch_2(manifest: dict[str, Any]) -> None:
    """30 traces stratified evenly across the 'role' product dimension.

    10 traces per role, chosen uniformly at random within each role. An even
    split rather than one proportional to the population (roughly
    155/51/44 shopper/merchant/support) is the point: batch 1 already skewed
    heavily shopper (24 of 30), so this batch forces real coverage of
    merchant and support regardless of their natural share.
    """
    traces = _load_support_traces()
    scenario_id_by_trace_id = {t["id"]: t["meta"]["scenario_id"] for t in traces}
    exclude = _already_sampled(manifest)

    for role in ROLES:
        pool = [t for t in traces if t["meta"].get("role") == role]
        picks = select(pool, k=10, strategy="random", exclude_ids=exclude, seed=SEED)
        _append_batch(
            manifest,
            batch_number=2,
            sub_batch=f"role_{role}",
            method=f"selection.select(strategy='random', k=10) restricted to role == '{role}'",
            picks=picks,
            scenario_id_by_trace_id=scenario_id_by_trace_id,
        )
        exclude |= {pick["trace_id"] for pick in picks}


def build_batch_3(manifest: dict[str, Any]) -> None:
    """25 traces from depth search on the two strongest candidate modes found
    in open coding so far (batches 1-2): semantic neighbors of confirmed
    instances, via next_candidates(strategy="enrich")'s bag-of-words cosine
    similarity over trace text. These are retrieval signals, not labels --
    every pick still needs a real open-code pass, including the possibility
    it is a close negative rather than another positive instance.
    """
    traces = _load_support_traces()
    scenario_id_by_trace_id = {t["id"]: t["meta"]["scenario_id"] for t in traces}
    sid_to_trace_id = {sid: tid for tid, sid in scenario_id_by_trace_id.items()}
    exclude = _already_sampled(manifest)

    # Confirmed instances from open coding, as (mode, budget, trace_ids).
    # Most were found via a scenario id already in the manifest; a few from
    # the cluster-representative sub-batch were only ever seen as raw
    # Langfuse trace ids while monitoring annotations live, so those are
    # listed directly.
    depth_targets = [
        (
            "unconfirmed_write",
            13,
            [
                sid_to_trace_id[sid]
                for sid in (
                    "support-0211", "support-0026", "support-0031", "support-0037",
                    "support-0209", "support-0151", "support-0168",
                )
            ],
        ),
        (
            "acts_beyond_scope",
            12,
            [
                sid_to_trace_id[sid]
                for sid in ("support-0039", "support-0150", "support-0178")
            ]
            + [
                "96a9fbbbd659c54b1370f5555467d4f0",
                "914a1ae982f4083181ab49f1bfe75b46",
                "51e9a99182a23017076ed6a9be3fdde2",
                "ea95b1b9c68f8d9902cdf1c6be9a577d",
                "5b8f2f02cebcddb687646d73428bb57a",
                "9e67b3ea8e0bc18723d7ce9741c17e14",
            ],
        ),
    ]

    for mode_name, k, confirmed in depth_targets:
        raw_picks = next_candidates(
            traces,
            mode=mode_name,
            k=k,
            strategy="enrich",
            confirmed_failures=confirmed,
            already_labeled=exclude,
            seed=SEED,
        )
        picks = [{"trace_id": p["trace_id"], "reason": p["signal"]} for p in raw_picks]
        _append_batch(
            manifest,
            batch_number=3,
            sub_batch=f"depth_{mode_name}",
            method=(
                f"selection.next_candidates(mode='{mode_name}', strategy='enrich', k={k}) "
                f"seeded by {len(confirmed)} confirmed instances from open coding"
            ),
            picks=picks,
            scenario_id_by_trace_id=scenario_id_by_trace_id,
        )
        exclude |= {pick["trace_id"] for pick in picks}


def build_batch_4(manifest: dict[str, Any]) -> None:
    """15 final uniformly-sampled traces, to check taxonomy stability.

    Drawn after the taxonomy has stabilized (Part D), excluding every trace
    already used in batches 1-3. A high rate of new consequential modes in
    this batch would mean the taxonomy is not yet stable and another batch
    is warranted (see hw4.md, "Part E, apply the final taxonomy").
    """
    traces = _load_support_traces()
    scenario_id_by_trace_id = {t["id"]: t["meta"]["scenario_id"] for t in traces}
    exclude = _already_sampled(manifest)

    picks = select(traces, k=15, strategy="random", exclude_ids=exclude, seed=SEED)
    _append_batch(
        manifest,
        batch_number=4,
        sub_batch="final_uniform_check",
        method="selection.select(strategy='random', k=15), excluding all 100 previously-used traces",
        picks=picks,
        scenario_id_by_trace_id=scenario_id_by_trace_id,
    )


BATCH_BUILDERS = {1: build_batch_1, 2: build_batch_2, 3: build_batch_3, 4: build_batch_4}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, required=True, choices=sorted(BATCH_BUILDERS))
    args = parser.parse_args()

    manifest = _load_manifest()
    BATCH_BUILDERS[args.batch](manifest)
    write_json(MANIFEST_PATH, manifest)
    print(f"[sample_manifest] batch {args.batch} added; {len(manifest['traces'])} traces total")


if __name__ == "__main__":
    main()
