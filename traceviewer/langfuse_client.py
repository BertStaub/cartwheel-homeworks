"""Minimal async client for Langfuse's public read API.

Read-only: every function here issues a GET. Nothing in this module writes,
scores, or annotates anything in Langfuse.
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


async def list_observations(trace_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """`limit` is capped at 100 by Langfuse's API; a trace with more spans
    than that would only show its first 100 here."""
    async with httpx.AsyncClient(base_url=base_url(), auth=_auth(), timeout=15) as client:
        resp = await client.get(
            "/api/public/observations", params={"traceId": trace_id, "limit": limit}
        )
        resp.raise_for_status()
        return resp.json()["data"]
