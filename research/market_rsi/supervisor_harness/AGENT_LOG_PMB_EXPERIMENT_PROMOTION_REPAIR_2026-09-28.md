# PMB experiment promotion-contract repair

- Task: `pmb_experiment_promotion_repair_20260928`
- Plan: `market-rsi-pmb-synthetic-foundation-20260928-04`
- Step: `harden_experiment_promotion_contract`
- Completed: `2026-09-29T00:10:24Z`
- Result: PASS

## Boundary and research basis

This was a local, standard-library-only contract hardening change. It reused the
project's existing causal-ladder and evidence-gate record plus the
`indicator-prediction-evals` rule that evidence validation is separate from a
promotion decision. No live literature search was performed because the task
forbade network access and introduced no new scientific method or empirical
claim.

Observed problem: `validate_experiment_spec` rejected
`promotion_eligible=true` only for `public_diagnostic_train`, leaving `train`,
`hidden_dev`, and `sealed_final` able to encode authority that a validator must
never grant. `ExperimentSpec` was also subclassable, permitting a subclass to
replace a commitment attribute such as `sha256` with stateful behavior.

Alternatives considered:

- Keeping role-specific promotion rules was rejected because it conflates an
  evidence label with a later supervisor promotion decision.
- Checking only `isinstance` at the file boundary was rejected because a
  subclass can override attribute access.
- The implemented design requires `promotion_eligible is False` for every
  evidence role, seals the commitment class with fail-closed
  `__init_subclass__`, and additionally requires the exact base type at
  construction/file-freeze boundaries.

`sealed_final` is documented as terminal evidence that must not feed a
controller or tuning loop. The validator grants neither promotion nor action
authority. Existing valid mappings whose field was already exactly false keep
their canonical JSON bytes and hashes unchanged.

## Files changed

- `research/market_rsi/pmb_simple_lane/experiment_spec.py`
  - Requires `promotion_eligible` to be exactly the `False` singleton for all
    roles.
  - Seals `ExperimentSpec` against subclassing and checks exact type.
  - Documents the non-authorizing validator boundary and terminal sealed Final.
- `research/market_rsi/tests/test_pmb_simple_lane_experiment_spec.py`
  - Adds all-role promotion-true rejection regressions.
  - Adds valid-false byte/hash preservation regressions for all roles.
  - Adds a stateful-`sha256` subclass-definition attack regression.
- This log.

No binder, manifest, lease, runtime, data, provider, training, evaluation,
release, or Git publication code/state was changed.

## Verification

- Focused: `python3 -m unittest research.market_rsi.tests.test_pmb_simple_lane_experiment_spec`
  - PASS, 19 tests.
- Combined: `python3 -m unittest discover -s research/market_rsi/tests -p 'test_pmb_simple_lane_*.py'`
  - PASS, 64 tests (the shared suite grew concurrently; this is the final run).
- Compile: `python3 -m py_compile` on the owned source and test.
  - PASS.
- Whitespace: `git diff --no-index --check /dev/null` on both owned untracked
  files.
  - PASS.
- Capability scan: AST scan for network/process imports and dynamic execution
  calls across both owned Python files.
  - PASS, zero forbidden findings. Test-only constant
    `__import__("hashlib")` uses were explicitly recognized as standard-library
    hashing, not an external capability.
- Direct adversarial probe: attempted definition of an `ExperimentSpec`
  subclass with a stateful `sha256` property.
  - PASS: class definition raised `TypeError: ExperimentSpec is sealed and
    cannot be subclassed`; the property was never read.
- Runtime: Python 3.12.3.

## Exact evidence hashes

- `experiment_spec.py`:
  `36b1b9c57bf9be835f2bdfc3fe34be6393c198cb3ee3b85e1705c0851025671c`
- `test_pmb_simple_lane_experiment_spec.py`:
  `8f2aa4e6c9cdef36e28fe378f91f38bfd2e21fd7dc6bff9e85b6159f8d049c12`

## Errors and remaining questions

No implementation or test failure occurred. This step does not itself make any
experiment promotion-eligible and does not authorize opening sealed Final;
those remain separate supervisor-controlled decisions outside this validator.
