"use strict";

/* Cartwheel Trace Viewer frontend. No local storage of trace data itself --
 * everything is re-fetched from the backend (which itself re-fetches from
 * Langfuse) on every navigation. Two things you type here do get written
 * back: a note on a generation/tool-call span (to Langfuse, permanently --
 * see the notes-modal functions) and the pilot review form (upserted into
 * scenarios/pilot_review.jsonl). */

const state = {
  page: 1,
  limit: 25,
  totalPages: 1,
  traces: [], // the current page's trace summaries, as returned by the API
  diffSelection: [], // up to 2 trace ids, checked in the list for prompt diffing
};

// ---------------------------------------------------------------------------
// Small render helpers. Missing/null values are always shown explicitly,
// never silently dropped.
// ---------------------------------------------------------------------------

function esc(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function missingSpan() {
  return '<span class="missing">missing</span>';
}

function fmtVal(v) {
  if (v === null || v === undefined || v === "") return missingSpan();
  return esc(String(v));
}

function fmtTime(iso) {
  if (!iso) return missingSpan();
  const d = new Date(iso);
  if (isNaN(d.getTime())) return esc(iso);
  return `${esc(d.toLocaleString())} <span class="mono" style="color:var(--text-faint)">(${esc(iso)})</span>`;
}

// List page only: local date/time, no raw ISO/Zulu suffix (that's kept in
// the detail view, where preserving the exact recorded timestamp matters).
function fmtTimeShort(iso) {
  if (!iso) return missingSpan();
  const d = new Date(iso);
  if (isNaN(d.getTime())) return esc(iso);
  return esc(d.toLocaleString());
}

function fmtLatency(seconds) {
  if (seconds === null || seconds === undefined) return missingSpan();
  return `${(seconds * 1000).toFixed(0)} ms`;
}

function fmtCost(cost) {
  if (cost === null || cost === undefined) return missingSpan();
  return `$${cost.toFixed(6)}`;
}

function fmtJSON(v) {
  if (v === null || v === undefined) return missingSpan();
  try {
    return `<pre>${esc(JSON.stringify(v, null, 2))}</pre>`;
  } catch (e) {
    return `<pre>${esc(String(v))}</pre>`;
  }
}

function okBadge(ok) {
  if (ok === true) return '<span class="badge ok">ok</span>';
  if (ok === false) return '<span class="badge error">failed</span>';
  return '<span class="badge unknown">n/a</span>';
}

async function fetchJSON(url) {
  const resp = await fetch(url);
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail || detail;
    } catch (e) {
      /* ignore */
    }
    throw new Error(`${resp.status}: ${detail}`);
  }
  return resp.json();
}

async function postJSON(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const data = await resp.json();
      detail = data.detail || detail;
    } catch (e) {
      /* ignore */
    }
    throw new Error(`${resp.status}: ${detail}`);
  }
  return resp.json();
}

// ---------------------------------------------------------------------------
// Connection status (checked once on load)
// ---------------------------------------------------------------------------

async function checkConnection() {
  const el = document.getElementById("conn-status");
  try {
    const health = await fetchJSON("/health");
    el.textContent = `connected to Langfuse at ${health.langfuse_host}`;
    el.className = "conn-status ok";
  } catch (e) {
    el.textContent = `cannot reach backend: ${e.message}`;
    el.className = "conn-status error";
  }
}

// ---------------------------------------------------------------------------
// List view
// ---------------------------------------------------------------------------

async function loadList() {
  const statusEl = document.getElementById("list-status");
  statusEl.textContent = "loading…";
  statusEl.className = "status-line";
  try {
    const data = await fetchJSON(`/api/traces?page=${state.page}&limit=${state.limit}`);
    state.traces = data.traces;
    state.totalPages = data.total_pages || 1;
    state.page = data.page || state.page;
    statusEl.textContent = `${data.total_items} trace(s) total`;
    renderList();
  } catch (e) {
    statusEl.textContent = `failed to load traces: ${e.message}`;
    statusEl.className = "status-line error";
    document.getElementById("trace-rows").innerHTML = "";
  }
}

