"""Alternate single-page trace review interface (personal build, HW4 prep).

Independent of the course reference (``analysis/server.py`` + ``analysis/ui/``
untouched). Built to a fixed, narrower spec than the reference's four-view
app: one page, one scenario at a time, showing:

  - the scenario's conversation messages in timestamp order,
  - each tool call rendered next to its result,
  - the scenario's expected outcome, read from the scenario JSONL files
    (``scenarios/pilot_scenarios.jsonl`` and ``scenarios/support_scenarios.jsonl``),
  - a free-text annotation field tied to the specific message or tool call
    clicked, not the trace as a whole.

Annotations are appended to ``analysis/state/annotations.json`` in the same
shape the course reference app reads (``{id, trace_id, quote, start, end,
note, ts}``), plus two extra fields:

  - ``session_id``: Homework 3 added a ``session.id`` span attribute (not
    part of the course instructions) so Langfuse groups a multi-turn
    scenario's several traces into one conversation; this app resolves it
    and records it so a note can be traced back to the right Langfuse
    session, not just a single component trace.
  - ``segment_index`` / ``segment_label``: which exact message or tool call
    within the trace's ordered message list the note is about (an index
    into that list, and a short label like ``"tool call: get_order"``).
    ``quote`` is populated with a short preview of that item's text instead
    of staying null.

The reference app ignores fields it does not know about, so the shared file
stays readable by both.

Run:
    uv run python -m analysis.alt_server            # serves on :8040
    uv run python -m analysis.alt_server --port 8041
"""

from __future__ import annotations

import argparse
import json
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from analysis.helpers._state import read_json, state_path, write_json
from analysis.helpers.normalization import _data, _merge_multi_turn, normalize_trace

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
UI_DIR = HERE / "ui_alt"
ANNOTATIONS_PATH = state_path("annotations.json")

SCENARIO_FILES = [
    REPO_ROOT / "scenarios" / "pilot_scenarios.jsonl",
    REPO_ROOT / "scenarios" / "support_scenarios.jsonl",
]

_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"traces": None, "fetched_at": None, "status": "idle", "error": None}


def _load_scenario_index() -> dict[str, dict[str, Any]]:
    """scenario_id -> {expected, tuple, scenario_group, opening_message}."""
    index: dict[str, dict[str, Any]] = {}
    for path in SCENARIO_FILES:
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                index[record["id"]] = {
                    "expected": record.get("expected"),
                    "tuple": record.get("tuple"),
                    "scenario_group": record.get("scenario_group"),
                    "opening_message": record.get("opening_message"),
                }
    return index


def _langfuse_base_url() -> str:
    import os

    return os.environ.get("LANGFUSE_HOST", "http://localhost:3000").rstrip("/")


def _fetch_all_traces() -> list[dict[str, Any]]:
    from observability.instrument import load_env

    load_env()
    from langfuse import Langfuse

    lf = Langfuse()
    base_url = _langfuse_base_url()

    summaries: list[Any] = []
    page = 1
    while True:
        resp = lf.api.trace.list(page=page, limit=100)
        batch = list(resp.data or [])
        summaries.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    print(f"[alt_server] fetching {len(summaries)} full trace records from Langfuse...", flush=True)
    raw_by_id: dict[str, dict[str, Any]] = {}
    for i, summary in enumerate(summaries, 1):
        full = _data(lf.api.trace.get(summary.id))
        if isinstance(full, dict) and full.get("id"):
            raw_by_id[str(full["id"])] = full
        if i % 25 == 0 or i == len(summaries):
            print(f"[alt_server]   ...{i}/{len(summaries)}", flush=True)

    session_by_trace = {tid: raw.get("sessionId") for tid, raw in raw_by_id.items()}

    normalized: list[dict[str, Any]] = []
    for trace_id, raw in raw_by_id.items():
        try:
            record = normalize_trace(raw)
        except ValueError as exc:
            # A trace with no renderable content (e.g. the orphaned timeout
            # attempt from a killed run) should not take down the whole page.
            print(f"[alt_server]   skipping {trace_id}: {exc}", flush=True)
            continue
        session_id = session_by_trace.get(trace_id)
        record["session_id"] = session_id
        record["trace_permalink"] = f"{base_url}/project/cartwheel-dev/traces/{trace_id}"
        record["session_permalink"] = (
            f"{base_url}/project/cartwheel-dev/sessions/{session_id}" if session_id else None
        )
        normalized.append(record)

    merged = _merge_multi_turn(normalized)

    scenario_index = _load_scenario_index()
    for record in merged:
        scenario_id = record["meta"].get("scenario_id")
        info = scenario_index.get(scenario_id, {})
        record["expected"] = info.get("expected")
        record["scenario_group"] = info.get("scenario_group")
        record["tuple"] = info.get("tuple")

    merged.sort(key=lambda r: r["meta"].get("scenario_id") or r["trace_id"])
    return merged


