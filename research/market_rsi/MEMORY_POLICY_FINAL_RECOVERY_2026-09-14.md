# Memory-policy Final recovery

## One problem being fixed

The eight controller rounds and all Round 8 models finished and were frozen, but
the first Final materialization stopped before any score was produced. The old
materializer allowed at most 4,000,000 selected quote observations. It stopped
after 2,009,539 raw records, at the point where roughly two quote changes per
record can reach that limit. The source file itself had already passed the full
compressed/decoded hash and JSON preflight.

The earlier statement that the decoder's 256 MiB limit caused the failure was
too broad. The decoder was terminated during cleanup after the parent-side
consumer raised `ValueError`. The 4,000,000-observation guard is the concrete
code boundary that matches the stopping point. The old worker discarded the
specific consumer error, so the recovery worker also records a bounded,
non-row-bearing failure category and the last ordinal.

## What changes

Only the raw-data materialization resource envelope changes:

- selected-observation limit: 4,000,000 to 12,000,000;
- per-entity limit remains 200,000 because the unchanged sampling kernel has the
  same reviewed bound;
- entity limit: 5,000 to 10,000;
- parent address-space limit: 768 MiB to 4 GiB;
- decoded-byte limit: 3 GiB to 4 GiB;
- wall limit is raised for the largest already-frozen hourly files.

The Linode has about 8 GiB total memory and showed about 7 GiB available before
this change. Only one materializer can run at a time. The decoder remains at a
separate 256 MiB address-space limit. Exceeding any new bound still fails closed.

Nothing scientific changes: no controller is called, no model is trained or
selected again, and the target, features, Train rows, Round 8 model files,
ordered 20-session Final manifest, paired rows and evaluator remain frozen.

## Why a recovery evaluation is still interpretable

The stopped attempt produced no Final cache, predictions, target statistics or
scores. Its report records zero fits, zero provider calls, zero raw-row export
and no controller access. The models had already been frozen. Reopening the same
predeclared source after an infrastructure-only repair therefore cannot change
model selection. The result must still be labelled as a recovery after one
runner-only partial read, not as an uninterrupted first-pass evaluation.

If the recovery fails, it stops and is reported incomplete. It does not replace
a session, choose another model, or retry after seeing a score.

## Existing research reused

This is a mechanical resource-envelope repair, not a new forecasting method.
It reuses `SINGLE_OBJECT_AUDIT_2026-09-13.md`, the one-pass hash/identity design,
the truncated-stream tests and the materialization parity checks. No new paper
claim is needed. The relevant observed comparison is the already-opened
2026-09-14T03 diagnostic: 1,949,883 raw records and 3,867,212 selected quote
observations completed, which places the new failure close to the old 4,000,000
guard. A new synthetic canary must prove that the configured larger guard reaches
the remote worker. A previously opened large diagnostic object must then pass
the exact published recovery worker before any Final recovery is allowed.

## Acceptance

- published source and annotated tag match the user's fork;
- synthetic canary passes with zero providers;
- a previously opened large diagnostic source passes and reproduces its prior
  cache hash under the new worker;
- original Round 8 model hashes and all 20 source receipts still match;
- all 20 sessions score every arm on identical paired rows;
- no Final score exists before the corresponding complete source receipt;
- final summary clearly carries the recovery qualification and makes no PnL or
  promotion claim.
