# WAITING · P0 candidate-admission integration independent review

- Owner: `capability_contract`
- Plan: `SUPERVISOR_P0_ADMISSION_INTEGRATION_2026-09-22-v1.json`
- Dependency: stable implementation snapshot and exact hashes
- Boundary: independent read-only zero-cost review; no network, provider, Dev/Final, admission, protected state, commit, tag or push

The reviewer is intentionally not dispatched until the implementation step produces a stable snapshot and the ready-step gate passes.

## 2026-09-22 16:59:55 EDT — independent result: REPLAN

The ready-step dependency was present and machine-ready, and the requested
snapshot was stable.  The exact pinned public path reproduces the expected
candidate-only receipt and all existing tests pass.  Independent adversarial
review nevertheless found two causal fail-closed gaps, so this is **REPLAN**,
not a scoped PASS and not release/admission readiness.  The reviewer did not
author or edit the implementation, its test, or the controlled manifest.

### Exact snapshot and manifest reproduction

Commands:

```text
python supervisor_harness/bottleneck_gate.py supervisor_harness/SUPERVISOR_P0_ADMISSION_INTEGRATION_2026-09-22-v1.json --ready-step independent_integration_review
shasum -a 256 supervisor_harness/p0_candidate_admission_integration.py supervisor_harness/test_p0_candidate_admission_integration.py supervisor_harness/protocol_source_release.py supervisor_harness/SUPERVISOR_P0_ADMISSION_INTEGRATION_2026-09-22-v1.json supervisor_harness/AGENT_LOG_P0_ADMISSION_INTEGRATION_IMPLEMENTATION_2026-09-22.md
python - <<'PY'
from market_rsi import digest
from supervisor_harness import protocol_source_release
hashes = protocol_source_release.source_hashes()
print('controlled_files', len(hashes))
print('controlled_digest', digest(hashes))
PY
```

Observed:

- ready-step output: `{"plan": "market-rsi-p0-admission-integration-20260922-01", "ready": true, "step": "independent_integration_review"}`.
- consumer: `cf2e4562cac7a42c18790bfff72948f0f8745c8abe7a94d87303defd56421838`.
- direct test: `4612008482209da9dd09ac7b538c0001b32a0a44cd02f6818a457bedd3580481`.
- controlled manifest source: `5f6345491294da9a1cd2996aedbbd2535d449234220da2e7e20d18848412deb6`.
- plan: `9b5caf99b7b82c44e39a4024ebf474f9ba49c5a4fd9105cb4ea9e93b6403f275`.
- implementation evidence: `632f4690ae218ef6d7b89c0369ef8147c997f56740f35526ba3cc01c401bb7d2`.
- controlled source: 335 files, digest
  `5d650ae3ed43e40ea51f239fd4758b1fbfa7ed669be2407dc1513e62d1f3ac5f`.
- The controlled set contains the ledger builder/test, orientation verifier/test,
  formal-admission validator/test plus watchdog test, v2 cursor module/test,
  integration consumer/test, and `protocol_source_release.py`.  No cited
  runtime component or its directly reviewed test was omitted.
- `pwd -P` was the exact canonical repository.  `stat -f` showed the repository,
  its parent and `supervisor_harness` as ordinary directories, and all three
  reviewed files as ordinary regular files at review time.

### Exact non-test consumer result

Command:

```text
python -m supervisor_harness.p0_candidate_admission_integration | python -c 'import json,sys; from market_rsi import digest; v=json.load(sys.stdin); print(digest(v)); print(v["status"], v["denominator"]["candidate_rows"], v["denominator"]["mapped_oriented_rows"], v["denominator"]["explicitly_unresolved_rows"], v["unresolved_event"]["event_id"], v["claim_boundaries"])'
```

Observed deterministic receipt digest:
`20e884ad20ddf6744cbbf3188fcc55926d1deb51c2eb290562eb26508f0aa345`.
The standalone non-test entry emitted `candidate_only`, exactly
`285 = 284 + 1`, with 284 cursor-candidate streams and event `17330` still the
single explicitly unresolved row.  Rights, provider origin, network execution,
v2 execution receipt validation, formal Train admission, Dev read, Final read
and prediction improvement were all false.  `TRUSTED_RECEIPT_COMMITMENTS`
remained empty.  Repository search found no other non-test caller: the module's
standalone `main()` is the current production-shaped consumer and no training or
evaluation path consumes this receipt yet.

### Existing focused and adjacent regressions

Commands:

```text
python -m unittest supervisor_harness.test_p0_candidate_admission_integration
python -m unittest supervisor_harness.test_p0_candidate_admission_integration supervisor_harness.test_build_2024_train_candidate_ledger supervisor_harness.test_p0_2024_outcome_orientation supervisor_harness.test_formal_train_admission supervisor_harness.test_supervisor_watchdog supervisor_harness.test_p0_polymarket_v2_cursor_acquisition supervisor_harness.test_protocol_source_release
```

