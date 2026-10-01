# PredictionMarketBench hidden-evaluation boundary review

Date: 2026-09-28  
Role: independent hidden-evaluation boundary worker  
Scope: local source inspection and design only

## Terminal conclusion

The repository already contains strong reusable primitives for append-only exposure ledgers, one-shot evaluation claims, candidate/source commitments, protected Final budget, no-network execution, credential isolation, strict chronological splitting, and a minimum of 20 untouched Final dates. It does **not** yet implement the requested PredictionMarketBench boundary as one closed system.

The principal mismatch is that the legacy controller workspace exposes current Dev feature rows (`controller_workspace.py` builds `train-dev-public.json`), while the new boundary requires the Controller to see only allowed Train data and/or the simulator's `AgentContext`. A second mismatch is that existing score objects retain per-date/per-game information; a hidden evaluator must persist those records privately and return only a schema-limited aggregate projection.

Recommendation: keep the current complex harness frozen as `strict-v0` and add a parallel PMB Simple Episode Lane. Reuse its security primitives, but do not retrofit hidden PMB episodes into the old Train/Dev workspace.

No sealed Final data was read. No network or provider call was made. No paid action was taken. No source file was modified by this review; this log is the only written artifact.

## Material checks

### Existing data roles and split gates

- `prospective_data_lifecycle.py` freezes ordered Train/Dev rounds, rejects dataset reuse across roles, hides Transfer before final freeze, requires all rounds to finish before Transfer submissions freeze, and records transitions in an append-only hash chain.
- `time_series_split_policy.py` enforces past-to-future ordering, whole-game isolation, target-blind boundary selection, label purge, one Dev opening per round, and `final_promotion_minimum_untouched_utc_days = 20`.
- `polymarket_data.py` already has `train`, `route_dev`, `audit_dev`, and `test` roles, chronological whole-game splitting, and an opaque Test commitment. Its public projection still exposes Route-Dev and Audit-Dev feature rows, so it must not be reused directly as the new Controller-visible PMB projection.
- `polymarket_scoring.py` enforces, for a Test contract, untouched evidence, a predeclared commitment, at least 20 distinct games, at least 20 untouched UTC dates, and a one-shot filesystem gate consumed before row validation/scoring.
- `scripts/validate_experiment_spec.py` already encodes the desired scientific policy: previously opened periods are diagnostic only, Final has at least 20 dates, Dev feedback is aggregate-only, the strong baseline is Train-selected, prediction is primary, and PnL is not a substitute for prediction evidence.

### Current Controller exposure

- `controller_workspace.py` validates immutable visible files and strips Dev labels, but writes every current Dev public feature row to `train-dev-public.json`. This is stricter than ordinary research but weaker than the requested PMB boundary.
- `controller_harness_contract.py` explicitly declares visible splits as `train` and `dev`. Its denied-capability list already forbids future Test, current Dev labels, host filesystem, credentials, direct paid dispatch, and unlogged network.
- `controller_candidate_harbor.py` keeps evaluation labels in the trusted job directory, sends only public rows to candidate code, disables network, and reads `E2B_API_KEY` only inside the trusted environment launcher. The candidate sandbox is not given the credential.

### Existing artifacts and evaluator behavior

- `data_scientist_harness/sealed_dev_gate.py` is the closest reusable pattern: private/public directories, cohort and evaluator commitments, claim-before-open, a consumed allowance even on failure, raw paths returned only to the trusted caller, and a public result receipt containing only a result hash.
- `sealed_dev_runner.py` binds a reaped Controller session, candidate hash, lifecycle view, and exact Dev claim before execution; it does not retry and records infrastructure failures durably.
- `controller_candidate_harbor.py` stores raw evaluation labels, predictions, split audit, and full score inside the trusted job. Its outward summary excludes row outcomes and per-game detail, but includes `temporal_robustness`, whose `days` object exposes exact date keys. That is too granular for the proposed hidden evaluator.
- `prediction_benchmark_v0/score.py` is explicitly only a development scorer and not an access boundary. It returns `per_date` and `per_game`, and a 19-date cohort merely fails a promotion flag after scoring. For formal hidden Final, the 20-date gate must reject the cohort before any Final opening; the full scorer output must remain runner-private.

### Budget and credential boundary

- `paid_budget.py` protects bucket allocations, prevents job-ID reuse and duplicate dispatch, retains holds for unresolved dispatches, and forbids borrowing occupied/protected funds. The existing Final bucket is therefore reusable as an outer authorization boundary.
- Provider/model credentials must remain absent from all Controller and candidate mounts. The PMB evaluator itself should be offline and credential-free. If a paid Controller is used, only the trusted launcher may resolve its credential after source/spec/budget validation and a unique reservation; no automatic retry is permitted.
- Raw PMB episodes and settlement must live in a stable local persistent root outside the Git worktree, cloud-synced folders, and temporary directories. The manifest may expose hashes and counts, never filesystem paths.

