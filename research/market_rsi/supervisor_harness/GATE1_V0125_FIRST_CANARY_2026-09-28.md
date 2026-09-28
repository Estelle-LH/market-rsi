# Gate 1 v0.1.25 zero-provider first-canary record

## Outcome

**PASS**, limited to the zero-provider production-CLI canary. This run is not a Controller-authored research decision, a data-acquisition result, a training run or a prediction experiment.

Permanent run ID: `market-rsi-v0125-gate1-first-current-source-20260928-01`. It ran exactly once with automatic retry disabled and is now permanently consumed.

## Authorized boundary

The user authorized one zero-provider first-current-source bootstrap under the permanent ID above. The run could not call a provider, fetch public data, read or admit Train/Dev/Final, or train. It used the ordinary production CLI and Supervisor parent after the typed bootstrap established the first current-source canary commitment.

## Exact release and runtime binding

- Annotated release: `market-rsi-protocol-v0.1.25`.
- Release commit: `ed4048e55096b763ba763526e768057b5180cdeb`.
- Annotated tag object: `67b8e4a88e22c1f00e60850f521b26282517d682`.
- Controlled source: 339 files, SHA-256 `c61f48e21084671c1ff1257639f6a5d5ccfc8c1a64065e02157c5eb75c10a2d4`.
- Runtime canonical SHA-256: `1faf044ade2390b0d4cdbc18605bb8851f84fb57951849400bed92e0025c83a3`.
- Bootstrap file SHA-256: `12e9e437297a5f4a5dad19731e914b2e2992a579038c7b3202e030ecbaf7deaf`.

## Terminal receipt

- Receipt: `<durable-run-root>/market-rsi-v0125-gate1-first-current-source-20260928-01/canary-result.json`.
- Receipt SHA-256: `187c819a42a90361956145017d34a87f788f83026decfdfa5adc8d3b9e47671f`.
- Child result SHA-256: `d3c559432df0941aa354ecb12d3b6375e621d788057d51eb35c455d351a3be68`.
- Supervisor result SHA-256: `c375dc259d0e41d4a37c5aaa3f9954d923001f3e5bda7ec232eb8552ad36aa0f`.
- Transaction review SHA-256: `84d9aed676be8b4ab4abc08ab4401433455d78724b633018768903347a9e407a`.
- `production_parent_used=true` and `production_cli_arguments_used=true`.
- `provider_calls=0`, `actual_provider_cost_usd=0`, `automatic_retry=false`.
- `public_fetch_performed=false`, `formal_data_admitted=false`, `sealed_data_read=false`.
- No compiled plan, task, proposal, fetch, Train/Dev/Final or training artifact was produced.

The run-local isolated budget journal closed terminal with synthetic metering `$0.00005103`; this is deterministic canary accounting, not provider spend. Its SHA-256 is `860860f5a66eca94662885e9026ad8738a565ed7eb929c1591a89c9522ce63c6`. The run-local global-state journal closed `passed` and has SHA-256 `987ce999ea489454c106fb7e14ada0a6046a0685a018fca9fc43242dbed3fd98`.

The authoritative paid budget journal remained unchanged with SHA-256 `c5d2b018484479cfe4ef6c9a42fa7d687586c1cfb54c7919dadbb8f3761da9b0`; its last paid event remains the terminal v0.1.24 D0 result.

## Independent review and Supervisor replay

An independent read-only reviewer returned PASS. It verified release/source/runtime/bootstrap lineage, production CLI/parent use, the zero-provider/fetch/data/training boundary, isolated ledger and state closure, cleanup and permanent-ID consumption.

The Supervisor independently replayed `verify_gate1_canary_receipt(...)`. It returned `passed=true`, `terminal_cleanup_verified=true` and 30 matching immutable evidence hashes. A fresh `exact_clear(...)` check returned `matching_process_ids=[]` and `matching_container_ids=[]`; the watchdog snapshot has no active task or incident.

## Claim boundary and next gate

This PASS establishes only that the published v0.1.25 zero-provider path is internally bound and fail-closed. It does not establish live GLM authorship, a valid Gate 1 source plan, data rights, formal Train admission, forecast improvement or an experiment result.

The next discriminating step is one paid v0.1.25 Controller D0 under a fresh permanent ID, with at most one provider sample and no automatic retry. That paid action requires separate explicit authorization. Its output must be independently reviewed before any public fetch; fetch, Train/Dev/Final access or admission, and training remain separately gated and unauthorized.
