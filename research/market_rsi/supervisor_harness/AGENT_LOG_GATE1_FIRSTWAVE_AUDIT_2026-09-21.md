# Gate 1 Wave 1 independent audit — agent work log

- 2026-09-21 14:46 EDT — Independent read-only audit started. Owner: `gate1_firstwave_audit`.
- Scope: review all three Wave 1 modules and tests for authority, hash, source/operation, split leakage, pagination, bounds and executor-claim gaps.
- Output: P0/P1/P2 findings plus an explicit PASS or REPLAN recommendation.
- Boundaries: no source edits, provider, network, data fetch, commit or push.
- Status: running. Result not yet claimed.

## 2026-09-21 15:19 EDT — Independent result

### Evidence reviewed

- Read `AGENTS.md`, `RESEARCH_SUPERVISOR.md`, `RESEARCH_STATE.md`, and all
  three Wave 1 agent logs before inspecting source.
- Reviewed the complete source and direct tests for
  `p0_gate1_research_contract.py`, `p0_gate1_sample_materializer.py`, and
  `p0_gate1_trade_query.py`, plus the current public-fetch, watched-fetch,
  Controller adapter/outer/live entry, and release-source manifests they must
  compose with.
- Audited source SHA-256 values:
  - research contract: `5666ac7fd95b1102880e8a7d3fc25ff53bf8e9bbe8a629e88ac108b6405ddef2`
  - sample materializer: `789d7712b9fdbe02750edb6a81f523c793be38a2ce39511ed8e33bcf95a81192`
  - trade-query builder: `f4fa4db8b61c56cebabb383a11cc7e1cb39648a2a40477cf34ce63ea73332133`
  - three direct test files: `d34934f220b54ed7ca88c1ff201e0dd9f1e13ffe28b770f5b96b0d9814d4d93b`,
    `569756ab96a3772a0a3544bb21ccfa06b114d25878c77f52e2ef6220e615c4f9`,
    and `1b31af7d706194d10f8b420f3fe69e04cdcd7f6f78ebd7d84f6de82bfe3a1e46`.
- Independently reran the three direct suites plus the existing public-fetch
  and watched-fetch suites with bytecode writes disabled: **44/44 passed**.
  `git diff --check` passed for the tracked contract and its test. The two new
  modules and their tests are still untracked, so a clean published-source
  boundary does not yet contain them.

### P0 findings

- **None in the current offline-only state.** The trade-query component has no
  HTTP transport, is not registered as an executable Controller capability,
  and is not connected to a provider, public fetch, Dev/Final reader, watchdog
  runner, or global-state entry. No network/provider/data action occurred in
  this audit. The P1 defects below would become P0 authority/provenance defects
  if this output were admitted directly to a network executor.

### P1 findings — blocking Wave 1 acceptance

1. **Trusted packet source and rights records are mutable aliases, so the new
   registry check can be made to approve a rewritten URL in-process.**
   `build_p0_gate1_controller_packet.build()` returns
   `list(SOURCE_REGISTRY)` and `RIGHTS_POLICY` without a deep copy (lines
   117–119). A packet entry is therefore the same dict as the supposedly
   trusted module constant. Mutating
   `packet["allowed_sources"][1]["url"]` also mutates
   `SOURCE_REGISTRY[1]["url"]`; the equality check at contract lines 165–167
   then compares the packet with the already-mutated authority, and lines
   184/203 copy that rewritten URL into the compiled task. An independent
   probe printed `aliases_source_registry True` and compiled
   `https://example.invalid/attacker-controlled`. The current regression uses
   `deepcopy(packet)`, so it misses this alias path. The same alias issue exists
   for `RIGHTS_POLICY`. This is not model arbitrary-code execution, but it is a
   real trusted/untrusted object-boundary failure for library callers.

2. **The catalog and selection hashes are self-asserted, not bound across the
   materializer→builder boundary.** The materializer receives both catalog
   bytes and the alleged frozen hash from the same caller (materializer lines
   51–58); it has no trusted precommitted catalog digest or catalog-admission
   receipt to compare against. A caller can construct or relabel any rows as
   `market_train`, hash those bytes, and obtain a valid materialization. The
   trade builder then accepts only the syntax of each `input_sha256` (trade
   lines 66–95); its top-level input has no `materialization_sha256` or
   `request_plan_inputs_sha256`, and it never recomputes the per-row hash.
   An independent probe replaced all three hashes with `f` repeated 64 times;
   six requests were still built and carried those fake hashes. Therefore the
   manifest does not yet prove that its IDs/windows came from the reviewed
   frozen Train catalog. The present split-string checks do not by themselves
   prevent a mislabeled Dev/Final-derived row from being self-committed.

3. **The builder does not enforce the fixed three-sample contract.**
   `validate_input` accepts any nonempty selection list (trade lines 120–126),
   subject only to the request cap. A one-selection input independently
   produced a valid two-request manifest. This permits an integrator bug or
   caller to replace the materializer's first/middle/last sample without
   violating the builder schema. It compounds the missing materialization-hash
   binding above.

