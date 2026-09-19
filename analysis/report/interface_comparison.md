# Interface comparison: `analysis/review_app/` vs. the course reference

The course reference (`analysis/server.py` + `analysis/ui/index.html`) implements the
generic error-discovery skill server: a trace/map/progress view built to work on any
dataset shape. `analysis/review_app/` is a narrower, Cartwheel-specific tool built after
reviewing several traces by hand in Langfuse's own annotation view.

## One design retained from the reference

The annotation record shape. The reference reads and writes
`analysis/state/annotations.json` records shaped `{id, trace_id, quote, start, end, note,
ts}`, and syncs a record to a Langfuse score only when it additionally carries a `mode`
and a 0/1 `label`. `review_app` keeps that same base shape and only adds fields the
reference does not know about (`session_id`, `segment_index`, `segment_label`) rather than
inventing a new file or a new schema. Both tools can read the same
`annotations.json` without stepping on each other, and the existing
`_sync_annotation_scores` pattern in the reference server is exactly what `review_app`
should reuse once Part E adds `mode`/`label` to a saved judgment, instead of writing a
second Langfuse-sync code path.

## One design changed after inspecting my traces

Multi-turn grouping. Cartwheel opens one Langfuse trace per user turn, so a follow-up
message in a multi-turn conversation showed up as its own disconnected trace in the
reference's per-trace view, with no visible link to the earlier turns' tool calls. That
was the single biggest friction point from the manual Langfuse review: stitching a
conversation back together by hand across several trace pages. `review_app` fixes this
at the data layer, not just the display layer: every trace is tagged with a
`cartwheel.session_id`, and `alt_server`'s `_fetch_all_traces` calls
`_merge_multi_turn` before the UI ever sees the records, so one sidebar entry always
represents one full conversation in chronological order.

## One limitation remaining

`review_app` only supports open coding today — a free-text note tied to one exact
message or tool call. It does not yet have a taxonomy view, a structured
present/absent labeling grid per trace and mode, a progress view, or an AI-suggestions
queue with accept/reject controls, and it does not write anything to Langfuse as a
score. Those four features are real "must provide" items for the finished interface,
but they all depend on data that does not exist yet at this point in the assignment (a
taxonomy from Part D, a defined review set from Part B, mode-scan suggestions from Part
C/D). They are deferred by design rather than overlooked, and will be added as each
part produces the data the corresponding view needs.
