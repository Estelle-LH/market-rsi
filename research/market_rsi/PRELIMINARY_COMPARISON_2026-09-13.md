# Preliminary historical model comparison — frozen before scoring

This is the separately approved diagnostic after the user's “sure”. It does not
activate or rewrite the original rev6 experiment, whose capture/heartbeat gates
remain blocked. It is not RSI, a final independent test, or a profitability test.

## What actually runs

Fit the existing GLM-selected one-feature, no-intercept least-squares model once.
The feature is the past midpoint change under the exact published rev6 sample
contract. Prediction is beta × feature; baseline predicts zero on identical rows.
Alpha=0, no normalization, clipping, sign constraint, or weighting; seed23.
Only prediction differs between these two arms. Do not compare scores to older
populations or attribute this executor-built diagnostic to autonomous improvement.

Training uses the complete sufficient statistics from the already measured
Aug21T12 file: 1,051,922 paired rows. Beta=sum_xy/sum_xx is the exact one-parameter
OLS solution; it is a real statistical fit, not LLM weight training. Write its
checkpoint and hash before reading later-file results. No refitting on checks.

| Role | UTC filename | Compressed bytes |
|---|---|---:|
| Train | polymarket-20260821T12.jsonl.zst | 65,819,206 |
| Check | polymarket-20260825T12.jsonl.zst | 35,120,175 |
| Check | polymarket-20260907T12.jsonl.zst | 16,365,581 |
| Check | polymarket-20260908T12.jsonl.zst | 13,166,507 |
| Check | polymarket-20260909T12.jsonl.zst | 18,153,334 |

These dates come from the previous controller plan, but the common T12 subset is
an executor-selected efficiency restriction, not the original full-date design.
Aug22 has no T12 object; it is not in this diagnostic's training definition.
No replacement files, no larger scan, no outcome-selected dates or retries.
The four checks total 82,805,597 compressed bytes, processed on Linode, not
downloaded to the Mac. Filenames define objects, not guaranteed timestamp coverage.

## Fixed sampling, measurement and verdict

Reuse the published price_change direct-BBO adapter and exact contract
25c420d2e5e79f6e1e5eea850127cbecb7d1c2b1471614d81996640b5b6808bb.
Past-only 60s lookback; declared source clock; same-group closure; future endpoint
backward-asof within 59,999ms tolerance. The answer's actual span is 1–60,000ms,
not necessarily an exact 60-second return. Report span and missingness counts.
Preserve all valid zero changes. Missing/invalid answers never become zero.
Whole-token file segments with time regressions are rejected with counts, not
sorted or repaired. Invalid routing, day, transport, or resource limits fail the
file. Price-unit, token-routing, clock and sample checks precede its scoring.

Primary: arithmetic mean of the four selected-file MSEs, equal file/date weight.
Every file must complete for a primary comparison. A failure stops this operation;
the unfinished primary remains incomplete, with all observed results retained.
Report each file's baseline and candidate MSE, RMSE in price-bps (1bp=$0.0001/share),
relative MSE change, counts, zero share, paired masks/prediction hashes, IC and
calibration where defined, and token/date breadth. Constant-prediction IC is
undefined, not zero. Direct prediction residuals must match sufficient-statistic
residuals. No financial-return-bps, PnL, fees assumption or execution claim.

If all checks complete and mean candidate MSE is lower: it beats zero on these
four opened diagnostic files. If equal/higher: it does not. Neither outcome proves
or refutes formal RSI. No model/target selection follows within this operation.

## Known limits, not waived formal gates

No original capture/heartbeat attestation: quiet versus outage remains unknown.
Hashes prove the bytes read now, not completeness at capture. Per-file identity
checks do not establish cross-file identity continuity. Earlier and later rows
may share markets. Training and checks span five selected hours, not five full
days, and checks are on previously opened diagnostic dates, not sealed OOS.
Overlapping rows and paired tokens are dependent. No IID p-values or promotion;
four hours cannot satisfy the evaluation checklist's 20 independent final-session
minimum. Run its component check, retain the expected final-promotion rejection.

## Research and alternatives checked before implementation

Access 2026-09-13. Queries: official scikit-learn Ridge “alpha = 0”; official SciPy
spearmanr “ConstantInputWarning”. Read Ridge objective, alpha and intercept
paragraphs; SciPy correlation definition and constant-input warning.

- https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html
  establishes alpha0 is OLS and recommends LinearRegression rather than numerical
  Ridge(alpha0). Reuse the controller's unchanged objective via its closed-form
  one-variable solution, checked against pinned sklearn1.6.1. No dependency upgrade.
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html
  documents undefined correlation for constant inputs. Use average tied ranks,
  validated against pinned SciPy; omit IID significance tests on overlapping data.

Alternatives not selected: nonzero regularization, intercept, sign restriction,
new features, filtering quiet rows, or full-date reads. These would change the
existing method or scope; no diagnostic-score-driven choice is authorized here.
Sources justify numerical implementation, not prediction-market effectiveness.

## Execution controls and trace

New external runner/tag pm-preliminary-comparison-v0.1.0; old DSH1.5.0 and converter
files untouched. Before empirical fit: tests, synthetic Linode transport/scoring
canary, clean scoped commit, annotated tag verified on private origin. Bind
source, spec, training report, checkpoint and program hashes to permanent claims.
One local operation lock, shared remote processing lock; serial files; 600 seconds
and combined 1GiB per remote Python/decoder operation. No automatic resume/retry.
No Tinker/GLM/E2B calls or new purchases. Existing Linode CPU is not separately
metered here; “zero new Tinker” does not mean all hosting is free. Keep original
$200 ledger and uncertainty/holds unchanged. Results and failures are append-only
under a fresh preliminary-comparison artifact directory.

Implementation: audit_tools/preliminary_comparison.py and
audit_tools/run_preliminary_comparison.py. Tests: test_preliminary_comparison.py
plus the frozen sample/stream regression tests. Test and empirical outcomes are
recorded separately after execution; this document does not presume success.
