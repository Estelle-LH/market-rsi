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
python3 -B -m market_rsi check --suite smoke
python3 -B -m market_rsi check --suite price
python3 -B -m market_rsi check --suite price --list
python3 -B -m unittest discover -s tests -v
```

`smoke` selects five control/identity test modules. `price` selects the existing
24-module production-entry, feedback, capacity, worker and price-scoring
regression set. `--list` prints the exact selection without importing or running
tests. The runner resolves the project directory from its own path, so an
absolute script path works from another working directory.

Suite selection lives in `configs/checks.json`; implementation lives in
`market_rsi/checks.py`. The old `tools/check.py` is a compatibility script with
the same options. Run module commands from the checkout root; from another cwd,
use the absolute compatibility-script path or explicitly set `PYTHONPATH` to
this checkout. This is a source-checkout package, not an installed distribution.

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

### Private research and source-only publication

The active Supervisor checkpoint branch stays local with its full research
history. CandidateAuthor requires immutable `author_receipt.json` files in its
local Git source bindings; the private branch keeps these versionable.
The public `market-rsi-supervisor-clean-20261007` snapshot starts from published
main and carries reviewed source changes, shared assets and documentation.
Its ignore rules exclude new runtime receipts and logs. Publish that snapshot
without pushing the private research ancestry. Complete Git bundles and record
archives stay in the local MarketRSI archive for recovery.

Apply tracking-only cleanup at an idle checkpoint: an active worker can bind
its exact HEAD. Preserve original file bytes and literal paths throughout.

### Repository layout

The layout adopts package/config/task/test separation from
[OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve/tree/9196d8763300d1e46cc8b48cb0dc987966db3d48),
and source/generated-output separation from
[RSIBench-Data](https://github.com/evolvent-ai/RSIBench-Data/tree/4c807610243e7b481d382c5ed360c71c79a22f61).
These references guide organization; their runtime backends, research policies
and benchmark tasks are not adopted. Keep failed/rejected source and evidence
in append-only history rather than resetting discarded experiment commits.

Current checkout layout:

```text
market_rsi/                   Importable developer interface
  checks.py                   Existing check implementation
  cli.py                      Check command and thin native price delegate
configs/checks.json           Exact development-suite selections
benchmarks/nfl_price/          Current task/source index; no run authority
tests/                        Developer-command, layout and cleanup regressions
tools/check.py                Compatible old check script
docs/DEVELOPMENT.md            Code map, checks and migration boundaries
research/market_rsi/           Existing core source and bound evidence, unchanged
  supervisor_harness/         Loop, roles, review, execution and state
  experiments/                Existing task implementation and candidate history
  data_scientist_harness/      Existing co-evolution controls and research tooling
```

The runtime's configured permanent artifact root remains authoritative.
Root `artifacts/` and other local output directories are ignored if used;
the layout does not redirect existing runs or move live accounting. Closed
historical logs are mapped by the
[local archive manifest](../research/market_rsi/LOCAL_LOG_ARCHIVE_2026-10-07.json).

Target source organization, to migrate one verified boundary at a time. This
refines the earlier separate top-level runner/backend proposal into one package:

| Responsibility | Current Market RSI implementation | Eventual destination |
| --- | --- | --- |
| Session runner | `supervisor_harness/run_price_discovery.py` and durable loop modules | `market_rsi/loop/` |
| Service implementations | Account roles, candidate author, review and worker adapters | `market_rsi/roles/`, `market_rsi/services/` |
| Research history | Existing durable journal and feedback modules | `market_rsi/history/` |
| Task definitions and evaluation | `experiments/nfl_ingame_price_data.py` and price diagnostic/scorer | `benchmarks/` |
| Documentation | Current development guide and curated operating instructions | `docs/` |
| Regression tests | Root developer tests and existing colocated `test_*.py` modules | `tests/` |
| Developer utilities | `tools/check.py` | `tools/` |

Developer checks have moved into the package; their options, suite order and
process behavior stay fixed. The package's `price` command delegates to
`python -B -m supervisor_harness.run_price_discovery` using the current
interpreter and the original project cwd. It makes caller-relative config and
feedback names absolute before changing cwd, without resolving symlinks, and
does not add defaults, retries, permissions or accounting. Native preflight
remains authoritative. This command has mocked launch tests only; no live
launch through the new wrapper has been authorized or tested.

Production imports, command paths, source-hashed manifests, task/scorer and
machine-referenced records remain at their existing locations. Native preflight
checks literal source paths, rejects symlink paths and binds committed bytes;
directory aliases would break that contract. Moving core modules requires a
separate import/reference inventory, cold replay tests and new prospective
bindings. The original historical source and outcomes must remain recoverable.
No duplicate core implementation or symlink facade has been added.
The pre-existing `market_rsi.py` name is also used by native modules. The new
package forwards missing attributes to that unchanged module so developer and
native fixtures can share a process. Forwarded functions/classes keep their
original source files; production subprocesses still use the native cwd and
import layout. This is an API bridge, not a completed core-module migration.
Earnings remains planned, with no implemented profile.

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
