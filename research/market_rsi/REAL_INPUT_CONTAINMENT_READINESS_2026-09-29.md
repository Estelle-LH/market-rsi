# Real-input and candidate-containment readiness — 2026-09-29

## Decision

`READY_TO_IMPLEMENT_LOCAL_ADAPTER; NOT_READY_TO_RUN_EMPIRICAL_EVAL`

The independently reviewed synthetic prediction-first loop remains the frozen
scoring/lineage base. This check inventories only already-opened durable local
artifacts and the existing local Docker boundary. It performs no fetch,
provider call, protected split read, training, empirical evaluation, canary,
release, commit, tag, push or publication.

The one problem now being tested is whether the existing local inputs and
containment primitives are sufficient to construct a non-promotional,
settlement-probability diagnostic without exposing outcomes to candidate code.
The causal stage under preparation is `prediction execution`; data, target,
objective and PnL are unchanged and remain unadmitted.

## Reused research basis

No new isolation method is selected here. The design reuses the primary-source
research already recorded in `AGENT_LOG_LOCAL_B_CONTAINMENT_2026-09-18.md`:
Docker bind-mount behavior, `docker run`, `--pull=never`, and Docker Desktop for
Mac. The previously reviewed flags remain applicable: pinned image, no network,
read-only root/source, non-root user, all capabilities dropped,
`no-new-privileges`, resource limits and a fresh bounded work mount. As recorded
there, flags alone do not prove adversarial isolation; a fresh exact canary and
independent review are still required before real candidate execution.

## Already-opened local input inventory

All referenced artifacts live under the persistent, non-cloud, non-temporary
root `/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts`.
No raw Dev/Final file or outcome was opened by this inventory.

| Cohort | Durable evidence | Observed support | Current admissibility |
| --- | --- | --- | --- |
| 2023 | `nfl-2023-refresh-20260922-01` | 285 scheduled games; 237 mapped; 48 unmapped; 4,130 fixed-window on-chain fill rows; 60s support 499/48,194 (1.04%); 300s 1,492/48,194 (3.10%); median mapped-game coverage is zero at both horizons | Not suitable as the first price-response diagnostic; fills are not executable quotes, rights are unresolved, and `train_admitted=false` |
| 2024 | `nfl-2024-refresh-20260921-01` plus candidate ledger `-03` | 284 mapped games; 407,225 window trades; 47,875 timed plays; 60s support 32,384 (67.64%); 300s 43,506 (90.87%); deterministic candidate token orientation exists for 284 games | Best opened diagnostic candidate, but only historical event-clock timing is proven; provider publish/local receive time and research/redistribution rights remain unresolved; `train_admitted=false`; ledger `admission_claim=false` |
| 2025 opened Train | `nfl-2025-train-refresh-20260922-01` | 195 Train games across 42 dates, 2025-09-04 through 2025-12-04; 530,222 window trades; 35,460 timed plays; 31,881 with 60s support and 35,275 with 300s support | Opened Train diagnostics only; `formal_train_admitted=false`, `dev_final_opened=false`; it cannot serve as untouched evaluation evidence |

The inventory changes the immediate data decision: 2024 is the only current
cohort with enough opened trade coverage to justify building a small local
diagnostic materializer. It does not change formal admission, rights or Final.

## Exact schema gap

The current durable artifacts are trade/fill/PBP support datasets. They are not
yet rows in the frozen settlement-probability contract:

```text
event_id
market_id
cutoff_ms
feature_available_ms
market_probability
outcome_available_ms
outcome
```

Before even a diagnostic score, a new deterministic materializer must bind:

1. a fixed opened-2024 cohort and exact source hashes;
2. one preregistered cutoff rule independent of price and outcome;
3. token/team orientation and decision-time market probability;
4. settlement outcome plus a conservative availability timestamp;
5. complete-row exclusions and reason codes without imputation; and
6. a diagnostic-only role that can never be promoted or relabelled Final.

The older 60/300-second price-change draft and the new settlement-probability
contract are different objectives. They must not share one lineage or score.
This readiness decision selects neither; the target must be frozen in a new
experiment spec before materialization.

## Containment gap

The local Docker engine is ready, no containers are present, and the exact
pinned image
`python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`
is present as Linux/arm64.

Existing components do not yet form a real prediction sandbox:

- `minimal_prediction_loop/prediction_protocol.py` proves deterministic,
  durable, label-free sequencing but uses a trusted fixture/callback.
- `supervisor_harness/local_b_container.py` constructs a hardened container
  for a fixed task worker, not the sequential probability protocol.
- `prediction_candidate_server.py` is an older E2B-oriented stdin runner and
  is not connected to the current local Docker boundary or the new journal.

The narrow missing adapter must:

- mount only immutable candidate source/runtime and one fresh communication
  directory;
- expose exactly one public as-of row after the prior host-side probability
  commit is durable;
- never mount outcomes, future rows, scorer source, lifecycle state,
  credentials or evaluator artifacts;
- terminate and verify container absence before host-side scoring;
- bind image, command, mounts, environment allowlist, candidate/public-row
  hashes, journal head, stdout/stderr bounds, exit and cleanup receipts; and
- keep `real_isolation_admitted=false` until a separately authorized fresh-ID
  zero-provider canary and independent attack review pass.

## Verification performed

- Local Docker engine: ready; current container inventory: empty.
- Exact pinned image: present locally; no pull occurred.
- Focused container and prediction-loop suites: 66/66 PASS.
- Scoped `git diff --check`: PASS.

## Next gates

1. Implement and unit-test the local sequential candidate adapter with only
   synthetic public rows. This is local source work, not a canary.
2. Independently review the exact adapter/source/test snapshot.
3. Request a fresh permanent ID and explicit one-shot authorization before
   running the zero-provider containment canary.
4. Separately freeze the diagnostic target/cutoff/materializer and obtain
   authorization before opening outcomes or running a real-data score.

No existing authorization is interpreted as permission for steps 3 or 4.
