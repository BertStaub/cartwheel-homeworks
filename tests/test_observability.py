"""Homework 2, Part D: authentication tests for the session endpoints.

Offline: no Langfuse, Docker, or model provider key required. These call
create_session and _authorize directly rather than through an HTTP client.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from server import app as server_app


def test_create_session_rejects_role_mismatch(world: dict) -> None:
    server_app._SESSIONS.clear()
    # User 9002 is a merchant in the seeded world; claiming a different role
    # for that same user id must be rejected, not silently accepted.
    with pytest.raises(HTTPException) as exc_info:
        server_app.create_session(server_app.SessionCreate(user_id=9002, role="shopper"))
    assert exc_info.value.status_code == 403


def test_token_for_one_session_cannot_authorize_another(world: dict) -> None:
    server_app._SESSIONS.clear()
    session_a = server_app.create_session(server_app.SessionCreate(user_id=1, role="shopper"))
    session_b = server_app.create_session(
        server_app.SessionCreate(user_id=9002, role="merchant")
    )

    with pytest.raises(HTTPException) as exc_info:
        server_app._authorize(session_b["session_id"], f"Bearer {session_a['token']}")
    assert exc_info.value.status_code == 403
