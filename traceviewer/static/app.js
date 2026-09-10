"use strict";

/* Cartwheel Trace Viewer — read-only frontend. No annotation state, no
 * local storage of trace data; everything is re-fetched from the backend
 * (which itself re-fetches from Langfuse) on every navigation. */

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
    const tools = (t.tool_names || [])
      .map((n) => `<span class="pill">${esc(n)}</span>`)
      .join("");
    const checked = state.diffSelection.includes(t.trace_id) ? "checked" : "";
    tr.innerHTML = `
      <td class="select-col"><input type="checkbox" class="diff-checkbox" ${checked}></td>
      <td>${statusBadge}</td>
      <td class="nowrap">${fmtTimeShort(t.timestamp)}</td>
      <td>${fmtVal(t.user_role)}</td>
      <td class="mono">${fmtVal(t.user_id)}</td>
      <td class="mono">${fmtVal(t.prompt_version)}</td>
      <td class="preview"><div class="preview-clamp">${t.input_preview ? esc(t.input_preview) : missingSpan()}</div></td>
      <td class="preview"><div class="preview-clamp">${t.output_preview ? esc(t.output_preview) : missingSpan()}</div></td>
      <td>${tools || missingSpan()}</td>
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

function renderToolCall(tc) {
  const tpl = document.getElementById("tpl-tool-call");
  const node = tpl.content.cloneNode(true);
  const card = node.querySelector(".tool-card");

  card.querySelector(".tool-badge").innerHTML = okBadge(tc.ok);
  card.querySelector(".tool-name").textContent = tc.name || "(missing name)";
  card.querySelector(".tool-latency").textContent =
    tc.latency !== null && tc.latency !== undefined ? `${(tc.latency * 1000).toFixed(0)} ms` : "";
  card.querySelector(".tool-id").textContent = tc.observation_id || "";

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

function renderGenerationCard(gen) {
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

function renderTurn(turn) {
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
    wrap.appendChild(renderGenerationCard(turn.generation));
  }
  for (const tc of turn.tool_calls) {
    wrap.appendChild(renderToolCall(tc));
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
    renderDetail(data);
  } catch (e) {
    container.innerHTML = `<p class="status-line error">failed to load trace: ${esc(e.message)}</p>`;
  }
}

function renderDetail(data) {
  const c = data.conversation;
  const container = document.getElementById("detail-content");
  container.innerHTML = "";

  // Header ---------------------------------------------------------------
  const header = document.createElement("div");
  header.className = "detail-header";
  const statusBadge = data.has_error
    ? '<span class="badge error">⚠ issue found</span>'
    : '<span class="badge ok">clean</span>';
  header.innerHTML = `
    <h2>${esc(data.trace_id)} ${statusBadge}</h2>
    <div class="detail-attrs">
      <div class="attr"><span class="field-label">Role</span>${fmtVal(c.user_role)}</div>
      <div class="attr"><span class="field-label">User ID</span>${fmtVal(c.user_id)}</div>
      <div class="attr"><span class="field-label">Store ID</span>${fmtVal(c.store_id)}</div>
      <div class="attr"><span class="field-label">Prompt version</span>${fmtVal(c.prompt_version)}</div>
      <div class="attr"><span class="field-label">Scenario ID</span>${fmtVal(c.scenario_id)}</div>
      <div class="attr"><span class="field-label">Langfuse</span><a class="permalink" href="${esc(data.permalink)}" target="_blank" rel="noopener">open in Langfuse ↗</a></div>
    </div>
  `;
  container.appendChild(header);

  // Conversation -----------------------------------------------------------
  const convo = document.createElement("section");
  convo.className = "block";
  convo.innerHTML = "<h3>Conversation</h3>";

  const userCard = document.createElement("div");
  userCard.className = "message-card user";
  userCard.innerHTML = `<span class="role-label">User</span><div class="content">${
    c.user_message ? esc(c.user_message) : missingSpan()
  }</div>`;
  convo.appendChild(userCard);

  if (c.turns.length === 0) {
    const none = document.createElement("p");
    none.className = "missing";
    none.textContent = "no model or tool spans recorded for this trace";
    convo.appendChild(none);
  } else {
    for (const turn of c.turns) {
      convo.appendChild(renderTurn(turn));
    }
  }

  const assistantCard = document.createElement("div");
  assistantCard.className = "message-card assistant";
  assistantCard.innerHTML = `<span class="role-label">Assistant</span><div class="content">${
    c.assistant_reply ? esc(c.assistant_reply) : missingSpan()
  }</div>`;
  convo.appendChild(assistantCard);

  container.appendChild(convo);

  // Timeline / all spans -----------------------------------------------
  const timelineSection = document.createElement("section");
  timelineSection.className = "block";
  timelineSection.innerHTML = `
    <h3>Timeline (every span in this trace)</h3>
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
  const tbody = timelineSection.querySelector("tbody");
  for (const o of data.timeline) {
    tbody.appendChild(renderTimelineRow(o));
  }
  container.appendChild(timelineSection);

  // Raw observation view --------------------------------------------------
  const rawSection = document.createElement("section");
  rawSection.className = "block";
  rawSection.innerHTML = `
    <details class="raw-block">
      <summary>Raw observation view (unmodified Langfuse API response)</summary>
      <div class="field-block"><span class="field-label">Trace</span>${fmtJSON(data.raw.trace)}</div>
      <div class="field-block"><span class="field-label">Observations (${data.raw.observations.length})</span>${fmtJSON(data.raw.observations)}</div>
    </details>
  `;
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
  checkConnection();
  route();
});
