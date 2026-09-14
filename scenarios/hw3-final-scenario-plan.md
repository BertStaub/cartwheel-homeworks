# HW3 Part C — final 250-scenario distribution plan

Working document, not a graded deliverable. Records the target shape of
`scenarios/support_scenarios.jsonl` (250 scenarios: 175 coverage, 75
challenge) and the reasoning behind it, before any real database record is
picked. Dimensions themselves were approved in Part A and are not
re-litigated here; this is about *how many* of each combination, and *how*
we'll find real records to ground them.

## Coverage (175) — role × intent

| Role | order_status | refund | cancellation | policy_question | product_search | dispute | out_of_scope | **Total** |
|---|---|---|---|---|---|---|---|---|
| shopper | 25 | 20 | 10 | 15 | 15 | 8 | 7 | **100** |
| merchant | 10 | 8 | 5 | 8 | 4 | 4 | 1 | **40** |
| support | 8 | 6 | 4 | 6 | 3 | 5 | 3 | **35** |
| **Total** | 43 | 34 | 19 | 29 | 22 | 17 | 11 | **175** |

**Reasoning:**
- Role split (100 / 40 / 35) weights shopper heaviest, matching who realistically
  contacts support most often, while still giving merchant and support
  deliberate, substantial coverage — more than the pilot's 30, which leaned
  harder on shopper by proportion.
- Intent counts follow how often each intent plausibly occurs per role:
  shoppers ask about orders/refunds most; merchants mostly handle
  order/refund/policy questions about their own store, rarely "out of
  scope"; support skews slightly toward dispute-handling (their escalation
  role) and away from product_search (not their job).
- Within each cell (not tracked as separate columns here): roughly 70%
  `well_specified`, 20% `ambiguous`/`boundary`, 10% `missing_information`;
  a store override (`applicable_policy: store_override`) in ~15-20% of
  `policy_question`/`refund`/`cancellation` rows; `user_style` sampled
  across all 8 approved values rather than defaulting to
  `neutral_conversational` everywhere, which the pilot mostly did.

## Challenge (75) — 30 fixed + 45 other

**The six damaged records (30, count fixed by the validator's `--final` check):**

| Case | Shopper | Merchant | Support | Total |
|---|---|---|---|---|
| dq-order-missing-delivery-date | 3 | 1 | 1 | 5 |
| dq-order-reversed-dates | 3 | 1 | 1 | 5 |
| dq-order-store-mismatch | 3 | 1 | 1 | 5 |
| dq-product-duplicate-title | 3 | 1 | 1 | 5 |
| dq-product-missing-title | 3 | 1 | 1 | 5 |
| dq-product-invalid-price | 3 | 1 | 1 | 5 |
| **Total** | 18 | 6 | 6 | **30** |

**Reasoning:** there is exactly one real record per defect, so the 5 scenarios
per case vary the requesting role/turn/style/wording, not the underlying
fact. The merchant row for each case uses that record's own owning store's
merchant (support can reach any of them regardless of store).

**45 more, not tied to a damaged record:**

| Category | Count | Same flavor as pilot's... |
|---|---|---|
| Refund/return boundary (threshold or window edge) | 12 | #26, #27 |
| Permission edges (shopper asks about another's order; merchant asks cross-store) | 10 | #28, #29 |
| Ambiguous / missing identifiers | 10 | #1, #2, #16, #21 |
| Multi-turn corrections/follow-ups | 8 | #18 |
| Store-override edge cases | 5 | #7, #14 |
| **Total** | **45** | |

175 + 30 + 45 = **250**.

## Plan for finding real data to populate this

The pilot picked records one at a time via ad-hoc queries. At this scale that
doesn't work — the plan is to query in **pools per bucket**, then sample
distinct records out of each pool, so no single query has to be re-run by
hand 250 times and no two scenarios accidentally collide on the same record.

1. **Ordinary coverage records** (order_status, refund, cancellation,
   dispute intents): one broad query per record *state* needed —
   `delivered` + eligible, `delivered` + past-window, `placed`
   (cancellable), `shipped` (not yet delivered), `above-threshold` eligible
   — each returning a pool of candidate order ids, then sampling distinct
   ones across scenarios so state-changing scenarios (refund, cancel) never
   reuse the same order twice. (The pilot did reuse order #4127 across three
   scenarios, including two that mutated it — harmless there since it
   surfaced a real, explainable interaction, but not something to repeat
   250 times over; distinct records avoid the ambiguity.)
2. **Merchant-role records**: query each candidate merchant's `store_id`,
   then pull that store's own orders in the needed states — mirrors step 1,
   scoped by store.
3. **Support-role records**: no ownership constraint (support can view any
   order), so any record from step 1/2's pools works; role is what varies,
   not the record.
4. **Store-override scenarios**: limited to the four stores with a real
   `return_window_days_override` (Juniper Home Goods, Northwind Books,
   Meridian Cycles, Saltbox Pantry) — already known from Part A/B, no new
   query needed beyond picking orders within each.
5. **Boundary scenarios (12)**: reuse the exact SQL technique from the pilot
   — `ORDER BY ABS(total_cents - 10000)` for threshold edges, and the
   day-before/day-after bracketing query for the 30-day window edge — but
   pull enough distinct rows to cover 12 scenarios, not just one each.
6. **Permission-edge scenarios (10)**: pick pairs of (authenticated user,
   a real record that isn't theirs) — same pattern as pilot #28/#29, sampled
   across several different user/order pairs instead of one.
7. **Ambiguous / missing-identifier scenarios (10)**: pick ordinary orders
   from step 1's pools, but the *message* deliberately omits the order
   number, describing the item/store/rough timing instead (same convention
   as the pilot).
8. **Multi-turn correction scenarios (8)**: need *pairs* of real orders per
   scenario (a plausible wrong initial mention + the corrected target),
   drawn from step 1's pools, avoiding orders already claimed by another
   scenario in this same set.
9. **Damaged records (30)**: no new query — reuses the six already-known
   records (orders 8001/8002/8003, products 2/3/4) and their owning
   stores/merchants.

Once these pools exist, the next step is turning them into the actual
250-row tuple table for review, the same way Part B's Step B1 worked, just
built from pool queries instead of one-off lookups.
