# InGameStaticStateNestedShrinkageDiagnostic-v2 — independent failure review

Date: 2026-09-29  
Attempt: `attempt-02` / `ingame-static-state-nested-shrinkage-v2-20260929-01`  
Reviewer scope: read-only forensic review; no repair, rerun, scoring, or scheduler-state transition  
Verdict: **execution failure confirmed; scientific result invalid**

## Frozen evidence

Artifact root:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-ingame-static-state-nested-shrinkage-train-diagnostic-20260929-01`

Observed files and SHA-256:

- `checkpoint_state.csv`: `235510db382de2e4b321f11db80b9f5b969c094eb2d122b18ab373e6d31ae96e`
- `exclusions.json`: `6bf5480e268d0fb803ad67efbb3e6a90191b101faebd0f20649a7d6b774a4865`
- `failure.json`: `d585d23d0a9bf8764b14e0dfdcf708344dc2ecb01e200f8cac4d99af94dfb0b2`
- `input_receipts.json`: `97058f551a95ee82edccf365525a00974cdff4c37b77cb5e7929d282538386b2`
- `pre_score_lock.json`: `4195d1529841715e46f65dcf089089ba3763ff373e9aee5efdc45bb6e551f55a`

The input receipt binds the executed runner to
`a3026d5a12fa0028087f470e44b71f4e6eb9de1432e351e415e72a039b83f65b`;
the current frozen runner has the same SHA-256. The batch terminal journal binds
the failed execution receipt to the exact `failure.json` hash above.

## Failure reconstruction

The frozen optimizer returned SciPy success/status `True/0` at `lambda=4.0`,
but its recomputed gradient infinity norm was
`1.87844783088309e-05`. The predeclared runner requires
`gradient_infinity_norm <= 1e-5`; therefore it raised the recorded
`RuntimeError` at the frozen convergence guard. The recorded objective was
`42.93458670404409` and the solver message was
`CONVERGENCE: REL_REDUCTION_OF_F_<=_FACTR*EPSMCH`.

`lambda=4.0` is the third member of the frozen inner-selection grid
`[0.25, 1, 4, 16, 64]`. The failure occurred while executing the frozen nested
optimizer before a complete set of inner losses and before any outer
prediction population could be committed. The failure receipt does not persist
the fold or inner-split index, so this review does not infer a more specific
block identity than the artifact proves.

This behavior is fail-closed and matches the pre-score lock: optimizer failure
is terminal, automatic retries are zero, and tuning after observing the failure
is forbidden for the frozen attempt.

## Output completeness and boundary review

The artifact directory contains exactly the five files listed above. In
particular, it contains **no** `predictions.csv`, `scorecard.json`, or
`manifest.json`. Consequently there is no complete common-mask prediction set,
no aggregate/fold score, no grouped interval, and no valid frozen
support/refute/inconclusive decision.

The persistent batch snapshot and terminal journal show one claim for
`attempt-02`, one terminal outcome `failed`, receipt SHA-256 equal to the frozen
failure file, one failed attempt consumed, and no second claim or retry. At the
time of this review the branch remains `execution_terminal`; its scorecard,
review, research credit, research outcome, and route fields are still null.
This review did not change them.

The lock, input receipts, and failure receipt all agree on the safety boundary:

- opened resident Train only;
- Dev not opened and Final sealed;
- external fetch false and network budget zero;
- paid provider false, provider calls zero, and cost `$0`;
- promotion unauthorized;
- retries zero.

The frozen runner has no network-client or subprocess import and writes the
failure receipt when no manifest exists. No artifact evidence contradicts the
declared boundary.

## Scientific classification

This attempt is **invalid scientific evidence**, not a refutation of static
state shrinkage. The execution stopped before producing the predictions and
scores required by the predeclared decision rule. A numerical convergence-gate
failure can diagnose an implementation/solver robustness issue, but it cannot
show that the candidate is worse than raw market or the frozen v1 control.

Required research-loop disposition:

- performance decision: operational `REVERT` only because no valid candidate
  result exists; do not encode or describe this as scientific `REFUTED`;
- research outcome: `invalid`;
- research credit: `0`;
- route action: `cooldown`;
- incumbent: unchanged;
- failed attempt remains counted against the batch budget;
- the failed runner is not eligible as an active research parent from this
  attempt.

Any solver repair or a fresh execution would be a new version/fresh attempt
with its own pre-score review and authorization path; it must not overwrite or
reinterpret this frozen failure.

## Review conclusion

**PASS as an independently verified failure receipt and boundary-preserving
fail-closed stop. INVALID as scientific performance evidence.** No retry or
state mutation was performed during this review.
