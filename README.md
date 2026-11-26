# Earnings research harness · Round 17 (3.18 / 5)

This standalone source branch contains the historical harness implementation at `217b13e28cceaba628a5fe057f6860b56ecbd978`, the exact frozen R/H programs used for candidate 154, and a local score verifier. The recorded training evaluation completed 25 companies and 125 targets over windows 155, 156, and 158. The candidate scored 79.5 points, or 3.18 / 5 per company, and became the incumbent.

The branch is a source export. Runtime evidence, sealed inputs, score rows, keys, the ledger and machine-specific campaign plans are kept outside Git. Some historical Python files had absolute workstation paths. This export replaces the personal home prefix in those files with `/__LOCAL_RESEARCH_HOME__`. The two frozen programs retain their original bytes and hashes. See `source-export.json` for the scope and path adjustments.

## Fresh full-panel reproduction (tested 2026-11-26)

The same frozen candidate and original source were evaluated again with fresh provider responses. A newly assembled runtime was independently reviewed, bound, checkpointed and passed the original preflight before any live call. The original `$5 / 90 minute` reservation guard stopped each window before it could over-allocate, so the 25 companies were completed as three disjoint suffix windows of 10, 10 and 5 companies. No completed company was replayed.

| run | companies | targets | points | mean |
| --- | ---: | ---: | ---: | ---: |
| recorded Round 17 | 25 | 125 | 79.5 | 3.18 |
| fresh reproduction | 25 | 125 | 81.0 | 3.24 |
| difference | 0 | 0 | +1.5 | +0.06 |

The fresh run used candidate `2493840dd5316742386e4123999bb40ba8baac9cdb5251b216dbeed31fa26c74`, R SHA-256 `75f698c2a138d6ddbc94b01c9f9eca3cd1d8043f8a3ac02ab24c1656bee06f54`, H SHA-256 `6d80fa56d0625188f4357d791a725083a6bab75119c0736424516b3dc5681350`, and source commit `217b13e28cceaba628a5fe057f6860b56ecbd978`. Total attributed provider cost was `$10.8757722`; all owned requests settled and the final pending count was zero.

This reproduces the 3.18 result at or above its recorded value. It is **not** evidence of a new algorithmic gain: the candidate, opened-Train panel and scorer were unchanged, while provider outputs were fresh. Treat `+0.06` as run-to-run variation unless a controlled repeated evaluation establishes otherwise.

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

## Tested live sequence

The following is the sequence used for the fresh 25-company reproduction. Private artifacts are intentionally represented by placeholders and must remain outside Git.

1. Check out the exact historical source in the machine-local checkout expected by the sealed runtime. Verify `git rev-parse HEAD` is `217b13e28cceaba628a5fe057f6860b56ecbd978` and that tracked files are clean.
2. Verify the frozen descriptor, R/H hashes, scorer, QA binding, Python runtime and point-in-time SEC corpus locally. Assemble a **new** runtime with a new run ID and fresh 90-minute clock. Do not reuse the closed 155/156/158 or reproduction runtime IDs.
3. Have an independent reviewer check the unreviewed runtime. Bind only the review receipt, then checkpoint the reviewed input. The review must confirm the exact candidate, source, company suffix, budget, privacy boundary and no-overlap rule.
4. Run the explicit preflight, then the live command against the exact same reviewed runtime:

```sh
export PYTHON_BIN=/path/to/pinned/python3.12
export REVIEWED_RUNTIME=/path/to/local/archive/inputs/<fresh-run-id>/runtime-reviewed.json

PYTHONPATH=tools:tests:research/market_rsi \
  "$PYTHON_BIN" -B tools/earnings_population_run.py \
  --runtime "$REVIEWED_RUNTIME" --preflight-only

# Continue only when the previous command prints: {'preflight': 'PASS'}
PYTHONPATH=tools:tests:research/market_rsi \
  "$PYTHON_BIN" -B tools/earnings_population_run.py \
  --runtime "$REVIEWED_RUNTIME"
```

5. After the owner process returns a true terminal exit, run the reviewed closure helper locally to verify fees, pending requests, company rows and the private checkpoint. Never infer success from process exit alone.
6. If the window ends with `normal_yield.remaining_suffix`, prepare a new reviewed runtime for **only** that suffix. Preserve the completed prefix, use a fresh clock and run ID, and repeat steps 3–5. In the tested reproduction the verified window sizes were `[10, 10, 5]`.
7. Aggregate only verified closure rows. Require 25 unique companies in the frozen order, 125 targets, settled owned requests and pending count zero before comparing the mean with 3.18.

Provider credentials, the ledger, sealed inputs, QA bodies, per-target predictions and private closure checkpoints must stay in the local credential/artifact stores. Do not add them to this branch or pass a key on the command line.
