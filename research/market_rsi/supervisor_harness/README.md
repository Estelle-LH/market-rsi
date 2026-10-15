# Co-evolution orchestration and supervisor services

This is the current co-evolution orchestration layer. It connects Controller
decisions to implementation, independent review, bounded execution and durable
feedback. R/H proposals use a separate capacity-review and activation path.
Several entry-point filenames still carry the historical `price_*` prefix;
that is a compatibility constraint, not a second active task. New task logic
belongs under its named benchmark adapter, not in this directory.

See the [current architecture](../../../docs/ARCHITECTURE.md) for the full flow
and code map, the [development guide](../../../docs/DEVELOPMENT.md) for checks
and commands, and the [history guide](../../../docs/HISTORY.md) for older work.

## Inputs and outputs

Input is a bound batch configuration, initial feedback and source/runtime
identities. A round records seven stages:
`input → controller → implement → source_review → execute → result_review → reconcile`.
Reconciliation produces the feedback, memory, history, candidate pool and source
context consumed by the next round; failed attempts remain in the history.

## Local entry points

Start at [run_price_discovery.py](run_price_discovery.py), the native launch,
preflight and recovery entry. It assembles services in
[price_loop_services.py](price_loop_services.py) around the stage driver in
[feedback_linked_loop.py](feedback_linked_loop.py). For R/H changes, follow
[price_capacity_loop.py](price_capacity_loop.py) into the capacity trial and
activation services.

Role models, launch limits and executable services are supplied by explicit
configuration. Passing regression tests establishes behavior on their fixtures;
live autonomy or researcher improvement needs separate experiment evidence.

The [operating protocol](RESEARCH_SUPERVISOR.md) and
[decision-state record](RESEARCH_STATE.md) preserve research governance and
checkpoint context. Dated model, E2B and canary records describe their original
work; use the current architecture to identify the published code path.

For the ownership rules used during the earnings transition, see
[`docs/CODE_STRUCTURE_MAINTENANCE.md`](../../../docs/CODE_STRUCTURE_MAINTENANCE.md).
