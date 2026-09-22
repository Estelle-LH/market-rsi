# P0 outer live-runner implementation

- Status: implementation complete; independent review pending
- Owner: `one_b_parent_runner`
- Goal: atomically enforce exact publication, protected global state, the sole budget ledger, fresh ID/process/image/public-input checks, one bounded adapter call, terminal reconciliation and cleanup.
- Forbidden: real provider/container/E2B/data/Final call, authoritative ledger/state mutation, commit, tag or push.
- Pass boundary: strict fake and temporary-ledger tests only; implementation cannot itself authorize the live canary.

## Implemented result

- Added `bounded_live_outer_runner_v3.py` and `test_bounded_live_outer_runner_v3.py` only. The runner has no CLI and performs no credential loading.
- It binds exact publication/current source, frozen packet/runtime/image, protected state, sole budget and process/container-clear gates; makes at most one adapter call after dispatch; and verifies provider, process, launch, cleanup and adapter receipts.
- Exact metering settles at returned frozen-rate cost. Missing metering after proven local termination settles conservatively at the upper bound. Missing or malformed process/cleanup evidence leaves the dispatched budget and active Supervisor claim unresolved for explicit recovery.
- Implementer tests passed: 16 focused, 84 combined and 15 PaidBudget tests. Supervisor's first independent command accidentally named nonexistent `supervisor_harness.test_paid_budget`, producing one loader error after 104 real tests; the correct paid-budget location was then used. Independent rerun passed 104 adjacent tests plus 15 PaidBudget tests, and `git diff --check` passed.
- Source SHA-256: runner `cd119abd29b9a7baea495f8dfe88463365befc771a17074c52b94b92264047b2`; test `5039e38739783c41b80edf010363a61d57052a245b57343653eb44862bf1baf2`.
- Expected fail-closed state: the current v0.1.5 publication manifest does not include the new runner. No provider, Docker/E2B, data/Final, authoritative ledger/state, commit, tag or push action occurred.

## Independent-review fixes

- The process/container-clear callback is now followed immediately by a second exact active-state and reserved-budget snapshot plus publication/runtime/input integrity checks before dispatch.
- A regression callback closes the active cycle while returning a valid-clear receipt. It now produces zero encode/sample/launch calls, no dispatch receipt, a cancelled reservation and an authoritative closed failure receipt.
- Pre-dispatch reconciliation now cancels and closes first, then atomically writes the final receipt with snapshot hashes and explicit reconciliation errors. A matching-process test verifies the receipt equals authoritative terminal state; cancellation/close failures preserve the original error and are recorded separately.
- Supervisor independently reran 106 adjacent tests and 15 PaidBudget tests; all passed. Updated SHA-256: runner `aa2df6caa9758ff985ea837439f7168961a83c82fced2163ceff5d84272bdc77`; test `13f62179a37ee3825372b52c6a3dc751547bcf47d2670a8db72a9510d9f99970`.
- No external call, authoritative state/budget mutation, publication or live canary occurred. Second independent review is required.
