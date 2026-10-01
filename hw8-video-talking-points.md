# HW8 video — talking points (personal prep notes, not a deliverable)

Working notes for the required ≤5 minute video (`homework/module-5/hw8.md`, "Video"):
one continuous screen recording from the failure mode you chose to the test-set
comparison, regenerating one committed number on camera. Not one of the files to
commit. Say it in your own words. The keep/revert and final-selection judgments are
yours; where a reason is listed below, it is the one you gave during the session.

**Ground rule:** every number below comes from a committed file
(`optimize/results/target.json`, `manual.csv`, `gepa-result.json`, `frontier.csv`,
`optimize/state/*.json`, the dated `development-*.json` / `test-configuration-*.json`
results). Say only what you can also point to on screen.

## Timing budget (target ~4:45 total, under the 5:00 limit)

| Beat | What | Target time |
|---|---|---|
| 0 | Intro: one sentence on what HW8 is | 0:15 |
| 1 | The failure mode and why you chose it | 0:40 |
| 2 | The starting result | 0:25 |
| 3 | One change at each layer | 1:00 |
| 4 | The automated search (GEPA) | 0:40 |
| 5 | The final selection | 0:40 |
| 6 | Test-set comparison + regenerate a number | 1:05 |

## Beat 1 — the failure mode

**Show:** `optimize/results/target.json`.

**Say:**
- Target: `unsupported_policy_claim`, requirement `RESP-3` (state when information is
  missing rather than inventing a value), prevalence 0.18 (90 of 500
  `store_predictions` in `analysis/state/judges/unsupported_policy_claim-v3.json`).
- It's the reference judge's mode, not your own HW5 judge's. Your
  `dispute_window_not_checked_against_current_date` judge has no HW6 case that scores
  it, and the handout needs at least one development case that does.
- The three example traces are real, inspectable traces from your Langfuse (not the
  `store-*` IDs, which exist only as IDs): `support-0187` (agent suggests an expired
  window "should be reconsidered"), `support-0241` (cites `cw-returns` and `cw-refunds`
  without retrieving them), `support-0089` (implies a replacement is available).
- Be ready for this: running the frozen judge on 60 of your traces flagged 9, and 7 of
  those were the "within 24 hours" claim. That claim is grounded, because
  `escalate_to_human` returns `sla_hours: 24` and `cw-escalations` says so, but the
  judge only sees retrieved policy documents. So 0.18 likely overstates the true rate.
  Say whether you do.

## Beat 2 — the starting result

**Show:** `optimize/state/starting_version.json`; the starting row in `manual.csv`.

**Say:**
- Split: 10 development cases, 5 test cases (`optimize/state/split.json`, locked). All
  three `unsupported_policy_claim` cases (e-011, e-012, e-013) are in development; none
  are in test.
- Development model `gemini/gemini-3.8-flash`. Starting agent: score 0.6, $1.54 per 100
  conversations, median 8.8 s, prompt hash `b4366aae125d`, commit `497c6f9`.
- `write_pass_5` is empty: none of the 15 cases changes data.
- Failing at baseline: e-006 (store names), e-012 (target), e-014, e-015 (premature
  lookup). e-012 failed on the judge's "24 hours" flag.

## Beat 3 — one change at each layer

**Show:** `optimize/results/manual.csv`.

| Layer | Predicted | Result (dev, 10 cases) | Cost per 100 | Decision |
|---|---|---|---|---|
| Prompt | Fixes e-012 by grounding the 24-hour claim; others unchanged | 0.7 (rerun 0.8) | $1.78 | keep |
| Tool | Fewer "platform does not offer" assertions | 0.8 | $2.21 | revert |
| Harness | One-time gate: retrieve `cw-escalations` before first escalation | 0.8 | $1.79 | revert |

**Say:**
- Prompt: added a Grounding section (state only what you retrieved; cite
  `cw-escalations` before giving a timeframe; no unsupported remedies). e-012 now cites
  `cw-escalations` and passes. In the first run e-011 regressed because the wording
  pushed the agent to assert "we do not offer store credit"; the rerun of the same
  prompt passed it.
