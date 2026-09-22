# 2024 complete Train-candidate denominator ledger

- 2026-09-22 16:16 ET — Implemented a zero-cost, offline ledger builder from the preserved 2024 schedule/PBP, catalog and mapping artifacts. No network, provider call, purchase, protected-state change, Dev/Final read, commit or push occurred. Existing artifacts were not modified.
- The first complete-schedule candidate artifact was `artifacts/nfl-2024-train-candidate-ledger-20260922-02/`. It was later superseded by `-03` after independent adversarial review found four provenance-validation gaps; see the final section below. Neither version makes an admission claim.
- Result is exactly **285 = 284 mapped + 1 explicit missing**. The missing schedule row is `2024_22_KC_PHI`, with `mapping_status=missing` and `missing_reason=moneyline_missing_or_ambiguous`. The sole unmatched catalog event (`17330`, slug `nfl-kc-phi-2025-02-09`) is preserved only as `unmapped_catalog_event_evidence` with `claimed_as_mapping=false`; the builder does not infer or repair the mapping.
- A first development output at `artifacts/nfl-2024-train-candidate-ledger-20260922-01/` was produced before the schedule-set-difference check was added. It is superseded, remains candidate-only, has no admission claim, and is not an input to `-02`. It was preserved rather than rewritten.

## Files added

| File | Purpose | SHA-256 |
| --- | --- | --- |
| `research/market_rsi/supervisor_harness/build_2024_train_candidate_ledger.py` | Hash-pinned offline builder; validates cross-manifest counts/hashes, extracts the 285 schedule IDs, preserves the one missing schedule row, emits only an allowlisted candidate schema. | `2f1a3aa60c5a5fde4ab98ecaaeb32d72cdbe9a7f181a9f060d4618e32100b34f` |
| `research/market_rsi/supervisor_harness/test_build_2024_train_candidate_ledger.py` | Focused denominator, identity, hash and split-boundary tests. | `77aad6abc66e6a053d38fc94de41230740c63b3c4ed1d0425497654be5a28678` |
| `artifacts/nfl-2024-train-candidate-ledger-20260922-02/ledger.json` | Deterministic 285-row Train-candidate ledger. | `67736e95b4f7199871dd339fe130f2d52c79030da3c60041635139b05418ec0a` |
| `artifacts/nfl-2024-train-candidate-ledger-20260922-02/receipt.json` | Candidate counts, ledger hash, zero provider cost and false admission claim. | `d5530943dcf6a8573e56106885fb51fe6764b108b432d4fe1c9cea7cbfa019d4` |

## Bound source evidence

The ledger contains the relative path and exact SHA-256 for each input. The production run independently rehashed every file and rejected any mismatch:

- capture manifest: `699b6d86a48f55fa3719fdc6195babb6b3e7dedeac24d3439f4a4e492c399945`
- schedule/PBP gzip: `16eb7af043e705bf6d75c2ea4e59b0b28f49d2ab17ea3e7d68ed2877a308ee7f`
- catalog manifest: `51b9b950566f981c1de386fc42ec5019cd97f5ff10dbd509a0713f9aab0ad54b`
- catalog payload: `c89f097b6538ceee46bb7b2950c3fd9ab6971fc5a39ddf00da61e5f589a3c0eb`
- mapping manifest: `481a059fec037efdb88fe55f8a2ddc9e6cf9f12c57739adff987af0dce93e7af`
- 284 mapped rows: `a8621f15ed703f01add64aaf4869b2ef262b4762d7bd241ba3168d040942008b`
- one mapping-failure record: `afb9a7631a5a79852901c0a72ef78509a74d3ae5be50967aa9156eef922ba8fd`

## Verification

Command: `PYTHONPATH=research/market_rsi python3 -B -m unittest research.market_rsi.supervisor_harness.test_build_2024_train_candidate_ledger -v`

Result: **6/6 passed**.

1. `285 = 284 + 1`, explicit missing row and `admission_claim=false`.
2. Duplicate mapped game ID fails closed.
3. Blank/missing mapped game ID fails closed.
4. Manifest denominator drift fails closed.
5. Any pinned source hash mismatch fails closed.
6. Output contains no Dev/Final fields.

