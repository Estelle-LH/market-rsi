# Market RSI × PredictionMarketBench replan — 2026-09-28

## Decision

Use PredictionMarketBench (PMB) as the fixed replay and trading-execution base. Stop expanding the legacy parser/canary/release-gate path by default. Build one thin Market RSI research/evaluation lane around PMB; do not rewrite PMB's event ordering, maker/taker fills, queueing, fees, settlement or standard output calculations.

The public January 2026 episodes are **Development/Diagnostic only**. They can validate integration, self-iteration and Controller behavior, but they cannot support an unseen-date, formal Final or paper-performance claim.

Prospective upstream intake is pinned to official `refs/heads/main` commit:

`611d66941717310858683278940df21c33c406f2`

This SHA was resolved by one read-only `git ls-remote` query on 2026-09-28. The commit is not yet accepted as a runtime until a durable checkout, tree/license manifest, dependency lock, import-origin check and upstream tests pass.

## What pauses, what remains

| Decision | Scope |
| --- | --- |
| Pause | v0.1.26 remote push, fresh canary/fetch, Gate 1 parser/tool-schema expansion, legacy NFL/Polymarket data-plumbing as the default experiment path, and any claim that a canary or release is an experiment result. |
| Preserve | The local v0.1.26 candidate and its review/test evidence remain parked and immutable; no evidence is deleted or rewritten. |
| Retain from strict-v0 | Budget and credential custody, external-side-effect authorization, sealed-Final isolation, never-reused IDs, exact source/runtime commitments, one-shot claims, append-only artifacts, cleanup and independent terminal review. |
| Do not carry into each research round | Global release/canary expansion, short-choice menus and per-round source publication. The Simple Lane has one episode lease and start/end snapshots; internal research rounds do not each require a new global canary. |

## Minimal architecture

```text
Controller -> Researcher in persistent Docker -> frozen prediction candidate
    |                    |                           |
    | Train/diagnostic   | code/tools/workspace      | immutable source+config hash
    v                    v                           v
Trusted episode owner -> thin PMB Agent adapter -> pinned PMB replay
                                                   |
                         private full evidence <----+
                                                   |
                             aggregate-only evidence -> next Controller round
```

Add a separate `research/market_rsi/pmb_simple_lane/` package. Do not modify existing `kalshi_replay.py` or `taking_replay.py` into a substitute simulator; both have materially weaker semantics.

### Upstream and data

- `third_party/PredictionMarketBench` is an exact detached git submodule at commit `611d66941717310858683278940df21c33c406f2` after intake review.
- `upstream.lock.json` binds URL, commit, tree/file manifest, license hash, inspected API entrypoints and dependency declaration.
- A separate PMB dependency lock and environment are derived from the pinned upstream. They do not modify strict-v0 runtime requirements.
- Runtime rejects the wrong URL/SHA, dirty upstream, tree/license drift, imports outside the pinned checkout, or any attempt to fetch/pull.
- Episode bytes live in `/Users/estelle/Library/Application Support/MarketRSI/pmb-simple-lane/episodes`, not a cloud folder, temporary directory or disposable worktree. Git stores only manifests/hashes and public code.

### New package

- `upstream_lock.py`: exact upstream/runtime/import verification.
- `episode_manifest.py`: venue, domain, UTC date, role and hashes/lengths for metadata, orderbook, trades and settlement.
- `experiment_spec.py`: one-sentence question, one changed causal stage, frozen target/horizon/baseline/costs/latency/exclusions/metrics.
- `prediction.py`: immutable timestamped fair-probability or future-price-change predictions committed before orders.
- `agent_adapter.py`: the only PMB-specific bridge; it implements the pinned upstream's real `Agent`/`AgentContext` contract.
- `episode_lease.py` and `artifact_store.py`: one episode ID, start/end snapshots, append-only journal, durable exclusive-create artifacts and exact cleanup.
- `controller_workspace.py`: allowed public Train/code/prior aggregates only; no hidden path, episode/date list, settlement, evaluator config or credentials.
- `runner.py`: verifies commitments and calls the official PMB harness. It never reimplements execution.
- `hidden_evaluator.py`: trusted offline owner of hidden episode bytes, settlement, candidate and private full evidence.
- `aggregate_evidence.py`: exact-schema aggregate projection with recursive leakage rejection.
- `controller_swap.py`: paired-arm equality, cross-arm isolation, arm-order commitment and blinded evaluation.

## Closed-loop episode protocol

One episode has one never-reused ID, one Controller session, one persistent Researcher container, one immutable start snapshot and five Controller decision slots.

