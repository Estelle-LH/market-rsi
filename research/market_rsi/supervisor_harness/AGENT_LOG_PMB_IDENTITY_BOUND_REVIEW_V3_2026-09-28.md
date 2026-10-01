# Independent PMB identity-bound review v3 — 2026-09-28

## Verdict

**REPLAN**

V3 closes the v1/v2 receipt-copy, receipt-mutation, reconstructed-lease and
stale-handle-retarget failures. Fresh read-only review nevertheless found
three P1 integrity/policy failures and no P0. V3 remains rejected and unsynced.

## Exact identity and verification

All ten constituent hashes and ordered aggregate
`96369948b1323a25805d9a1b9d4d48a77b2eb650b614a1da06499d2489fdfa5a`
from the v3 integration receipt matched. The receipt matched SHA
`41c442ec1ba1568a8d221b47fcfb0c813c7cce62e979946ff9a2122e89925899`.
The reviewed plan before this result matched
`3afa3cdf30daaabc55b46faaad39b4185856a31c98676ae089fbe6385df27b27`.

- Complete PMB discovery: **58/58 PASS**.
- Receipt/lease identity selection: **9/9 PASS**.
- Bottleneck-gate regression: **6/6 PASS**.
- Receipt mutations: upstream/manifest **28/28 rejected**; foundation all ten
  fields rejected; copy/deepcopy/pickle/replace **4/4 rejected**.
- Lease root, lifecycle, claim, copy and recovery probes: **PASS with no write
  on rejected attacks**.
- Compilation and ten no-index whitespace checks: **PASS**.
- Static capability scan: no external runtime/provider/data capability.

One initial zsh loop used reserved variable `status` and stopped without a
result. The corrected loop passed 10/10; no verdict used the failed command.

## P1-1 — Reachable receipt issuance helpers bypass validators

The external weak registries work, but the modules expose callable helpers
`_issue_upstream_verification` and `_issue_manifest_set_validation`. Calling
them directly registered arbitrary shape-valid hashes/counts/roles without
source or manifest validation. The reviewer bound an authentic sealed-Final
foundation receipt using upstream `a*64`, manifest `b*64`, 20 fabricated Final
dates and all three authority bits still false.

Required repair: remove callable value-accepting issuers. Construct and
register receipts inline only at the successful end of the actual validators,
using validator-derived locals. Add a regression proving no reachable helper
can register caller-selected evidence.

## P1-2 — Polymorphic repeated experiment reads permit arbitrary hash

The binder accepts `ExperimentSpec` subclasses and reads `sha256` more than
once. A stateful subclass returned `f*64` first and the real hash later, causing
an authentic foundation receipt to commit `f*64` while canonical bytes hashed
to `bb905a397bff42ab27b727f2623dee2f4d803e1370f8fd15a0243b5d4fee17fa`.

Required repair: require exact `ExperimentSpec` type, capture bytes and declared
hash once, rehash the captured bytes, validate only a local exact base-class
object, and build the receipt from the computed local hash.

## P1-3 — Promotion flag is not bound to role contract

Only public diagnostics force `promotion_eligible=false`. Caller-supplied true
was accepted for Train and hidden Dev; an authentic hidden-Dev manifest/spec
bound successfully. This contradicts the reviewed role contract: diagnostic
never promotes, Train is candidate development, hidden Dev is model selection,
and sealed Final is terminal rather than a feedback/promotion action.

Required repair: enforce an exact fail-closed role matrix. At minimum diagnostic,
Train and hidden Dev must be false. A manifest role alone must never imply that
an unvalidated Final episode independently grants promotion authority.

## Canonical probe

The canonical probe kept every v1/v2 mutation/retarget case false, but recorded:

```text
reachable_issuers_forged_final_accepted=true
stateful_experiment_subclass_arbitrary_hash_accepted=true
hidden_dev_promotion_true_bound=true
```

Probe SHA-256:
`dec14d0e669d6a5c31c2b6fd64c5c8523f111ae0609c14bae2e2328862332843`.

## Authority boundary

No source was edited by the reviewer. No network, PMB/real episode bytes,
Docker, provider/payment, protected state, training/evaluation, release or Git
mutation occurred. All external gates remain blocked.