function applyFilters(traces) {
  const role = document.getElementById("filter-role").value;
  const issuesOnly = document.getElementById("filter-issues").checked;
  const search = document.getElementById("filter-search").value.trim().toLowerCase();

  return traces.filter((t) => {
    if (role && t.user_role !== role) return false;
    if (issuesOnly && !t.has_error) return false;
    if (search) {
      const hay = `${t.input_preview || ""} ${t.output_preview || ""}`.toLowerCase();
      if (!hay.includes(search)) return false;
    }
    return true;
  });
}

function renderList() {
  const rows = document.getElementById("trace-rows");
  const filtered = applyFilters(state.traces);
  rows.innerHTML = "";

  if (filtered.length === 0) {
    rows.innerHTML = `<tr><td colspan="11" class="missing">no traces match the current filters</td></tr>`;
  }

  for (const t of filtered) {
    const tr = document.createElement("tr");
    const statusBadge = t.has_error
      ? '<span class="badge error">⚠ issue</span>'
      : '<span class="badge ok">clean</span>';
    const checked = state.diffSelection.includes(t.trace_id) ? "checked" : "";
    tr.innerHTML = `
      <td class="select-col"><input type="checkbox" class="diff-checkbox" ${checked}></td>
      <td>${statusBadge}</td>
      <td class="nowrap">${fmtTimeShort(t.timestamp)}</td>
      <td>${fmtVal(t.user_role)}</td>
      <td class="mono">${fmtVal(t.user_id)}</td>
      <td class="mono">${fmtVal(t.prompt_version)}</td>
      <td class="mono">${fmtVal(t.scenario_id)}</td>
      <td class="mono">${fmtVal(t.turn_count)}</td>
      <td class="mono">${fmtVal(t.tool_count)}</td>
      <td class="nowrap">${fmtLatency(t.latency)}</td>
      <td class="nowrap">${fmtCost(t.total_cost)}</td>
    `;
    tr.addEventListener("click", () => {
      location.hash = `#/trace/${t.trace_id}`;
    });
    tr.querySelector(".diff-checkbox").addEventListener("click", (e) => {
      e.stopPropagation();
      toggleDiffSelection(t.trace_id);
    });
    rows.appendChild(tr);
  }

  document.getElementById("page-info").textContent = `page ${state.page} of ${state.totalPages}`;
  document.getElementById("prev-page").disabled = state.page <= 1;
  document.getElementById("next-page").disabled = state.page >= state.totalPages;
  updateDiffBar();
}

function toggleDiffSelection(traceId) {
  const idx = state.diffSelection.indexOf(traceId);
  if (idx !== -1) {
    state.diffSelection.splice(idx, 1);
  } else {
    state.diffSelection.push(traceId);
    if (state.diffSelection.length > 2) {
      // Keep only the 2 most recently checked traces.
      state.diffSelection.shift();
    }
  }
  renderList();
}

function updateDiffBar() {
  const info = document.getElementById("diff-selection-info");
  const btn = document.getElementById("diff-btn");
  const n = state.diffSelection.length;
  if (n === 0) {
    info.textContent = "Check 2 traces below to diff their prompts";
  } else if (n === 1) {
    info.textContent = `1 selected (${state.diffSelection[0]}) — check 1 more`;
  } else {
    info.textContent = `Ready to diff: ${state.diffSelection[0]} vs ${state.diffSelection[1]}`;
  }
  btn.disabled = n !== 2;
}

function setupListControls() {
  document.getElementById("filter-role").addEventListener("change", renderList);
  document.getElementById("filter-issues").addEventListener("change", renderList);
  document.getElementById("filter-search").addEventListener("input", renderList);
  document.getElementById("refresh-btn").addEventListener("click", loadList);
  document.getElementById("prev-page").addEventListener("click", () => {
    if (state.page > 1) {
      state.page -= 1;
      loadList();
    }
  });
  document.getElementById("next-page").addEventListener("click", () => {
    if (state.page < state.totalPages) {
      state.page += 1;
      loadList();
    }
  });
  document.getElementById("diff-btn").addEventListener("click", () => {
    if (state.diffSelection.length === 2) {
      location.hash = `#/diff/${state.diffSelection[0]}/${state.diffSelection[1]}`;
    }
  });
}

