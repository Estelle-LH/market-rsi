# P0 Gate 1 trusted-rights-policy repair review — 2026-09-21

## Problem

The v0.1.16 Controller made a relevant scientific choice but failed because it
submitted the free-text `rights_check` field twice. Duplicate-field rejection
must remain strict: trusted code cannot choose, merge, or edit two
model-authored values.

The deeper design error was asking the Controller to author a safety policy.
Data-access and data-use limits are Supervisor responsibilities, not a
scientific degree of freedom.

## Local repair

The unpublished vNext source now separates those roles:

- Controller chooses the question, official source, hypothesis, fixed sample,
  requested operations, expected evidence, limits, and stop rule.
- Supervisor binds policy `official_public_research_only_v1` in the frozen
  packet and trusted broker task.
- The policy requires an allowlisted official public source, no credentials,
  purchases or writes, no inference of research rights from accessibility,
  and no formal data admission.
- `rights_check` is absent from the model tool schema. If the model still emits
  it, or emits any duplicate/extra field, the response fails closed.
- Packet, decision and broker-task schemas were versioned to v2; adapter,
  request and adapter-result schemas were versioned to v3.

## Validation

- 41 focused packet/adapter/contract/fetch tests passed.
- The full pinned-runtime suite passed all 516 tests; two environment-dependent
  integration checks were explicitly skipped as before.
- A regression reproducing the v0.1.16 duplicate-rights shape remains rejected.
- Fresh adapter canary `p0-gate1-controller-adapter-canary-20260921-05`
  passed with zero provider calls, zero cost, no fetch, and no admission.
- Fresh full production-path canary
  `p0-gate1-production-cli-canary-20260921-14` passed with the production
  parent and CLI, zero provider calls, zero real cost, no fetch, and no
  admission.
- Fresh v2 packet artifact
  `p0-data-admission-gate1-packet-20260921-02` was built without a model call:
  file SHA-256
  `404e60d0ca8c87bf705ccf2a5c64577bf858a3bcd2b1f0fb0fceb2a29c5902a7`;
  canonical SHA-256
  `cdbcf2af187769d3ee5f743a58725acb4a1f936633ffafe7fd809b538652687d`.
- The pinned GLM tokenizer measured 1,468 input tokens. With the unchanged
  3,072-token maximum, the worst-case metered upper is `$0.04445928`, below
  the per-attempt `$0.05` ceiling.
- Current controlled source is 318 files with unpublished manifest
  `9200f93f7e3fb7827ccb0c76f5d61b7b70a70b188f918e53a8a3e41a9afcd15d`.

## Boundary

This is a local, human-assisted operational repair committed as `bfef4d0`. It
has not been tagged, published, independently release-reviewed, or used for a
new provider sample. It does not authorize a new Controller request, public
fetch, formal data admission, training, or evaluation.
