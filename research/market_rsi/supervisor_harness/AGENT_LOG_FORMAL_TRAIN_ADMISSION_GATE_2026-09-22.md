# Formal Train admission gate — 2026-09-22

## Scoped verdict: **PASS; integration remains REPLAN**

Implemented and tested a minimal code-owned formal Train admission receipt validator and bound `SupervisorWatchdog.claim_task(...)` training/evaluation claims to the exact validated receipt and exact Train dataset file bytes. The production trusted-receipt registry is deliberately empty, so this change admits **no current artifact**. Non-training watchdog behavior remains compatible and its zero-paid repair canary still passes.

This is not end-to-end training authorization. There is no production training/evaluation runner call site using this API yet, and the new validator must be added to the controlled source manifest by Supervisor integration before a release. No provider/network call, purchase, current-artifact admission, protected/global-state mutation, Dev/Final read, commit, tag or push occurred.

## Problem and reused research record

The read-only critical-path audit found that `SupervisorWatchdog` accepted any syntactically valid 64-hex `data_admission_sha256`; its test used `"8" * 64`. That checked hash shape, not issuer authority, receipt bytes, dataset bytes, rights, coverage, exposure, season or Controller task identity. The same audit required a separate independent admission receipt rather than promoting a Gate 1 request catalog.

This implementation reuses the already-recorded data-admission policy in `AGENTS.md`, `P0_DATA_ADMISSION_ORCHESTRATION_2026-09-18.md`, `P0_DATA_READINESS_DECISION_2026-09-21.md`, `RESEARCH_STATE.md` and `AGENT_LOG_REAL_TRAIN_ADMISSION_CRITICAL_PATH_2026-09-22.md`: access is not rights; missing/unknown evidence fails closed; Train cannot include Dev/Final; complete coverage and exposure evidence must precede training. No live external research was needed or performed because this is an unchanged local authorization/integrity operation, not a new scientific or data-source method.

## Files changed

- New `supervisor_harness/formal_train_admission.py`
  - current SHA-256: `d8ca66434b759954afdadd59a25c02a518f37ec3b7775815692df9c4453a33c7`;
  - exact canonical JSON receipt schema;
  - production `TRUSTED_RECEIPT_COMMITMENTS` is an empty immutable mapping;
  - code-owned commitment must bind exact receipt file SHA-256, schema, independent issuer, dataset ID/hash, sorted season IDs, Controller question ID and exact Controller task SHA-256;
  - rights, coverage and exposure gates must each be `passed` with evidence hashes;
  - `formal_train_admitted=true`, `unknowns_remaining=false`, `dev_data_read=false` and `final_data_read=false` are mandatory;
  - duplicate JSON fields, noncanonical bytes, nonfinite constants, unknown/failed gates and extra/missing fields fail closed;
  - receipt and dataset paths must be absolute, canonical regular files with no symlink component or final symlink;
  - receipt bytes are bounded to 128 KiB; the exact single-file Train bundle is streamed and SHA-256 checked with pre/post device, inode, size, mtime and ctime stability under a 100 GiB hard ceiling;
  - the code-owned receipt is validated before the dataset is read, so an untrusted receipt cannot induce an arbitrary data-file read.
- Updated `supervisor_harness/supervisor_watchdog.py`
  - current SHA-256: `f27a1475c7a5cf959223689e2c6e61f972ccb214673e55ec59553e24257213f2`;
  - training/evaluation now require receipt path, expected receipt hash, exact dataset path, question ID, sorted season tuple and Controller task hash;
  - a digest alone is rejected;
  - accepted journal claims record the validated receipt ID/issuer, dataset ID/path/hash/byte count, question, seasons and Controller task hash;
  - non-training tasks reject any supplied admission fields and otherwise retain their prior payload/behavior.
- New `supervisor_harness/test_formal_train_admission.py`
  - current SHA-256: `4252d46ebbb3218026fa38fd4cfb1de0cb085f92cb3f0a0fbc62682c63bb1509`.
- Updated `supervisor_harness/test_supervisor_watchdog.py`
  - current SHA-256: `77a402b0f7f052471883aa35d96313c17950c549ec6f6c19fb2a9d6213880e61`;
  - replaced the old arbitrary-digest acceptance assertion with a digest-only rejection and an exact-byte synthetic test receipt admitted only under a test-local registry patch.
- This dedicated log only. Per Supervisor instruction, `protocol_source_release.py` was not edited to avoid collision with the v2-cursor worker.

## Exact authority chain