// ---------------------------------------------------------------------------
// Detail view
// ---------------------------------------------------------------------------

function renderToolCall(tc, traceId) {
  const tpl = document.getElementById("tpl-tool-call");
  const node = tpl.content.cloneNode(true);
  const card = node.querySelector(".tool-card");

  card.querySelector(".tool-badge").innerHTML = okBadge(tc.ok);
  card.querySelector(".tool-name").textContent = tc.name || "(missing name)";
  card.querySelector(".tool-latency").textContent =
    tc.latency !== null && tc.latency !== undefined ? `${(tc.latency * 1000).toFixed(0)} ms` : "";
  card.querySelector(".tool-id").textContent = tc.observation_id || "";
  wireNotesButton(card, traceId, tc);

  card.querySelector(".tool-obs-id").innerHTML = fmtVal(tc.observation_id);
  card.querySelector(".tool-start").innerHTML = fmtTime(tc.start_time);
  card.querySelector(".tool-end").innerHTML = fmtTime(tc.end_time);
  card.querySelector(".tool-level").innerHTML = fmtVal(tc.level);
  card.querySelector(".tool-status-message").innerHTML = fmtVal(tc.status_message);

  let pd = missingSpan();
  if (tc.permission_denied !== null && tc.permission_denied !== undefined) {
    const denied = String(tc.permission_denied) === "true";
    pd = denied
      ? `<span class="badge error">true</span> — ${fmtVal(tc.permission_denied_reason)}`
      : '<span class="badge ok">false</span>';
  }
  card.querySelector(".tool-permission-denied").innerHTML = pd;

  card.querySelector(".tool-args").outerHTML = fmtJSON(tc.input) || "<pre></pre>";
  card.querySelector(".tool-output").outerHTML = fmtJSON(tc.output) || "<pre></pre>";
  card.querySelector(".tool-raw").outerHTML = fmtJSON(tc.raw) || "<pre></pre>";

  // If this call failed, open it by default and flag the card so it's easy
  // to spot while scanning a long trace.
  if (tc.ok === false || (tc.level && tc.level !== "DEFAULT")) {
    card.setAttribute("open", "");
    card.style.borderColor = "var(--error)";
  }

  return node;
}

function renderGenerationCard(gen, traceId) {
  const tpl = document.getElementById("tpl-generation-card");
  const node = tpl.content.cloneNode(true);
  const card = node.querySelector(".tool-card");

  const isError = gen.level && gen.level !== "DEFAULT";
  card.querySelector(".tool-badge").innerHTML = isError
    ? '<span class="badge error">error</span>'
    : '<span class="badge unknown">model</span>';
  card.querySelector(".tool-latency").textContent =
    gen.latency !== null && gen.latency !== undefined ? `${(gen.latency * 1000).toFixed(0)} ms` : "";
  card.querySelector(".tool-id").textContent = gen.observation_id || "";
  wireNotesButton(card, traceId, gen);

  card.querySelector(".gen-obs-id").innerHTML = fmtVal(gen.observation_id);
  card.querySelector(".gen-model").innerHTML = fmtVal(gen.model);
  card.querySelector(".gen-start").innerHTML = fmtTime(gen.start_time);
  card.querySelector(".gen-end").innerHTML = fmtTime(gen.end_time);
  card.querySelector(".gen-level").innerHTML = fmtVal(gen.level);
  card.querySelector(".gen-status-message").innerHTML = fmtVal(gen.status_message);
  card.querySelector(".gen-tokens").innerHTML = fmtVal(gen.total_tokens);
  card.querySelector(".gen-cost").innerHTML = gen.total_cost ? fmtCost(gen.total_cost) : missingSpan();
  card.querySelector(".gen-raw").outerHTML = fmtJSON(gen.raw) || "<pre></pre>";

  if (isError) card.style.borderColor = "var(--error)";

  return node;
}

