# Independent review — 2026-10-03

Registered before dispatch. Own log only; no edits to candidate, scheduler, protected evaluator or historical artifacts. No fits.

## 2026-10-03 19:15 UTC — baseline launch review

Read the applicable AGENTS, Supervisor, current state, Oct3 implementation
contract, small-step controls and indicator evaluation instructions. Reviewed
existing data-time/scoring source rather than treating state summaries as proof.
Only resident opened-Train artifacts were read. No fit, provider, network,
protected Dev/Final or historical artifact mutation occurred.

Independent standard-library arithmetic and hash checks confirm:

- Source cohort is 195 unique games on 42 dates; source manifest/cohort SHA-256
  match the frozen values, manifest is complete and protected data remain closed.
- V0 and A3 have all five manifest-declared output hashes intact. Both account
  for 193 materialized + two explicit exclusions (unresolved GB/DAL; stale
  TEN/ARI). The union exactly equals the full cohort; no silent exclusion.
- Both have exactly 87 unique, identical event/market/cutoff keys, SHA-256
  `2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`,
  20 check dates / seven weeks, and fold counts 26/16/28/17. Locked folds are
  precisely the 22-date initial fit plus four five-date expanding checks.
- All87 A3 labels, times and comparator probability strings equal V0. Market
  Brier/logloss recompute to `0.1419525290032328 / 0.4296707847132428`;
  ordinary to `0.1454823125327172 / 0.4399219724562196`; state parent to
  `0.1606809901646525 / 0.4711973192666776`; A3 to
  `0.1419536874132747 / 0.4296330176680234`.
- Independently reconstructed A3 date/week bootstrap (10,000 draws, seed
  20260929) and event-weighted point deltas match the saved scorecard within
  1e-15. Brier delta `+0.0000011584100419364`; date interval
  `[-0.0000186924113837201, +0.0000224468713829653]`; week interval
  `[-0.0000177209796609578, +0.0000222824460755360]`. Both cross zero.
- Baseline materialized receipts already contain causal age for every one of
  193 rows, range 1.0–147.0 seconds. This is coverage evidence, not evidence
  that age improves prediction. Latest integer-second trade precedes the
  checkpoint's integer second; frozen maximum age is 300 seconds.
- Current V0, settlement, probability contract and proper-score sources match
  their input receipt commitments. Structural outcome times are after cutoff.
  Fit filtering requires outcome availability before the earliest check cutoff.

No launch-critical baseline issue found. PBP actual publish/receive clocks are
absent; labels use catalog resolution timestamps, and historical event clocks
do not establish live availability. Existing reused folds are Discovery, not
untouched OOS. These tests do not authenticate Controller model identity,
establish arbitrary-code containment, or show mechanism superiority.

Validation used the existing pinned ds-py312 Python, standard-library JSON/CSV
checks and independent numpy bootstrap with all declared thread env vars=1 and
PYTHONHASHSEED=0. Zero fits. Baseline SHA refs: manifest/cohort
`429a0ef100ade70f7e7b7f5862c39f42adffd7dcdaaddf35c73c88b60f80074f` /
`ba07b5535917f6ccfd4ddb5eadb53f6428b02bcc238595adac42894643d37885`;
V0 scorecard `74c2f23de2ae129ead4d7def1a692d69240ac799582e54db3623865c3525de87`;
A3 scorecard `5d246a61ea2e98f3489f4a1ebecf34e3b526e43632d0ba47e7dc42d6b386fdd7`.

Next: inspect exact new adapter and synthetic tests, then pre-score recipe
review. Verdict applies only to the old immutable baseline, not forthcoming
source or unexecuted tests.

## 2026-10-03 19:17 UTC — worker binding source review

Reviewed the exact new adapter and synthetic tests. Adapter source SHA-256
`fccf586a383de9ef95e413359660dd39f802a87cdd343cdc530786f18c733405`;
test source `65a85ebdaa071648f7227a1fd0839b14cc15b496728f9905ebecd1b8034ac8b0`.
No changes to scheduler, kernel or existing experiments were made by reviewer.

