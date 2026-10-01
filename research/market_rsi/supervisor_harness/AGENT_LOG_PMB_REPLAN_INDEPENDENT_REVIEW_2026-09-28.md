# Independent PMB replan review — 2026-09-28

- Exact document: `../PREDICTIONMARKETBENCH_REPLAN_2026-09-28.md`
- Expected SHA-256: `d08c213ddaec28abd0b7561811c52ad162713f9b3945f6afdb1d4980ef8ad2f4`
- Review matrix: official-source traceability; PMB-not-rewritten; strict-v0 pause/retain; diagnostic-only public episodes; one-stage Track A; Track B after freeze; hidden raw/settlement isolation; Final >=20 untouched dates pre-open; five-slot lease; paired Controller equality; exact unresolved permissions/models; no implied paid/fetch/release authority.
- Boundary: read-only review. No provider, network, data fetch, sealed-Final read, source edit or external write beyond this dedicated review log.

Verdict: pending.

## Fresh exact-snapshot review — 2026-09-28

- Expected SHA-256: `d08c213ddaec28abd0b7561811c52ad162713f9b3945f6afdb1d4980ef8ad2f4`.
- Observed SHA-256: `d08c213ddaec28abd0b7561811c52ad162713f9b3945f6afdb1d4980ef8ad2f4` (`shasum -a 256`); exact-input check **PASS**.
- **Verdict: REPLAN.** The document is directionally sound, but it is not yet a fail-closed execution contract. Do not start a hidden evaluation, PMB/source/episode fetch, paid Controller swap, fresh canary, or release from this snapshot.

### Checks that pass

- Official-source traceability is adequate for a replan: lines 194–196 name the official paper, repository/README and exact read-only ref query, state the overfit/transfer limit, and correctly keep commit `611d66941717310858683278940df21c33c406f2` prospective until checkout, license/tree/dependency/import and upstream-test verification (lines 9–13). This review did not independently fetch the sources; it confirms the document does not elevate README/ref metadata into an accepted runtime.
- PMB remains the fixed execution base. Lines 5, 38 and 54–59 explicitly forbid reimplementation of event ordering, fills, queueing, fees, settlement and standard outputs and confine Market RSI to a thin `Agent`/`AgentContext` adapter plus independent evidence projection.
- The strict-v0 pause/retain boundary is clear at lines 19–22: legacy push/canary/fetch/parser expansion pauses, while authorization, sealed-Final, one-shot, exact-source, append-only and terminal-review controls remain.
- All four January 2026 public episodes are permanently diagnostic: the global rule is at line 7, the first episode is non-promotable at lines 80 and 90, and the four-episode swap is permanently diagnostic at lines 132 and 145.
- The first episode declares prediction as its only changed stage (line 84), makes Track A primary, prohibits Track B optimization during the five research rounds and allows trading evidence only after prediction freeze (lines 88–116). PnL cannot rescue Track A.
- The five-slot/persistent-B design is internally coherent at lines 64–76: four optional task slots, a forced synthesis/freeze fifth slot, no hidden sixth task, no retry/resampling, one persistent non-networked/credential-free container and start/end global snapshots.
- The Controller Swap declares Controller-stack identity as the sole changed factor and holds episode bytes, Supervisor, Researcher, tools, prompts, slots and resource ceilings equal (lines 132–145). It correctly blocks the paid swap because “GLM 3.5”, the frontier stack, adapters/contracts and rates are unresolved.
- The durable episode root at line 46 is outside cloud, temporary and disposable-worktree locations. Formal Final has an explicit pre-open floor of at least 20 distinct untouched UTC dates and chronology/overlap/cohort/claim/candidate checks (line 128).
- Payment, sealed-Final opening and public release remain gated at line 190; no such action is authorized by this document.

### Required corrections before PASS

1. **P0 — separate iterative hidden Dev from terminal sealed Final.** The architecture sends aggregate evidence to the “next Controller round” (line 35), and the Controller may receive prior aggregates (lines 56 and 120), while the same hidden-evaluator section defines one-shot Final claims (lines 118–128). As written, repeated aggregate feedback from the same sealed Final could adaptively overfit it even without raw-row leakage. Define disjoint roles and stores such as `hidden_dev` and `sealed_final`; permanently taint every evaluated hidden-Dev date; cap and ledger adaptive hidden-Dev queries; and make sealed-Final output terminal—never an input to another Controller round. Reject role/date reuse and cross-role manifest overlap before opening.
2. **P0 — make source and episode fetch authorization explicit.** Line 190 preserves exact gates for paid calls, purchases, Final opening and publication, but does not state whether cloning/fetching PMB source or downloading the four public episode files is authorized. Phase 0 “intake” (line 151) and the episode-byte blocker (line 185) could therefore be read as authorization to perform network fetches. State that `git clone/fetch/submodule update`, public episode download/materialization and any other new network fetch require a separately recorded authorization; zero-paid implementation may proceed only from already admitted local bytes or synthetic fixtures until then.
3. **P1 — close aggregate small-cell and differencing leakage.** Lines 125–126 permit support counts plus venue/domain-specific aggregate metrics, but provide no minimum cell size, suppression rule, query budget or protection against differencing across successive candidates/cohorts. Freeze separate exact output schemas for diagnostic hidden-Dev and sealed Final, minimum date/market support per reported cell, non-overlapping cohort projections, and a cumulative disclosure/query ledger. Unknown, undersized or derivable cells must fail closed.
4. **P1 — enforce the one-stage claim, not merely declare it.** Lines 68 and 71 allow candidate-harness changes in a writable workspace; line 92 freezes target construction and missingness rules but does not place the full `experiment_spec`—target, horizon, baseline, row mask, cadence, scorer, costs/latency/exclusions and evaluator—outside Controller write authority or require its hash at every round. Bind and fsync that spec before round 1, mount it read-only, verify its hash before/after every task and evaluator run, and reject mutations. Give the post-freeze Track B diagnostic a separate never-reused ID plus a trading policy committed before any Track B output; otherwise post-hoc trading choices silently add a second causal-stage change.
5. **P1 — split pre-open admission from post-replay coverage.** Line 128 requires a “complete common mask” before any Final bytes are opened, but candidate/baseline row completeness cannot generally be established until the hidden replay runs. Keep date count, untouchedness, chronology, frozen cohort/spec/candidate and one-shot claim as pre-open manifest checks; make identical-row-mask completeness a post-replay, pre-release fail-closed result-admission check. Add negative tests for 0–19 dates, overlap/role reuse, spec/hash drift, symlink/path escape, low-support aggregate cells, repeated/differenced queries, Final-to-next-round feedback, post-hoc Track B policy, incomplete common masks and wrong/dirty/import-diverted PMB.

### Boundary confirmation

This was a read-only review of the exact document and local registered evidence. No network request, provider call, payment, data/source fetch, sealed-Final read, experiment, Docker launch, release, commit, tag or push occurred. The only write is this appended independent-review record.
