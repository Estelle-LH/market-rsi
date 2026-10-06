# P1 entry follow-up — comparison-only v2 (2026-10-06)

Owner `/root/priority_parent_entry_20261006` (implementer agent initially named
`priority_parent_20261006`); user-directed H engineering, not autonomous R/C.
Actual source parent: `4f13fb9b372bc67a2e66ae777e2f687727cd3963`.
Contract `PRIORITY_PARENT_ENTRY_CONTRACT_2026-10-06-v1.json` read in full before
edits; SHA256 `1fc96e5eb9277aeb4d1da8d32d9b87aa3eb4c6c6a65aa5e6c120bb666b0ef916`.
Its earlier declared parent `bfdb2a1` is preserved; actual implementation starts
from the independently accepted P1 source checkpoint, not a rewritten contract.
Only new v2 adapter, matching tests and this dedicated log may be written.
Original adapter/scorer/runners/records/ledgers remain unchanged. Root alone
integrates, reviews and commits; this task authorizes synthetic fitting only.

## 16:51–16:56 UTC — observed problem, reuse, implementation and first tests

Original H1 requires specific C1/C7 state replay before running a candidate.
The accepted P1 reference loader intentionally does not supply parent states;
without a new entry, this installed comparison capability cannot reach execution.
Reused immutable materialization, four-fold fitting orchestration, shared CSV
writer, proper scorer, grouped intervals, correction diagnostics and unchanged
KEEP rules. No new predictive method or literature retrieval was needed; recorded
engineering reuse, not a synopsis-directory claim of original-paper reading.

Implemented `run_recipe(source_root, output, binding, prepare_features,
fit_predict, replay_predictor, *, allow_test_paths=False)` in a separate v2 module.
Callbacks see features/fold/reference identity+provenance, no parent parameters.
Exact candidate/source/contract/helper/adapter/callback byte pins and original
Controller parent/incumbent metadata are checked. The candidate contract also
binds the complete Supervisor-materialized `accepted_reference` (reference and
separate acceptance pin); it cannot float outside the reviewed contract.

`fit_completion_requirements` is a frozen nonempty map of dotted trainer-field
selectors to exact typed values. Source review decides whether those receipts
actually establish that candidate's fit completion. An optimizer can require
`optimizer.converged: true`; a fixed-stage learner can require `n_iter: 1` or its
own reviewed stage count. This entry does not assert that all trainers are SciPy
optimizers or invent a common scientific convergence threshold. One reported
statistical fit/fold, JSON-safe state/hash, probability policy, exact replay and
bounding equality remain mandatory; source review is necessary for actual call
semantics, not replaceable by self-reported counters.

Progress is saved before callback entry, after callback return with its returned
receipt, and after valid state/prediction completion. Returned-but-invalid work
is not erased or represented as a completed valid fit. A failure retains the
first valid receipt, exact entered/returned/completed counts and partial evidence;
no retry, scorecard or successful manifest is fabricated. Output never overwrites.

Initial7 tests PASS5.102s; after contract-pinning/returned-receipt regressions,
8 tests PASS5.105s. All data synthetic195→193+2,87 checks/four folds. Same
predictor yields byte-identical CSV, equal numeric states, aggregate scores,
grouped intervals and unchanged KEEP versus the immutable helper-chain control.
The nonlinear candidate fixture trains a one-stage two-leaf primitive tree;
it is a method-agnostic completion check, not performance evidence. Its archived
parent identity/artifacts are simulated accepted evidence, not a real old run.
Source/root/frozen boundary functions are patched only inside the synthetic test
context; production has no monkeypatch. Old H1 source bytes are checked exactly.

Added deep copies at feature/fit/replay callback boundaries so callback mutation
cannot alter row objects later used by the frozen scorer. This is local object
separation, not arbitrary-code, OS, network or filesystem containment. Candidate
code and causal feature usage still require independent semantic source review.

## Freeze verification

