# v0.1.26 exact fetch-adapter preflight

## 2026-09-28T21:11:37Z — read-only audit

Scope: identify the minimum safe execution seam from the stable v0.1.25 D0 documentation-request bundle to one future v0.1.26 one-shot watched fetch. This audit did not contact Git remotes, the documentation source, any provider, or any credential; did not read Train/Dev/Final or protected data; and did not perform a fetch, release, canary, admission, training, or evaluation. This log is the only edited file.

Audited candidate and boundary commitments:

- current controlled source: 341 files, `c80531648d07f83ff73c1c70c3a8c0d5fd5d02459bb1957c875959daa51faee2`
- bridge source: `469d0f5e548ceb18d3e7aefdce1d8cf36558c1acbcfa110e9c319fe5eddfe9b2`
- bridge tests: `271f817f34de7193763e1deac36ad2771ee85e1db610423b5377fab0b6081733`
- exact request-plan canonical SHA-256: `34b45266df887dbf308b196eac865bfc5a3a6b65257c667849605e5a8b9b812c`
- exact complete bundle canonical SHA-256, independently recomputed: `7f340e20702a03200628cbad06f300257252d06a8b564985cbbf60ad8535b931`
- future-admission-requirements canonical SHA-256, independently recomputed: `d2641c593b83f97722e7fb261b78a87849af5236166645c095f72f5523ab023e`
- `p0_gate1_public_fetch.py`: `76620786849db45ebc3d747bd469fcff65019b9a7b27f5904069fd5e5eb712df`
- `p0_gate1_watched_fetch.py`: `444e8c042b6790e07a6916a074594012fa44b18446afcfb863e8b9166e43f930`
- `gate1_canary_receipt.py`: `40f5916f64e4963c938b6e5af3d6ec27bc8c2400e8cfb7a95182314c12545590`
- `protocol_source_release.py`: `cf65cee14a0304b8664b1c130e6d8966f746487ad88d581aa03a0e0e5c1aaac7`

The already completed offline bridge tests passed 7/7 under the pinned Python 3.12 runtime. No test or command in this audit invoked a transport.

## Exact missing boundary

The bridge output is correctly inert: its bundle/plan schemas differ from the current `market_p0_gate1_broker_task_v3` and `market_p0_gate1_fetch_admission_v1` schemas; `authority.fetch_admission_present`, `request_executable`, `network_fetch_authorized`, and `snapshot_retention_authorized` are false; and no current source file consumes the bundle. Directly passing the bundle, plan, or its `future_fetch_admission_requirements` to `p0_gate1_public_fetch.fetch_snapshot` fails its schema/admission checks.

The missing component is not another planner. It is a trusted, release-bound adapter that verifies the complete exact bundle, consumes a distinct immutable one-shot authorization, creates the only admissible execution task/admission internally, owns a fresh attempt/process/output/watchdog lifecycle, and verifies the terminal response evidence. The existing public fetch cannot be treated as that adapter: it accepts any caller-created object bearing the legacy task schema plus a matching caller-created admission digest and literal `fetch_authorized: true`; it does not know the new plan hash, release, canary, retention authority, attempt registry, or output root. An unreviewed dictionary translation from the new plan into that legacy schema would therefore be a boundary bypass.

The implementation must also close one ambient transport gap before the authorized request: `urllib.request.build_opener(_NoRedirect)` installs the default proxy handler, so ambient `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` state may redirect the connection through an unapproved intermediary even though the URL string is fixed. The v0.1.26 live transport must use `ProxyHandler({})` and a sanitized child environment. It should also reject duplicate case-folded `Content-Type`, `ETag`, or `Last-Modified` response header names rather than selecting the first ambiguous value.

## Minimum fail-closed implementation contract

The smallest safe implementation is two narrow layers plus their tests. Combining them into a caller-side conversion helper is insufficient because the blocked-child/outer-monitor requirement cannot be enforced from the fetching process itself.

### 1. Pure exact adapter: `p0_gate1_source_scope_fetch_adapter.py`

