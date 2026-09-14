"""Trace viewer: the two write paths added for Homework 3 pilot review.

Offline: no Langfuse, Docker, or model provider key required. These call the
route functions directly, and cover only the parts that don't touch the
Langfuse API (or, for api_get_review, with lf.get_trace monkeypatched).
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException

from traceviewer import app as tv_app
from traceviewer import langfuse_client as lf


@pytest.fixture
def pilot_review_path(tmp_path, monkeypatch):
    path = tmp_path / "pilot_review.jsonl"
    monkeypatch.setattr(tv_app, "PILOT_REVIEW_PATH", path)
    return path


def _review_in(**overrides):
    fields = dict(
        scenario_id="pilot-0001",
        scenario_valid=True,
        confirmed_failure=False,
        evidence="order #4127 has no delivery date in the database",
        scenario_change=None,
    )
    fields.update(overrides)
    return tv_app.ReviewIn(**fields)


def test_save_review_upserts_by_scenario_id(pilot_review_path) -> None:
    tv_app.api_save_review("trace-a", _review_in(evidence="first pass"))
    result = tv_app.api_save_review("trace-a", _review_in(evidence="revised after a second look"))

    rows = [json.loads(line) for line in pilot_review_path.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["evidence"] == "revised after a second look"
    assert result["total_reviewed"] == 1


def test_save_review_preserves_other_scenarios(pilot_review_path) -> None:
    tv_app.api_save_review("trace-a", _review_in(scenario_id="pilot-0001"))
    tv_app.api_save_review("trace-b", _review_in(scenario_id="pilot-0002"))

    rows = [json.loads(line) for line in pilot_review_path.read_text().splitlines()]
    assert {r["scenario_id"] for r in rows} == {"pilot-0001", "pilot-0002"}


def test_save_review_rejects_confirmed_failure_without_valid_scenario(pilot_review_path) -> None:
    with pytest.raises(HTTPException) as exc_info:
        tv_app.api_save_review(
            "trace-a", _review_in(scenario_valid=False, confirmed_failure=True)
        )
    assert exc_info.value.status_code == 400


def test_save_review_rejects_empty_scenario_id(pilot_review_path) -> None:
    with pytest.raises(HTTPException) as exc_info:
        tv_app.api_save_review("trace-a", _review_in(scenario_id="   "))
    assert exc_info.value.status_code == 400


def test_get_review_returns_existing_row_for_scenario(pilot_review_path, monkeypatch) -> None:
    tv_app.api_save_review("trace-a", _review_in(scenario_id="pilot-0007", evidence="prior review"))

    async def fake_get_trace(trace_id: str):
        assert trace_id == "trace-a"
        return {"metadata": {"attributes": {"cartwheel.scenario_id": "pilot-0007"}}}

    monkeypatch.setattr(lf, "get_trace", fake_get_trace)

    result = asyncio.run(tv_app.api_get_review("trace-a"))
    assert result["scenario_id"] == "pilot-0007"
    assert result["existing"]["evidence"] == "prior review"


def test_get_review_no_scenario_id_on_trace(pilot_review_path, monkeypatch) -> None:
    async def fake_get_trace(trace_id: str):
        return {"metadata": {"attributes": {}}}

    monkeypatch.setattr(lf, "get_trace", fake_get_trace)

    result = asyncio.run(tv_app.api_get_review("trace-a"))
    assert result["scenario_id"] is None
    assert result["existing"] is None


def _stub_no_observations_or_comments(monkeypatch) -> None:
    """_build_exchange also calls list_observations/list_comments; stub both
    to empty so these tests only exercise the session-grouping logic."""

    async def fake_list_observations(trace_id: str, limit: int = 100):
        return []

    async def fake_list_comments(object_type: str, object_id: str):
        return []

    monkeypatch.setattr(lf, "list_observations", fake_list_observations)
    monkeypatch.setattr(lf, "list_comments", fake_list_comments)


def test_get_trace_without_session_id_returns_one_exchange(monkeypatch) -> None:
    _stub_no_observations_or_comments(monkeypatch)

    async def fake_get_trace(trace_id: str):
        return {
            "id": "trace-a",
            "sessionId": None,
            "metadata": {"attributes": {"cartwheel.scenario_id": "pilot-0001"}},
        }

    monkeypatch.setattr(lf, "get_trace", fake_get_trace)

    result = asyncio.run(tv_app.api_get_trace("trace-a"))
    assert result["session_id"] is None
    assert result["scenario_id"] == "pilot-0001"
    assert [e["trace_id"] for e in result["exchanges"]] == ["trace-a"]


def test_get_trace_with_session_id_returns_every_member_in_order(monkeypatch) -> None:
    """Two traces (opening + followup) sharing one session id must come back
    as ordered exchanges, oldest first -- not just the trace that was
    clicked. This is the exact bug the pilot-0018 mis-grading came from."""
    _stub_no_observations_or_comments(monkeypatch)

    async def fake_get_trace(trace_id: str):
        return {"id": trace_id, "sessionId": "sess-1", "metadata": {"attributes": {}}}

    async def fake_get_session(session_id: str):
        assert session_id == "sess-1"
        return {
            "id": "sess-1",
            "traces": [
                {
                    "id": "trace-followup",
                    "sessionId": "sess-1",
                    "timestamp": "2026-01-01T00:00:10Z",
                    "metadata": {"attributes": {"cartwheel.scenario_id": "pilot-0018"}},
                },
                {
                    "id": "trace-opening",
                    "sessionId": "sess-1",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "metadata": {"attributes": {"cartwheel.scenario_id": "pilot-0018"}},
                },
            ],
        }

    monkeypatch.setattr(lf, "get_trace", fake_get_trace)
    monkeypatch.setattr(lf, "get_session", fake_get_session)

    result = asyncio.run(tv_app.api_get_trace("trace-followup"))
    assert result["session_id"] == "sess-1"
    assert [e["trace_id"] for e in result["exchanges"]] == ["trace-opening", "trace-followup"]


def test_attach_notes_is_keyed_per_span_not_per_turn(monkeypatch) -> None:
    """A tool call keeps its own notes even on a turn with no generation
    span (the rare _build_turns edge case) -- notes are per-observation."""

    async def fake_list_comments(object_type: str, object_id: str):
        assert object_type == "OBSERVATION"
        if object_id == "gen-1":
            return [{"id": "c1", "content": "model chose well", "createdAt": "2026-01-01T00:00:00Z"}]
        if object_id == "tool-2":
            return [{"id": "c2", "content": "wrong order id", "createdAt": "2026-01-02T00:00:00Z"}]
        return []

    monkeypatch.setattr(lf, "list_comments", fake_list_comments)

    turns = [
        {
            "turn_index": 1,
            "generation": {"observation_id": "gen-1"},
            "tool_calls": [{"observation_id": "tool-1"}],
        },
        {
            "turn_index": 2,
            "generation": None,
            "tool_calls": [{"observation_id": "tool-2"}],
        },
    ]
    asyncio.run(tv_app._attach_notes(turns))

    assert turns[0]["generation"]["notes"][0]["content"] == "model chose well"
    assert turns[0]["tool_calls"][0]["notes"] == []
    assert turns[1]["tool_calls"][0]["notes"][0]["content"] == "wrong order id"


def test_add_note_targets_the_observation(monkeypatch) -> None:
    calls = []

    async def fake_create_comment(object_type, object_id, content):
        calls.append((object_type, object_id, content))
        return {"id": "c1"}

    monkeypatch.setattr(lf, "create_comment", fake_create_comment)

    asyncio.run(tv_app.api_add_note("trace-a", "obs-9", tv_app.NoteIn(content="nice catch")))
    assert calls == [("OBSERVATION", "obs-9", "nice catch")]


def test_add_trace_note_targets_the_trace_not_an_observation(monkeypatch) -> None:
    """The assistant reply has no observation id of its own (it's
    trace.output), so its note must anchor to the trace id instead."""
    calls = []

    async def fake_create_comment(object_type, object_id, content):
        calls.append((object_type, object_id, content))
        return {"id": "c1"}

    monkeypatch.setattr(lf, "create_comment", fake_create_comment)

    asyncio.run(tv_app.api_add_trace_note("trace-a", tv_app.NoteIn(content="great final answer")))
    assert calls == [("TRACE", "trace-a", "great final answer")]
