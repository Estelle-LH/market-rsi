# P0 Gate 1 trusted-schema repair review — 2026-09-21

## Problem

The single v0.1.17 Controller response supplied every scientific and limit
field but omitted the fixed decision `schema`. Strict review correctly failed
closed. Requiring a model to reproduce protocol version metadata created a
formatting failure without adding scientific freedom or safety.

## Local repair

- Gate 1 packet schema is versioned to v3.
- Adapter, request and result schemas are versioned to v4.
- `schema` is removed from the model tool and its required fields.
- Trusted adapter code injects the one frozen decision schema before the
  contract validator runs.
- A model-authored `schema` is now an extra field and fails closed.
- Missing, duplicate or extra scientific fields still fail closed.
- Supervisor-owned rights policy and every existing data, budget and
  evaluation boundary remain unchanged.

The preserved v0.1.17 response was not converted into a decision or reused for
execution.

## Validation

- 55 focused Gate 1 tests passed.
- The full pinned-runtime suite passed all 516 tests; the same two
  environment-dependent integrations were explicitly skipped.
- Fresh packet `p0-data-admission-gate1-packet-20260921-03` was built with
  zero model calls, fetches, admissions or provider cost:
  - file SHA-256: `5f261e0079f1dbe45cdbeb8e3ab2d903dae8ced7a68cfcb77d1568b68d5eff85`
  - canonical SHA-256: `28d5265ca7e01779b5ece512506f3a4c08d26afdeaa04c669494b54c81b908c6`
- Pinned local tokenizer measured 1,456 input tokens. The unchanged 3,072
  output-token maximum gives a `$0.04440096` hard upper.
- Fresh adapter canary `p0-gate1-controller-adapter-canary-20260921-06`
  passed with zero provider calls and zero cost.
- Fresh outer canary `p0-gate1-controller-outer-canary-20260921-04` passed
  with zero real provider calls/cost and no fetch/admission.
- Fresh production-path canary `p0-gate1-production-cli-canary-20260921-16`
  passed with the real parent/child arguments, zero provider calls/cost, no
  fetch/admission and exact cleanup.
- Current 318-file controlled manifest is
  `69b0ea27103a348c18561c0ac1906b8d3f556de3c028be5a90fca069aa4af1dd`.

## Boundary

This is an offline, human-assisted operational repair committed locally as
`4fa02dd`. It is not tagged or published, and it authorizes no provider sample,
public fetch, data admission, training or evaluation. A future sample requires a new release,
post-publication zero-provider acceptance, fresh permanent ID and separate
explicit authorization.
