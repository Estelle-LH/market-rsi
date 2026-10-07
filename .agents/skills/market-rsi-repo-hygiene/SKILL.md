---
name: market-rsi-repo-hygiene
description: Clean up or reorganize the Market RSI repository while preserving core behavior, source bindings, and replayable history. Use for requested repo cleanup, layout changes, or maintenance refactors; not for choosing experiments or changing research evaluation.
---

# Market RSI repository hygiene

Keep reusable code, task definitions, configuration, tests, documentation and
generated runs easy to distinguish. Preserve the working research pipeline.
This skill guides maintenance; it does not authorize a cleanup, experiment,
dependency change, merge, activation or remote push on its own.

## Establish the actual checkout

Check the Git root, remote, branch and dirty files. The old RSIBench-Data fork
is not the active `market-rsi` source. A cleanup worktree may be behind the
Supervisor; preserve its concurrent work and state exactly which checkout was
changed. Read applicable `AGENTS.md` files and the
[development guide](../../../docs/DEVELOPMENT.md) when present. If an older
checkout lacks the guide, inventory its actual code rather than assuming the
new layout is installed.

## Organize by responsibility

Prefer an importable `market_rsi/` package for reusable loop, role, service and
history code; `benchmarks/` for task adapters/evaluation; `configs/` for
versioned configuration; and separate `tests/`, `docs/` and small `tools/`
commands. Create directories only when moving or adding real material.
Use existing code rather than copying a parallel implementation.

The current package is a developer interface and native-launch bridge, not a
completed core migration. Bound modules and evidence still live under
`research/market_rsi/`. Task profiles are source indexes, not run grants.
The existing `market_rsi.py` shares the package name: test legacy helper imports
and source identity whenever changing that namespace. Preserve the existing API
or explicitly version a breaking migration; avoid global import-path tricks.

## Keep changes attributable and replayable

Before editing, identify one bounded component, its dependencies, exact write
set, protected interfaces, expected effect, tests and rollback checkpoint in the
existing progress record. Inventory callers, imports, `__file__` assumptions,
literal paths, CLI arguments and source-hash bindings before moving code.

Keep protected scorers, data boundaries, model/runtime, permission and budget
policy fixed during organization work. Native preflight binds committed bytes
at literal canonical paths; a symlink or mass rename is not a safe shortcut.
Move a bound component only with reviewed new prospective bindings and replay
checks; preserve the historical source, manifests and outcomes unchanged.
Leave a documented partial migration when moving a boundary is not justified.

Separate generated outputs from Git source. Keep raw data, credentials,
runtimes and live ledgers out of commits; retain curated baseline evidence and
compact source/result/decision references. Before archiving logs, resolve their
callers and verify original-path/hash manifests and recovery. Age or a REVERT
decision alone is not grounds to delete a record. Never reset failed commits
or consumed operational history as a cleanup technique.

## Verify the changed boundary

For executable/layout changes, check imports and public commands from the root
and a different cwd, including failure, restart/history and no-duplicate-work
behavior where affected. Verify the protected files are byte-identical or
explicitly account for a separately authorized change. Run focused tests first,
then the relevant existing regressions. Use the existing runtime; do not install
new dependencies or run live science merely to validate organization.

Current developer commands are `python -B -m unittest discover -s tests -v`,
`python -B -m market_rsi check --suite smoke`, and the relevant `price` suite;
`tools/check.py` remains a compatibility entry. Consult the guide for runtime
and host-process-inspection requirements. Instruction-only changes need skill,
link and scope validation, not another full empirical or price experiment.
Tests passing establish engineering behavior, not research improvement.

Commit each meaningful source/result checkpoint locally, including failures
and repairs as new history. Inspect the exact staged scope and excluded
material. Report what actually moved, what stayed fixed, tests run, checkpoint
and whether integration/activation occurred. Keep further migration work
explicitly pending; do not describe a facade as a finished core refactor.