## Proposed PMB boundary

### Three-process separation

1. **Controller/Researcher** sees allowed public Train artifacts, code/tooling, prior aggregate Dev evidence, and the PMB adapter. It receives no hidden episode path, episode ID, date list, order/trade rows, settlement, evaluator config, or credential path.
2. **Candidate agent runtime** runs with no network and no credentials. During replay it sees only PMB `AgentContext` methods. It has no filesystem mount containing raw episode files or `settlement.json`, including on Train replay; offline Train analysis may occur in a separate allowed-Train research mount.
3. **Trusted Evaluator** alone mounts the frozen PMB upstream source, hidden raw episode files, settlement, candidate snapshot, scorer, and private artifact root. It claims the evaluation before opening data, runs deterministically, stores full traces/scores privately, validates the public projection, and emits aggregate evidence only.

### Lifecycle

1. Freeze an episode cohort manifest before research: exact PMB upstream commit, adapter hash, simulator config, venue, domain, UTC episode date, role, and SHA-256/byte length for `metadata.json`, `orderbook.parquet`, `trades.parquet`, and `settlement.json`.
2. Enforce role disjointness and strict chronology. The four January 2026 public episodes are permanently `diagnostic`; none may be relabeled as formal Dev/Final or used for promotion evidence.
3. Freeze Track A target, horizon, timestamp/as-of rule, strong market baseline, metrics, exclusions, and candidate budget before any hidden evaluation. Freeze Track B trading policy only after the prediction candidate is frozen.
4. Freeze the candidate source-tree hash, dependency lock/image digest, PMB commit, adapter hash, seed, and configuration.
5. Consume the Dev/Final claim before resolving or reading hidden paths. A crash or invalid candidate consumes that evaluation ID; recovery reconciles receipts and never resamples.
6. Store full prediction, replay, per-date/per-episode, trade, fill, and settlement-derived evidence privately. Publish only the validated aggregate schema. Dev aggregates may enter the next Controller round; Final output is terminal and never re-enters research memory.

### Public aggregate evidence schema

The public artifact should contain only:

- immutable bindings: evaluation ID, candidate/source/config hashes, PMB commit, cohort commitment, evidence class, changed causal stage;
- support counts: episode count, distinct-date count, market count, valid/failed action counts, and predeclared venue/domain cohort names without episode/date/market IDs;
- Track A primary: candidate and strong-market-baseline Brier/log loss/MSE as applicable, calibration slope/intercept, candidate-minus-baseline paired delta, date-block interval, positive-date fraction, coverage, and validity/gate booleans;
- Track B secondary, only after prediction freeze: net PnL, fees, slippage, maximum drawdown, fill ratio, active-date count, and concentration summary;
- execution integrity: one-shot consumed, deterministic replay, no network, credentials absent, full-cohort coverage, automatic retry false, and private-result hash.

It must reject recursively any raw labels/predictions, episode/date/market/ticker/order/trade IDs, exact timestamps, per-date/per-episode arrays/maps, settlement values, raw PMB paths, stdout/stderr traces, credentials, or tool transcripts. Kalshi and Polymarket must be separate cohorts; crypto, weather, and sports should be separately aggregated, never pooled as the only result.

## Concrete file plan

Keep legacy strict-v0 source behavior unchanged. Add a new package and tests:

- `research/market_rsi/pmb_simple_lane/episode_manifest.py`: exact episode-file schema, upstream commit binding, data roles, diagnostic exposure ledger, venue/domain/date checks, role disjointness, and persistent-root anchoring.
- `research/market_rsi/pmb_simple_lane/experiment_spec.py`: fail-closed Track A/Track B contract; one changed causal stage; frozen target/horizon/baseline/costs; Final policy; no paid authority implied.
- `research/market_rsi/pmb_simple_lane/controller_workspace.py`: visible allowlist containing only allowed Train data/code/prior aggregate evidence; no Dev/Final rows, paths, identifiers, or settlement.
- `research/market_rsi/pmb_simple_lane/agent_adapter.py`: thin adapter from frozen Market RSI candidate interface to the pinned PMB Agent/AgentContext API; no simulator rewrite.
- `research/market_rsi/pmb_simple_lane/evaluation_gate.py`: private/public roots, append-only ledger, reserve/register/claim/terminal states, claim-before-open, one use per evaluation ID, no retry.
- `research/market_rsi/pmb_simple_lane/hidden_evaluator.py`: trusted offline replay owner, read-only hidden mounts, candidate AgentContext-only execution, private trace/full-score storage, deterministic receipt verification.
- `research/market_rsi/pmb_simple_lane/aggregate_evidence.py`: exact public schema, recursive forbidden-field/path/identifier checks, cohort aggregation, and Track A/Track B separation.
- `research/market_rsi/pmb_simple_lane/final_policy.py`: chronology/exposure audit, at least 20 untouched UTC dates, no previously inspected date, exact cohort commitment, candidate freeze, one terminal Final opening.
- `research/market_rsi/pmb_simple_lane/artifact_store.py`: stable-local-root validation, exclusive creation, mode `0700`, no symlinks, append-only receipts, and private/public namespace separation.
- `research/market_rsi/tests/test_pmb_simple_lane_*.py`: negative and deterministic integration tests listed below.

