---
name: error-analysis
description: Run agent-assisted error analysis on a trace store. Help a human build a review interface over Langfuse, organize human observations into failure modes, validate one LLM judge per selected subjective mode, use DocETL to apply judges to trace batches, and emit a corrected failure report.
---

# Error Analysis Skill

You are running an interactive error analysis session with a human. The human has a store of agent traces in Langfuse (from the Cartwheel course, but any trace store works) and wants to find out what is actually wrong with their agent and put defensible numbers on it. You help at every step. You do not do the whole thing yourself.

The error analysis skill covers taxonomy discovery and judge validation. It runs inside a coding agent, uses DocETL to apply each judge to trace collections, and computes validation statistics directly in Python. It is a workflow to follow rather than a service to host.

## The one rule that organizes everything

**The human notices and decides. You build, organize, compute, and scale.**

Product quality depends on human judgment and on requirements recorded in the product specification. Reading traces alone cannot determine either source, so you never invent a requirement or a label. Your job is to help the human express a judgment, relate it to the specification, and apply it consistently. Concretely, across both halves of the skill:

- You never open-code a fresh trace on your own account, and you never add a failure mode to the taxonomy from your own reading. You group only the notes the human wrote. If the human's notes do not support a mode, it does not exist.
- You never change a human label. When your judge disagrees with a human label, you surface the disagreement and route it to the human. The human may flip their own earlier label, and every flip is logged. You do not flip it for them.
- Every intermediate persists on disk under `analysis/state/` so the next batch starts from the current state, not from scratch. Persisting the taxonomy, the labels, the judge prompts, and their scores is the whole reason this beats "point an agent at the traces and ask it to evaluate my app."

Keep this rule in view. When you are unsure whether a step is yours or the human's, ask: is this noticing and deciding (theirs), or building, organizing, computing, and scaling (yours)?

## The two halves

This skill runs one discovery loop twice: once to find and name failures, once to measure them.

- **First half (discovery), phases 1 to 5.** Inventory the trace store, design the visual encoding, build a single file review interface over Langfuse, cluster and select a diverse batch, and run the live annotation loop. The supplied server and interface are implementation references, not the student's completed interface. The live session instructions are in [review-loop.md](review-loop.md).
- **Second half (measurement), phases 6 to 11.** From the axial taxonomy, draft one judge prompt per selected subjective mode, collect enough human judgments, split the judgments, refine on development data, freeze the evaluator, test it once, use DocETL to apply it to the defined trace population, and compute corrected prevalence directly in Python.

For Homework 5, use the current handout with the course `write-judge-prompt` and `validate-evaluator` skills. Use the older measurement phases below only as background. Follow the handout for workload, label counts, and metric calculations.

Read this whole file first so you understand the shape before you start. Do the first half using phases 1 to 5 and [review-loop.md](review-loop.md). When the human is ready to measure, do the second half using phases 6 to 11.

## The loop is a cycle, not a pipeline

Do not run these phases as a fixed order once through. The steps interleave and repeat. You read a handful of traces, start grouping before you have read everything, read more, revise the groups, scan one recurring mode across the whole store, discover a new mode late and go back to re-read earlier traces under it, and stop naming when new traces stop teaching you anything. The same holds in the second half: you draft a judge, validate it, inspect disagreements, refine, and repeat, and sometimes a disagreement makes the human change a label instead of the prompt.

Two rhythms name this movement, and both come from the discovery half:

- **Breadth then depth, repeated.** Review broadly until a new mode appears, then scan that one mode in depth across the whole store, then go broad again.
- **Multiple passes over the same data.** A reviewer's criteria drift as they see more traces. Re-reading earlier traces after new modes emerge is standard practice, not rework. It is how coverage catches up with what the human has learned.

## Progress updates

