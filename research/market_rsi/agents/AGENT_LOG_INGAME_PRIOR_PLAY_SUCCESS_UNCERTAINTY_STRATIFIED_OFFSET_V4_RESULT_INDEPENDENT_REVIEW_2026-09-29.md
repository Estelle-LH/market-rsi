# InGamePriorPlaySuccessUncertaintyStratifiedOffset-v4 — independent result review

Date: 2026-09-29  
Artifact-validity verdict: **PASS**  
Frozen scientific / operational decision: **REFUTED / REVERT**

Artifact reviewed read-only:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-ingame-prior-play-success-uncertainty-stratified-offset-20260929-01`

All metrics and the decision below were independently recomputed from
`predictions.csv` and frozen v0/feature artifacts, without using the scorecard
as an arithmetic source.

## Artifact and lineage integrity

| file | SHA-256 |
|---|---|
| `manifest.json` | `a0143a045282ec5315e01d7294befe201e3bc5263abe5cd67a6756da63ae7b64` |
| `pre_score_lock.json` | `eea3645906033970d7d2173e72c81bcd00ddf764c7df9ae108fe1f1141125899` |
| `input_receipts.json` | `3c4bff0a55110353d0f34aa3b5db5b56338d840dd729b711424dd0bdac832e42` |
| `exclusions.json` | `99b5646499c7deb3572637bda45b9c175efe2ed0d6c236d83468d49263e3aabd` |
| `predictions.csv` | `0da49156a9a1543d326f94aa62b8f8077b6a02ab860fcb82aa1a4e7033ba894a` |
| `scorecard.json` | `5d246a61ea2e98f3489f4a1ebecf34e3b526e43632d0ba47e7dc42d6b386fdd7` |

The directory contains exactly those six regular result files. The manifest
binds the other five hashes exactly. Input receipts bind every frozen v0 file
and every prior-play feature artifact file to its independently recomputed
hash, including feature SHA-256 `cca09f294f88f19a5cfa05fce294d6ec2a11c6264fed54840460784cbabea764`.

`predictions.csv` has exactly 87 unique `(event_id, market_id, cutoff_ms)`
keys. Ordered key SHA-256 is
`2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`.
Every key, fold, game, date, week, label, cutoff, outcome-availability stamp,
raw probability, frozen ordinary probability and frozen v0 parent probability
matches the frozen v0 row exactly. Every prior-play signal equals the validated
frozen feature row exactly. There are no missing or duplicate check rows.

The exact source reconciliation remains `195 = 193 materialized + 2 excluded`;
the exclusions are `2025_04_GB_DAL / unresolved_outcome` and
`2025_05_TEN_ARI / market_trade_too_stale`.

## Independent proper-score replay

Equal-event aggregate metrics:

| arm | Brier | log loss |
|---|---:|---:|
| raw market | `0.14195252900323282` | `0.4296707847132428` |
| frozen v0 ordinary market-only | `0.14548231253271718` | `0.43992197245621956` |
| frozen v0 market-plus-state parent | `0.16068099016465245` | `0.4711973192666776` |
| candidate | `0.14195368741327474` | `0.4296330176680234` |

Candidate-minus-comparator deltas:

| comparator | Brier delta | log-loss delta |
|---|---:|---:|
| raw market | `+0.0000011584100419181897` | `-0.00003776704521940566` |
| ordinary | `-0.0035286251194424356` | `-0.010288954788196136` |
| v0 parent | `-0.01872730275137771` | `-0.04156430159865415` |

Thus the candidate improves log loss over all three controls and improves both
proper scores over ordinary and the v0 parent, but its aggregate Brier is
slightly worse than raw market.

Independent fold replay (`candidate / raw / ordinary / v0 parent`):

| fold (events) | Brier | log loss | candidate raw-Brier win |
|---|---|---|---|
| 1 (26) | `0.124481785081 / 0.124478431116 / 0.130617108777 / 0.150199182184` | `0.377990262784 / 0.378011962643 / 0.396562133591 / 0.435937115706` | no |
| 2 (16) | `0.172927801210 / 0.172963546150 / 0.175895495925 / 0.167357931585` | `0.503671333310 / 0.503827775525 / 0.512761920284 / 0.502197284512` | yes |
| 3 (28) | `0.149390233328 / 0.149372680446 / 0.151805916663 / 0.166138569767` | `0.460183448448 / 0.460197770007 / 0.466069178604 / 0.486973189087` | no |
| 4 (17) | `0.127274884725 / 0.127269354316 / 0.129177809458 / 0.161438855807` | `0.388614577366 / 0.388603839572 / 0.394615788521 / 0.469964465955` | no |

Candidate Brier beats raw in `1/4` folds and ordinary in `4/4` folds.

## Independent complete-group bootstrap replay

Using the frozen seed `20260929`, 10,000 draws, resampling complete groups and
recomputing pooled equal-event candidate-minus-raw Brier in every draw:

| grouping | groups | point delta | 95% interval |
|---|---:|---:|---|
| schedule date | 20 | `+0.0000011584100419364056` | `[-0.0000186924113837201, +0.00002244687138296532]` |
| observed game week | 7 | `+0.0000011584100419364056` | `[-0.000017720979660957808, +0.000022282446075536034]` |

Both upper bounds exceed zero.

## Frozen decision replay

- aggregate Brier below all three: **false**
- aggregate log loss below all three: **true**
- raw Brier wins at least 3/4 folds: **false**
- ordinary Brier wins at least 3/4 folds: **true**
- date/week candidate-minus-raw Brier upper bounds below zero: **false / false**
- raw Brier wins at most 1/4 folds: **true**

The predeclared refutation condition is met both because aggregate candidate
Brier is not below raw and because raw Brier wins are only `1/4`. Independent
decision: **REFUTED / REVERT**. This exactly matches the manifest and scorecard
claims. The raw-market incumbent must remain unchanged. The result refutes this
exact fixed candidate; it does not establish that the underlying prior-play
information is universally useless.

## Boundary review

Manifest, pre-score lock and input receipts all record:
`route_dev_opened=false`, `sealed_final_opened=false`, `external_fetch=false`,
`paid_provider=false`, and `provider_cost_usd="0"`; manifest/lock also record
`promotion_authorized=false`. The lock limits the run to four local fits, one
process/thread, zero network bytes/provider calls, and zero retries. Frozen v0
and feature artifact hashes and their protected-data boundary records validate.
The result directory has no unexpected file indicating an external operation.
No Dev/Final, network, paid-provider or promotion boundary violation is present
in the reviewed receipts/artifacts.

The recovery scheduler currently binds this exact runner SHA
`b827eecdd669451d92a24a1023e2407a10ddebd26585f4515e395c0f486ff589`
and claim ID `ingame-prior-play-success-uncertainty-stratified-offset-v4-20260929-01`;
at review time it remains at `execution_claimed`, awaiting terminal/result-review
recording. This review does not mutate scheduler state.
