"""Local trace viewer for the Cartwheel support agent.

Reads directly from the Langfuse API on every request; this app keeps no
state of its own. It exists to make a trace easy to read end to end --
conversation, tool calls with full arguments/results, and a raw observation
view -- without clicking through the Langfuse UI.

Two write paths exist, both added for Homework 3 pilot review, and both
scoped narrowly:
  - A free-text note, posted as a Langfuse comment (see
    langfuse_client.create_comment). Anchored to whatever you clicked: a
    generation or tool-call span gets an OBSERVATION comment on its own
    observation id; the assistant's final reply isn't a span at all
    (it's trace.output), so it gets a TRACE comment on the trace id
    instead. Comments cannot be edited or deleted afterward -- neither
    here nor in Langfuse.
  - The structured pilot review form, which upserts one row per
    `scenario_id` into scenarios/pilot_review.jsonl (by `scenario_id`, so
    re-reviewing a trace edits its row instead of duplicating it).
There is still no local database and no other state; every read is fetched
fresh from Langfuse on every request.

Run with:
    uv run uvicorn traceviewer.app:app --port 8030
"""

from __future__ import annotations

import asyncio
import difflib
import json
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.config import REPO_ROOT
from traceviewer import langfuse_client as lf

STATIC_DIR = Path(__file__).resolve().parent / "static"
PILOT_REVIEW_PATH = REPO_ROOT / "scenarios" / "pilot_review.jsonl"

app = FastAPI(title="Cartwheel trace viewer")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _text_of(messages: Any) -> str | None:
    """Pull the first text part's content out of an OTel GenAI message list.

    `messages` is `[{"role": ..., "parts": [{"type": "text", "content": ...}]}]`
    (see server/app.py's gen_ai.input.messages / gen_ai.output.messages) when
    content capture was on for that request, else None.
    """
    if not isinstance(messages, list) or not messages:
        return None
    first = messages[0]
    parts = first.get("parts") if isinstance(first, dict) else None
    if not isinstance(parts, list):
        return None
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "text":
            return part.get("content")
    return None


def _preview(text: str | None, length: int = 140) -> str | None:
    if text is None:
        return None
    text = " ".join(text.split())
    return text if len(text) <= length else text[: length - 1] + "…"


def _tool_ok(observation: dict[str, Any]) -> bool | None:
    """The tool's own `ok` field, or None when the output has no such field."""
    output = observation.get("output")
    if isinstance(output, dict) and "ok" in output:
        return bool(output["ok"])
    return None


def _has_error(observations: list[dict[str, Any]]) -> bool:
    for obs in observations:
        level = obs.get("level")
        if level and level != "DEFAULT":
            return True
        if obs.get("type") == "TOOL" and _tool_ok(obs) is False:
            return True
    return False


def _permalink(trace_id: str, html_path: str | None) -> str:
    if html_path:
        return f"{lf.base_url()}{html_path}"
    return f"{lf.base_url()}/project/cartwheel-dev/traces/{trace_id}"


def _attrs(entity: dict[str, Any]) -> dict[str, Any]:
    return (entity.get("metadata") or {}).get("attributes") or {}


def _tool_call_summary(obs: dict[str, Any]) -> dict[str, Any]:
    obs_attrs = _attrs(obs)
    return {
        "observation_id": obs.get("id"),
        "name": obs.get("name"),
        "start_time": obs.get("startTime"),
        "end_time": obs.get("endTime"),
        "latency": obs.get("latency"),
        "level": obs.get("level"),
        "status_message": obs.get("statusMessage"),
        "input": obs.get("input"),
        "output": obs.get("output"),
        "ok": _tool_ok(obs),
        "permission_denied": obs_attrs.get("cartwheel.permission_denied"),
        "permission_denied_reason": obs_attrs.get("cartwheel.permission_denied.reason"),
        "raw": obs,
    }


