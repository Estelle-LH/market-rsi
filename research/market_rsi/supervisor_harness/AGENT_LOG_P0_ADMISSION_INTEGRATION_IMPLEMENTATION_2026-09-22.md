# ACTIVE · P0 candidate-admission integration implementation

- Owner: `final_nonexposure_audit`
- Plan: `SUPERVISOR_P0_ADMISSION_INTEGRATION_2026-09-22-v1.json`
- Started: 2026-09-22 16:44 ET
- Boundary: local zero-cost source/tests only; no network, provider, Dev/Final, admission, protected state, Git publication or push

The task is to compose the already reviewed candidate ledger and orientation receipts with the formal Train receipt boundary in a non-test consumer. A successful implementation remains candidate-only and must not convert unresolved rights or provider timing into a pass. Material checks, files, tests and blockers will be appended after evidence exists.

## 2026-09-22 16:50 EDT — implementation result

Scoped result: **implementation complete; ready for independent review**. This is not a release or a formal Train admission. No network/provider call, fetch, purchase, protected/global-state mutation, Dev/Final read, commit, tag or push occurred.

### Problem and reused record

The four offline components had separate reviewed checkpoints, but no production consumer owned their path provenance and immutable bytes end to end. The orientation verifier intentionally accepts bytes, the ledger checkpoint lived in an artifact, the v2 cursor module defines a no-network future acquisition boundary, and the formal Train registry is intentionally empty. Connecting them by passing mutable paths between validators would preserve the check-to-use gap.

This work reuses the already recorded integrity and admission policy in `AGENTS.md`, `AGENT_LOG_CHAT_2024_FULL_DENOMINATOR_REVIEW_2026-09-22.md`, `AGENT_LOG_CHAT_2024_ORIENTATION_REVIEW_2026-09-22.md`, `AGENT_LOG_FORMAL_TRAIN_ADMISSION_GATE_2026-09-22.md`, and `AGENT_LOG_V2_CURSOR_ACQUISITION_CONTRACT_2026-09-22.md`. No new scientific method, provider behavior or rights claim was introduced, so no live search was needed or performed.

Alternatives considered:

1. Pass existing paths independently to each validator. Rejected because a later open could consume substituted bytes.
2. Copy the candidate into a new artifact. Rejected because it adds mutable duplication and was outside the exact write paths.
3. Open exact canonical pinned files once, retain bytes, and pass only those bytes through the semantic validators. Chosen because it closes substitution after the read while preserving the reviewed component boundaries.

### Files and exact hashes

- `p0_candidate_admission_integration.py` — `f03c4f5b01f27ce706edfcd4716ce3b2f54e0ae3c0fc74b690f86d31de64d8e7`
- `test_p0_candidate_admission_integration.py` — `08d9da79a7f578ae941b3774e21549c7c6566e62c41c1e0cee26e75eaf866783`
- `protocol_source_release.py` — `5f6345491294da9a1cd2996aedbbd2535d449234220da2e7e20d18848412deb6`
- controlled-source digest after adding the reviewed modules/tests — `a6d68ce7602422f6f73a8688295bd09e747e9b4c81ce5aa9561567b43da7b03f` across 335 files.

The manifest now contains the reviewed ledger builder/test, orientation verifier/test, formal-admission validator/test, formal-admission watchdog test, v2 cursor module/test, and this integration consumer/test. This changes only a future candidate source snapshot; published `v0.1.21` was not moved, rewritten, verified or claimed current.

### Exact consumer behavior

1. Requires the exact canonical repository and exact pinned `-03` ledger/receipt plus preserved catalog/mapping paths. Every path component is checked for symlinks.
2. Opens the repository and every relative parent directory with descriptor-relative no-follow calls, then opens the file with no-follow behavior. It checks regular-file type and hard byte ceiling, retains bytes, and compares descriptor device/inode/mode/size/mtime/ctime before and after reading. Both the descriptor-relative final entry and canonical pathname must still refer to the opened inode. Exact reviewed SHA-256 is required.
3. All later validators consume retained bytes, not the path. Ledger and receipt use duplicate-key/nonfinite rejection and exact reviewed serialization; all 285 row commitments are recomputed.
4. Calls the reviewed bytes-only orientation verifier and requires 284 ledger rows to match all 284 orientation receipts on game, event, catalog and mapping identity.
5. Requires the sole missing row to remain game `2024_22_KC_PHI`, event evidence `17330`, with no source mapping and no inferred orientation.
6. Builds and revalidates the reviewed v2 cursor manifest/receipt contract for exactly 284 candidate streams. It does not execute a request or validate a live execution receipt.
7. Requires the production formal Train commitment registry to remain empty. A registered/admitted receipt is rejected by this candidate-only consumer rather than silently promoted.
8. Emits only a candidate receipt. Rights, provider origin, network execution, v2 execution validation, formal admission, Dev/Final reads and prediction improvement remain false.

