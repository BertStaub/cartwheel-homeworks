# Cartwheel trace viewer

A local trace viewer for the Cartwheel support agent. Not a homework
deliverable for any module — a personal tool for reading a Langfuse trace end
to end (conversation, tool calls, raw spans) without clicking through the
Langfuse UI, plus two write paths added to support Homework 3's pilot review.

It reads directly from the Langfuse API on every request and keeps no state
of its own beyond the two things below: no database, no local cache file.
Everything you see otherwise is fetched live and can be refreshed at any time.

## Requirements

- The Langfuse stack running: `docker compose -f observability/docker-compose.yml up -d`
- `.env` with `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` set
  (the defaults in `.env.example` match the stack's `LANGFUSE_INIT_*` values)
- At least one traced request already in Langfuse — run the agent server
  (`uv run uvicorn server.app:app --port 8010`) and send it a message first

## Run it

```bash
uv run uvicorn traceviewer.app:app --port 8030
```

Open `http://localhost:8030/`.

## What it shows

- **List view**: every trace, newest first. Role, user id, prompt version,
  scenario id, tool call count, latency, cost, and a `clean` / `⚠ issue` badge
  computed from actual tool failures (`output.ok == false`) or a non-`DEFAULT`
  span level. A role filter, an "issues only" checkbox, and a text search
  (still matching the request/reply text, just not shown as a column) all run
  client-side against the current page — no extra requests.
- **Detail view**: the conversation as user message → expandable tool-call
  cards → assistant reply, each tool call showing its full arguments and
  result, observation id, start/end timestamps, level, status message, and
  permission-denied reason. A failed call auto-expands with a red border so it
  can't hide inside a collapsed card. Below that, a flat timeline table of
  every span in the trace, and a collapsed **raw observation view** with the
  unmodified Langfuse API response for the trace and its observations.
- Every field that's actually missing (a null attribute, an unset store id)
  renders as `missing` rather than being silently omitted.
- **Turn notes**: a free-text note box under each turn, saved as a Langfuse
  comment on that turn's generation observation. Langfuse's public API has
  no endpoint to edit or delete a comment afterward, so a posted note is
  permanent — there is no undo, here or in Langfuse.
- **Pilot review form**: at the top of the detail view, when the trace
  carries a `cartwheel.scenario_id` (i.e. it came from `scenarios.runner`,
  not a manual session). Records the five Homework 3 Part B fields
  (`scenario_id`, `scenario_valid`, `confirmed_failure`, `evidence`,
  `scenario_change`) and upserts them into `scenarios/pilot_review.jsonl` by
  `scenario_id` — revisiting a trace edits its row instead of duplicating it.

## What it still does not do

No scores, no other writes to Langfuse beyond turn comments, and no
database. This is not the Module 2 review interface (`analysis/server.py`) —
that tool exists for labeling traces for error analysis at scale; this one
is for reading one trace closely and recording your Homework 3 pilot review.

## Files

```
traceviewer/
  app.py              FastAPI app: trace list/detail, prompt diff, turn
                       notes, pilot review (see docstring for every route)
  langfuse_client.py   async httpx client for Langfuse's public API: reads
                       traces/observations, writes comments
  static/
    index.html        page shell + the tool-call <template>
    style.css
    app.js            hash-based routing (#/ list, #/trace/{id} detail), all rendering
```
