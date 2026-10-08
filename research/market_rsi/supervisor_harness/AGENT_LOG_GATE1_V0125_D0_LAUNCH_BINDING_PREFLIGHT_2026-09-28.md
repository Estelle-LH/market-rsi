# v0.1.25 paid D0 launch-binding preflight

- 2026-09-28 — Task registered and assigned after explicit authorization. Derive and audit the exact one-shot production entry and arguments only. Do not claim the ID, reserve budget, construct/call a provider, fetch, access protected data or train.

## Independent read-only verdict

**REPLAN / HOLD. Do not launch this ID from the current snapshot.** The immutable v0.1.25 launch binding is internally consistent, but the current production transaction requires a fixed `$0.05` setup-bucket reservation while the authoritative setup bucket has only `$0.044036812` available. In addition, the durable decision document has not yet been revised to record this v0.1.25 paid authorization, so there are no truthful post-authorization values for the two required state-hash arguments.

No claim, reservation, provider object/call, public fetch, protected-data access or training occurred in this audit. The credential contents were not read.

## Frozen immutable binding

- Sole production entry: `research/market_rsi/supervisor_harness/p0_gate1_controller_supervisor_parent.py`. Do not invoke `p0_gate1_controller_live_entry.py` directly. The parent fixes the child path, binds its PID/command in the Supervisor claim, and supplies the exact task-derived absent container name `market-rsi-b-market-rsi-v0125-gate1-controller-d0-20260928-01`.
- Local release identity: origin `https://github.com/Estelle-LH/market-rsi.git`; annotated tag `market-rsi-protocol-v0.1.25`; tag object `67b8e4a88e22c1f00e60850f521b26282517d682`; peeled commit `ed4048e55096b763ba763526e768057b5180cdeb`. All 339 controlled paths are clean and their current digest is `c61f48e21084671c1ff1257639f6a5d5ccfc8c1a64065e02157c5eb75c10a2d4`.
- Frozen packet: `<durable-root>/runs/market-rsi-v0125-gate1-first-current-source-20260928-01/controller-input.json`; regular non-symlink; file SHA-256 `bb15603ffd32c8b18b17339ce88aec15294862950d8dc8cb3036485716fe1acd`; canonical SHA-256 `39114563de6f34b100431d02edb0677184a40f83ce9c0d3eda8afe76f963620b`.
- Runtime receipt: `<durable-root>/runs/market-rsi-v0125-gate1-first-current-source-20260928-01/runtime.json`; regular non-symlink; file SHA-256 `e36476560b78a5653306d93d4cdb7a4391f92580a9e2749dd6a0dfdbfb4c9ffd`; canonical SHA-256 `1faf044ade2390b0d4cdbc18605bb8851f84fb57951849400bed92e0025c83a3`. Launch interpreter: `<durable-root>/runtimes/ds-py312-20260912-01/bin/python`.
- Prior canary receipt: `<durable-root>/runs/market-rsi-v0125-gate1-first-current-source-20260928-01/canary-result.json`; file SHA-256 `187c819a42a90361956145017d34a87f788f83026decfdfa5adc8d3b9e47671f`. A fresh local `verify_gate1_canary_receipt(...)` replay against the exact release/source/runtime returned `passed=true` and `terminal_cleanup_verified=true`; the receipt records zero provider calls, zero actual cost, no fetch, no admission and no retry.
- Pinned offline tokenizer revision `aca966e4e02791568aa6a4ced368624b3d897f42`, chat-template SHA-256 `3740abcea51c45830cb3ca562084ad5fb2ef53589376f73332e9886f93ade41c`. Fresh offline encoding of this packet and v0.1.25 request produced exactly **4,020 input tokens**; `MAX_OUTPUT_TOKENS=1,600`; frozen-rate no-cache request upper is exactly `(4020*4.86 + 1600*12.15)/1,000,000 = $0.0389772`. The local check created no sampler.
- Credential boundary: `<durable-root>/tinker-gate1-20260921.env` is a regular non-symlink, mode `0600`, size 90 bytes; contents were not inspected. Tokenizer cache `<durable-root>/tokenizer-cache-glm53-20260921-01` is a durable local directory. The child reads `TINKER_API_KEY` only after release, runtime, packet, canary, state, budget, no-catalog, process/container and Supervisor-claim checks pass (`p0_gate1_controller_live_entry.py:54-102`).

