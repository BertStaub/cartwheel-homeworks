# Monitoring

## Questions:
### Did the corrected failure estimate move between the two periods?
*Yes the failure estimate did move betweem the runs.  In fact it crossed the threshold. Before (0.1888) is above 0.15; after (0.0607) is below it. So  it started above threshold and dropped below*
### Do the intervals support a conclusion, or is the result uncertain?
*No, the intervals are low and wide on both, indicating a need for more negaive traces.  Different bottlenecks identified: the judge's held-out test set has only 12 labeled Fail examples (that's the "negative traces" lever), but the monitoring random sample is also only 10 traces/period*
### What did the risk groups reveal that the random estimate did not?
*Random samples can't converge on specific named cases. The , citable point is coverage: the risk group judges all 27 policy_lookup traces exhaustively, so it caught 5 specific failing scenarios (support-0090, -0093, -0096, -0169, -0227) that the random sample never even drew — and support-0090 failed in both periods,*
### What action should happen if the estimate crosses the threshold?
*A threshold crossing should start error analysis on the flagged traces. Confirmed failures should become new evaluation cases in the Homework 6 suite.*