# Homework 4 review summary

## Reviewed sample

123 distinct `support-*` traces reviewed (pilot scenarios excluded by design; this
assignment reviews the 250 Homework 3 support scenarios only). Composition:

| Batch | Method | Count |
|---|---|---|
| 1a | Uniform random | 15 |
| 1b | Cluster representatives (k-means on turn count, tool-call count, distinct tools, retrieval presence, tokens; 8 clusters) | 15 |
| 2 | Stratified by role, 10 each shopper/merchant/support | 30 |
| 3 | Depth search: semantic-similarity and deterministic code-check searches for candidate modes and close negatives | 48 |
| 4 | Final uniform random (post-taxonomy stability check) | 15 |
| **Total** | | **123** |

Role composition: shopper 88, merchant 21, support 14. `scenario_group`: coverage 100,
challenge 23.

## Final taxonomy (7 confirmed modes)

| Mode | Positives | Close negatives | Evaluator | Requirement |
|---|---|---|---|---|
| `refund_proceeds_past_eligibility_window` | 8 | 0 | code | `TOOL-11` (new) |
| `overstates_write_status` | 9 | 2 | judge | `RESP-2` (existing) |
| `store_id_shown_instead_of_name` | 6 | 0 | code | `TOOL-12` (new) |
| `premature_help_lookup` | 3 | 2 | judge | `RESP-6` (new) |
| `dispute_window_not_checked_against_current_date` | 12 | 3 | judge | `RESP-7` (new) |
| `unsolicited_reply_content` | 7 | 2 | judge | `RESP-5` (existing) |
| `store_override_policy_not_cited` | 3 | 4 | code | `RESP-1` (existing) |

Two additional patterns (`cross_tenant_store_disclosure`, `silent_order_substitution`) are
recorded in `patterns.json` as `status: "candidate"` -- one confirmed instance each, below the
three-instance minimum for a final mode, each with well-characterized close negatives. They are
excluded from the counts and labels below.

Every trace in the review set received a present/absent judgment for each of the 7 confirmed
modes (861 judgments total), written to `analysis/state/labels/` and to Langfuse as scores.

**Sample fractions** (not prevalence estimates -- this sample was deliberately shaped by
clustering and targeted search, not drawn at random from the full trace population):

`dispute_window_not_checked_against_current_date` 9.8%, `overstates_write_status` 7.3%,
`refund_proceeds_past_eligibility_window` 6.5%, `unsolicited_reply_content` 5.7%,
`store_id_shown_instead_of_name` 4.9%, `premature_help_lookup` 2.4%,
`store_override_policy_not_cited` 2.4%.

## Stability check (final 15 traces)

Of the final 15 uniformly-sampled traces (batch 4), 3 (20%) surfaced a pattern not yet in the
taxonomy at the time: a cross-tenant store-identity disclosure, a silent order substitution
after a `permission_denied` result, and a missed store-specific policy override. Each was
searched further across the full 250-scenario corpus. One (the missed policy override)
accumulated enough evidence to become a confirmed mode
(`store_override_policy_not_cited`, 3 positives / 4 close negatives). The other two remained at
one confirmed instance each after exhaustive search and are recorded as candidates, not
promoted. No mode was found to be systemic enough after searching to require a further review
batch.

## Taxonomy revision

The first candidate mode, initially named `write_without_eligibility_check`, was defined from
open-coding notes describing cancellations issued "without checking policy first"
(support-0046, 0047, 0050) and a refund the reviewer believed was outside its return window
(support-0239). On inspection of the actual tool calls and results, all three cancellation
instances turned out to be close negatives: `cancel_order`'s eligibility check (order status
`placed`) had worked correctly, and no policy lookup was actually required for that decision.
support-0239, however, revealed a real and more precise defect: `seed/generate.py` computes
`refund_eligible` once at database-seed time and never recomputes it, so the flag silently goes
stale as real time passes. The mode was rewritten as
`refund_proceeds_past_eligibility_window`, with a code-check evaluator (recompute eligibility
against the trace's own timestamp) rather than a judge, and `SPEC.md` `TOOL-11` was added to
require eligibility to reflect the current date at request time. A full-corpus code-check search
then found 5 more instances and confirmed the mode; the same search found zero close negatives
anywhere in the 250-scenario corpus, suggesting the underlying database may have been seeded
once, long enough ago that no order remains genuinely within its return window at request time --
recorded as a dataset limitation rather than a search gap.

## Rejected search suggestion

A semantic-similarity search for more instances of `unsolicited_reply_content` (seeded by 5
confirmed "Great news!"/"Done!" tone instances) returned support-0126, a merchant asking a
general policy question ("what's the standard return window?") with no specific order or
customer interaction involved. It was rejected: the retrieval matched on shared vocabulary
("return window") alone, not on the actual failure -- there is no unsolicited or mistoned
content in a plain, correctly-scoped policy answer. The boundary that excludes it: the mode
requires a customer-facing outcome (an order status, a refund decision) where a tone mismatch or
unprompted suggestion is possible; a standalone policy lookup has no such outcome to mismatch
against.

## SPEC.md revisions

Four new requirements added, each motivated by a specific annotation:

- **`TOOL-11`** (eligibility must reflect the current date at request time) -- motivated by
  support-0239, support-0116, support-0240.
- **`TOOL-12`** (`search_products` must return a store name) -- motivated by support-0083,
  0085, 0165, 0167, 0197, 0200.
- **`RESP-6`** (ask a clarifying question before assuming a specific need) -- motivated by
  support-0003, support-0005, support-0009.
- **`RESP-7`** (a computed date-based deadline must be checked against the current date) --
  motivated by support-0238, support-0150, support-0027 (and 9 further confirmed instances).

## Known data-quality limitation (not part of the taxonomy)

Three traces (support-0106, support-0137, support-0138) involve a merchant-role caller asking
about what is actually a personal (shopper) order -- a scenario-construction mismatch from
Homework 3, not an agent failure. All three are marked "no failure observed." One of them
(support-0137/0138's underlying question, generalized) surfaces a genuine `SPEC.md` gap worth
noting for future work: `AUTH-1`'s access matrix defines permissions by order ownership but does
not address what should happen when a caller's role itself does not match the kind of order
being discussed.