## One-shot and research-boundary verification

- The adapter fixes `num_samples=1`, `max_output_tokens=1600`, `sample_timeout_seconds=90` and `automatic_retry=false`; the provider client fixes `max_retries=0`, `RetryConfig(enable_retry_logic=False)` and `num_samples=1` (`p0_gate1_controller_adapter.py:665-682,705-748`; `codex_glm_provider.py:142-181`). There is no CLI override for any of these values.
- Omit `--catalog`, `--expected-catalog-file-sha256` and `--catalog-commitment-id`. With no catalog, the Controller can return only the non-executing scope decision; no exact fetch plan can be compiled. The adapter and outer receipts hard-code `public_fetch_performed=false`, `sealed_data_read=false`, `formal_data_admitted=false` and `automatic_retry=false`. The model prompt explicitly denies files, network, credentials, benchmark rows, Dev/Final, execution, admission, training and scoring.
- The v0.1.24 terminal run confirms the real terminal topology: exactly one provider sample was preserved before semantic validation; the authoritative budget settled `metered_terminal`; outer/global state closed failed; Supervisor emitted an incident plus `terminal-cleanup.json` with exact process/container absence. No retry/fetch/data/training occurred. The old ID is not reused by this recipe.

## Blocking mismatch 1 — production reservation is `$0.05`, not `$0.0389772`

The exact request upper is `$0.0389772`, but v0.1.25 production code independently uses `UPPER_USD = Decimal("0.05")`, requires both global and setup availability to be at least `$0.05`, records `$0.05` in `admission.json`, and reserves `$0.05` (`p0_gate1_controller_outer.py:34,272-325`; `bounded_live_outer_runner_v3.py:173-198`). There is no CLI argument that narrows this reservation to `$0.0389772`.

Fresh read-only authoritative budget reconstruction:

- root: `<durable-root>/budget-authoritative-20260916-01`
- experiment/cap: `kalshi-research-glm53-20260907-01` / `$200`
- global available: `$106.191396658`
- setup allocation/effective/reserved/available: `$10.60` / `$8.355963188` / `$2.20` / **`$0.044036812`**
- new candidate job: absent

Therefore the current child would fail its credential-free `_budget_snapshot` before credential read or provider construction; the recipe is not launchable. The orchestration-plan statement that the production reservation is capped at `$0.0389772` is false for v0.1.25. The smallest non-code repair is an explicitly authorized allocation transfer of at least `$0.005963188` into `setup` while keeping the `$200` cap unchanged, followed by a fresh budget replay. Without that authority, the alternative is a separately reviewed/released/canary-tested code change that reserves the exact measured request upper. Neither repair was performed here.

## Blocking mismatch 2 — paid authorization is not yet state-bound

The durable control document `<durable-root>/control/RESEARCH_STATE.md` currently hashes to `2f491782f526846cd250bcbe22c6754a408c134f19fc53318a6f7d19bbb9a8ae`; the matching global-state head is `9da325a3bdb24f8edbebdcdc6695cc8407ca85e937b75f35a9493388b4c7b44a`. That revision records the v0.1.25 zero-provider canary and says a paid D0 is the next separately authorized gate; it does not record the newly received paid authorization. These current hashes must not be supplied to the launch. After the budget blocker is resolved, Supervisor must revise the durable document, append the matching idle `decision_revision`, then capture the new exact `head_sha256` and `decision_doc_sha256` and rerun every mutable gate immediately before the one invocation.

## Exact dormant argv template

This is the complete production argument set, but it is **not executable** until the setup bucket is at least `$0.05` and the two placeholders are replaced with one matching fresh post-authorization state snapshot. Do not add catalog arguments or wrap this command in a retry:

```sh
cd '<canonical-checkout>'
PYTHONPATH='research/market_rsi' PYTHONDONTWRITEBYTECODE=1 \
  '<durable-root>/runtimes/ds-py312-20260912-01/bin/python' -B \
  research/market_rsi/supervisor_harness/p0_gate1_controller_supervisor_parent.py \
  --root '<durable-root>/runs/market-rsi-v0125-gate1-controller-d0-20260928-01' \
  --claim-root '<durable-root>/self-evolving-v18-local/artifacts/p0-gate1-controller-claims-v1' \
  --global-state-root '<durable-root>/self-evolving-v18-local/research/market_rsi/artifacts/supervisor-global-state-20260917-01' \
  --decision-doc '<durable-root>/control/RESEARCH_STATE.md' \
  --budget-root '<durable-root>/budget-authoritative-20260916-01' \
  --packet '<durable-root>/runs/market-rsi-v0125-gate1-first-current-source-20260928-01/controller-input.json' \
  --runtime-receipt '<durable-root>/runs/market-rsi-v0125-gate1-first-current-source-20260928-01/runtime.json' \
  --env-file '<durable-root>/tinker-gate1-20260921.env' \
  --tokenizer-cache '<durable-root>/tokenizer-cache-glm53-20260921-01' \
  --prior-canary-receipt '<durable-root>/runs/market-rsi-v0125-gate1-first-current-source-20260928-01/canary-result.json' \
  --experiment-id 'kalshi-research-glm53-20260907-01' \
  --budget-cap-usd '200' \
  --cycle-id 'market-rsi-v0125-gate1-controller-d0-20260928-01' \
  --expected-packet-file-sha256 'bb15603ffd32c8b18b17339ce88aec15294862950d8dc8cb3036485716fe1acd' \
  --expected-packet-canonical-sha256 '39114563de6f34b100431d02edb0677184a40f83ce9c0d3eda8afe76f963620b' \
  --expected-head-sha256 '<FRESH_POST_AUTHORIZATION_GLOBAL_STATE_HEAD_SHA256>' \
  --expected-decision-sha256 '<FRESH_POST_AUTHORIZATION_DECISION_DOC_SHA256>' \
  --prior-canary-sha256 '187c819a42a90361956145017d34a87f788f83026decfdfa5adc8d3b9e47671f' \
  --release-tag 'market-rsi-protocol-v0.1.25' \
  --expected-release-commit 'ed4048e55096b763ba763526e768057b5180cdeb' \
  --expected-release-tag-object '67b8e4a88e22c1f00e60850f521b26282517d682' \
  --expected-source-sha256 'c61f48e21084671c1ff1257639f6a5d5ccfc8c1a64065e02157c5eb75c10a2d4' \
  --supervisor-root '<durable-root>/runs/market-rsi-v0125-gate1-controller-d0-20260928-01-supervisor'
```

## Terminal acceptance and cleanup

After the sole invocation, independently review before any later action:

1. `adapter/<ID>/cost-preview.json` must bind 4,020 input, 1,600 max output and `$0.0389772`; `raw-response.json` and `raw-response.txt` must preserve the only response before semantic review; `provider-receipt.json` must show `sample_count=1`, terminal returned-token metering and `automatic_retry=false`. A pre-provider failure must show zero samples instead.
2. The authoritative budget job must be terminal: normally `metered_terminal` with returned cost `<= $0.0389772`; if provider metering is unavailable after dispatch, production conservatively records `uncertain_terminal` against the fixed `$0.05` reservation and Supervisor must treat it as an incident. Never retry either outcome.
3. Outer `review.json`, `result.json` or `outer-failure.json` must hash-link release/runtime/packet/canary/adapter evidence and retain `public_fetch_performed=false`, `formal_data_admitted=false`, `automatic_retry=false`; no fetch, Train/Dev/Final, training or score artifact may exist. Global state must close the ID terminally unless an explicitly unreconciled dispatched state is preserved for repair.
4. Supervisor `result.json` must show either clean success (`child_exit_code=0`, no incident, watchdog `active_task=null`) or an incident. On any failure/stall, require `terminal-cleanup.json`, `controller-repair-input.json`, preserved `child.log`, exact process absence and exact container absence. The v0.1.24 terminal run demonstrated this failure path; its cleanup receipt had all identity/absence checks true.

Only after the budget allocation and state-binding blockers are resolved may Supervisor repeat source/packet/runtime/canary/budget/ID/output/claim/process/container checks and substitute the two fresh state hashes. This review does not authorize or perform either repair.
