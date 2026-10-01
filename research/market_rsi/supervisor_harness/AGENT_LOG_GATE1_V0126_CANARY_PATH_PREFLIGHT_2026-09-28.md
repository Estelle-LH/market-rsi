# v0.1.26 zero-provider canary-path preflight

## 2026-09-28T21:10:39Z — verdict: REPLAN before release or canary

This was a read-only trace in `/Users/estelle/Developer/market-rsi`. I did not edit source, commit, tag, push, verify a remote, run a canary, contact a provider/source, read credentials or catalog/Train/Dev/Final, fetch bytes, reserve budget, claim global state, train or evaluate.

### Finding

The existing production-CLI canary is not the correct functional canary for the new D0-to-request bridge.

- `run_p0_gate1_controller_production_cli_canary.execute_first_canary_bootstrap(...)` correctly verifies a published annotated release before creating output, installs a typed first-current-source bootstrap, uses the real Gate 1 Supervisor parent and production CLI arguments, substitutes an offline provider, creates isolated run-local budget/global state, and produces a receipt that the pure `verify_gate1_canary_receipt(...)` can independently replay.
- Its exact child, `p0_gate1_controller_cli_canary_child.py`, synthesizes a new Controller submission with `model_training`, `train_candidate` and a prospective 60-second horizon, then exercises `p0_gate1_controller_live_entry`. The expected terminal outer result has `compiled_plan_sha256=null`.
- It never imports or calls `p0_gate1_source_scope_request_plan.compile_document_request_plan`, never loads the immutable paid D0 decision/provenance, and never checks request-plan SHA-256 `34b45266df887dbf308b196eac865bfc5a3a6b65257c667849605e5a8b9b812c`. Adding the bridge to `PROTOCOL_FILES` binds its bytes, but does not exercise its semantics.
- `RESEARCH_SUPERVISOR.md` requires the relevant zero-provider/zero-network canary to prove that the valid decision compiles to the exact manifest. Therefore rerunning only the current production-CLI canary would be insufficient evidence for the bridge-to-fetch transition.

The correct repair is one dedicated, release-controlled, no-network bridge canary. It may reuse `bounded_live_supervisor_parent_v1.supervise_started` for exact PID/watchdog/terminal cleanup, but it must have a dedicated child, receipt schema and pure receipt verifier. It must not invoke the Controller adapter, construct a provider, read an environment credential, use a paid budget, touch authoritative global state, or invoke `p0_gate1_public_fetch`/`p0_gate1_watched_fetch`.

### Exact new identity and persistent paths

- Release tag: `market-rsi-protocol-v0.1.26`.
- Permanent canary ID: `market-rsi-v0126-gate1-d0-bridge-first-current-source-20260928-01`.
- Durable run root: `/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0126-gate1-d0-bridge-first-current-source-20260928-01`.
- Dedicated permanent claim: `/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/p0-gate1-source-scope-request-canary-claims-v1/market-rsi-v0126-gate1-d0-bridge-first-current-source-20260928-01.json`.
- Exact absent container identity: `market-rsi-b-market-rsi-v0126-gate1-d0-bridge-first-current-source-20260928-01`.

At this audit snapshot, the run path, claim path and local v0.1.26 tag are absent. Those facts are perishable and must be rechecked immediately before the single invocation. The current candidate is not releaseable yet: the controlled tree contains an uncommitted changed `protocol_source_release.py` and the two untracked bridge source/test files. The present 341-file digest `c80531648d07f83ff73c1c70c3a8c0d5fd5d02459bb1957c875959daa51faee2` is the reviewed bridge candidate, but adding the mandatory canary child/runner/verifier/tests will change it. It must not be used as the v0.1.26 release digest.

### Required safe wiring before source freeze

Add a dedicated module pair (or equivalently separated entry/verifier) under these proposed controlled paths:

- `supervisor_harness/p0_gate1_source_scope_request_plan_canary_child.py` — pure child that loads only exact local evidence, compiles twice, writes the non-executing plan and terminal result, and has no provider/network/fetch/data imports;
- `supervisor_harness/run_p0_gate1_source_scope_request_plan_canary.py` — release verification, fresh-ID/path/claim checks, exact child launch under the Supervisor/watchdog, receipt creation and terminal cleanup;
- `supervisor_harness/source_scope_request_plan_canary_receipt.py` — bounded, duplicate-key-rejecting, path-safe pure verification of the complete evidence tree; the later watched-fetch preflight must consume this verified receipt rather than a bare digest;
- focused adversarial tests for the three modules.

All new runtime modules and their tests must occur exactly once in `protocol_source_release.PROTOCOL_FILES`. The runner must accept no URL, method, headers, query, body, handler, capability, limit, retry or authority input. The child must use only the exact bridge result resolved from trusted code.

The canary must bind the current v0.1.26 publication/runtime and these immutable v0.1.25 D0 inputs:

| Evidence | Absolute path | Exact file SHA-256 |
| --- | --- | --- |
| D0 decision | `/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01/adapter/market-rsi-v0125-gate1-controller-d0-20260928-01/decision.json` | `01054900be9075f0fef57b9e1481abb73f722b2223d664df24db8e6c81dcc216` |
| Controller submission | `/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01/adapter/market-rsi-v0125-gate1-controller-d0-20260928-01/submission.json` | `ed1e391532112f413962d13ab1e6d9718cf92eb0e90ace8caeb31473e4f402d6` |
| Field provenance | `/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01/adapter/market-rsi-v0125-gate1-controller-d0-20260928-01/decision-provenance.json` | `bcd768989e33af91e42ba4d3db35201f294fb6be6d9a3182165f890140eeec65` |
| Raw Controller response | `/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01/adapter/market-rsi-v0125-gate1-controller-d0-20260928-01/raw-response.txt` | `126a5a1309251721a45b86ecc51955083234b60a9b40ffe09f4cf03e0f89fd27` |
| Frozen packet | `/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-first-current-source-20260928-01/controller-input.json` | `bb15603ffd32c8b18b17339ce88aec15294862950d8dc8cb3036485716fe1acd` |
| D0 publication | `/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01/publication.json` | `a11e41473a1ddb70335239e466a46bca63451b85caf8c2771687f48d9210f527` |
| D0 terminal result | `/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01/result.json` | `6c41f67aa9832abc812f5b422e650bccf3724a45f5c5558fbb96434e1536e02e` |
| D0 independent outer review | `/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01/review.json` | `676a549ff9a1289afd08c0ee283182babf528d85ce9f3bcccb2e59a7358d144f` |

The child must rederive and require canonical decision/submission/provenance/packet digests `a4007dfc53d1cda8722e51f2545e95f3666e9d6e3c93c631606809e4f5a763cd`, `71d3b31caa90b05d95578988bf747386390701421d587cdebef571a59bf051fa`, `d1344a446e9e04d9f56337cb60d501c7475869213cec7f67db8e00d11a8f683a`, and `39114563de6f34b100431d02edb0677184a40f83ce9c0d3eda8afe76f963620b`. It must verify that the D0 publication is exactly v0.1.25 commit `ed4048e55096b763ba763526e768057b5180cdeb`, annotated tag object `67b8e4a88e22c1f00e60850f521b26282517d682`, source `c61f48e21084671c1ff1257639f6a5d5ccfc8c1a64065e02157c5eb75c10a2d4`, and that result/review say passed, one source-scope decision, no compiled plan/fetch/admission/retry.

### Required canary behavior and receipt

1. Before creating the run root, verify the published annotated v0.1.26 tag against the exact post-wiring controlled-source digest and current local bytes.
2. Fail if the permanent ID was ever claimed, the run/supervisor/claim path exists or is a symlink, or `exact_clear(ID)` finds a matching process/container.
3. Create the permanent claim with exclusive semantics, binding v0.1.26 publication, runtime, all D0 file/canonical hashes and expected plan hash. `automatic_retry=false`; a failed claim remains consumed.
4. Launch exactly one dedicated child under the existing Supervisor/watchdog. Budget evidence must be literal `state=none`; data gate is `not_applicable`; no authoritative budget reservation and no authoritative global-state claim/revision are permitted.
5. Load only bounded regular non-symlink local files, recheck them after read, call `compile_document_request_plan(...)` twice and require equality plus canonical plan SHA-256 `34b45266df887dbf308b196eac865bfc5a3a6b65257c667849605e5a8b9b812c`.
6. Persist the exact plan with both canonical-object and file-byte SHA-256. Require `plan_only=true`; all execution, network, credential, spend, retention, data, Train/Dev/Final, training, evaluation, repository and publication authority false; future `fetch_authorized=false`.
7. Record `provider_calls=0`, provider cost `0`, `network_request_performed=false`, `external_bytes_received=false`, `public_fetch_performed=false`, `snapshot_retained=false`, `data_admitted=false`, and `automatic_retry=false`.
8. Close the watchdog successfully only after the exact child exits 0 and process/container evidence is absent. Record `old_id_reusable=false`; never auto-retry.
9. The pure receipt verifier must independently replay the complete hash tree and return PASS only for this exact release/runtime/D0/plan/cleanup boundary.

### Exact intended invocation after wiring, review and publication

