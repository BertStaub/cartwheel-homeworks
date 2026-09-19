# HW4 video — talking points (personal prep notes, not a deliverable)

Working notes for recording the required ≤5 minute video (`homework/module-2/hw4.md`,
"Video" section). Not one of the "Files to commit" — this is just a script to read
from. The video itself is yours to record; nothing here should be read verbatim on
screen, say it in your own words.

**Ground rule:** every fact below is pulled directly from the committed files
(`analysis/state/patterns.json`, `analysis/report/review_summary.md`,
`analysis/report/workshop_notes.md`) — say only what you can also point to on screen.

## Timing budget (target ~4:40 total, under the 5:00 limit)

| Beat | What | Target time |
|---|---|---|
| 0 | Intro: one sentence on what HW4 is | 0:15 |
| 1 | One interface decision made after inspecting traces | 0:35 |
| 2 | One Workshop suggestion, accept/revise/reject | 0:35 |
| 3 | Two failure modes, one trace each, one SPEC tie | 1:35 |
| 4 | One taxonomy revision | 0:40 |
| 5 | One rejected search suggestion + the boundary | 0:35 |
| 6 | New modes found in the final 15 traces | 0:25 |

## Beat 1 — an interface decision made after inspecting traces

**Show:** `analysis/report/interface_comparison.md`, the "design changed" section.
Open the review app (`analysis/review_app/`), pick any multi-turn scenario, scroll
the conversation to show it's one continuous thread.

**Say:**
- Cartwheel opens one Langfuse trace per turn, so the reference view shows a
  multi-turn conversation as several disconnected traces with no visible link
  between them — the biggest friction point from the manual Langfuse review pass.
- The interface fixes this at the data layer: every trace carries a
  `cartwheel.session_id`, and the server merges same-session traces into one
  ordered conversation before the UI ever sees them — not just a display trick.

## Beat 2 — a Workshop suggestion and your decision

**Show:** `analysis/report/workshop_notes.md`, the "genuine uncertainty" section.
Open Workshop (`localhost:5899`) and find run `8b6e24809cfdffcbbe0ca998b2209396`
(`workshop-05-support-refund`) if it's still there, or just read the quote on screen.

**Say:**
- Ran 8 fresh scenarios through the live, newly-instrumented server and inspected
  them in Workshop's raw trace view.
- One reply said *"a human support agent will need to review and approve it before
  the funds are released"* for a queued refund. Accepted it as another instance of
  the `overstates_write_status` mode, but flagged real uncertainty: it could also
  just be describing the process requirement (review is mandatory), not asserting
  the outcome (approval) is certain — a softer case than the mode's other examples.
- No wholly new failure category came out of the Workshop pass — treated that as
  confirmation the taxonomy generalizes to fresh, out-of-corpus runs, not a
  shallow search.

## Beat 3 — two failure modes, one trace each, one SPEC tie

**Mode A: `overstates_write_status`.** Trace `f1c9aa3857940ea7ec71a38d9ee9e738`
(`support-0211`).

**Say:**
- Definition: the reply describes a refund needing human approval using
  completed-action language — either a bare "refund" instead of "refund request,"
  or asserting the approval outcome as certain.
- support-0211: *"Your refund has been submitted!... Status: Queued for human
  approval."* The tool result was `queued_for_approval`, not approved.
- Ties directly to `SPEC.md` **RESP-2**: "do not claim that an action succeeded
  before the relevant tool reports success." 9 confirmed instances, 2 close
  negatives (both a refund that really was `auto_approved`, where the same
  "processed" language is correct).

**Mode B: `refund_proceeds_past_eligibility_window`.** Trace
`454f8e151e47768bf7f80c5271799dad` (`support-0239`).

**Say:**
- A refund is auto-approved or queued because `get_order`/`issue_refund` reports
  the order eligible, when it's actually 85–98 days past the return window.
- Root cause traced into `seed/generate.py`: eligibility is computed once at
  database-seed time and stored, never recomputed against the real current date.
- Not the agent's fault — the agent correctly trusted the tool. Added a new SPEC
  requirement, **`TOOL-11`**, requiring eligibility to reflect the current date at
  request time. A full-corpus code-check search found 8 total instances and zero
  close negatives anywhere in the dataset.

## Beat 4 — a taxonomy revision

**Show:** `analysis/report/review_summary.md`, "Taxonomy revision" section.

**Say:**
- First version of this mode, `write_without_eligibility_check`, was built from
  open-coding notes saying cancellations happened "without checking policy
  first."
- On inspecting the actual tool calls, those cancellations were all close
  negatives — `cancel_order`'s eligibility check (order status `placed`) had
  worked correctly, no policy lookup was ever needed for that decision.
- Rewrote the mode entirely around what was actually wrong (the stale
  `refund_eligible` flag), changed its evaluator from a judge to a deterministic
  code check, and only then confirmed it with real evidence.

## Beat 5 — a rejected search suggestion

**Show:** `analysis/state/suggestions.json`, the support-0126 entry (`status:
"rejected"`).

**Say:**
- Searching for more instances of `unsolicited_reply_content` (tone-mismatch
  replies) using semantic similarity to 5 confirmed examples returned
  support-0126 — a merchant asking a general policy question, no specific order
  or customer interaction at all.
- Rejected it: it only matched on shared words like "return window," not the
  actual failure. The boundary: this mode requires a customer-facing outcome —
  an order status, a refund decision — for there to be a tone to mismatch
  against. A plain, correctly-scoped policy answer has no such outcome.

## Beat 6 — new modes in the final 15

**Show:** `analysis/report/review_summary.md`, "Stability check" section.

**Say:**
- 3 of the final 15 uniformly-sampled traces (20%) surfaced a pattern not yet in
  the taxonomy: a merchant being told another store's specific identity, a silent
  order substitution after a permission error, and a missed store-specific
  policy override.
- Searched each across the full 250-scenario corpus. One (the missed policy
  override) reached 3 confirmed instances and became mode #7,
  `store_override_policy_not_cited`. The other two stayed at one instance each
  after exhaustive search — recorded as documented candidates, not forced into
  the taxonomy.

## Facts you can cite if asked, all verified against committed files

- 123 distinct traces reviewed across 4 batches (15 uniform + 15 cluster reps, 30
  role-stratified, 48 depth-search, 15 final uniform check).
- 7 confirmed failure modes, 2 documented candidates below the 3-instance
  minimum.
- 4 new `SPEC.md` requirements added: `TOOL-11`, `TOOL-12`, `RESP-6`, `RESP-7`
  — each with a named motivating annotation in the review summary.
- 861 present/absent judgments written (123 traces × 7 confirmed modes) to
  `analysis/state/labels/` and to Langfuse as scores.
- Sample fractions range from 2.4% (`premature_help_lookup`,
  `store_override_policy_not_cited`) to 9.8%
  (`dispute_window_not_checked_against_current_date`) — reported as sample
  fractions, not prevalence, since the sample was deliberately shaped by
  clustering and targeted search, not drawn at random.
