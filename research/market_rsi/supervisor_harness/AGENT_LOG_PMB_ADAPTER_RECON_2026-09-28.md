# PMB adapter reconnaissance — 2026-09-28

- 2026-09-28T22:28:43Z — Assigned read-only reconnaissance at dirty-worktree base `f06214b3bb521096078d897fe60ec9ba589c00c6`; the dirty Market RSI diff digest at dispatch was `788c2e367dd92e410fcdec1599cbf2efe596746d70e31ea38607d4395cad66a7`.
- Boundary: no provider call, public-data download, purchase, sealed-Final read, source edit, commit, tag or push. The worker must not invent the PMB upstream commit SHA.
- Deliverable: exact local integration points, minimal adapter/API/test proposal, and the required immutable upstream pin.

## Result

- 2026-09-28T22:30:07Z — **PASS for a read-only integration replan; implementation remains blocked on exact upstream intake.** Neither this worktree nor canonical `/Users/estelle/Developer/market-rsi` contains a `PredictionMarketBench`, `oddpool`, `AgentContext`, `KXBTCD`, `KXHIGHNY`, `KXNCAAF` or `KXNFLGAME` integration. No upstream commit SHA is locally established, so none is asserted here.
- Existing `kalshi_replay.Replay` is a raw recorded-WebSocket order-book reconstruction with invalidation on gaps, clock reversal and missing snapshots; its own header says it is not a backtest and its summary sets `scoring_ready=False`. Evidence: canonical `research/market_rsi/kalshi_replay.py:1-5,35-192`.
- Existing `taking_replay` is intentionally a separate, approximate top-of-book FOK diagnostic: no passive fills or queue priority, one global pending/open order, approximate fee rounding, and `scientific_admission=False`. It must not be extended or represented as PredictionMarketBench execution. Evidence: canonical `research/market_rsi/taking_replay.py:1-8,73-101,240-258,299-313` and `research/market_rsi/tests/test_taking_replay.py:38-226`.
- Existing Harbor agents implement `setup(environment)` and `run(instruction, environment, context)`; the context is used for terminal metadata and is not a prediction-market trading `AgentContext`. Evidence: canonical `research/market_rsi/development_harbor.py:228-319` and `research/market_rsi/controller_candidate_harbor.py:350-429`.
- Existing sequential prediction code provides useful design precedent for as-of release, complete prediction masks and append/fsync hash-chain receipts, but consumes pre-materialized rows rather than PMB's live replay context. Evidence: canonical `research/market_rsi/prediction_stream.py:1-8,43-88,91-141,144-199`.
- Existing dependency practice is explicit consumer-owned commit/file pinning plus import-origin verification and frozen runtime identity. Evidence: canonical `research/market_rsi/data_scientist_harness/core_dependency.py:1-49` and `research/market_rsi/data_scientist_harness/store.py:22-33`. The repository has no `pyproject.toml`, `setup.py`, `setup.cfg`, `tox.ini` or `pytest.ini`; its two scoped dependency lists are `data_scientist_harness/requirements-cpu.txt` and `supervisor_harness/live_runtime_requirements_v1.txt`. Test convention is stdlib `unittest`; evidence: canonical `research/market_rsi/README.md:139-150`. Repository-wide discovery is recorded elsewhere as `python -m unittest discover -s research/market_rsi -p 'test*.py'`.
- Existing prediction scoring already demonstrates frozen source/baseline/candidate hashes, exact full-cohort coverage, chronological separation, per-date paired aggregation and a minimum-20-date promotion gate. Evidence: canonical `research/market_rsi/prediction_benchmark_v0/score.py:67-212`.

## Minimal adapter proposal

Keep the present complex Supervisor Harness frozen as `strict-v0`. Add a parallel `research/market_rsi/simple_episode_lane/` rather than editing `supervisor_harness` or either existing simulator:

1. `upstream_lock.py`: `UpstreamLock.verify(checkout)` checks the official repository URL, exact 40-character commit, clean checkout, tree/license manifest and that imported PMB modules resolve inside the pinned checkout.
2. `episode_manifest.py`: `EpisodeManifest` binds episode ID, venue, domain, diagnostic/Train/Dev/hidden-Final role, upstream identity, simulator config/seed and hashes for `metadata.json`, `orderbook.parquet`, `trades.parquet` and `settlement.json`. Public January episodes must be labelled diagnostic, never OOS/Final.
3. `candidate.py`: `FrozenPredictionPolicy` loads one immutable candidate and emits timestamped fair-probability or future-price-change predictions before any order action.
4. `pmb_agent.py`: the only upstream-specific bridge. It must implement the actual PMB agent hook and use the actual `AgentContext` API after inspecting the pinned source; hook/class/module names must not be guessed before that intake. It receives no raw episode path or hidden settlement path.
5. `runner.py`: `PmbEpisodeRunner` verifies the lock, episode manifest and candidate, then calls the official upstream runner. It does not implement or override event ordering, maker/taker matching, queueing, fees, slippage or settlement. It records pre/post upstream tree hashes and hashes of official outputs.
6. `evidence.py`: Track A independently evaluates prediction quality and incremental information beyond market price; Track B only aggregates PMB-produced PnL, fees/slippage, drawdown, fill ratio, active dates and concentration. It does not recompute exchange execution.

Pin the upstream as a durable local git submodule at `third_party/PredictionMarketBench`, pointing to `https://github.com/oddpool/PredictionMarketBench.git`, detached at an exact reviewed 40-character SHA. A companion `simple_episode_lane/upstream.lock.json` should record that URL/SHA, tree-file manifest, license hash and inspected API/dependency entrypoints. Runtime code must never fetch, pull or follow a branch/tag. The SHA is currently unknown and is an explicit blocker. After authorized upstream intake, derive a separate `requirements-pmb.lock` and isolated environment from the pinned upstream declaration; do not append unknown PMB dependencies to either current requirements file.

## Required tests

- Reject missing/short/mismatched SHA, wrong URL, dirty upstream, changed license/tree and import origin outside the submodule.
- Reject changed candidate/config/episode bytes; verify all four episode-file hashes and immutable role/domain/venue assignments.
- Enforce AgentContext-only, monotone/as-of observations and prediction commitment before action; prove hidden raw files and `settlement.json` are absent from Controller/Researcher inputs.
- Run the same pinned episode/candidate/config/seed twice and require identical action, trade, metric and output hashes; verify the upstream tree is unchanged before/after.
- Pass an official PMB reference baseline through the adapter and require exact official outputs, showing no local execution-semantic rewrite.
- Test Track A completeness and Brier/log-loss/MSE/calibration/incremental-market metrics separately from Track B; ensure Track B values are read from PMB output, not locally re-simulated.
- Return aggregate-only hidden-evaluator evidence with no raw events, order identifiers or settlement contents; keep Kalshi and Polymarket cohorts separate and reject a formal Final claim with fewer than 20 untouched dates.
- Run targeted `unittest` discovery for `simple_episode_lane`, then the pinned-runtime repository-wide suite and the pinned upstream's own documented tests after its exact source and dependency instructions are inspected.

## Boundary confirmation

This task performed local read-only inspection only. It made no network request, provider call, purchase, data download, experiment run, Docker/E2B launch, sealed-Final read, commit, tag, push or source implementation change. The only write is this registered agent-log result. No PMB exact commit, dependency version, import path or callback name has been invented.

## Supervisor upstream-ref verification

- 2026-09-28T22:31Z — After the worker froze its local-only report, the Supervisor made one read-only `git ls-remote` query to the official URL. `refs/heads/main` resolved to exact commit `611d66941717310858683278940df21c33c406f2`. This identifies the prospective intake commit; it is not yet a vendored checkout, tree/license manifest, dependency lock or accepted runtime.
