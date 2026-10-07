# Independent complete call-chain wait source review — 2026-10-07

Owner /root/price_live_review_20261006; final integrated checkpoint pending.
Source-only scope: price_account_roles.py, coevo_pilot_transaction.py,
run_price_discovery.py and three matching tests. Own log only; no production
edits, private artifacts or Train reads, model calls, fits, ledger writes or
scientific selections. This is Supervisor engineering verification, not
independent scientific approval or evidence of autonomous R/H gain.
Frozen local repair contract and actual tests/failures in existing price-loop
repair worklog. Legacy grants remain120, explicit future limits may reach300;
all calls deadline-bound, terminal-only, original-capped/no-retry.

## 2026-10-07 20:56–20:58 UTC — integrated source verdict

Verdict: **PASS_CODE_ONLY** for integrated checkpoint `9fd2f7f` against parent
`4136a84`. No blocking defect found in the assigned three-production-module
call-chain scope. This is an engineering source/test verdict, not permission
to activate a pending batch, a scientific review, or evidence of live closure.

Read the applicable full AGENTS.md, RESEARCH_SUPERVISOR.md, current source-only
RESEARCH_STATE.md and existing frozen repair contract. Applied the
market-rsi-research-progress skill: human-directed completion-wait repair is H
engineering, not autonomous R/H learning. Reviewed split checkpoint A
`f1be520` and B `849b842`, including preserved disposable-fixture failure and
its fixture-only correction `9fd2f7f`. No source was edited by this reviewer.

Observed scope: price_account_roles.py 11 additions/3 deletions,
coevo_pilot_transaction.py 10 additions/3 deletions, run_price_discovery.py
4 additions/2 deletions: 25 additions/8 deletions total in production.
The three-module integration is the declared union of the two small source
checkpoints, not an undeclared expansion. Matching tests and append-only worklog
account for the remaining diff. `git diff --check 4136a84..9fd2f7f` passed.

### Source findings

- Controller wait comes from immutable account_transfer.max_call_seconds;
  absent legacy value remains 120. An explicit value must have exact int type
  and be 1..300. Null, bool, float, string, zero and over-cap values fail.
- Legacy role grants without a call_seconds map still require exactly 120.
  New explicit maps must contain all and only four roles, exact positive ints
  <=300, and max_call_seconds equal to their maximum. Longer author waits need
  that explicit map; no global default has been enlarged.
- AccountRoles construction validates both Controller and role allowances
  before metadata preflight or model dispatch. The transaction validates the
  Controller allowance before original claim/reservation. Existing destination,
  source, input-byte, tool, original-count, window and protected-boundary checks
  remain in force. A code allowance is not consent to a new operational grant.
- Controller original claim pins the authorized wait; timeout diagnostics pin
  allowance/deadline. Admission refreshes time after review, rejects closed
  selection before reservation, and recalculates remaining hard-deadline time
  immediately before transport. Passing the deadline after reservation retains
  a failed uncertain original and does not refund or retry it.
- The formal entry passes the same grant-derived author wait to BOTH
  CandidateAuthor and CapacityAuthor. Both actual author paths forward their
  instance timeout to role_call; no remaining hardcoded constructor-120 hole
  exists in this entry. Independent reviewer waits retain their grant-bound
  stage-specific behavior.
- The new roles import inside transaction.call is function-local. The reverse
  import of input_limit remains module-level in roles; module loading succeeds
  because no eager transaction-to-roles import cycle was introduced.
- Native completed-turn, exact final response/source/input/schema checks,
  completed cold replay, unresolved-original rejection and no automatic retry
  remain unchanged. Old original caps/history are not reopened. No frozen
  scorer/runner, data-time rules, prediction recipe, model or resource ceiling
  was changed by this reviewed source diff.

### Actual independent verification and preserved failure

Exact command from canonical research/market_rsi cwd, using pinned runtime:

`env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 '/Users/estelle/Library/Application Support/MarketRSI/runtimes/ds-py312-20260912-01/bin/python' -B -m unittest supervisor_harness.test_price_account_roles supervisor_harness.test_coevo_pilot_transaction supervisor_harness.test_run_price_discovery -q`

First sandbox invocation (session 57646): 81 tests in 10.465 seconds,
**74 passed / 7 errors**, exit 1. First concrete cause was PermissionError
launching `/bin/ps` for local disposable-hook RSS diagnostics. Other entry
errors followed failed hooks; the uncertain-author assertion could not find
an author directory because the earlier input hook had not completed. This
failed verification is retained, not rewritten as a pass or diagnosed as
candidate science. No production repair was made for it.

One exact local diagnostic escalation reran the same command (session 9159),
with parent confirmation that inert tests/ps were within the source-review
scope. Result: **81 tests PASS in 23.894 seconds**, exit 0. Numeric threads
remained one. The test fixtures substitute account stdio with a disposable
native-RPC Python process and substitute training/predictions with synthetic
rows. Pure capacity-hook/test child processes are local and disposable; no
real account or training process is invoked.

Verified tests exercise invalid config before originals, legacy120, explicit300,
virtual late Controller completion, real short delayed terminal author response,
fresh deadline clipping, review crossing selection cutoff, deadline crossing
after reservation, original caps, terminal-only partial handling, and both
production author constructions. The official-entry synthetic native-wire path
records all ten actual-service dispatch waits at both legacy120 and explicit300
(2 Controller, 2 author, 6 reviewers), completed cold replay with zero new calls,
KEEP/negative/no-benefit continuation, known worker failure and uncertain-author
no retry. Neither virtual 180 seconds nor short subprocess delay is evidence of
an actual 300-second account response.

Root's separate 58-test and 23-test passes are parent-reported corroboration,
not substituted for the above independent 81-test result. The separately
running broad regression and private old-ledger hash checks belong to Root;
this reviewer did not inspect private operational bodies or ledgers.

### Exact source bindings and limits

- price_account_roles.py: `223fa286a52c4ec45f17bd2dad6a5ceaf98b3024b0e1a886e1dd9535361f15d2`
- coevo_pilot_transaction.py: `83718b1b00d6f8a354073357c911733b3049b8eed340297db8789d5ac9dc15d1`
- run_price_discovery.py: `596d4e654b77d8653065b6e74862573eaa77b45bb252740cdcbbb285fb30798f`
- test_price_account_roles.py: `51de280984b4149370c782c4c284efb568aea4b15f521ac1c63b191ac07792a1`
- test_coevo_pilot_transaction.py: `22fe7f827393252d2faaf71d70442a12ad08e488779607772fd6d36a77272d19`
- test_run_price_discovery.py: `7bc6a872846667057392dd5cd1812a478a67efa2927d420d39dfde62bf3c8421`

Final status check found these six owned production/test files clean. Only
this permitted review log was written. No source edits, commits, private
artifact/Train/Dev/Final reads, account/provider calls, actual fits, operational
ledger/grant writes or scientific choices. New live authorization is still
pending; no new window was opened by this review.

Nonblocking limits: longer waits do not guarantee completion or extend the
45-minute deadline; the real batch must still verify exact current grant,
input, source and native runtime policy. Source-bound replay is not arbitrary
cross-version replay. Synthetic closure demonstrates engineering behavior,
not autonomous co-evolution, prediction gain, OOS validity or profitability.