Do not return `prediction_benchmark_v0.score.score()` directly. It can be refactored into a private scorer core, but its per-date/per-game result must remain inside the trusted evaluator and pass through `aggregate_evidence.py` before publication.

## Required fail-closed tests

### Data and role isolation

- Reject a cohort with missing/extra episode files, wrong hash/size, unpinned or changed PMB commit, symlinked files, duplicate episode/date/role membership, mixed venues in one cohort, or Train/Dev/Final overlap.
- Reject any formal Final date that appeared in Train, Dev, a public diagnostic episode, a prior failed/opened Final claim, or external-history selection feedback.
- Reject nonchronological Train/Dev/Final, cross-boundary as-of violations, and external history whose timestamp exceeds the replay clock.
- Prove the four public January 2026 episodes are always diagnostic and never promotion-eligible.

### Workspace and runtime isolation

- Inventory the Controller workspace and fail on any unexpected file, hidden path, raw Dev/Final data, episode/date ID, settlement, evaluator config, env file, or credential.
- Assert the candidate mount contains only source/runtime plus AgentContext transport; attempts to open raw episode/settlement paths, enumerate host paths, access network, or read environment secrets fail.
- Assert evaluator-private raw results cannot be hard-linked, symlinked, copied, or named into the public artifact tree.

### One-shot and binding

- Claim is written and fsynced before the first hidden-data open; a failure during open/replay/scoring still leaves allowance zero.
- Reject duplicate claim, retry, candidate hash drift, dependency/image drift, target/horizon/baseline/cost/latency drift, PMB commit drift, or aggregate projector drift.
- Reconciliation may finalize the exact pending receipt only; it may not launch another replay.

### Aggregate-only output

- Exact-schema validation rejects unknown fields recursively, NaN/Inf, unbounded arrays/strings, row-level predictions/labels, IDs, dates/timestamps, raw paths, per-date/per-episode maps, settlements, trades/orders/fills, and stdout/stderr.
- Public Track A evidence recomputes from the private result hash and reports the same common cohort for baseline/candidate; missing predictions invalidate rather than shrink the mask.
- Public Track B is absent until prediction is frozen; once present, it cannot alter Track A metrics or promotion gates.
- Domain and venue reports are predeclared aggregate cohorts. Empty/undersupported cohorts return invalid/null evidence, never disappear from the report.

### Final >=20 dates

- Formal Final admission with 0-19 distinct untouched UTC dates raises before opening Final; it is not merely a post-score `promotion=false` result.
- Twenty episodes on one date fail; multiple episodes across only 19 dates fail; at least 20 distinct dates plus all other gates pass admission.
- Previously inspected dates do not count, even if relabeled or source bytes change.
- The date count is computed by the trusted evaluator from the frozen private manifest and cross-checked against the public count; the Controller never receives the date list.
- Final remains one shot after all candidate/config/baseline hashes freeze. A failed Final attempt is consumed and cannot be replaced with another 20-date subset.

### Budget and credentials

- Local PMB replay runs with zero provider credentials and cannot charge a provider bucket.
- Any paid Controller dispatch requires a unique authorized job ID, exact input hash, matching budget experiment/bucket, terminal metering reconciliation, and `automatic_retry=false`.
- Learning/repair/setup cannot reserve against Final; Final cannot execute if the protected allocation, full atomic batch, or reporting window is insufficient.

## Final-date rule

For formal evidence, the admission rule should be conjunctive:

`untouched && distinct_utc_dates >= 20 && no_opened_date_overlap && strict_time_order && exact_frozen_cohort && one_shot_claim && candidate_frozen && complete_common_mask`

Twenty dates are a floor, not sufficient proof. Sparse activity, domain imbalance, or venue concentration can require more dates. Primary inference must block by date; exact dates and per-date deltas remain evaluator-private. Previously inspected periods remain diagnostic forever.

## Implementation order

1. Episode manifest plus formal Final admission validator.
2. Controller workspace allowlist and AgentContext-only candidate adapter.
3. One-shot private gate and trusted evaluator.
4. Aggregate projector with recursive leakage tests.
5. Deterministic synthetic integration tests, then the four public episodes as diagnostic-only integration tests.
6. Independent source review before any fresh hidden cohort, paid Controller, or Final authorization.

The evaluation-gate skill materially shaped this design by keeping `raw data -> prediction -> objective -> PnL` separate, making Track A prediction evidence primary, requiring one changed stage per comparison, and preventing trading PnL from substituting for prediction validity.
