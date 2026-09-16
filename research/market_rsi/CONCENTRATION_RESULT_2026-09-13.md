# What drove the earlier improvement?

The two tokens that contributed most of the gain are the two outcomes of **one
market**. Their 1,481 paired quote updates were exact complements. No identical
full-message repeats were found in this selected stream. We must not count this
as two independent opportunities.

Both had a median bid–ask spread of 40 cents. Each had 11 midpoint jumps of at
least 10 cents; 10 of those changed only one side of the quote. The model did
better mainly when quotes were wide. It did worse in the narrow-quote diagnostic
bucket. This is evidence about recorded quotes, not evidence of executable profit.
No `last_trade_price` events were recorded for these tokens in this file; that
does **not** prove no trades occurred. Four messages per token had no event type,
so this audit cannot establish complete book/trade capture either.

One reporting limitation: the diagnostic's 10-cent spread boundary uses binary
floating point. Exactly-10-cent complementary quotes can fall into different
buckets. Do not use its exact boundary counts as a filter or an independent
finding. The 40-cent median, complementary-market finding and original scores do
not depend on that boundary. Preserve this published audit; do not silently fix
or rerun its result.

The original model, rows and scores are unchanged. This is a post-result
diagnosis, not another successful prediction experiment.

## Evidence

- Run: `artifacts/concentration-audit-20260913-01`.
- Source: `f8bb509`, published tag `pm-concentration-audit-v0.1.0` before replay.
- 63 tests passed; separate Linode synthetic replay/cleanup canary passed.
- Two complete passes, 26.324 seconds; compressed source hash
  `687bd727f2da89dfd51517eec863df50ae588c0fc0df84b532f938069b06b543`.
- Report internal hash:
  `34c4f3423fefc78e3884ca627c8ac3d9e32338d18d836be4f206055fea1b3e3f`.
- Report file hash:
  `fdbd65a6ab93a75029914df22f458b8dc2f4750a9a8ba9804bdb6e860f8250d5`.
- Worker 1476216 is absent; shared Linode lock was acquired and released in a
  read-only cleanup check. Both streaming transports completed.
- No Tinker calls, no fits. Original budget snapshot hash remains
  `518b0b840cc1f5c242494d44b0562b63612b321fd8e4e38c9225953304104a97`.

Both arms of the next comparison receive this same finding. Neither arm gets
permission to change the external target or discard wide-spread outcomes after
seeing their future labels. See [audit protocol](CONCENTRATION_AUDIT_2026-09-13.md).
