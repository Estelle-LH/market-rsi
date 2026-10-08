# v0.1.25 D0 post-transfer budget/state recheck

- 2026-09-28 — Task registered before the authorized allocation transfer. It remains unassigned until the transfer and durable state revision validate. Read-only recheck only; no claim, reservation, credential/provider, fetch, protected-data access or training.

## Independent post-transfer/post-rebind audit — 2026-09-28T20:21:57Z

**Verdict: PASS for this exact snapshot.** The authorized transfer supplies the production runner's fixed `$0.05` reservation, the durable decision document is exactly bound, and the permanent D0 ID remains unused and operationally clear. This PASS grants no fetch, purchase, protected-data read/admission, training, retry, or additional provider authority. The Supervisor must reproduce all mutable gates immediately before the sole launch.

### Authoritative budget replay

- Root: `/Users/estelle/Library/Application Support/MarketRSI/budget-authoritative-20260916-01`.
- `PaidBudget(...)._snapshot()` reproduced cap `$200`, effective cost `$91.508603342`, metered `$85.150022462`, reserved `$2.30`, and global available `$106.191396658`.
- `setup`: allocation `$10.606`, effective `$8.355963188`, reserved `$2.20`, available **`$0.050036812`**. This exceeds the production outer's fixed `$0.05` reservation by `$0.000036812`.
- `repair`: allocation `$19.394`, effective `$0.00223803`, reserved `$0`, available `$19.39176197`.
- Journal tail is sequence `5807`, event `allocation_transfer`, event-chain head **`4c3c98586f6058c2e1c05eb50a29391ce656ea58a6bcddc94b22258b981d0155`**. Its payload records exactly `$0.006` from `repair` to `setup` under the stated standing authority.
- Journal file SHA-256: `b82e3ad984bb71bfba822a77a152a16ab2c0decf79504ef1d13a71d753ed12c8`. It was identical before and after this audit.
- Candidate `market-rsi-v0125-gate1-controller-d0-20260928-01` is absent from all budget jobs by exact and substring search. No reservation, dispatch, metering, settlement, or uncertainty entry exists for it.

### Authoritative global decision state replay

- Root: `/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/research/market_rsi/artifacts/supervisor-global-state-20260917-01`.
- Decision document: `/Users/estelle/Library/Application Support/MarketRSI/control/RESEARCH_STATE.md`.
- `SupervisorGlobalState(...).snapshot()` passed. Decision file SHA-256 and bound state SHA-256 both equal **`6142cd3979d15288b3bda21f288bdd7a93d6bcde13802655d276c5d2e48ed4d6`**.
- State journal tail is sequence `105`, event `decision_revision`; state chain head **`75782ed35c36e7bac5107147598089a653575e74d22d2c8b121c81191b3aa6ce`**.
- State journal file SHA-256: `790e97e42ca3b8180f6bc475037634d31237d7655726cb586f55b984f571352b`. It and the decision document were identical before and after this audit.
- `active_cycle` is `null`. The candidate is absent from both `claimed_cycles` and `completed_cycles`, including substring search.

### ID paths and live-system clearance

- Exact run root absent: `/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01`.
- Exact supervisor root absent: `/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01-supervisor`.
- Exact claim absent: `/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/p0-gate1-controller-claims-v1/market-rsi-v0125-gate1-controller-d0-20260928-01.json`.
- Production `exact_clear("market-rsi-v0125-gate1-controller-d0-20260928-01")` returned schema `market_bounded_live_outer_preflight_v3`, `clear: true`, with empty process and container match lists.

### v0.1.25 canary and publication binding

- Pure `verify_gate1_canary_receipt(...)` replay PASS using the pinned runtime; no credential, provider, budget, global-state, or network operation was invoked.
- Canary receipt SHA-256: `187c819a42a90361956145017d34a87f788f83026decfdfa5adc8d3b9e47671f`.
- Controlled source SHA-256: `c61f48e21084671c1ff1257639f6a5d5ccfc8c1a64065e02157c5eb75c10a2d4`; runtime SHA-256: `1faf044ade2390b0d4cdbc18605bb8851f84fb57951849400bed92e0025c83a3`.
- Publication: tag `market-rsi-protocol-v0.1.25`, tag object `67b8e4a88e22c1f00e60850f521b26282517d682`, peeled commit `ed4048e55096b763ba763526e768057b5180cdeb`.
- Verifier reproduced `passed: true`, `provider_calls: 0`, provider cost `$0`, `public_fetch_performed: false`, `formal_data_admitted: false`, `automatic_retry: false`, and terminal cleanup verified.

### Boundary and commands

- Registered v3 plan SHA-256: `06cf339ccb0fe220fb49037be16e1e7e6ad4801a054ebc5f4b43ab363f0cbe7f`. Its boundary permits only the single D0 invocation under the permanent ID, at most one GLM/Tinker sample, request upper `$0.0389772`, production reservation `$0.05`, and no retry; fetch, purchase, Train/Dev/Final read/admission, training, and a new release remain closed.
- Executed only: pinned-Python `PaidBudget._snapshot()`; `SupervisorGlobalState.snapshot()`; exact job/claim/path membership checks; pure `verify_gate1_canary_receipt(...)`; and production `exact_clear(...)` using read-only `ps`/Docker inventory.
- No claim, reserve, provider construction/call, credential read, fetch, protected-data access/admission, or training occurred.
