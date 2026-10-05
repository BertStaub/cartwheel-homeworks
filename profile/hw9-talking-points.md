# Homework 9 video talking points (5 minutes)

Every number below comes from a saved file in this repository. Items marked **YOUR CALL** are decisions or reasons that only you can state.

## 1. Where cost comes from (about 40 s)
Show `profile/results/costs.csv` (built by `profile/scripts/build_costs.py`).
- Most expensive customer-conversation call site: the agent's model call, 789 calls, **$6.38** (Langfuse export, `claude-opus-4-6`).
- Most expensive judge call site: `unsupported_policy_claim` v3 validation, 600 verdicts, **$3.62**. Judge token counts are **estimates** (characters / 4, output assumed 100 tokens per call). The cost is dominated by call count and the Opus price, not by anything the table shows about the judge's reasoning.
- Why the two are separate: conversation cost grows with users; judge cost grows with how often you evaluate.

## 2. Part B, fewer tokens (about 70 s)
- Change: `search_help_center` returns 2 results instead of 3 (`agent/agent.py`, commit `93797ad`).
- Why this change: it is about 60% of tool-result characters. In the export, the policy the agent fetched next ranked 1st in 59% of searches, 2nd in 30%, 3rd in 9%, and absent in 1%. So top 2 carries about a 10% risk.
- Numbers, HW8 final vs fewer-tokens: score 0.9 vs 0.7, input tokens 193,756 vs 154,498, output tokens 20,435 vs 11,687, cost per 100 conversations $2.22 vs $1.60, median latency 14.6 s vs 10.9 s. `write_pass_5` is empty because the development cases contain no expected-write case.
- Decision: kept. **YOUR CALL**: state your reason. Your stated reasoning was that the score swings between 0.7 and 0.9 across runs of the same configuration, and cost and latency are worth a possible small loss. Say plainly that this departs from the handout rule (keep only if the score does not drop).
- Open question, not a conclusion: e-012 hit `MaxTurnsExceeded` only in this run (earlier e-012 failures were judge failures). Fewer results may have led to more searching. One run cannot tell.

## 3. Part C, caching (about 70 s)
- Model: `gpt-5.5`, direct OpenAI key (the gateway route made no tool calls in a one-request test).
- Change: `## Session context` moved to the end of the system prompt (commit `54a1c19`), wording unchanged.
- Four runs of the same 10 cases:

| Run | Cached fraction | Input tokens | Cost per 100 | Mean latency |
|---|---|---|---|---|
| before | 0.394 | 70,109 | $5.07 | 22.3 s |
| after | 0.477 | 85,934 | $5.42 | 18.4 s |
| rerun1 | 0.442 | 90,382 | $5.65 | 17.8 s |
| rerun2 | 0.348 | 70,570 | $5.30 | 16.1 s |

- Explanation: most of the cached tokens come from reuse within one conversation (the prefix repeats on each model call). The reorder lets different conversations share tools plus rules, which my estimate put at about 1,600 tokens against the 1,024 minimum. The cached fraction and cost both follow total input tokens, not the reorder. The effect is inside the run-to-run spread.
- Decision: kept, because the score did not drop. **YOUR CALL**: how much you trust it (you said you do not).

## 4. Part D, cascade (about 70 s)
- Oracle: `unsupported_policy_claim` v3 (`claude-opus-4-6`). Proxy: `gemini-3.8-flash`. Examples: 66 judged HW7 monitor traces (33 development, 33 test, split by scenario). There are **no human labels**, so agreement is with the oracle only. The cascade is not ready for CI or monitoring.
- Minimum agreement you set before seeing results: 0.9.
- Development: proxy confidence was almost always 1.0 (29 of 33). Agreement 0.939 with no threshold, 0.970 at threshold 1.0. The proxy missed 2 of 5 oracle failures, and one of those misses had confidence 1.0.
- `gemini-3.1-flash-lite` was rejected on development: agreement 0.818 at every threshold, 4 of 33 outputs unparseable. No threshold met 0.9. It cost about $0.00046 per verdict against $0.0042 for 3.8-flash, because it produced far fewer output tokens.
- Locked before the test run (`cascade/results/locked.json`): `gemini-3.8-flash`, threshold 1.0. Test: agreement **1.000**, **0 disagreements of 33**, proxy handled 29 (0.879), cost about $4.54 per 1,000 verdicts. The oracle's cost per verdict ($0.006) is an **estimate**, so the saving is soft.
- Decision: rejected. **YOUR CALL**: the reason you gave was that 4 oracle failures in the test split is too few to give a usable signal. State that the agreement met your requirement, so this is a sample-size judgment and not a failed threshold.

## 5. Part E, frontier (about 50 s)
Show `profile/results/frontier.csv`.
- Frontier: **hw8-final** (0.9, $2.22) and **fewer-tokens** (0.7, $1.60). The four `gpt-5.5` rows are dominated by hw8-final: the same 0.9 score at less than half the cost.
- Configuration you would use: **hw8-final** (your choice). **YOUR CALL**: your reason. Be ready for one tension: you kept the fewer-tokens change in Part B but chose hw8-final here, which does not include it. Say why (for example, the score gap, or that 10 runs cannot show the gap is noise).
- Caveat: 10 case runs per row, and identical runs of this configuration have scored 0.7 and 0.9.

## 6. Recalculate one number (about 20 s)
From `optimize/results/development-final-gemini_gemini-3.8-flash-20261001-184500.json`:
`(193,756 x $0.75 + 20,435 x $3.75) / 1,000,000 = $0.2219` for 10 runs, so **$2.2195 per 100 conversations**. This matches `cost_per_100_conversations_usd` in the file and the frontier row.
