# `InGameMarketOffsetScoreTimeDiagnostic-v1` independent result review — 2026-09-29

## Verdict

**PASS. P0: none. P1: none.**

The sole completed artifact is internally hash-consistent and reproduces the
predeclared decision `SCORE_TIME_K4_HYPOTHESIS_REFUTED`.  The exact tested
representation, a fixed market-logit offset model augmented with
`score_time_ratio_k4`, does not improve over the otherwise identical linear
state offset and is materially worse than the unfitted raw-market diagnostic
incumbent on this opened-Train cohort.  The raw-market incumbent is unchanged.

This is prediction-representation evidence from already inspected Train data.
It is not untouched out-of-sample, promotion, trading, PnL, or evidence that
the broader play-by-play/game-state family is useless.

## Frozen scope and lineage

Reviewed artifact, read-only:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-ingame-market-offset-score-time-train-diagnostic-20260929-01`

All seven result files existed and their bytes matched the expected and
cross-linked SHA-256 values:

| file | SHA-256 |
|---|---|
| `manifest.json` | `b9840bc2fe6258be40f61800fa212e157821230bd3e5c0af6bc8bf43f537ab4b` |
| `pre_score_lock.json` | `4e578c6cdd94297ff8ab3753fb36f384b2db9bbe46a442d6f3f7f54c45f2a5fa` |
| `scorecard.json` | `2301883843090a09326f03403be9564d6fbeddd962c3cc71789eba7b5155bcaf` |
| `predictions.csv` | `f79a3f61a8bdcb71bcdf0f673bb87cfffe5a600a52ed523ec854978fa01fda54` |
| `input_receipts.json` | `6f8b4c196f82fe7e9bb4ab75952eb66aaecdfb96040ff22beb2b71738bd1ebe8` |
| `exclusions.json` | `f8aafae494b633ba32b0e786b49391008c544dd9aa1bb5736916cdbff46aa704` |
| `checkpoint_state.csv` | `235510db382de2e4b321f11db80b9f5b969c094eb2d122b18ab373e6d31ae96e` |

The frozen runner SHA-256 is
`6194d25712df0e251fe0c56c671557967f8c7f5f7e62c28ca9981c09a3adf120`.
The focused test SHA-256 is
`72be12f0a84c46550e1f3604ae1769c261e22311dbdd2903c99b9b3812e1ea76`.
The bound Controller log SHA-256 is
`3930ab266e1983e6cd15a3472977984961b0f08a45e246eebb8feefbb048e8ce`;
the implementation log SHA-256 is
`2753e5bbefda642720a7193c22e2a21ac0367963a7632a5f67a71f42d29e607a`;
and the pre-score review SHA-256 is
`bd32577374246e5845242f6cec61d7619bfbb5238ad2d2679c837793ee4bc4d0`.

The lock fixes question `ingame-offset-scoretime-v1-q1` with question-record
SHA-256
`8cfabbfb4f93b2eddf31f61f7d4a2850b1e4dd0032661ae80ed433d1e36bfa9f`.
Its comparison incumbent is the v0 unfitted decision-time raw market on the
exact common mask, not a pregame or cross-task score.

## Population, masks, folds, and fitting receipts

- The lineage is exactly 195 source games to 193 materialized games.
- The two and only two exclusions are `2025_04_GB_DAL` with
  `unresolved_outcome` and `2025_05_TEN_ARI` with
  `market_trade_too_stale` (staleness `1088.157...` seconds).
- There are 87 unique OOF prediction rows, one checkpoint per game, no
  label-unavailable game, and no duplicated prediction key or game ID.
- All four arms use the same rows, labels, checkpoint, and fold assignment.
  The common check-key SHA-256 is
  `2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`,
  and the scorecard marks it as equal to the v0 check-key digest.
- Independent row-by-row comparison with the v0 saved predictions found exact
  equality for fold, game/date/week identity, event/cutoff identity, outcome
  availability, outcome, and raw-market probability.
- Expanding-window fold sizes are exactly fit `[106, 132, 148, 176]` and
  check `[26, 16, 28, 17]`.
- There are exactly 12 optimizer reports: three fitted offset arms in each of
  four folds.  Every report has `success=true`, `retry_count=0`, and the market
  logit coefficient fixed at `1.0`.  The arm component-spec SHA-256 values are
  `e2f71e54a5c2d933c4554ee111b8316ac7e64198b047b053fbd39d3b12242da7`
  (intercept),
  `bd907c7048076b033611d56eb10a02a637d427a7d0dcd3d95c45da84af42d95c`
  (linear state), and
  `bcdb518f4f7c7ea1a0da70bc841d67990b07c39c953c9cf63b707b3f5cfdd56a`
  (score-time state).

## Independent score replay

I parsed the frozen CSV directly and recomputed equal-event Brier loss,
clipped Bernoulli log loss, and calibration intercept/slope for every arm.  I
did not import the experiment runner, fit a model, or regenerate any artifact.
Values reproduced the scorecard (only ordinary last-bit floating-point
differences were observed):

| arm | rows | Brier | log loss | calibration intercept | calibration slope |
|---|---:|---:|---:|---:|---:|
| raw market | 87 | 0.14195252900323282 | 0.4296707847132428 | -0.011806646530491793 | 1.0370387494646494 |
| market offset intercept | 87 | 0.14524889804269395 | 0.43767065552795775 | -0.0015283771108292044 | 1.0156090151705999 |
| market offset linear state | 87 | 0.15956510197512852 | 0.46778903179152254 | 0.05699679231917337 | 0.8983310814194778 |
| market offset score-time state | 87 | 0.15959773603419797 | 0.4679675389347205 | 0.057996966414728124 | 0.8965806341506259 |

Per-fold Brier/log-loss replay also matched:

| fold (check n) | raw market | intercept offset | linear state | score-time state |
|---|---|---|---|---|
| 1 (26) | 0.1244784311 / 0.3780119626 | 0.1304975465 / 0.3921001552 | 0.1540698502 / 0.4468536824 | 0.1540374379 / 0.4468077226 |
| 2 (16) | 0.1729635462 / 0.5038277755 | 0.1775002902 / 0.5171015429 | 0.1732039735 / 0.5086281554 | 0.1732094231 / 0.5092763860 |
| 3 (28) | 0.1493726804 / 0.4601977700 | 0.1509941733 / 0.4638392506 | 0.1526889569 / 0.4549861364 | 0.1528526400 / 0.4553268219 |
| 4 (17) | 0.1272693543 / 0.3886038396 | 0.1279927308 / 0.3895070172 | 0.1664584351 / 0.4824581011 | 0.1664002917 / 0.4822707006 |

The score-time arm minus the otherwise identical linear-state arm is
`+0.00003263405906944` Brier and `+0.00017850714319795` log loss.  Score-time
minus raw market is `+0.017645207030965126` Brier and
`+0.03829675422147764` log loss.  The linear-state arm is also worse than raw
market by `+0.01761257297189569` Brier and `+0.03811824707827968` log loss.
Negative loss delta would be better; all aggregate deltas above are worse.

The score-time arm beats the linear arm on fold Brier only in folds 1 and 4,
giving the exact win vector `[true, false, false, true]`, or 2/4 rather than
the locked requirement of at least 3/4.

## Independent grouped uncertainty replay

Using the locked 10,000 complete-group resamples and seed `20260929`, then
recomputing the pooled equal-event mean inside each draw, independently
reproduced:

| contrast / metric | point | date-group 95% interval | week-group 95% interval |
|---|---:|---:|---:|
| score-time minus linear / Brier | 0.0000326340590694404 | [-0.00010044025335872863, 0.00011817573482291882] | [-0.0000786144287364669, 0.00012807322639239534] |
| score-time minus linear / log loss | 0.00017850714319795377 | [-0.00029989115833677066, 0.0005451781983846267] | [-0.0002341395783008241, 0.0005883368442281024] |
| score-time minus raw / Brier | 0.017645207030965126 | [0.0009821028297633057, 0.0382194659122864] | [-0.0011866396311722039, 0.037912259729848415] |
| score-time minus raw / log loss | 0.03829675422147764 | [-0.00668046873178215, 0.09179092374452855] | [-0.009001916491038061, 0.09085618389261586] |
| linear minus raw / Brier | 0.01761257297189569 | [0.0008807087985825904, 0.03829440675983162] | [-0.001313657823301061, 0.0379702270269658] |
| linear minus raw / log loss | 0.03811824707827968 | [-0.006830131584734332, 0.09195042135522685] | [-0.009378447911253328, 0.09097081790364062] |

The date/week intervals are uncertainty diagnostics and do not replace or
relax the exact locked decision rule.

## Decision and boundaries

All five locked support predicates are false: score-time Brier and log loss do
not beat linear state, Brier wins occur in only 2/4 folds, and score-time Brier
and log loss do not beat raw market.  The locked refute branch therefore
applies exactly.  `SCORE_TIME_K4_HYPOTHESIS_REFUTED` is not a post-hoc response
to a negative score.

The manifest, lock, inputs, predictions, and scorecard consistently retain the
opened-Train diagnostic boundary: Dev and sealed Final remained closed,
external fetch and paid-provider use are false, provider cost is exactly
`0`, promotion is false, and only historical event-clock availability is
claimed.  There was no automatic retry.  No realtime, execution, publication,
or state-update authority is present in the result.

## First launch failure versus the completed run

The separate Supervisor launch record SHA-256 is
`c15b182561e3bece7053ed6c3d4cf1b0303cc84140ad5cdf1c3c89ef9442c6c5`.
It preserves the exact first command and
`ModuleNotFoundError: No module named 'minimal_prediction_loop'`: the process
was launched from `research/market_rsi` without the required source import
path.  The failure occurred during module import, before `main()` or `run()`,
and the Supervisor recorded that the intended output path did not exist and
the frozen runner hash was unchanged.  Thus this was a zero-fit,
no-artifact Supervisor launch-path failure, not a scored scientific attempt.

The corrected command used the same reviewed runner, source, persistent output
ID, question, and decision rule.  Filesystem inventory and the launch record
identify exactly one completed v1 artifact and the manifest above.  The launch
failure does not alter the completed-run arithmetic or decision and receives
no research credit.

## Scientific disposition and research-credit recommendation

Stop and archive the exact `score_time_ratio_k4` augmentation route.  Preserve
raw market as the in-game diagnostic incumbent.  The result does not support
this representation as a data increment and must not be used to update an
incumbent, open Dev/Final, or authorize promotion.  A future experiment may
ask a genuinely different, predeclared play-by-play representation question;
it must not silently relabel this exact failed route.

For the separate research-credit admission process, I recommend **credit 2,
outcome `refute`, route action `stop`** for the exact locked question because
the run is complete, independently reproducible from frozen evidence, and
provides a valid negative answer that stops a route.  This is only a
recommendation: this review neither records credit nor mutates scheduler,
budget, incumbent, or durable research state.  The Supervisor/independent
credit gate must deduplicate it against the exact question/evidence hashes.

## Actions not taken

No fitting or experiment rerun, no runner or artifact modification, no
Train/Dev/Final read beyond the already frozen result evidence, no network or
provider call, no payment, no Git action, and no authoritative state, budget,
incumbent, or research-credit mutation occurred during this review.
