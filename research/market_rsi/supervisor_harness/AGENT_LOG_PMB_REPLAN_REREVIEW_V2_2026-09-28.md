# Independent PMB replan v2 rereview — 2026-09-28

- Preserved v1 expected SHA-256: `d08c213ddaec28abd0b7561811c52ad162713f9b3945f6afdb1d4980ef8ad2f4`.
- V2 amendment expected SHA-256: `39ad796ff16ce88ea0ad01fb813f07a317b93853467e57625c488d239a7ee0e9`.
- Repair evidence expected SHA-256: `295266a4b40f9af5c2ad51b05193ede83b471e48dafd3ebae2015abb257b2306`.
- Required replay: hidden Dev/terminal Final separation; exact intake authorization; small-cell/differencing protection; read-only per-round spec hash; separate precommitted Track B ID; pre-open versus post-replay gates; accepted v1 direction unchanged.
- Boundary: read-only. No network/fetch, provider, payment, sealed-data read, source edit or external write beyond this log.

Verdict: pending.

## Fresh combined-contract rereview — 2026-09-28

- Preserved v1 observed SHA-256: `d08c213ddaec28abd0b7561811c52ad162713f9b3945f6afdb1d4980ef8ad2f4` — exact match.
- V2 amendment observed SHA-256: `39ad796ff16ce88ea0ad01fb813f07a317b93853467e57625c488d239a7ee0e9` — exact match.
- Repair evidence observed SHA-256: `295266a4b40f9af5c2ad51b05193ede83b471e48dafd3ebae2015abb257b2306` — exact match.
- **Verdict: PASS for the combined v1+v2 planning/execution contract.** V2 expressly supersedes v1 on conflicts (v2 line 5), closes every prior P0/P1 finding, preserves the accepted PMB direction and introduces no new payment, fetch, sealed-data, provider, release or publication authority.

### Replay of the prior findings

1. **P0 hidden-Dev versus sealed-Final separation — PASS.** V2 lines 11–24 establish disjoint roots/roles/ledgers, allow iterative aggregate feedback only from `hidden_dev`, permanently taint opened dates, cap queries, reject cross-role or prior-exposure reuse, and make `sealed_final` a one-shot terminal report excluded from Controller packets, archives, prompts and future selection. This narrowly supersedes v1 lines 35, 56 and 120: “aggregate to next round” now means hidden Dev only, never sealed Final. Negative tests at v2 lines 101–103 cover Final-to-Controller leakage, overlap/relabeling/reuse and insufficient Final dates.
2. **P0 network/intake authority — PASS.** V2 lines 28–37 state that the completed `ls-remote` is the sole admitted PMB network action and separately block clone/fetch/submodule/source, public episode, public API/archive and dependency downloads unless a receipt names source, destination and action. V2 line 113 limits the next step to zero-provider local implementation with synthetic fixtures or already admitted bytes and separately gates source intake, episodes, provider execution, sealed data and publication. This removes the ambiguity in v1 line 190 without over-authorizing work.
3. **P1 small-cell/differencing leakage — PASS.** V2 lines 41–51 define role-specific exact schemas, recursive unknown-field rejection, predeclared mutually non-overlapping cells, minimum five-date/ten-market support, suppression without counts/metrics, venue/domain separation, cumulative disclosure ledgers, query caps and rejection of repeated or algebraically derivable projections. Sealed Final receives exactly one projection. V2 line 105 requires adversarial tests for thresholds, overlap, repeated projections and schema/rounding/differencing attacks.
4. **P1 immutable one-stage experiment and separate Track B — PASS.** V2 lines 55–67 place the fsynced complete `experiment_spec` outside Controller/Researcher write authority, bind target/horizon/row mask/baseline/scorer/features/costs/runtime/evaluator/schema and verify its hash around every turn, task, freeze and evaluation. Lines 65 and 69 require Track B to be absent or separately frozen, use a never-reused ID and precommitted policy, bind unchanged Track A prediction and never feed back into Track A. Tests at lines 106–107 exercise shadow/mutation and Track A/B boundary failures.
5. **P1 pre-open versus post-replay gate timing — PASS.** V2 lines 73–85 keep role/date/exposure, chronology, Final >=20 untouched dates, bindings, claim, path and Track-B-policy checks before hidden paths open, while explicitly declining to assert row completeness pre-replay. Lines 87–97 move identical-mask completeness, missingness, deterministic outputs, unchanged commitments and disclosure checks after private replay but before aggregate release; invalid coverage consumes the one-shot claim and releases no scientific metric. Tests at lines 103, 108 and 109 cover the boundary.

### Combined-contract consistency checks

- PMB remains the fixed simulator and the adapter remains thin; v2 line 7 preserves v1's no-rewrite direction. Strict-v0 remains the frozen protected-action lane and `pmb_simple_lane` remains separate.
- The four public January 2026 episodes remain permanently diagnostic and non-promotable. V2 role `public_diagnostic_train` explicitly has promotion use `Never` (line 15).
- Track A remains primary and precedes a separately frozen Track B. The first diagnostic episode still changes only prediction; v2 converts that statement into an enforceable immutable-spec boundary.
- The five-slot, no-resample, persistent-Researcher lifecycle and Controller-Swap rule that only Controller-stack identity changes are untouched. Exact paid model stacks remain unresolved and therefore blocked by v1 lines 132–145 plus v2 line 113.
- V2's role-specific feedback rules, intake denial, Track-B ID and post-replay mask gate are narrower than and explicitly override the corresponding v1 ambiguities; none contradicts the durable local episode-root or append-only evidence requirements.
- No plan-level path/persistence gap remains: v1 supplies the durable non-cloud/non-temporary episode root; v2 requires separate durable roots, private/public separation, no symlink/path escape and immutable ledgers/specifications.

### Test/readiness scope

The negative-test matrix at v2 lines 99–109 covers the five repaired findings plus PMB identity/import drift and path escape. During implementation, the hidden-Dev test should exercise more than one precommitted, disjoint query cohort and terminal allowance exhaustion; the sealed-Final test should prove the terminal namespace is absent from both packet construction and archive/search inputs. These are implementation acceptance details already implied by v2 lines 20–24 and 101–102, not a document-level blocker.

This PASS does **not** attest that code exists, that any negative/upstream/full test has run, that prospective PMB commit `611d66941717310858683278940df21c33c406f2` is an accepted runtime, or that any source/episode/provider/Final/release action is authorized. The only next admitted work is the synthetic, zero-provider local implementation enumerated at v2 line 113, followed by tests and independent review.

### Boundary confirmation

The rereview read only the exact v1, v2 and repair-evidence snapshots plus the existing local review context. It made no network request, source/data/package fetch, provider call, payment, sealed-data read, experiment run, Docker launch, release, commit, tag or push. The only write is this appended rereview record.