The command name and permanent ID are fixed below. `<V0126_SOURCE_SHA256>` is intentionally unresolved now: it must be replaced by the independently reviewed post-wiring controlled-source digest, never by the current pre-wiring `c805...` value.

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/market_rsi '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' -m supervisor_harness.run_p0_gate1_source_scope_request_plan_canary \
  --output '/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0126-gate1-d0-bridge-first-current-source-20260928-01' \
  --claim-root '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/p0-gate1-source-scope-request-canary-claims-v1' \
  --release-tag 'market-rsi-protocol-v0.1.26' \
  --expected-source-sha256 '<V0126_SOURCE_SHA256>' \
  --d0-decision '/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01/adapter/market-rsi-v0125-gate1-controller-d0-20260928-01/decision.json' \
  --expected-d0-decision-file-sha256 '01054900be9075f0fef57b9e1481abb73f722b2223d664df24db8e6c81dcc216' \
  --d0-submission '/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01/adapter/market-rsi-v0125-gate1-controller-d0-20260928-01/submission.json' \
  --expected-d0-submission-file-sha256 'ed1e391532112f413962d13ab1e6d9718cf92eb0e90ace8caeb31473e4f402d6' \
  --d0-provenance '/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01/adapter/market-rsi-v0125-gate1-controller-d0-20260928-01/decision-provenance.json' \
  --expected-d0-provenance-file-sha256 'bcd768989e33af91e42ba4d3db35201f294fb6be6d9a3182165f890140eeec65' \
  --d0-raw-response '/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01/adapter/market-rsi-v0125-gate1-controller-d0-20260928-01/raw-response.txt' \
  --expected-d0-raw-response-sha256 '126a5a1309251721a45b86ecc51955083234b60a9b40ffe09f4cf03e0f89fd27' \
  --d0-packet '/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-first-current-source-20260928-01/controller-input.json' \
  --expected-d0-packet-file-sha256 'bb15603ffd32c8b18b17339ce88aec15294862950d8dc8cb3036485716fe1acd' \
  --d0-publication '/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01/publication.json' \
  --expected-d0-publication-file-sha256 'a11e41473a1ddb70335239e466a46bca63451b85caf8c2771687f48d9210f527' \
  --d0-result '/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01/result.json' \
  --expected-d0-result-file-sha256 '6c41f67aa9832abc812f5b422e650bccf3724a45f5c5558fbb96434e1536e02e' \
  --d0-review '/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01/review.json' \
  --expected-d0-review-file-sha256 '676a549ff9a1289afd08c0ee283182babf528d85ce9f3bcccb2e59a7358d144f' \
  --expected-request-plan-canonical-sha256 '34b45266df887dbf308b196eac865bfc5a3a6b65257c667849605e5a8b9b812c'
```

The runner must reject any extra locator/authority option, and the invocation must occur exactly once with no wrapper retry.

### Perishable preflight immediately before that one invocation

- **Source/release:** all controlled paths clean; source hash equals the independently reviewed post-wiring digest; local tag is annotated and immutable; tag commit bytes equal current controlled bytes; remote origin has the exact tag object and peeled commit; `verify_published(...)` passes. Recheck after verification and before output creation.
- **Tests/review:** focused bridge/canary/receipt adversarial tests and the full pinned-runtime suite pass on the same digest; fresh non-author source review passes. Do not rely on the earlier 12/12 or 516/516 after adding canary code without rerunning.
- **Runtime:** use only the durable runtime path above; record Python executable/version, dependency versions, canary runner/child/verifier hashes and runtime canonical digest. All must be included in v0.1.26 source.
- **D0 lineage:** every path above is canonical, regular, non-symlink, bounded and hash-exact; canonical hashes and v0.1.25 publication fields reproduce; D0 independent review remains PASS.
- **Identity/paths:** exact run root, supervisor root and permanent claim are absent and non-symlink; the ID is absent from all dedicated claim/watchdog records; fresh `exact_clear(ID)` has empty process/container matches.
- **Budget:** scope is `none`; no provider constructor, credential, paid-budget object, reservation, dispatch or metering. Snapshot/hash the authoritative budget journal immediately before and after only as independent no-touch evidence; no job may exist for the canary ID.
- **Global state:** this is not a recursive scientific round, so authoritative global-state authority is `none`. Require the authoritative state to be readable and idle, record decision/journal hashes before and after, and make no claim/revision/close event for this canary ID.
- **Boundaries:** no catalog argument, no Train/Dev/Final path, no public fetch module invocation, no network/source permission, no retention/admission/training/evaluation authority, and automatic retry false.

Any changed source/runtime/D0 hash, present path/claim/ID, non-idle state, budget job, residual PID/container, missing review, or inability to prove publication stops before child creation. Because source and release identities are not yet final, the canary is **HOLD** now.

### Required independent post-canary review

The independent reviewer must use the pure verifier and separately confirm:

- v0.1.26 tag/commit/tag-object/current controlled-source and runtime hashes;
- exact D0 file and canonical lineage, including terminal D0 review;
- plan compiled twice, canonical plan hash `34b45266...b9b812c`, exact URL hash `2f12d47b49fc82adafda53effcc7a11edaa9fbd85a6de9b9403cc90f86cfb3fc`, fixed GET/empty query/no body, and all authority false;
- provider calls/cost, source/data network requests, external bytes, fetch, retention, admission, Train/Dev/Final, training and evaluation all zero/false;
- no authoritative budget event/job and unchanged budget journal; no authoritative global-state event and unchanged state journal;
- exact Supervisor claim/command, valid watchdog hash chain, child exit 0, no incident/cleanup, no residual process/container, `old_id_reusable=false`, permanent claim present, and ID consumed;
- immutable receipt/plan/evidence file SHA-256 values and fresh independent `exact_clear(ID)`.

Only that post-canary PASS may establish a current v0.1.26 offline bridge receipt. It still grants no watched fetch, snapshot retention, rights finding, data admission, catalog/Train/Dev/Final access, training, evaluation or experiment claim. The separately authorized watched fetch must use a fresh ID and bind this exact verified canary receipt plus the exact plan hash; it must not reuse the canary ID.
