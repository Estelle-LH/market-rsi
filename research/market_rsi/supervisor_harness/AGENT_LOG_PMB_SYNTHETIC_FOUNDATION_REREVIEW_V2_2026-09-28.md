# Independent PMB synthetic foundation rereview v2 — 2026-09-28

## Verdict

**REPLAN**

The exact v2 snapshot closes both original v1 reproductions, but fresh
read-only adversarial review found two practical P1 integrity bypasses.  No P0
was found.  V2 must not be accepted or synced as the durable foundation.

## Exact reviewed identity

All ten constituent hashes in
`PMB_SYNTHETIC_FOUNDATION_INTEGRATION_2026-09-28-v2.md` and its documented
aggregate
`e235b469b96510f578411a184286639a931e8f37aaf46091bf5a8d8ef31356d6`
were independently recomputed and matched.  The integration receipt matched
SHA `6e9d0adf90ac2fcfc8cbaf5728c331003347acf41a628057ae6e2f1d92f85b5d`.
The reviewed plan before this result matched
`e21db781e75d2dcf988bfbe0eae99ba5f709e4054c0fa2160d58db05ea39280f`.

## Verification replay

- Full PMB discovery: **48/48 PASS**.
- Original six P1/integration regressions: **6/6 PASS**.
- Bottleneck-gate regression with the required `PYTHONPATH`: **6/6 PASS**.
- Compilation, constituent/aggregate hashes and whitespace: **PASS**.
- Static capability inspection: no network/process/provider/payment/Docker/
  training/evaluation/publication capability.

Two initial gate invocations lacked the legacy test's required `PYTHONPATH`
and produced import-only loader errors.  No code verdict was taken from them;
the corrected command passed 6/6.

## P1-1 — Issuance token does not authenticate current receipt fields

`ProspectiveUpstreamVerification`, `ManifestSetValidation` and
`SyntheticFoundationCommitment` authenticate only possession of a token stored
inside the object. A shallow copy preserves that token. `object.__setattr__`
can then mutate otherwise frozen fields while retaining authenticity.

The reviewer reproduced all of the following:

- copied upstream and manifest receipts accepted unrelated shape-valid hashes;
- a copied public-diagnostic manifest receipt changed to coherent
  `roles=("sealed_final",)`, `episode_count=20` and
  `sealed_final_distinct_dates=20`, then bound a sealed-Final experiment;
- a copied foundation receipt accepted arbitrary replacement hashes;
- `object.__new__` plus a copied authentic token was accepted.

Direct authority-bit expansion, `dataclasses.replace` and pickle round trips
were correctly rejected.  The accepted mutations remain P1 because code
holding one authentic diagnostic receipt can transform its evidence identity
and role without rerunning a validator.

## P1-2 — Live lease membership is not bound to its claim

`EpisodeLease._verify_live` checks only membership of the Python object in a
weak set.  It does not bind that identity to its original store, lease ID,
journal name or lifecycle snapshot.

The reviewer created an authentic lease, closed it unresolved while retaining
the object, created a second registration-only lease, retargeted the stale
object's mutable attributes to the second claim, and successfully advanced the
second lease to `start_snapshotted`.  Fresh constructor handles, shallow-copy
handles, pickle handles and later-state reconstructions were correctly
rejected; stale authentic-object retargeting was not.

## Canonical probe

The canonical JSON adversarial probe recorded:

```text
mutated_foundation_receipt accepted=true
mutated_hash_receipts_bind accepted=true
mutated_public_to_final_receipt accepted=true
object_new_with_copied_token accepted=true
stale_live_handle_retarget accepted=true
authority_bit_expansion accepted=false
constructor_registered accepted=false
constructor_later_state accepted=false
copy_live_handle accepted=false
pickle_live_handle accepted=false
pickle_upstream accepted=false
replace_upstream accepted=false
```

Probe SHA-256:
`1f38c26baf95006ada6acf9b88aa16948d3b50642c21fd23b947426d01f01241`.

## Required repair

For receipts, use identity semantics plus a per-module weak registry that
stores the full frozen issuance snapshot outside the object.  Only the exact
validator/binder-issued identity may validate, and every validation must
compare all current fields to that external snapshot.  Copies, pickle results,
`object.__new__` instances and mutated originals must fail.

For leases, bind the exact live object externally to its immutable store
identity, lease ID, journal name, registration claim, journal head, state,
next slot and early-stop status.  Verify the entire snapshot before any write,
update it only after a verified append, and revoke ownership at terminal state.

## Authority boundary

No real PMB/episode bytes, hidden data, sealed Final, provider, payment,
runtime, training or evaluation were accessed.  The review made no repository
edits, Git mutation, network request, Docker action or publication.  Every
external gate remains blocked.
