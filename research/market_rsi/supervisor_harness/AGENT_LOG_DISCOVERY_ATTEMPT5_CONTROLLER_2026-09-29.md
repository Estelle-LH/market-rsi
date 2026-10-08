# Discovery Attempt 5 Controller — MarketRecencyWeightedCompositeDispersion-v5

Time: 2026-09-29.  Status: **one recipe frozen before implementation or
Attempt-5 scores**.  This is adaptive opened-Train Discovery, not untouched
OOS evidence.

## Evidence to choice

Attempt 4 is REVERT.  Its candidate scores `0.20442236 / 0.59708031` versus
market `0.20553336 / 0.59845093`, but loses to the Attempt-3 incumbent by
`+0.00056577` Brier and `+0.00124354` log loss.  All-prior support slightly
improves fold 1 versus Attempt 3, while folds 2–4 all worsen.  Increasing Kish
fit rows from about 32–34 to 42–44 therefore added more regime bias than useful
variance reduction.  I will not sweep window length, decay, penalty or sign.

The next problem is whether a distinct causal family adds information beyond
the retained recent path composite.  The existing weighted probability
dispersion columns are a pre-existing, decision-time measure of within-window
market disagreement/instability, not another location or signed-path feature.
Exactly one candidate is selected; count, size and staleness families are not
tested in this attempt.

Attempt-4 artifact hashes are:

- exclusions `5a024887952e3876ad8f7e4dc03fc0c343193074d97bc8025a622d08b3aeb4ed`;
- inputs `cced501566428aa3011d6e301b3fdb18c5368a2318840ec3f766d87bb91094f4`;
- manifest `74569b89cc3497d732f0fabb1a2236584999d4a7e704955db7102ef5c62d831b`;
- pre-score lock `c42702a47b4a181349edceeb493265097c9766d827447a8cae798dd3aec7e173`;
- predictions `ba9885f8d67c9c20838dabd251354d4803afb9ff90c39f990f3c0521d7c8c128`;
- scorecard `407cf8f393a0196a3893b1d574e714a2a3b6a448084cd7b42dcd4fd63b000643`;
- staleness `3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e`.

## Frozen candidate

Name: `MarketRecencyWeightedCompositeDispersion-v5`.

Preserve the exact source, 195/194/87 denominator and common mask, sole tie
exclusion, orientation, 15-minute cutoff, inclusive 600-second staleness gate,
22 + 4x5 folds, proper scorer, calibration report, seed-23 complete-day and
observed-week resampling, and the exact Attempt-3 three-week cohorts and event
weights `0.25/0.50/1.00`.  Reuse Attempt 3's unweighted, selected-fit-only
market scaler, price-path residualization and standardized composite `z_c`
bit-for-bit.

Select the three exact frozen feature names
`trailing_{15,60,240}m_weighted_std_home_probability`.  Define

```text
v_raw = mean(std_15m, std_60m, std_240m)
```

On selected fit rows only, form `B=[1,z_market,z_c]` and compute
`gamma=lstsq(B,v_raw,rcond=1e-12)`.  Require rank three.  Apply the same gamma
to selected, older-diagnostic and check rows.  Standardize the residual with
its selected-fit mean and population standard deviation.  If the fit standard
deviation is at most `1e-8`, set `z_v=0` everywhere without dropping rows.
This makes the new family linearly orthogonal on fit to both market level and
the incumbent path composite; it does not claim nonlinear independence.

Fit exactly two unconstrained residual coefficients on the exact Attempt-3
selected rows and weights:

```text
eta = market_logit + w_c*z_c + w_v*z_v
J = sum_i a_i*NLL(y_i,eta_i)/sum_i a_i + 0.5*(w_c^2+w_v^2)
```

Use float64, lambda one, zero initialization, analytic gradient and L-BFGS-B
with `maxiter=1000`, `gtol=1e-8`, `ftol=1e-12`; require success, finite values
and gradient infinity norm `<=1e-6`.  No intercept, market slope, sign
constraint, clipping, fallback, sweep, retry or post-score edit.  At both
coefficients zero, predictions must equal market bit-for-bit.

Fit exactly four candidates.  Bind a passing Attempt-4 result review before a
real fit.  Archive market, ordinary, calibration, full offset and Attempts
1–4 with zero refits.  Use nine arms on the identical mask.  KEEP replaces the
current best only if the existing market/ordinary aggregate and 3/4-fold
Brier gates pass and the candidate beats archived Attempt 3 on aggregate
Brier and log loss by more than `1e-12` and in at least three of four fold
Brier comparisons.  Attempt 4 remains a branch, not the incumbent.

Report, without tuning or gating, exact dispersion formula/name resolution;
raw/residual variance; rank/singular values; inactive state; Pearson/Spearman
correlation with market logit and `z_c`; selected-fit orthogonality; weighted
and unweighted `z_v*(y-p_market)` overall and by week; both coefficients and
probability correction; fold/date/week deltas against every archive.  Fail
closed with a structured fresh-ID receipt for identity/source/archive/review
drift, feature/rank/nonfinite/causality/count/mask/objective/optimizer/
probability/control-refit failures.  Phase flags must remain truthful.

Established principles are prior-only transforms, identical paired masks,
proper scores and dependence-aware grouped reporting.  The three-week window,
equal dispersion average, residualizer, lambda, optimizer and KEEP thresholds
are project choices.  The unvalidated hypothesis is that recent probability
dispersion contains incremental settlement information beyond market level
and signed price path.  Selection explicitly used repeatedly inspected,
label-dependent Attempt-4 results and prior branch history.
