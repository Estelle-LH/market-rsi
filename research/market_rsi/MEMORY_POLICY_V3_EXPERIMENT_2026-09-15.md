# Controller memory study v3: repaired rerun

## What this run asks

The question is unchanged: when the controller receives no prior memory, its full
raw archive, or a compact evidence archive, which representation leads to lower
out-of-sample prediction error after eight rounds?

Only controller memory differs across the three arms. The target, rows, feature
and trainer library, controller model, Codex harness, random seed and evaluation
metric remain identical.

## Why v2 cannot resume

`memory-policy-v2-20260915-01` completed two rolling Dev rounds. In Round 3, the
fresh arm selected a nine-feature ridge model. The candidate fit succeeded on
4,426,632 rows with peak RSS 1,991,664 KiB, but the mandatory refit on 6,105,040
rows was killed after crossing the fixed 2 GiB cap at 2,317,184 KiB.

This was a harness resource mismatch: the controller was allowed to select a
plan that the final refit could not execute on the larger cumulative Train set.
It was not a valid low-score outcome. Because two Dev results were already
opened, v2 is preserved and invalidated rather than resumed. Its checkpoints,
controller archives and Dev scores are not imported into v3.

## Repair

- Candidate fits: 6 GiB RSS, 480 seconds.
- Mandatory refits and common baselines: 8 GiB RSS, 600 seconds.
- Maximum fit rows remains 12,000,000.
- Cumulative score-free semantic observations across initial Train and all eight
  rolling Dev sessions must be no more than 10,000,000.
- No silent row subsampling, no plan modification and identical limits for all
  three arms.
- After each derived cache is transferred to the Mac and its exact hash and size
  are verified, the runner removes only that run/session directory from Linode.
  Raw data is never deleted. This prevents the 97%-full remote disk from becoming
  a later-run failure source.

The old 2 GiB failure is the negative canary. The exact failed request must pass
unchanged under the new refit envelope before a paid run may start. Its resulting
diagnostic checkpoint is never reused.

## Fresh evidence

The initial Train sources remain Train. The two v2 Dev sessions are permanently
excluded from v3. New Dev and Final sessions are selected only from prior
score-free semantic receipts. Three sources moved from the old Final candidate
pool to Dev and received new score-free role-specific semantic preflights.

Selection uses only time, source integrity, compressed size, selected-observation
count and prior exposure. It does not use targets, fits, controller output or
scores. The exact rule and rows are frozen in
`MEMORY_POLICY_V3_SOURCE_SELECTION_2026-09-15.json`.

## Hypotheses

Primary hypothesis: compact memory lowers equal-session Final MSE relative to
fresh memory because it preserves measured decisions without replaying all raw
tool text.

Alternative hypothesis: the full archive is better because details removed by
the compact representation matter for the next research decision.

Null/negative result: neither memory arm reliably improves over fresh on the
twenty untouched Final sessions. This remains a valid outcome.

Mechanical hypothesis for the repair: an unchanged 6,105,040-row refit that
failed only at the old 2 GiB limit completes below the new 8 GiB limit without
subsampling and without opening scores.

Infrastructure hypothesis: the exact per-session derived-cache cleanup removes
only its two-component path after verified transfer, is idempotent, and leaves
the raw source tree untouched.

## Retry, rerun and skip rules

A failure may be rerun only after its cause is identified, repaired and covered
by a negative and positive canary. If no score, target statistic or uncertain
provider side effect was written, use a fresh run ID; resume the same run only
from an exact idempotent checkpoint.

Do not rerun valid low scores, no improvement, valid model failures or valid
timeouts. They are results. Do not replace a source after the manifest is frozen.
Before freeze, a source that fails the preregistered semantic gate may be skipped
according to the frozen candidate order. After any Dev or Final result is opened,
an infrastructure repair requires a new experiment with new unopened evidence.

## Acceptance

- Eight complete paired rounds; no performance early stopping.
- One frozen Round 8 model per arm before Final opens.
- At least twenty untouched Final sessions across at least four UTC dates.
- Equal-session MSE and paired per-session differences for fresh, archive,
  compact and the common baseline.
- Actual metered provider cost reported separately from reservations.
- Complete process cleanup and unchanged published source hashes.
- No profitability or general RSI claim from this study alone.