def _generation_summary(obs: dict[str, Any]) -> dict[str, Any]:
    return {
        "observation_id": obs.get("id"),
        "model": obs.get("model"),
        "start_time": obs.get("startTime"),
        "end_time": obs.get("endTime"),
        "latency": obs.get("latency"),
        "level": obs.get("level"),
        "status_message": obs.get("statusMessage"),
        "total_tokens": obs.get("totalTokens"),
        "total_cost": obs.get("calculatedTotalCost"),
        "raw": obs,
    }


def _build_turns(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group generation and tool spans into agent turns.

    A "turn" here is the OpenAI Agents SDK's own unit (MAX_TURNS in
    agent/cli.py, server/app.py): one model call, plus whatever tool calls
    that decision produced, before the next model call. Bucketing by
    start-time-sorted order works because a tool's span always starts after
    the generation that decided to call it and before the next generation
    that reacts to its result.
    """
    relevant = [o for o in observations if o.get("type") in ("GENERATION", "TOOL")]
    relevant.sort(key=lambda o: o.get("startTime") or "")

    turns: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for obs in relevant:
        if obs.get("type") == "GENERATION":
            current = {
                "turn_index": len(turns) + 1,
                "generation": _generation_summary(obs),
                "tool_calls": [],
            }
            turns.append(current)
        else:
            if current is None:
                # A tool call recorded with no preceding generation span
                # (shouldn't normally happen) still gets its own turn
                # rather than being silently dropped.
                current = {"turn_index": len(turns) + 1, "generation": None, "tool_calls": []}
                turns.append(current)
            current["tool_calls"].append(_tool_call_summary(obs))
    return turns


async def _attach_notes(turns: list[dict[str, Any]]) -> None:
    """Fetch Langfuse comments for every generation and tool-call span.

    Notes are per-span, not per-turn: each generation summary and each tool
    call summary already carries its own `observation_id` (see
    _generation_summary / _tool_call_summary), so every one of them gets its
    own `notes` list, independent of whether its turn has a generation span
    at all.
    """
    targets: list[dict[str, Any]] = []
    for turn in turns:
        if turn.get("generation"):
            targets.append(turn["generation"])
        targets.extend(turn.get("tool_calls", []))

    comment_lists = await asyncio.gather(
        *(lf.list_comments("OBSERVATION", t["observation_id"]) for t in targets)
    )
    for target, comments in zip(targets, comment_lists):
        target["notes"] = [
            {"id": c["id"], "content": c["content"], "created_at": c["createdAt"]}
            for c in comments
        ]


def _extract_system_prompt(observations: list[dict[str, Any]]) -> str | None:
    """The full rendered system prompt, read off any GENERATION span's input.

    Every model call's `input` starts with the system message, so the first
    GENERATION span in the trace has it -- this is the same rendered prompt
    that produced `cartwheel.prompt_version`, just not re-hashed here.
    Returns None when no GENERATION span captured its input (content capture
    off, or no model call in this trace).
    """
    for obs in observations:
        if obs.get("type") != "GENERATION":
            continue
        messages = obs.get("input")
        if not isinstance(messages, list) or not messages:
            continue
        first = messages[0]
        if not isinstance(first, dict) or first.get("role") != "system":
            continue
        for part in first.get("parts") or []:
            if isinstance(part, dict) and part.get("type") == "text":
                return part.get("content")
    return None


def _session_permalink(session_id: str) -> str:
    return f"{lf.base_url()}/project/cartwheel-dev/sessions/{session_id}"


async def _build_exchange(trace: dict[str, Any]) -> dict[str, Any]:
    """Everything about one HTTP request's trace: its turns, notes, timeline,
    and raw data. One Cartwheel session can have several of these -- one per
    call to POST /sessions/{id}/messages (the opening message, then each
    followup) -- see _session_permalink's caller for how they're combined.
    """
    trace_id = trace["id"]
    observations = await lf.list_observations(trace_id)
    observations = sorted(observations, key=lambda o: o.get("startTime") or "")
    turns = _build_turns(observations)
    trace_comments, _ = await asyncio.gather(
        lf.list_comments("TRACE", trace_id), _attach_notes(turns)
    )
    notes = [
        {"id": c["id"], "content": c["content"], "created_at": c["createdAt"]}
        for c in trace_comments
    ]
    timeline = [
        {
            "observation_id": obs.get("id"),
            "parent_id": obs.get("parentObservationId"),
            "type": obs.get("type"),
            "name": obs.get("name"),
            "level": obs.get("level"),
            "status_message": obs.get("statusMessage"),
            "start_time": obs.get("startTime"),
            "end_time": obs.get("endTime"),
            "latency": obs.get("latency"),
            "model": obs.get("model"),
            "total_cost": obs.get("calculatedTotalCost"),
            "total_tokens": obs.get("totalTokens"),
        }
        for obs in observations
    ]
    return {
        "trace_id": trace_id,
        "permalink": _permalink(trace_id, trace.get("htmlPath")),
        "timestamp": trace.get("timestamp"),
        "has_error": _has_error(observations),
        "user_message": _text_of(trace.get("input")),
        "assistant_reply": _text_of(trace.get("output")),
        "notes": notes,
        "turns": turns,
        "timeline": timeline,
        "raw": {"trace": trace, "observations": observations},
    }


async def _trace_prompt(trace_id: str) -> dict[str, Any]:
    trace = await lf.get_trace(trace_id)
    observations = await lf.list_observations(trace_id)
    attrs = _attrs(trace)
    return {
        "trace_id": trace_id,
        "prompt_version": attrs.get("cartwheel.prompt_version"),
        "prompt_text": _extract_system_prompt(observations),
    }


@app.get("/api/prompt-diff")
async def api_prompt_diff(a: str, b: str) -> dict[str, Any]:
    try:
        prompt_a, prompt_b = await asyncio.gather(_trace_prompt(a), _trace_prompt(b))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(404, "one of the traces was not found") from exc
        raise HTTPException(502, f"Langfuse returned {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Cannot reach Langfuse: {exc}") from exc

    diff_lines: list[dict[str, str]] = []
    if prompt_a["prompt_text"] is not None and prompt_b["prompt_text"] is not None:
        diff = difflib.unified_diff(
            prompt_a["prompt_text"].splitlines(),
            prompt_b["prompt_text"].splitlines(),
            fromfile=f"trace {a} ({prompt_a['prompt_version'] or 'unknown version'})",
            tofile=f"trace {b} ({prompt_b['prompt_version'] or 'unknown version'})",
            lineterm="",
        )
        for line in diff:
            if line.startswith("+++") or line.startswith("---"):
                kind = "file-header"
            elif line.startswith("@@"):
                kind = "hunk-header"
            elif line.startswith("+"):
                kind = "add"
            elif line.startswith("-"):
                kind = "remove"
            else:
                kind = "context"
            diff_lines.append({"type": kind, "text": line})

    return {
        "a": prompt_a,
        "b": prompt_b,
        "same_version": prompt_a["prompt_version"] == prompt_b["prompt_version"],
        "diff_lines": diff_lines,
    }


@app.get("/api/traces")
async def api_list_traces(page: int = 1, limit: int = 25) -> dict[str, Any]:
    try:
        payload = await lf.list_traces(page=page, limit=limit)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Langfuse returned {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Cannot reach Langfuse: {exc}") from exc

    traces = payload.get("data", [])
    observations_by_trace = await asyncio.gather(
        *(lf.list_observations(t["id"]) for t in traces)
    )

    # Group by Langfuse session (see server/app.py's session.id attribute)
    # so a multi-turn scenario's separate per-request traces collapse into
    # one row, the same way clicking through to the detail view already
    # expands one row back into every exchange. A trace with no session id
    # (older data, or a manual one-off request) is its own singleton group.
    # Caveat: this only groups traces that land on the same fetched page: a
    # session split across a pagination boundary undercounts here, though
    # the detail view is always correct since it re-fetches the full
    # session directly from Langfuse rather than relying on this page.
    groups: dict[str, list[tuple[dict[str, Any], list[dict[str, Any]]]]] = {}
    order: list[str] = []
    for trace, observations in zip(traces, observations_by_trace):
        key = trace.get("sessionId") or trace["id"]
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((trace, observations))

    summaries = []
    for key in order:
        members = groups[key]
        newest_trace, newest_observations = members[0]
        attrs = _attrs(newest_trace)
        tool_count = sum(
            len([o for o in observations if o.get("type") == "TOOL"])
            for _, observations in members
        )
        search_text = " ".join(
            text
            for trace, _ in members
            for text in (_text_of(trace.get("input")), _text_of(trace.get("output")))
            if text
        )
        summaries.append(
            {
                "trace_id": newest_trace["id"],
                "timestamp": newest_trace.get("timestamp"),
                "user_role": attrs.get("cartwheel.user_role"),
                "user_id": attrs.get("cartwheel.user_id"),
                "prompt_version": attrs.get("cartwheel.prompt_version"),
                "scenario_id": attrs.get("cartwheel.scenario_id"),
                "input_preview": _preview(search_text),
                "output_preview": None,
                "tool_count": tool_count,
                "turn_count": len(members),
                "has_error": any(_has_error(observations) for _, observations in members),
                "latency": sum(trace.get("latency") or 0 for trace, _ in members),
                "total_cost": sum(trace.get("totalCost") or 0 for trace, _ in members),
                "permalink": (
                    _session_permalink(key)
                    if newest_trace.get("sessionId")
                    else _permalink(newest_trace["id"], newest_trace.get("htmlPath"))
                ),
            }
        )

    meta = payload.get("meta", {})
    return {
        "page": meta.get("page", page),
        "limit": meta.get("limit", limit),
        "total_items": meta.get("totalItems", len(summaries)),
        "total_pages": meta.get("totalPages", 1),
        "traces": summaries,
    }


@app.get("/api/traces/{trace_id}")
async def api_get_trace(trace_id: str) -> dict[str, Any]:
    """One full conversation, starting from any trace that belongs to it.

    If the trace carries a Langfuse session id (server/app.py sets one on
    every request in a Cartwheel session), this fetches every trace in that
    session and returns all of them as ordered `exchanges` -- the opening
    message and every followup, each with its own turns/notes/timeline. A
    trace with no session id (older data, or a one-off request) comes back
    as a single-exchange conversation, so the frontend only handles one
    response shape either way.
    """
    try:
        trace = await lf.get_trace(trace_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(404, "trace not found") from exc
        raise HTTPException(502, f"Langfuse returned {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Cannot reach Langfuse: {exc}") from exc

    session_id = trace.get("sessionId")
    try:
        if session_id:
            session = await lf.get_session(session_id)
            member_traces = sorted(session["traces"], key=lambda t: t.get("timestamp") or "")
            permalink = _session_permalink(session_id)
        else:
            member_traces = [trace]
            permalink = _permalink(trace_id, trace.get("htmlPath"))
        exchanges = list(await asyncio.gather(*(_build_exchange(t) for t in member_traces)))
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Langfuse returned {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Cannot reach Langfuse: {exc}") from exc

    attrs = _attrs(member_traces[0])
    return {
        "session_id": session_id,
        "permalink": permalink,
        "has_error": any(exchange["has_error"] for exchange in exchanges),
        "scenario_id": attrs.get("cartwheel.scenario_id"),
        "user_role": attrs.get("cartwheel.user_role"),
        "user_id": attrs.get("cartwheel.user_id"),
        "store_id": attrs.get("cartwheel.store_id"),
        "prompt_version": attrs.get("cartwheel.prompt_version"),
        "exchanges": exchanges,
    }


class NoteIn(BaseModel):
    content: str


async def _add_comment(object_type: str, object_id: str, body: NoteIn) -> dict[str, Any]:
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "note content cannot be empty")
    try:
        return await lf.create_comment(object_type, object_id, content)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Langfuse returned {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Cannot reach Langfuse: {exc}") from exc


@app.post("/api/traces/{trace_id}/observations/{observation_id}/notes")
async def api_add_note(trace_id: str, observation_id: str, body: NoteIn) -> dict[str, Any]:
    return await _add_comment("OBSERVATION", observation_id, body)


@app.post("/api/traces/{trace_id}/notes")
async def api_add_trace_note(trace_id: str, body: NoteIn) -> dict[str, Any]:
    """A note on the assistant's final reply, which is trace.output -- not
    any single span -- so it's anchored to the trace itself."""
    return await _add_comment("TRACE", trace_id, body)


