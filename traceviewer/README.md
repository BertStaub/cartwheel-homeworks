# Cartwheel trace viewer

A local, read-only trace viewer for the Cartwheel support agent. Not a homework
deliverable for any module — a personal tool for reading a Langfuse trace end
to end (conversation, tool calls, raw spans) without clicking through the
Langfuse UI.

It reads directly from the Langfuse API on every request. It keeps no state of
its own: no database, no local cache file, no annotation or scoring endpoints.
Everything you see is fetched live and can be refreshed at any time.

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

- **List view**: every trace, newest first. Role, user id, request/reply
  previews, which tools ran, latency, cost, and a `clean` / `⚠ issue` badge
  computed from actual tool failures (`output.ok == false`) or a non-`DEFAULT`
  span level. A role filter, an "issues only" checkbox, and a text search all
  run client-side against the current page — no extra requests.
- **Detail view**: the conversation as user message → expandable tool-call
  cards → assistant reply, each tool call showing its full arguments and
  result, observation id, start/end timestamps, level, status message, and
  permission-denied reason. A failed call auto-expands with a red border so it
  can't hide inside a collapsed card. Below that, a flat timeline table of
  every span in the trace, and a collapsed **raw observation view** with the
  unmodified Langfuse API response for the trace and its observations.
- Every field that's actually missing (a null attribute, an unset store id)
  renders as `missing` rather than being silently omitted.

## What it deliberately does not do

No annotations, no labels, no scores, no writes back to Langfuse, no local
database. If you want to label traces for error analysis, that's the Module 2
review interface (`analysis/server.py`), not this.

## Files

```
traceviewer/
  app.py              FastAPI app: GET /api/traces, GET /api/traces/{id}, GET /health
  langfuse_client.py   thin async httpx client for Langfuse's public read API
  static/
    index.html        page shell + the tool-call <template>
    style.css
    app.js            hash-based routing (#/ list, #/trace/{id} detail), all rendering
```
