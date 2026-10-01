# PMB Simple Episode Lane / Controller Swap design review — 2026-09-28

- Timestamp: `2026-09-28T18:31:28-0400`
- Reviewer: independent orchestration design lane
- Scope: local read-only inspection plus this registered log only
- External effects: no network, provider, payment, credential read, public-data fetch, Git mutation, training, or sealed Dev/Final read
- Verdict: **DESIGN PASS / EXECUTION HOLD**

## Material checks

The proposed lane can reuse useful existing primitives, but it is not already implemented by any one of them:

- `global_state_gate.py` already supplies the one-active-cycle/fresh-ID authority and must remain the single global-state authority.
- `paid_budget.py` already supplies append-only authoritative reservation/dispatch/settlement. An episode must use one authoritative whole-episode job; per-turn metering is subordinate evidence, not a second reservation ledger.
- `codex_glm_provider.ControllerSession` already demonstrates a persistent multi-turn controller session and append-only turn artifacts, but its current contract permits up to 32 turns/tool calls and is not a five-round episode contract.
- `data_scientist_harness/store.py` and the trajectory archive provide useful immutable records, hash-linked activity, intent-before-result, and reflection conventions. They do not provide an episode-wide lease binding controller, B, budget, snapshots, and global-state closure.
- `directional_handoff.py` and `local_b_container.py` prove a synthetic 20-handoff path and strong B isolation. They only accept order counts `{1,20}` and a fixed directional guest; they are not a scientific five-round worker.
- `bounded_live_adapter_v2.py` is deliberately one provider sample plus one B task and creates/cleans B for that call. It cannot provide a single persistent B across a five-round episode.
- The existing first-round research harness executes CPU work on the host. The new lane must move every allowed research operation into pinned B code; it must not give B arbitrary shell/code execution.
- Existing research contracts already require intent before result, opened-Train-only diagnostics, D-1 fitting, same-row paired comparisons, and one changed causal stage. The simple lane must preserve those boundaries rather than weaken them.

Data readiness was checked without opening sealed data. The persistent 2025 Train refresh manifest reports dataset `nfl-2025-train-refresh-20260922-01`, 195 Train games, 42 dates, 531,148 raw trade rows, 530,222 fixed-window rows, 35,460 timed plays, 31,881 with a preceding trade within 60 seconds, and `dev_final_opened=false`. However, it also reports `formal_train_admitted=false`; the production trusted admission registry is empty. Therefore an actual Train-reading or fitting episode is not launchable yet.

The model names are also not ready for a fair swap. Repository code pins `zai-org/GLM-5.3:peft:262144` / `zai-org/GLM-5.3`, not “GLM 3.5”. A frontier model is mentioned only as orchestration intent; no exact controller model identity, provider adapter, tokenizer/rendering contract, immutable rates, budget bound, or reviewed canary exists for that arm. These values must not be inferred.

## Simple Episode Lane contract

One episode has one never-reused episode ID, one controller session, one B container, one immutable start snapshot, and five controller decision slots. Slots 1–4 may issue exactly one allowlisted B task or stop early; slot 5 is forced terminal synthesis and cannot dispatch another task. Thus the episode has at most four observable B actions and always closes without a hidden sixth model turn. If five B actions are required, that is a different six-decision protocol and must be separately specified.

For each action slot, the controller sees only the start packet plus previously admitted observations, emits one schema-valid decision, and either stops or selects one code-owned task. The broker writes one immutable order; B emits an ACK, append-only events, and one immutable result; the parent independently measures and admits the observation before the next decision. There is no automatic provider retry or resampling. Infrastructure/protocol ambiguity is terminal. A valid negative scientific result may inform the next decision. Each scientific action changes at most one causal stage while every other declared field remains frozen.

Recommended lease states are:

`registered -> start_snapshotted -> budget_reserved -> global_claimed -> b_started -> round_N_claimed -> round_N_observed -> terminal_review_pending -> closed_passed | closed_failed | unresolved`

The durable lease binds episode/pair/arm IDs, controlled release/source/runtime, start-snapshot hash, exact data-admission receipt, model/adapter identity, budget job, B image/container identity, owner PID and command hash, deadlines, and watchdog. A permanent claim exists before any provider or B side effect. The entire episode ceiling is reserved as one `PaidBudget` job; turn receipts append local metering and the job settles once at aggregate terminal usage. Any uncertain provider state settles conservatively at the episode upper bound. An unresolved process/provider/container leaves both budget and global state unresolved and blocks another episode.

## Start and end snapshots

The immutable start snapshot must contain:

