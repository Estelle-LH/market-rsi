# Earnings research harness · Round 17 (3.18 / 5)

This standalone source branch contains the historical harness implementation at `217b13e28cceaba628a5fe057f6860b56ecbd978`, the exact frozen R/H programs used for candidate 154, and a local score verifier. The recorded training evaluation completed 25 companies and 125 targets over windows 155, 156, and 158. The candidate scored 79.5 points, or 3.18 / 5 per company, and became the incumbent.

The branch is a source export. Runtime evidence, sealed inputs, score rows, keys, the ledger and machine-specific campaign plans are kept outside Git. Some historical Python files had absolute workstation paths. This export replaces the personal home prefix in those files with `/__LOCAL_RESEARCH_HOME__`. The two frozen programs retain their original bytes and hashes. See `source-export.json` for the scope and path adjustments.

## Start locally

```sh
git clone --branch codex/harness-incumbent-318-full-source --single-branch \
  https://github.com/Estelle-LH/market-rsi.git market-rsi-round17
cd market-rsi-round17
python3.12 reproduction/round17/verify.py
```

The verifier checks the exact frozen-program hashes and compiles the source without executing a candidate. It uses the standard library. The historical harness CLI and a small offline regression are available with the source on the Python path:

```sh
PYTHONPATH=tools:research/market_rsi python3.12 -B tools/earnings_population_run.py --help
PYTHONPATH=tools:tests:research/market_rsi python3.12 -B -m unittest test_earnings_population_loop
```

## Recompute the recorded 3.18 locally

Provide the exact local `TRAIN25-CLEAN-ROUND17-FINAL-COMPARISON.json` report from the sealed experiment archive:

```sh
python3.12 reproduction/round17/verify.py \
  --score-report /path/to/local/archive/TRAIN25-CLEAN-ROUND17-FINAL-COMPARISON.json
```

This checks the report hash, checks all company and target awards, and recomputes the result. It makes no API calls and prints only aggregate scores.

## Start a fresh evaluation using the original gates

This published branch is intended for source review and local verification. The live harness checks the original Source commit, exact runtime bindings and clock. For a fresh authorized evaluation, start from the original local checkpoint (`codex/local-incumbent-318` in the owner's workspace), with the original private config and artifact layout still in place. The original owner prepares and independently reviews a fresh runtime referencing the frozen candidate and the same training split. Required local inputs include the frozen descriptor and source, point-in-time SEC corpus, original scorer and QA, ledger, Python 3.12 runtime, Docker environment, and provider credential. Keep credentials in the original local credential store or environment.

Run the original entry point against that **newly reviewed runtime**:

```sh
PYTHONPATH=tools:research/market_rsi python3.12 -B tools/earnings_population_run.py \
  --runtime /path/to/local/fresh-runtime-reviewed.json --preflight-only
PYTHONPATH=tools:research/market_rsi python3.12 -B tools/earnings_population_run.py \
  --runtime /path/to/local/fresh-runtime-reviewed.json
```

The second command is a live evaluation and may accrue provider fees. The old 155, 156 and 158 runtime receipts have closed clocks. The 3.18 result is from the recorded training panel. A fresh provider run may produce different predictions.
