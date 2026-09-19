# Raindrop Workshop notes (HW4, Part C)

## Setup

Installed Raindrop Workshop locally (`curl -fsSL https://raindrop.sh/install | bash`, no cloud
account). Instrumented one real entry point, `server/app.py`'s `post_message` (the
`cartwheel.session_message` handler), with `raindrop.begin`/`interaction.finish`, using
`api_key=None` (local-only) and `tracing_enabled=False` so Raindrop's Traceloop-based
auto-instrumentation never touches OpenTelemetry or competes with the tracer provider Langfuse
already owns. Verified by direct inspection of the local Workshop SQLite database
(`~/.raindrop/raindrop_workshop.db`) that a real run captured the exact input and output text,
not just that the request returned 200.

## Runs inspected

Ran 8 fresh scenarios through the live, instrumented server, deliberately spanning different
roles and tools -- none of these were part of the original 250-scenario HW3 corpus, so this is a
genuine stability check on a different sample.

| Run ID | Scenario | Role | Tool path |
|---|---|---|---|
| `c8c4f587e4d112b3e613f5bbd765f9b2` | workshop-01-auto-refund | shopper | issue_refund (auto_approved) |
| `b564edf738fc0de9f68cc91de9a9da9e` | workshop-02-queued-refund | shopper | issue_refund (queued_for_approval) |
| `84ce5f52fb5a5f6b6f5f5e154bb49b11` | workshop-03-cancel | shopper | cancel_order |
| `e715a9e85a76ced45122d256a1915c3b` | workshop-04-merchant-cancel | merchant | cancel_order |
| `8b6e24809cfdffcbbe0ca998b2209396` | workshop-05-support-refund | support | issue_refund (queued_for_approval) |
| `5e376b8f1b9f7c00c83544fdc6dc9622` | workshop-06-product-search | shopper | search_products |
| `19af872facb8093accab1212a71f7250` | workshop-07-vague | shopper | (no tool call) |
| `2655a55b31fa707ed0e819295aa28dea` | workshop-08-permission-denied | merchant | get_order (permission_denied) |

## Candidate failures / unusual behavior

- **workshop-02-queued-refund** and **workshop-05-support-refund** both reproduce the confirmed
  `overstates_write_status` mode: "Your refund has been submitted!... A support agent will
  review and approve the refund shortly" (workshop-02) and "a human support agent will need to
  review and approve it" (workshop-05) both describe a pending human decision with more
  certainty than the tool result (`queued_for_approval`) supports.
- **workshop-06-product-search** reproduces `store_id_shown_instead_of_name`: "Store 2" / "Store
  1" shown raw in a product comparison table, because `search_products` still does not return a
  store name (the root cause documented for that mode).

No previously-unseen failure category appeared in this batch. Treating this as **confirmation
that the taxonomy generalizes** to fresh, out-of-corpus scenarios, not as a gap in the search --
the batch was small (8 runs) and deliberately diverse, not exhaustive.

## Good behavior observed (informative, not failures)

- **workshop-07-vague** ("I need help with something.") correctly asks a plain clarifying
  question instead of assuming a topic -- the same close-negative pattern already documented for
  `premature_help_lookup` and `unsolicited_reply_content`.
- **workshop-08-permission-denied** correctly refuses without revealing the other store's
  identity ("doesn't belong to your store", not "belongs to store 2") and without silently
  substituting a different order -- a clean close negative for both the `cross_tenant_store_disclosure`
  and `silent_order_substitution` candidates.
- **workshop-01, 03, 04** were all verified against the database directly (both cancellations
  actually transitioned the order to `cancelled`) and contained no detected issues.

## One case of genuine uncertainty

**workshop-05-support-refund**: "a human support agent will need to review and approve it
before the funds are released." I'm not fully certain this belongs in `overstates_write_status`.
An alternative reading: this describes the *process requirement* (review is mandatory) rather
than asserting the *outcome* (approval will happen) -- weaker than workshop-02's "will review and
approve the refund shortly," which reads more like a promise of the result. I logged it as a
match to the existing mode, but flagging the ambiguity rather than treating it as clear-cut.

## Accept / revise / reject

No new mode was proposed by this Workshop pass, so there is nothing to accept, revise, or
reject in that sense. The two candidate matches above (workshop-02, workshop-05) are recorded as
**additional confirmed instances** of `overstates_write_status`, and workshop-06 as an additional
instance of `store_id_shown_instead_of_name` -- not added to `patterns.json`'s counts, since
these are live-server runs outside the reviewed-trace sample manifest, kept here as a separate,
out-of-sample confirmation rather than mixed into the Part B/E sample fractions.
