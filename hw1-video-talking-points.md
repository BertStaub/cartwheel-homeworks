# HW1 demo video talking points

Not a graded deliverable (not in the "Files to commit" list) — just a run sheet for
recording the 5-minute demo.

## 1. Authorized request — shopper 1, order 4127

```bash
uv run python -m agent.cli --role shopper --user 1 --debug
```

Ask: "What is the status of order 4127?" — shows the `get_order` call succeeding.

## 2. Permission denial — merchant 9002, order 4127 (belongs to store 1)

```bash
uv run python -m agent.cli --role merchant --user 9002 --debug
```

Ask: "Can you show me the details for order 4127?" — shows `permission_denied`.

## 3. Order 4455 refund — shopper 1, above the $100 threshold

```bash
uv run python -m agent.cli --role shopper --user 1 --debug
```

Ask: "I'd like a refund for my order 4455, it wasn't what I expected."

Narrate: `issue_refund` never actually gets called; the agent just asks permission
instead of queuing it. This is the ESC-1 gap found in Part B (record #3 in
hw1-session.jsonl) but not the one fixed in Part C (Candidate B was chosen instead)
— worth calling out explicitly.

## 4. Explain the Part C investigation

- State the omission: the citation rule in the system prompt was reactive, not
  proactive — nothing forced a policy lookup before explaining an eligibility
  decision.
- Show the exact edit: `git diff agent/agent.py`
- Reference the "before" evidence: record #2 in `hw1-session.jsonl` (order 3980,
  no citation, `met_requirement: false`).
- Run the "after" case live: same order 3980 refund request, shopper 1 — now cites
  `cw-returns`/`cw-disputes`.

```bash
uv run python -m agent.cli --role shopper --user 1 --debug
```

Ask: "Can I get a refund for order 3980?"

## 5. Run at least one test

```bash
uv run pytest tests/test_hw_holes.py -k hw1 --runxfail -v
```

All 5 pass.

## 6. Confirm the record count in hw1-session.jsonl

```bash
wc -l hw1-session.jsonl
```

Shows 10.
