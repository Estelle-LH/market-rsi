# Real Train admission critical-path audit — 2026-09-22

## Verdict: **REPLAN**

The scoped read-only audit completed. The existing 2024 v2 capture is substantial and internally receipt-backed, but there is no continuous, released path from one valid v0.1.21 Controller decision to source-rights acceptance, a version-correct complete acquisition manifest, full-universe game coverage, and a formally admitted Train catalog. The existing 2024 artifact remains a **candidate source version**, not admitted Train. This review made no provider or network call, purchase, Dev/Final read, data admission, protected-state change, source edit, commit, tag or push. Only this dedicated log was written.

The audit itself passes as a faithful map of the current boundary. The executable/admission path does not pass.

## Exact inspected state

- Canonical checkout HEAD: `f06214b3bb521096078d897fe60ec9ba589c00c6`, exact tag `market-rsi-protocol-v0.1.21`.
- Released packet artifact: `../../artifacts/p0-data-admission-gate1-packet-20260922-03/controller-input.json`, file SHA-256 `c819e55db781b6620cd2c4923afc442027312e082264127e4c1cadf100b6f614`; its receipt says zero model calls, zero fetch and zero admission.
- Controlled source SHA-256 values inspected:
  - `build_p0_gate1_controller_packet.py`: `1f604042332c517b8fa3b6f1903c77b05cc84d942fe4cc1d3413ba2490215da4`
  - `p0_gate1_controller_adapter.py`: `425dd13e13986a51d5ffa8351885e925dd6d15cb7a2a9f313450ca9be3afc64a`
  - `p0_gate1_research_contract.py`: `9c5efe191660dd78111ef09d82d82bd1c800f6a093b9f86f6a80c3bec842a01c`
  - `p0_gate1_sample_materializer.py`: `789d7712b9fdbe02750edb6a81f523c793be38a2ce39511ed8e33bcf95a81192`
  - `p0_gate1_trade_query.py`: `60117c1ea76bfec6bca818d31ae05699f01ebe412ffd1babd1363e8da085784e`
  - `p0_gate1_plan_compiler.py`: `32dd48b10dc7eb7dcde03f9dfa1805729cddc156d54b0423014251cf96969c1e`
  - `p0_gate1_controller_outer.py`: `9a14c98871429565e5d1bc16dfafbe00cb45321e822425f250d56d40fba60644`
- Focused no-network validation actually run:

  ```text
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
    supervisor_harness.test_p0_gate1_controller_packet \
    supervisor_harness.test_p0_gate1_controller_adapter \
    supervisor_harness.test_p0_gate1_research_contract \
    supervisor_harness.test_p0_gate1_sample_materializer \
    supervisor_harness.test_p0_gate1_trade_query \
    supervisor_harness.test_p0_gate1_plan_compiler \
    supervisor_harness.test_p0_gate1_controller_outer \
    supervisor_harness.test_p0_gate1_public_fetch \
    supervisor_harness.test_p0_gate1_watched_fetch
  ```

  Result: **112/112 passed** in 0.237 seconds. This proves the present bounded offline contracts, not real-data admission.

## Critical-path map

