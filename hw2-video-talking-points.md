# HW2 demo video talking points

Not a graded deliverable (not in the "Files to commit" list) — just a run sheet for
recording the 5-minute demo. Docker + the Langfuse stack must be up, and the server
running (`uv run uvicorn server.app:app --port 8010`).

## 1. Run one authentication test

```bash
uv run pytest tests/test_observability.py -v
```

Either test works; both are offline (no Langfuse/Docker/model key needed).

## 2. Read both selected traces, root span to final response

Open both permalinks from `hw2-traces.json` in the Langfuse UI:

- `772f71807c4128e127fdae3f3470a5e1` — merchant 9002 blocked from order 4127
- `1fe5c2cd0dd533f8e217b4086c3d1c56` — shopper 1, refund status on order 3988

Walk each from the `cartwheel.session_message` root span down through its tool
call(s) to the final assistant reply.

## 3. Explain how the endpoint established the authenticated identity

- `POST /sessions` (`create_session`, server/app.py): validates the claimed role is
  a real role, loads the user row from the DB, rejects a role that doesn't match
  the *stored* role (403) — this is what stops a real user from claiming a more
  powerful role than the database assigned them.
- The `AuthContext` is built from the stored DB row, never the client's claim.
- Every later request carries a signed token (`session_id`, `user_id`, `role`,
  `store_id`, `issued_at`); `_authorize` verifies the signature and that the token
  matches the session id in the URL before the agent ever runs.

## 4. Explain the tool calls and results in the selected traces

- Trace 1 (merchant 9002 / order 4127): one tool call, `get_order`, returns
  `permission_denied` — order 4127 belongs to store 1, merchant 9002 is store 2.
- Trace 2 (shopper 1 / order 3988): two tool calls — `get_order` (shows
  `orders.status: "refunded"`, which is misleading) then `get_refund_status` (shows
  the real `refunds` table status, `queued_for_approval`). This is the Part-A
  additional tool built in HW1 to fix exactly this gap.

## 5. Show the two prompt version hashes from the controlled comparison

- Before (HW1-original prompt): `cartwheel.prompt_version = b3f4a5686618`
- After (Part C revision — proactive policy lookup before eligibility claims):
  `cartwheel.prompt_version = a8f250827370`
- Same request ("Can I get a refund for order 3980?"), same user, same model,
  fresh session/empty history each time — only the prompt text differs.

## 6. Regenerate the span count for one selected trace

Resubmit the same request that produced trace 2 (shopper 1, "What's the status of
my refund on order 3988?") through a fresh session, then recount its observations
and confirm it matches (7 observations: root span, `Agent Workflow`, the agent
span, 2 model-generation spans, and the `get_order`/`get_refund_status` tool spans).

```bash
SESSION_JSON=$(curl -s -X POST http://localhost:8010/sessions \
  -H 'Content-Type: application/json' -d '{"user_id":1,"role":"shopper"}')
SESSION_ID=$(echo "$SESSION_JSON" | uv run python -c "import json,sys; print(json.load(sys.stdin)['session_id'])")
TOKEN=$(echo "$SESSION_JSON" | uv run python -c "import json,sys; print(json.load(sys.stdin)['token'])")
curl -s -X POST "http://localhost:8010/sessions/${SESSION_ID}/messages" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer ${TOKEN}" \
  -d '{"message":"What'"'"'s the status of my refund on order 3988?"}'
```

Then pull the new trace's observation count from Langfuse (UI, or
`GET /api/public/observations?traceId=...`) and confirm it's 7 again.
