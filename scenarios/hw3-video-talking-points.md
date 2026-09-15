# HW3 video — talking points (personal prep notes, not a deliverable)

Working notes for recording the required ≤5 minute video (`homework/module-1/hw3.md`,
"Video" section). Not one of the "Files to commit" — this is just a script to read
from. The video itself, and the self-assessment, are yours to record; nothing here
should be read verbatim on screen, and you should say it in your own words.

**Ground rule from the handout:** "Every statement in the video must agree with the
committed files and the Langfuse traces shown on screen." Every fact below was
pulled directly from the actual committed files and verified against the live
database or Langfuse — say only what you can also point to on screen.

## Timing budget (target ~4:30 total, under the 5:00 limit)

| Beat | What | Target time |
|---|---|---|
| 0 | Intro: one sentence on what HW3 is | 0:15 |
| 1 | Pilot failure + expected result + evidence | 1:10 |
| 2 | A final scenario you revised | 0:55 |
| 3 | One complete final trace | 1:10 |
| 4 | Regenerate the scenario-id count + close | 0:40 |

## Beat 1 — a pilot scenario that failed

**Scenario:** `pilot-0001` (shopper, order_status, well_specified, order #4127).

**Show, in this order:**
1. `scenarios/pilot_scenarios.jsonl` — find `pilot-0001`, read the `opening_message`
   and the `expected` block on screen.
2. The Langfuse trace for it — trace id `d8d85a66fd5471b7aa51b6f9f87d217d`
   (open `http://localhost:3000`, project `cartwheel-dev`, paste the trace id into
   the trace search, or use the traceviewer at `http://localhost:8030` and search
   scenario `pilot-0001`). Show the `list_my_orders` tool call's result panel, then
   scroll to the final assistant message.
3. `scenarios/pilot_review.jsonl` — find the `pilot-0001` row, read `evidence` on
   screen.

**Say (in your own words):**
- The opening message: *"I'm checking in about an order I placed with Blue Heron
  Ceramics a couple months ago... haven't heard anything."*
- Expected result (from `SPEC.md`/DB): order 4127 is delivered 2026-06-19, $84.00,
  and within the return window — grounded in `orders.id=4127`, not a guess.
- What actually happened: the `list_my_orders` tool call **did** return order 4127
  in its results, but the agent's final reply said *"the search didn't return any
  matches for 'Blue Heron Ceramics'"* and asked the user for an order number instead.
- That's the failure: the correct data was already in the tool result, but the
  model didn't use it. `scenario_valid: true`, `confirmed_failure: true` in the
  review file, with that exact tool-vs-reply mismatch as the recorded evidence.

## Beat 2 — a final scenario you revised after review

**One honest framing note before you record this:** the 15-scenario review file
(`scenarios/support_review.jsonl`) records this scenario's decision as `accept`,
not `revise` — because the fix happened *before* the formal 15-sample review, not
during it. While preparing that review, a systemic defect was found: every
`refund`- and `cancellation`-intent scenario (73 of 250) had opening messages that
never actually asked for a refund or cancellation, just a generic status check.
All 73 were regenerated with grounded facts before the review sample was shown.
It's fair to call this "a scenario you revised," but say it accurately: found
during review prep, fixed by regeneration, then confirmed accepted — don't imply
the JSONL says `revise` when it says `accept`.

**Scenario:** `support-0213` (shopper, refund, boundary, order #693).

**Show:**
- The current text in `scenarios/support_scenarios.jsonl` for `support-0213`.
- Read the "before" text out loud (it's below — no need to dig up the git diff on
  screen unless you want to; reading it is enough):
  - **Before:** *"Order #693 - Slim Daypack, Trailhead Supply, $257.75, ordered
    ~1mo. Need status update."*
  - **After (current):** *"Order #693. Slim Daypack. Trailhead Supply. $257.75.
    About a month ago. Refund requested."*
- The `expected` block: refund denied, order is past the 30-day return window for
  Trailhead Supply (order 693 delivered 2026-05-31, and the world date is
  2026-07-01 — 31 days later, one day past the window).

**Say:**
- The original message only asked about order status — it never requested a
  refund at all, even though the whole point of the scenario is to test the
  30-day refund-window boundary.
- Caught this while sampling scenarios for the 15-review, traced it to all 54
  refund and 19 cancellation scenarios sharing the same problem, and regenerated
  just the request text (not the underlying order data or expected outcome) for
  all 73, grounding each one back in a fresh database lookup.

## Beat 3 — one complete final trace

**Scenario:** `support-0176` (shopper, `return_deadline`, challenge,
`dq-order-missing-delivery-date`, order #8002).

*(Any completed trace works for this beat — this one is a good pick because it's
short, single-turn, and ties directly to one of the six seeded damaged records,
which makes for an easy on-screen story. If you'd rather show something simpler,
`support-0071` — a one-tool product search — is the cleanest possible example.)*

**Show:**
- Trace id `5052763848a44654168f2f9ad06c7a3c` in Langfuse (or the traceviewer).
- Point at the `cartwheel.scenario_id` attribute = `support-0176`.
- Scroll through the tool activity: `get_order`, `get_policy`,
  `search_help_center`, `escalate_to_human`.
- The model name shown on the generation span: `anthropic/claude-opus-4-6`.

**Say:**
- Order #8002 is one of the six deliberately damaged seed records — its status is
  `delivered` but it has no `delivered_at` date, so there's no way to compute a
  return deadline from it.
- Expected outcome: the agent should not invent a return deadline from missing
  data. What it actually did: called `get_order`, then `get_policy` and
  `search_help_center`, then escalated to a human via `escalate_to_human` rather
  than fabricating a deadline — matching the expected outcome.

## Beat 4 — regenerate the scenario count, then close

**Run on screen:**
```bash
jq '[.traces[].cartwheel_scenario_id] | unique | length' traces/support_traces.json
```
Should print `250`.

**Say:**
- 250 unique final scenario identifiers exported, matching all 250 scenarios in
  `scenarios/support_scenarios.jsonl`.
- One-sentence close: pilot found real failures, the 250-scenario set is
  validated and grounded, and the traces are ready for Homework 4's failure
  analysis.

## Facts you can cite if asked, all verified against the live DB or committed files

- Pilot: 30 scenarios run, 8 confirmed failures (`pilot-0001, 0002, 0008, 0013,
  0017, 0021, 0022, 0024`) — well above the required minimum of 5.
- Final set: 250 scenarios, 175 coverage / 75 challenge (30 of which are the six
  damaged records × 5 each), validated with
  `uv run python -m scenarios.validate scenarios/support_scenarios.jsonl --final`.
- Final run: all 250 completed (`jq -s 'group_by(.status)...'` → one group,
  `completed`, count 250). One scenario (`support-0050`) needed a `--resume` after
  its first attempt hit a genuine upstream provider timeout
  (`litellm.Timeout... time taken=2011.922 seconds`) — order #6360 was confirmed
  unmutated before the resume, so nothing was double-run.
- Export: 259 trace records for 250/250 unique scenario ids (the extra 9 = the 8
  multi-turn scenarios' followup traces + the one orphaned timeout trace from the
  killed `support-0050` attempt).
