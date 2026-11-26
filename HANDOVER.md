# Round 17 harness handover

## Purpose

This branch is the reviewable source handover for the historical Round 17 earnings-research harness and its frozen 3.18 candidate. It contains the complete source export, exact frozen R/H programs, an offline verifier, and public-safe reproduction instructions.

The executable public-safe controls are in [`reproduction/round17/kit/`](reproduction/round17/kit/README.md).

It does **not** contain provider credentials, the experiment ledger, sealed SEC inputs, QA bodies, per-target predictions, private runtime receipts, or machine-specific paths.

## Current verified state

| item | value |
| --- | --- |
| branch | `codex/harness-incumbent-318-full-source` |
| historical source | `217b13e28cceaba628a5fe057f6860b56ecbd978` |
| candidate ID | `2493840dd5316742386e4123999bb40ba8baac9cdb5251b216dbeed31fa26c74` |
| R SHA-256 | `75f698c2a138d6ddbc94b01c9f9eca3cd1d8043f8a3ac02ab24c1656bee06f54` |
| H SHA-256 | `6d80fa56d0625188f4357d791a725083a6bab75119c0736424516b3dc5681350` |
| recorded result | 79.5 points / 25 companies = **3.18** |
| fresh reproduction | 81.0 points / 25 companies = **3.24** |
| fresh targets | 125 |
| fresh window sizes | `[10, 10, 5]` |
| fresh attributed cost | `$10.8757722` |
| final pending requests | `0` |

The fresh run reproduces 3.18 at or above its recorded value. The `+0.06` difference is not a new-model result: the candidate, opened-Train panel and scorer were unchanged. Treat it as run-to-run/provider variation unless controlled repeated evaluation proves otherwise.

## Quick verification

```sh
git clone --branch codex/harness-incumbent-318-full-source --single-branch \
  https://github.com/Estelle-LH/market-rsi.git market-rsi-round17
cd market-rsi-round17
python3.12 reproduction/round17/verify.py
```

Expected output:

```text
Frozen R and H match their original SHA-256 and compile without executing candidate code.
```

To recompute the recorded 3.18 from the owner's sealed report:

```sh
python3.12 reproduction/round17/verify.py \
  --score-report /path/to/local/TRAIN25-CLEAN-ROUND17-FINAL-COMPARISON.json
```

## Live reproduction workflow

A live reproduction requires the owner's local-only artifact archive. Do not attempt to reconstruct private inputs from this public branch.

1. Restore the exact historical source and verify its commit and tracked-file cleanliness.
2. Locally verify the frozen descriptor, R/H hashes, scorer, QA binding, Python runtime, point-in-time SEC corpus and ledger.
3. Create a fresh run ID and 90-minute clock. Seal an unreviewed runtime referencing the same candidate and an exact unmeasured company suffix.
4. Obtain an independent static review. Bind only that review receipt and checkpoint the reviewed runtime.
5. Run preflight against the exact runtime that will be launched:

   ```sh
   export PYTHON_BIN=/path/to/pinned/python3.12
   export REVIEWED_RUNTIME=/path/to/local/runtime-reviewed.json

   PYTHONPATH=tools:tests:research/market_rsi \
     "$PYTHON_BIN" -B tools/earnings_population_run.py \
     --runtime "$REVIEWED_RUNTIME" --preflight-only
   ```

6. Continue only after `{'preflight': 'PASS'}`:

   ```sh
   PYTHONPATH=tools:tests:research/market_rsi \
     "$PYTHON_BIN" -B tools/earnings_population_run.py \
     --runtime "$REVIEWED_RUNTIME"
   ```

7. Observe the true owner exit, then use the reviewed closure helper to verify company rows, fees, pending requests and the private checkpoint.
8. If the budget guard returns an unmeasured suffix, create a **new** reviewed runtime for only that suffix. Never replay completed companies or reuse an expired run ID.
9. Aggregate only verified closure rows. Require 25 unique companies in frozen order, 125 targets, settled owned requests and zero pending requests.

## Operational lessons from the fresh reproduction

- The original `$5 / 90 minute` guard is based on conservative reservation exposure, so one window did not fit all 25 companies. The successful reproduction used three disjoint windows of 10, 10 and 5 companies.
- The sealed historical candidate validation depends on exact local source/runtime bindings. Missing local sealed copies must be restored from authenticated checkpoints and verified by hash; they must not be synthesized.
- Use `close-clean-continuous-v4.py` for runtimes carrying the additional-budget grant. Earlier closure code omitted that grant type from its archive allowlist.
- The checkpoint metadata contract expects the most recent closure in `previous_closure` (singular). A full list may be retained separately, but it does not replace the singular compatibility field.
- Process exit alone is not a scientific result. A window is usable only after formal closure reports `VERIFIED_SCORED_WINDOW`, all owned fees are settled and pending count is zero.

## What is safe to publish

- source code and frozen R/H programs already present on this branch;
- source/candidate hashes;
- aggregate company/target counts, scores and total attributed cost;
- public-safe setup and verification instructions.

Keep the following local:

- API keys and credential-store contents;
- ledgers and request receipts;
- sealed SEC input bundles and private archives;
- QA/reference/heldout bodies;
- per-company and per-target prediction payloads;
- private runtime, closure and checkpoint artifacts.

## Recommended next research step

Do not optimize against this same inspected panel. First decide whether the goal is reproducibility or genuine improvement:

- For reproducibility, repeat the unchanged candidate under a preregistered seed/provider policy and report the score distribution.
- For improvement, freeze a new research question, change one causal stage, and evaluate on untouched evidence with paired diagnostics. Do not promote a candidate from the `+0.06` rerun difference alone.

## Maintainer checklist

- [ ] `python3.12 reproduction/round17/verify.py` passes.
- [ ] `git diff --check` passes.
- [ ] no local absolute paths or credentials appear in tracked files.
- [ ] README and this handover agree on hashes, counts, score and cost.
- [ ] any future live result links to its own reviewed runtime and formal closure rather than reusing historical run IDs.
