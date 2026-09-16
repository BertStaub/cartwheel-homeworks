# Cartwheel course repository

Cartwheel is the support agent used throughout "Evaluating and Improving AI Agents." Students complete the starter code and use the same repository for later evaluation exercises.

## Commands

See README.md for setup and the full command list. To run a single test:
`uv run pytest path/to/test_file.py -k test_name`. Homework-hole tests use
`--runxfail` so an unfinished function fails loudly instead of silently
xfailing (see each handout for its exact `-k` filter).

## Architecture at a glance

One request crosses five files before it reaches Langfuse: `server/app.py`
authenticates the bearer token and opens the `cartwheel.session_message` root
span; `agent/agent.py` builds the `Agent` for that role (system prompt +
`TOOLS_BY_ROLE`); a tool call is dispatched to `agent/tools.py` (or a lecture
tool in `agent/agent.py`), gated by the access matrix in `agent/auth.py`
before it touches `agent/db.py`; `observability/instrument.py` then stamps
`cartwheel.*` attributes onto the tool span OpenLLMetry already opened.
Authorization lives in this code path, never in the prompt.

## Find the relevant instructions

- Read [README.md](README.md) for setup and commands. Run commands from the repository root.
- For homework help, identify the assignment from the request and existing work. If it is unclear, ask which assignment the student is working on. The [homework index](homework/README.md) lists released assignments.
- For HW1, HW2, or HW3, read the relevant handout in `homework/module-1/` and follow its requirements and deliverables. When the student invokes a handout's interactive walkthrough, follow its pacing and review points. For HW3, also read and follow `scenarios/skill/SKILL.md`; keep query generation separate from application execution and stop for the required human reviews.
- For repository maintenance, follow the requested change directly. Preserve unfinished homework functions unless implementing them is part of the request.
- For HW4, read the handout in `homework/module-2/` and the [error-discovery](https://github.com/ai-evals-course/evals-skills/blob/main/skills/error-discovery/SKILL.md) skill on GitHub. For HW5, use the current handout with [write-judge-prompt](https://github.com/ai-evals-course/evals-skills/blob/main/skills/write-judge-prompt/SKILL.md) and [validate-evaluator](https://github.com/ai-evals-course/evals-skills/blob/main/skills/validate-evaluator/SKILL.md). HW5 requires one judge; additional judges and prevalence estimation are optional. Follow its label minimums, metric calculations, and interrupted-test instructions. Do not require numerical acceptance targets. Preserve the student's human labels and final decisions.

## Shared rules

- Read [SPEC.md](SPEC.md) and the relevant function contracts before changing agent behavior. Policy numbers come from `facts.yaml`. Editing the specification alone does not change the running application.
- Reuse the supplied database and authorization helpers and return structured tool results.
- Preserve permission checks, refund thresholds, human approval, and kill-switch protections. Keep evaluation cases as regression tests and keep evaluation inputs out of prompts.
- Preserve existing student work and settings. Before regenerating data, check whether it would erase work the student wants to keep. Generate demo data through the seed tools and preserve the pinned demo orders. Confine adversarial fixtures to temporary database copies and keep their generated data out of commits.
- Handle API keys locally through `.env`. Never request keys in chat, print their values, or commit them. Refer to credentials by environment variable name.
- Homework placeholders intentionally raise `NotImplementedError`. Expected failures are unfinished work, not proof of completion. Follow the handout's focused tests and run relevant regression checks; resolve mismatches without weakening requirements or tests merely to pass.
- Report which checks ran offline and which used a live model, and record only observed conversations and tool results. When helping with a submission, leave the student's assessments and recording to the student, and keep unverified deliverables marked as pending.

The repository root `AGENTS.md` is the canonical instruction file. The root `CLAUDE.md` is a relative symlink to it; edit the target rather than maintaining a second copy.