| Gate | Exact present path | What can run immediately after a valid plan | Separate authority or missing implementation |
| --- | --- | --- | --- |
| 1. Valid Controller decision | Adapter admits only one of eight short bounded choices or archives a novel proposal. All eight released choices are `inspect_official_documentation`; packet explicitly says `reviewed_real_train_catalog_available=false` (`build_p0_gate1_controller_packet.py:70-106,223-235`; `p0_gate1_controller_adapter.py:112-140`). | Preserve raw response, validate exact packet/claim/provenance, compile the bounded documentation task, independently review it, recompute hashes. | A novel proposal is non-executable. The Supervisor cannot turn a documentation choice into a trade-acquisition choice without replacing the Controller's scientific decision. A new capability/release and then a fresh Controller decision are required if Controller authorship is required for trade acquisition. |
| 2. Source-rights review | Trusted policy treats access as distinct from rights and forbids formal admission. Existing local evidence may be reviewed. The one implemented runner can snapshot one exact documentation URL (`p0_gate1_public_fetch.py:93-150`). | Read existing local source/rights records, record unknowns, and evaluate the exact chosen source without network or state mutation. | Any fresh documentation GET needs an exact task-hash-bound `fetch_authorized=true` admission and network authorization. Ambiguous research/storage/redistribution or third-party data rights require a human/legal scope decision; Controller text cannot grant rights. The joined dataset needs separate decisions for both Polymarket and nflverse. |
| 3. Exact acquisition manifest | A trade compiler exists only for `2025_whole_season_trade_access`, first/middle/last, legacy v1 `/trades`, two fixed offsets `[0,100]`, six requests total (`p0_gate1_research_contract.py:131-177`; `p0_gate1_trade_query.py:31-61,172-228,254-323`; `p0_gate1_plan_compiler.py:179-217`). It explicitly has `future_executor_handler_id=None` and `network_execution_authorized=false`. | Nothing beyond rebuilding the synthetic offline manifest. The only code-owned catalog commitment is `synthetic_canary_only` (`p0_gate1_trade_query.py:38-52`). | There is no released complete-source v2 cursor manifest, executor or receipt validator. A reviewed real catalog is required before the current compiler can compile, while the packet says that catalog must be separately admitted before exposing a trade plan. This is circular for a Controller-led acquisition path. |
| 4. Complete redownload and source-version hash | A past local candidate exists at `../../artifacts/nfl-2024-refresh-20260921-01`. It used `/v2/trades`, every opaque cursor until null, and stored exact realized URLs and raw/stored page hashes. It is not a product of a valid v0.1.21 Controller plan and `git ls-files` returns no controlled files for this artifact. | Recompute local file hashes and independently replay its audit in a scratch copy. A new download is not justified merely because this audit found the artifact. | A future network replay/redownload requires an independently reviewed, versioned v2 cursor state-machine manifest, hard request/byte/time caps, a released executor, exact task admission and separate network authorization. The artifact-local `fetch_v2.py` is not that released executor. |
| 5. Game-level coverage | Artifact-local `audit.py:42-208` verifies the 284 selected mappings, every stored page hash, cursor continuity to null, condition/token identity, derived window rows, PBP hashes and per-game 60/300-second reason reconciliation. | Recompute the recorded hashes; replay the audit offline in scratch; produce a corrected full-universe ledger without touching Dev/Final. | The audit denominator is only 284 mapped games. The source schedule has 285 and the omitted event is `nfl-kc-phi-2025-02-09`, classified `moneyline_missing_or_ambiguous`. Formal policy requires the missing game remain in the denominator. Outcome orientation is also `false`, and provider publication/local-receipt time is unproven. These must fail admission until explicitly resolved or retained as missing. |
| 6. Admitted Train catalog | No formal data-admission producer or validator exists. `market_p0_gate1_train_catalog_v1` contains only request-routing rows: date, game ID, split role, condition, asset IDs and time bounds (`p0_gate1_sample_materializer.py:18-29,79-119`). | Draft/review an admission schema and candidate receipt offline, but do not mark it passed. | Formal admission must be a separate Supervisor/independent-auditor gate bound to rights, source/version, full schedule, missingness, exposure, orientation, clock/target rules, coverage, exact bytes and audit code. A code registry string `evidence_scope=reviewed_real_train_catalog` is not that receipt. Publication/global-state mutation and later training remain separate gates. |

## Findings

### P0 — The released Controller path is documentation-only and cannot reach real acquisition

The current packet's eight choices all resolve to one-page documentation inspection. Although `CAPABILITY_REGISTRY` still describes `fetch_fixed_public_sample`, it is not offered by the released packet, and the live outer runner requires a code-owned commitment with `evidence_scope=reviewed_real_train_catalog` before it will accept supplied catalog bytes (`p0_gate1_controller_outer.py:232-239`). A valid decision therefore yields either a documentation task or a non-executable proposal; it cannot yield the trade plan needed to create the catalog. Retrofitting a documentation decision into a data download would transfer scientific choice from Controller to Supervisor.

**Required replan:** treat documentation/rights resolution as one cycle. Then implement and release the exact source-version acquisition capability, expose only the compatible bounded choice, and obtain a new valid Controller decision. Do not reuse or reinterpret the earlier decision.

### P0 — Current exact manifest is the wrong API and cannot prove a complete capture

