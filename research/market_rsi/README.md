# Market RSI

Market RSI studies feedback-driven research and small, separately reviewed
changes to researcher workflow (R) and the execution harness (H).

## Development

- [Code map and synthetic test commands](../../DEVELOPMENT.md)
- [Price-research entry](supervisor_harness/run_price_discovery.py)
- [R/H integration](supervisor_harness/price_capacity_loop.py)

The current implementation uses the historical NFL five-minute trade-VWAP
change task. Equities/earnings is the next planned adapter. Live improvement
and trading value require separate experiment evidence.

## Research operations

- [Current decision state](supervisor_harness/RESEARCH_STATE.md)
- [Supervisor operating protocol](supervisor_harness/RESEARCH_SUPERVISOR.md)
- [Checkpoint and research history](supervisor_harness/HUMAN_PROGRESS.md)
- [Project contribution boundaries](AGENTS.md)

Dated designs, protocols and results remain in their original files. The earlier
[architecture description](ARCHITECTURE.md) and [prototype research protocol](RESEARCH_PROTOCOL.md)
are historical references; use the development guide for the current code path.
