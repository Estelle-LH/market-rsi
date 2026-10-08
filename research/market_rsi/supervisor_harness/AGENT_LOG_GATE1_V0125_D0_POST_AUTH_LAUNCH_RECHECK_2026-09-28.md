# v0.1.25 D0 post-authorization launch recheck

- 2026-09-28 — Task registered before the authorized allocation transfer. It remains unassigned until fresh budget and state hashes exist. Read-only replay only; no claim, reservation, credential read, provider construction/call, fetch, protected-data access or training.

## Independent verdict

**PASS for the exact post-authorization launch binding.** The previously blocking setup reservation now fits, the durable decision document and global state reproduce the supplied fresh hashes, and every immutable production argument replays against v0.1.25. This PASS is deliberately perishable: setup headroom above the fixed `$0.05` reservation is only `$0.000036812`, so Supervisor must rerun the budget/ID/path/process/container checks immediately before the sole invocation.

No claim or reservation was created. No credential content was read, no provider/backend/sampler was constructed, and no provider call, public fetch, Train/Dev/Final access or admission, training or score occurred.

## Replayed evidence

- Fresh anonymous publication replay through `protocol_source_release.verify_published(...)` passed: origin `https://github.com/Estelle-LH/market-rsi.git`, annotated tag `market-rsi-protocol-v0.1.25`, tag object `67b8e4a88e22c1f00e60850f521b26282517d682`, peeled commit `ed4048e55096b763ba763526e768057b5180cdeb`, 339 controlled files, current digest `c61f48e21084671c1ff1257639f6a5d5ccfc8c1a64065e02157c5eb75c10a2d4`. Controlled paths are clean.
- Packet `/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-first-current-source-20260928-01/controller-input.json`: file SHA-256 `bb15603ffd32c8b18b17339ce88aec15294862950d8dc8cb3036485716fe1acd`; canonical SHA-256 `39114563de6f34b100431d02edb0677184a40f83ce9c0d3eda8afe76f963620b`.
- Runtime receipt `/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-first-current-source-20260928-01/runtime.json`: file SHA-256 `e36476560b78a5653306d93d4cdb7a4391f92580a9e2749dd6a0dfdbfb4c9ffd`; canonical SHA-256 `1faf044ade2390b0d4cdbc18605bb8851f84fb57951849400bed92e0025c83a3`.
- Prior canary `/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-first-current-source-20260928-01/canary-result.json`: receipt SHA-256 `187c819a42a90361956145017d34a87f788f83026decfdfa5adc8d3b9e47671f`. Fresh `verify_gate1_canary_receipt(...)` replay returned `passed=true` and `terminal_cleanup_verified=true` against the exact release/source/runtime.
- Durable decision document SHA-256 `6142cd3979d15288b3bda21f288bdd7a93d6bcde13802655d276c5d2e48ed4d6`; global-state head `75782ed35c36e7bac5107147598089a653575e74d22d2c8b121c81191b3aa6ce`; journal SHA-256 `790e97e42ca3b8180f6bc475037634d31237d7655726cb586f55b984f571352b`; `active_cycle=null`; candidate absent from `claimed_cycles`.
- Authoritative budget journal SHA-256 `b82e3ad984bb71bfba822a77a152a16ab2c0decf79504ef1d13a71d753ed12c8`. Experiment/cap remain `kalshi-research-glm53-20260907-01` / `$200`; global available `$106.191396658`; setup allocation/effective/reserved/available `$10.606` / `$8.355963188` / `$2.20` / **`$0.050036812`**; candidate job absent. The production `$0.05` reservation now fits without touching Final.
- Offline direct tokenizer replay used revision `aca966e4e02791568aa6a4ced368624b3d897f42` and chat-template SHA-256 `3740abcea51c45830cb3ca562084ad5fb2ef53589376f73332e9886f93ade41c`: exactly 4,020 input tokens and 1,600 maximum output tokens, frozen-rate request upper exactly `$0.0389772`. This loaded only the local tokenizer and constructed no provider backend or sampler.
- Credential path `/Users/estelle/Library/Application Support/MarketRSI/tinker-gate1-20260921.env`: regular non-symlink, mode `0600`, size 90 bytes; contents not opened. Tokenizer cache is a regular durable local directory. Production reads the credential only after release/runtime/packet/canary/state/budget/no-catalog/exact-clear/Supervisor-claim checks.
- Candidate output root, Supervisor root and permanent claim file are absent. Fresh production `exact_clear(...)` returned `clear=true`, `matching_process_ids=[]`, `matching_container_ids=[]`.
- The production parser accepted the complete parent argv with all three catalog arguments absent. Parent argv SHA-256 under canonical JSON encoding: `e81924434c3838da3791e9ff201de9229cefc9c2e33ffab1da3f7843b7702a22`. Its fixed 48-element child command targets only `p0_gate1_controller_live_entry.py`; canonical command SHA-256 `b9b40053d391470c5a2c18870ee389cb59478d8d2252e549209011e9d5f97cfc`.

