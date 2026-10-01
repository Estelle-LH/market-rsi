# In-game predictive autonomy — final Controller memory

Date: 2026-09-29  
Status: post-budget scientific memory; no attempt selected, authorized, implemented, or executed

## Bound evidence

- Attempt-03 independent result review:
  `research/market_rsi/agents/AGENT_LOG_INGAME_PRIOR_PLAY_SUCCESS_UNCERTAINTY_STRATIFIED_OFFSET_V4_RESULT_INDEPENDENT_REVIEW_2026-09-29.md`,
  SHA-256 `69e5578a55670fb5327979a9e5dc30cedbbcfe2660d763f234489738d9d4f078`.
- Generation-1 Controller record SHA-256
  `a6259940439dff5e6c86a0d1c4de73e634608bb7b3d82804731ac103674e4efb`.
- Generation-2 Controller record SHA-256
  `db9481637ab55dec104bdd9cde4a0199022ea404781e60bec9563c05aad94eb8`.
- Attempt-02 independent result review SHA-256
  `e234818638de242efeda2bef08e8d35727e18793af3b4d642b0e7fb4922be4ae`.

## Decision update from attempt-03

Attempt-03 was a valid 87-row prediction result, not an infrastructure failure.
Its uncertainty-stratified prior-play-success offset was essentially tied with
raw market but missed the frozen rule: candidate Brier was worse by
`+0.0000011584100419181897`, candidate log loss was better by
`-0.00003776704521940566`, raw-market Brier wins were only `1/4`, and both
date- and week-grouped candidate-minus-raw Brier intervals crossed zero
(`[-0.0000186924113837201, +0.00002244687138296532]` and
`[-0.000017720979660957808, +0.000022282446075536034]`). Improvements over the
ordinary market-only and v0 state parents therefore do not establish an
increment over the stronger raw-market comparator.

The exact `InGamePriorPlaySuccessUncertaintyStratifiedOffset-v4` branch is
`REFUTED / REVERT / stop`. It must not consume another active slot through
threshold, ridge, interaction, or subgroup retuning on these inspected 87
rows. If separately recorded by the scheduler, this is a valid negative
resolution consistent with research credit 2; this memory does not write that
credit or mutate scheduler state. The broader proposition that causal
prior-play or play-by-play information can never help is not established.

## Research active pool after budget close

The comparison incumbent remains separate from all research parents:

- task-local comparison incumbent: raw-market prediction artifact SHA-256
  `89a8ef92c9cf4844b99e0136c51a1f8b896cdd66afcd23e8b8a23499859ffc7f`,
  Brier/log loss `0.14195252900323282 / 0.4296707847132428`;
- eligible archived research lineage parent: v0 market-plus-state negative
  branch SHA-256
  `c40b1df57588b296e72ffe5b220c91aa0dd16d31ef1c573bdb4b0e7c0d72f79d`.
  It may parent orthogonal questions, but it is not the incumbent.

The research pool contains exactly two eligible question slots, neither of
which is an authorized attempt:

1. **Market-freshness interaction.** Test whether the age of the latest causal
   prior market fill changes how strongly the current market logit should be
   trusted. This is a data/interaction question and is the recommended next
   experiment below.
2. **Coarse causal state residual.** Test one predeclared, low-dimensional,
   monotone residual basis over causal possession/down-distance/field-position
   state with the raw-market logit held as a fixed offset. This remains a
   model-stage backup question only; it must not reuse the stopped score-time
   ratio, support-geometry, identity-calibration, or prior-play-stratification
   routes.

There is no third member: adding one only to fill capacity would not be an
evidence-led allocation. Attempt-01 remains invalid/cooldown because three
required fit games lacked the frozen 120-second/300-second coverage;
attempt-02 and attempt-03 remain exact stop routes.

## Recommended next prediction experiment, for a separately budgeted batch

`InGameMarketFreshnessInteractionOffset-v1`:

- Before any fit, prove the latest-prior-fill age feature exists causally for
  all 193 materialized games; otherwise terminate as invalid with zero fits.
- On the unchanged 87 evaluation rows, fit only
  `logit(q) = logit(p_market) + beta * z_age * logit(p_market)`, with no
  intercept, raw-market coefficient fixed at one, fit-only standardization of
  `z_age`, fixed L2 penalty 16, four deterministic outer fits, one process and
  thread, and no grid, retry, or post-score tuning.
- Emit paired probabilities for candidate, raw market, frozen ordinary
  market-only, and frozen v0 state parent on the identical mask/folds/labels.
- KEEP only if candidate aggregate Brier and log loss beat every comparator,
  candidate beats raw and ordinary Brier in at least `3/4` folds, and both
  date- and week-grouped 10,000-draw paired candidate-minus-raw Brier upper
  bounds are below zero. Otherwise REVERT and stop the exact route.
- Treat fill age as historical event-clock evidence only; do not describe it
  as publish-time, receive-time, or real-time availability.

This recommendation grants no execution, Train, network, provider, Dev/Final,
cost, scheduler, or promotion authority.

## Unsupported claims

- Attempt-03 does not improve the raw-market incumbent and does not justify an
  incumbent update; its slight log-loss gain cannot replace the frozen Brier
  and paired-stability rule.
- The completed work does not show that all prior-play/PBP information is
  useless, nor does attempt-01's coverage failure scientifically refute
  pre-anchor momentum.
- It establishes no untouched out-of-sample, Dev/Final, deployment, PnL,
  provider-availability, receive-time, or real-time result.
- Research credit is evidence-routing metadata, not model reward, and cannot
  enter Brier scoring, KEEP/REVERT, or independent validation.
- No threshold, penalty, feature family, or route may be selected by further
  inspection of the same 87 outcomes.
