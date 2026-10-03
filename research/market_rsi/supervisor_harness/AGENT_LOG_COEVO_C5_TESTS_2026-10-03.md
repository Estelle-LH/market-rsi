# C5 disjoint tests

Registered by Supervisor before dispatch; last observedclock22:27:46UTC.
Own new experiments/test_nfl_ingame_curvature_unit_matched_brier_joint_offset.py
and append this log only. Worker owns production and has not started tests;
handoff sent before this assignment. Frozen contract2da17c7c unchanged.
Expected APIs: curvature_units, objective_gradient_hessian, optimize_brier,
fit_brier, replay_brier, load_parent, replay_parent, run. Read actual stable
source for signatures; synthetic data only for all fits. No oldsource/contract/
result/judge edits, real Train fits or commits. Reviewer remains independent.
This Supervisor coordination change is not autonomous R self-modification.

## 2026-10-03 22:34:07 UTC — Disjoint synthetic tests complete

Actual clock obtained from clock tool. Read the full frozen batch5 contract,
current runner, immutable C4 test/fixture helpers, AGENTS and evaluation skill
before writing. The skill kept paired-row/parent/scorer attribution explicit;
the user Open Discovery instruction remains authoritative. No literature
retrieval, new scientific selection, production/helper/contract/result edits,
real Train fits, provider calls, protected reads or commits in this role.

Changed only the registered new test file and this appended log. Runner remained
worker-owned at SHA021e347fce1692189dbe666c7367a833b83dc61c31f957a81fe95f0e7f08256b;
contract remained2da17c7c181ad3ffe050ac9c926bf3c0e27128f7d3a7e5aba2f1a9aca4b2f852.
Final test SHA5f656f5f8b9a1a5662957df86b05e7d608615daf9a232a89c5bc859b0f1d6a6a.

Sixteen focused synthetic tests cover analytic Brier gradient/Hessian finite
differences, conditional zero-point expected diagonal curvature and fit-only
units, deterministic actual synthetic optimization, both successful and
unsuccessful nonstationary phase1 continuation, zero-step stationarity,
truthful status/same prior/no restart, nonfinite x/fun/jac rejection,
25-iteration/60-proposal terminal caps, actual Hessian PD distinct from direction
floor, C4 exact design/scale/hash parity, primitive zero identity and replay,
check-label/future-column isolation, saved prior drift, four-fold parent replay
without parent fitting, portable seven-file/canonical-state/control/label
fail-closed checks, exact195→193+2→87 synthetic scoring, old KEEP unchanged,
source-admission failure/no overwrite, first-fit partial-receipt persistence
(started1/completed0/no retry), and preservation of a converged optimizer receipt
when later prediction validation fails. New tests fit only synthetic data.

Run history, preserved rather than claimed green retroactively:

- First focused run:14tests,1error/1failure,0.067s. Test-only issues were NumPy
  array assertEqual and a constant-F Armijo fixture that rounded to equality at
  tiny alpha. Corrected to exact array comparison and rejecting proposalF2 vs
  initialF1. No production/algorithm fix or tolerance change.
- Corrected focused run:14/14PASS,0.065s. Expanded pre-freeze status/failure
  coverage at worker request; next focused run16/16PASS,0.075s.
- First inherited in-game run:193tests,2errors,12.264s. Both existing admission
  tests rejected missing PYTHONHASHSEED, not candidate code/scoring. Launch
  corrected to the existing frozen value0, without relaxing admission.
- Final inherited run:195/195PASS,12.250s,exit0. Includes all16new tests and179
  inherited in-game tests. This is not a full repository green claim.
- git diff --check on the new test path passed before final freeze.

Final inherited command (source working directory /Users/estelle/Developer/market-rsi):

`env PYTHONPATH=research/market_rsi PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 '/Users/estelle/Library/Application Support/MarketRSI/runtimes/ds-py312-20260912-01/bin/python' -B -m unittest discover -s research/market_rsi/experiments -p 'test_nfl_ingame*.py'`

Focused command used the same DS Python/-B/thread launch and
`-m unittest experiments.test_nfl_ingame_curvature_unit_matched_brier_joint_offset -v`;
the focused run after additions used PYTHONHASHSEED20260929 but the final
inherited launch0 reexecuted the identical focused tests under frozen env.
Runtime:Python3.12.3/numpy1.26.4/SciPy1.14.0/sklearn1.6.1. Zero real Train fits,
zero provider/$0; Codex token/cost not metered here. Test elapsed seconds above
are not full research elapsed or predictive performance. Independent reviewer
receives exact hashes and actual outcomes; Supervisor alone checkpoints and
may authorize the one real candidate attempt after review. L1 test evidence
is not L3 prediction or R self-modification evidence.
