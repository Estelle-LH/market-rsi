# Feedback pilot — Controller-selected candidate implementation

2026-10-06T18:45:43Z: Original signed-in account Controller decision10c021e3 chose InGameTemperatureCloseScorePossessionJointOffset-v1, actualparent0414fcf2 (validnegative score-time), rawmarket comparator89a8ef92. Feedback cites latest score5881ef68 and Rmemory9a6b01b9; changes possession modulation from marketuncertainty/scoretime to close-score, not an exactrepeat. R/H sources retained. Worker mechanical implementation only, no fits/scientific choice.

Frozen candidate01allowlist: experiments/nfl_ingame_close_score_possession_offset_v1.py; experiments/test_nfl_ingame_close_score_possession_offset_v1.py; supervisor_harness/FEEDBACK_PILOT_C1_CONTRACT_2026-10-06.json; this log. Use alreadyreviewed v2 comparison-only parent interface to compare actual score-time parent, not silently C7. No changes to adapter/scorer/controller/worker/R/Hsemantic. One2parameter recipe, sumNLL+8norm², beta>=-1, one L-BFGS-B/fold initzero/max1000/gtol1e-8/ftol0/no retry/controlrefits. Rawfeature x=(2possession-1)*(1-abs(clip(score/14,-1,1))). Inputtiming/folds/mask unchanged.

## Mechanical implementation and frozen verification

Implementation began2026-10-06T18:46:53Z; source frozen18:49:32Z and final combined verification returned14/14PASS, within the requested five-minute implementation bound. Author: feedback_pilot_candidate_20261006 implements the original signed-in account Controller's exact C specification. Requested scientific Controller model gpt-6.1-sol; serving snapshot unknown. No independent worker scientific selection, changed equation or forced R/H mutation.

Actual prior evidence: score-time had Brier0.14207819118069467 versus C7 0.14195410408172784 and market0.14195252900323282, remained valid negative REVERT, and intervals crossed zero. The original Controller used that feedback and prior hypothesis memory to choose possession modulated by score closeness instead of repeating constant possession, market-uncertainty possession or score-time. Scientific parent remains0414fcf2; market incumbent remains89a8ef92, not the latest evaluated predictor.

New C production module155lines. Feature reads only trusted home-token market probability and fixed preplay state columns0/2, checks exact column names, finite numeric nonboolean values and exact0/1 possession. Formula bounded[-1,1], zero at absolute score>=14, possession antisymmetry. Candidate-specific independent numeric fixtures are C validation, not a mutation or repurposing of the fixed score-time H oracle. Existing v2 replay/probability/source/reference interfaces are reused unchanged. Old R/H source reuse and scientific/process benefits remain separately attributable and unmeasured.

Four fixed folds each make one scipy L-BFGS-B call with analytic gradient, initial[0,0], maxiter1000, gtol1e-8, ftol0, beta>=-1, unrestricted gamma, summed unweighted NLL+8norm², no intercept/tuning/restarts/fallback/control refits/parent warm start. Solver convergence, finite parameters and constraint validity required. Primitive numeric state records coefficients, clipping constants, formula/version, probability transform, source/input hashes and truthful optimizer receipt. Check outcomes never enter fit/prediction; actual-parent predictions/identity remain comparison-only without weights/state inheritance.

Template contract FEEDBACK_PILOT_C1_CONTRACT_2026-10-06.json preserves the original question text, scientific parent/incumbent, recipe/constants, completion requirements and attribution. `accepted_reference:null` explicitly blocks activation until Supervisor independently normalizes/binds the actual original source/result/learning evidence in the runtime contract. This is not an acceptance claim or permission boolean.

Native admission uses the fresh04 exact grant bytesd7ff6d39, clocks, worker request/source validation, exact module/candidate/attempt/four-fit/spec identity, configured native pair, claimed branch and original Train path identity. Independent reviewer found the initial local admission expected max_attempts3 although each isolated native child is actually configured with max_attempts1. Repaired to1 and added exact native branch candidate identity; global grant three-attempt/twelve-fit accounting remains Supervisor-owned and unchanged. Root still must rehearse admission against its actual prepared native child before any live launch.

Initial synthetic full-path test failed because a temporary fixture path retained the macOS symlink alias; repaired only the test fixture to resolve its path. Failure preserved here. Source mathematics was unchanged. No live attempt was consumed by these synthetic checks.

Exact final command, research/market_rsi working directory:

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 PYTHONHASHSEED=0 '/Users/estelle/Library/Application Support/MarketRSI/runtimes/ds-py312-20260912-01/bin/python' -B -m unittest experiments.test_nfl_ingame_close_score_possession_offset_v1 experiments.test_nfl_ingame_candidate_evidence_adapter_v2 -q
```

14/14PASS in7.624s: five candidate tests plus nine unchanged v2 tests. Candidate checks: exact bounds/zero/sign semantics, invalid inputs before solver, analytic-gradient finite differences, one fit call, identical numeric replay, check-label isolation, no retry on solver failure, recipe drift rejection, actual complete model-agnostic fourfold87prediction path, invalid accepted-parent evidence before any fit, and actual admission predicate under synthetic read/snapshot/worker boundary mocks. Isolated native capacity1 passes; capacity3, wrong batch and deadline mismatch fail. Parent original proofs and data in fixtures are synthetic, not semantic acceptance of actual historical artifacts; the synthetic identity SHA is patched only at its fixture boundary. `git diff --check` PASS.

Frozen SHA-256:

- production `8f0c13ee50eb19533c4861a8e62fcdb7d0ebbca7ddf89bb8cd38a43b81b7f6f7`
- tests `4ac3470689e473ec58ba814d101f89d4d66f7a8da989bbba2a701a3f8b001afc`
- scientific template contract `ec5b0233221a1ed5013fcd686c5a323afeb62d63b852c7f794a880882fd2b451`

No real Train/Dev/Final/raw artifact reads, live fitting, model/provider/account calls, network, shared R/H/scorer/worker changes, commits or global ledger writes by implementer. The already completed original response and fresh grant were read; no retry or new transfer occurred. Existing unrelated work preserved. Root owns independent source review, exact normalized parent acceptance, runtime bindings, native rehearsal, activation/accounting, results and feedback-dependent next choice. Current evidence supports implementation readiness only, not prediction improvement, H/R benefit or fixed-process superiority.
