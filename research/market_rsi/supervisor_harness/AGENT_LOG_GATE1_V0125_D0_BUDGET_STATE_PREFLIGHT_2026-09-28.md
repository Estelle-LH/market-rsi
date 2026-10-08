# v0.1.25 paid D0 budget/state preflight

- 2026-09-28 — Task registered and assigned after explicit authorization for exactly one paid D0 under `market-rsi-v0125-gate1-controller-d0-20260928-01`. Scope is read-only: no claim, reservation, provider construction/call, fetch, protected-data access or training.

## Read-only audit — 2026-09-28T20:09:02Z

**Verdict: REPLAN. Do not claim, reserve, construct/call a provider, fetch, read/admit protected data, or train.** The permanent ID is fresh and every non-budget gate inspected here is clear, but the authoritative `setup` bucket cannot satisfy the production runner's fixed `$0.05` reservation. It has only `$0.044036812` available, a shortfall of exactly `$0.005963188`.

### Authoritative budget

- Root: `<durable-root>/budget-authoritative-20260916-01`.
- Read-only replay used `PaidBudget(...)._snapshot()` rather than a mutating operation. The journal SHA-256 was unchanged before/after replay: `c5d2b018484479cfe4ef6c9a42fa7d687586c1cfb54c7919dadbb8f3761da9b0`.
- Journal tail: sequence `5806`, event `metered_terminal`, chain head `0e6239206bb7a710f2eb5969474198840bbca77b17da626dd42347292e882840`.
- Global cap `$200`; effective cost `$91.508603342`; metered `$85.150022462`; reserved `$2.30`; global available `$106.191396658`.
- `setup`: allocation `$10.60`; effective `$8.355963188`; reserved `$2.20`; available **`$0.044036812`**.
- Candidate ID is absent from all budget jobs (exact and substring search). No reservation, dispatch, metering, settlement, or uncertainty record exists for it.
- The published production outer is SHA-256 `72fe69d56645cb02601ff697d74c86739d377eeff8cafcd99b7f3de4b2ee74c2`; `p0_gate1_controller_outer.py:34` defines `UPPER_USD = Decimal("0.05")`, and line 325 calls `budget.reserve(..., UPPER_USD, ...)`. Therefore the operational reservation requirement is `$0.05`, not merely the request-cost upper `$0.0389772` stated in the registered plan. Launch would fail the protected-allocation gate after other state may already have advanced.

### Authoritative global decision state

- Root: `<durable-root>/self-evolving-v18-local/research/market_rsi/artifacts/supervisor-global-state-20260917-01`.
- Decision document: `<durable-root>/control/RESEARCH_STATE.md`.
- `SupervisorGlobalState(...).snapshot()` passed. Document file SHA-256 and bound state SHA-256 both equal `2f491782f526846cd250bcbe22c6754a408c134f19fc53318a6f7d19bbb9a8ae`.
- State head: `9da325a3bdb24f8edbebdcdc6695cc8407ca85e937b75f35a9493388b4c7b44a`; journal tail sequence `103`, event `decision_revision`; journal file SHA-256 `931dfe4fc000b998ceeda7ae223c441bb51d06ea767d2fdc91dc741240c771f1`.
- `active_cycle` is `null`. Candidate ID is absent from `claimed_cycles` and `completed_cycles`; `last_review_sha256` is the all-zero sentinel from the prior failed close.
- The decision document and both authoritative journals retained identical SHA-256 values across the audit.

### ID, run roots, process and container clearance

- Exact run root absent: `<durable-root>/runs/market-rsi-v0125-gate1-controller-d0-20260928-01`.
- Exact supervisor root absent: `<durable-root>/runs/market-rsi-v0125-gate1-controller-d0-20260928-01-supervisor`.
- Exact claim absent: `<durable-root>/self-evolving-v18-local/artifacts/p0-gate1-controller-claims-v1/market-rsi-v0125-gate1-controller-d0-20260928-01.json`.
- Production `exact_clear("market-rsi-v0125-gate1-controller-d0-20260928-01")` returned schema `market_bounded_live_outer_preflight_v3`, `clear: true`, with empty `matching_process_ids` and `matching_container_ids`.

### v0.1.25 canary and publication binding

- Pure verifier command: pinned runtime `ds-py312-20260912-01` imported `verify_gate1_canary_receipt(...)`; it performs no provider, credential, fetch, budget, or global-state mutation.
- Receipt: `<durable-root>/runs/market-rsi-v0125-gate1-first-current-source-20260928-01/canary-result.json`; SHA-256 `187c819a42a90361956145017d34a87f788f83026decfdfa5adc8d3b9e47671f`.
- Verification PASS: source `c61f48e21084671c1ff1257639f6a5d5ccfc8c1a64065e02157c5eb75c10a2d4`; runtime `1faf044ade2390b0d4cdbc18605bb8851f84fb57951849400bed92e0025c83a3`; tag `market-rsi-protocol-v0.1.25`; annotated tag object `67b8e4a88e22c1f00e60850f521b26282517d682`; peeled commit `ed4048e55096b763ba763526e768057b5180cdeb`.
- Receipt verifies `passed: true`, production CLI/parent and first-canary bootstrap, terminal cleanup, `provider_calls: 0`, cost `$0`, `public_fetch_performed: false`, `formal_data_admitted: false`, and `automatic_retry: false`.

### Authority boundary and required repair

- Registered plan SHA-256 `79294e138b50b10fb64748d85a8e8a20c772d3c721fd8e382b4efaba77cb6fc6` authorizes exactly one D0 sample at most and explicitly grants no public fetch, Train/Dev/Final read or admission, or training. This audit did not access any protected dataset or credential and made no provider call.
- Before launch, obtain explicit authority for an append-only allocation transfer of **at least `$0.005963188`** from an eligible bucket into `setup` (without changing the global cap), then rerun this entire preflight and the immediate launch gates. Do not consume this ID while the shortfall remains.

### Commands/checks executed

- Pinned Python replay of `PaidBudget._snapshot()` and `SupervisorGlobalState.snapshot()`, with SHA-256 capture before and after and exact candidate membership/path checks.
- Pinned Python call to `verify_gate1_canary_receipt(...)` with exact receipt/source/runtime/tag/commit/tag-object inputs.
- Pinned Python call to production `bounded_live_entry_v1.exact_clear(...)`, which performed read-only `ps` and Docker inventory checks.
- `git rev-parse HEAD`, `git rev-parse origin/main`, and tag dereference confirmed current main/origin `6403028a39eae77536e033eef6b505294f1699bb`, peeled v0.1.25 commit `ed4048e55096b763ba763526e768057b5180cdeb`, and tag object `67b8e4a88e22c1f00e60850f521b26282517d682`.
