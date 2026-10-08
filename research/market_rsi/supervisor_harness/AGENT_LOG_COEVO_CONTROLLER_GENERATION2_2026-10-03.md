# Opened-Train Controller — generation 2 — 2026-10-03

## 2026-10-03 19:36:17 UTC — verified evidence to descendant choice

Author `/root/coevo_controller_20261003`, GPT-6 family, exact serving version
unknown. Timestamp observed using clock tool, not an estimate. No fits or new
data/network/provider access by Controller. Generation-1 records stay frozen.

First received A2 feedback, SHA
`812250d571f956b58ae7c6768be35cf1b9a6dd182d25372445170fd24f108fbc`.
It is valid four-fit/87-row evidence: Brier worse than raw market by
`+0.00023879815313244062`, log loss very slightly better by
`-0.000007924783348473572`; one raw-Brier fold win and both grouped intervals
cross zero. Beta is consistently positive (`0.083–0.111`), but coefficient
stability and beating ordinary/state do not imply an incremental market edge.
Only fold 3 improves both scores. This is not a failed trainer execution.

Then received independently verified A1 feedback, SHA
`812cd7b0adba76e7de15b5216dbf9d9bffb0e356c42e8cac333a57adb65b7a0f`.
It is valid four-fit/87-row evidence: Brier worse by only
`+0.00000595662579408819`, log loss better by `-0.00012380721376853068`;
two raw-Brier fold wins, both grouped intervals cross zero. Betas consistently
negative (`-0.0465–-0.0692`). Folds 2/3 improve but 1/4 worsen. I did not read
its unreviewed result before the verified packet arrived.

Decision: neither replaces raw-market incumbent. The exact NLL freshness and
pressure recipes are refuted under the frozen rule. Valid negative research
credit is evidence-routing information, not a Brier bonus. Both broader
questions can retain an exploration slot for a different stated test; REVERT
does not erase either code/result. This is evidence-led, not top-three ranking.

I choose `InGameMarketFreshnessBrierOffset-v2` as the sole remaining attempt.
Actual parent is A1, runner `d7e16a2...`, not raw market or v0 state. The only
scientific component changed is the candidate training objective: identical
age-by-market-logit feature, fold-fit standardization, market coefficient one,
no intercept and penalty 16, but minimize Brier instead of Bernoulli NLL.
Analytic-gradient L-BFGS-B is a bounded implementation of that changed trainer.

Why this choice: A1 is much closer to the market on Brier than A2 and already
has a modest log-loss gain, while both expose divergence between NLL fitting
and the primary Brier target. Testing objective alignment is a smaller, more
discriminating follow-up than combining feature families or tuning ridge on
the inspected checks. Negative first-generation results caused this choice;
the final algorithm was not frozen with generation 1.

Numeric penalty 16 remains fixed, but loss-unit change also changes effective
shrinkage. Even an improvement would not identify target alignment alone.
Brier in logit parameters is not claimed globally convex or globally optimized.
This candidate has one start, four fits, no grid/retry/post-score tuning.

The score judge stays unchanged. Save A1's exact 87 frozen parent predictions
as an additional paired arm, including fold/date/week deltas, without replacing
raw/ordinary/v0state KEEP comparators. Source/hash/key/label drift or optimizer
nonconvergence is terminal invalidity, not scientific refutation. Full195
denominator and193 materialized coverage must remain accounted for.

Exact contract: `COEVO_GENERATION2_CONTRACT_2026-10-03.json`. One new runner and
its synthetic test are allowed; all old candidates, scorer, scheduler, worker,
contracts, raw data and artifacts are protected. Supervisor freezes new source,
memory and reviewed execution binding before any real fit. This is a C change
under normal feedback accumulation, not an R-policy self-modification, H
improvement or matched self-evolution advantage. No Dev/Final, new data, paid
provider, publication or promotion is proposed.
