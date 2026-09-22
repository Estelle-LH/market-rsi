# P0 outer runner second independent review

- Status: completed — pass for code-only release
- Owner: independent reviewer (`canary_review`)
- Scope: verify the two independently reproduced defects are fixed, rerun their regression tests, and reassess code-only release readiness.
- Forbidden: edits, external calls, model/container/data execution, authoritative state/budget mutation, commit, tag or push.
- Required verdict: pass/block code-only release; never authorize a live canary.

## Independent result

- Focused outer-runner tests passed 18/18; adjacent adapter, global-state and PaidBudget tests passed 34/34, 52 total.
- The hostile valid-clear callback regression cannot reach budget dispatch, provider encode/sample or process launch. After the callback, the runner rechecks the active claim, exact reserved job, publication/current source and persisted receipt, runtime/image and persisted receipt, and exact packet/hash before the sole dispatch site.
- Pre-dispatch failures now reconcile in the order cancel reservation, close or observe the cycle, snapshot authoritative budget/state, then atomically replace `outer-failure.json`. The original error remains raised; cancel/close failures are hash-recorded separately.
- Static review found no CLI, environment/key loading, subprocess or Docker call in the runner; one dispatch and one adapter-call site remain.
- Minor nonblocking caveat: the atomic staged receipt write fsyncs the file but not its containing directory, consistent with current repository receipt helpers.
- Verdict: **pass for code-only release**. Live/formal admission remains blocked until a new manifest is reviewed, published and exact preflight passes.
