# Market RSI × PredictionMarketBench replan v2 — fail-closed amendment

Date: 2026-09-28

This amendment applies together with v1, `PREDICTIONMARKETBENCH_REPLAN_2026-09-28.md`, exact SHA-256 `d08c213ddaec28abd0b7561811c52ad162713f9b3945f6afdb1d4980ef8ad2f4`. It supersedes v1 wherever the two differ. V1 remains an immutable reviewed REPLAN snapshot.

The accepted direction is unchanged: PMB is the fixed simulator; strict-v0 is frozen as the protected-action lane; the new code lives in a separate `pmb_simple_lane`; public January 2026 episodes are diagnostic only; Track A prediction evidence precedes a separately frozen Track B trading test.

## 1. Data roles and feedback

The manifest has four disjoint roles with separate durable roots, credentials and ledgers:

| Role | Controller visibility | Feedback | Promotion use |
| --- | --- | --- | --- |
| `public_diagnostic_train` | Raw public Train bytes and allowed tools | Full diagnostic evidence allowed | Never |
| `train` | Admitted Train bytes and allowed tools | Full Train evidence allowed | Candidate development only |
| `hidden_dev` | No raw bytes, paths, IDs, dates or settlement | Fixed aggregate schema; may enter the next Controller round | Model selection only; every opened date is permanently tainted |
| `sealed_final` | No raw bytes, paths, IDs, dates, settlement or prior results | One terminal human/report artifact only | Final evidence; never returns to Controller/Researcher memory |

Before any open, the trusted episode owner rejects an episode/date/file appearing in more than one role or in a prior diagnostic, hidden-Dev or Final exposure ledger. Relabeling, changed bytes or a new source version never makes an opened date untouched again.

Hidden Dev is the only hidden role that can support iterative feedback. Its manifest freezes `max_hidden_dev_evaluations`, candidate/evaluator bindings and the only reportable cells before the first query. Each claim consumes one query and permanently taints the evaluated dates even on failure. Exhaustion is terminal; no new subset is chosen based on results.

Sealed Final is one shot. The complete candidate, Track A specification, any precommitted Track B policy, cohort and public-report schema freeze before the claim. The evaluator writes the Final report to a terminal reporting namespace that is excluded from all future Controller packets, searchable archives, prompt construction and candidate selection. A Final failure or invalid common mask consumes the claim. No new candidate, threshold, cell or cohort is evaluated from that result.

## 2. Network and intake authorization

The one read-only `git ls-remote` ref lookup already completed is the only PMB network action admitted by v1/v2.

The following remain blocked until a separately recorded authorization names the source, destination and action:

- `git clone`, `git fetch`, submodule add/update or any source-tree download;
- downloading/materializing the four public episode directories;
- any new public-data API or archive request;
- package/dependency download or installer network access.

Zero-paid implementation may proceed only with synthetic fixtures and already admitted local bytes. Prospective commit `611d66941717310858683278940df21c33c406f2` is not an accepted runtime until authorized intake, tree/license/dependency/import verification and upstream tests complete. The user's broad “授权所有” is not treated as an exact network-intake, payment, sealed-Final or publication authorization.

## 3. Aggregate disclosure and differencing protection

`hidden_dev` and `sealed_final` use different exact output schemas and ledgers. Both reject unknown fields recursively.

- Report cells are fixed in the cohort manifest. No evaluator request may introduce an ad hoc episode, date, market, ticker, time bucket or overlapping subgroup.
- Cells must be mutually non-overlapping within one report. The initial formal policy requires at least 5 distinct dates and 10 markets per reported cell; the sealed-Final total additionally requires at least 20 distinct untouched dates. A stricter preregistered threshold may replace these values before any open.
- An undersupported cell returns only `suppressed=true` and a code-owned broad reason; it returns no exact support count, metric, interval or identifier.
- The aggregate schema reports predeclared venue/domain cells separately and never emits arbitrary combinations that permit subtraction. Kalshi and Polymarket never share a cell.
- The append-only disclosure ledger binds role, cohort, candidate, schema, cell set and output hash. It rejects repeated, overlapping or algebraically derivable projections and schema/rounding changes.
- Hidden-Dev query count and cumulative cell disclosure are capped before the first query. Sealed Final has exactly one fixed projection.
- Exact dates, episode/market/ticker/order/trade IDs, row predictions/labels, timestamps, paths, settlements, per-date/per-episode maps and raw traces remain forbidden.

