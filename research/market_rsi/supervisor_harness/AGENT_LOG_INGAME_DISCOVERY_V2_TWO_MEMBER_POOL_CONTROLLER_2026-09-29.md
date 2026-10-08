# In-game Discovery v2 two-member pool — Controller selection — 2026-09-29

## Frozen selection

Select one **global two-member active pool**. This is not a separate multi-arm
pool under each parent. The selection is scientific and plan-only: no scheduler
state/archive import, implementation, model fit, score change, data access,
network/provider call, or execution occurred.

Exact parent evidence:

- v0 scorecard SHA-256:
  `74c2f23de2ae129ead4d7def1a692d69240ac799582e54db3623865c3525de87`;
- v0 independent result-review PASS SHA-256:
  `325543498c556a1c1ba0e8e3adde42c4546c35e1b0bcffac8efbeafd3d38f983`;
- frozen v1 score-time-offset Controller log SHA-256:
  `3930ab266e1983e6cd15a3472977984961b0f08a45e246eebb8feefbb048e8ce`.

Pool-plan canonical SHA-256:
`37e65ab1e6af35a413f6b5c8a446bdc93c3c75441f467b4785ac9f06b32d5145`.

| Member | Allocation | Method family | Research parent | Comparison incumbent |
| --- | --- | --- | --- | --- |
| `InGameMarketOffsetScoreTimeDiagnostic-v1` | exploitation | `market_offset_nonlinear_prediction` | archived v0 `market_plus_state_model` negative branch | v0 `raw_market` arm |
| `InGameStateSupportGeometryAudit-v1` | exploration | `chronological_support_geometry_audit` | archived v0 `market_plus_state_model` negative branch | v0 `raw_market` arm |

The pool has one exploration slot out of two (50%). With only two indivisible
slots this is the smallest allocation meeting the requested approximately-30%
reserve without dropping exploration to zero. It does not expand total
attempts, time, data, money, or authority.

Research parent and comparison incumbent are deliberately separate. Both
questions learn from the failed state-model branch; neither rewrites that
branch into the current best prediction. Raw market remains the comparison
incumbent unless a frozen predictive replacement rule and independent review
say otherwise.

## Member 1 — frozen representation test

- Question ID: `ingame-offset-scoretime-v1-q1`.
- Original canonical question digest:
  `8cfabbfb4f93b2eddf31f61f7d4a2850b1e4dd0032661ae80ed433d1e36bfa9f`.
- Question/hypothesis/rule digest for this pool:
  `5384ef8ad35e599134ef507f058f6da01b124879d1a22ecdf72a668d848b1b81`.
- Hypothesis: fixing the market-logit coefficient at one and adding the single
  predeclared nonlinear `score_time_ratio_k4` representation recovers stable
  settlement information missed by additive linear state.
- Support: nonlinear offset has lower aggregate equal-event Brier and log loss
  than both linear offset and raw market, and lower Brier than linear offset in
  at least 3/4 folds.
- Refute: it fails either aggregate proper-score comparison against linear
  offset, or wins Brier in fewer than 3/4 folds.
- Stop: one frozen run or the first integrity/boundary/optimizer failure; no
  retry, sweep, alternative `k`, or post-score feature edit.
- Resource hint: at most 12 local fits, 10 wall minutes, 1 GiB RSS, zero network
  bytes, zero provider calls/cost, zero retries.

This member tests the **model representation/trainer** explanation.

## Member 2 — distinct sample-support investigation

Experiment ID: `InGameStateSupportGeometryAudit-v1`

Question ID: `ingame-v0-state-support-geometry-v1-q1`

Canonical question/hypothesis/rule digest:
`bd0f59c86735a2f20175b9b0784ecfe33fc51468ca3614edbdea07f454c2b8ae`.

**Question:** Is the v0 state-arm degradation primarily concentrated in
chronological check rows whose game-state vectors are unsupported by prior fit
games?

**Hypothesis:** prior-only state-space support failure, rather than absence of
state information, explains most v0 state-minus-market-model Brier harm.

