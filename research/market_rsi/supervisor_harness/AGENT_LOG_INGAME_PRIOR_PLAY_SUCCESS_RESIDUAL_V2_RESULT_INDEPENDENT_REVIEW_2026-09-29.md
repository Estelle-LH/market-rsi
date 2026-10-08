# In-game prior-play success residual audit v2 — independent result review — 2026-09-29

## Verdict

**PASS.** Zero P0 and zero P1 findings. The completed artifact is internally
consistent with the frozen runner and independently reproduces the exact
decision `PRIOR_PLAY_SUCCESS_RESIDUAL_INCONCLUSIVE` on all 87 frozen check
games. This is valid but unresolved opened-Train raw-signal evidence: it is not
a prediction candidate, KEEP/REVERT decision, promotion result, realtime claim,
or untouched OOS evidence.

This review did not modify the runner, completed artifact, incumbent, research
credit, scheduler state, Dev/Final, or any historical result. It did not rerun
the audit or R extraction.

## Frozen source and artifact integrity

The runner remains frozen at SHA-256
`a612371ae77a78441c2d9416d6edc035a916879057fed9ef731de46476a07bcb`.
The reviewed artifact is
`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-ingame-prior-play-success-residual-audit-20260929-01`.

| Artifact file | SHA-256 |
| --- | --- |
| `manifest.json` | `addececc96838399be8b9713b85048dba6c449e840aff6f69f099f1779750144` |
| `pre_audit_lock.json` | `d046d70927f0f29f327b0ed8552e523fbaf3c1955db257af19a225250f9e2929` |
| `input_receipts.json` | `0f8902d5aee81a08d5c17c44f2025e10ca650cc6f825c4be150735c0ac7934e0` |
| `prior_play_success.csv` | `cca09f294f88f19a5cfa05fce294d6ec2a11c6264fed54840460784cbabea764` |
| `event_audit.csv` | `0b85a96491237edcf1b74e8718db0582bae28d0bf380c0d0f89564edaf20e2f5` |
| `scorecard.json` | `db53da50fecbebce76eb105915d53db51ce44eced92fbf41dd9688ac40e71846` |

The complete manifest exactly binds the other five artifact hashes and records
the same decision as the scorecard. Input receipts bind the exact extractor
SHA `fe3e4096f80ea37a8074fc6e404b659474aa4c9e7586367cc218fb50e1650bea`,
runner SHA above, source/cohort/PBP receipts, and all seven reviewed v0 files.
The lock binds Controller SHA
`a2c1c060b3ddf63ee3c0e1b6f7baebdba08b550c91be0a7d5585ead9b5dac18f`,
question digest
`402ccc0147784eedf540918028d297b2d645d9f374e515bf403e9930682e14f5`,
and rule digest
`96c92f3ce51d779412e3953392eb037c2190ef0522fc8454a4f4f6701424b40e`.

## Independent population and signal reconstruction

The frozen lineage independently reproduced as `195 source -> 193
materialized + 2 named v0 exclusions -> 87 check games`. The extracted
indicator file contains 195 unique eligible games. The event audit contains
exactly the same 87 unique game IDs, folds, dates, weeks, outcomes, and raw
market probabilities as the hash-bound v0 prediction mask; no v0 check game is
dropped. The 87 checks span 20 schedule dates and seven observed game weeks,
with fold counts `26, 16, 28, 17`.

For every event I independently reconstructed:

```text
home_rate = home_successes / home_eligible_plays
away_rate = away_successes / away_eligible_plays
signal = home_rate - away_rate
market_residual = outcome - raw_market_probability
log_alignment = signal * market_residual
brier_logit_alignment = log_alignment * p_raw * (1 - p_raw)
```

Both sides have positive eligible-play counts for every reviewed event. Counts,
successes, rates and signals match the 195-row extraction artifact. The maximum
absolute formula discrepancy across the 87 event rows is
`4.996003610813204e-16`, consistent with decimal serialization only.

## Independently recomputed evidence

Aggregate results are:

| Metric | Independent value |
| --- | ---: |
| events | 87 |
| Pearson(signal, market residual) | `0.03144531928850585` |
| Spearman(signal, market residual) | `0.14767663330713243` |
| mean log-loss directional alignment | `0.0013703394461542545` |
| mean Brier-logit directional alignment | `-0.00018037640333657938` |