Each phase takes time, especially building the interface. Tell the human what you are doing at each step. Before a phase, say what you are about to do and why. When a step finishes, say what you did and what comes next. For example: "Pulling 10 traces from the Langfuse queue to understand the trace shape", "Building the review app with three views: trace, map, and progress", "Clustering on six trace features to select a diverse batch of 24." Do not go silent for long stretches, and never go silent while background work runs.

## The state directory

Langfuse is the default store for traces and accepted annotations because Module 1 already recorded complete traces there, and Langfuse scores preserve the association between a judgment and its trace. Plain files under `analysis/state/` preserve an inspectable local mirror and workflow state, including taxonomy versions, evaluator versions, splits, cached predictions, and offline demonstration fixtures. The offline path supports development and grading when Langfuse is unavailable; it does not replace the normal Langfuse workflow.

```
analysis/
  skill/
    SKILL.md            this file
    review-loop.md      live-session instructions for phase 5
  server.py             stdlib HTTP server; serves the UI and the file-backed API
  ui/                   the single-file HTML review app
  state/
    samples.json        current normalized traces displayed by the interface
    sample_manifest.json selection method and reason for every sampled trace
    annotations.json    human notes, their in-place text spans, and timestamps
    patterns.json       the taxonomy as you currently hold it
    suggestions.json    depth-scan suggestions awaiting human accept or reject
    graph.json          the 2D projection of all traces for the map view
    labels/<mode>.jsonl one line per (trace_id, label, source, ts) for a mode
    splits.json         per-mode train, dev, and test assignment
    judges/<id>.json    prompt text and hash, model, status, and the iteration log
    demo_annotations.json  canned annotations for the demo replay fallback
  helpers/              thin scripts the skill carries (you call these, you do not write them)
  report/
    failure_report.md   the emitted module deliverable
```

The helper functions live in `analysis/helpers/`, and you call them as documented in each phase below. You do not implement them. `run_judge` constructs and executes the DocETL map operation, while `judge_alignment` and `corrected_prevalence` compute their statistics directly from persisted labels and predictions. Read a helper's docstring before you call it.

---

# First half: discovery (phases 1 to 5)

This is agent-assisted open and axial coding. The human reads traces and notices failures. You do the setup and the bookkeeping around it, and you scale the human's judgment across the whole store.

## Phase 1: Understand the domain and the trace store

Before building anything, read `SPEC.md` and study the traces thoroughly. `SPEC.md` is a reference document rather than an operational input: neither the agent nor the review helpers load the Markdown file as executable policy. The human uses existing requirement identifiers when an observation violates a stated commitment. A newly desired behavior remains a specification gap until the human revises the document.

### 1a: Read and inventory the trace store

The store is in Langfuse. The review interface reads traces and writes binary judgments back as scores against the score configs defined in the project settings. For inventory, pull traces through Langfuse or use the Module 1 JSON export. `select_traces` accepts either source and normalizes the trace records. Examine 5 to 10 traces across the distribution. For each trace, identify:

- The fields that make up the trace: the user messages, the agent's messages, the tool calls and their results, any retrieval spans, and the metadata.
- Which fields are the primary content the human needs to judge (the agent's messages and its tool calls and results).
- Which fields are metadata: context for understanding, but not the thing being judged (`cartwheel.user_role`, `cartwheel.store_id`, `cartwheel.prompt_version`, `cartwheel.scenario_id`, timestamps, token totals).
- Which fields vary across traces and which are constant (the system prompt is often near-constant; mute it, do not delete it).

### 1b: Identify the content structure

Cartwheel traces are multi-turn agent traces: a sequence of messages with different roles (user, assistant, tool call, tool result, and sometimes a retrieval span). For multi-turn traces, identify:

- What roles exist: user, assistant, tool call, tool result, system, and any reasoning blocks.
- Whether there are tool call and tool result pairs. In Cartwheel there always are (order lookup, refunds, search, help-center retrieval).
- What the logical grouping of steps is. One step is usually a tool call plus its result, and a retrieval-plus-answer sequence is a subtree that can be judged on its own.

Read whole traces, not isolated turns. Context from earlier turns changes the meaning of later ones, and errors cascade, so one upstream mistake produces many downstream symptoms. This is why open coding notes the first failure (defined in phase 2 of the review method). One rule survives every data modality: read the underlying data, not the model's paraphrase of it, because a model's summary of a document, an image, a PDF, or an audio transcript is itself a generation that can hallucinate. Cartwheel traces are text and structured tool results, so this is mostly a note here, but if a trace carries other modalities, render the source and not the paraphrase.

### 1c: Identify dimensions of variation

You will use these to design the visual encoding and to cluster for sampling.

Between traces (vary across records):
- Metadata: user role (shopper, merchant, support), store, prompt version, scenario id.
- Structural: turn count, number of tool calls, which tools were used, retrieval present or not, token totals.
- Outcome: whether the linked scenario's expected outcome matched, where one exists.

Within one trace (vary across parts of one record):
- Role of each segment (user, assistant, tool call, tool result, system).
- Content type of each segment (natural language, JSON tool arguments, structured tool results, retrieved policy text).
- Importance of each segment (a repeated system prompt is boilerplate; a tool result can hold the actual bug).

### 1d: Think about what "bad" might mean

Jot a few plausible failure categories for a commerce support agent (an unconfirmed write, a policy claim with no supporting doc, a tool result misreported to the user). Expect the human to discover most of the real ones during review. Do not seed the taxonomy with these. They are only for you to design a sensible interface.

## Phase 2: Design the visual encoding

Before writing any code, design how every dimension of variation maps to a visual property. Use Gestalt principles and information-visualization fundamentals. The point is a review interface a human can read at speed, where the thing that matters jumps out and the boilerplate recedes.

### Core Gestalt principles to apply

- **Similarity (color, shape).** Viewers perceive things that share a visual property as related. Use this for categorical dimensions. Give each message role its own color, and give each failure mode its own badge color.
- **Proximity (spacing).** Viewers perceive things that are close together as grouped. Place the turns in one step close together, and separate steps by more space.
- **Common region (containers, backgrounds).** Viewers perceive things inside a shared boundary as grouped. Put a tool call and its result in a shared container.
- **Figure and ground (opacity, contrast).** Important content should be high-contrast. Less important content should recede. Show boilerplate at low opacity.

### Visual encoding rules

Map each dimension of variation to exactly one visual channel. Do not use the same channel for two different things.

**Color hue.** Use for the most important categorical distinction, which for traces is message role. Give each role (user, assistant, tool call, tool result, system) its own distinct hue at full saturation. Pick hues that are easy to tell apart. Do not use color hue for quantitative data.

**Opacity and saturation.** Use to show whether the human needs to read this content carefully. Reduce opacity only for content the human genuinely does not need to read, such as a system prompt that is identical across every trace, or a verbose tool schema. Ask: if I removed this, would the human miss anything? Do not mute content by role. A tool result or a system message can hold the actual bug. Mute only content that is redundant or mechanical, whatever role produced it. Normal content gets full opacity.

**Spacing.** Use for hierarchical structure. Tight spacing (4 to 8px) between items within one step. Medium spacing (16 to 24px) between steps. Large spacing (32 to 48px) between major sections of a trace.

**Typography.** Use for content type. Prose in a proportional font at normal size. Tool arguments and structured results in a monospace font, slightly smaller. Metadata small, muted, compact. Reasoning blocks in italic or a distinct treatment to signal that they are internal.

**Border and container.** Use for grouping. Put a tool call and its result in a shared container with a subtle border. Give a retrieval span and the answer that uses it a visible boundary so the human can judge the subtree on its own.

**Structural outlier flags.** Show in the header only, never inline. Pre-compute store-level averages for key structural features (turn count, tool-call count, token total). For each trace, flag the dimensions where it is a clear statistical outlier (top or bottom 10%). Show these as small compact badges in the header, such as "8 tool calls (more than 91%)". Keep it minimal. Most traces should carry zero or one flag.

## Phase 3: Build the review interface with the human

The interface is a single file HTML app served by a Python standard library server. Generate or adapt the interface for the observed trace structure, because the appropriate rendering depends on the available messages, retrieval records, tools, and metadata. The skill ships a reference server (`analysis/server.py`) and a reference interface (`analysis/ui/`). Read both implementations, but do not submit the reference interface unchanged.

Before writing code, propose the visual organization and ask the human to approve or revise it. After the interface works, help the human write `analysis/report/interface_comparison.md`. The comparison records one design retained from the reference, one adaptation motivated by the observed traces, and one remaining limitation.

### Why a custom interface and not the Langfuse annotation queue on its own

The Langfuse annotation view is a generic form, while the generated interface provides a layout suited to Cartwheel traces. The generated interface is not a separate database. It writes accepted binary judgments to Langfuse scores and maintains matching local files. The homework begins with a short session in the ordinary Langfuse view so the interface design responds to observed review friction.

### Architecture

- A Python HTTP server using the standard-library `http.server`, no dependencies:
  - `GET /` serves the HTML app.
  - `GET /api/samples` returns the current sample set. `POST /api/samples` lets you push new samples.
  - `GET /api/annotations` returns the current annotations. `POST /api/annotations` lets the app save annotations on every change.
  - `GET /api/graph` returns the 2D projection of all traces for the map view.
  - `GET /api/patterns` returns your current taxonomy. `POST /api/patterns` lets you push the updated taxonomy.
  - `GET /api/suggestions` returns your suggested annotations. `POST /api/suggestions` lets you push suggestions.
- On-disk files under `analysis/state/`: `samples.json`, `annotations.json`, `graph.json`, `patterns.json`, `suggestions.json`, and the `labels/`, `splits.json`, `judges/` used by the second half.
- The HTML app auto-saves to the server on every annotation and polls for new samples and suggestions.

The reference server (`analysis/server.py`) implements exactly this API and reads and writes `analysis/state/`. Run it with `python analysis/server.py`, and for the demo add `--replay state/demo_annotations.json` to replay the canned annotations on a timer, so the watcher, grouping, and suggestion pipeline all fire on stage even if live annotation fails.

### HTML app structure

Four views, toggled from the top bar:

1. **Trace view.** The main review interface where the human reads one trace and annotates it in place.
2. **Map view.** A 2D scatter plot (PCA or UMAP projection) of all traces. It shows clusters, which traces are in the current sample, and which have been annotated. The human can click a sample node to open its trace view.
3. **Progress view.** Two sections: a treemap of the failure modes you have organized so far, each block sized by count and listing its notes, and a queue of your pending suggestions with accept and dismiss controls.
4. **Structured labeling view.** After the taxonomy stabilizes, show one row per reviewed trace and one present or absent control per final mode. Display missing decisions clearly, permit an evidence note, write accepted decisions to Langfuse scores, and maintain one matching JSON Lines file per mode.

Trace view design, applying the encoding from phase 2:

- **Header:** the trace id or permalink, the user role, the store, and the prompt version. Keep it minimal. Add structural outlier flags only when the trace is a genuine outlier. Do not add cluster ids, sampling method, or other pipeline metadata.
- **Body:** render each message or step as a block. Left-align all blocks but give each a colored left border or background tint by role. Put a small bold role label at the top of each block. Show tool-call function names prominently and put the arguments in collapsible formatted JSON. Make long tool results collapsible by default with a summary line visible. Group a tool call with its result in a shared container with tight spacing. Only reduce opacity for content that is literally identical across traces, such as a repeated system prompt.
- **Inline annotation:** the human selects text, a floating popover appears with a text input, they press Enter to save, and the span is highlighted. When the popover appears and the input is focused, the browser clears the native text selection, so wrap the selected range in a temporary highlight span (for example a "pending-highlight" class with a visible background) before focusing the input, and remove it when the annotation is saved, cancelled, or dismissed. This way the human always sees what text they are annotating.
- **Margin notes:** annotations and suggestions appear as side notes in a right margin column, aligned vertically with their highlighted text. Use a two-column layout: the trace body on the left (flex: 1, max-width about 720px) and a margin-notes column on the right (about 240px). Each margin note is position: absolute inside the margin column, its top offset computed from the highlight's position relative to the margin container (use getBoundingClientRect on both and take the difference, and do not add scrollTop, which double-counts the scroll offset). Stack notes with a minimum gap so they do not overlap. Add hover linking: hovering a margin note outlines its highlight, and hovering a highlight outlines its margin note. Each margin note shows the quoted text, the human's note, and edit and delete buttons on hover. Do not use hover tooltips as the primary way to show annotation content. Margin notes replace tooltips.
- **Agent suggestions:** visually distinct from human annotations in both the inline highlight (dashed border, muted tint) and the margin note (a different left-border color and an "agent suggestion" tag). The margin note shows accept and dismiss buttons that are always visible, not hover-gated. Accepting promotes the suggestion to a human-confirmed annotation and writes a label with source `accepted_suggestion`. Dismissing removes it.
- During open coding, do not place predefined quality labels, dropdowns, or structured forms in the trace view. Use free text notes until the taxonomy stabilizes. The separate structured labeling view applies the final binary modes to every reviewed trace. Do not add a 1-to-5 score, because the scale has no defined interpretation in the assignment.
- Auto-save to the server on every change and keep a localStorage backup. Poll for new samples and suggestions periodically and show a banner or toast when new ones arrive.

Map view: a 2D scatter of all traces from the PCA or UMAP projection, colored by cluster (not by label), with sample traces as larger nodes with a dark border and annotated traces in a distinct color such as orange. Draw subtle cluster hulls. On hover, show a tooltip with the trace id, its metadata, and its annotation count. On click of a sample node, open its trace view.

## Phase 4: Cluster and select a diverse batch

Reading traces in logged order surfaces only the most common patterns, so cluster the store and return a diverse batch. Use the `select_traces` helper:

- `select_traces(source, k, strategy, exclude_ids)` accepts the literal `langfuse` or a Module 1 JSON export path. `strategy` defaults to `diversity`, which combines cluster representatives with random traces because clustering never captures every relevant dimension. The helper returns normalized traces with a selection reason, writes the interface records to `state/samples.json`, and writes the selection details to `state/sample_manifest.json`.

The Cartwheel demo default is 24 traces: 16 cluster representatives (2 per cluster over 8 clusters on the features turn count, tool-call count, tools used, retrieval presence, role, and token totals) plus 8 random picks. This is the pinned `select_traces` default for the demo.

Use `select_traces` again in phase 4 of the measurement half and whenever the current batch is exhausted and the human calls for more. The caution that runs through the whole method: a cluster or an outlier is a prompt to read traces, never a failure mode by itself.

The full trace-selection toolkit lives in the reader (cluster and read representatives, plot a metric's distribution and read each mode of a bimodal shape, cross-tabulate metadata against outcomes, filter to a slice and read twenty back to back, flag outliers by the interquartile-range rule, and semantic-search from one confirmed bad example). `select_traces` covers the diversity and random strategies. Reach for the others by hand when a specific question calls for them.

## Phase 5: Run the interactive review loop

Once the app is running and the human starts reviewing, follow [review-loop.md](review-loop.md) for the live session. The human reads until the first failure, writes a short free form note without using predefined categories, and then stops the initial review of the trace. Poll the annotation file while the review session is active, propose groupings from human notes, and search the store for possible instances of confirmed modes. Propose a new sample after the human finishes a batch.

The boundaries in the live loop, restated because they are where the method lives:

- You do not open-code. Open coding requires taste about what counts as a failure for this product, which is exactly the thing that lives in the human's head and not in the traces.
- Axial grouping organizes notes the human already wrote, so you may propose groupings, names, and draft definitions. The human renames, merges, splits, or rejects them and owns the taxonomy. You never add a mode from your own reading.
- The test for a merge or a split is always "does fixing one fix the other?" If two notes have the same fix, they are one mode. If they have different fixes, they are two.
- Suggestions favor recall. A false suggestion costs one click to dismiss, and a missed instance costs coverage, so over-suggest and let the human prune. You are not exhaustive, so the human still reads.
- Stop naming at theoretical saturation, when new traces stop producing new modes and mostly confirm known ones. Report the discovery-rate curve so the human can see it. Counting continues on new data forever; naming stops when names stop appearing.

The output of the first half is a failure taxonomy in `state/patterns.json`: 5 to 8 binary failure modes, each with a snake_case name, a one-sentence definition a stranger could apply, at least 3 confirmed example traces, and a `created_from` list of the human annotation ids the mode came from. Every mode must trace to a human annotation. A mode with no originating human annotation is not a valid mode.

---

# Second half: measurement (phases 6 to 11)

Now choose three subjective failure modes, develop one LLM judge for each mode, and determine whether held out agreement supports a stated use. The same rule holds: you build, organize, compute, and scale; the human decides. Judge development resembles classifier development where prompt editing shapes the decision rule, so split the data, score on held out judgments, and do not touch the test set until the prompt is frozen.

## Phase 6: Choose the evaluator per mode, and code first

For each mode in the taxonomy, the human picks a code-based check or an LLM judge. The axis is whether the check is objective. Propose the split; the human decides.

- **Code check** when the definition is objective: there is a reference answer to compare against or a rule to apply. Cartwheel examples include permission assertions, refund state transitions, schema checks on tool arguments, and requirements for policy identifiers. Code checks are fast, deterministic, and free at any scale. They need no alignment study when they compare directly against authoritative state.
- **LLM judge** when the check needs interpretation: whether a policy claim is actually supported by the cited doc, or whether the tone suited the situation. This is the rest of this half.

One evaluator per failure mode, binary output (pass or fail). A compound "quality score" hides which failure moved and cannot be validated against anything.

Before building any evaluator, fix specification failures. A failure the prompt never specified against (for example an unconfirmed write when the system prompt never said to confirm before irreversible writes) is a specification gap, and the fix is a prompt edit, not an evaluator. Evaluators are for generalization failures, where the instruction was clear and the model still failed. A fixed specification failure should show up as a prevalence drop between prompt versions.

## Phase 7: Draft the judge prompt

For each subjective mode, draft a judge prompt from the mode's definition and its training examples. The prompt has four required components:

1. A single, narrowly scoped task (one mode, one binary question).
2. Precise definitions of pass and fail, written from the axial-coding definition.
3. Few-shot examples of both classes, drawn from the training split only.
4. A structured output format with `critique` followed by a `result` of `Pass` or `Fail`.

Decide what the judge receives. This is a design choice, not "give it the whole trace." For a groundedness mode like `unsupported_policy_claim`, give the judge the agent's final message plus the policy docs it cited, not the whole trace, because the question is "is the claim supported by the cited docs" and extra context invites the judge to excuse the claim from its own world knowledge. Tell the judge to use only the provided documents, not its own knowledge.

You draft the prompt. The human edits it. Register each version with `register_judge(mode, prompt_text, judge_model)`, which returns a judge id and a prompt hash and appends to the version history, so the iteration history is inspectable. Every edit is a new version.

**Label convention, stated once and used everywhere.** Pass is the positive class, and Fail is the negative class. TPR is the fraction of human Pass labels that the judge calls Pass, while TNR is the fraction of human Fail labels that the judge calls Fail. Mode files store failure indicators for convenient counting, so the helpers convert stored values before computing the statistics. `corrected_prevalence` corrects the Pass rate and subtracts it from one before reporting failure prevalence.

The default judge model for the demo is a different family from the agent under evaluation (for Cartwheel, `claude-opus-4-6` judging a `gpt-5.5` agent), which reduces self-enhancement bias. Say this out loud once.

## Phase 8: Collect enough human judgments, then split

A judge is validated against held out human judgments, so each selected mode needs enough Pass and Fail examples. Homework 4 already provides at least 100 decisions per mode because the human applies every final mode to every reviewed trace. Failures may be rare, so additional retrieval is often necessary.

- Retrieve additional cases with `next_to_label(mode, k, strategy)`. Strategies include semantic neighbors of confirmed failures, disagreement cases, and random traces. The helper returns candidate identifiers with the signal responsible for selection. The human judges every candidate. For Homework 5, reuse your Homework 4 decisions. Collect at least 30 Pass and 30 Fail labels from independent conversations. Use your coding agent to search for candidates or generate targeted scenarios. Review the resulting traces yourself. If you cannot find enough cases, follow the handout's Stop early instructions.
- Split with `split_labels(mode, fractions, seed, min_per_class)`. The helper retains default fractions of 0.15 train, 0.425 development, and 0.425 test for compatibility. Homework 5 explicitly passes 0.20, 0.40, and 0.40. Its eligible identifier list excludes related, incomplete, and out of scope records without deleting label history. The course default requires at least 10 examples of each class in development and test, which provides preliminary educational evidence rather than a production guarantee. The helper persists the assignment to `state/splits.json` and refuses a class count too small for the requested minimum. Any trace appearing in the prompt is excluded from development and test.

The class counts control how precisely TPR and TNR can be measured. Small counts produce wide intervals, and no single minimum establishes reliability. Do not extend Homework 5 collection indefinitely to meet a larger sample target.

## Phase 9: The judge-building loop is iterative

Building a judge is not draft-then-done. It is a cycle: draft, validate against dev, inspect the disagreements, refine, and repeat. This is the same iterative movement as open and axial coding.

- Run the judge on development data with `run_judge(judge_id, split)`. The helper executes a DocETL map operation and returns per-trace binary predictions cached by prompt hash and trace identifier.
- Score alignment with `judge_alignment(judge_id, split)`, which returns TPR, TNR, overall agreement, the confusion counts, and the disagreement trace ids, and auto-appends a row to the iteration log when run on dev. Read TPR and TNR, never overall agreement alone (phase notes below on why).
- Read every disagreement with the human labels. Propose a prompt edit from the disagreement patterns: clarify a definition, or swap or add a few-shot example. The human decides each edit. Register the edit as a new version with `register_judge`, rerun, and score again.
- Disagreement review cuts both ways. Sometimes the judge is wrong. Sometimes re-reading changes the human's mind and the human flips their own label. You never flip a label yourself. Label flips are logged, and the numbers are recomputed when they happen. Inspect the running table any time with `iteration_log(judge_id)`, which shows version, change note, dev TPR, dev TNR, and label flips.
- For Homework 5, run a baseline and at most two revisions. Compute TPR, TNR, and confidence intervals. Use the rates, uncertainty, and disagreements to explain whether you would use the judge. Do not require numerical acceptance targets.

**Why overall agreement is inadequate.** When failures are rare, overall agreement is dominated by the majority class. If a mode appears in 7 of 100 traces, a judge returning Pass for every trace has 93 percent agreement and a TNR of zero. Report TPR for Pass and TNR for Fail as a pair.

**If refinement stalls**, try these in order of cheapness: a stronger judge model, splitting the criterion into two narrower judges, or improving the labeled data. Automated prompt optimizers exist and are deferred to Module 5. Doing this loop by hand at least once builds the intuition the optimizer then automates.

## Phase 10: Freeze, then test once

Before the first prompt run, save the judge inputs in a local export and set `CARTWHEEL_JUDGE_TRACE_SOURCE` to that file. Keep the export unchanged when resuming. When you finish development, call `freeze_judge(judge_id)` once. Keep the prompt, model, test identifiers, and human labels unchanged during the final evaluation.

Run the test set with `run_judge(judge_id, "test")` and `judge_alignment(judge_id, "test")`, and report the final test rates. An interrupted run may resume with the same judge id, model, prompt, input export, labels, and split. Completed batches are saved; only missing predictions run again. An interrupted unsaved batch may incur repeat calls. Do not register, split, or freeze again to resume. Recomputing metrics from saved predictions is allowed. The demonstration reaches 0.95 Pass TPR and 0.91 Fail TNR on development, followed by 0.95 Pass TPR and 0.83 Fail TNR on test. The lower test TNR shows why the correction must use the held out result.

## Phase 11: Correct to true prevalence, set the accuracy bar, and report

The frozen judge's raw Pass rate is biased, because the judge can fail acceptable traces or pass traces containing the named failure. Correct the estimate only when held out evidence supports using the judge.

- Run the frozen judge over a representative trace sample with `run_judge(judge_id, trace_ids)`. The helper applies the frozen prompt and recorded model through a DocETL map operation. Use the full store only when it is the population whose prevalence you intend to estimate.
- Compute corrected prevalence with `corrected_prevalence(judge_id, trace_filter, confidence)`. The helper computes the Rogan--Gladen estimate from the judge's held-out TPR and TNR, then obtains a percentile-bootstrap interval by resampling both the held-out records and the unlabeled predictions. It warns when TPR plus TNR is close to 1 because the correction is then unstable.

For example, suppose the judge flags 0.180 of the store, so its observed Pass rate is 0.820. With Pass TPR 0.947 and Fail TNR 0.833, the corrected Pass rate is $(0.820 + 0.833 - 1)/(0.947 + 0.833 - 1)=0.837$. The corrected failure prevalence is therefore $1-0.837=0.163$. A small held out set still produces a wide interval even when DocETL evaluates many unlabeled traces.

**Set the required accuracy from the consequence of each failure.** A permission violation and an awkward explanation do not require the same evidence or evaluator. Use deterministic checks for properties defined by authoritative state. Reserve judge validation for properties requiring interpretation.

**Emit the report** with `failure_report(output_path)`, which writes `analysis/report/failure_report.md` and matching JSON. For each selected mode, the report contains the definition, requirement source, confirmed examples, judge version, held out TPR and TNR, use or reject decision, and corrected prevalence when the judge is trusted. The report also preserves several confirmed traces as Module 3 evaluation case set candidates.

The report is the handoff to Module 3. Its modes become regression dimensions, and its confirmed examples provide candidates for curated evaluation sets. Production monitoring and deployment checks are outside the Module 2 deliverable.

## Batch execution with DocETL

Use the same DocETL map operation for development, held-out test, and subsequent unlabeled batches. The operation receives only the trace fields required by the failure-mode definition, and its output schema contains the critique and Pass/Fail verdict. DocETL parallelizes the model calls and caches repeated work. The skill additionally records predictions by prompt hash and trace identifier, so editing a prompt creates a new evaluator version without obscuring earlier results.

Do not substitute a cheaper model only for the unlabeled batch. A model change creates a different judge with different error rates, so it requires its own development and held-out validation. Cost and accuracy optimization across several evaluator models belongs in the later optimization workflow.

## Guardrails, and why they teach the method

These are enforced in the helpers, and they teach the method by refusing to break it. Do not try to work around them. If one blocks you, it is telling you a step is out of order.

- `judge_alignment` on `test` raises unless the judge is frozen.
- `freeze_judge` is one-way per version. Fixing a frozen judge means a new version, which re-locks the test set.
- `split_labels` refuses thin classes instead of silently producing unstable estimates.
- Label edits append rather than overwrite (a flip sets `superseded_by` on the old line and adds a new one), so the flip history in `iteration_log` is complete and nothing is lost.
