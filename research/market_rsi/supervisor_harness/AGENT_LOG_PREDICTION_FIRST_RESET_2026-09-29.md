# Prediction-first strategy reset — 2026-09-29

## Verdict

**PASS for the strategy correction and compressed local plan. No empirical
prediction result.**

The Supervisor withdraws the earlier PMB-primary-base assumption. Historical
PMB plans and v4 foundation evidence remain preserved, but PMB is now only an
optional public compatibility/smoke lane with zero promotion authority. No PMB
source, episode, runtime or external action was admitted.

## Independent read-only audits

Two non-author audits ran in parallel:

1. The PMB role-reversal audit found 42 PMB-related files forming an isolated,
   entirely untracked local island. None is in the current architecture/state,
   controlled release manifest or v0.1.26 public allowlist. It recommended one
   superseding decision rather than mutating hash-bound historical snapshots.
2. The minimal-loop audit mapped reusable components and found exactly three
   core gaps: no settlement-probability row/materialization contract; no proper
   scorer for Brier/log loss/calibration and paired delta versus market; and no
   current candidate/evaluator process-and-filesystem boundary. PMB closes none
   of them.

Both audits were read-only. No network, provider, data, training, evaluation,
release, canary, Git mutation or protected-state action occurred.

## Frozen correction artifacts

| Artifact | SHA-256 |
|---|---|
| `PREDICTIONMARKETBENCH_ROLE_CORRECTION_2026-09-29.md` | `83ca286e97f249e039d710570f61c07851d90c4267f50b12e084e3a9ab90417a` |
| `PREDICTION_FIRST_MINIMAL_LOOP_2026-09-29.md` | `b06adbbb58f7ee1d068eabedf8bd6371c1f6e2e08408d2ae87c44a2502cde057` |
| `pmb_simple_lane/README.md` | `a78f2c3a7b5f47d3217583ba4a1ed51a55bc7bda4f8e387578139cb63e688df1` |
| updated `ARCHITECTURE.md` | `e250b1e6367b89d43a46cc835477a9e6ea9f783286bb492c2f378a9d8ccbd83b` |
| updated `RESEARCH_STATE.md` | `e44068d4a284f4107514026d5c07cf08b231eb57ea30f78eca9aa8048c57e057` |
| updated `SUPERVISOR_ROADMAP_2026-09-21.md` | `62b455cbef6b10ecb6f1d923e28154c8506242331686d108d60301309e8c5a0a` |

The prior PMB role documents remain unchanged at:

- v1 `d08c213ddaec28abd0b7561811c52ad162713f9b3945f6afdb1d4980ef8ad2f4`;
- v2 `39ad796ff16ce88ea0ad01fb813f07a317b93853467e57625c488d239a7ee0e9`.

## Reusable-source base

The next local implementation wave is based on six existing primitives:

| Path | SHA-256 |
|---|---|
| `objective_contract.py` | `7fe9d148f9408dfc84ac08098da582f9d6ee5c98b4062d5b2c13e1bc8b5352d5` |
| `prediction_stream.py` | `cd960d69ed1ee207568ae340f47265dba003723ba02178974dea68acb86f3652` |
| `data_lifecycle.py` | `c60106e10c20576a9d130fd236d54f1338cce320d59c0d496e5aedb680d787f7` |
| `supervisor_harness/local_b_container.py` | `76b0420fdd9c0fdc6b90cbfdc35979e5c196f0917102936edb9ea3f03e8525be` |
| `learner.py` | `98353e38eefa9ae2ad91fed5c35e3639cb4a388909cad8b8290e94e14dae687d` |
| `time_series_split_policy.py` | `55a7f99f686a2b6607f086caa96218efa97af6254207a5aa38e981d6519f2d9a` |

Ordered path-plus-hash aggregate:
`507d818d9dc6f408c1a6ffe3874dfb059750cf2fd3d72c80a8c17b0ff4810c33`.

## Decision boundary

The next milestone is a two-round synthetic probability loop: round one KEEP,
round two REVERT, restart persistence, candidate-visible as-of rows only and
Final unreachable. Proper prediction scoring precedes any execution/PnL test.
The `indicator-prediction-evals` causal ladder determined this order: raw data
→ raw signal → prediction → objective → PnL, with one changed stage per A/B.

The preserved local v0.1.26 candidate is strategically paused. Publishing it
would not close a scientific blocker and is no longer the immediate milestone.
