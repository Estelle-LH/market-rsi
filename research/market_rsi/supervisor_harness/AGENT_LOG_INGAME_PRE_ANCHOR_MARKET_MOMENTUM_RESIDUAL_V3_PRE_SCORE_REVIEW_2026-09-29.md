# InGamePreAnchorMarketMomentumResidualAudit-v3 — independent pre-score review

Date: 2026-09-29  
Reviewer role: non-author implementation reviewer  
Scope: frozen source/tests and no-score preflight only; no real audit execution and no scheduler mutation  
Verdict: **PASS**

## Frozen inputs

- generation-2 Controller log SHA-256:
  `4186a3554b7f7aed50596123c135943dbf986d5e39b84fe507fac91c6e04e986`
- runner SHA-256:
  `a99cf9889ad1e463e8ae2294711cb0b1ad94735be933f2e02ba99cdb49ca26b9`
- tests SHA-256:
  `fc5cce906049608e0e842e02267170d8c9c830c11eeb40a26f301b483eebd231`
- implementation log SHA-256:
  `a39b016f26622d2105d57fd36d42f27a55cdf0f5ebc71bebfff1da7979b12826`

All observed bytes match the hashes provided for review. The runner additionally
binds and the review independently confirmed:

- v0 runner:
  `e61668c7e29cf4dda95f6cc315b248dbe6744a9dcc0ae0cd6077d880ca6265b7`;
- prior v0 artifact validator:
  `a612371ae77a78441c2d9416d6edc035a916879057fed9ef731de46476a07bcb`;
- settlement/trade dependency:
  `1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b`;
- scheduler attempt-04 branch digest:
  `c033d747aedf039e8d1369ed6fd9ca207d93b18947193f99a62129c76d0e5433`.

## Lineage and mask review

The exact reviewed v0 artifact contains and matches all seven frozen hashes:

| v0 file | SHA-256 |
| --- | --- |
| `manifest.json` | `9c6ab11fc553a13e35b410c8763d87a85b535a5ab9b47df8c8dc0d10ac922fc7` |
| `pre_score_lock.json` | `dc3a8bf1a27795750c44193000480c9279dd47de5d115d6cfad829e5b81d6ef2` |
| `input_receipts.json` | `0fa0a2444beaddd0a51efd2024c5e6d7c09158db7d6488a59421a99866fdbf18` |
| `exclusions.json` | `db5b535d261f1e6676beafebeb7aee70833ea1d7988aba25a95c905a9955eaf1` |
| `checkpoint_state.csv` | `235510db382de2e4b321f11db80b9f5b969c094eb2d122b18ab373e6d31ae96e` |
| `predictions.csv` | `505e11a4ceb3ae569397bbbc11c6a0be6e9f04a494c9ecb1f4ca40dc06d76d56` |
| `scorecard.json` | `74c2f23de2ae129ead4d7def1a692d69240ac799582e54db3623865c3525de87` |

The reused validator fail-closed verifies `195 source -> 193 materialized + 2`
named exclusions, the exact 87 unique check games, fold counts
`26/16/28/17`, and check-key digest
`2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`.
It also verifies the opened-Train source/cohort and all 195 PBP/source receipts.

The new extraction iterates the frozen predictions rather than discovering a
new population. Every check game must have cohort, checkpoint and materialized
receipt entries. The result must have the same length and unique game IDs; in
production it must be exactly 87. Missing or stale reference coverage raises a
terminal error. There is no row-drop or imputation path.

## Strict time and orientation review

PASS:

- Decision time is the exact v0 checkpoint time. The current cutoff is
  `floor(decision_epoch)` and the selected current fill second must be strictly
  less than it. This is equivalent to the v0 integer-second cutoff
  `floor(decision_epoch)-1`, which is explicitly rechecked.
- Reference cutoff is exactly `floor(decision_epoch)-120`. The reference is the
  latest fill second strictly less than that cutoff; a fill at the cutoff itself
  is excluded.
- Reference age is `reference_cutoff-reference_fill_second` and must satisfy
  `(0,300]`. The 300-second edge passes and 301 seconds fails.
- All fills at the selected integer second are combined with size weighting.
  The same home-token orientation is reconstructed from the hash-bound catalog
  and selected moneyline market. PBP home/away identity must agree.
- `p_now` and its selected fill second must exactly reproduce the frozen v0
  probability and receipt. Catalog stored/raw hashes, market metadata, trade
  manifest, trade window and protected-boundary receipt are checked for each
  event.
- Only the logit transform clips probabilities to `[1e-6,1-1e-6]`; raw
  `p_now`/`p_ref` are preserved. The signal builder has no outcome argument.

The frozen signal is therefore exactly
`logit(p_now)-logit(p_ref)` under the clipped-logit convention, with no label
input and no alternate lag or staleness choice.

## Metrics, inference and decision review

On the one exact mask the runner computes Pearson and tie-aware Spearman versus
`y-p_now`, mean `signal*(y-p_now)`, and mean
`signal*(y-p_now)*p_now*(1-p_now)`. It reports the same metrics for all four
frozen folds.

For both directional-alignment metrics it performs 10,000 complete
schedule-date bootstrap draws and 10,000 complete observed-game-week draws at
seed `20260929`, recomputing the pooled equal-event mean inside each draw. It
records valid and undefined counts; given a valid non-regime audit, every draw
is defined and the implementation records zero undefined draws.

The decision matches the generation-2 Controller exactly:

- support requires positive Pearson, Spearman, both directional alignments,
  both date/week log-alignment lower bounds, and positive log alignment in at
  least three of four folds;
- refute applies when both correlations are nonpositive, both directional
  alignments are nonpositive, or at most one of four folds is positive;
- every other valid result is inconclusive.

Integrity, source receipt, chronology and complete coverage are checked before
analysis. All production analysis inputs originate from finite validated
probabilities, finite signals and binary outcomes; undefined correlation
geometry raises in the frozen Pearson implementation instead of becoming a
scientific result.

## Zero-fit and authority boundary

The runner performs zero prediction-model fits and contains no model/predict
path or network-client import. It emits an event-level raw-signal audit rather
than a candidate probability and records no incumbent or KEEP/REVERT change.
Persistent-output guards reject temporary and cloud-looking destinations.

The lock, receipts, scorecard, manifest and failure record keep Dev closed,
Final sealed, external fetch false, paid provider false, cost `$0`, and
promotion unauthorized. Evidence is explicitly historical opened-Train
diagnosis, not realtime availability, untouched OOS, prediction improvement,
PnL, publication or promotion.

## Verification executed

Using the pinned local Python 3.12 runtime:

1. New attempt-04 tests plus prior-play and v0 regressions: **30/30 PASS** in
   4.552 seconds.
2. `py_compile` for the frozen runner and tests: **PASS**.
3. `git diff --check` for runner, tests and implementation log: **PASS**.
4. Post-test SHA-256 verification of runner, tests, implementation log and
   Controller log: **PASS**, unchanged.

The tests used synthetic trades for signal/edge/end-to-end behavior and read
the real v0 artifact only for no-score hash, lineage and mask preflight. This
review did not run `_extract_market_signals` or `_audit` on the real 87 games,
did not create a production artifact, and did not claim or mutate scheduler
state.

## Disposition

**PASS for a separately controlled one-shot execution of the exact frozen
runner.** This is implementation clearance only. It contains no result about
market momentum and does not itself authorize execution, research credit,
candidate creation, KEEP, promotion or any protected-data access.

The indicator-evaluation review principle materially used here is that the raw
signal must be evaluated on the immutable paired event mask with strict causal
ordering and complete-group uncertainty before any prediction fit is proposed.
