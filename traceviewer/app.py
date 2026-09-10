"""Local, read-only trace viewer for the Cartwheel support agent.

Reads directly from the Langfuse API on every request; this app keeps no
state of its own and writes nothing (no annotations, no scores, no database).
It exists to make a trace easy to read end to end -- conversation, tool
calls with full arguments/results, and a raw observation view -- without
clicking through the Langfuse UI.

Run with:
    uv run uvicorn traceviewer.app:app --port 8030
"""

from __future__ import annotations

import asyncio
import difflib
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from traceviewer import langfuse_client as lf

STATIC_DIR = Path(__file__).resolve().parent / "static"

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

    summaries = []
    for trace, observations in zip(traces, observations_by_trace):
        attrs = _attrs(trace)
        tools = [o for o in observations if o.get("type") == "TOOL"]
        summaries.append(
            {
                "trace_id": trace["id"],
                "timestamp": trace.get("timestamp"),
                "user_role": attrs.get("cartwheel.user_role"),
                "user_id": attrs.get("cartwheel.user_id"),
                "prompt_version": attrs.get("cartwheel.prompt_version"),
                "input_preview": _preview(_text_of(trace.get("input"))),
                "output_preview": _preview(_text_of(trace.get("output"))),
                "tool_names": [o.get("name") for o in tools],
                "tool_count": len(tools),
                "has_error": _has_error(observations),
                "latency": trace.get("latency"),
                "total_cost": trace.get("totalCost"),
                "permalink": _permalink(trace["id"], trace.get("htmlPath")),
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
    try:
        trace = await lf.get_trace(trace_id)
        observations = await lf.list_observations(trace_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(404, "trace not found") from exc
        raise HTTPException(502, f"Langfuse returned {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Cannot reach Langfuse: {exc}") from exc

    observations = sorted(observations, key=lambda o: o.get("startTime") or "")
    turns = _build_turns(observations)

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

    attrs = _attrs(trace)
    return {
        "trace_id": trace_id,
        "permalink": _permalink(trace_id, trace.get("htmlPath")),
        "has_error": _has_error(observations),
        "conversation": {
            "user_message": _text_of(trace.get("input")),
            "assistant_reply": _text_of(trace.get("output")),
            "user_role": attrs.get("cartwheel.user_role"),
            "user_id": attrs.get("cartwheel.user_id"),
            "store_id": attrs.get("cartwheel.store_id"),
            "prompt_version": attrs.get("cartwheel.prompt_version"),
            "scenario_id": attrs.get("cartwheel.scenario_id"),
            "turns": turns,
        },
        "timeline": timeline,
        "raw": {"trace": trace, "observations": observations},
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "langfuse_host": lf.base_url()}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