def refresh_traces() -> None:
    with _cache_lock:
        if _cache["status"] == "loading":
            return
        _cache["status"] = "loading"
        _cache["error"] = None

    try:
        traces = _fetch_all_traces()
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        with _cache_lock:
            _cache["status"] = "error"
            _cache["error"] = str(exc)
        print(f"[alt_server] fetch failed: {exc}", flush=True)
        return

    with _cache_lock:
        _cache["traces"] = traces
        _cache["fetched_at"] = datetime.now(timezone.utc).isoformat()
        _cache["status"] = "ready"
    print(f"[alt_server] ready: {len(traces)} scenarios loaded", flush=True)


def _snapshot() -> dict[str, Any]:
    with _cache_lock:
        return {
            "status": _cache["status"],
            "error": _cache["error"],
            "fetched_at": _cache["fetched_at"],
            "traces": _cache["traces"] or [],
        }


def _read_annotations() -> dict[str, Any]:
    data = read_json(ANNOTATIONS_PATH, default={"annotations": []})
    if not isinstance(data, dict) or not isinstance(data.get("annotations"), list):
        return {"annotations": []}
    return data


def _append_annotation(payload: dict[str, Any]) -> dict[str, Any]:
    trace_id = str(payload.get("trace_id") or "").strip()
    note = str(payload.get("note") or "").strip()
    if not trace_id or not note:
        raise ValueError("trace_id and note are both required")
    record = {
        "id": uuid.uuid4().hex,
        "trace_id": trace_id,
        "quote": payload.get("quote"),
        "start": None,
        "end": None,
        "note": note,
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": payload.get("session_id"),
        # Which exact message or tool call this note is about -- the index
        # into that trace's ordered message list, and a short human-readable
        # label (e.g. "tool call: get_order"), not just a whole-trace note.
        "segment_index": payload.get("segment_index"),
        "segment_label": payload.get("segment_label"),
    }
    data = _read_annotations()
    data["annotations"].append(record)
    write_json(ANNOTATIONS_PATH, data)
    return record


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # quieter default log
        print(f"[alt_server] {self.address_string()} {fmt % args}", flush=True)

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib method name
        if self.path == "/" or self.path == "/index.html":
            self._send_file(UI_DIR / "index.html", "text/html; charset=utf-8")
        elif self.path.startswith("/api/traces"):
            self._send_json(_snapshot())
        elif self.path.startswith("/api/annotations"):
            self._send_json(_read_annotations())
        else:
            self.send_error(404, "not found")

    def do_POST(self) -> None:  # noqa: N802 - stdlib method name
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON"}, status=400)
            return

        if self.path.startswith("/api/annotations"):
            try:
                record = _append_annotation(payload)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json({"ok": True, "annotation": record})
        elif self.path.startswith("/api/refresh"):
            threading.Thread(target=refresh_traces, daemon=True).start()
            self._send_json({"ok": True, "status": "loading"})
        else:
            self.send_error(404, "not found")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8040)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    threading.Thread(target=refresh_traces, daemon=True).start()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[alt_server] serving on http://{args.host}:{args.port} (fetching traces in the background)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
