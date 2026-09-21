# P0 Gate 1 v0.1.14 live failure review — 2026-09-21

## Outcome

- Permanent ID: `market-rsi-gate1-controller-20260921-03`
- Published source: `market-rsi-protocol-v0.1.14`, commit `61cb1aa0ca103a9041b0010a1e99b1ce8775aafd`
- Provider samples: exactly 1; automatic retry: false
- Usage: 1,393 input tokens, 582 output tokens, finish reason `stop`
- Metered cost (not invoice): `$0.01384128`; reserved upper: `$0.05`
- Public fetch: false; formal data admitted: false; Dev/Final read: false
- Terminal cleanup: process absent and container absent

## What the Controller attempted

The response chose `2025_whole_season_trade_access` with source
`polymarket_official_trades`. It proposed a fixed lexicographic sample of at
most 20 public 2025 market identities and a bounded documentation/metadata
inspection. Because the submission was invalid, this content is preserved as
failure evidence only and is not an accepted decision or executable task.

## Exact failure layers

1. The pinned GLM template appended one empty `<|observation|>` marker after the
   single completed tool call. v0.1.14 classified all such trailing bytes as
   non-terminal content.
2. Independent offline replay after removing only that template marker exposed
   an additional undeclared empty field, `rights_check_placeholder`. The frozen
   contract requires an exact field set, so the response remains invalid.

The system did not delete the extra field, infer missing intent, repair the
answer, resample, fetch data, or reuse the permanent ID.

## Offline vNext repair

- Accept exactly one empty `<|observation|>` template terminator after exactly
  one complete tool call.
- Continue rejecting narrative, repeated markers, additional tool calls, and
  all undeclared or missing fields.
- Tell the Controller explicitly to submit exactly the declared fields and no
  placeholder fields.
- Check the exact field set before compiling a trusted plan-only task.

## Verification

- 43 adjacent Gate 1 tests passed (one attempted module name was absent; it was
  not counted as a product failure).
- 12 packet/public-fetch/watchdog tests passed.
- Full discovery ran 516 tests: 515 passed; the sole error is the pre-existing
  `memory_policy.test_final_recovery` source-artifact hash drift, outside Gate 1.
- Captured live response replay still fails with `submitted fields differ from
  frozen contract`.
- Zero-provider canaries passed:
  - `p0-gate1-controller-adapter-canary-20260921-04`
  - `p0-gate1-controller-outer-canary-20260921-03`
  - `p0-gate1-production-cli-canary-20260921-10`
- All three canaries performed zero provider calls, zero public fetches, and no
  formal data admission.
- The pinned tokenizer measures 1,406 input tokens for vNext; the unchanged
  3,072-token output ceiling gives a `$0.04415796` worst-case upper, below the
  `$0.05` per-attempt cap.

## Remaining boundary

The repair is local and unpublished. A future live decision needs independent
diff review, a fresh commit and annotated release on the user's fork, a
post-publication zero-provider canary, a fresh permanent ID, and separate paid
authorization. The failed v0.1.14 ID is terminal and must never be retried.
