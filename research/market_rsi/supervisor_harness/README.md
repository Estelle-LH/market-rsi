# Research supervisor services

This directory connects research decisions, candidate implementation, independent
review, bounded execution and durable feedback. Its price-task services also
support reviewed R/H proposals and activation.

## Start here

- [Current code map and test commands](../../../DEVELOPMENT.md)
- [Operating protocol](RESEARCH_SUPERVISOR.md)
- [Current decision state](RESEARCH_STATE.md)
- [Original supervision charter](USER_SUPERVISION_CHARTER_2026-09-16.txt)

## Main components

- [Production entry and recovery](run_price_discovery.py)
- [Durable round transitions](feedback_linked_loop.py)
- [Price-task services](price_loop_services.py)
- [R/H integration](price_capacity_loop.py)
- [Capacity activation and identity](research_capacity_activation.py)
- [Worker scheduling and history](continuous_discovery_batch.py)

[Human progress](HUMAN_PROGRESS.md), [interventions](HUMAN_INTERVENTIONS.md) and
[agent logs](AGENT_LOG_INDEX_2026-09-17.json) retain the research trajectory.
Dated canary, E2B and GLM designs describe their original experiments; their
records are preserved alongside the current services. Execution authority comes
from the explicitly bound batch configuration, not from a README example.
