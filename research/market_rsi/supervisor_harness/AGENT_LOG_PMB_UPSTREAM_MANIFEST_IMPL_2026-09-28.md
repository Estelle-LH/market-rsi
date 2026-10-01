# PMB upstream and episode manifest implementation — 2026-09-28

- Assigned at `2026-09-28T23:15:34Z`; base HEAD `f06214b3bb521096078d897fe60ec9ba589c00c6`; dirty Market RSI diff digest `ec4ca5ae3a5975f4c5647e4e3126ef8d5c8810c0dbfb3ece20770ed135e84f6b`.
- Write scope: `pmb_simple_lane/upstream_lock.py`, `episode_manifest.py`, one focused test and this log.
- Boundary: synthetic local bytes only; no clone/fetch, package install, PMB source, public episode, provider or protected data.

## Material checks

- `2026-09-28T23:16Z` — Read the accepted v1/v2 PMB replan, independent rereview, repository `AGENTS.md`, and the `indicator-prediction-evals` skill plus evaluation gates. Reused the accepted PMB paper/repository findings; this bounded implementation did not perform a new network query.
- `2026-09-28T23:18Z` — Confirmed the prospective upstream identity is an exact commitment only: official URL `https://github.com/oddpool/PredictionMarketBench.git`, 40-lowercase-hex commit `611d66941717310858683278940df21c33c406f2`, exact file tree, exact MIT license commitment and exact import-origin set. The verifier invokes neither git nor network and always returns `runtime_admitted=false`.
- `2026-09-28T23:20Z` — Implemented four-role episode commitments with exact required file names/hash/length, immutable UTC dates, permanent diagnostic treatment of all four public January 2026 episode IDs, role/date/file disjointness, permanent prior-exposure taint, strict chronology and sealed-Final pre-open floor of 20 distinct untouched dates. Validation reports `data_opened=false` and `admission_granted=false`.
- `2026-09-28T23:21Z` — Added explicit path defenses: canonical relative paths, absolute and pairwise non-nested role roots, no role-root/checkout/episode/file/import symlinks, resolved containment and exact materialized file sets. Synthetic materialized bytes are read only when a caller explicitly invokes the verifier; manifest validation itself does not resolve or open hidden paths.
- `2026-09-28T23:22:57Z` — Focused test command: `python3 -m unittest -v research.market_rsi.tests.test_pmb_simple_lane_upstream_manifest` → **13/13 PASS** in 0.010s. Negative coverage includes wrong URL/SHA, unknown fields, tree/license drift, dirty checkout, import diversion, symlinks, public-episode relabeling, missing files, path traversal, cross-role date/file reuse, prior exposure, 0–19 distinct Final dates, 20 Final episodes on one date, chronology and nested roots.
- `2026-09-28T23:22:57Z` — `python3 -m compileall -q` on both modules and the focused test → **PASS**; `git diff --check` on the owned source/test/log paths → **PASS**.

## Exact owned files and SHA-256

- `research/market_rsi/pmb_simple_lane/upstream_lock.py` — `970feed94a3f258d6a624794540e7da4f1faf9665f206e2a9544619271db42f1`
- `research/market_rsi/pmb_simple_lane/episode_manifest.py` — `44f1cfdf9ea70815846bf61e7eee9607712e10d09895f5079ce8eb03f4a8481f`
- `research/market_rsi/tests/test_pmb_simple_lane_upstream_manifest.py` — `fdb0cda1f5a8500df70f895a94d87a11ad8ffd049b4989915ffad285430c413e`

Base HEAD remained `f06214b3bb521096078d897fe60ec9ba589c00c6`. No network, clone/fetch, install, PMB or real episode bytes, provider, protected data/state, Docker, release, commit, tag or push was used.

Result: **PASS for the assigned synthetic implementation step.** It supplies prospective commitment validation only; authorized upstream intake, actual episode admission, execution and independent integrated review remain required.
