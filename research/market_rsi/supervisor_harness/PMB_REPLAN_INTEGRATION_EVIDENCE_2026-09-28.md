# PMB replan integration evidence — 2026-09-28

- Integrated document: `../PREDICTIONMARKETBENCH_REPLAN_2026-09-28.md`
- Integrated document SHA-256: `d08c213ddaec28abd0b7561811c52ad162713f9b3945f6afdb1d4980ef8ad2f4`
- Upstream prospective pin: official `refs/heads/main` -> `611d66941717310858683278940df21c33c406f2` by one read-only `git ls-remote` query.
- Inputs: official paper/repository plus the adapter, hidden-evaluator and Simple-Lane/Controller-Swap registered audits.
- Integration decisions: strict-v0 frozen; PMB simulator not rewritten; separate `pmb_simple_lane`; public January 2026 episodes diagnostic only; Track A before Track B; Final pre-open gate >=20 untouched dates; exact Controller identities unresolved; legacy-NFL-first and `supervisor_harness` placement suggestions excluded.
- Verification: `git diff --check` passed for the integrated document and human logs; source/link/token strings were inspected with `rg`.
- Boundary: no provider call, data download/purchase, sealed Final read, experiment, release, commit, tag or push.

Verdict: integration PASS, pending fresh independent exact-snapshot review.