The controlled builder pins legacy v1 `https://data-api.polymarket.com/trades`, 100 rows at offsets 0 and 100. The fresh candidate chose the distinct v2 cursor API `https://data-api.polymarket.com/v2/trades`, limit 1000, and followed all cursors. The candidate contains 561 pages and 409,419 raw rows; a six-request, 200-row-per-game v1 sample is neither a replay nor completeness evidence for it. The controlled source registry also freezes the v1/core documentation URL, while the candidate cites the v2 feeds page (`README.md:19-28`).

Opaque cursors mean that all later URLs cannot be enumerated before the first response. The exact predeclared manifest must instead bind: initial URL/query, API version, allowlisted next-cursor transition, invariant query fields, termination condition, repeated/empty cursor rejection, and total pages/bytes/time. Each realized request then needs a receipt. No such released implementation exists.

### P0 — The request catalog can be semantically mismatched and is not a data-admission receipt

The compiler hard-codes the scientific question to **2025**, but the catalog schema has no season/question/source-version/rights/coverage fields and performs no check that row dates are 2025. A hash-registered 2024 catalog could therefore be structurally accepted under a `2025_whole_season_trade_access` task. The commitment record likewise binds only catalog ID/hash/schema, generic source ID/data scope and an evidence-scope string. It does not bind season, intended universe, endpoint version, rights, mapping, exposure or coverage.

This catalog is useful as a deterministic **request catalog**, not as an admitted model-training dataset. Rename or separate those concepts. A full data admission receipt must bind the exact candidate dataset and all independent gate evidence.

### P0 — Training gate presently checks only hash shape, not an admission receipt

`SupervisorWatchdog.claim_task` accepts any syntactically valid 64-hex `data_admission_sha256` for a training/evaluation task (`supervisor_watchdog.py:202-250`). Its own test demonstrates acceptance with `"8" * 64` (`test_supervisor_watchdog.py:134-147`). `record_data_gate` similarly accepts a caller-supplied Boolean and hash without loading or validating an admission object (`supervisor_watchdog.py:287-298`). No non-test producer/validator resolves that hash to an exact dataset, approved issuer, gate results or immutable receipt.

**Required replan:** introduce a code-owned admission receipt schema and validator, resolve exact bytes from an allowlisted immutable location/registry, verify every required field and hash, and have training/evaluation entry points validate it rather than accepting a bare digest.

### P0 — The 2024 artifact is not yet admissible even though the capture is complete

Read-only recomputation found:

- top-level `manifest.json` SHA-256: `699b6d86a48f55fa3719fdc6195babb6b3e7dedeac24d3439f4a4e492c399945`;
- `audit/result.json`: `3a034a51d47350fdf560c9bf89b48d7434cfff2f21e58b67e9af34c4965dfa6b`;
- `audit/per_game.json`: `b5c80a49d1666ff5b4e8e92b96c2de96baa1ee9fb8a5a37dd420c363fe840c71`;
- exact PBP CSV SHA-256 `6ae564c2c49378ec531303292966caee596982278b9fcdad9c9dd0a0dc16bfa7` and deterministic gzip SHA-256 `16eb7af043e705bf6d75c2ea4e59b0b28f49d2ab17ea3e7d68ed2877a308ee7f`;
- 284 mapped/traded games, 561 raw pages, 409,419 raw rows, 407,225 window rows, and 47,875 timed typed plays;
- 60-second coverage 32,384/47,875 = 67.6428%; 300-second coverage 43,506/47,875 = 90.8742%.

However, its own records say `rights_status="not formally resolved"`, `train_admitted=false`, `outcome_orientation_verified=false`, `historical_event_clock_only=true`, and `provider_publish_or_local_receive_proven=false`. Its game audit excludes the one ambiguous/unmapped scheduled game rather than representing it in the full 285-game denominator. Those are admission failures, not documentation omissions.

### P1 — The fresh artifact is useful evidence but lacks controlled lineage

`fetch_v2.py` and `audit.py` are hash-bound inside the artifact, and the audit checks stored response integrity well. They are nevertheless artifact-local, untracked by the released source manifest, not bound to a valid v0.1.21 Controller decision, and not backed by a formal admission issuer. The top-level manifest also needs an external immutable receipt rather than self-description alone. Preserve it; do not overwrite or call it admitted.

