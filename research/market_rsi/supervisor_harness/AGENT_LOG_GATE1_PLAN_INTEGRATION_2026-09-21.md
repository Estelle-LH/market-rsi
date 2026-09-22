# Gate 1 plan integration — agent work log

- 2026-09-21 14:48 EDT — Started bounded Wave 2 offline integration. Owner: `gate1_plan_integration`.
- Observed problem: Wave 1 produced a capability registry, deterministic Train-only materializer, and offline trade-query builder, but no trusted compiler yet binds them into one exact request manifest.
- Scope: add one standalone compiler, register only its exact verified rule/handler, add focused tests, and verify both materialization commitments before manifest construction.
- Existing research reused: `AGENTS.md`, `RESEARCH_SUPERVISOR.md`, `RESEARCH_STATE.md`, and the three 2026-09-21 Wave 1 agent logs. No new live search is needed because the operation is unchanged offline integration of already-reviewed modules.
- Hard boundaries: no network/provider/model call, public fetch, Dev/Final access, execution, commit, or push.
- Status: running; result not yet claimed.

## 2026-09-21 15:32 EDT — implementation result

- Added standalone `p0_gate1_plan_compiler.py`. Its public entry is
  `compile_exact_request_plan(decision, packet, catalog_json,
  catalog_commitment_id) -> dict`. It returns bundle schema
  `market_p0_gate1_compiled_plan_bundle_v1` containing the compiled broker
  task, verified materialization, one
  `market_p0_gate1_exact_request_manifest_v1`, a receipt contract, canonical
  commitments, and explicit zero-side-effect claim boundaries.
- Registered exactly one new executable Controller combination:
  source `polymarket_official_trades`, question
  `2025_whole_season_trade_access`, operation `fetch_fixed_public_sample`, and
  exact rule text `Select the first, middle, and last games by game_date and
  game_id from the frozen public Train catalog.`. No similar prose, composite
  operation list, alternate question, or drifted bound is accepted.
- The registry maps that scientific source explicitly to execution source
  `polymarket_public_trades_v1`, rule
  `first_middle_last_by_game_date_game_id_v1`, compiler handler, materializer
  handler and offline request-builder handler. `future_executor_handler_id`
  remains null and `network_execution_authorized=false`; this is an offline
  builder, not an executor.

## Independent Wave 1 audit REPLAN items

1. **Packet alias authority:** `build_p0_gate1_controller_packet.py` now deep
   copies `SOURCE_REGISTRY` and `RIGHTS_POLICY`. The contract also compares
   against independent import-time trusted snapshots. Dedicated regression
   mutates the packet copies and proves neither trusted constant can be
   rewritten and compilation fails closed.
2. **Prior catalog commitment:** the compiler does not accept a caller-supplied
   expected hash. It accepts only a commitment ID resolved from its trusted
   registry. The only current entry is
   `gate1_synthetic_train_catalog_v1`, exact SHA-256
   `33722e897d13213298c00009511e962cfae3b72464cc053345e183dc21a02068`,
   explicitly labelled `synthetic_canary_only`. Any real Train catalog remains
   blocked until a separately reviewed hash is registered in a future version.
3. **Materialization binding:** before building requests, the compiler verifies
   `materialization_sha256`, recomputes
   `request_plan_inputs_sha256`, independently recomputes each selected input
   from the complete committed catalog row, and requires exactly the frozen
   first/middle/last IDs and three sample commitments. The exact manifest binds
   all of those hashes and IDs.
4. **No-gap pagination:** `p0_gate1_trade_query.py` now requires `limit==100`
   when offsets are exactly `[0, 100]`; `limit=50` fails. The compiler supplies
   both values from trusted constants, never from Controller text.
5. **Explicit routing:** the exact manifest records mapping ID
   `polymarket_official_trades_to_public_trade_endpoint_v1`, Controller source,
   execution source, operation, capability ID and the full trusted handler
   chain. URL, endpoint, method, query fields and pagination are produced only
   by the trade-query registry.
6. **Offline/executor boundary:** the manifest contains six exact HTTPS GETs
   but authorizes no network. Its handler chain intentionally has no future
   executor, redirects/auth/payment/writes/retries are disabled, and the bundle
   reports zero calls/fetches and no Dev/Final/formal admission.
7. **Frozen hard ceilings:** the contract compares the packet's full
   `hard_limits` object to trusted constants before using any ceiling. The
   trade capability additionally requires exact trusted bounds of 6 requests,
   2,000,000 bytes, 15 minutes and `$0`; packet expansion and tighter/looser
   Controller values fail closed.

## Verification

- 47/47 compiler + three Wave 1 component tests passed.
- 95/95 focused and adjacent Controller/outer/public-fetch/watchdog tests
  passed under the pinned local Python runtime, including the separate canary
  fixture tests.
- The deterministic synthetic compile produced samples
  `train-game-001,train-game-003,train-game-005`, 6 requests, exact manifest
  SHA-256 `fae89758cd7974c8559a0c8bd253f6f39a72018d492474688ef404405eda9a3d`,
  materialization SHA-256
  `b8a96e3a6c6d80a39439fc839392b74da82d25e9bf7d2362ff381c64ad15a113`,
  and request-plan-input SHA-256
  `784147a202221932dcf7d29221581b54bb3dc8c71085e066d64be76e211ab410`;
  network authorization remained false.
- Full `supervisor_harness` discovery ran 444 tests: 442 passed. Two existing
  environment-dependent tests errored: local socket bind is denied by this
  sandbox, and the retired dual-E2B real-child test exited before a canary
  claim. Neither imports nor exercises the new compiler path. No network was
  authorized or attempted by this work.
- `git diff --check` passed for all files in this bounded task.
- Stable implementation SHA-256: packet builder `f6cbbe19...4c030`, research
  contract `f7dd140d...d833c`, trade query `184dcd87...e8d82`, plan compiler
  `8c806cb0...ca7b0`; focused test files `9e43d294...2d67e`,
  `2c04dc43...9313b`, and `2091f630...e70b`.

## Remaining gates

- No real catalog commitment is registered; current successful compilation is
  synthetic-canary-only.
- There is still no network executor, response validator, runtime
  request/byte/clock ledger, or execution receipt implementation.
- The compiler is not yet wired into the production Controller outer entry,
  watchdog/global-state gate, controlled source manifest, or release receipt.
  Those changes invalidate prior production canaries and need a fresh
  zero-provider/zero-network canary after integration.
- The current bytes changed after the first independent snapshot audit. They
  require a fresh independent stable-diff review before any release-ready
  claim. Publication, provider dispatch and real public fetch remain closed.

- Status: bounded Wave 2 compiler integration complete and locally verified;
  production/executor admission remains blocked by the gates above.
