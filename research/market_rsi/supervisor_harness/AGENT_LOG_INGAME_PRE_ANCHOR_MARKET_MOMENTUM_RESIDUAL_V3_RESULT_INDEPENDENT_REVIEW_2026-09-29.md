# InGamePreAnchorMarketMomentumResidualAudit-v3 — independent result review

Date: 2026-09-29  
Artifact: `/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-ingame-pre-anchor-market-momentum-residual-audit-20260929-01`  
Verdict: **PASS — valid opened-Train result, scientifically INCONCLUSIVE**

## Artifact integrity

The artifact contains exactly the expected five completed files:

| File | SHA-256 |
| --- | --- |
| `manifest.json` | `9e7d5813a798a23da5e9992e079ec795e55d952529f11927f6244e9ac80f7499` |
| `scorecard.json` | `86ea1966786b523785512987fab174df3ac02b43c6b297d1e8cadf1a0e013d72` |
| `event_audit.csv` | `324a0c4e607321c10c5303c301109b847c18dcdc84d0018f503963f4f7eb3ba9` |
| `input_receipts.json` | `61bcf572a99863092af8721db4c532586172d9213c108ad6834e3fcd7dcdf2eb` |
| `pre_audit_lock.json` | `31023472c8af84803275aa3a43f250f8554040470725a30dbe477eff07dfd387` |

The complete manifest binds the other four hashes exactly. Receipts bind runner
`a99cf9889ad1e463e8ae2294711cb0b1ad94735be933f2e02ba99cdb49ca26b9`,
Controller
`4186a3554b7f7aed50596123c135943dbf986d5e39b84fe507fac91c6e04e986`,
and all seven reviewed v0 artifact hashes.

The v0 lineage independently verifies as `195 source -> 193 materialized + 2`
named exclusions -> 87 check games. Event audit and v0 predictions have the
same 87 unique game IDs, identities, labels, folds and raw probabilities, fold
counts `26/16/28/17`, 20 dates, seven observed weeks, and check-key SHA-256
`2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`.
No row was dropped or imputed.

## Independent signal reconstruction

Without calling the runner's `run`, `_extract_market_signals`, `_audit`, metric,
or bootstrap functions, I independently read all 87 hash-bound local trade
windows and reconstructed their home orientation from the recorded home token.
For every event I verified catalog stored/raw/meta hashes, trade manifest and
window hashes, and the manifest's closed protected-data boundary.

For all 87 games:

- `current_fill_second < floor(decision_epoch)`;
- `reference_cutoff = floor(decision_epoch)-120`;
- `reference_fill_second < reference_cutoff`;
- reference age equals cutoff minus fill second and is in `(0,300]`;
- `p_now` is the size-weighted probability over every fill at the latest
  eligible current second and exactly matches v0;
- `p_ref` is the analogous probability at the latest strictly-prior reference
  second;
- signal is the clipped-logit difference with clipping used only inside the
  transform.

Independent reconstruction matched serialized `p_now`, `p_ref`, signal,
residual, log alignment and Brier-logit alignment exactly; maximum absolute
discrepancy for every field was `0`.

## Independently recomputed result

Aggregate equal-event evidence:

| Metric | Value |
| --- | ---: |
| events | 87 |
| Pearson(signal, `y-p_now`) | `0.09858521380247207` |
| Spearman(signal, `y-p_now`) | `0.07984252042335277` |
| mean log-loss directional alignment | `0.011165899514078152` |
| mean Brier-logit directional alignment | `0.0012822701996301423` |

Fold log alignments are respectively
`0.029029574218373592`, `-0.00593331971126795`,
`0.003144012553290418`, and `0.013150887760896544`: three of four are
positive, but fold 2 reverses.

I independently reran all 10,000 complete-group draws at seed `20260929`,
recomputing pooled equal-event means inside every draw. All draws were valid;
undefined count was zero. The exact 95% intervals are:

| Metric | Grouping | 95% interval |
| --- | --- | --- |
| log alignment | schedule date | `[-0.004838555975452239, 0.028928914770157594]` |
| log alignment | observed week | `[-0.0017025915815155022, 0.02468904151524127]` |
| Brier-logit alignment | schedule date | `[-0.0018680652631516152, 0.004494576004328799]` |
| Brier-logit alignment | observed week | `[-0.0010914464662462623, 0.0032251149656429617]` |

All aggregate, fold and interval values match the frozen scorecard within
`2e-15` (and the event formulas match exactly).

## Decision reconstruction

Pearson, Spearman, both directional alignments and three of four fold log
alignments are positive. Support nevertheless fails because both required
grouped log-alignment lower bounds are negative. Refutation also fails because
the two correlations are not both nonpositive, the two directional alignments
are not both nonpositive, and three rather than at most one fold is positive.

The exact predeclared result is therefore
`PRE_ANCHOR_MARKET_MOMENTUM_RESIDUAL_INCONCLUSIVE`.

This is directional but unstable raw-signal evidence. It is not a probability
candidate, prediction improvement, realtime-availability result, untouched
OOS evidence, KEEP, promotion, or PnL result.

## Boundary and scheduler recommendation

Lock, receipts, scorecard and manifest agree on zero model fits, no candidate,
no incumbent/KEEP-REVERT mutation, no external fetch, no paid provider or cost,
Dev closed, Final sealed, and promotion unauthorized. The review observed no
boundary contradiction.

Recommended append-only scheduler disposition, **not applied here**:

- result review: `REVERT` operationally, because there is no candidate and no
  incumbent update; do not describe it as scientific refutation;
- incumbent: unchanged;
- research credit: `1`;
- research outcome: `inconclusive`;
- route action: `bounded_followup`;
- evidence bundle: manifest SHA-256
  `9e7d5813a798a23da5e9992e079ec795e55d952529f11927f6244e9ac80f7499`.

Credit 1 is warranted because this valid, nonduplicate experiment produced a
verifiable new finding: recent pre-anchor market momentum is directionally
positive in aggregate and 3/4 folds, but date/week uncertainty and one fold do
not establish stability. Credit 2 is not warranted because neither support nor
refute fired. The current batch is already at its final attempt; recording the
contractual `bounded_followup` route does not create authority or an additional
attempt in this batch.

This independent review did not edit the artifact, runner, incumbent, research
credit, or scheduler state.
