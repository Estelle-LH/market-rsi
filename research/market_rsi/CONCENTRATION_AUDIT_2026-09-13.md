# Why the September 9 result is concentrated — fixed diagnostic

Question: are the two tokens dominating the already completed result separate
evidence, duplicated deliveries, or one market's complementary quote movements?
User approved this audit before proceeding with the memory comparison. It is not
a retry, refit, changed objective or deletion of losing data. Preserve the old run.

Replay only the exact Sep09T12 object twice: 18,153,334 compressed bytes/pass,
expected SHA687bd727f2da89dfd51517eec863df50ae588c0fc0df84b532f938069b06b543.
First reproduce the entire frozen profile; select the two highest baseline-SSE
tokens by the already recorded order (score indices316/317, source indices324/325).
Second inspect only those tokens' complete-file messages. Reproduce their old
sample counts and sufficient statistics before reporting new diagnostics.

Report same market, same-message/same-time pairs, complementary BBO relationships,
identical full-message repeats, bid/ask/mid/spread distributions, boundary quotes,
zero-size updates, recorded trade messages and empty-depth observations. A missing
trade message is not proof no trade occurred; an identical message is not by
itself proof of erroneous delivery. Never deduplicate the original scoring rows.

Fixed descriptive thresholds: a large midpoint jump is >=$0.10; a rapid exact
roundtrip returns to its prior midpoint within60s after such a jump. Report old
score contributions for rows with either target endpoint spread>$0.10 versus
the remaining rows. These future-endpoint buckets are post-result diagnostics,
NOT a prediction-time filter or a newly chosen primary metric. Do not create a
cleaned score or pick a new model from them. No quote sequence/identifier export.

Research accessed2026-09-13, before implementation:

- Query `site:docs.polymarket.com websocket market channel price_change best_bid
  best_ask hash timestamp`; read the official message examples for price_change,
  book and last_trade_price, including their different fields:
  https://docs.polymarket.com/api-reference/wss/market
- Query `site:docs.polymarket.com tokens yes no complementary orderbook buy sell`;
  read Outcome Tokens and Split/Merge: a market has two collateral-linked outcomes.
  https://docs.polymarket.com/concepts/positions-tokens
- Read Prices/Displayed Price/Order Book: a midpoint is not necessarily tradable;
  the displayed-price rule switches to last trade for spreads>$0.10. This motivates
  a spread diagnostic, NOT automatic adoption of its display rule as our objective.
  https://docs.polymarket.com/concepts/prices-orderbook

Current documentation is conceptual guidance, not proof of historical feed
semantics or capture completeness. We inspect the archived bytes directly.
Reuse the existing published parser/kernel and paired-error method unchanged.
No new general harness component; this is a bounded external audit with its own
tests, synthetic Linode canary and annotated tag before real replay. Same600s,
1GiB combined process limits and shared Linode lock. Zero Tinker/E2B calls.
Original capture attestation and formal evaluation gates remain unchanged.

Next comparison preparation: current filename-only inspection finds513 objects
over23 dates, including later Sep10–13, rather than only the six dates in the old
inventory. These are availability metadata, not cleaned/admitted files or20
untouched final sessions. Do not open candidate final-period contents during
controller development. Record a new bounded manifest and chronological roles
before model work. No new data purchase is necessary just to inspect this archive.

Implementation: audit_tools/concentration_audit.py, run_concentration_audit.py;
test_concentration_audit.py plus frozen paired-score/sample/stream regressions.
Outcomes are recorded after execution, not presumed here.
