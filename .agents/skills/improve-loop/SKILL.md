---
name: improve-loop
description: Improve one Cartwheel failure mode by editing allowed agent files, scoring each edit on the Homework 8 development cases, and keeping only edits that raise the score, within the 150 run search budget.
---

# Improve loop

Use the development cases only. Never run `uv run python -m optimize.runner --split test` or `uv run python -m optimize.frontier` during the improvement loop.

1. Read `optimize/allowlist.txt`, `optimize/state/split.json`, `optimize/state/search_budget.json`, and `optimize/results/target.json`. Stop and name the missing file when one is absent.
2. Read `optimize/results/latest-development.json`, and choose one failing case whose failure modes include the target failure mode.
3. Change files from one layer only. The allowed layers are the prompt in `agent/agent.py`, the tools in `agent/tools.py`, or the agent harness in the other allowlisted files. Do not edit files outside `optimize/allowlist.txt`.
4. Do not edit `eval_cases/`, `tests/`, `analysis/state/judges/`, or `optimize/state/`. Do not weaken the permission checks in `agent/auth.py`.
5. Commit the change, then run:

   ```bash
   uv run python -m optimize.runner --split development --candidate <short-name> --search
   ```

   One evaluated case run uses one unit of the 150 run budget, and the command refuses a run that would exceed the budget.
6. Compare the new `score` and `write_pass_5` with the current best result. Keep the change only when the score improves and `write_pass_5` does not drop; otherwise revert the commit.
7. Stop when the budget is exhausted, when two consecutive changes do not improve the score, or when one candidate passes every development case.

After every candidate, append one JSON object to `optimize/results/improve-loop.jsonl`. Record `candidate`, `changed_layer`, `changed_files`, `rationale`, `development_score`, `write_pass_5`, `decision`, `git_commit`, and `result_file`.

Report the changed layer, the files changed, the development results compared, the remaining budget, and any failures that remain.
