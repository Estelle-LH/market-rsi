# Controller memory: next experiment

## Question

Does a short, structured record of prior rounds help the same GLM researcher
more than either no memory or the complete raw archive?

Only the controller-memory representation changes:

- `fresh`: sees no earlier-round record.
- `archive`: can read its complete own-arm tool and result archive.
- `compact`: can read a deterministic runner-made record containing each tested
  hypothesis, actual fit outcome, interpretation, selected plan, Dev result,
  baseline result, protocol error, cost and source-record hashes. It omits copied
  web pages and routine tool transcript. No model summarizes or edits this record.

The controller model, Codex harness, target, source rows, features, trainer
library, fit limits, seed, number of rounds and evaluation sessions remain the
same. Each arm has its own history and never sees another arm.

## Why this follows from the completed work

The eight-round replacement completed every controller and rolling Dev round.
On equal-session Dev MSE, the complete archive was `2.3285275525678192e-05`,
fresh was `2.4004943994660502e-05`, and the baseline was
`2.5275436247398544e-05`. The archive beat fresh on 5 of 8 sessions, but it cost
about 3.6 times as much.

The preregistered 20-session Final did not complete because its last frozen
source object was truncated. The first 19 Final sessions are therefore only a
diagnostic: archive MSE was `0.0012204794888414532`, fresh MSE was
`0.0011438434917760705`, and baseline MSE was `0.0011376225196439793`.
This cannot support a primary Final conclusion, but it gives a concrete reason
to test whether useful memory can be kept without carrying the whole transcript.

## Data gate before any paid controller call

Every selected Train, rolling Dev and Final `JSONL.zst` object must pass a full
structural read before the experiment starts. The runner records its exact byte
count, compressed and decoded hashes, file identity, decoded byte count and JSON
object count. Every line must parse, decompression must end cleanly, the source
must not change during the read, and no row or target statistic may leave the
data host. A later materialization must reproduce the same receipt.

If one object fails, the experiment does not start. We select a new experiment
manifest before model work; we do not replace a failed Dev or Final after seeing
scores.

This reuses the project's existing one-pass bounded source reader and earlier
source-integrity findings. No new literature search is needed for this mechanical
failure: the applicable evidence is the observed truncated object plus the
existing `single_object_stream` implementation and its truncated-zstd test.

## Evaluation

- Eight rolling rounds; no performance early stop.
- Primary result: equal-session mean MSE on at least 20 untouched future
  sessions, frozen before controller work.
- Secondary: row-weighted MSE, IC, calibration, per-session win fraction,
  result concentration, controller dollars, tool calls, valid candidates and
  protocol errors.
- Report all three pairwise comparisons and treat them as exploratory; do not
  select the best pair after seeing Final.
- The 19 already opened Final sessions from the stopped run can be used only as
  disclosed diagnostics or future Train. They cannot be Final again.
- This is prediction evidence, not a PnL or profitability claim.

## Admission status

The code and experiment manifest must receive a new committed and published
version, pass the zero-paid canary, and receive explicit authorization for this
distinct paid experiment. No new paid run is authorized by the prior
`memory-replication-20260914-02` approval.
