# InGamePriorPlaySuccessUncertaintyStratifiedOffset-v4 — implementation

Date: 2026-09-29. Implementation/tests only; no real run or scheduler mutation.

- Controller SHA-256: `db9481637ab55dec104bdd9cde4a0199022ea404781e60bec9563c05aad94eb8`.
- Controller component/rule digests: `a0f6647768c575fa95b9826a917faf53baed4891125d549ae9d892cadfa7dbde` / `aa9a76e5a245c5cc353cb1ca236d19069f72cda1e522afad956cda72bb70bb4d`.
- Recovery selection/state-hint digests: `0d7e7fc61de795ca13ac546c7c96ffd55f2362bb62c94647a0eb2155b533003e` / `a702cf0354cdac9c088c742d1197ec41e80e4c00719f44fc487c2ff57ff63137`.
- Frozen 193-row feature/manifest hashes: `cca09f294f88f19a5cfa05fce294d6ec2a11c6264fed54840460784cbabea764` / `addececc96838399be8b9713b85048dba6c449e840aff6f69f099f1779750144`.

Files:

- `research/market_rsi/experiments/nfl_ingame_prior_play_success_uncertainty_stratified_offset.py` — SHA-256 `b827eecdd669451d92a24a1023e2407a10ddebd26585f4515e395c0f486ff589`.
- `research/market_rsi/experiments/test_nfl_ingame_prior_play_success_uncertainty_stratified_offset.py` — SHA-256 `5f0ae9f9e001b56e29bdd68f2fb48941ad37c4e58a0a7b9119e80d9638dcae5a`.

The runner reads and arithmetically validates the frozen prior-play feature for all 193 materialized games, preserves the v0 chronology/common mask and archived raw/ordinary/market-plus-state predictions, and fits exactly four no-intercept coefficient-one market-logit candidates. The exact low/high split is `p*(1-p) < 0.1875` versus `>= 0.1875`; deterministic analytic damped Newton uses ridge `16`, at most 50 iterations, gradient infinity tolerance `1e-8`, and no retry. The scorecard supplies proper scores/calibration, all folds, complete-date/week 10,000-draw paired intervals and the frozen decision.

Verification: focused `8/8 PASS`; adjacent uncertainty-audit and identity-calibration `20/20 PASS`; `py_compile` and `git diff --check` PASS. No real artifact was executed.

Post-review one-shot command:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONHASHSEED=0 \
PYTHONPATH=research/market_rsi /Users/estelle/LightHouse/venv_3.12/bin/python \
  -m experiments.nfl_ingame_prior_play_success_uncertainty_stratified_offset \
  --source-root "/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01" \
  --output "/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-ingame-prior-play-success-uncertainty-stratified-offset-20260929-01"
```

Dev/Final, network, provider, payment, publication and promotion remain closed.
