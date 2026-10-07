# Developing Market RSI

## Start here

Source snapshot: October 7, 2026. The current integration is the price-discovery
loop. Historical probability experiments and earlier harnesses remain available
for replay. The equities/earnings adapter is planned.

Use Python 3.12 with the existing CPU environment described by
[`requirements-cpu.txt`](../research/market_rsi/data_scientist_harness/requirements-cpu.txt).
The check runner uses its own interpreter; it never installs or upgrades packages.
Some inherited integration tests use host-specific runtime paths, so the full
suite currently targets the existing development machine. They also invoke
`/bin/ps` to measure test-child RSS. A sandbox that denies process inspection
cannot run these checks faithfully; the runner does not elevate permissions or
skip the measurements. Start with `smoke` in restricted environments.

From the repository root:

```sh
python3 -B tools/check.py --suite smoke
python3 -B tools/check.py --suite price
python3 -B tools/check.py --suite price --list
python3 -B -m unittest discover -s tests -v
```

`smoke` selects five control/identity test modules. `price` selects the existing
24-module production-entry, feedback, capacity, worker and price-scoring
regression set. `--list` prints the exact selection without importing or running
tests. The runner resolves the project directory from its own path, so an
absolute script path works from another working directory.

Each suite has a five-minute subprocess timeout, disables bytecode writes and
sets numerical-library thread counts to one. It returns the test process's exit
status; timeout returns 124. These are developer regression commands, with
synthetic account/worker fixtures. They do not launch the live research entry or
grant experiment authority. The runner is not a network or process sandbox.

## Current pipeline

The production entry binds a batch configuration and initial feedback to the
existing services. A round follows seven durable stages:

```text
input → controller → implement → source_review → execute → result_review → reconcile
          ↑                                                                  |
          └──────────────── verified feedback / next round ──────────────────┘

controller proposal: C (prediction recipe) or R/H (research capacity/harness)
    → corresponding implementation and review path
    → execution/replay evidence
    → reconcile: retain history, update accepted state, deliver feedback
```

| Responsibility | Main code under `research/market_rsi/` |
| --- | --- |
| Launch, preflight and reviewed recovery | `supervisor_harness/run_price_discovery.py` |
| Once-only durable stage transitions | `supervisor_harness/feedback_linked_loop.py`, `feedback_loop_runtime.py` |
| Price-task handoffs and reconciliation | `supervisor_harness/price_loop_services.py`, `price_loop_handoff.py` |
| Account-backed role calls | `supervisor_harness/price_account_roles.py` |
| Candidate implementation and independent review | `supervisor_harness/price_candidate_author.py`, `price_independent_review.py` |
| R/H proposal, trial and activation | `supervisor_harness/price_capacity_loop.py`, `price_capacity_services.py`, `price_capacity_trial.py`, `research_capacity_activation.py` |
| Identity and small-step controls | `supervisor_harness/research_capacity_identity.py`, `data_scientist_harness/co_evolution_loop.py` |
| Worker scheduling and durable research history | `supervisor_harness/continuous_discovery_batch.py`, `opened_train_discovery_worker.py` |
| Historical NFL price data, target and scoring | `experiments/nfl_ingame_price_data.py`, `nfl_ingame_price_change_train_diagnostic.py`, `nfl_ingame_price_score.py` |

Passing these tests demonstrates engineering behavior on the fixtures. Live
agent-proposed R/H improvement, matched fixed-versus-evolving comparisons and
future-event performance require their own experiment evidence. The current
five-minute trade-VWAP target measures historical price changes, not executable
quotes or PnL.

## Code, state and history

### Repository layout

The layout follows the separation of responsibilities in the reference
[RSIBench-Data repository](https://github.com/evolvent-ai/RSIBench-Data/tree/4c807610243e7b481d382c5ed360c71c79a22f61).
Its runner, backend, benchmark profiles, docs, tests and tools are distinct;
generated sessions live under ignored `artifacts/runs/`. Selected baseline
diagnostics are committed under its benchmarks. We adopt the separation, not
its Tinker/E2B runtime or benchmark tasks.

Current checkout layout:

```text
README.md                     Project summary and main entry
docs/DEVELOPMENT.md            Current code map, checks and migration boundaries
tools/check.py                Developer check command
tests/                        Developer-command and fixture-cleanup regressions
research/market_rsi/           Existing production modules and bound evidence
  supervisor_harness/         Loop, roles, review, execution and state
  experiments/                Current data adapters, prediction recipes and scorer
  data_scientist_harness/      Existing co-evolution controls and research tooling
```

The runtime's configured permanent artifact root remains authoritative.
Root `artifacts/` and other local output directories are ignored if used;
the layout does not redirect existing runs or move live accounting. Closed
historical logs are mapped by the
[local archive manifest](../research/market_rsi/LOCAL_LOG_ARCHIVE_2026-10-07.json).

Target source organization, to migrate one verified boundary at a time:

| Reference responsibility | Current Market RSI implementation | Eventual destination |
| --- | --- | --- |
| Session runner | `supervisor_harness/run_price_discovery.py` and durable loop modules | `runner/` |
| Service implementations | Account roles, candidate author, review and worker adapters | `backend/` |
| Task definitions and evaluation | `experiments/nfl_ingame_price_data.py` and price diagnostic/scorer | `benchmarks/` |
| Documentation | Current development guide and curated operating instructions | `docs/` |
| Regression tests | Root developer tests and existing colocated `test_*.py` modules | `tests/` |
| Developer utilities | `tools/check.py` | `tools/` |

Only developer documentation and its two regression modules have moved in this
pass. Production imports, command paths, source-hashed manifests, task/scorer
and machine-referenced records stay at their existing locations. Migrating
runner/backend/benchmarks requires an import/reference inventory, cold replay
tests and fresh prospective source bindings; preserve old run identities.
Earnings remains a planned task adapter, not an implemented benchmark profile.

- Production code and its `test_*.py` modules often share directories. The named
  suites above make the current regression scope explicit.
- `supervisor_harness/RESEARCH_STATE.md` is the decision-state entry;
  `supervisor_harness/HUMAN_PROGRESS.md` records engineering/research checkpoints.
- Dated Markdown, JSON and JSONL files include historical designs, source
  bindings and immutable experiment evidence. Age alone does not establish that
  a file is unused. Preserve references and source hashes before relocating it.
- Existing ignored `data/`, `artifacts/` and `.runtime/` directories hold local
  material. Keep raw data, credentials, runtimes and live ledgers out of commits.

## Bounded cleanup sequence

1. **Developer entry (this pass):** current documentation and an explicit test
   runner. Production behavior and existing experiment identities stay fixed.
2. **Recovery-path readability:** audit indirect module aliases and duplicated
   prefix restoration in `run_price_discovery.py`. Preserve exact-once behavior,
   source identities and cold-replay tests; version any changed runtime source.
3. **Scheduler boundaries:** review the 2,827-line
   `continuous_discovery_batch.py` for separable scheduling, persistence and
   capacity responsibilities. Refactor one boundary per checkpoint after
   dependency and success/failure/restart tests are mapped.
4. **Historical layout:** build an import and artifact-reference inventory before
   moving records or legacy tools. Preserve the original checkout for replay.
5. **Portability:** replace host-specific test/runtime assumptions only after
   environment identity and subprocess behavior are explicitly covered.

The first pass is an isolated local candidate branch. Integration into the
Supervisor's active source remains a separate step, with the exact source diff
and verification reviewed together. No push or live activation is implied.
