# PMB replan v2 repair evidence — 2026-09-28

- Preserved v1: `../PREDICTIONMARKETBENCH_REPLAN_2026-09-28.md`, SHA-256 `d08c213ddaec28abd0b7561811c52ad162713f9b3945f6afdb1d4980ef8ad2f4` (unchanged from independent review).
- V2 amendment: `../PREDICTIONMARKETBENCH_REPLAN_2026-09-28-v2.md`, SHA-256 `39ad796ff16ce88ea0ad01fb813f07a317b93853467e57625c488d239a7ee0e9`.
- P0 hidden-role finding: v2 sections 1 and 5 define disjoint `hidden_dev` and terminal `sealed_final`, independent roots/ledgers, permanent date taint, query cap, no Final feedback and role/date overlap rejection.
- P0 intake-authority finding: v2 section 2 explicitly blocks clone/fetch/submodule, episode and dependency downloads without a separate named authorization.
- P1 aggregate-leakage finding: v2 section 3 fixes cells, minimum support, suppression, non-overlap, query/disclosure ledger, differencing rejection and one Final projection.
- P1 stage-enforcement finding: v2 section 4 makes the complete fsynced experiment spec trusted/read-only with per-round hash checks; Track B has a separate ID and precommitted policy.
- P1 gate-timing finding: v2 section 5 splits pre-open date/role/spec/candidate admission from post-replay common-mask/result admission.
- Negative tests for every finding are listed in v2 section 6.
- `git diff --check` passed; `rg` inspection confirmed every required term and v1 hash remained unchanged.
- Boundary: no network/source/data fetch, provider call, payment, sealed-data read, experiment, protected-state change, release or Git publication.

Verdict: repair PASS, pending fresh independent combined-contract rereview.
