# v0.1.25 D0-to-request bridge gap audit

- 2026-09-28 — Registered before assignment. Read-only source/provenance audit only; no provider, credential, network, fetch, data access, training, release or repository publication.

## 2026-09-28T20:44:58Z — decision-to-capability gap audit

**Verdict: PASS for the read-only audit; the implementation, publication, canary and fetch gates remain closed.** One minimal deterministic offline bridge is identifiable. No existing reviewed production path already performs that bridge.

### Pinned state and immutable input

- The current 339-file controlled-source digest is `c61f48e21084671c1ff1257639f6a5d5ccfc8c1a64065e02157c5eb75c10a2d4`, equal to the plan base and the immutable D0 `publication.json`. The publication binds annotated tag `market-rsi-protocol-v0.1.25`, release commit `ed4048e55096b763ba763526e768057b5180cdeb` and tag object `67b8e4a88e22c1f00e60850f521b26282517d682`.
- The external durable decision state at `/Users/estelle/Library/Application Support/MarketRSI/control/RESEARCH_STATE.md` has SHA-256 `a727445ba25b372eae71e23a21a8f8a0c749435b1b955a7393632e11a8e5f417`; its journal has no active cycle and records the D0 cycle terminally completed. This audit did not mutate either object.
- Immutable D0 file commitments are: packet/input `768905b3b7008f83abe79d420ef6301d3174f50cd7706390e3158276e8838131`, decision `01054900be9075f0fef57b9e1481abb73f722b2223d664df24db8e6c81dcc216`, submission `ed1e391532112f413962d13ab1e6d9718cf92eb0e90ace8caeb31473e4f402d6`, decision provenance `bcd768989e33af91e42ba4d3db35201f294fb6be6d9a3182165f890140eeec65`, raw response `126a5a1309251721a45b86ecc51955083234b60a9b40ffe09f4cf03e0f89fd27`, and adapter result `b24f1571981444e7d916c44b51eb598acafb01f4ee883b142821d11c5f8b4528`.
- Rebuilding locally with the published v0.1.25 code proves: canonical decision SHA-256 `a4007dfc53d1cda8722e51f2545e95f3666e9d6e3c93c631606809e4f5a763cd`, canonical submission SHA-256 `71d3b31caa90b05d95578988bf747386390701421d587cdebef571a59bf051fa`, scope-options SHA-256 `e7834b4946721201feaac1893e356cebd84a3df6eba686d85381cfa612bbd4d0`, and raw-response SHA-256 all equal `decision-provenance.json`; `_scope_submission(...)` and `_decision_provenance(...)` reproduce the archived objects exactly.
- The immutable scientific choice is exactly `src_bbbbbbbbbbbbbbbbbbbbbbbbbb` + `rsp_ffffffffffffffffffffffffff`, use `private_research`, future role `unassigned_candidate`, split `spl_jjjjjjjjjjjjjjjjjjjjjjjjjj` / `7e3985f09cd825cd888232765aaa567a6990700739741c1896f734243f39730e`, descriptive/no-forecast horizon 0, cutoff `cut_kkkkkkkkkkkkkkkkkkkkkkkkkk` / `eff4aa8851da997c8845a43bd137537a08caddb6defeee21355a74e8d567534f`, and one 300-second first-party-document review. Provider requests, provider raw bytes and spend are all zero; all 17 authority bits are false; failure preservation without retry expansion is true.

### Trace and precise gap

1. `build_p0_gate1_controller_packet.py:36-59` already owns the legacy official-source registry, including source `polymarket_official_trades` and exact URL `https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets`. Lines 83-103 own the legacy documentation capability ceilings: one request, 1,000,000 bytes, five minutes, zero provider cost. Lines 112-145 separately own the opaque D0 source/response pairs; lines 122-123 define the selected `src_b...` + `rsp_f...` pair. There is no explicit code-owned crosswalk from that opaque pair to the legacy source record; matching by array position, controller brief, or `PRIOR_CONTROLLER_FEEDBACK` would import an unreviewed inference.
2. `prospective_source_scope_decision.py:108-184,367-385` is reusable for closed-shape, grammar, horizon consistency and all-false authority validation. It intentionally validates opaque ID syntax, not registry membership or pair assignment. Mechanical mutations showed that a valid-looking reassignment (`src_c...` + `rsp_f...`), `unassigned_candidate -> train_candidate`, and an internally consistent cutoff/claim change can each pass this generic validator. Therefore validation alone is not immutable-decision binding.
3. `p0_gate1_controller_adapter.py` is reusable evidence for the original transaction: `_scope_submission` checks the exact registered pair and fixed split/cutoff, while `_decision_provenance` binds decision, submission, packet scope options and raw response. It emits no URL, request or task. An offline reassigned-pair test failed as intended with `ValueError: source and response class are not one reviewed pair`.
4. `p0_gate1_controller_outer.py:100-113` requires a `source_scope_decision` to have no task or compiled plan. Lines 419-437 compile only a `bounded_plan` whose task requests `fetch_fixed_public_sample`. The archived review accordingly has `task_sha256: null`, `compiled_plan_sha256: null`, `public_fetch_performed: false`, `formal_data_admitted: false` and `automatic_retry: false`.
5. `p0_gate1_research_contract.validate_and_compile` plus `p0_gate1_plan_compiler.compile_exact_request_plan` are reusable patterns for trusted registry snapshots, exact member sets, canonical commitments, code-owned URL construction and non-executing manifests, but not implementations for D0. Passing the exact D0 into the legacy compiler fails closed with `ValueError: decision fields differ from frozen contract`. The plan compiler is specifically the catalog-bound public-Train trade-query lane, not a documentation bridge.
6. `p0_gate1_public_fetch.py` and `p0_gate1_watched_fetch.py` are reusable only after this offline bridge and a separate exact fetch admission. They enforce a separately authorized one-request task hash, exact HTTPS URL, no redirects, bounded body, fixed 15-second transport timeout, immutable output and watchdog terminal accounting. They are network executors, so this audit did not invoke them. Their existing task schema cannot consume the D0 decision or the proposed new manifest directly.