This module should expose a pure preparation/verification function and no transport. Its accepted inputs must be exact objects or safely read exact local artifacts; the callable must have no URL, method, parameter, header, limit, retry, redirect, handler, transport, source, rights, or authority override arguments.

It must:

1. Re-run `compile_document_request_plan` from the exact reviewed D0 decision, provenance, packet, and v0.1.25 D0 source commitment. Require the entire returned bundle to equal the reviewed schema and recompute both bundle SHA `7f340e...b931` and plan SHA `34b452...812c`; do not accept a caller-provided expected hash as authority. Require the future-requirements object and all plan/claim authority fields to remain exactly false.
2. Require current v0.1.26 release evidence: exact annotated tag, full commit, tag object, controlled-source digest, complete `protocol_source_release.source_hashes()`, pinned runtime receipt/digest, and a freshly verified adapter-specific zero-provider canary receipt. Recompute current local source hashes and compare them to the verified publication/canary record. Actual-fetch preflight must use immutable local release/canary receipts and must not contact the Git remote, because the only network destination authorized for the run is the fixed documentation page.
3. Require one immutable canonical authorization document by canonical absolute regular-file path and expected file SHA-256. Its exact closed schema must bind: a never-used attempt ID; the exact bundle and plan hashes; source ID `polymarket_official_trades`; URL SHA `2f12d47b49fc82adafda53effcc7a11edaa9fbd85a6de9b9403cc90f86cfb3fc`; current v0.1.26 tag/commit/tag-object/source/runtime/canary hashes; exact output root; one request; 1,000,000 bytes; 300 seconds overall; 15 seconds transport; zero cost; and all no-redirect/no-retry/no-auth/no-credential/no-purchase/no-write/no-alternate-host/no-link-follow flags. `fetch_authorized` and `immutable_document_snapshot_retention_authorized` must be separate exact booleans and both must be true. Formal admission, Train/Dev/Final, training, evaluation, redistribution, publication, and prediction-improvement authority must remain false. The bridge's false `future_fetch_admission_requirements` can never substitute for this document.
4. Claim the attempt ID in the existing append-only Supervisor global-state journal against its exact expected head, current protected decision-document hash, v0.1.26 source digest, and fresh canary hash before any child or transport is created. The ID must be a safe identifier, must equal the authorized output-root basename, must never have appeared in the journal, and can never be retried under a new directory. A terminal failure closes that exact claim as failed; a successful fetch remains pending independent review and is closed passed only with the review hash.
5. Derive one exact new execution-task schema and one exact new plan-bound fetch-admission schema. Do not manufacture a partial object labelled `market_p0_gate1_broker_task_v3`. The new task/admission must bind the attempt ID, plan hash, authorization file hash, current release/source/runtime/canary hashes, exact source record, exact request fields, exact limits, and retention authority. Construction is internal and returns isolated copies.

### 2. Sole executable parent/child: `run_p0_gate1_source_scope_watched_fetch.py`

This must be the only live CLI. It should use a narrowly extended `p0_gate1_public_fetch` branch for the new exact task/admission schema and reuse `p0_gate1_watched_fetch` for the watchdog state transitions. The legacy fetch path must remain unchanged and must not accept the bridge bundle.

The live CLI must not expose `--url`, method, query, headers, body, source, max-request, max-byte, timeout, retry, redirect, transport, or arbitrary environment inputs. It may accept only exact local artifact paths/hashes, the attempt ID, expected global-state head, current release/runtime/canary commitments, and the exact authorized output root. The live branch must construct `UrlLibTransport` internally; transport injection is test/canary-only and cannot be selected by live CLI arguments.

Before spawning the child, the parent must validate a canonical absolute output root under the approved local MarketRSI runs parent, reject source-tree/temporary/relative/alias paths, retain and recheck stable ancestor `dev+ino+mode`, require safe owner/modes, and create the fresh attempt directory without following symlinks. It derives fixed subpaths for authorization copy, plan, child log, snapshot, watchdog, and terminal result. Existing roots, symlink/hardlink leaves, path replacement, or noncanonical components fail before transport.