Independent focused command in `research/market_rsi`, using pinned Python and
all five thread environment variables=1 / PYTHONHASHSEED=0:
`python -B -m unittest supervisor_harness.test_opened_train_discovery_worker
supervisor_harness.test_continuous_discovery_small_steps`.
Actual result: 46 tests passed in 0.864s; eight new adapter cases plus 38
existing small-step cases. Synthetic mocked child only, zero real fits.

Confirmed: exact request keys/module shape and bounded IDs; runner, provided
source files, interpreter and memory hashes checked; HEAD comparison;
per-branch four-fit/900s ceilings; conservative twelve-fit reservation;
two claimed execution slots; durable claim before child spawn; existing claim
refuses relaunch even though recorder claim API is idempotent; exclusive
request/log/receipt creation; timeout kills process group; all five output
hashes checked before terminal success; score review explicitly remains false.
Restored recorder history equals original and second execute refuses spawn.

Verdict: no launch-critical issue found for this **trusted, independently
reviewed, frozen four-fit pilot**, subject to Supervisor checking a complete
local-source/dependency manifest, matching immutable request and source commit,
and actual recipe review. Regex module admission and caller-provided file map
are not a complete capability registry or imported-dependency proof. Supervisor
must include adapter, scheduler, kernel, runner and every imported local helper
and verify no dirty executable bytes differ from the committed snapshot.

Explicit limitations: interpreter executable hash alone does not identify
installed dependencies; network/RSS isolation is not enforced in adapter;
1GiB RSS in candidate contract is observational unless externally enforced;
interrupted claim deliberately blocks retry and still needs trusted recovery
after verifying child absence. This is not arbitrary-code containment or an
authenticated model-provenance receipt. Save/open failures can leave a durable
active claim; that is visible conservative recovery, not automatic resumption.
No live effect, descendant feedback, prediction gain or H/R superiority earned
yet. Root was informed of the exact verdict and limitations before launch.

## 2026-10-03 19:20 UTC — revised worker final H verdict

Supervisor added parent-process RSS sampling and one-second bounded waits in the
same child-lifecycle component. Re-reviewed complete adapter/tests and ran the
same independent focused command: 47 tests passed in 0.807s (nine adapter,
38 inherited). RSS over-limit test verifies process-group kill and terminal
failure. New exact adapter SHA-256
`512176a1cb84ad81383e7e890abf9b2058ee66e7a8a643e3549fd5ec4c0db360`;
test SHA `00f4bd421d8fe0098d24bfa2bb092231da71b5cc5b9580a85e1044e76119c60e`;
164 production lines. No launch-critical issue under the same trusted/frozen
pilot conditions. Sampling is parent-only polling; short peaks and descendants
are not bounded by an OS hard memory limit. Complete source/runtime freeze,
candidate review and actual result review remain separate prerequisites.

Starting candidate pre-score review in parallel. No fits. First Controller
contract timestamp was corrected before candidate pinning; frozen corrected
contract SHA `e3b7bac05aeef4376674e8bbf01832e75f7ea6b6c8a6613d541fae01896ffa39`.
Source-only new recipe dependency check and immutable V0 validator pass;
both feature definitions cover all193 materialized games. C1 293 production
lines/C2 57 trigger explicit inseparability review, not implicit smallness.

## 2026-10-03 19:24 UTC — candidate pre-score verdict

Final exact candidate source: freshness
`d7e16a2d745f6440fe84b97aba54950b2c78a23428172b6002b187b385f057cd`;
possession-pressure
`4ea2935fb896397b4d21125bb040a0f82ff82be01abd2779717378d3465a0ab3`.
Test hashes respectively
`a0c6d740d8b9025959ae5d78dcb0b85875db4dcd0774c6ba9c4175eddafb4f32` /
`4b33c4f9ab5e22893b615e47d6729a7dd449173938bb4cbafcc38c3a98f04d10`.