// ---------------------------------------------------------------------------
// Notes popup. Every generation/tool-call span carries its own `notes`
// array and `observation_id` (see _attach_notes in app.py) and posts to its
// own observation URL; the assistant reply isn't a span at all (it's
// trace.output), so it carries `conversation.notes` instead and posts to
// the trace-level notes URL. Either way the modal itself only needs a
// postUrl, the current notes array, and a badge element to update.
// ---------------------------------------------------------------------------

const notesModal = { postUrl: null, notes: null, badgeEl: null };

function updateNotesBadge(badgeEl, count) {
  badgeEl.textContent = count > 0 ? String(count) : "";
  badgeEl.closest(".notes-btn").classList.toggle("has-notes", count > 0);
}

function wireNotesButton(card, traceId, span) {
  const btn = card.querySelector(".notes-btn");
  const badge = btn.querySelector(".notes-count");
  updateNotesBadge(badge, span.notes.length);
  const postUrl = `/api/traces/${encodeURIComponent(traceId)}/observations/${encodeURIComponent(span.observation_id)}/notes`;
  const label = span.name || (span.model ? `model call (${span.model})` : "model call");
  btn.addEventListener("click", (e) => {
    e.preventDefault(); // don't also toggle the <details> open/closed
    e.stopPropagation();
    openNotesModal(postUrl, span.notes, badge, label);
  });
}

// The whole assistant-reply card is clickable (it's a plain div, not a
// <details> that a click would otherwise toggle) and posts a trace-level
// comment, since the reply itself has no observation id of its own.
function wireCardNotes(cardEl, badgeEl, traceId, notes, label) {
  const postUrl = `/api/traces/${encodeURIComponent(traceId)}/notes`;
  updateNotesBadge(badgeEl, notes.length);
  cardEl.classList.add("notes-clickable");
  cardEl.title = "Click to view or add a note on this reply";
  cardEl.addEventListener("click", () => openNotesModal(postUrl, notes, badgeEl, label));
}

function renderNotesList() {
  const list = document.getElementById("notes-modal-list");
  list.innerHTML = "";
  if (notesModal.notes.length === 0) {
    list.innerHTML = '<span class="missing">no notes yet</span>';
    return;
  }
  for (const n of notesModal.notes) {
    const item = document.createElement("div");
    item.className = "note-item";
    const time = document.createElement("span");
    time.className = "note-time";
    time.textContent = new Date(n.created_at).toLocaleString();
    const content = document.createElement("div");
    content.className = "note-content";
    content.textContent = n.content;
    item.appendChild(time);
    item.appendChild(content);
    list.appendChild(item);
  }
}

function openNotesModal(postUrl, notes, badgeEl, label) {
  notesModal.postUrl = postUrl;
  notesModal.notes = notes;
  notesModal.badgeEl = badgeEl;

  document.getElementById("notes-modal-title").textContent = label ? `Notes — ${label}` : "Notes";
  document.getElementById("notes-modal-textarea").value = "";
  const status = document.getElementById("notes-modal-status");
  status.textContent = "";
  status.className = "note-status";
  renderNotesList();
  document.getElementById("notes-modal").hidden = false;
  document.getElementById("notes-modal-textarea").focus();
}

function closeNotesModal() {
  document.getElementById("notes-modal").hidden = true;
}

async function saveNoteFromModal() {
  const textarea = document.getElementById("notes-modal-textarea");
  const status = document.getElementById("notes-modal-status");
  const saveBtn = document.getElementById("notes-modal-save");
  const content = textarea.value.trim();
  if (!content) return;

  saveBtn.disabled = true;
  status.textContent = "saving…";
  status.className = "note-status";
  try {
    const note = await postJSON(notesModal.postUrl, { content });
    notesModal.notes.push({ id: note.id, content, created_at: new Date().toISOString() });
    updateNotesBadge(notesModal.badgeEl, notesModal.notes.length);
    textarea.value = "";
    status.textContent = "saved";
    renderNotesList();
  } catch (e) {
    status.textContent = `failed: ${e.message}`;
    status.className = "note-status error";
  } finally {
    saveBtn.disabled = false;
  }
}

