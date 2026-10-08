# Independent formal-entry integration review

## 2026-10-07 02:07:49 UTC — bounded review begins

Owner: `price_live_review_20261006`; registered task:
`price_entry_integration_review_20261006`. Parent integration owner: Root.
Frozen reviewed snapshot: `dcfe4a5987ebdbb71c327429972a28f087abf403`;
comparison parent: `fcde61c`. Maximum review window: ten minutes.

Contract: F6c at the existing price-loop repair worklog end. Read applicable
`AGENTS.md`, `RESEARCH_SUPERVISOR.md`, current `RESEARCH_STATE.md`, registered
assignment and the complete `market-rsi-research-progress` skill. Reused the
existing price/native evaluation and research-progress rules; no new literature
or data investigation. Only this fresh dedicated log is written. No source
edits, commits, live account calls, actual Train/Dev/Final reads, private runtime
inspection, remote operations, quota changes or old-artifact mutation.

## Source and scope evidence

The comparison contains two production modules: 20 added and two removed lines
in the entry and two added lines in capacity reconciliation, totaling 22 additions
and two deletions. The other changed
files are the existing repair log and 201 added test lines. The source is a
series of preserved small checkpoints, not one unrecorded rewrite:

- `d521fc0`: earlier admission before account preflight;
- `66703db`: failed fresh-path engineering fixture preserved;
- `f911fc3`: normal fresh-launch timing namespace;
- `e56a089`: scientific finding survives capacity transition;
- `dcfe4a5`: five production-service engineering paths.

The aggregate test-heavy diff exceeds the approximate 200-line review warning.
Its narrow integrated scope is justified here by testing the same formal entry
across success, negative, rejection, known failure and uncertain replay, with
only the two small production fixes and earlier preflight admission guards.
This is an explicit bounded integration review, not a future exemption from
the small-change contract.

Reviewed source SHA256:

- `run_price_discovery.py`:
  `ef9fb6a41b20d08876eced47d78bda2aa9d11205d865fbd6612d38b8d3eb0318`
- `price_capacity_loop.py`:
  `d79bf7746008a63cfe4174a7ce94b1099c48fb9264bc0cb57580ed669dea27d4`
- `test_run_price_discovery.py`:
  `7158dfb065aed8fbadb64557bffdc2c48aab59d13390438bc2cec83b9006478a`

Actual inspected differences and inherited behavior:

1. Entry lines 283–284 bind all roles to the exact same original authorization.
   The existing account grant validator still requires exact role names/types,
   once-only caps, model/destination, closed data/expense/publication boundaries
   and an ordered window no longer than 45 minutes. No authority is added.
2. Entry lines 327–329 reject insufficient declared per-role caps before account
   preflight. Lines 339–343 reject capacity write paths outside the exact batch
   namespace. Lines 370–385 check baseline capacity component hashes alongside
   the frozen files, including their bytes at actual Git HEAD, before account
   metadata initialization. Conflicting commitments fail rather than overwrite.
3. Entry line 318 now uses `price-loop` for fresh runs. The existing reviewed
   recovery bindings retain their historical v2/v3 namespaces. The driver still
   refuses failed/uncertain claims; cold replay consumes bound completed stages,
   not a new account response, fit or quota refund.
4. Capacity lines 187–188 project the existing `last_experiment` into the new
   history, preserving its immutable prior binding. Capacity feedback remains
   separate, with prediction decision `UNCHANGED`; neither score nor incumbent
   is rewritten. The next selected hook and native candidate retain the same
   selected research/harness pair.
5. The five `ProductionEntryTests` instantiate real production entry, account,
   author, separate reviewer, capacity trial/activation and candidate handoff
   code. Disposable native journals use the actual batch implementation with
   explicit temporary-root/test-clock settings. Actual local Git, generated
   smoke tests, bounded hook subprocesses, native wire validation and frozen
   scorer recomputation run. Account stdio messages and all prediction/fit
   outputs are explicitly synthetic. These are not independent scientific
   approvals or resident-Train training results.

## 2026-10-07 02:09 UTC — diagnostic failure and same-test rerun

Pinned reviewer Python:
`/Users/estelle/Library/Application Support/MarketRSI/runtimes/ds-py312-20260912-01/bin/python`.
Working directory: `/Users/estelle/Developer/market-rsi/research/market_rsi`.

Exact focused command, with bytecode disabled and all named BLAS/thread ceilings
set to one:

```sh
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 '/Users/estelle/Library/Application Support/MarketRSI/runtimes/ds-py312-20260912-01/bin/python' -B -m unittest supervisor_harness.test_run_price_discovery supervisor_harness.test_price_capacity_loop
```

First sandbox run: 29 tests, 13 errors, 10.115 seconds. The concrete underlying
failure was `PermissionError: [Errno 1] Operation not permitted: '/bin/ps'` in
the inherited RSS sampler; selected hooks consequently failed closed before
the intended fixture path. This was a local diagnostic permission failure,
not empirical evidence or a reason to relax the sampler. Original output
preserved in tool session 31503. No source repair or skipped check.

The exact same synthetic-only command received local diagnostic escalation
approval and passed **29 tests in 23.838 seconds**, tool session 31645, exit 0.
All five actual-service cases passed: accepted capacity followed by a negative
predictor and cold replay; no-benefit rejection retaining the parent pair;
predictor KEEP/incumbent update; known worker failure with credit zero and no
performance claim; uncertain author retaining its original claim and refusing
a second call. The source remained frozen.

Root separately reported 369 tests passing in 56.029 seconds across 24 modules
and no-operation CLI help loading. That is parent-reported broader evidence;
the 29-test result above was executed by this reviewer.

## 2026-10-07 02:11 UTC — verdict

**PASS_CODE_ONLY** for the frozen F6c integration scope. No first-launch code
blocker found in the changed entry/history path. `git diff --check
fcde61c..dcfe4a5` passed; HEAD and owned production files remained unchanged.
The unchanged runner/scorer hashes were independently read from source:
`acfbfbb53c45b0746ed71aac49f3256cb041160cd194bceef9055e0299ca7f8b`
and `d66b6c6ba6ca466622cbf531662b8fcdf4a4d06ddcfa148c2d7f3cfa3dfb350b`.
No changes to the price data adapter, scorer, native role transport, reviewer
service or loop driver appear in the reviewed comparison. Old operational
grants/ledgers were deliberately not opened by this review; Root's unchanged
hash statement is not represented here as independent runtime inspection.

Remaining limitations are not silently converted into launch conditions:
general pre-author certain-failure continuation is still deferred; valid
credit-one branches remain archive-only under the unchanged native-parent
adapter; the actual selected capacity benefit and downstream scientific use
still require one freshly authorized real batch. Static admission and sampled
RSS do not establish OS-hard arbitrary-code containment. A runtime metadata
acknowledgement is narrower than proof of every possible tool configuration.
Reused historical Train, a working engineering path, and synthetic KEEP do not
establish forecasting improvement, profitability, autonomous researcher/harness
evolution or matched-budget superiority over fixed research.

This independent code review is **not** whole-role payload consent, input or
operation approval, a renewed old batch, or permission to launch a real trial.
Research-progress rules informed the separate engineering and scientific claim
levels. Root retains integration, checkpoint and any fresh-grant responsibilities.
