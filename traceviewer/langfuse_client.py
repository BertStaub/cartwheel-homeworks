"""Minimal async client for Langfuse's public API.

Mostly read (GET): traces and observations. Two write paths exist for the
trace viewer's notes feature: `create_comment` posts a free-text comment on
a trace or observation. Langfuse's public API has no update or delete for
comments, so a posted comment is permanent -- there is no edit/retract path
here or in Langfuse itself.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from observability.instrument import load_env


def base_url() -> str:
    load_env()
    return os.environ.get("LANGFUSE_HOST", "http://localhost:3000").rstrip("/")


def _auth() -> tuple[str, str]:
    load_env()
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        raise RuntimeError(
            "LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY are not set. Copy .env.example "
            "to .env and start the stack: docker compose -f observability/docker-compose.yml up -d"
        )
    return public_key, secret_key


async def list_traces(page: int = 1, limit: int = 25) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=base_url(), auth=_auth(), timeout=15) as client:
        resp = await client.get("/api/public/traces", params={"page": page, "limit": limit})
        resp.raise_for_status()
        return resp.json()


async def get_trace(trace_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=base_url(), auth=_auth(), timeout=15) as client:
        resp = await client.get(f"/api/public/traces/{trace_id}")
        resp.raise_for_status()
        return resp.json()


async def get_session(session_id: str) -> dict[str, Any]:
    """A Langfuse session: every trace sharing this session's `session.id`
    span attribute (see server/app.py), returned together. This is how a
    multi-turn scenario's separate HTTP-request traces come back as one
    conversation instead of requiring client-side stitching."""
    async with httpx.AsyncClient(base_url=base_url(), auth=_auth(), timeout=20) as client:
        resp = await client.get(f"/api/public/sessions/{session_id}")
        resp.raise_for_status()
        return resp.json()


async def list_observations(trace_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """`limit` is capped at 100 by Langfuse's API; a trace with more spans
    than that would only show its first 100 here."""
    async with httpx.AsyncClient(base_url=base_url(), auth=_auth(), timeout=15) as client:
        resp = await client.get(
            "/api/public/observations", params={"traceId": trace_id, "limit": limit}
        )
        resp.raise_for_status()
        return resp.json()["data"]


_project_id: str | None = None


async def project_id() -> str:
    """The project id visible to this API key, cached after the first lookup."""
    global _project_id
    if _project_id is None:
        async with httpx.AsyncClient(base_url=base_url(), auth=_auth(), timeout=15) as client:
            resp = await client.get("/api/public/projects")
            resp.raise_for_status()
            projects = resp.json()["data"]
        if not projects:
            raise RuntimeError("no Langfuse project is visible to this API key")
        _project_id = projects[0]["id"]
    return _project_id


async def create_comment(object_type: str, object_id: str, content: str) -> dict[str, Any]:
    """Attach a free-text comment to a trace or observation. See module
    docstring: Langfuse has no endpoint to edit or delete a comment afterward.
    """
    pid = await project_id()
    async with httpx.AsyncClient(base_url=base_url(), auth=_auth(), timeout=15) as client:
        resp = await client.post(
            "/api/public/comments",
            json={
                "projectId": pid,
                "objectType": object_type,
                "objectId": object_id,
                "content": content,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def list_comments(object_type: str, object_id: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(base_url=base_url(), auth=_auth(), timeout=15) as client:
        resp = await client.get(
            "/api/public/comments",
            params={"objectType": object_type, "objectId": object_id, "limit": 100},
        )
        resp.raise_for_status()
        return resp.json()["data"]