function setupNotesModal() {
  document.getElementById("notes-modal-close").addEventListener("click", closeNotesModal);
  document.getElementById("notes-modal-save").addEventListener("click", saveNoteFromModal);
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !document.getElementById("notes-modal").hidden) closeNotesModal();
  });
}

function renderTurn(turn, traceId) {
  const wrap = document.createElement("div");
  wrap.className = "turn";

  const hasIssue =
    (turn.generation && turn.generation.level && turn.generation.level !== "DEFAULT") ||
    turn.tool_calls.some((tc) => tc.ok === false || (tc.level && tc.level !== "DEFAULT"));

  const divider = document.createElement("div");
  divider.className = "turn-divider";
  const bits = [`Turn ${turn.turn_index}`];
  if (turn.generation) {
    if (turn.generation.model) bits.push(esc(turn.generation.model));
    if (turn.generation.latency !== null && turn.generation.latency !== undefined) {
      bits.push(`${(turn.generation.latency * 1000).toFixed(0)} ms`);
    }
    if (turn.generation.total_tokens) bits.push(`${turn.generation.total_tokens} tokens`);
    if (turn.generation.total_cost) bits.push(`$${turn.generation.total_cost.toFixed(6)}`);
  }
  if (turn.tool_calls.length) bits.push(`${turn.tool_calls.length} tool call(s)`);
  divider.innerHTML = bits.join(" · ") + (hasIssue ? ' <span class="badge error">⚠ issue</span>' : "");
  wrap.appendChild(divider);

  if (turn.generation) {
    wrap.appendChild(renderGenerationCard(turn.generation, traceId));
  }
  for (const tc of turn.tool_calls) {
    wrap.appendChild(renderToolCall(tc, traceId));
  }

  return wrap;
}

function renderTimelineRow(o) {
  const levelClass = o.level && o.level !== "DEFAULT" ? `level-${o.level.toLowerCase()}` : "";
  const tr = document.createElement("tr");
  tr.className = levelClass;
  tr.innerHTML = `
    <td>${fmtVal(o.type)}</td>
    <td>${fmtVal(o.name)}</td>
    <td>${fmtVal(o.level)}</td>
    <td>${fmtVal(o.status_message)}</td>
    <td>${fmtTime(o.start_time)}</td>
    <td>${o.latency !== null && o.latency !== undefined ? (o.latency * 1000).toFixed(0) + " ms" : missingSpan()}</td>
    <td>${fmtVal(o.model)}</td>
    <td>${o.total_tokens ? fmtVal(o.total_tokens) : missingSpan()}</td>
    <td>${o.total_cost ? fmtCost(o.total_cost) : missingSpan()}</td>
    <td>${fmtVal(o.observation_id)}</td>
  `;
  return tr;
}

async function loadDetail(traceId) {
  const container = document.getElementById("detail-content");
  container.innerHTML = `<p class="status-line">loading trace ${esc(traceId)}…</p>`;
  try {
    const data = await fetchJSON(`/api/traces/${encodeURIComponent(traceId)}`);
    let reviewState = { scenario_id: null, existing: null };
    try {
      // The review is keyed by scenario_id, which is the same across every
      // exchange in a session, so any one exchange's trace_id works here.
      const reviewTraceId = data.exchanges[0].trace_id;
      reviewState = await fetchJSON(`/api/traces/${encodeURIComponent(reviewTraceId)}/review`);
    } catch (e) {
      /* Review state is a nice-to-have; a failure here shouldn't block the
       * rest of the trace from rendering. */
    }
    renderDetail(data, reviewState);
  } catch (e) {
    container.innerHTML = `<p class="status-line error">failed to load trace: ${esc(e.message)}</p>`;
  }
}