Two fresh `/private/tmp` production-shape builds produced the same ledger SHA-256 before `-02` was written. `git diff --check` passed for the two source/test files. No orientation-verifier file was read or changed.

## Claim boundaries and remaining limits

- This is a **Train candidate only**, not Train admission, a model fit, a target table, a benchmark score or prediction improvement.
- Rights remain formally unresolved in the preserved source manifest.
- Outcome/token orientation remains unverified and is deliberately not inferred here.
- The ledger proves the complete 285-game denominator and preserves mapping failure; it does not prove trade coverage, label coverage, contemporaneous availability or 60-second predictability.
- The catalog payload is hash-bound, but the emitted ledger contains no prices, results, outcomes, token IDs, trades, model fields or Dev/Final fields.
- Existing protected state, the reserved Final candidate and all historical artifacts remain unchanged.

## Independent review remediation — superseding `-03`

- 2026-09-22 16:21 ET — Independent review returned **REPLAN**, not PASS. It reproduced four issues: callers could supply a fabricated but internally rehashed tree; the catalog payload was hash-bound but not membership-validated; an unexpected `dev_score` CSV column was silently ignored; and rows lacked their own source commitments.
- All four were fixed without changing `-01` or `-02`. The superseding candidate is `artifacts/nfl-2024-train-candidate-ledger-20260922-03/`.

### Fixes

1. The public `build(repo)` now accepts only the exact resolved canonical checkout and the seven pinned paths. It rejects a substitute checkout and any symlink component before hashing. Callers can no longer supply their own “expected” hashes to the production boundary.
2. The builder now parses the pinned 285-event catalog, checks unique event identities, requires the exact explicit failure `{event_id: 17330, slug: nfl-kc-phi-2025-02-09, reason: moneyline_missing_or_ambiguous}`, and proves catalog IDs equal 284 mapped IDs plus that one unmatched ID. Mapped event ID/slug pairs must match the catalog.
3. The mapped CSV header must equal the exact preserved 13-column schema. Extra or missing columns—including `dev_score` or any Dev/Final addition—fail before row construction.
4. Every one of the 285 rows now has a deterministic `row_commitment_sha256` plus explicit schedule/catalog/mapping source commitments and pinned per-row source-artifact hashes. The missing row separately binds the schedule identity, unmatched catalog evidence and mapping-failure record while keeping `claimed_as_mapping=false`.

### Final files and hashes

| File | SHA-256 |
| --- | --- |
| `research/market_rsi/supervisor_harness/build_2024_train_candidate_ledger.py` | `0299f344b217bee374e32f5141da5f06451758af064d952ff44a36a8a78cb34a` |
| `research/market_rsi/supervisor_harness/test_build_2024_train_candidate_ledger.py` | `d1b248069734cdd142e4a5f411c3a5f15c41b0ddcbf8e6acc79daa3f1ba3d93e` |
| `artifacts/nfl-2024-train-candidate-ledger-20260922-03/ledger.json` | `1c12f53955d1b80a79896c845a563745c910a639036fa9c1ff280a0990c35819` |
| `artifacts/nfl-2024-train-candidate-ledger-20260922-03/receipt.json` | `245d70bbfbd0e7f4432829640e8da1eca1e620ce94dcbb0971b170cba9c2e38f` |

### Final verification

The focused suite now passes **11/11** tests. In addition to the original denominator/identity/hash/split tests, it adversarially verifies:

- a fully rehashed substitute repository is rejected;
- a symlinked source is rejected even when its target bytes match the expected hash;
- fabricated missing event `999999` / `fabricated-event` is rejected after all dependent manifests are rehashed;
- an extra `dev_score` field is rejected after all dependent manifests are rehashed; and
- all 285 row commitments recompute and bind the pinned schedule and catalog hashes.

Two production-shape runs (temporary and `-03`) yielded ledger SHA-256 `1c12f53955d1b80a79896c845a563745c910a639036fa9c1ff280a0990c35819`. `git diff --check` passes. The result remains a zero-cost candidate ledger with `admission_claim=false`; rights, orientation, trade/label coverage and prediction quality remain unresolved.