The missing capability is therefore one new pure module, appropriately the preregistered `p0_gate1_source_scope_request_plan.py`, containing an explicit injective, code-owned mapping for the selected opaque pair. It must not reinterpret the controller brief, reuse the historical failed attempt's `selected_source_id`, call the legacy compiler with fabricated scientific text, or treat any D0 non-authority flag as execution authorization.

### Minimal deterministic contract

Input should be only `(decision, decision_provenance, packet)` plus exact expected commitments fixed by trusted caller/release. The compiler must revalidate the closed D0 schema, reproduce the provenance links, require the exact cycle/decision IDs and canonical hashes above, require the exact registered `src_b...` + `rsp_f...` pair, and require the exact immutable use/role/split/horizon/cutoff/investigation/non-authority values. Trusted code—not any input URL or prose—then resolves that pair to mapping ID, legacy source ID and official page.

Output should be one canonical object, for example `market_p0_gate1_source_scope_document_request_plan_v1`, containing:

- bindings to cycle ID, decision ID, canonical decision/submission/scope-options/provenance hashes and controlled-source digest;
- a code-owned mapping ID from the exact opaque pair to `polymarket_official_trades`;
- exactly one prospective document request: code-owned request ID, `GET`, the fixed HTTPS URL above and its SHA-256, empty query, no body, and only fixed safe headers;
- separate ceilings: one document, at most one later HTTP attempt, at most 1,000,000 response bytes, at most 300 elapsed seconds, zero provider requests, zero provider spend and zero credentials. The one-request/byte envelope comes from the trusted documentation capability, while the 300-second ceiling is no wider than either D0 or that capability; it is a plan ceiling, not authority;
- fixed policy: `network_execution_authorized=false`, `fetch_admission_present=false`, redirects/authentication/purchase/write/retention/admission/training/Dev/Final/evaluation/publication all false, `max_attempts=1`, `silent_retries_allowed=false`, and failures terminal/preserved;
- claim boundaries stating no request/provider call, bytes, retention, formal admission, role assignment, protected-data read, training or scoring occurred.

Canonical serialization and a canonical SHA-256 must be stable on two rebuilds. The compiler itself must have no transport, filesystem write, credential, provider, budget, process, training or data-import dependency. A later executor must rebuild/compare this exact manifest and require a separate admission bound to its hash; no output field may itself satisfy that admission.

### Required adversarial rejects

- unknown opaque IDs, individually registered IDs combined into an unregistered pair, or any reassignment from the exact `src_b...` + `rsp_f...` mapping;
- decision, submission, provenance, packet/scope-options, controlled-source or cycle/decision hash mismatch, including any post-D0 mutation even when the generic validator still accepts it;
- model/input-supplied URL, host, path, query, parameters, method, headers, body, request ID, mapping ID, capability/handler ID or authority. Current closed D0 validation already rejects added URL/parameter/retry members and any true authority bit; the bridge must also reject unknown arguments rather than ignore them;
- any change of `private_research`, `unassigned_candidate`, split/exposure policy, descriptive/no-forecast horizon 0, cutoff ID/hash/relations, provider-receiver clock separation, one-document/300-second mode, zero provider requests/raw response bytes/spend, or the three fixed stop/preservation flags;
- any request count above one, redirect, authentication/credential, paid access, write, retention, catalog/Train/Dev/Final/evaluation/training/admission/publication claim, or attempt to turn the descriptive review into a forecast/data role;
- any retry/redirect expansion or second attempt. There is no automatic retry of the consumed paid D0 ID and no retry of a later document fetch under the same admission after any response, timeout, malformed body, ambiguity or partial side effect.

### Boundary

This PASS means the gap and one minimal bridge contract are sufficiently precise for the supervisor's integration step after the parallel fetch-boundary audit agrees. It does **not** authorize implementation beyond the preregistered plan, a provider/model call, credentials, network/document/data fetch, budget reservation/spend, role assignment, retention, data admission, training, Dev/Final access, evaluation, publication, commit, tag, push or release.
