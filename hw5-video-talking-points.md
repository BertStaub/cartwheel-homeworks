# HW5 video — talking points (personal prep notes, not a deliverable)

Working notes for recording the required ≤5 minute video (`homework/module-2/hw5.md`,
"Part E"). Not one of the "Files to commit" — just a script to read from. Say it in
your own words, don't read verbatim on screen.

**Ground rule:** every fact below is pulled directly from the committed files
(`analysis/state/patterns.json`, `analysis/prompts/`, `analysis/report/`,
`analysis/state/judges/`) — say only what you can also point to on screen.

## Timing budget (target ~4:40 total, under the 5:00 limit)

| Beat | What | Target time |
|---|---|---|
| 0 | Intro: one sentence on what HW5 is | 0:15 |
| 1 | The failure mode and its boundary | 0:40 |
| 2 | Label collection, briefly | 0:20 |
| 3 | One development disagreement and how you responded | 1:25 |
| 4 | Test TPR, TNR, confidence intervals | 0:40 |
| 5 | Recalculate test metrics live from saved predictions | 0:45 |
| 6 | Would you use the judge | 0:35 |

## Beat 1 — the failure mode and its boundary

**Show:** `analysis/state/patterns.json`, the `dispute_window_not_checked_against_current_date`
entry (built in HW4, reused here). `analysis/prompts/dispute_window_not_checked_against_current_date-v1.txt`,
the "What this judge does NOT evaluate" section.

**Say:**
- Chosen mode: does the reply correctly resolve a computed **dispute-window**
  deadline (60 days after delivery, `cw-disputes`) against the current date —
  not the *return/refund* window, a different policy entirely.
- Disqualified the other 6 HW4 modes because 3 are already code-checked
  (no judge needed) and the remaining judge-evaluator modes had far fewer
  confirmed Fail examples than this one (12 of 30 needed, the closest to the
  minimum).
- Boundary: a trace is Pass if no specific deadline is ever asserted, or if
  the deadline is asserted and correctly resolved, or if the reply honestly
  admits it can't determine today's date. Only a false or dangling assertion
  is a Fail.

## Beat 2 — label collection

**Show:** `analysis/state/hw5_labels/dispute_window_not_checked_against_current_date.jsonl`
(186 lines), `analysis/run_dispute_scenarios.py` / `_2.py`.

**Say:**
- Needed 30 Pass and 30 Fail; had only 12 confirmed Fail from HW4's 123-trace
  review, and organic semantic search over the unreviewed pool found zero
  more in 24 tries.
- Every order in the seeded database is already past the 60-day dispute
  window (same root cause as HW4's `TOOL-11`), so generated 39 new targeted
  conversations raising a dispute on real orders and ran them live through
  Cartwheel — no need to hunt for boundary cases, every order qualified.
- Final: 186 labels, 154 Pass / 32 Fail.

## Beat 3 — one development disagreement and how you responded

**Show:** `diff analysis/prompts/dispute_window_not_checked_against_current_date-v0.txt
analysis/prompts/dispute_window_not_checked_against_current_date-v1.txt`.
`analysis/report/dev-dispute_window_not_checked_against_current_date-v0.json`
vs `-v1.json`.

**Say:**
- v0 on dev (75 traces): TPR 0.968, TNR 1.0, 2 disagreements — both the
  judge saying Fail where the human label said Pass.
- One disagreement (trace `f90c08...`) revealed a real prompt gap: the reply
  said *"if today is on or before March 29, the dispute window is still
  open. (I don't have today's exact date in my session, but you can confirm
  on your end.)"* — an honest hedge, which the Part A rules explicitly call
  a Pass. The judge's critique quoted only the dangling-conditional half of
  the sentence and never engaged with the admission right after it.
- Fixed the prompt (v1): strengthened the honest-hedge rule to explicitly
  say "check the sentence right after" a conditional, and added a fourth
  few-shot example demonstrating exactly this pattern.
- v1 on dev: TPR 1.0, TNR 1.0, zero disagreements. One revision, well
  within the "at most two" budget.
- (Second disagreement, `51e9a99...`/support-0009, is worth a one-line
  mention: it revealed a genuinely mislabeled trace from HW4's original
  review — not a prompt problem, so it was fixed by flipping the label
  instead. `analysis/state/hw5_labels/...jsonl` keeps the flip's history
  via `superseded_by` rather than silently overwriting it.)

## Beat 4 — test TPR, TNR, confidence intervals

**Show:** `analysis/report/test-dispute_window_not_checked_against_current_date-v1.json`.

**Say:**
- Froze v1, ran it once on the 74 held-out test traces (61 Pass / 13 Fail).
- TPR 0.967 [0.888, 0.991], TNR 1.0 [0.772, 1.0], agreement 0.973.
- Two test disagreements exist (`768eb97c...` is support-0039, your own
  HW4 close-negative example — a real, appropriately hedged reply the judge
  still missed, because the hedge was phrased differently from the one
  example added in v1). Per the handout, these are reported, not
  iterated on — no v2 after seeing test results.

## Beat 5 — recalculate test metrics live from saved predictions

**Show:** run this on screen (no live model call, purely reads cached
predictions and labels from disk):

```bash
uv run python3 -c "
from analysis.helpers import judge_alignment
import json
print(json.dumps(judge_alignment('dispute_window_not_checked_against_current_date-v1', split='test'), indent=2))
"
```

**Say:**
- Same numbers as the saved report — this is deterministic recomputation
  from the cached predictions in `analysis/state/judges/`, not a re-run of
  the model.

## Beat 6 — would you use the judge?

**Say:**
- Leaning yes, as a triage/flagging tool for human review, not an
  auto-decision gate. TPR is strong and TNR is perfect on both splits, but
  the TNR confidence interval stays wide ([0.772, 1.0] on only 13 test Fail
  examples) — genuine uncertainty about the true Fail-detection rate at this
  sample size.
- The honest-hedge rule generalizing to one phrasing but not another
  (support-0039) is a real, documented limitation — worth one more round of
  dev-set revision (with fresh dev data, not the touched test set) before
  trusting this judge at higher stakes than triage.

## Facts you can cite if asked, all verified against committed files

- Judge model: `gemini-flash` (not `gpt-4o-mini` as the handout names —
  substituted because no working OpenAI key was available; noted here and
  in `analysis/run_judges.py`'s `JUDGE_MODEL` constant).
- 186 total labels (154 Pass / 32 Fail): 123 carried over from HW4
  (polarity-converted), 24 from organic search (all Pass), 39 from two
  targeted live-scenario batches (20 Fail / 19 Pass).
- Split: 20% train (37) / 40% dev (75) / 40% test (74), seed 7.
- One prompt revision (v0 → v1); one label correction (support-0009,
  Pass → Fail, documented with a `flip_reason`).
- Total judge cost across both dev runs and the test run: **$0.12**
  ($0.08 for v0 on dev, $0.02 for v1 on dev, $0.02 for v1 on test —
  recorded in each DocETL execution summary this session, not committed
  anywhere but worth citing if asked about cost).