- Tool: a `note` in `search_help_center` results ("if no excerpt covers it, say no
  document covers it"). It changed the wording as intended, but cost rose about 24%
  with no score gain. You reverted on cost.
- Harness: step control in `_call`. The SDK copies the context for every tool call, so
  state is keyed by the shared `AuthContext`. The result matched the prompt rerun
  (0.8) at about the same cost; you reverted for no measurable gain.
- With 10 cases and one run each, the same prompt scored 0.7 and 0.8, so differences of
  0.1 are noise. Say that plainly.

## Beat 4 — the automated search

**Show:** `optimize/results/gepa-result.json`, `gepa-summary.json`;
`optimize/state/search_budget.json`.

**Say:**
- Method: GEPA, because the fix is in prompt wording. Reflection model
  `anthropic/claude-opus-4-6`, direct with your key. Budget: 60 of 150 evaluated case
  runs used (capped at `--max-runs 60`); 3 candidates; search scores 0.7, 0.8, 0.8.
- GEPA optimizes the mean over all 10 development cases, so it added text for e-014 and
  e-015 (clarify before acting), e-006 (include store names), not for your target.
- Rerun of the best candidate: 0.9, $1.74, median 12.7 s. But e-006 failed with
  `MaxTurnsExceeded`: `search_products` returns no store name (TOOL-12 is unmet), so the
  agent looped trying to find one. You asked for it trimmed.
- Trimmed candidate (store-name clause removed by hand, a labeled new candidate made
  after seeing the first rerun): 0.8, $1.69, median 8.6 s, prompt `96681bfc90c3`.
- Leakage check you asked for: longest shared word sequence with any case message was 3
  words ("I need help", with e-014).

## Beat 5 — the final selection

**Show:** `optimize/state/final_version.json`.

**Say:**
- Final: layer `prompt`, methods `gepa` and `manual`, commit `b1aadbe`, hash
  `96681bfc90c3`. Three development runs of this prompt: 0.8, 0.9, 0.7. The saved record
  uses the latest run (0.7) so it wasn't cherry-picked; the mean is 0.8.
- Cost and latency swung on the same prompt: $1.69 / 8.6 s, $2.22 / 14.6 s, $1.70 /
  9.2 s.
- Your reason from the session: it combined GEPA's e-015 gain with the target fix at the
  lowest cost and time of the prompt variants. Target cases passed 2/3, 3/3 and 1/3 in
  the three runs, so no variant was measurably better on the target. Decide how you
  want to put that.

## Beat 6 — the test set

**Show:** `optimize/results/frontier.csv`.

| # | Configuration | Score | Cost per 100 | Median time | Dominated |
|---|---|---|---|---|---|
| 1 | Starting, `gpt-5.5` | 0.0 | $1.32 | 5.6 s | no |
| 2 | Starting, `claude-opus-4-6` | 0.4 | $7.35 | 22.8 s | yes |
| 3 | Starting, `gemini-3.8-flash` | 0.4 | $2.95 | 14.6 s | no |
| 4 | Final, `gemini-3.8-flash` | 0.4 | $2.96 | 16.3 s | yes |

**Say:**
- Configurations 1–3 isolate the model; 3 vs 4 isolate the agent change.
- Configuration 4 equals 3 on every case: e-003 and e-010 pass; e-001, e-002 (agent
  still refunds past the window) and e-005 (no store name) fail. The test set has no
  target-mode case, so it can only show your prompt broke nothing. 4 is "dominated" by
  $0.005, which is noise.
- Claude is dominated: the same score as Gemini at 2.5× the cost.
- **The `gpt-5.5` row is not a valid measurement.** It used 4,577 input tokens in total
  and never called a tool. A dev-case diagnosis (e-004) and a one-call trivial-tool
  test both ended with `finish_reason: stop`, no tool call, and 0 reasoning tokens under
  `reasoning_effort="high"` on the gateway's chat-completions route. The 0.0 reflects the
  route, not the model. The route change was made after your Claude/Gemini model checks
  had already passed, and the first gpt-5.5 gateway check (1 request, no tool call) was
  the early sign.

## Regenerating a committed number on camera

Easiest and free: `uv run python -m optimize.frontier run`. Every configuration is
already complete, so it makes **no model calls**; it re-reads the saved results and
rewrites `frontier.csv`. Then `git diff optimize/results/frontier.csv` should be empty
(only `optimize/state/test_run.json` gets a new `completed_at` timestamp).

## Things to be ready for if someone looks closely

- Two model checks (Claude, Gemini) ran direct before the gateway routing existed;
  Gemini stays direct on your personal key; the frozen Claude judge and GEPA's reflection
  model also stay direct, by your choice.
- GLM-5.2 was replaced by Gemini because the Together key was invalid.
- Gemini prices ($0.75 / $3.75) exclude context caching.
- Two tests fail in the full suite (`test_m2_run_judge_persists_store_predictions_for_prevalence`,
  `test_m2_failure_report_matches_artifact_l_schema`); they fail identically on earlier
  commits, so they aren't from HW8 changes.
- e-006 and e-005 can't pass: `search_products` doesn't return the store name.
