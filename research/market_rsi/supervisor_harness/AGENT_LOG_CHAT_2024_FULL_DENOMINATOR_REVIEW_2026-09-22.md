# DONE · P0 285-game ledger rereview

- Visible task: `01a0c589-757c-7991-8ed7-164d8eb5eb2c`
- Assigned: 2026-09-22 16:12 ET
- Role: independent, read-only reviewer
- Network/provider/Dev/Final/admission authority: none

## Scope

Review the deterministic offline 2024 candidate ledger after implementation lands. The acceptance boundary is exactly 285 unique schedule rows: 284 mapped rows plus one explicit unresolved row for nflverse `2024_22_KC_PHI`, Polymarket event `17330`, reason `moneyline_missing_or_ambiguous`. The reviewer must challenge duplicates, denominator drift, source-hash substitution, inferred rows and any Dev/Final fields.

## Final independent verdict

`REPLAN`; do not freeze the reviewed snapshot.

Positive evidence:

- Canonical sources independently reconcile to 285 unique schedule games, 284 unique mapped games/events and one explicit missing schedule row `2024_22_KC_PHI` with event evidence `17330`.
- Two canonical serializations were byte-identical at SHA-256 `179d701a0075f55e1fec3c57a29a61d50ac1ab4868b96f2326baa76e86f9a8c2`.
- The focused suite passed 6/6 and stale expected-hash tampering was rejected.

Blocking findings independently reproduced:

1. Fully fabricated schedule/catalog/mapping inputs were accepted when the caller supplied matching hashes, while the output labelled them with canonical source paths.
2. The catalog payload was not parsed, so rehashed event `999999` / slug `fabricated-event` was accepted as the missing evidence.
3. An added `dev_score` input column was silently accepted and discarded instead of failing closed.
4. Source hashes appeared only at the ledger top level; individual rows lacked source commitments.

Reviewed source SHA-256: `2f1a3aa60c5a5fde4ab98ecaaeb32d72cdbe9a7f181a9f060d4618e32100b34f`. Reviewed test SHA-256: `77aad6abc66e6a053d38fc94de41230740c63b3c4ed1d0425497654be5a28678`. The implementation owner received all four counterexamples for a superseding candidate.

## Superseding -03 rereview

Final scoped verdict: `PASS` for the exact ledger checkpoint.

- Builder SHA-256: `0299f344b217bee374e32f5141da5f06451758af064d952ff44a36a8a78cb34a`
- Test SHA-256: `d1b248069734cdd142e4a5f411c3a5f15c41b0ddcbf8e6acc79daa3f1ba3d93e`
- Ledger SHA-256: `1c12f53955d1b80a79896c845a563745c910a639036fa9c1ff280a0990c35819`
- Receipt SHA-256: `245d70bbfbd0e7f4432829640e8da1eca1e620ce94dcbb0971b170cba9c2e38f`
- Focused tests: 11/11 passed.
- Separate probes rejected a rehashed substitute repository, matching-hash symlink, fabricated event `999999`, and extra `dev_score`, `Dev`, or `Final` columns.
- All 285 row commitments and explicit source bindings were independently recomputed; all matched and were unique.
- Exact denominator remained 285=284+1; the missing row is `2024_22_KC_PHI` with event evidence `17330`, `claimed_as_mapping=false`.

No network/provider call, Dev/Final read, admission, release, commit or push occurred. This PASS does not grant data rights or formal Train admission.