The four frozen folds independently reproduce:

| Fold | Events | Pearson | Spearman | Log alignment | Brier-logit alignment |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 26 | `0.26895944251043624` | `0.5165811965811966` | `0.0063393409337890025` | `0.0009876412879486576` |
| 2 | 16 | `0.08593452556164852` | `0.03235294117647059` | `0.0040556693037342014` | `-0.000049362173241489045` |
| 3 | 28 | `0.1622157179211897` | `0.30655536074679457` | `0.006625031406577946` | `0.0010011949953421754` |
| 4 | 17 | `-0.4053994336139794` | `-0.35294117647058826` | `-0.01741146592394257` | `-0.004036181510274388` |

Thus three of four folds have positive log alignment, but fold 4 reverses
strongly. The aggregate Brier-logit directional derivative is also negative.

I independently reran every complete-group bootstrap with NumPy's seeded
generator, 10,000 draws, linear 2.5%/97.5% quantiles, and pooled equal-event
means inside each draw:

| Metric | Group/breadth | 95% interval |
| --- | --- | --- |
| log alignment | schedule date / 20 | `[-0.008293056639868054, 0.008072970192477045]` |
| log alignment | observed week / 7 | `[-0.007805652739882053, 0.007919299442964106]` |
| Brier-logit alignment | schedule date / 20 | `[-0.0022608618281456205, 0.0012754324709687676]` |
| Brier-logit alignment | observed week / 7 | `[-0.0020346588916465083, 0.0011468438809697809]` |

All values agree with the scorecard within `2e-15`.

## Exact decision reconstruction

The positive Pearson, Spearman and aggregate log alignment plus three positive
folds are directional evidence. Support nevertheless fails because the
Brier-logit alignment is negative and both date- and week-grouped log-alignment
lower bounds are negative. Refutation also fails: the two associations are not
both nonpositive, the two directional alignments are not both nonpositive, and
positive log alignment occurs in 3/4 rather than at most 1/4 folds.

The frozen ordered rule therefore yields exactly
`PRIOR_PLAY_SUCCESS_RESIDUAL_INCONCLUSIVE`. No threshold, sign, fold or
resampling choice was changed after viewing results.

## Zero-fit, incumbent, and authority boundary

Manifest, lock and scorecard all record `model_fits=0`. No prediction candidate
was emitted and `incumbent_or_keep_revert_changed=false`. The artifact awards
zero research credit pending this review.

Manifest, lock, scorecard and receipts consistently record zero provider cost,
no external fetch, and closed Dev/Final. Paid provider and promotion remain
false. The evidence is explicitly limited to repeatedly inspected historical
opened-Train PBP ordering; publication/receipt latency is unobserved, so no
realtime-availability conclusion is supported.

## Verification performed

The independent reconstruction read event-level files and recomputed all
signals, associations, fold summaries, group bootstraps and the decision; it did
not call the runner's `_audit()` or `run()` functions. Using the pinned Python
3.12 runtime, the frozen parent and audit suites also passed:

```text
python -m unittest -v \
  experiments.test_nfl_ingame_win_probability_train_diagnostic \
  experiments.test_nfl_ingame_prior_play_success_residual_audit

Ran 19 tests in 4.637s — OK
```

## Credit and route recommendation (not applied)

Recommend **research credit 1**, outcome **`inconclusive`**, route action
**`bounded_followup`** for the exact predeclared question. The completed
manifest SHA
`addececc96838399be8b9713b85048dba6c449e840aff6f69f099f1779750144`
is the natural evidence-bundle root because it binds the lock, receipts,
indicator, per-event audit, scorecard and frozen v0 lineage.

The reason is valid partial information rather than success: rank and log-loss
directions are positive and 3/4 folds agree, but proper-score direction,
grouped uncertainty and late-fold stability do not resolve the question. A
bounded follow-up may parent one genuinely distinct, predeclared question from
this branch; it must not rerun or retune this frozen audit, claim prediction
gain, replace the raw-market incumbent, or grant new data/network/provider
authority. The Supervisor must perform the append-only, duplicate-checked
credit/state write separately; this review intentionally performs neither.