# ---------------------------------------------------------------------------
# Pilot review (Homework 3, Part B): scenarios/pilot_review.jsonl, one row
# per scenario_id. Pure local file I/O, no Langfuse call, so these two
# handlers are plain `def`, not `async def` -- FastAPI runs sync handlers in
# a thread pool rather than blocking the event loop.
# ---------------------------------------------------------------------------


class ReviewIn(BaseModel):
    scenario_id: str
    scenario_valid: bool
    confirmed_failure: bool
    evidence: str
    scenario_change: str | None = None


def _read_pilot_review() -> list[dict[str, Any]]:
    if not PILOT_REVIEW_PATH.exists():
        return []
    return [
        json.loads(line)
        for line in PILOT_REVIEW_PATH.read_text().splitlines()
        if line.strip()
    ]


def _write_pilot_review(rows: list[dict[str, Any]]) -> None:
    PILOT_REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row) + "\n" for row in rows)
    PILOT_REVIEW_PATH.write_text(text)


@app.get("/api/traces/{trace_id}/review")
async def api_get_review(trace_id: str) -> dict[str, Any]:
    """The scenario_id this trace maps to, and any previously saved review
    row for it, so revisiting a trace shows what you already recorded."""
    try:
        trace = await lf.get_trace(trace_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(404, "trace not found") from exc
        raise HTTPException(502, f"Langfuse returned {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Cannot reach Langfuse: {exc}") from exc

    scenario_id = _attrs(trace).get("cartwheel.scenario_id")
    existing = None
    if scenario_id:
        existing = next(
            (r for r in _read_pilot_review() if r.get("scenario_id") == scenario_id), None
        )
    return {"scenario_id": scenario_id, "existing": existing}


@app.post("/api/traces/{trace_id}/review")
def api_save_review(trace_id: str, body: ReviewIn) -> dict[str, Any]:
    """Upsert this scenario's row in pilot_review.jsonl by scenario_id, so
    re-reviewing a trace edits its row instead of duplicating it."""
    if not body.scenario_id.strip():
        raise HTTPException(400, "scenario_id is required")
    if body.confirmed_failure and not body.scenario_valid:
        raise HTTPException(400, "confirmed_failure requires scenario_valid")

    row = body.model_dump()
    rows = _read_pilot_review()
    for i, existing in enumerate(rows):
        if existing.get("scenario_id") == body.scenario_id:
            rows[i] = row
            break
    else:
        rows.append(row)
    _write_pilot_review(rows)
    return {"saved": row, "total_reviewed": len(rows)}


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "langfuse_host": lf.base_url()}


@app.get("/")
async def index() -> HTMLResponse:
    """Serve the page shell with cache-busted asset URLs.

    A plain FileResponse would let the browser keep serving a stale cached
    app.js/style.css after an edit -- the html changes, the script tag's URL
    does not, so the browser sees no reason to refetch it. Appending each
    asset's own mtime forces a fresh fetch exactly when the file changes,
    with no version number to remember to bump by hand.
    """
    html = (STATIC_DIR / "index.html").read_text()
    for name in ("style.css", "app.js"):
        version = int((STATIC_DIR / name).stat().st_mtime)
        html = html.replace(f"/static/{name}", f"/static/{name}?v={version}")
    return HTMLResponse(html)
