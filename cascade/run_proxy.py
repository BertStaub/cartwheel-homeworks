"""Run the cascade proxy: the oracle's judge prompt on a cheaper model, plus a confidence.

Run from the repository root:
    uv run python -m cascade.run_proxy --split development
    uv run python -m cascade.run_proxy --split test

Paid: one gemini/gemini-3.8-flash call per example (GEMINI_API_KEY, direct).
The oracle is unsupported_policy_claim-v3; its verdicts are already saved in
cascade/data/split.json, so the oracle is never called here.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from observability.instrument import load_env

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "cascade" / "data"
RESULTS = ROOT / "cascade" / "results"
ORACLE = ROOT / "analysis" / "state" / "judges" / "unsupported_policy_claim-v3.json"
PROXY_MODEL = "gemini/gemini-3.8-flash"

# The monitor's suffix, with one added instruction asking for a confidence.
SUFFIX = (
    "\n\n--- Trace to evaluate ---\n{content}\n\n"
    "First write a critique of the trace against the criterion. Use specific "
    "evidence from the provided trace. Then return result as exactly Pass when "
    "the named failure is absent, or Fail when present. Finally, state your "
    "confidence that your verdict is correct as a number from 0 to 1.\n"
    'Return JSON with the keys "critique", "result" and "confidence".'
)


def build_prompt(content: str) -> str:
    oracle = json.loads(ORACLE.read_text())
    return oracle["prompt_text"] + SUFFIX.replace("{content}", content)


def parse(text: str) -> dict:
    """Return {'verdict': 1 for fail / 0 for pass, 'confidence': float, 'critique': str}."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    row = json.loads(match.group(0))
    result = str(row["result"]).strip().lower().rstrip(".")
    if result not in {"pass", "passed", "fail", "failed"}:
        raise ValueError(f"unexpected result {row['result']!r}")
    confidence = float(row["confidence"])
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence {confidence} outside 0 to 1")
    return {"verdict": int(result.startswith("fail")), "confidence": confidence,
            "critique": str(row.get("critique", ""))}


def run_one(content: str, model: str = PROXY_MODEL) -> dict:
    import litellm

    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": build_prompt(content)}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    usage = response.usage
    return {**parse(response.choices[0].message.content),
            "input_tokens": usage.prompt_tokens, "output_tokens": usage.completion_tokens}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("development", "test"), required=True)
    parser.add_argument("--model", default=PROXY_MODEL)
    args = parser.parse_args()
    load_env()

    examples = json.loads((DATA / "examples.json").read_text())
    split = json.loads((DATA / "split.json").read_text())["split"]
    chosen = [e for e in examples if split[e["trace_id"]] == args.split]

    # The original gemini-3.8-flash results keep their file name.
    suffix = "" if args.model == PROXY_MODEL else "_" + args.model.replace("/", "_")
    out_path = RESULTS / f"proxy_{args.split}{suffix}.json"
    done = json.loads(out_path.read_text()) if out_path.exists() else {}
    for example in chosen:
        if example["trace_id"] in done:
            continue
        try:
            done[example["trace_id"]] = run_one(example["text"], args.model)
        except Exception as error:  # record and continue; rerun picks up the rest
            done[example["trace_id"]] = {"error": f"{type(error).__name__}: {str(error)[:200]}"}
        RESULTS.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(done, indent=1))
    errors = sum("error" in r for r in done.values())
    print(f"Saved {out_path}: {len(done)} examples, {errors} errors")


if __name__ == "__main__":
    main()
