# 2024 outcome-orientation verifier — implementation log

- 2026-09-22 16:17 EDT — **PASS for an offline candidate-orientation checkpoint only.** Added `p0_2024_outcome_orientation.py` and `test_p0_2024_outcome_orientation.py`. No existing source, preserved artifact, ledger, admission receipt, catalog, board, or protected state was edited. No network/provider/fetch operation, Dev/Final read, commit, tag, or push occurred.

## Reused evidence and bounded design

This implementation reuses the already-preserved 2024 capture and the source analysis recorded in `AGENT_LOG_REAL_TRAIN_ADMISSION_CRITICAL_PATH_2026-09-22.md`; no new external fact or method was required, so no new live search was performed. Exact inputs are:

- `artifacts/nfl-2024-refresh-20260921-01/catalog/events.catalog.json`, SHA-256 `c89f097b6538ceee46bb7b2950c3fd9ab6971fc5a39ddf00da61e5f589a3c0eb`, 285 source events;
- `artifacts/nfl-2024-refresh-20260921-01/mapping/candidate_mapping.csv`, SHA-256 `a8621f15ed703f01add64aaf4869b2ef262b4762d7bd241ba3168d040942008b`, 284 mapped games; and
- the preserved gap event `17330`, slug `nfl-kc-phi-2025-02-09`, which has no mapping row because its moneyline was missing or ambiguous. The verifier emits no orientation or token pair for this event.

Alternatives considered:

1. Infer orientation from event/market slug order. Rejected: the capture contains both `home_away` and `away_home` event slugs, and market slugs include spelling changes such as `WAS/WSH` and `LV/LAS`. Slugs are identity checks only.
2. Assume outcome index 0 is home or away. Rejected: outcome order follows the provider market and is not a venue rule. Each outcome label is resolved through the exact alias table, and the token remains paired to the same source array index.
3. Fuzzy-match team names or reconstruct the missing Super Bowl from its slug. Rejected: this expands authority and hides ambiguity. The table accepts only 32 exact observed nicknames, and the missing event remains explicitly unoriented.

## Implemented boundary

- `p0_2024_outcome_orientation.py:20-35` freezes candidate receipt schemas, the exact catalog/mapping byte hashes and counts, and the one unoriented source event.
- `:37-80` owns the reviewed 32-team exact outcome-name table plus narrow identifier-only aliases for provider/nflverse abbreviations. The outcome table's canonical SHA-256 is `be32ebc8e106bcdc92a2b1b789bf6e7caa841770fa7638065aa7656e7358d201`.
- `:99-187` requires exact bytes, strict UTF-8/JSON/CSV shape, rejects duplicate JSON members and non-finite constants, validates the alias table, and rejects within-team duplicates or cross-team alias collisions. Caller-supplied alias-table expansion is not accepted.
- `:204-264` binds each mapping row back to one source event and one unique moneyline market, exact start/event/market/condition identity, explicit `slug_order`, recognized provider abbreviation aliases, and nflverse game-ID home/away order. Reversed home/away rows fail closed.
- `:267-323` requires exactly two unique names and two unique canonical token IDs, exact mapping/source array equality, and exactly the mapped home and away teams. It then preserves each outcome-token array pairing and emits a per-game candidate receipt bound to the catalog, mapping, alias table, source event, and mapping row hashes.
- `:326-426` rejects duplicated events/slugs/games/conditions/tokens, emits deterministic sorted candidate receipts, records every unrepresented source event without inferring it, and keeps source rights, provider authentication, formal Train admission, network authority, Dev, and Final false. The only public entry point pins the exact preserved hashes/counts and exact missing-event record.

The exact preserved offline replay produced 284 candidate receipts and one unoriented-source record. Canonical receipt-set SHA-256: `abc24dd40e43702e89308b6e2df6afd2a2b60c6e87e085d6e8b3f3c13792da70`. This hash is evidence of deterministic local output, not a persisted artifact or admission decision.

## Adversarial verification

Final source SHA-256: `fbe3b7e15aa829902bd5718c4c584d22a1be7ab3487061d15aff17cd610fdb4c`.

Final test SHA-256: `5e6a50dc8b0f0fd7e2b5d62cf7c44cd0a441073435db52c2df16cc05a0ad78e9`.

Pinned-runtime focused command:

```text
PYTHONPATH=research/market_rsi PYTHONDONTWRITEBYTECODE=1 \
  /Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python -B \
  -m unittest -v supervisor_harness.test_p0_2024_outcome_orientation
```

Result: **17/17 passed**. Coverage includes the exact 285/284 preserved replay; both slug-order variants; reversed source outcome order with intact token pairing; reversed mapped home/away rejection; alias collision and unreviewed alias-table rejection; unknown and duplicate outcome names; non-two-token and duplicate-token rejection; mapping/source token mismatch; catalog and mapping byte substitution; duplicate event identity; absent source event; extra moneyline ambiguity; deterministic output; and all candidate-only boundary flags.

Adjacent zero-provider suite covering this verifier, the v2 cursor contract, formal-admission and inventory validators, and legacy Gate 1 trade query: **73/73 passed**. Scoped `git diff --check` passed.

## Remaining gates

These three files are untracked development and are not in the controlled source manifest. The verifier authenticates only internal byte/hash/mapping continuity; it does not authenticate provider origin, establish source rights, repair the missing game, construct prices or targets, or admit any row to Train. A Supervisor must independently review the final bytes, decide source-rights coverage, preserve the missing event in the 285-game denominator, integrate the code into a new controlled release, and require a separate formal Train-admission decision before any training use.