Results: focused **13/13 passed** in 0.138s; focused plus adjacent **95/95
passed** in 1.613s.  These suites reproduce rejection of ordinary repository,
file and parent symlink substitution, lexical substitution, observed identity
change, mutable-path reopen, ledger/receipt/orientation mismatch, exact known
authority fields, Dev/Final fields, event-17330 inference/removal, nonempty
formal receipt registry, malformed cursor chains and controlled-manifest
omission.  Passing tests did not cover the two independent counterexamples
below.

### Counterexample 1 — generic authority aliases are accepted

An embedded zero-I/O Python harness loaded the exact retained snapshot, added
one Boolean field to a ledger row, recomputed that row's own commitment and the
ledger/receipt hashes, and called the same semantic `_compose_snapshot`
validator.  This mirrors the direct negative tests without reopening any data.
Observed seven-category matrix:

```text
rights_authorized              REJECTED
provider_verified              ACCEPTED
network_access_authorized      ACCEPTED
formal_training_authorized     ACCEPTED
dev_secret_available           REJECTED
final_secret_available         REJECTED
improvement_claim_allowed      ACCEPTED
```

Thus the generic recursion is asymmetric.  It rejects any key containing
`rights`, `admission`/`admitted`, Dev or Final and a short fixed-name set, but
unknown provider/network/formal-training/improvement authority aliases survive
when true.  The exact public snapshot cannot currently inject them because its
whole-file hash is pinned, and the emitted top-level boundaries remain false;
however, the semantic validator explicitly claims generic authority rejection
and its existing mutation tests call this same boundary.  A later reviewed
ledger schema extension or internal caller could therefore carry an unreviewed
true authority field without failure.  This violates the predeclared generic
authority-escalation pass condition.

Required repair: validate exact allowed row/nested schemas, or use a complete
positive authority-field policy rather than an incomplete substring/field-name
denylist.  Add provider, network, formal-training and improvement alias
counterexamples before claiming closure.

### Counterexample 2 — transient ancestor symlink swap is accepted

An embedded temporary-directory harness created a canonical-looking
`base/repo/nested/value.bin` and an alternate parent tree whose file was a hard
link to the same inode.  After the first lexical/symlink check it atomically
renamed `base`, installed `base -> attacker` as an ancestor symlink for the
absolute `os.open(repo, O_NOFOLLOW|O_DIRECTORY)`, then restored the original
ancestor immediately before the final path check.  `_read_pinned_file` returned
the reviewed bytes instead of rejecting the substitution:

```text
transient_parent_symlink ACCEPTED True component_checks 2
```

The final file identity and SHA-256 remain exact, so this counterexample does
not alter candidate bytes or grant authority.  It does prove that `O_NOFOLLOW`
is applied only to the final component of the absolute repo open; ancestor
directory entries are not held and rechecked descriptor-relative from a stable
root.  A transient parent-path substitution can therefore occur and be restored
between the two pathname checks.  This violates the plan's explicit requirement
to reject parent/path TOCTOU substitution, even though different-inode or
different-byte variants are correctly rejected.

Required repair: open and retain a descriptor chain for every canonical repo
ancestor with no-follow semantics, read all four inputs relative to the pinned
repo descriptor, and verify every retained parent entry identity before close
(or use an equivalent OS primitive that guarantees beneath/no-symlink
resolution).  Add the transient ancestor-swap/hardlink regression.

### Verdict and remaining gates

**REPLAN.** Preserve the current exact snapshot and its passing evidence, but do
not mark `independent_integration_review` or the bottleneck resolved.  Repair the
two causal gaps under a new stable source/test hash, rerun the focused and
adjacent suites, recompute the controlled-source digest and candidate receipt,
then obtain a fresh independent review.

Even after those repairs, offline candidate integration will still not establish
source rights, provider origin/timing, network execution, a validated v2
execution receipt, a code-owned formal Train receipt, Dev/Final eligibility,
prediction improvement, or release status.  Event `17330` must remain explicit,
and a future commit/annotated tag/publication plus release canary require separate
authority.  No network, provider, fetch, purchase, Dev/Final read, protected-state
mutation, commit, tag or push occurred during this review.

### Post-review moving-target notice

After the counterexamples, test runs, exact-hash recheck and REPLAN record were
completed, another parallel workflow changed
`p0_candidate_admission_integration.py`.  A final observation returned
`3d4f9f67923daa265ccd9852d6a447ad29e513dea7b6d840c62262d42dd178b7`
instead of the dispatched `cf2e4562...21838`; at that instant the direct test
and manifest source still had their dispatched hashes.  This review and its
two findings apply only to the exact `cf2e4562...21838` snapshot.  They neither
approve nor reject the new bytes.  The repair snapshot needs its own stable
source/test/manifest hashes, controlled digest, deterministic receipt, focused
and adjacent reruns, and fresh independent review before the plan can resolve.