## Exact one-shot command

Execute only after one final immediate replay still returns the same state hashes, candidate absence, setup available `>= $0.05`, and exact-clear result. Invoke once; do not wrap in a retry and do not add catalog arguments:

```sh
cd '/Users/estelle/Developer/market-rsi'
PYTHONPATH='research/market_rsi' PYTHONDONTWRITEBYTECODE=1 \
  '/Users/estelle/Library/Application Support/MarketRSI/runtimes/ds-py312-20260912-01/bin/python' -B \
  research/market_rsi/supervisor_harness/p0_gate1_controller_supervisor_parent.py \
  --root '/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01' \
  --claim-root '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/p0-gate1-controller-claims-v1' \
  --global-state-root '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/research/market_rsi/artifacts/supervisor-global-state-20260917-01' \
  --decision-doc '/Users/estelle/Library/Application Support/MarketRSI/control/RESEARCH_STATE.md' \
  --budget-root '/Users/estelle/Library/Application Support/MarketRSI/budget-authoritative-20260916-01' \
  --packet '/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-first-current-source-20260928-01/controller-input.json' \
  --runtime-receipt '/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-first-current-source-20260928-01/runtime.json' \
  --env-file '/Users/estelle/Library/Application Support/MarketRSI/tinker-gate1-20260921.env' \
  --tokenizer-cache '/Users/estelle/Library/Application Support/MarketRSI/tokenizer-cache-glm53-20260921-01' \
  --prior-canary-receipt '/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-first-current-source-20260928-01/canary-result.json' \
  --experiment-id 'kalshi-research-glm53-20260907-01' \
  --budget-cap-usd '200' \
  --cycle-id 'market-rsi-v0125-gate1-controller-d0-20260928-01' \
  --expected-packet-file-sha256 'bb15603ffd32c8b18b17339ce88aec15294862950d8dc8cb3036485716fe1acd' \
  --expected-packet-canonical-sha256 '39114563de6f34b100431d02edb0677184a40f83ce9c0d3eda8afe76f963620b' \
  --expected-head-sha256 '75782ed35c36e7bac5107147598089a653575e74d22d2c8b121c81191b3aa6ce' \
  --expected-decision-sha256 '6142cd3979d15288b3bda21f288bdd7a93d6bcde13802655d276c5d2e48ed4d6' \
  --prior-canary-sha256 '187c819a42a90361956145017d34a87f788f83026decfdfa5adc8d3b9e47671f' \
  --release-tag 'market-rsi-protocol-v0.1.25' \
  --expected-release-commit 'ed4048e55096b763ba763526e768057b5180cdeb' \
  --expected-release-tag-object '67b8e4a88e22c1f00e60850f521b26282517d682' \
  --expected-source-sha256 'c61f48e21084671c1ff1257639f6a5d5ccfc8c1a64065e02157c5eb75c10a2d4' \
  --supervisor-root '/Users/estelle/Library/Application Support/MarketRSI/runs/market-rsi-v0125-gate1-controller-d0-20260928-01-supervisor'
```

## Enforced execution and terminal boundaries

- The production adapter/provider path fixes `num_samples=1`, `max_output_tokens=1600`, Tinker `max_retries=0`, retry logic disabled, and `automatic_retry=false`. Neither the parent nor child CLI exposes an override.
- All catalog arguments are absent. The packet and prompt authorize a scope-only D0 response, not an operation. No fetch plan can be compiled without reviewed catalog bytes; fetch, purchase, Train/Dev/Final read/admission, training and scoring remain false and separately gated.
- Before the sole sample, production repeats exact publication/runtime/packet/canary/state/budget/process checks, locally re-encodes the 4,020-token request, verifies `$0.0389772 <= $0.05`, claims the permanent ID and reserves `$0.05`. Any intervening change fails closed before dispatch.
- After termination, require immutable raw response before semantic validation, `provider-receipt.json` with at most one terminal sample and returned-token metering when available, authoritative budget terminal settlement, global-state close, outer review/result or preserved failure, Supervisor result and exact process/container absence. A failure or uncertain terminal state must produce incident/cleanup evidence and must never be retried. Independent terminal review remains mandatory before any downstream action.

At the recorded snapshot, all launch-binding checks pass. This audit itself did not execute the command.
