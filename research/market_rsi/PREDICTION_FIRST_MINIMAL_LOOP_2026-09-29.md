# Prediction-first minimal loop — 2026-09-29

## One objective

Run the smallest auditable self-evolving **prediction** loop before adding more
governance or monetization machinery:

```text
opened historical as-of rows
  -> propose one prediction change
  -> implement one candidate
  -> emit label-free probability journal
  -> score once on Dev in a separate evaluator
  -> KEEP or REVERT
  -> write bounded aggregate memory
```

This first milestone is synthetic/local and proves orchestration only. It does
not claim prediction improvement and does not open Final.

## Reuse instead of rebuilding

| Need | Existing component to reuse | Narrow missing piece |
|---|---|---|
| Source/order audit | `raw_audit.py`, `historical_materializer.py`, `time_series_split_policy.py` | settlement-outcome row/cutoff contract |
| Causal features | `historical_grid_features.py`, `historical_recorded_features.py` | diagnostics residualized against market probability |
| Prediction | `learner.py`, `prediction_stream.py` | current local isolated execution adapter |
| Objective | `objective_contract.py` already names `event-resolution-probability-v1` | materializer and proper-score scorer |
| Split lifecycle | `data_lifecycle.py` | bind score/KEEP/REVERT to consumed Dev ID |
| Evidence | `market_rsi.Journal` | one small parent-lineage record |
| Sandbox pattern | `local_b_container.py` | candidate/evaluator filesystem separation |

`taking_replay.py` and PMB are parked. Execution/PnL is a later experiment
after prediction freezes.

## Three implementation tracks

### 1. Probability contract and scorer

Freeze one row schema:

```text
event_id
market_id
cutoff_ms
feature_available_ms
market_probability
outcome_available_ms
outcome
```

All related markets for one event stay in one split. A training outcome must
have become available before a later evaluation cutoff. Baseline and candidate
must cover exactly the same complete rows. The trusted scorer reports
equal-event candidate and market Brier, candidate-minus-market Brier, bounded
log loss and paired delta, calibration, reliability bins, coverage,
event/date breadth, concentration and event/date-block intervals.

### 2. Isolated prediction execution

Combine the sequential label-free protocol from `prediction_stream.py` with
the current local-container hardening pattern:

- pinned image, no network, non-root user, read-only root and no capabilities;
- candidate source and public as-of rows only;
- Dev/Final outcomes, future rows, scorer source and evaluator files never
  mounted;
- one row becomes visible only after the previous prediction is durably
  committed;
- terminate the candidate before host-side scoring;
- keep evaluator lifecycle state outside the candidate filesystem.

Until a real container isolation canary passes, mock/fake-runner tests prove
only protocol logic, never hidden-evaluation security.

### 3. KEEP/REVERT lineage

Use one append-only parent chain, not the full historical study framework:

```text
frozen parent
  -> proposal + changed-stage hash
  -> candidate source hash
  -> prediction journal hash
  -> one-shot Dev score receipt
  -> KEEP or REVERT
  -> bounded aggregate memory
```

KEEP advances the parent only under the preregistered Dev rule. REVERT leaves
the parent unchanged and preserves the failed candidate. Next-round memory
contains aggregate metrics and failure facts, never row-level Dev outcomes.
Consumed Dev may later become Train through `DataLifecycle`; Final never does.

## First closed-loop acceptance

Use synthetic binary events and two rounds:

1. a candidate improves the predeclared proper score and becomes the parent;
2. a second candidate fails and rolls back;
3. restart preserves parent, used IDs, score receipts and memory;
4. future rows and outcomes remain invisible to candidate execution;
5. Final remains sealed and unreachable;
6. no PMB, network, provider, payment, release or real data is involved.

After independent attack review, the next decision is whether an already
opened, locally resident historical dataset can exercise the same loop as a
non-promotional diagnostic. Real data admission and untouched Final remain
separate gates.

## Promotion boundary

Formal evaluation freezes candidate, market baseline, cutoff extraction,
split, scorer and data manifests before Final. Final runs once outside the
agent process/filesystem, covers at least 20 untouched dates plus sufficient
independent events, and sends no feedback into research memory. Only a frozen
prediction that passes proper-score gates may enter a separate execution/PnL
study.

