# P0 outer runner independent review

- Status: completed — release blocked pending two fixes
- Owner: independent reviewer (`canary_review`)
- Scope: read-only review of `bounded_live_outer_runner_v3.py`, its tests and exact interaction with publication, protected state, PaidBudget and the v2 adapter.
- Forbidden: source edits, external calls, model/container/data execution, authoritative state/budget mutation, commit, tag or push.
- Required verdict: code-only release readiness and any fail-closed/accounting issue; this review cannot authorize a live canary.

## Independent result

- Exact `outer_runner_offline` readiness passed. Focused runner tests passed 16/16; adjacent adapter/state/budget tests passed 34/34. No external service, container or authoritative state/budget action occurred.
- **P0 mutable-gate race:** the runner checked state/budget, then invoked the unconstrained process/container-clear callback, then dispatched without rechecking state. A temporary-fixture reproduction closed the active cycle inside that callback while returning a valid-clear receipt; the runner still dispatched and sampled once, settled metered, and failed only at global close. This violates the required no-call-without-active-claim property.
- **Failure-receipt mismatch:** the pre-dispatch failure receipt was written before reservation cancellation and cycle close. A matching-process reproduction recorded `reserved/active` even though authoritative terminal state was `cancelled_before_dispatch` with no active cycle.
- Other boundaries behaved as designed: one dispatch/call site, no retry/CLI/credential loading; metering is recomputed and capped; absent metering with proven local termination settles at the upper bound; missing process/cleanup remains dispatched/active; settlement and close failures remain explicit.
- Verdict: **block code-only release** until state and budget are rechecked after the clear callback immediately before dispatch, and the final pre-dispatch failure receipt is written after cancellation/close with authoritative terminal values. Both need regression tests and independent rerun.
