# HW6 video — talking points (personal prep notes, not a deliverable)

Working notes for recording the required ≤5 minute video (`homework/module-3/hw6.md`,
"Video" section). Not one of the "Files to commit" — a script to read from, in your
own words. Classifying the cases and explaining what the numbers mean is yours; the
facts below are things you can point to on screen, not conclusions reached for you.

**Ground rule:** every fact below comes from `eval_cases/cases.jsonl`,
`eval_results/*.json`, `ci-runs.json`, or the GitHub Actions runs themselves (the two
run conclusions and the revert-run summary table were re-checked against GitHub, not
only copied from `ci-runs.json`). Say only what you can also point to on screen.

## Timing budget (target ~4:40 total, under the 5:00 limit)

| Beat | What | Target time |
|---|---|---|
| 1 | The 15 cases and the failure modes they cover | 0:50 |
| 2 | One regression and one capability case, with baselines | 1:00 |
| 3 | pass@k and pass^k, using your numbers | 1:00 |
| 4 | The two GitHub Actions runs, and the second result | 1:10 |
| 5 | Capability result after 5, 10, 15 runs | 0:40 |

## Beat 1 — the cases and the failure modes

**Show:** `eval_cases/cases.jsonl` (15 lines).

**Say:**
- 15 cases (the minimum is 10) across 5 failure modes:

| mode | cases | regression / capability |
|---|---|---|
| `refund_proceeds_past_eligibility_window` | e-001 to e-004 | e-003, e-004 / e-001, e-002 |
| `store_id_shown_instead_of_name` | e-005 to e-007 | e-007 / e-005, e-006 |
| `store_override_policy_not_cited` | e-008 to e-010 | e-010 / e-008, e-009 |
| `unsupported_policy_claim` | e-011 to e-013 | e-013 / e-011, e-012 |
| `premature_help_lookup` | e-014, e-015 | e-014 / e-015 |

- 6 regression cases, 9 capability cases.
- Four of the five modes appear in your HW4 taxonomy (`analysis/state/patterns.json`).
  `unsupported_policy_claim` does not — it's the reference-judge mode from the HW5
  reference patch, so say that plainly instead of calling it a HW4 mode.
- Exact facts use code checks (`tool_called`, `no_refund_row`, `reply_contains`,
  `no_investigation_tools`, `reply_asks_question`). Only the three
  `unsupported_policy_claim` cases use a judge, and it's the reference judge, not
  the `dispute_window_not_checked_against_current_date` judge you built in HW5 — no
  case references that one.
- The first 10 cases came first (commit `62d68f2`); e-011 to e-015 were added later
  (`5a612af`). The revert run's summary table (Beat 4) lists exactly e-001 to e-010.

## Beat 2 — one regression, one capability, with five baseline runs

**Show:** the `kind` and `baseline_pass_rate` fields in `cases.jsonl`.

**Say, reading off the file:**
- Regression = five of five baseline passes (no `baseline_pass_rate` stored):
  e-003, e-004, e-007, e-010, e-013, e-014.
- Capability = at least one baseline failure, with the observed fraction recorded:

| case | baseline | | case | baseline |
|---|---|---|---|---|
| e-001 | 0.2 | | e-009 | 0.4 |
| e-002 | 0.0 | | e-011 | 0.6 |
| e-005 | 0.0 | | e-012 | 0.2 |
| e-006 | 0.0 | | e-015 | 0.2 |
| e-008 | 0.6 | | | |

- Pick one of each to show on screen. e-007 (regression) is the natural one because
  Beat 4 targets it; e-011 or e-009 (capability) because Beat 5 uses them.

## Beat 3 — pass@k and pass^k with your numbers

**Show:** `tests/eval/passk.py`; `eval_results/e-011-15.json`.

**Say (computed with your own `pass_at_k` / `pass_hat_k` on e-011, n=15, 9 passes):**
- pass@k is the chance at least one of k attempts succeeds; pass^k is the chance all
  k succeed.

| e-011, n=15, c=9 | k=1 | k=3 | k=5 |
|---|---|---|---|
| pass@k | 0.600 | 0.956 | 0.998 |
| pass^k | 0.600 | 0.185 | 0.042 |

- Same observations, opposite readings: with 5 tries it almost surely succeeds once,
  but almost never succeeds every time. That is the capability-versus-reliability
  distinction the handout asks about.
- Regression gate: all five runs must pass. A case at 5/5 has pass^5 = 1.0; the same
  case at 4/5 has pass^5 = 0.0, which is why e-010 at 4/5 blocked in Beat 4.

## Beat 4 — the two GitHub Actions runs

**Show:** `ci-runs.json`; both run URLs; PR #1 (`hw6/harbor-evals`, merged).

**Say:**
- Regression run: `.../actions/runs/36245086698`. A temporary prompt instruction told
  the agent to refer to stores only by numeric `store_id`. Target case e-007 failed
  0/5 and the CI decision was `block` (per `ci-runs.json`); the other regression
  cases e-003, e-004, e-010 were recorded at 5/5.
- Revert run: `.../actions/runs/36245957878`. Instruction reverted (`72b660d`).
  e-007 went back to 5/5. In the summary table pulled from the run:
  e-003, e-004, e-007 passed 5/5, **e-010 passed 4/5 and was `block`**.
- The second result, as you recorded it in `ci-runs.json`: e-010 was untouched by the
  injection and the revert, and had been 5/5 in its baseline, so you recorded it as
  new evidence of sampling variance and didn't rerun the same commit (the handout's
  instruction).
- Be ready for this, because it's visible on screen: the **`offline checks` job
  failed in both runs**, not just Harbor. It's two tests that also fail locally,
  identical both times: `tests/test_cli.py::test_non_openai_direct_run_does_not_export`
  and `tests/test_hw_holes.py::test_m2_failure_report_matches_artifact_l_schema`. They
  aren't related to the injected regression, but `ci-runs.json` doesn't mention them,
  so decide whether to say it.

## Beat 5 — capability result after 5, 10, and 15 runs

**Show:** `eval_results/e-011-15.json` (and `e-009-15.json` if you show both).

**Say, reading off the files:**

| case | n | passes | pass@1 | pass@3 | pass@5 |
|---|---|---|---|---|---|
| e-011 | 5 | 4 | 0.80 | 1.00 | 1.00 |
| e-011 | 10 | 6 | 0.60 | 0.967 | 1.00 |
| e-011 | 15 | 9 | 0.60 | 0.956 | 0.998 |
| e-009 | 5 | 5 | 1.00 | 1.00 | 1.00 |
| e-009 | 10 | 8 | 0.80 | 1.00 | 1.00 |
| e-009 | 15 | 13 | 0.867 | 1.00 | 1.00 |

- At fixed n, pass@k doesn't decrease as k grows (visible in each row's progression).
- At fixed k, pass@1 moved between n=5 and n=10 for both cases; whether 15 runs
  counts as a "stable" estimate is the call the handout asks you to make, and
  say so explicitly if you think it isn't.
- Worth noticing, since a viewer may ask: e-009's baseline was 0.4 (2 of 5), but the
  first 5 trials of its 15-run job were 5 of 5, and it passed 5/5 in the revert run.
  e-011's baseline was 0.6 and the first 5 of its 15-run job were 4 of 5. The
  handout only requires one capability case; you ran two.
