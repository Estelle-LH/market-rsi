# Research history and compatibility

Use [Architecture](ARCHITECTURE.md) to understand the published price-research
pipeline and [Development](DEVELOPMENT.md) to work on it. This page distinguishes
that implementation from earlier designs and private operational records.

## Read earlier designs in their original context

- [Earlier architecture](../research/market_rsi/ARCHITECTURE.md): September's
  probability/D0, GLM and local-B design, including its original trust boundaries.
- [Prototype research protocol](../research/market_rsi/RESEARCH_PROTOCOL.md):
  the archived three-arm study; its header records the superseded status.
- [Data Scientist Harness original README](https://github.com/Estelle-LH/market-rsi/blob/03d31a01bcf7bab01534379acdc5cde6322377ed/research/market_rsi/data_scientist_harness/README.md):
  preserved tool capabilities, source semantics and older setup/canary commands.
- [Original development and migration notes](https://github.com/Estelle-LH/market-rsi/blob/03d31a01bcf7bab01534379acdc5cde6322377ed/docs/DEVELOPMENT.md):
  the proposed future package layout, compatibility rationale and staged cleanup
  plan before documentation was separated by responsibility.
- [Harness version history](../research/market_rsi/HARNESS_VERSIONS.md):
  source/version changes and evidence tied to their own experiments.

These records explain their recorded source snapshots. Their old model names,
data objectives, readiness statements, paths and grants do not describe or
authorize a new run. Keep original experiment definitions and outcomes intact.

## Separate current services from compatibility packages

The published mainline uses the price-discovery entry and its R/H hook services.
The [Data Scientist Harness](../research/market_rsi/data_scientist_harness/README.md)
contains both reused controls and an earlier standalone research workflow;
its older broker is a separate entry path.

The [archived PMB compatibility lane](https://github.com/Estelle-LH/market-rsi/blob/330f2953d63c1b261b49b7db3e1405515e49e9db/research/market_rsi/pmb_simple_lane/README.md)
is a historical prototype, not the current benchmark. Its source and exclusive
tests are recovered from the parent snapshot described below. The
[quote-source adapter](../research/market_rsi/quote_source/README.md) and
[pinned shared checks](../research/market_rsi/ds_harness_core/README.md) have
their own source contracts; their presence does not imply that every mainline
round invokes them.

Layout references included
[OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve/tree/9196d8763300d1e46cc8b48cb0dc987966db3d48)
and [RSIBench-Data](https://github.com/evolvent-ai/RSIBench-Data/tree/4c807610243e7b481d382c5ed360c71c79a22f61).
They informed source/config/task/test organization. Market RSI retains its own
runtime, task and evaluation implementation.

## Locate private operational evidence

In the active local Supervisor workspace, decision state, human progress,
interventions, task indexes and per-run evidence describe actual execution.
Those local records can be newer than published main. Old copies in a remote
snapshot are historical evidence rather than a live status feed.

The existing
[local archive manifest](https://github.com/Estelle-LH/market-rsi/blob/cd778704138489ebb71da009b41d7b9e8223907f/research/market_rsi/LOCAL_LOG_ARCHIVE_2026-10-07.json)
maps previously archived records to original paths and hashes. Full local Git
bundles and immutable run artifacts are needed for recovery; another model call
is not guaranteed to reproduce an earlier response.

## Recover records removed from the public file tree

The October 8 tracking cleanup removes **245 generated/local records** from the
current Git tree: 121 Markdown files, 122 JSON files, one JSONL file and one
generated Word document. This includes 106 agent logs and the old local task
index, bottleneck board, human progress and intervention snapshots. The same
paths remain ignored, so new local records do not enter ordinary commits.

Their original bytes were copied to a local archive with an original-path,
size and SHA-256 manifest. Every archived file was restored to a separate
directory and checked against that manifest; a complete published-history Git
bundle was also verified. Originals remain in the cleanup checkout and the
active Supervisor workspace was not modified.

The complete pre-cleanup public tree is available at the immutable
[parent snapshot](https://github.com/Estelle-LH/market-rsi/tree/ec5122bef5675e864ed4c3ca6fd42a5ad8a6f7b8).
For bulk recovery, create a separate checkout at that commit rather than
restoring an old state into a running research workspace:

```sh
git worktree add --detach ../market-rsi-record-recovery ec5122bef5675e864ed4c3ca6fd42a5ad8a6f7b8
```

Existing research checkouts should archive their own local records before
applying this tracking change. A Git checkout of deletions can remove old
tracked files; ignore rules alone do not preserve those files during a pull.
The local archive manifest identifies the independently saved originals.

That tracking checkpoint intentionally retained **235 ignored-but-tracked references**. They
include files named by existing code/tests, pinned contracts and their reference
closure, protocol documentation and linked historical notes. Reusable source,
configuration, fixtures and scorers retained their original paths and bytes.
The retained `RESEARCH_STATE.md` supports an existing fixture default; its
published historical snapshot is not a live status feed or a new run grant.

Further removal needs a separate consumer/binding review. Historical source
checkpoints, exposed-data history, consumed budgets and old authority remain
unchanged; this cleanup provides source/record recovery, not a new empirical
rerun guarantee.

## Recover retired experiment components

The later October 8 component cleanup removes **104 files** from the current
public tree: the three earlier `memory_pilot`, `memory_policy` and
`memory_replication` packages, the PMB prototype, its four exclusive test
modules, and 14 associated memory-study records. These packages have no retained
Python imports or executable path references in the audited published source
or the separately inspected committed Supervisor snapshot. Current suite
selectors do not select their tests. Shared R/H controls, current memory
components, scorers and data adapters remain at their existing paths.

The [September memory pilot postmortem](../research/market_rsi/MEMORY_PILOT_POSTMORTEM_2026-09-14.md)
remains available because the earlier status page links its result and
limitations. Retained historical PMB plans and source-hash records still
describe their original snapshots; recover that snapshot before checking or
executing their old paths. Their presence is not current execution authority.

All 104 original files remain local and ignored. A separate non-iCloud archive
contains their original-path/size/SHA-256 manifest and a complete published-parent
Git bundle. Every file was restored independently and hash-checked. The complete
source before this component cleanup is the immutable
[parent snapshot](https://github.com/Estelle-LH/market-rsi/tree/330f2953d63c1b261b49b7db3e1405515e49e9db):

```sh
git worktree add --detach ../market-rsi-legacy-recovery 330f2953d63c1b261b49b7db3e1405515e49e9db
```

Recover the whole old source snapshot, not an isolated package copied into the
current pipeline. Its old runtime, data and authorization requirements still
apply; source recovery does not authorize a rerun. Archive local changes before
pulling these tracking deletions into any existing research checkout. This
maintenance branch does not activate changes in the Supervisor workspace.

## Recover the retired two-E2B diagnostic

The next reviewed cleanup batch retires the standalone `dual_e2b_canary.py` and
its exclusive test together. The September 17 local-B decision had already
retired this symmetric two-E2B admission route; the protocol source list also
labels that CLI retired. Its source/test pair is outside the retained release
selectors. The dashboard still recognizes its process name for observation;
that string does not import or launch it.

The complete source/test pair is preserved at the immutable
[parent snapshot](https://github.com/Estelle-LH/market-rsi/tree/efd4b3817f50976ccb4b80d6067b642b62b3449c),
with original-path/SHA-256 copies and a complete history bundle in the local
archive. Restore that entire parent into a separate checkout for old diagnostics;
do not copy the old CLI alone into a running research workspace. Archive local
changes before applying tracking deletions. These files remain local and ignored
in the cleanup checkout; the active Supervisor checkout is unchanged.

The earlier `e2b_coder_probe.py` remains tracked because the legacy release
selector includes root-level Python files dynamically. Other E2B protocol
components have explicit source pins, and Harbor has retained consumers and
fixture imports. Their retirement requires separate component-level review.

## Recover the historical 60-second benchmark

A separate reviewed batch retires the complete three-file
`prediction_benchmark_v0` package, including its nine exclusive synthetic test
cases. This was September's fixed 60-second development contract. The current
300-second evaluator and its tests are separately implemented and unchanged;
retiring the old package does not declare the two contracts equivalent.

The [original package](https://github.com/Estelle-LH/market-rsi/tree/efd4b3817f50976ccb4b80d6067b642b62b3449c/research/market_rsi/prediction_benchmark_v0)
is preserved in the immutable published parent, exact-path local copies and a
complete recovery bundle. The historical design and recorded test commands
retain their original meaning. Recover the whole old snapshot to replay those
commands; do not substitute the current scorer or rewrite frozen source hashes.

The old Supervisor README still links this scorer. Any later integration into
that private checkout must route its navigation to the historical snapshot and
review private frozen source maps first. This public cleanup does not pull,
activate or overwrite the Supervisor workspace. Archive local changes before
applying tracking deletions; originals remain local and ignored here.

## Keep generated operational records local

The next log-cleanup batch removes **32 generated JSON/JSONL records** from the
public tree: closed-window status/closeouts, operational plans/resolutions,
independent reviews, selected trajectories and the earlier local-archive map.
Retained default execution and source selectors do not require these exact
files; historical tools can still read supplied local paths. The review also
retains every dated record referenced by retained Python or another retained
JSON, including source-bound contracts and H1 proof records. Shared configuration,
the benchmark profile and synthetic fixture remain tracked and byte-identical.

All 32 originals stay at their ignored local paths. An exact-path, size, mode
and SHA-256 archive, independently restored copies and full published-parent
Git bundle preserve them. Their immutable
[original snapshot](https://github.com/Estelle-LH/market-rsi/tree/cd778704138489ebb71da009b41d7b9e8223907f)
contains the complete historical record/reference context. Read old report paths
in that snapshot; do not reinterpret a dated plan as current authority.

Archive local modifications before applying these tracking deletions in any
existing checkout. This batch changes only public tracking and this history
navigation, not the active Supervisor workspace, code, source bindings, test
selection, scorer, data, budgets or permissions. No scientific rerun or
co-evolution improvement is implied. Remaining records and legacy workflows
still require separately bounded review; the 200–400-file goal is unfinished.

## Recover retired manual audit workflows

The next reviewed batch retires **43 files across 23 historical workflows**:
27 manual inspection, diagnostic, replay or dispatch tools and 16 exclusive
test modules. Retained consumers, source selectors and their required helpers
remain byte-identical; their tests stay tracked. The retired tests cover their
old workflows, and are not claimed equivalent to current tests.

All 43 originals remain local and ignored, with exact-path/hash/mode backups,
independently restored copies and a verified full parent Git bundle. Recover
the complete [original snapshot](https://github.com/Estelle-LH/market-rsi/tree/70364d02334066fb9aa0a033c89356523fb65ab4)
for old commands and source bindings. Archive local modifications before
applying tracking deletions. This batch does not activate or modify the private
Supervisor workspace, runtime pins, data, scoring or execution authority.

## Keep historical Supervisor records local

The next bounded records cleanup moves **64 historical Supervisor records** out
of remote Git tracking: old agent logs, co-evolution review JSON/JSONL, checkpoint
contracts and superseded gate notes. No Python source imports these exact paths;
current architecture/state references remain tracked. Every original stays at
its local path and in a separate archive with an independent restore check and
complete parent-history bundle. Use the immutable parent snapshot above for
historical reading. This changes record visibility only; it does not alter the
Supervisor runtime, model, scorer, data or authority.

## Keep superseded experiments and tests local

The next bounded cleanup moves **303 historical experiment and standalone test
modules** out of remote tracking. The batch covers superseded NFL research
variants, their exclusive regression tests, older root-level Market RSI tests,
and Supervisor tests that are not selected by the current protocol or check
suites. The current price/evidence adapter and price-candidate artifacts are
explicitly retained.

Every removed path remains at its local working-tree path and in an exact-path
archive with independent restore checks and a complete published-parent Git
bundle. The cleanup changes public tracking and navigation only; it does not
claim scientific equivalence, change the active price/co-evolution checks, or
alter the private Supervisor workspace. Recover the archived parent snapshot
and local archive together to replay a retired experiment.

## Keep superseded audit workflows local

The following bounded cleanup moves **143 historical `audit_tools` modules** out
of remote tracking. These are standalone capture, replay, comparison, repair,
and test workflows that are not in the current release source set. The six
release-bound audit inputs remain tracked: the two NFL feedback preparation
controllers, direction-field canary, public source metadata, and the Vantage
coverage/metadata auditors.

The 143 originals remain at their local paths and in an exact-path archive with
independent restore checks and a complete published-parent Git bundle. This is
remote organization only: no live data, scoring, provider, runtime, or private
Supervisor workspace was changed.
