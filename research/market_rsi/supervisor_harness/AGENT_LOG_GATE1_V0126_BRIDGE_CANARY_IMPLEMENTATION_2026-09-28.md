# v0.1.26 D0 bridge canary component implementation

## 2026-09-28T22:05:00Z — component result: PASS

Implemented the dedicated zero-provider, zero-source-network canary component for the exact reviewed v0.1.25 D0-to-request-plan bridge.  This is an offline unpublished component result only.  I did not edit shared fetch/watchdog/protocol-manifest/state files, contact a provider or public source, read credentials, reserve budget, claim global state, run a real canary, create a durable run/claim, read catalog or Train/Dev/Final data, train/evaluate, mutate Git, tag, push, or publish.

## Fixed bindings

- Permanent canary ID: `market-rsi-v0126-gate1-d0-bridge-first-current-source-20260928-01`.
- Fixed durable run root: `<passwd-home>/Library/Application Support/MarketRSI/runs/market-rsi-v0126-gate1-d0-bridge-first-current-source-20260928-01`, where `<passwd-home>` is derived from `pwd.getpwuid(os.geteuid()).pw_dir` and never from `HOME`.
- Fixed durable claim root: `<passwd-home>/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/p0-gate1-source-scope-request-canary-claims-v1`, using the same passwd-derived account root.
- Fixed release tag: `market-rsi-protocol-v0.1.26`; the invocation must additionally supply and match the exact full release commit, annotated tag object and post-integration controlled-source SHA-256.
- Fixed D0 file commitments: decision `01054900...cc216`, submission `ed1e3915...02d6`, provenance `bcd76898...ec65`, raw response `126a5a13...fd27`, frozen first-current-source packet `bb15603f...1acd`, D0 publication `a11e4147...f527`, terminal result `6c41f67a...02e`, and independent review `676a549f...44f`.
- Fixed canonical commitments: decision `a4007dfc...63cd`, submission `71d3b31c...1fa`, provenance `d1344a44...683a`, packet `39114563...620b`, request plan `34b45266df887dbf308b196eac865bfc5a3a6b65257c667849605e5a8b9b812c`, request bundle `7f340e20702a03200628cbad06f300257252d06a8b564985cbbf60ad8535b931`.

## Implemented boundary

- The child loads bounded canonical regular files with duplicate-key/non-finite rejection and before/after file plus ancestor dev/inode/mode stability checks.  It validates the exact D0 lineage and terminal semantics, reconstructs the Controller submission, compiles the bridge twice, requires byte-for-byte equality and the fixed plan/bundle canonical hashes, and writes only a plan-only bundle and zero-effect result.
- The parent accepts no URL, method, query, headers, body, handler, retry, budget, global-state, catalog, split, data, training or evaluation argument.  It binds literal persistent run/claim/D0 paths, recomputes the complete current `protocol_source_release.source_hashes()` mapping against the supplied publication receipt, consumes the permanent ID before launch, uses `python -I` with a minimal `PATH`/locale-only environment, records exact PID/parent-command/container identities, and never automatically retries.
- The parent uses the existing durable `SupervisorWatchdog` and exact local process/container control without modifying them.  A passing path requires pre- and post-compilation material heartbeats, child exit zero, budget state literal `none`, data gate `not_applicable`, no exact container, successful task close with `old_id_reusable=false`, and a second exact-clear receipt.  Outer failures consume the ID and preserve terminal cleanup evidence.
- The pure verifier requires the fixed durable receipt/claim locations and caller-supplied receipt/source/runtime/tag/commit/tag-object commitments.  It replays the complete evidence hash tree and watchdog chain, validates exact member sets and typed zero counters, and returns `market_p0_gate1_source_scope_request_plan_canary_verification_v1`.  Runtime SHA-256 is the canonical runtime-object digest; the byte-level runtime file SHA-256 is retained separately.
- Runtime/child/verifier imports contain no `p0_gate1_public_fetch`, `p0_gate1_watched_fetch`, provider, paid-budget, HTTP client or socket import.  The only release-module use is local full-manifest source hashing; the canary performs no remote publication lookup itself and must consume a separately produced, exact publication receipt.
- Publication-privacy repair: runtime, verifier, tests and this log contain no literal account name or absolute user-home string.  All authoritative persistent paths are derived from the effective UID through the system passwd database; changing the ambient `HOME` cannot redirect them.