- Slots 1–4: each may issue at most one logged Researcher task or stop early.
- Slot 5: forced terminal synthesis and candidate freeze; it cannot dispatch a hidden sixth task.
- The Controller may research, write code/tools and modify its candidate harness inside the episode workspace. It is not constrained to a short-choice menu.
- Each round records hypothesis, changed causal stage, support/refutation criteria, action, admitted observation and next decision.
- No provider resampling or automatic retry. An infrastructure ambiguity is terminal for that episode ID.
- One persistent Docker container serves all rounds: no network, no credentials, non-root, read-only code/Train mounts and one writable episode workspace.
- Only episode start/end snapshots are global. Per-round artifacts remain append-only under the episode lease.

The state path is:

`registered -> start_snapshotted -> running_round_N -> candidate_frozen -> terminal_review_pending -> closed_passed | closed_failed | unresolved`

## First Train-only self-iteration episode

Episode: `KXBTCD-26JAN2017`, permanently labelled `public_diagnostic_train`; no promotion eligibility.

Problem statement: **Can a Controller-led, order-book-derived prediction adjustment improve 15-minute future executable midpoint prediction over the no-change market-price baseline on the same as-of PMB replay rows?**

- Changed stage: prediction only.
- Candidate output: future price change or equivalent 15-minute probability mark adjustment, committed before the future window.
- Frozen baseline: current executable market midpoint/no-change forecast.
- Frozen cadence: 60 seconds.
- Primary diagnostic metrics: paired candidate-minus-baseline MSE, calibration slope/intercept, signed Pearson/rank IC for predicted change, complete common-mask coverage, positive-market fraction and block interval. Brier/log loss are reserved for the later settlement-probability target; they are not mixed into this experiment.
- No Track B optimization in the five research rounds. After the prediction candidate freezes, one separate diagnostic PMB replay may report trading metrics without changing the prediction.
- Because the Controller can inspect this public episode during research, every score is in-sample diagnostic evidence, even if computed by a chronological replay. It cannot promote a candidate.

The exact target construction, executable-price rule, maximum mark lateness and missing-row policy must be frozen in `experiment_spec.json` before the first observation is returned. Missing future marks invalidate rows; they are not forward-filled.

## Evidence tracks

### Track A — primary: prediction discovery

Evaluate prediction before monetization:

- fair probability or fixed-horizon future price change;
- Brier/log loss for binary settlement targets, MSE for future-price targets;
- calibration slope/intercept and coverage;
- incremental information over current market price on an identical row mask;
- stability by date, market, venue and domain with block intervals;
- candidate/source/config hashes and reproducibility.

### Track B — secondary: trading after prediction freeze

PMB alone computes execution results. The Market RSI layer only reads official outputs:

- net PnL, fees, slippage and maximum drawdown;
- fill ratio, maker/taker mix, trades and active dates;
- episode/market/date concentration;
- deterministic output hashes.

Track B cannot repair or replace a failing Track A result. Trading-policy changes are separate A/B experiments with the prediction held fixed.

## Hidden evaluator boundary

1. Controller/Researcher sees allowed Train data, code and prior aggregate evidence only.
2. Candidate runtime sees PMB `AgentContext` only and has no raw episode/settlement filesystem mount, network or credentials.
3. Trusted evaluator alone mounts hidden raw episode files, settlement, pinned PMB, frozen candidate and private artifact root.
4. The one-shot claim is written and fsynced before any hidden path is resolved or opened. Failure consumes the ID.
5. Full predictions, rows, dates, episode IDs, trades, fills, settlement-derived values and traces stay private.
6. Public evidence contains only frozen bindings, support counts, aggregate Track A/Track B metrics, intervals and integrity booleans. Unknown fields and row/date/episode/order/trade identifiers fail closed.
7. Kalshi and Polymarket are separate cohorts. Crypto, weather and sports are separately reported.

Formal Final admission rejects **before opening** unless there are at least 20 distinct untouched UTC dates, strict chronology, no overlap with any opened/diagnostic date, an exact frozen cohort, one-shot claim, frozen candidate and complete common mask. Twenty dates are a floor, not sufficient evidence by themselves.

## Clean Controller Swap

Use the four public PMB episodes as a permanently diagnostic paired test. Each episode gets two independent arm runs; both receive the same episode bytes, Supervisor, Researcher image, tools, logical prompts, five slots, seed where supported, and token/USD/wall/CPU/memory ceilings. The second arm never sees the first arm's artifacts.

Only Controller-stack identity changes. The repository currently pins GLM 5.3, not an exact model called “GLM 3.5”; the frontier model, adapters, tokenizer/rendering contracts and rates are not yet fixed. Do not silently substitute identities. The paid swap remains blocked until both exact stacks are frozen and separately canaried at the adapter boundary.

Primary swap measurements:

