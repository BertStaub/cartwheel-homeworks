# HW7 video — talking points (personal prep notes, not a deliverable)

Working notes for recording the required ≤5 minute video (`homework/module-3/hw7.md`,
"Video" section) and for writing `monitoring/README.md`'s four answers. Not one of
the "Files to commit" — a script to read from, in your own words. The interpretation
in both places (README's four questions, and anything you say about what the
numbers mean) is yours; everything below is facts you can point to on screen, not
a conclusion already reached for you.

**Ground rule:** every fact below is pulled directly from the committed files
(`monitoring/config.json`, `monitoring/history.jsonl`, `scenarios/monitoring_scenarios.jsonl`,
`scenarios/hw7-after-results.jsonl`, Langfuse scores) or the live GitHub Actions
run — say only what you can also point to on screen.

## The six required video beats

### Beat 1 — the two periods, shared scenario set and model

**Show:** `scenarios/monitoring_scenarios.jsonl` (50 lines, `wc -l`).
`monitoring/config.json`'s `periods` block.

**Say:**
- Both periods run the same 50 scenarios (the subset saved in Homework 3) on the
  same Cartwheel model, `claude-opus-4-6`.
- **before**: the original Homework 3 run, `2026-09-14T22:59:54Z` →
  `2026-09-15T00:40:37Z` in Langfuse.
- **after**: one fresh run of the current agent, `2026-09-28T18:48:23Z` →
  `2026-09-28T19:01:02Z`, written to `scenarios/hw7-after-results.jsonl`
  (50/50 completed).
- One real wrinkle worth mentioning: the original Langfuse window contained
  52 traces for 50 scenarios. `support-0238` (turn_count=2) legitimately has
  two traces. `support-0050` had two traces because the first attempt never
  produced a final output (`output: null`, 6 observations) — a dead run, not
  a second turn. `monitoring/run.py` drops the incomplete one and keeps the
  completed retry, so the conversation record matches the single completed
  entry in `scenarios/final-results.jsonl`.

### Beat 2 — the random sample and risk groups

**Show:** `monitoring/config.json` (`random_rate: 0.2`, `risk_groups: ["policy_lookup"]`,
`threshold: 0.15`). `monitoring/sample.py`'s `DEFAULT_RISK_GROUPS`.

**Say:**
- Frozen judge: `unsupported_policy_claim-v3` (`claude-opus-4-6`), the reference
  judge from the Homework 5 patch — say plainly that this is the reference judge,
  not a judge you personally built and froze.
- Random sample: 10 of the 50 scenarios per period, drawn with `random.Random(seed=7)`
  — the **same 10 scenario IDs in both periods** (`support-0019, 0027, 0040, 0049,
  0110, 0126, 0135, 0174, 0189, 0217`), so it's a paired before/after comparison,
  not two independent slices.
- Risk group `policy_lookup`: every one of the 27 traces that called `get_policy`
  or `search_help_center`, judged in full both periods (not sampled, so it doesn't
  feed the rate estimate — it's for inspection).
- One development fix worth mentioning: the first implementation built each
  period's 50 conversation records in whatever order Langfuse's trace-id sort
  produced. Trace IDs are fresh per run, so the same seed picked a *different*
  10 scenarios each period (only 3 of 10 overlapped) — the before/after
  comparison wasn't actually paired. Fixed by sorting records by `scenario_id`
  before sampling, so list position — and the seeded sample — is stable across
  periods. Caught this because the first before/after numbers looked
  suspiciously identical.

### Beat 3 — raw and corrected estimates with their interval

**Show:** `monitoring/history.jsonl` (two lines).

**Say, reading straight off the file:**

| period | raw | corrected | 95% CI | failure_sensitivity | pass_specificity |
|---|---|---|---|---|---|
| before | 0.20 (2/10) | 0.1888 | [0.0, 0.584] | 0.833 | 0.947 |
| after | 0.10 (1/10) | 0.0607 | [0.0, 0.368] | 0.833 | 0.947 |

- `raw` is the uncorrected flag rate on the 10 random traces only.
- `corrected` is the Rogan-Gladen estimate, adjusting for the judge's own
  error rate.
- sensitivity/specificity are fixed properties of the frozen judge (from its
  50-trace held-out test set: 12 Fail / 38 Pass), identical in both rows
  because it's the same judge both times, not re-measured per period.
- Which specific traces flagged Fail in the random sample: `support-0027`
  and `support-0049` in **before**; only `support-0049` in **after**.
  `support-0049` flagged Fail in *both* periods.

### Beat 4 — the Langfuse dashboard

This one's yours to build (Settings → Dashboards in the Langfuse UI) and show
live — no prep notes to give here beyond what's already committed as scores:
`unsupported_policy_claim_verdict` (10/period), `_risk_verdict` (27/period),
`_corrected_prevalence` (1/period, comment carries the CI).

### Beat 5 — one successful scheduled workflow run

**Show:** `.github/workflows/monitor.yml`. The GitHub Actions run at
`https://github.com/BertStaub/cartwheel-homeworks/actions/runs/36487306613`.

**Say:**
- Triggered manually (`workflow_dispatch`), ran on a self-hosted runner (your
  machine, since Langfuse is self-hosted on `localhost`).
- Command: `uv run python -m monitoring.run --last-hours 24 --confirm`.
- It correctly found zero eligible conversations (Cartwheel has no live
  traffic outside scenario runs) and recorded a zero count *without* calling
  the judge — the exact behavior the handout requires for an empty window.
- Uploaded `monitor-output` (history.jsonl + prevalence.svg) as a workflow
  artifact.

### Beat 6 — what happens after a threshold crossing

**Say (this is the handout's own stated policy, not your judgment call):**
- A threshold crossing (corrected prevalence ≥ 0.15) should start error
  analysis on the flagged traces, and confirmed failures should become new
  evaluation cases in the Homework 6 suite.
- Whether *this* run's numbers actually cross that line, and what you'd
  personally do next, is the part to answer live, in your own words.

## Groundwork for `monitoring/README.md`'s four questions

Facts for each, not the answers:

1. **Did the corrected estimate move?** 0.1888 → 0.0607, on the same 10 paired
   scenarios.
2. **Do the intervals support a conclusion?** Both 95% CIs span roughly
   [0.0, 0.4-0.6] and heavily overlap. The width comes from two stacked small
   samples: 10 random traces per period, and only 12 labeled Fail examples in
   the judge's own held-out test set.
3. **What did the risk groups show that random didn't?** The 27-trace
   `policy_lookup` group flagged 3/27 (before) and 4/27 (after) — not a rate
   estimate (it's not random), but it names specific repeat offenders:
   `support-0090` flagged Fail in the risk group in *both* periods, and
   `support-0027` flagged in both the random sample and the risk group in
   *before*. That's traceable, inspectable evidence the random 10-sample
   alone doesn't hand you.
4. **Action on a threshold crossing?** Quoted directly from the handout in
   Beat 6 above — error analysis on the flagged traces, confirmed failures
   become new Homework 6 evaluation cases.