function renderReviewForm(traceId, reviewState) {
  const section = document.createElement("section");
  section.className = "block review-block";
  section.innerHTML = "<h3>Pilot review — scenarios/pilot_review.jsonl</h3>";

  const scenarioId = reviewState.scenario_id;
  if (!scenarioId) {
    const note = document.createElement("p");
    note.className = "missing";
    note.textContent =
      "no cartwheel.scenario_id on this trace — not a scenario-runner request, nothing to record a pilot review against";
    section.appendChild(note);
    return section;
  }

  const existing = reviewState.existing;
  const form = document.createElement("div");
  form.className = "review-form";
  form.innerHTML = `
    <div class="field"><span class="field-label">Scenario ID</span><span class="mono">${esc(scenarioId)}</span></div>
    <label class="checkbox"><input type="checkbox" class="rv-valid"> scenario_valid</label>
    <label class="checkbox"><input type="checkbox" class="rv-failure"> confirmed_failure</label>
    <div class="field-block">
      <span class="field-label">Evidence</span>
      <textarea class="rv-evidence" placeholder="database value, policy, tool result, or requirement that supports your decision"></textarea>
    </div>
    <div class="field-block">
      <span class="field-label">Scenario change (leave blank if none needed)</span>
      <textarea class="rv-change"></textarea>
    </div>
    <div class="note-form-row"><button type="button" class="rv-save">Save review</button><span class="rv-status"></span></div>
  `;
  const validCb = form.querySelector(".rv-valid");
  const failureCb = form.querySelector(".rv-failure");
  const evidenceEl = form.querySelector(".rv-evidence");
  const changeEl = form.querySelector(".rv-change");
  const status = form.querySelector(".rv-status");

  if (existing) {
    validCb.checked = !!existing.scenario_valid;
    failureCb.checked = !!existing.confirmed_failure;
    evidenceEl.value = existing.evidence || "";
    changeEl.value = existing.scenario_change || "";
  }

  // confirmed_failure only counts when scenario_valid is true (hw3.md).
  function syncFailureEnabled() {
    failureCb.disabled = !validCb.checked;
    if (!validCb.checked) failureCb.checked = false;
  }
  syncFailureEnabled();
  validCb.addEventListener("change", syncFailureEnabled);

  form.querySelector(".rv-save").addEventListener("click", async () => {
    status.textContent = "saving…";
    status.className = "rv-status";
    try {
      const result = await postJSON(`/api/traces/${encodeURIComponent(traceId)}/review`, {
        scenario_id: scenarioId,
        scenario_valid: validCb.checked,
        confirmed_failure: failureCb.checked,
        evidence: evidenceEl.value,
        scenario_change: changeEl.value.trim() ? changeEl.value : null,
      });
      status.textContent = `saved (${result.total_reviewed} scenario(s) reviewed so far)`;
    } catch (e) {
      status.textContent = `failed: ${e.message}`;
      status.className = "rv-status error";
    }
  });

  section.appendChild(form);
  return section;
}

// One HTTP request's worth of the conversation: the user message that
// triggered it, the agent's internal turns, and its final reply. A session
// with followups renders several of these, one after another, in order.
function renderExchange(exchange, index, total) {
  const wrap = document.createElement("div");
  wrap.className = "exchange";

  const divider = document.createElement("div");
  divider.className = "exchange-divider";
  const bits = total > 1 ? [`Exchange ${index + 1} of ${total}`] : [];
  if (exchange.timestamp) bits.push(new Date(exchange.timestamp).toLocaleString());
  const issueBadge = exchange.has_error ? ' <span class="badge error">⚠ issue</span>' : "";
  divider.innerHTML =
    `<span>${esc(bits.join(" · "))}</span>${issueBadge}` +
    `<a class="permalink" href="${esc(exchange.permalink)}" target="_blank" rel="noopener">trace ↗</a>`;
  wrap.appendChild(divider);

  const userCard = document.createElement("div");
  userCard.className = "message-card user";
  userCard.innerHTML = `<span class="role-label">User</span><div class="content">${
    exchange.user_message ? esc(exchange.user_message) : missingSpan()
  }</div>`;
  wrap.appendChild(userCard);

  if (exchange.turns.length === 0) {
    const none = document.createElement("p");
    none.className = "missing";
    none.textContent = "no model or tool spans recorded for this exchange";
    wrap.appendChild(none);
  } else {
    for (const turn of exchange.turns) {
      wrap.appendChild(renderTurn(turn, exchange.trace_id));
    }
  }

  const assistantCard = document.createElement("div");
  assistantCard.className = "message-card assistant";
  assistantCard.innerHTML = `
    <span class="role-label">Assistant <span class="notes-btn" title="Notes on this reply">📝<span class="notes-count"></span></span></span>
    <div class="content">${exchange.assistant_reply ? esc(exchange.assistant_reply) : missingSpan()}</div>
  `;
  wireCardNotes(
    assistantCard,
    assistantCard.querySelector(".notes-count"),
    exchange.trace_id,
    exchange.notes,
    "assistant reply"
  );
  wrap.appendChild(assistantCard);

  return wrap;
}