Deterministic output evidence:

- integration receipt digest: `20e884ad20ddf6744cbbf3188fcc55926d1deb51c2eb290562eb26508f0aa345`
- ledger: `1c12f53955d1b80a79896c845a563745c910a639036fa9c1ff280a0990c35819`
- ledger receipt: `245d70bbfbd0e7f4432829640e8da1eca1e620ce94dcbb0971b170cba9c2e38f`
- orientation receipt set: `abc24dd40e43702e89308b6e2df6afd2a2b60c6e87e085d6e8b3f3c13792da70`
- v2 cursor manifest: `30df7fc6af2f759feb24765c91aab30736d6d23187a77cc587cf6661eb601500`
- v2 receipt contract: `c8fdf9863eb821918746eec130c8a5e40b38e0c520a92a8cff14173f396d09a6`
- denominator: 285 candidate rows = 284 mapped/oriented/cursor streams + 1 explicit unresolved row.

### Tests

Focused integration suite: **14/14 passed**. It covers canonical success with no authority; repository, file and parent-symlink substitution; lexical path substitution; descriptor identity change during read; retained-byte use after pathname replacement; transient ancestor-directory symlink replacement with an alternate hardlink to the same file inode; ledger receipt/admission mutation; inserted rights/provider/network/formal-training/improvement authority aliases; any Dev/Final ledger field even when false; ledger/orientation mismatch; inferred event `17330`; formal-registry escalation; and controlled-manifest inclusion.

Combined focused plus adjacent ledger, orientation, formal admission, watchdog, v2 cursor and publication suite: **96/96 passed**. `git diff --check` passed for the four allowed files.

### Remaining gates

- Source rights and provider-origin/timing are unresolved.
- No code-owned formal Train receipt exists; `formal_train_admitted=false` is mandatory.
- No v2 network executor or execution receipt was run or admitted.
- No release exists for these new bytes. Independent review, a future commit/tag/publish action under separate authority, and release canary are still required.
- Event `17330` remains unresolved and is not silently removed from the denominator.

## Independent REPLAN repair — superseding snapshot

The first independent integration review reproduced two causal gaps and issued `REPLAN`:

1. Recommitted ledger rows could add `provider_verified=true`, `network_access_authorized=true`, `formal_training_authorized=true`, or `improvement_claim_allowed=true` because the authority scan recognized only narrower aliases.
2. The source read held only the current parent directory descriptor. A transient ancestor rename/symlink/restore could escape the final pathname check when the alternate file was a hardlink to the same inode.

Both are fixed in the exact hashes above:

- Authority detection now rejects non-false scalar keys across rights, admission/admitted, authorization, provider verification/authentication/access, network access, formal training/data, and improvement claim/proof aliases. Ledger rows and their nested source-binding/source-artifact objects also have exact field sets, so an unrecognized recommitted field fails closed rather than being silently retained.
- The safe read holds the complete repository-to-parent descriptor chain until validation ends. Each directory's device/inode/mode/size/mtime/ctime must remain stable, every descriptor-relative parent/child entry must still match, and every canonical absolute entry must still identify the held descriptor. The deterministic adversarial test renames an ancestor, temporarily installs a symlink to an alternate directory containing a hardlink to the same file inode, restores the ancestor before the final pathname check, and now receives `candidate ancestor directory changed while reading`.

The deterministic integration receipt remains byte-semantically unchanged at `20e884ad20ddf6744cbbf3188fcc55926d1deb51c2eb290562eb26508f0aa345`; only the fail-closed consumer and adversarial tests changed. A fresh independent rereview must bind the superseding hashes above before any scoped PASS.