### P1 — One documentation page cannot settle rights for the joined dataset

The actual Train candidate joins Polymarket trade prints with nflverse PBP. Formal use needs exact-source/version decisions for research, local storage, derived features/labels and any redistribution for both sources. The current choice mechanism inspects one page from one source, while the artifact README itself notes that code licensing, underlying NFL data rights, CC-BY descriptions and Polymarket research descriptions are not the same grant. Existing local review can continue, but unknown rights must stop admission.

### P2 — Naming currently invites an authority mistake

Comments call the synthetic commitment the “sole admitted catalog,” while every claim boundary correctly says synthetic-only and formal admission false. Use explicit names such as `candidate_request_catalog` / `reviewed_fetch_catalog` versus `formal_train_dataset_admission_receipt` so a future registry edit cannot be mistaken for admission.

## Immediate read-only work versus separately authorized work

### Safe immediately, after a valid plan

1. Preserve and independently validate the Controller response, decision, task, claim, packet and source-release hashes.
2. Review existing local official-source snapshots and rights notes; record `unknown` rather than infer rights.
3. Recompute the existing 2024 manifest/audit hashes:

   ```text
   shasum -a 256 \
     ../../artifacts/nfl-2024-refresh-20260921-01/manifest.json \
     ../../artifacts/nfl-2024-refresh-20260921-01/audit/result.json \
     ../../artifacts/nfl-2024-refresh-20260921-01/audit/per_game.json
   ```

4. Replay `audit.py` only from a private scratch copy, preserving the recorded `audit/` directory separately because the script intentionally creates a fresh output directory. Compare the new result structurally and by deterministic count/hash fields; timestamps will differ. Do not run it in place.
5. Produce a 285-game candidate ledger that includes the ambiguous Super Bowl event with a missing reason, and bind orientation/clock/coverage evidence. This is still a candidate, not admission.
6. Specify and test offline the v2 cursor manifest/executor/receipt contract and the formal admission receipt validator. No network is required for unit tests with frozen responses.

### Requires a separate gate or explicit authorization

- Any new Controller provider call: fresh user authorization, unique ID, release/global-state/budget/process preflight.
- Any official-document, metadata, trade or PBP network request: exact task/manifest admission plus separate network authorization. A complete redownload must use the new v2 versioned executor; no silent retry.
- Any credentials, authenticated access, vendor quote acceptance or purchase: explicit human authorization; the existing experiment cap is not a data-purchase budget.
- Any rights interpretation that changes scope or accepts ambiguous underlying-data terms: explicit human/legal decision.
- Adding a real registry commitment, publishing a new source version, tag or push: independent source review and explicit release/push authorization under the current protocol.
- Marking formal Train admission or mutating protected/global state: Supervisor-owned independent admission gate with a validated exact receipt. Controller, builder, artifact author and watchdog caller cannot self-admit.
- Training/evaluation: only after the admission validator passes; Dev/Final remain outside this path and were not inspected here.

## Minimum viable replan

1. Preserve `nfl-2024-refresh-20260921-01` unchanged as a candidate. Do not redownload first.
2. Resolve exact Polymarket v2 and nflverse rights for this use, or stop with rights unknown.
3. Independently replay the candidate audit in scratch and extend the ledger to all 285 scheduled games; bind orientation, source version, event-time limitations and missingness.
4. Separate a season-bound fetch/request catalog from the full admitted training dataset. Add season, intended universe, question compatibility, endpoint/API version, rights receipt, mapping/exposure/coverage receipts and exact artifact hashes to the appropriate trusted commitments.
5. Implement and independently review a released v2 cursor state-machine manifest, executor and receipt validator. Use a new network fetch only if the preserved capture cannot pass independent review or the Controller's exact new task requires it.
6. Implement a formal Train admission receipt producer/validator and bind the watchdog/training entry to its exact validated bytes, not a bare digest.
7. Publish/re-canary the compatible capability only with separate authorization. Then obtain a fresh Controller decision through that release; do not reinterpret a docs-only decision.
8. Only after rights, full-universe coverage and exact receipt validation pass may the Supervisor mark Train admitted. Training is a later, separately admitted action.

Until these steps pass, the correct status is: **complete 2024 candidate capture available; formal Train catalog absent; Controller-led admission critical path REPLAN**.