function renderExchangeTimeline(exchange, index, total) {
  const section = document.createElement("div");
  section.className = "exchange-timeline";
  const label = total > 1 ? `Exchange ${index + 1} of ${total} — ` : "";
  section.innerHTML = `
    <h4>${esc(label)}every span in this exchange</h4>
    <table class="timeline-table">
      <thead>
        <tr>
          <th>Type</th><th>Name</th><th>Level</th><th>Status message</th>
          <th>Start</th><th>Latency</th><th>Model</th><th>Tokens</th><th>Cost</th><th>Observation ID</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  `;
  const tbody = section.querySelector("tbody");
  for (const o of exchange.timeline) {
    tbody.appendChild(renderTimelineRow(o));
  }
  return section;
}

function renderDetail(data, reviewState) {
  const container = document.getElementById("detail-content");
  container.innerHTML = "";
  const entryTraceId = data.exchanges[0].trace_id;
  const exchangeCount = data.exchanges.length;

  // Header ---------------------------------------------------------------
  const header = document.createElement("div");
  header.className = "detail-header";
  const statusBadge = data.has_error
    ? '<span class="badge error">⚠ issue found</span>'
    : '<span class="badge ok">clean</span>';
  const idLabel = data.session_id ? `session ${data.session_id}` : entryTraceId;
  header.innerHTML = `
    <h2>${esc(idLabel)} ${statusBadge}</h2>
    <div class="detail-attrs">
      <div class="attr"><span class="field-label">Role</span>${fmtVal(data.user_role)}</div>
      <div class="attr"><span class="field-label">User ID</span>${fmtVal(data.user_id)}</div>
      <div class="attr"><span class="field-label">Store ID</span>${fmtVal(data.store_id)}</div>
      <div class="attr"><span class="field-label">Prompt version</span>${fmtVal(data.prompt_version)}</div>
      <div class="attr"><span class="field-label">Scenario ID</span>${fmtVal(data.scenario_id)}</div>
      <div class="attr"><span class="field-label">Exchanges</span>${fmtVal(exchangeCount)}</div>
      <div class="attr"><span class="field-label">Langfuse</span><a class="permalink" href="${esc(data.permalink)}" target="_blank" rel="noopener">open in Langfuse ↗</a></div>
    </div>
  `;
  container.appendChild(header);

  // Pilot review (Homework 3) ---------------------------------------------
  container.appendChild(renderReviewForm(entryTraceId, reviewState));

  // Conversation, every exchange in order ----------------------------------
  const convo = document.createElement("section");
  convo.className = "block";
  convo.innerHTML = "<h3>Conversation</h3>";
  data.exchanges.forEach((exchange, i) => {
    convo.appendChild(renderExchange(exchange, i, exchangeCount));
  });
  container.appendChild(convo);

  // Timeline, one table per exchange --------------------------------------
  const timelineSection = document.createElement("section");
  timelineSection.className = "block";
  timelineSection.innerHTML = "<h3>Timeline</h3>";
  data.exchanges.forEach((exchange, i) => {
    timelineSection.appendChild(renderExchangeTimeline(exchange, i, exchangeCount));
  });
  container.appendChild(timelineSection);

  // Raw observation view, one block per exchange ---------------------------
  const rawSection = document.createElement("section");
  rawSection.className = "block";
  rawSection.innerHTML = "<h3>Raw observation view</h3>";
  data.exchanges.forEach((exchange, i) => {
    const label = exchangeCount > 1 ? `Exchange ${i + 1} of ${exchangeCount} — ` : "";
    const details = document.createElement("details");
    details.className = "raw-block";
    details.innerHTML = `
      <summary>${esc(label)}unmodified Langfuse API response</summary>
      <div class="field-block"><span class="field-label">Trace</span>${fmtJSON(exchange.raw.trace)}</div>
      <div class="field-block"><span class="field-label">Observations (${exchange.raw.observations.length})</span>${fmtJSON(exchange.raw.observations)}</div>
    `;
    rawSection.appendChild(details);
  });
  container.appendChild(rawSection);
}

