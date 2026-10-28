# AWS migration and memory enforcement

This directory records a migration plan and the memory lifecycle contract reviewed on 2026-10-28. Deployment is incomplete until the original implementation and its state handoff pass their own checks.

- [迁移计划](MIGRATION_PLAN.zh-CN.md): scope, order, acceptance and rollback.
- [Memory 执行机制](MEMORY_ENFORCEMENT.zh-CN.md): current state, immutable inputs, lifecycle hooks and failure handling.
- [Migration inventory template](migration-inventory.template.json): an empty inventory to fill in a controlled environment.
- [Portable synthetic checks](../../examples/deployment_checks/README.md): standard-library fixtures and an optional disposable-container guest.

The documents summarize a controlled research implementation. That production memory implementation and its real state are not included in this publication. The examples are independent test utilities; they do not replace the research runner or authorize a live launch. Source changes require fresh original admission.

This export contains no account identifiers, infrastructure bindings, private source revisions, research outcomes, memory contents, ledgers, model responses or private history. Populate operational paths and evidence only in the controlled deployment environment.