This does not repeat v1. It does not fit an offset, add a nonlinear feature,
produce a candidate probability, or compete for KEEP. It audits whether the
existing negative result is an extrapolation/sample-support failure.

### Frozen method

Use only the exact v0 `checkpoint_state.csv`, `predictions.csv`, four fold
definitions, and their existing hashes. Preserve the 195 -> 193 + 2 lineage,
the exact 87-row common mask, outcomes, checkpoints, and existing per-event
state-minus-market-model Brier deltas. No row may be dropped.

For each fold independently:

1. Use the exact nine v0 state columns. Fit `StandardScaler` on that fold's fit
   rows for continuous columns only; keep possession and down indicators
   unchanged. No outcome or prediction is used in preprocessing.
2. For every fit row, compute mean Euclidean distance to its five nearest
   *other* fit rows. Freeze the support cutoff as the fit-only 95th percentile
   using linear quantile interpolation.
3. For every check row, compute mean distance to its five nearest fit rows.
   Mark it unsupported only when this value is strictly above the fit-only
   cutoff.
4. Stratify the already-frozen per-event
   `state_model_minus_market_model` Brier delta by supported/unsupported. Report
   counts, feature-range violations, means, signed contributions, all four fold
   contrasts, schedule-date/week breadth, and complete-group intervals. These
   are diagnostic summaries; they do not modify v0 scoring or KEEP/REVERT.

Let `delta_i` be the frozen state-minus-market-model Brier loss for check game
`i`. Because `sum_all(delta_i)` is positive in v0, define unsupported signed
contribution exactly as `sum_unsupported(delta_i) / sum_all(delta_i)`.

**Support the sample-support explanation** only if all hold:

- at least 10% of the 87 check rows are unsupported;
- unsupported signed contribution is at least 50%;
- unsupported mean delta exceeds supported mean delta; and
- that unsupported-minus-supported contrast is positive in at least 3/4 folds.

**Refute this exact sample-support explanation** if any decisive condition
holds:

- fewer than 5% of check rows are unsupported;
- unsupported signed contribution is nonpositive;
- aggregate unsupported-minus-supported mean delta is nonpositive; or
- that contrast is positive in at most 1/4 folds.

Otherwise record **inconclusive/credit 1 at most**. A valid support or valid
refutation may receive credit 2 after independent review because either
resolves the predeclared question. Invalid hash/mask/chronology/nonfinite
evidence receives credit 0.

**Stop:** one audit over frozen artifacts, or the first integrity, common-mask,
chronology, or nonfinite failure. Do not change `k=5`, the 95th percentile,
distance, representation, metric, or thresholds after output.

Resource hint: zero model fits, at most two wall minutes, 512 MiB RSS, zero
network bytes, zero provider calls/cost, and zero retries.

## Why this pair

The v0 artifact shows two separable facts: raw market robustly beats a fitted
market-logit LR, while the state arm's harm is fold/week concentrated and its
grouped intervals cross zero. One next question should therefore test a
nonlinear representation without re-estimating market; the other should test
whether chronological state support is too sparse for the existing trainer.

Joint interpretation is frozen before either result:

| v1 representation | support audit | Interpretation |
| --- | --- | --- |
| support | any valid result | linear representation/trainer failure is demonstrated; sample support may still modulate it |
| refute | support | v0 harm is primarily a sample-support/extrapolation problem for this state model |
| refute | refute | stronger negative evidence for stable increment in the current one-checkpoint state summary, but still not a rejection of all PBP |
| inconclusive | inconclusive | insufficient 87-game/7-week support; preserve both branches and do not tune automatically |

The first member can propose a new diagnostic incumbent only through its frozen
raw-market comparison and independent review. The second member never changes
the incumbent; it only determines whether to retain, stop, or redesign the
sample-support branch.

## Boundaries

Both members remain repeatedly inspected opened-Train Discovery. Historical
PBP event time is not proof of real-time publish/receive availability. Dev and
Final remain closed; no external acquisition, network, paid provider,
publication, promotion, PnL, formal OOS, or cross-task numerical comparison is
authorized. Scheduler archive import and state mutation are explicitly outside
this scientific selection.