Final tests/hashes pending at initial log write; later evidence appended below.
No actual Train/Dev/Final/raw-artifact reads, account/provider calls, external
retrieval, live outputs, ledger changes, commits, releases or promotion.
L2 synthetic evidence only; scientific/live operational improvement untested.

## 16:58–16:59 UTC — final exact-source verification

**40/40 PASS**, 11.609 seconds unittest time: nine new v2 tests,21 reference
tests,10 inherited H1 tests. Command execution yielded after10seconds, then
completed on the next bounded poll. All fitting and artifacts were synthetic;
there were zero real-data fits or new empirical scores. The matched v2 runner
entered/completed exactly four candidate callbacks, independently counted
four C7 solver calls, wrote87 identical prediction rows and equal numeric
states, and reproduced aggregate/fold/pairing/interval/KEEP evidence from the
unchanged helper-chain control. Other fixtures include synthetic parent-fit
construction and invalid/failing candidates; these are engineering test cost,
not real candidate admissions or evidence of an empirical research trajectory.

Exact command, cwd `/Users/estelle/Developer/market-rsi/research/market_rsi`:

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 PYTHONHASHSEED=0 '/Users/estelle/Library/Application Support/MarketRSI/runtimes/ds-py312-20260912-01/bin/python' -B -m unittest experiments.test_nfl_ingame_candidate_evidence_adapter_v2 experiments.test_nfl_ingame_prediction_reference experiments.test_nfl_ingame_candidate_evidence_adapter -q
```

Same pinned runtime alias and binary
`80ee2dd97bc26259d4e30853336f72ad38aa4aa0531bb196cc444d899422689d`;
Python3.12.3/NumPy1.26.4/SciPy1.14.0/sklearn1.6.1 (import-only version verification
recorded in accepted P1 log, runtime unchanged). Thread env values all1,
PYTHONHASHSEED0. Input/output/temp hashes dynamic synthetic fixtures; empirical
data/memory/provider manifests not applicable. No source checkpoint made by
implementer; Root must independently accept/commit before activation.

Frozen module:
`5a65ea4f4073a30141a3f58bef852eb45a570af6f4d6caa6aff5eca96dd76df4`.
Frozen tests:
`88841c147343e3d909d35b8ab8476b44e69c6654d6241778f6acf9a516e87235`.
Source162lines/one production module, below the approximate200-line warning;
size alone is not safety proof. Exact old H1 adapter remains
`f62a5459a8e3c78bcdd7810e25291d1ef164ccc2d41f876fa37fb166f9dcc8bc`;
accepted comparison loader remains
`664b9566ad61c7c4e60e1aeeea0602482a37e8a2ab6db2d2cd319ea56d89b19d`.
`git diff --check` PASS. Changed files exactly the assigned three new paths;
all other concurrent work belongs to its existing owner and was not staged.

Regression evidence: valid-negative and arbitrary nonlinear parent identity
loads comparison-only; fixed-stage learner completes without optimizer receipt;
missing/changed acceptance pin/parent/helper/callback/contract/comparator/feature
identity fails before fitting; malformed model_fits/state/hash/probability/
completion/bounding/replay is invalid, with entered/returned counts preserved;
second-fit failure retains2entered/1returned/1valid-completed and first receipt;
no output overwrite/retry/success manifest after failure. Scorer-owned row
objects retain exact original bytes despite feature/fit/replay callback mutation.
No parent states are implicitly passed, fitted or loaded by v2.

Remaining integration: Supervisor review of original acceptance normalization,
new candidate scientific contract with fixed `accepted_reference` and
`fit_completion_requirements`, source-reviewed candidate callbacks and exact
request/preflight mapping. P2 verifies pinned original bytes before selection;
v2 verifies all parent pairing/data-time evidence before candidate fitting.
Untrusted candidate code is not granted arbitrary host execution by this API.
There is no OS/network/filesystem sandbox or proof of causal feature validity
in this module; those remain exact independent source/runtime review boundaries.
Fresh live experiments require their bounded authorization; old closed caps stay
closed. No live operational, prediction, autonomous R or superiority claim.
