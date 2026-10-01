# In-game pre-anchor market momentum residual audit v3 — implementation — 2026-09-29

## Status

Implemented scheduler-v2 batch `market-rsi-ingame-discovery-v3-20260929-02`
final member `attempt-04`, candidate
`InGamePreAnchorMarketMomentumResidualAudit-v3`. No real audit was executed,
no real trade-derived signal or score was opened, and scheduler state was not
changed. Frozen v0/v1 runners, source data and prior artifacts were not edited.

Controller source:
`AGENT_LOG_INGAME_DISCOVERY_V3_GENERATION2_TWO_MEMBER_POOL_CONTROLLER_2026-09-29.md`,
SHA-256
`4186a3554b7f7aed50596123c135943dbf986d5e39b84fe507fac91c6e04e986`.

Frozen identifiers:

- question ID: `ingame-pre-anchor-market-momentum-residual-v3-q1`;
- question digest:
  `f82528a6d379831c10e9d98979d29fc9cb77037fd5749ad9f59f041214b1ddfa`;
- hypothesis digest:
  `d581adb57a3a6d554bd23248d9325c8fb0d2082db8c73c74fd944f616b5e9d6d`;
- rule digest:
  `d1a3369bbedc9c9c01848986ecf7c387bfeef6c124e9d1e85343ab19e68f2270`;
- generation-2 plan digest:
  `c10ed553121ac9c0da123138a4e3d7b2f03979cf7143dc7092b8d8dad513a92c`.

The runner records an exact attempt-04 branch object with exploration
allocation, generation 2, raw-market comparison incumbent, archived-v0
research parent and non-authoritative local-analysis resource hint. Its
canonical digest is
`c033d747aedf039e8d1369ed6fd9ca207d93b18947193f99a62129c76d0e5433`.
Selection state and journal head are bound at
`69ad82c5938b4b8793cd29e0af22471658315d75737959c77cc6ced48e2b8627`
and
`cb737d39ce98748f0cced47b73fcddff8c9df993a3941e15b4bf6b0047efbb06`.

## New files and frozen hashes

- runner:
  `research/market_rsi/experiments/nfl_ingame_pre_anchor_market_momentum_residual_audit.py`
  — `a99cf9889ad1e463e8ae2294711cb0b1ad94735be933f2e02ba99cdb49ca26b9`;
- tests:
  `research/market_rsi/experiments/test_nfl_ingame_pre_anchor_market_momentum_residual_audit.py`
  — `fc5cce906049608e0e842e02267170d8c9c830c11eeb40a26f301b483eebd231`.

## Implemented data and time boundary

The runner validates the exact seven-file v0 artifact, all source/PBP
receipts, the original `195 -> 193 + 2` lineage and the exact 87-game v0 check
mask before scoring. For each check game it additionally verifies the catalog,
compressed raw event, trade manifest and trade-window hashes against the frozen
v0 materialization receipt and reuses the exact v0 market/token home-away
orientation.

For integer-second trades:

- `p_now` is the size-weighted home probability at the latest fill second
  strictly before `floor(decision_epoch)`;
- reference cutoff is exactly `floor(decision_epoch) - 120`;
- `p_ref` is the size-weighted home probability at the latest fill second
  strictly before that reference cutoff;
- reference age is `reference_cutoff - reference_fill_second` and must be in
  `(0, 300]` seconds;
- `p_now` and its fill second must exactly reproduce the v0 prediction and
  materialization receipt;
- absent/stale reference coverage fails the entire audit. No check row is
  dropped and no probability is imputed.

The frozen signal is
`logit(clip(p_now,1e-6,1-1e-6)) - logit(clip(p_ref,1e-6,1-1e-6))`.
Raw probabilities remain unchanged in artifacts; clipping is used only for the
logit transform. Signal construction has no outcome/label input.

## Frozen analysis and decision

On the exact 87 rows the audit reports Pearson and tie-aware Spearman against
`y-p_now`, mean `signal*(y-p_now)`, and mean
`signal*(y-p_now)*p_now*(1-p_now)`, both in aggregate and for all four frozen
folds. Schedule-date and observed-week bootstraps use seed `20260929`, 10,000
complete-group draws per metric/group, and recompute pooled equal-event means.
Valid and undefined draw counts are explicit; this single-regime audit has
zero undefined draws when inputs are valid.

Support/refute/inconclusive rules are copied exactly from the Controller.
Integrity and coverage gates run before scoring. The runner performs zero model
fits, emits no candidate probability, has no KEEP/REVERT transition and cannot
change the task-local raw-market incumbent. A complete result awards zero
credit pending independent review.

Artifacts are atomically hash-bound as input receipts, pre-audit lock,
per-event audit, scorecard and manifest. A terminal error writes a failure
receipt and the fresh output ID cannot be reused.

## Research-source handling

No method choice was made during implementation. The lag, staleness rule,
orientation, signal, diagnostics, resampling and decision rule were already
frozen by the Controller, while the market materialization and probability
orientation reuse reviewed local code. Accordingly no live literature search
was used to alter the recipe. The implementation follows the existing
indicator-evaluation principles of strict causal time ordering, immutable row
mask, raw-signal evaluation before prediction fitting and complete-group
inference; the 120/300-second values remain project parameters rather than
literature consensus.

## Verification actually run

Pinned Python runtime:
`/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python`.

Focused suite:

```text
python -m unittest -v \
  experiments.test_nfl_ingame_pre_anchor_market_momentum_residual_audit

Ran 11 tests in 0.252s — OK
```

Frozen v0, prior-play audit and new runner regression:

```text
python -m unittest -q \
  experiments.test_nfl_ingame_win_probability_train_diagnostic \
  experiments.test_nfl_ingame_prior_play_success_residual_audit \
  experiments.test_nfl_ingame_pre_anchor_market_momentum_residual_audit

Ran 30 tests in 4.650s — OK
```

Runner and tests passed `py_compile` with bytecode redirected to
`/private/tmp`. Both new files passed whitespace diff checking. Tests cover
strict-exclusive current/reference cutoffs, same-second size weighting,
120-second lag, exact 300/301-second staleness edges, missing reference
coverage, endpoint logit-only clipping, label independence, alignment formulas,
grouped bootstrap draw accounting, all three decisions, actual v0 hash/mask
preflight, scheduler digests, persistent output guard, zero-fit/no-network
static checks, synthetic end-to-end artifacts, and terminal failure receipts.

## Boundary and next gate

- Real audit executions: `0`.
- Prediction-model fits: `0`.
- Scheduler mutations/claims: `0`.
- Network bytes, provider calls and cost: `0`.
- Dev/Final access: `0`.
- Candidate emission, incumbent mutation, publication and promotion: `0`.

The next step is an independent pre-execution review of the exact runner/test
hashes above. Any byte change requires new hashes and review. Only a separately
bound one-shot execution may open the real result; no alternate lag, retry or
post-score tuning is permitted.
