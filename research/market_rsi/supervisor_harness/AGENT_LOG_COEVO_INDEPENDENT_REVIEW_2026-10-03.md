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