4. **Pagination is internally inconsistent for accepted inputs and has no
   completeness/truncation contract.** `limit` may be any value from 1 through
   100 (trade line 108), while offsets must always be `[0, 100]` (lines
   109–112). An independently accepted `limit=50` manifest queried offsets 0
   and 100, silently skipping rows 50–99. Every sample always gets exactly two
   planned pages (lines 166–176), but the receipt contract does not say whether
   a full second page means truncated data, whether a short first page permits
   the second request to be skipped, or what request-count relationship is
   required for terminal success. This prevents an exact, scientifically
   interpretable page/window result.

5. **The source/operation/handler chain is not closed.** The Controller-facing
   registry uses scientific source ID `polymarket_official_trades`, while the
   materializer and builder use execution source ID
   `polymarket_public_trades_v1`. There is no trusted mapping between them.
   `CAPABILITY_REGISTRY` still registers only
   `inspect_official_documentation` with the old one-document handler, and the
   adapter's tool schema imports only that operation. Consequently the
   first/middle/last trade plan correctly remains unselectable, but Wave 1 as a
   whole is not yet an executable-plan closure. Mapping these IDs by convention
   in Wave 2 would be an authority transfer; it must be an explicit trusted
   source×operation×rule×handler record.

6. **The new execution path is not release-, watchdog-, or global-state-bound.**
   Neither new module nor its tests are present in
   `protocol_source_release.PROTOCOL_FILES`; they are also absent from the
   Controller adapter's `_sources()` and the outer runner's
   `REQUIRED_SOURCE_FILES`. A current publication/canary can therefore pass
   without committing these bytes. The only watched Gate 1 handler remains
   `p0_gate1_watched_fetch.run` around the old one-document fetch. The trade
   component is correctly an **offline manifest builder**, not a runner or
   executor: it has no durable watchdog claim, global-state claim, aggregate
   request/byte/clock enforcement, response validator, or receipt validator.
   It must not be labelled executable or network-ready yet.

7. **The contract only partially authenticates the packet's trusted policy.**
   It compares questions, sources, rights policy, and required fields with
   module constants, but takes byte/time ceilings from the caller's
   `packet["hard_limits"]` (contract lines 192–200). A probe raised those two
   packet ceilings and compiled a task with `max_bytes=1000000000000` and
   `max_minutes=1000000000`. The current production adapter's exact-packet
   check blocks this route, and the old document handler independently caps
   bytes/time, but the new public contract is not fail-closed as a standalone
   compiler and a future integrator could accidentally bypass the adapter
   guard.

### P2 findings

1. **Window semantics remain underspecified.** The materializer proves only
   positive `start < end`; it does not bind the timestamps to `game_date`, cap
   window duration, state UTC units, or define inclusive/exclusive endpoints.
   The builder drops `game_date` and relies on the currently unverified
   `input_sha256`. Before empirical interpretation, the trusted catalog schema
   or admission receipt must define and validate those semantics.

2. **The future execution receipt is only a schema description.** No function
   currently validates an execution receipt against `expected_requests`, exact
   URLs/methods, aggregate budgets, row scope, or terminal status. This is
   appropriate for an offline first-wave builder, but callers must not treat
   `build_receipt_contract()` as enforcement.

### Checks that passed

- Unsupported known operations and source/operation/sample combinations fail
  closed in the current Controller compiler.
- Direct model/caller URL, method, arbitrary-query, auth, write, paid, redirect,
  and Dev/Final scope fields are rejected by the strict builder schemas.
- Duplicate JSON members are rejected by all three explicit JSON parsers;
  non-finite constants are rejected by the materializer and fail type checks in
  the other accepted fields.
- The materializer's first/middle/last order is deterministic, its direct
  canonical commitments are stable, and the builder resolves a fixed HTTPS
  host/path without doing I/O.

## Decision: REPLAN

Do not advance this Wave 1 result to a release canary, provider dispatch, or
network fetch. Minimum repair before re-review:

1. Deep-copy/freeze source and rights constants at packet construction and
   compare the complete trusted packet/hard-limit record against immutable
   constants; add alias-mutation and packet-ceiling regressions.
2. Obtain the catalog hash from a separate trusted commitment/admission record,
   validate the exact materialization schema and canonical hash, require and
   verify `request_plan_inputs_sha256`, and recompute/bind each selected row's
   provenance before building requests. Enforce exactly the three materialized
   selections.
3. Add one explicit trusted mapping from Controller source, operation and exact
   rule ID to execution source and handler ID; never infer it from similar names
   or Controller prose.
4. Make pagination coherent (`limit == 100` for offsets `[0,100]`, or derive
   offsets from the fixed limit) and define bounded window plus terminal
   completeness/truncation semantics in a real receipt validator.
5. Add every integrated component to the release/source commitments and bind
   any later network executor to the durable watchdog, global state, exact
   aggregate budgets and response validation. Keep the present component
   labelled `offline builder` until that separate executor passes its canary.

- Final status: **complete, REPLAN**. No source code was changed; only this
  required audit log was updated. No provider, network, public fetch,
  Dev/Final read, commit, or push occurred.

### Concurrent-change notice

- Immediately after the result was written, a concurrent Wave 2 integration
  edit changed `p0_gate1_research_contract.py` from the audited Wave 1 SHA
  `5666ac7f…` to `9a34694f…`. The findings and 44-test result above bind the
  full exact hashes listed under “Evidence reviewed”; they are not an audit of
  the later integration bytes. Some findings may be under active repair, but no
  current-source PASS follows from that. The stable integrated diff requires a
  fresh independent review before any canary/release claim.