1. The caller names an absolute canonical receipt path and its expected file SHA-256.
2. Validator safely opens the receipt with no-follow behavior, verifies the exact canonical bytes, strict schema, trusted issuer and all fail-closed gate/boundary values.
3. Validator resolves `receipt_id` through the code-owned immutable commitment registry. Caller-supplied issuer, Boolean or digest cannot add authority.
4. The commitment and receipt must agree on exact receipt hash, dataset identity/hash, seasons, Controller question and Controller task hash.
5. Only after that authority passes does the validator safely open the exact dataset path, stream its bytes, reject symlink/path substitution or concurrent mutation, and compare the actual SHA-256 to the code-owned receipt.
6. Only then may `SupervisorWatchdog` append a training/evaluation task claim containing those validated identities.

## Adversarial coverage

The dedicated tests cover:

- production registry empty, so no present artifact is admitted;
- missing issuer and untrusted caller-claimed issuer;
- untrusted receipt rejected before any dataset read;
- exact dataset byte/hash mismatch;
- wrong season set, wrong Controller question and wrong exact Controller task hash;
- rights, coverage and exposure statuses independently set to `failed` or `unknown`;
- residual unknowns, Dev read, Final read, or `formal_train_admitted=false`;
- receipt symlink and receipt byte/path substitution;
- dataset symlink and dataset byte substitution;
- arbitrary digest with no matching bytes, and exact caller-created bytes with no code-owned registry entry;
- digest-only watchdog training claim rejected;
- successful test-only claim journals exact dataset path/hash/size and task bindings.

## Tests run

Focused gate and watchdog suite:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  supervisor_harness.test_formal_train_admission \
  supervisor_harness.test_supervisor_watchdog
```

Result: **23/23 passed**.

Focused plus adjacent non-training watchdog/monitor/fetch suite:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  supervisor_harness.test_formal_train_admission \
  supervisor_harness.test_supervisor_watchdog \
  supervisor_harness.test_supervisor_watchdog_monitor \
  supervisor_harness.test_supervisor_watchdog_local_control \
  supervisor_harness.test_p0_gate1_watched_fetch
```

Result: **37/37 passed**.

Fresh zero-paid non-training canary:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m supervisor_harness.run_supervisor_watchdog_canary \
  --output <fresh-private-tmp>/supervisor-watchdog-formal-train-gate-canary
```

Result: **passed**, `classification=no_material_progress`, restart recovered, old ID not reusable, no paid process, provider cost `$0`; repair-canary SHA-256 `3745af9b72741a330199d3d23eb62b5729e93b600ad1280dfdf859b3edc46aab`.

`git diff --check` passed on all four source/test files. A broader parent-runner import attempt could not start in either available bare Python runtime because the pre-existing `python-dotenv` dependency is absent; no dependency was installed and no network access was requested. The focused and adjacent suites above are fully passing.

## Remaining limitations and mandatory integration work

1. **No real receipt is registered.** This is intentional. Adding one is a reviewed protocol-source change and must not happen until the independent rights/coverage/exposure evidence passes for exact data bytes.
2. **No production training/evaluation call site exists.** Repository search found training/evaluation logic, including direct core functions, but no non-test caller currently claims a watchdog task of kind `training` or `evaluation`. Therefore this component closes the watchdog API flaw but does not claim every legacy/direct trainer is routed through it. Before any formal run, the production runner must make this claim before training/evaluation and must not offer a bypass path.
3. **Post-claim file reuse still needs runner binding.** The watchdog hashes and journals the exact canonical dataset path/bytes at claim time, then closes the descriptor. A future production runner must either consume an already-open descriptor from the validated handoff or revalidate the same path/hash immediately before reading it; otherwise replacement after the claim could create a time-of-check/time-of-use gap. There is no production runner here to implement that handoff.
4. **Single-file bundle contract.** The minimal validator admits one exact regular-file Train bundle. A directory or multi-file dataset must first be packaged into one deterministic bundle or receive a separately reviewed manifest/tree-hash implementation.
5. **Evidence objects are not dereferenced here.** Rights, coverage and exposure evidence hashes are indirectly frozen by the exact code-owned receipt commitment. The independent admission producer/reviewer must validate those evidence files before a receipt hash can be added to source.
6. **Controlled manifest inclusion is pending.** Supervisor integration must add `supervisor_harness/formal_train_admission.py` (and the v2 worker's new controlled modules) to `protocol_source_release.PROTOCOL_FILES`, update its manifest test, recompute the source digest, independently review, and run a new zero-provider release canary. This worker deliberately did not edit the shared manifest.

The scoped code is ready for independent review. Formal Train admission and any production training/evaluation remain blocked.