Independently run 16 new synthetic tests: PASS in 0.024s. Combined source
boundary/scaffold regressions plus adapter/small-step tests: 91 PASS in12.458s.
Command: pinned `python -B -m unittest` on both new candidate test modules,
`test_nfl_ingame_win_probability_train_diagnostic`,
`test_nfl_ingame_prior_play_success_uncertainty_stratified_offset`,
`test_nfl_ingame_identity_anchored_market_calibration`,
`supervisor_harness.test_opened_train_discovery_worker` and
`supervisor_harness.test_continuous_discovery_small_steps`, with frozen one-thread
environment. All fitted test cases used synthetic data, not resident Train.

Separate reviewer-written arithmetic check (without fitting) confirms direct
NLL+8*beta², gradient/Hessian and finite differences; fit-age statistics cannot
change when check ages change; pressure uses exactly the four declared pre-play
fields and ignores poisoned future/terminal fields. Immutable source guards and
V0 validator pass. Recipe feature coverage is193/193; live runner rechecks all
PBP receipt hashes, exact materialized receipt equality,195->193+2 attrition,
87keys,106/132/148/176 fit counts and26/16/28/17 check counts. Four scientific
fits; no comparator refit or label-unavailable fit row is permitted.

Explicit inseparability review: ACCEPT the over200-line warning for the
freshness module. Its extra lines are the minimum self-contained causal input
validation and immutable run/prediction/score/failure writer around one frozen
feature/trainer recipe. Actual solver/scorer/decision still reuse existing
unchanged modules. Splitting that single runner into another production module
does not isolate another scientific effect. This acceptance does not imply that
350 source lines are automatically safe; static and synthetic boundaries were
reviewed. Pressure is a second independent C recipe using a pinned common source,
not a change to the external evaluator or permissions.

Verdict: PASS pre-score for these exact sources, subject to Supervisor's committed
source/runtime/request manifest. K/M/H/R must remain fixed across their prediction
comparison. Their result/credit and descendant are unreviewed until actual run.
Parent H source at this point is22ecd45. Supervisor separately identified a v3
branch-credit scheduling contradiction; that narrow new H proposal requires its
own review and identity checkpoint, not retroactive inclusion in this verdict.

## 2026-10-03 19:26 UTC — bounded v3 branch-retention review

Reviewed separate H scheduling contract
`603ce04e72549db60d1e25a3ef201a1641e06ca4765b00cbee411698d692193b`.
Measured production diff: ten additions/one removal in the sole allowlisted
`continuous_discovery_batch.py`; no candidate, evaluator, permission, budget,
model or data change. Exact scheduler SHA
`1b3065ea2990e886ff05869d5c6afd39bc0e80ebb053436f51fd9d9cee0d148c`;
new test SHA `675976511122192be61aa074fe51a48831119afa635cbc14eac7209e4180d7d5`.

Independent command on branch-retention, original scheduler, small-step and
adapter test modules: 78 PASS in1.386s, including all six new retention cases.
Verified public recorder, journal replay and parent-eligibility agree: only v3
can explicitly retain `credit2/refute/branch`. Failed or unreviewed outcomes
cannot get positive credit. Legacy v2 still rejects new action. Duplicate
question digest remains forbidden; global capacity stays2. Valid REVERT can
parent a distinct question while incumbent stays unchanged, and reconstructed
history/state equals original. C1/C2 source hashes remain the exact accepted
values above. No real Train fit or running pilot existed at activation boundary.

Verdict: PASS the narrow human-directed H scheduling correction atL2 synthetic
eligibility/restart evidence. Not a change to scientific KEEP/scoring, not an R
improvement and not a live research effect yet. Supervisor must checkpoint and
refresh H/pair identities before any claim; existing baseline scores/history
must not be rewritten. Log keeps earlier H review identities rather than
silently relabelling them with the new source.
