# MarketOffsetRidgeLogistic-v1 real Train result — independent review

Review completed: `2026-09-29T17:35:21Z`.

## Verdict

**PASS. No P0 or P1 finding.** The completed artifact is internally bound,
reproducible from its persisted prediction rows and frozen source, and correctly
resolves to **REVERT**. `MarketOffsetRidgeLogistic-v1` substantially improves on
the ordinary LogisticRegression reference, but it is worse than the
decision-time market on both proper losses and in every chronological fold.

This is repeatedly inspected, opened-Train Discovery evidence. It is not
untouched OOS evidence, a promotion result, a profitability result, or a claim
of generalization beyond the 2025 NFL seed domain. The review did not retrain a
model, run another real experiment, open Dev/Final, use a network or provider,
or change experiment code. The only file written by the review is this log.

Reviewed result:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-offset-ridge-20260929-02`

## Artifact and source integrity

The result directory contains exactly seven files. Independently recomputed
SHA-256 values are:

| File | SHA-256 |
| --- | --- |
| `exclusions.json` | `2d6d6327a59f77ac20b945fe7eece2c982e16da671aabf8fc96f48a4573f72a9` |
| `input_receipts.json` | `79a0d53c9bd1b78a3e4059cd2aa7e6c9f7100eef1a40a05877e10d5a6ce82cd9` |
| `manifest.json` | `2296835ec561858383750cba8d81124daf479de1caa288908d98503a7b93acc6` |
| `pre_score_lock.json` | `264341f66c382001c86a01ab45835b03780b06e926d79176b141d6c86d3492a1` |
| `predictions.csv` | `d917a1980bc0b4621ee9ab0cdc6672b47e58cbea0ae4ed335c952d40dd51288c` |
| `scorecard.json` | `276423d4cfe97ca1198f6f95a420036bf53b7f756bdd021d691951bc4b367907` |
| `staleness_inventory.json` | `3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e` |

Every manifest-to-artifact binding matched. The pre-score lock's bindings to
the input receipts, exclusions and staleness inventory also matched. The input
receipts bind the following current files exactly:

| Binding | SHA-256 |
| --- | --- |
| Offset runner | `6b788cf2070cc98ae8aca03d825d7f84df8f14beb1e08ad9ec88117f294b974f` |
| Parent runner | `1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b` |
| Parent tests | `6c349018fb28abcfcea825bec5cb8c9e2702d46e15712e30c9e66d5fb9785927` |
| Proper scorer | `64165cbceb4bcba6d03b6b42402ea7a47790c9a57f9280b15bfe2fe57becc06b` |
| Probability contract | `7ba4a32d3c3a2ab80ac17ca6c18ea29fe864b958de8a81ac2be59dba121e9d74` |
| Controller proposal | `7345349cb0560a23e447b1e89b83e1c3de49adec6b1ada967a5a909ff1ab1314` |

The current focused test source is
`409fd88d93c59b5d0bb25a1765471ad9249c0a5872cc77d31e69922a77fd0f41`,
matching the implementation log. The runtime receipt is the persistent local
CPython 3.12.3 environment with NumPy 1.26.4, SciPy 1.14.0 and scikit-learn
1.6.1. The source manifest and cohort hashes independently match
`429a0ef100ade70f7e7b7f5862c39f42adffd7dcdaaddf35c73c88b60f80074f`
and `ba07b5535917f6ccfd4ddb5eadb53f6428b02bcc238595adac42894643d37885`.

For all 195 cohort events, all four recorded source file hashes matched:
**780/780**. Independently decompressed raw catalogs matched their stored and
raw hashes for **195/195** events, and every trade manifest matched its trade
window, identity and closed Train boundary. Re-materializing without fitting
reproduced all **194/194** materialized-event receipts exactly.

## Population, staleness, chronology and controls

- Frozen source denominator: **195 events on 42 schedule dates**.
- Materialized: **194/195**. The sole exclusion is source ordinal 53,
  `2025_04_GB_DAL`, schedule date `2025-09-28`, whose result prices are
  `[0.5, 0.5]`; `unresolved_outcome` is the correct code.
- Materialized-key digest independently reproduces
  `59128473ae6c50b4acd2436ac18478d4fcd7dbd96ee887eb5ce2ae77ddfc72bd`.
- The inclusive 600-second common staleness gate checked all 194 binary rows.
  Observed ages were 0–313 seconds, with zero violations. The gate was
  therefore nonbinding and did not alter the parent comparison mask.
- The four chronological folds independently reconstruct as fit/check counts
  **107/26, 133/16, 149/28 and 177/17**, with zero unavailable fit labels.
- The check population is exactly **87 events / 20 complete source schedule
  dates / 7 observed NFL game-week clusters**. The common mask hash is
  `eddf8cc9509a3121a884143e9c9d24e2e85c72283957f446b1b44fd0bfc341cb`.
- Market and ordinary rows reproduce the frozen parent artifact exactly:
  identity and order match on 87/87 rows, market probabilities are byte-value
  equal after CSV parsing, and the maximum ordinary probability difference is
  0.0 (required tolerance `1e-10`).

The candidate probabilities were independently reconstructed from each
persisted 18-parameter vector, prior-fold StandardScaler and market-logit
offset; maximum absolute difference from `predictions.csv` was 0.0. Independently
recomputed objective values and gradients match the scorecard. All four
optimizers report success/status 0, finite parameters and objectives, and final
gradient infinity norms below `1e-6`:

`4.2853588791240405e-08`, `5.949916739161898e-08`,
`2.3934130607972115e-08`, `7.568208814159871e-08`.

The earlier `-01` directory is preserved as a technical failure. It contains
only exclusions, input receipts, a pre-score lock, staleness inventory and
`failure.json`; it contains no predictions, scorecard or completed manifest.
Its receipt correctly says `fit_started=true`, `scoring_started=false`, and
the error is the pre-score mask-order implementation mismatch. It is not a
scientific result and contributes no KEEP/REVERT observation.

## Independently reproduced scorecard

All row-level Brier and bounded log-loss values, aggregate values, per-fold
values and OLS outcome-on-probability calibration diagnostics were recomputed
directly from the 87 persisted prediction rows.

| Forecast | Equal-event Brier | Equal-event log loss | Calibration slope | Calibration intercept |
| --- | ---: | ---: | ---: | ---: |
| Decision-time market | 0.20553336372767944 | 0.5984509292283796 | 1.0155134726661597 | -0.029218480860792484 |
| Ordinary LogisticRegression | 0.23560472453952527 | 0.6759482937171853 | 0.6366611551135252 | 0.17273454690115536 |
| MarketOffsetRidgeLogistic-v1 | 0.20945065421878312 | 0.6082677941274733 | 0.9385363221033207 | 0.014390690942336914 |

Candidate deltas use `candidate minus reference`; negative loss is better:

- Versus market: **+0.003917290491103701 Brier** and
  **+0.009816864899093742 log loss**.
- Versus ordinary: **-0.02615407032074219 Brier** and
  **-0.06768049958971191 log loss**.
- Candidate Brier fold wins versus market: **0/4**
  (`false, false, false, false`).
- Candidate Brier fold wins versus ordinary: **3/4**
  (`true, true, true, false`).

Thus offset anchoring plus strong residual shrinkage repaired much of the
ordinary replacement model's damage, but did not reveal incremental predictive
information beyond the market. This diagnoses this fixed recipe; it does not
prove the non-market features contain no usable signal or that the branch has
no future research value.

## Corrected grouped inference

The grouped procedure was independently reimplemented from the CSV without
calling the runner's interval helper. Each draw samples complete observed units
with replacement, pools every event in the selected units (including all games
in repeated units), and recomputes the equal-event mean loss delta. Seed 23 and
1000 replicates reproduce every stored interval exactly.

Key 95% percentile intervals for candidate minus market are:

| Resampling unit | Brier delta interval | Log-loss delta interval |
| --- | --- | --- |
| Complete source schedule date (20 units) | `[0.0008447572935078003, 0.007129935098859866]` | `[0.0015841786527093012, 0.018286087395410912]` |
| Observed NFL game-week cluster (7 units) | `[0.0009960367258132492, 0.006468002035828517]` | `[0.002113085828817663, 0.016272425127715266]` |

The 20 schedule-date event counts independently match the scorecard. Observed
week counts are `13/14/14/15/14/16/1` for weeks 08–14. Week 14 is a one-event
partial right-edge cluster and is explicitly labeled as a secondary sensitivity,
not a complete-week claim; retaining it preserves the frozen 87-event primary
denominator. The complete-schedule-day analysis is the clean corrected analysis
requested for the equal-event estimand. These intervals are descriptive under
repeated Train inspection, not formal OOS confidence guarantees.

## Decision and research boundary

The preregistered rule requires both aggregate proper losses below both
references and at least three of four Brier fold wins against each reference.
The candidate beats ordinary on both aggregate losses and gets 3/4 Brier fold
wins, but it loses both aggregate losses and all four Brier folds to market.
The exact decision is therefore **REVERT**.

REVERT changes only the current-best prediction: the decision-time market
remains current best. The offset candidate branch and the prior HGB branch are
both retained with their code, artifacts and lessons. Ordinary LogisticRegression
remains an ordinary reference, not `Strong-Baseline-1`.

The lock correctly separates:

- literature-supported evaluation principles: strictly prior fitting,
  prior-row preprocessing and dependence-aware grouped resampling;
- project choices: the 15-minute cutoff, 22 + 4x5 folds, 600-second limit,
  lambda 1, fixed trainers, seed 23 and 1000 resamples;
- the still-unvalidated hypothesis: residual features can improve settlement
  prediction beyond the decision-time market.

Artifact flags and source receipts consistently show Route-Dev false, sealed
Final false, external fetch false, paid provider false, provider cost `$0` and
promotion false. Static import review found no network or provider client in
the runner. The synthetic test explicitly blocks sockets; these checks support
the declared boundary but do not convert opened Train into independent OOS.

Unsupported after this PASS: promotion, formal OOS improvement, profitability,
executable-price performance, generalization beyond the 2025 NFL seed domain,
or a uniquely identified causal contribution from market anchoring versus
ridge shrinkage. A past-only market-calibration baseline remains the appropriate
next diagnostic for separating calibration gain from incremental feature gain.

## Verification run

Canonical persistent-runtime unit command covering the offset and parent
modules passed **24/24** tests in 0.598 seconds. Coverage includes the analytic
gradient, zero-residual market recovery, penalty semantics, 600/601-second
fail-closed behavior, canonical mask repair, parent control parity, optimizer
gates, corrected unequal-cluster arithmetic, partial-week disclosure, exact
KEEP/REVERT rules, no-network synthetic execution and unchanged parent tests.

The review applied the local `indicator-prediction-evals` evaluation gates for
same-row proper scoring, strictly prior fitting, dependence-aware inference and
the mandatory distinction between reused Train Discovery and untouched OOS.