Small-cell or differencing ambiguity fails closed; the system does not weaken suppression to make a report more informative.

## 4. Immutable experiment specification

The trusted episode owner creates and fsyncs `experiment_spec.json` before round 1 in a root that the Controller and Researcher cannot write. The candidate workspace receives a read-only projection plus its hash.

The immutable specification binds:

- one problem sentence and one changed causal stage;
- target, horizon, executable-price rule, maximum mark lateness and row mask;
- cadence, baseline, normalizer, trainer, loss/scorer and feature-sign policy;
- costs, latency, exclusions, missing-row behavior and seeds;
- candidate, adapter, PMB upstream, episode/cohort and runtime commitments;
- Track A metrics, support rules and aggregate schema;
- whether Track B is absent or the exact separately frozen Track B contract.

The broker verifies the spec hash before and after every Controller turn, Researcher task, candidate freeze and evaluator run. Any mutation, shadow copy or alternate scorer is terminal.

Track B uses a separate never-reused evaluation ID and a trading-policy hash committed before any Track B output is opened. It binds the frozen Track A candidate and may change only the PnL-policy stage. Track B results cannot rewrite, select or recalibrate Track A.

## 5. Pre-open and post-replay gates

### Pre-open admission

Before resolving or opening hidden paths, require:

- exact role-separated episode manifest and no role/date/exposure overlap;
- strict chronological Train -> hidden Dev -> sealed Final ordering;
- for sealed Final, at least 20 distinct untouched UTC dates in the private manifest;
- exact frozen upstream, adapter, runtime, candidate, experiment spec and report-schema hashes;
- unique one-shot evaluation ID, remaining role-specific allowance and claim fsynced;
- private/public roots, no symlink/path escape and no credentials/network;
- for Track B, separate ID and precommitted policy hash.

The pre-open gate does **not** claim prediction-row completeness, because hidden replay has not run.

### Post-replay, pre-release result admission

After replay but before any public aggregate is published, require:

- baseline and candidate predictions on the exact same eligible row mask;
- complete required predictions, explicit missing/invalid counts and no silent mask shrinkage;
- deterministic output/trace hashes and unchanged source/spec/upstream/runtime commitments;
- the fixed cell/support/disclosure policy and no forbidden field;
- Track A/Track B stage separation and the correct evaluation ID.

If common-mask completeness or any result-admission check fails, the evaluator stores full evidence privately, consumes the claim and publishes only a schema-valid terminal invalid status with no scientific metric. It never retries or chooses another subset.

## 6. Required negative tests added by v2

- hidden-Dev aggregate passed into a later round is allowed only under its query/disclosure ledger; any sealed-Final artifact in a Controller packet fails.
- role/date reuse, relabeling, changed bytes, cross-role overlap and post-result subset replacement fail before open.
- 0–19 sealed-Final dates, 20 episodes on one date and opened-date reuse fail before open.
- clone/fetch/submodule/episode/package network actions fail without an exact intake authorization receipt.
- cells below 5 dates or 10 markets suppress; overlapping cells, repeated projections, rounding/schema drift and subtractable candidate/cohort queries fail.
- Controller/Researcher writes or shadows `experiment_spec.json`, scorer, baseline, row mask or evaluator fail; every round checks the same spec hash.
- Track B reuses the Track A ID, lacks a precommitted policy, changes prediction bytes or feeds its output back into Track A selection fails.
- incomplete common masks fail only after private replay and before public metric release; the one-shot claim remains consumed.
- wrong/dirty/import-diverted PMB, symlink/path escape and upstream/runtime drift fail at their appropriate pre-open or post-replay gates.

## 7. Next allowed step

After independent PASS on the combined v1+v2 contract, the next allowed work is local, zero-provider implementation against synthetic PMB-shaped fixtures: immutable spec, role manifests, upstream-lock validator, episode lease and negative tests. Actual PMB source intake, public episode download, provider-backed Controller execution, sealed data, release and publication remain separately gated.