## Verification performed

Command:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/market_rsi python3 -B -m unittest -v supervisor_harness.test_p0_gate1_source_scope_request_plan_canary_child supervisor_harness.test_run_p0_gate1_source_scope_request_plan_canary supervisor_harness.test_source_scope_request_plan_canary_receipt
```

Initial result: `13/13 PASS` in `0.043s`.

After the publication-privacy repair and explicit isolated-mode `-B` child launch, the identical command was rerun: `13/13 PASS` in `0.038s`.  A separate `env -i` / `python -I` import probe also reached the child CLI successfully because the child derives its sole source root from its own exact file path before project imports; it does not consume ambient `PYTHONPATH`.

The tests cover deterministic double compilation, exact zero-effect counters, mutated D0 rejection, the real registered frozen-packet file hash when present, forbidden-import AST inspection, symlink and mid-read ancestor replacement rejection, complete controlled-source recomputation, process/container exact-clear, permanent-claim exclusivity, fixed non-cloud paths, minimal environment/no generic locator CLI, full receipt/watchdog replay, `False != typed integer zero`, mutated-bundle rejection, and wrong durable-root rejection.

A separate read-only check against the actual persistent D0 files also passed and reproduced:

```text
same True
plan 34b45266df887dbf308b196eac865bfc5a3a6b65257c667849605e5a8b9b812c
bundle 7f340e20702a03200628cbad06f300257252d06a8b564985cbbf60ad8535b931
packet_file bb15603ffd32c8b18b17339ce88aec15294862950d8dc8cb3036485716fe1acd
```

## Component file SHA-256

| File | SHA-256 |
| --- | --- |
| `p0_gate1_source_scope_request_plan_canary_child.py` | `61850f4f0a306d36ea5b938e79f82ee3cef28f34d10820bde1edad3a45241f62` |
| `run_p0_gate1_source_scope_request_plan_canary.py` | `5931ae7baa6120d9aeb69f0fc4ff859be3a3d247a6bd51bd3c0ae11ddd9c297c` |
| `source_scope_request_plan_canary_receipt.py` | `a1d3d7f114af84b8a72fd4c99caeefd42b9f5b3f3aa5991cecb0f9d452fd4017` |
| `test_p0_gate1_source_scope_request_plan_canary_child.py` | `97066fdcfd706b1ce6cc8b8ca50cbfced00824033db6b352d56d2da6de8908ab` |
| `test_run_p0_gate1_source_scope_request_plan_canary.py` | `7921145505067fbd86d98d232e3c895c7243ab48a006d5ce4051500b3126e903` |
| `test_source_scope_request_plan_canary_receipt.py` | `4ed6162cf866aa7c3b7156a4e5d8a6be2a212f599dd233b37a48edc5593d642a` |

## Remaining integration needs

1. Independently review this component and the sibling exact fetch component together; reconcile the verifier call already fixed as `verify_canary_receipt(receipt_path, *, expected_receipt_sha256, expected_source_sha256, expected_runtime_sha256, expected_release_tag, expected_release_commit, expected_release_tag_object)`.
2. Add each new runtime module and test exactly once to `protocol_source_release.PROTOCOL_FILES`; complete the separately assigned shared proxy/header/schema integration without changing this component's fixed authority boundary.
3. Run the combined adversarial tests and the full pinned-runtime suite on the final integrated controlled-source digest, then perform fresh non-author review.
4. Commit, create and publish the immutable annotated v0.1.26 tag; produce a durable exact publication receipt containing the full source-hash mapping.  Do not move the tag.
5. Re-run the full perishable preflight: clean controlled tree, exact release/runtime/D0 hashes, absent run/claim/ID/process/container, authoritative budget no-job/unchanged evidence, and authoritative global-state idle/unchanged evidence.
6. Invoke the canary exactly once with the fixed ID and no wrapper retry, then perform the separately registered independent terminal receipt/exact-clear review.  Only that review may unlock the separately authorized fresh-ID one-shot fixed-page fetch.

This component PASS grants no release, canary execution, provider/model call, public fetch, snapshot retention, rights finding, data admission, catalog or Train/Dev/Final access, training, evaluation, publication of fetched bytes, or prediction claim.