- episode, pair, arm, schema and never-reused IDs;
- release tag/commit/tag-object, controlled-source hashes, Python/package/runtime identity;
- exact controller model, adapter, tokenizer/chat-template, rates and sampling policy;
- harness/tool/system-prompt schemas and hashes;
- B image digest, guest-source hash, Docker command and security policy;
- exact formal Train admission receipt, deterministic data manifest/tree hash, row-key hash, allowed dates, rights/coverage and exposure-ledger hashes;
- frozen question, causal stage, target/horizon, costs, latency, exclusions, feature signs, normalization, trainer, trading policy, baseline and metrics;
- allowed prior-archive hash, budget/global-state heads and limits;
- an allowlist containing no Dev/Final path plus explicit `dev_read=false` and `final_read=false`;
- exact-clear process/container evidence and stable durable-root identities.

The immutable end snapshot must rehash the unchanged start commitments and bind the terminal episode-journal head; all controller turns, orders, ACKs, events, results and provider receipts; aggregate token/cached-token/cost accounting and budget settlement; the single B identity across all rounds; exact process/container cleanup; the complete output-tree manifest; common Train-row/missing-row/per-day metrics; and explicit zero Dev/Final/network/purchase/credential exposure. The global state remains `terminal_review_pending` until an independent receipt hash closes it. The scientific label is `opened_train_diagnostic_only`, never a promotion or prediction-improvement claim.

## Append-only persistent layout

Use the non-cloud durable MarketRSI run root:

```text
<durable-runs>/<episode_id>/
  lease.json
  start-snapshot.json
  episode-journal.jsonl
  controller/claim.json
  controller/turn-001/...
  b/launch.json
  b/orders/0001.json
  b/acks/0001.json
  b/events/0001.jsonl
  b/results/0001/...
  rounds/001/intent.json
  rounds/001/decision.json
  rounds/001/observation.json
  rounds/001/review.json
  budget/reservation-reference.json
  budget/turn-metering/...
  end-snapshot.json
  terminal-review.json
  cleanup.json
  result.json | failure.json
```

Every leaf is exclusive-create and immutable. `episode-journal.jsonl` is sequence- and previous-hash chained. Partial writes use private temporary files plus atomic publication. `result.json` or `failure.json` is published last. Budget artifacts here are immutable references/evidence; `PaidBudget` remains authoritative.

## Persistent B

Implement a dedicated new guest rather than changing the historical directional worker. One B container starts before round 1 and stops after terminal synthesis. It uses an immutable image digest, `--network none`, read-only root, nonroot user, dropped capabilities, no-new-privileges, bounded PIDs/memory/CPU, sanitized environment, and no credentials, proxy variables, custom CA, Docker socket, A workspace, supervisor state, global-state journal, or budget store.

Mount exactly: an immutable code bundle read-only, the exact admitted Train bundle/manifest read-only, and one episode workspace writable. The guest accepts only closed-schema code-owned operations with sequence number, order hash, start-snapshot hash and admission hash. The parent continuously checks container ID/labels/process/deadlines and cleans the exact identity on every terminal path. B never calls a model or the network and cannot replace itself between rounds.

## Paired Controller Swap

The pair manifest freezes every field except controller-stack identity. Each arm has a separate episode ID, controller session, B container and workspace, but the same immutable start snapshot, Train rows, harness/tools, scientific question, round policy, sampling policy, output/wall/CPU/memory ceilings and USD ceiling. The second arm sees the original start packet, never the first arm's artifacts or conclusions.

Run arms sequentially under the one-active global-state gate. Pre-register or derive arm order from a public immutable hash. The logical prompt and tool JSON are identical; separately record unavoidable tokenizer/rendered-prompt differences. Use the same seed where supported, but do not claim equivalent randomness. No retries. If an equal ceiling cannot safely cover both exact model stacks, the comparison is invalid rather than silently asymmetric.

The evaluator is model-blind until it freezes its verdict, and neither controller evaluates itself. One pair is diagnostic, not evidence of a generally superior controller; model selection requires multiple preregistered paired episodes. If either arm has an infrastructure/protocol failure, the paired quality result is unscorable and the failure is reported without retry.

Use a lexicographic assessment, not “best Train MSE” alone:

1. Safety/protocol: valid termination, valid B tasks, forced terminal slot, zero invalid tools/retries/boundary violations, complete cleanup.
2. Attributable research quality: correct causal-stage identification, one-stage change, preregistered support/refute criteria, evidence-hash citations, correct response to negative evidence, no overclaim.
3. Efficiency: time to first valid task, wall time, B CPU/RSS, provider turns, input/output/cached tokens, USD, and cost per admitted observation.
4. Scientific diagnostics on identical Train rows: raw/rank IC for raw-signal work; paired delta IC/MSE, calibration slope/intercept, positive-date/FIGI/game fraction and date-block intervals for prediction/trainer work; common-mask and missing-row counts. PnL belongs in a separate episode with frozen predictions.
5. Robustness/completeness: duplicate tasks, failure classification, concentration, and artifact closure.

## Concrete implementation and test set

Add, after design approval:

- `supervisor_harness/simple_episode_contract.py`
- `supervisor_harness/simple_episode_lease.py`
- `supervisor_harness/simple_episode_artifacts.py`
- `supervisor_harness/simple_episode_guest.py`
- `supervisor_harness/simple_episode_container.py`
- `supervisor_harness/simple_episode_controller.py`
- `supervisor_harness/simple_episode_outer.py`
- `supervisor_harness/simple_episode_receipt.py`
- `supervisor_harness/controller_swap_contract.py`
- `supervisor_harness/controller_swap_evaluator.py`
- `supervisor_harness/run_simple_episode_canary.py`
- matching focused `test_*.py` files.

After independent source review, register those bytes in `protocol_source_release.py` and its manifest tests. Reuse `global_state_gate.py`. Prefer one existing `PaidBudget` job plus an episode aggregate meter; change `paid_budget.py` only if the current job receipt cannot bind aggregate turn evidence. Do not change legacy directional/handoff or bounded-live semantics. Register a real receipt in `formal_train_admission.py` only after a separate exact admission review.

Required tests cover: exact schemas and five-slot/forced-stop semantics; early stop; frozen one-stage fields; duplicate ID, owner crash, deadline, restart and unresolved-state blocking; path/symlink/hardlink/ancestor/TOCTOU mutation; snapshot equality; Dev/Final denial; journal sequence/hash/overwrite/partial-write rejection; one-container identity across rounds; exact mounts and environment; cleanup at every failure point; order/ACK/event/result replay and mutation; whole-episode budget reserve/dispatch/aggregate settlement without double reservation; uncertainty and cap exhaustion; exact model identity and no retry; arm equality/cross-visibility/order; blinded evaluation; same-row metrics and date-block intervals; zero-provider/no-network synthetic persistent-B canary; immutable receipt and release inclusion.

## First Train-only diagnostic episode

Execution is conditional on a separately reviewed formal admission receipt for an exact deterministic Train-only bundle derived solely from `nfl-2025-train-refresh-20260922-01`. No fit or Train-row read occurs before that gate.

The first episode should be a single-controller infrastructure/reproducibility diagnostic, not the controller swap and not a candidate search:

> Reproduce the frozen 60-second strong HGB baseline and its exact row/date diagnostics on the admitted refreshed 2025 opened-Train bundle without changing data, raw signal, target, normalizer, trainer, costs, latency or policy.

Suggested five slots:

1. Validate the immutable admission/QA snapshot and state the replay hypothesis, discrepancy taxonomy and stop criteria.
2. Run the code-owned row-mask/materialization audit in B.
3. Run the exact frozen HGB baseline replay in the same B.
4. Run code-owned per-date/common-mask/calibration/concentration diagnostics and classify discrepancies.
5. Forced terminal synthesis: pass only against preregistered hash/spec/row/tolerance checks; otherwise stop and classify data, spec, runtime or infrastructure cause.

Report exact games/dates/rows, missing rows, HGB MSE, per-date paired loss, calibration, positive-date fraction, date-block interval, prediction-artifact hash, elapsed time and peak RSS. The historical opened-Train HGB MSE `0.0013540355` is a reference, not a standalone acceptance gate. The terminal label is `opened_train_replay_diagnostic`; it grants no promotion, prediction-gain, Dev/Final, release, fetch, training expansion or evaluation authority.

## Holds and launch order

1. Decide the exact controller identities. Current repository evidence supports GLM 5.3, not GLM 3.5; the exact frontier stack is unknown.
2. Implement and independently review the episode owner, persistent guest, snapshots, append-only receipts and aggregate budget binding.
3. Release and run one fresh zero-provider/no-network synthetic five-slot canary, followed by independent terminal review.
4. Separately admit the exact Train bundle and receipt; until then, Train execution remains blocked.
5. Run one released/canaried single-controller Train replay diagnostic.
6. Only after that passes, release/canary both exact controller adapters and authorize one separately budgeted paired swap.

No step above authorizes a provider call, data fetch, Train read/fit, Dev/Final access, release, canary, or controller-swap execution.
