# Round 1 discussion notes

## Inspect-only failure

- Trial: `task-007-learn-step-00`
- Arm: Learn
- Phase: transfer
- Result: unscored failure

The Learn agent used one proposal to inspect the data and runtime instead of submitting predictions. The inspection completed successfully: the training and public Dev data were present, the runtime matched, isolation checks passed, no hidden labels leaked, and the E2B sandbox was cleaned up. The proposal did not produce the required `execution.json` or predictions, so the independent scorer could not score it.

This is not an infrastructure failure. It is evidence about the Learn policy: after seeing earlier failures, its memory became cautious enough to choose diagnosis instead of a scored research attempt. We preserve the outcome and do not retry it, because a retry would give the Learn arm an extra attempt after observing the result.

### Discuss after Round 1

- Should `inspect` use a separate diagnostic budget instead of consuming a scored proposal?
- Should every scored proposal be required to end with predictions, even if it begins with inspection?
- How do we keep failure memory useful without making the Learn agent overly cautious?
- Any revised rule must be frozen before the next round and applied equally to all arms.

### Evidence

- Formal review: `artifacts/polymarket-rsi-round1-20260907-07/study/failure-reviews/task-007-learn-step-00-review-01/review.json`
- Sandbox collection: `artifacts/polymarket-rsi-round1-20260907-07/runner/jobs/task-007-learn-step-00/task-007-learn-step-00-sandbox/collection.json`
- Isolation receipt: `artifacts/polymarket-rsi-round1-20260907-07/runner/jobs/task-007-learn-step-00/task-007-learn-step-00-sandbox/collected/isolation.json`
- Cleanup receipt: `artifacts/polymarket-rsi-round1-20260907-07/runner/jobs/task-007-learn-step-00/task-007-learn-step-00-sandbox/cleanup-01.json`