The parent must launch one exact child command under the pinned runtime, record and verify the real PID plus stable command SHA-256, initialize a fresh watchdog, and continuously tick the watchdog outside the fetching child. The child task ID is derived from the attempt ID. The existing 20-second heartbeat and 30-second progress deadlines apply; the network call retains its 15-second timeout; the parent has a fixed bounded kill/cleanup ceiling and must prove the child is absent afterward. No container is expected, and budget state is exactly `none` with zero provider/spend cost. Any hang, signal, nonzero exit, identity mismatch, cleanup failure, watchdog incident, or uncertain terminal state is terminal and cannot dispatch again.

`p0_gate1_public_fetch` must enforce the new exact task/admission member sets, plan/authorization/release bindings, GET, the exact URL, empty parameters, null body, exact two trusted headers, one attempt, 1,000,000 bytes, 15-second timeout, zero redirects, and zero retries. `UrlLibTransport` must disable proxies explicitly, retain `_NoRedirect`, and use no ambient cookies/authentication. The child environment must remove proxy, credential-helper, custom CA/trust-store, and Python injection variables; the pinned runtime and source paths are explicit. A distinct host, explicit port, trailing slash, query, fragment, userinfo, alternate encoding, or final URL is rejected.

After the single call, the adapter must independently verify rather than merely relay the public-fetch result:

- exact response receipt schema and members; status 200; allowed normalized content type; request count 1; redirect count 0; exact source/task/URL hashes; and all sealed/formal-admission boundaries false;
- response `Content-Encoding` absent or `identity`; one unambiguous bounded `Content-Type`; only optional unambiguous `etag`/`last-modified` values at most 500 UTF-8 bytes in the receipt;
- `public-source.snapshot` is a safe single-link regular file, 1..1,000,000 bytes, and its bytes match `snapshot_bytes` and `snapshot_sha256`;
- `receipt.json` is canonical sorted compact JSON plus one LF, hashes to the watchdog's final progress/result commitment, and has not changed during verification;
- watchdog journal/snapshot have exactly initialize → task claim → at least one pre-request heartbeat → at least one post-receipt material heartbeat → passed task close, with correct hash chain, task/input/process identities, no incident, and terminal idle state;
- the output/ancestor identities remain stable, the child/container are absent, budget remains none, and the global attempt claim is not reusable.

Write the final adapter result last and exclusively. It must bind every input/release/canary/authorization/task/admission/snapshot/receipt/watchdog/process/output hash and state: one request, zero redirects/retries/provider calls/cost, rights still unknown, snapshot retained only under the one explicit authority, and no data admission or experiment claim. On failure preserve a distinct terminal failure/incident receipt if possible, but never write a success marker. A partial snapshot after a post-response write failure remains evidence under the authorized retention scope and cannot cause a retry.

## Required adversarial tests

The implementation is not releasable unless deterministic tests cover at least:

- bundle/plan/future-requirements missing, extra, reordered-semantics, mutated, caller-rehashed, stale, wrong-schema, or authority-flipped fields; plan-only input without the complete bundle; exact old/current source mismatch;
- decision, provenance, packet, registry, capability, envelope, URL, method, query, body, either header, limits, content types, handler, policy, rights, or claim-boundary mutation;
- direct bridge bundle/plan/future-requirements passed as a fetch task/admission; a forged legacy task plus matching digest; a current legacy fetch admission; a bare plan digest; or an internally derived task/admission mutated between preparation and dispatch;
- absent, extra-field, noncanonical, symlinked, hardlinked, wrong-mode/owner, wrong-hash, wrong-attempt, wrong-output, stale-release/runtime/canary, one-boolean-only, Boolean-as-integer, widened-scope, or reused authorization; `fetch_authorized=true` without retention and retention without fetch must both reject;
- relative/noncanonical/source-tree/temp output, existing root, symlink/ancestor replacement, inode/type/mode change, target mutation, output-name/attempt mismatch, and interrupted writes. Unrelated sibling activity may not create false authority;
- wrong/missing global head, active/reused ID, changed protected decision document, wrong PID/command, no outer monitor, stale/mutated watchdog, missing/reordered heartbeat, watchdog timeout, child hang/signal/nonzero exit, container appearance, non-none budget, and cleanup failure;
- injected transport in live CLI, proxy/custom-CA/Python environment injection, attempted DNS/URL/host/port/query/fragment/trailing-slash change, redirect, retry, second call, alternate page, linked-page/API follow-up, authentication/cookie/range/conditional header, request body, or source write;
- timeout, DNS/TLS/HTTP error, every 3xx/non-200, final-URL difference, empty/non-bytes/oversize body, missing/extra response members, disallowed/oversized/ambiguous content type, duplicate case-folded safe headers, non-identity content encoding, snapshot or receipt mutation, receipt hash mismatch, and second-run attempt;
- success receipt tampering in every hash/state/authority field, attempt to infer rights from HTTP success, or attempt to feed the snapshot into candidate/formal admission, Train/Dev/Final, training, evaluation, redistribution, publication, or a prediction claim.

Tests should assert exact transport call count zero for every preflight/admission mutation and exactly one only for the valid fake/live boundary. They should use a fake transport and temporary paths, never the real network/source.

## v0.1.26 release and zero-provider canary

This adapter can and should be included in v0.1.26 before release; no local `market-rsi-protocol-v0.1.26` tag currently exists. The pure adapter, live parent/child runner, their tests, the adapter-specific canary and verifier/tests, and any required hardening edits to `p0_gate1_public_fetch.py`/`p0_gate1_watched_fetch.py` must all be added to `protocol_source_release.PROTOCOL_FILES` before the controlled digest is frozen. Focused, adjacent, and full offline suites plus an independent integrated review must pass on one stable source digest. Publishing the tag is a separate authorized action and still does not authorize a fetch.

The one fresh zero-provider canary after publication must be adapter-specific and use the same production parent/child, release/runtime/source checks, exact bundle preparation, output safety, watchdog, process identity, cleanup, and terminal-receipt verification. A code-owned canary-only transport may return one fixed synthetic response while a socket/network guard proves no network call; it must be unreachable through live CLI arguments and use a distinct synthetic authorization/schema. The canary must also invoke the live branch without a live authorization and prove rejection before transport. Its immutable receipt must prove:

- exact published v0.1.26 tag/commit/tag-object/controlled source and pinned runtime;
- exact bundle `7f340e...b931`, plan `34b452...812c`, URL and fixed request contract;
- production parent/child used, real PID/command verified, watchdog terminally passed, fresh output, child/container cleanup exact;
- the synthetic transport observed exactly one fixed GET contract, but network requests, provider calls, credentials, external bytes, source fetches, spend, and actual provider cost were all zero;
- every live fetch/retention authority bit remained false in canary mode, the canary ID is permanently consumed, and no canary artifact can satisfy the live authorization schema;
- snapshot/receipt/watchdog/result hashes cross-link and no Train/Dev/Final, candidate/formal admission, training, evaluation, redistribution, release mutation, or prediction claim occurred.

Only after independent verification of that exact canary receipt may the separately authorized fresh-ID live document fetch be claimed. The actual live authorization must bind the canary receipt path and file hash; changing any controlled source/runtime after the canary invalidates it.

## Verdict

**PASS for the preflight design, with implementation still required.** The adapter can be included safely in v0.1.26 before release, but the current 341-file candidate does not yet contain the hash-bound execution adapter or outer live monitor. Do not release or fetch until the exact new task/admission schema, explicit fetch+retention authorization, ambient-proxy hardening, process/watchdog/output checks, terminal receipt verifier, adversarial tests, release inclusion, and adapter-specific zero-provider canary above are implemented and independently reviewed.