- valid research-action rate and executable-task rate;
- correct causal-stage isolation and preregistration;
- response to negative evidence and rerouting after failure;
- evidence increment per round;
- reproducible frozen candidate;
- protocol closure, time, tokens and cost per admitted observation.

Candidate prediction diagnostics are secondary paired evidence. PnL is not a Controller-quality proxy. One four-episode diagnostic cannot establish general model superiority.

## Implementation and experiment gates

### Phase 0 — zero-paid local implementation

1. Intake and verify upstream commit `611d6694…06f2` in the durable canonical repo.
2. Implement upstream lock, episode manifest, prediction record and thin adapter.
3. Implement episode lease, persistent-B boundary and append-only artifact store.
4. Implement private evaluator and aggregate projector.
5. Run focused negative tests, pinned upstream tests, deterministic duplicate replay and the relevant full local suite.
6. Independent review of one integrated snapshot.

### Phase 1 — diagnostic loop

1. Run a zero-provider synthetic episode to verify five-slot lifecycle and cleanup.
2. Run the single-Controller `KXBTCD-26JAN2017` public diagnostic episode.
3. Freeze the candidate and, separately, run one Track B diagnostic without changing Track A.
4. Preserve negative and failed results; no resampling for a better score.

### Phase 2 — diagnostic Controller Swap

1. Freeze both exact Controller stacks and equal budgets.
2. Run paired arms across all four public episodes with preregistered order.
3. Independent blinded review returns aggregate paired evidence only.

### Phase 3 — formal MarketRSI-Bench

1. Expand dates/events with rights, provenance and as-of histories.
2. Freeze chronological Train/Dev/hidden Final; Final has at least 20 untouched dates.
3. Keep Kalshi and Polymarket separate; stratify crypto/weather/sports.
4. Freeze a strong static market-price baseline and one Track A target.
5. Admit Track B only after a Track A candidate freezes.

## Current blockers and authorization interpretation

| Blocker | Smallest next proof |
| --- | --- |
| PMB source not locally intaken | Durable exact-SHA checkout, manifest/license/dependency lock and upstream tests. |
| Adapter API not source-verified | Implement only after inspecting the pinned commit's actual hooks; no guessed class/module names. |
| Episode bytes not admitted to durable local root | Hash/size/role manifests for the four public episodes; public files remain diagnostic. |
| Exact Controller swap identities unclear | Resolve “GLM 3.5” versus repository-pinned GLM 5.3 and name the exact frontier stack, adapters and rates. |
| No formal hidden benchmark | Acquire/construct lawful as-of episodes, freeze splits and prove at least 20 untouched Final dates without opening them. |
| Dirty multi-repo state | Implement in a dedicated branch/worktree with an exact allowlist; do not commit historical private logs or unrelated dirty files. |

The user's 2026-09-28 “授权所有” admits the zero-paid local planning, public upstream ref verification and subsequent local implementation/testing within this defined scope. It is **not** interpreted as an unlimited purchase/payment authorization, permission to read sealed Final, or permission to publish externally. Paid Controller IDs, data purchases, hidden Final opening and a public release retain exact recorded gates.

## Source record

- Query/access: direct read of the official paper HTML, 2026-09-28: `https://arxiv.org/html/2602.00133v1`. Read abstract; benchmark construction; task formulation; maker/taker, fee, deterministic replay and output sections; data table; LLM logging/reproducibility; limitations. Finding: PMB provides the execution base and explicitly warns that naive backtests can mislead through selection and overfitting. Transfer limit: four public episodes illustrate the harness but cannot support a broad OOS claim.
- Query/access: direct read of the official repository/README, 2026-09-28: `https://github.com/oddpool/PredictionMarketBench`. Read installation, Agent/AgentContext, execution modes, fees, metrics, configuration, episode files and MIT license. Finding: the adapter can remain thin and use official outputs. Transfer limit: README API claims must be checked against the exact pinned source before coding.
- Query/access: `git ls-remote https://github.com/oddpool/PredictionMarketBench.git refs/heads/main`, 2026-09-28. Finding: official main resolved to `611d66941717310858683278940df21c33c406f2`. Transfer limit: a ref lookup is not a source-tree, license, dependency or runtime acceptance test.
- Local evidence: three registered independent read-only audits covering adapter integration, hidden evaluator and Simple Lane/Controller Swap. Their detailed logs are under `supervisor_harness/AGENT_LOG_PMB_*_2026-09-28.md`; two full reports are also preserved in the durable canonical repo.

The `indicator-prediction-evals` rules materially changed this replan: they made Track A prediction evidence primary, forced one causal-stage change per comparison, marked inspected periods diagnostic forever and prevented PnL from standing in for prediction validity.