// ---------------------------------------------------------------------------
// Prompt diff view
// ---------------------------------------------------------------------------

async function loadDiff(traceIdA, traceIdB) {
  const container = document.getElementById("diff-content");
  container.innerHTML = `<p class="status-line">loading prompts for ${esc(traceIdA)} and ${esc(traceIdB)}…</p>`;
  try {
    const data = await fetchJSON(
      `/api/prompt-diff?a=${encodeURIComponent(traceIdA)}&b=${encodeURIComponent(traceIdB)}`
    );
    renderDiff(data);
  } catch (e) {
    container.innerHTML = `<p class="status-line error">failed to load prompt diff: ${esc(e.message)}</p>`;
  }
}

function renderDiff(data) {
  const container = document.getElementById("diff-content");
  container.innerHTML = "";

  const header = document.createElement("div");
  header.className = "diff-header";
  const missingNote = (side) =>
    side.prompt_text === null
      ? `<span class="missing">no system prompt captured for this trace (content capture may have been off)</span>`
      : "";
  header.innerHTML = `
    <div class="diff-side"><span class="field-label">Trace A</span><span class="mono">${esc(data.a.trace_id)}</span> — version <span class="mono">${fmtVal(data.a.prompt_version)}</span> ${missingNote(data.a)}</div>
    <div class="diff-side"><span class="field-label">Trace B</span><span class="mono">${esc(data.b.trace_id)}</span> — version <span class="mono">${fmtVal(data.b.prompt_version)}</span> ${missingNote(data.b)}</div>
    ${data.same_version ? '<div class="same-version-note">Both traces recorded the same prompt version — expect no differences below.</div>' : ""}
  `;
  container.appendChild(header);

  const block = document.createElement("div");
  block.className = "diff-block";
  if (data.a.prompt_text === null || data.b.prompt_text === null) {
    block.innerHTML = `<div class="diff-line missing">Cannot diff: at least one trace has no captured system prompt.</div>`;
  } else if (data.diff_lines.length === 0) {
    block.innerHTML = `<div class="diff-line context">No differences — these two traces used the exact same prompt text.</div>`;
  } else {
    for (const line of data.diff_lines) {
      const div = document.createElement("div");
      div.className = `diff-line ${line.type}`;
      div.textContent = line.text;
      block.appendChild(div);
    }
  }
  container.appendChild(block);
}

// ---------------------------------------------------------------------------
// Routing: #/  -> list view, #/trace/{id} -> detail view,
// #/diff/{idA}/{idB} -> prompt diff view
// ---------------------------------------------------------------------------

function route() {
  const hash = location.hash || "#/";
  const detailMatch = hash.match(/^#\/trace\/(.+)$/);
  const diffMatch = hash.match(/^#\/diff\/([^/]+)\/([^/]+)$/);
  const listView = document.getElementById("view-list");
  const detailView = document.getElementById("view-detail");
  const diffView = document.getElementById("view-diff");

  listView.hidden = true;
  detailView.hidden = true;
  diffView.hidden = true;

  if (diffMatch) {
    diffView.hidden = false;
    loadDiff(decodeURIComponent(diffMatch[1]), decodeURIComponent(diffMatch[2]));
  } else if (detailMatch) {
    detailView.hidden = false;
    loadDetail(decodeURIComponent(detailMatch[1]));
  } else {
    listView.hidden = false;
    loadList();
  }
}

window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", () => {
  setupListControls();
  setupNotesModal();
  checkConnection();
  route();
});
