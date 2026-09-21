# P0 Gate 1 v0.1.16 live failure review — 2026-09-21

## Outcome

Permanent ID `market-rsi-gate1-controller-20260921-04` used exactly one
Tinker-hosted GLM sample and then failed closed. There was no retry.

- reported model: `zai-org/GLM-5.3:peft:262144`
- finish reason: `stop`
- input tokens: `1406`
- output tokens: `465`
- metered cost, not invoice: `$0.01248291`
- provider receipt SHA-256:
  `1fd3f095a107cffafc6b8efc29390674904f70476c3a959487b998fd7e709145`

No Controller decision or task was admitted. No public request, data
admission, training, Dev/Final access, or second model sample occurred. Exact
process and container cleanup passed.

## What the Controller chose

The response selected the `2025_whole_season_trade_access` question and the
official `polymarket_official_trades` source. It proposed a bounded check of
whether official market and trade interfaces cover the 285 scheduled 2025
games, with 10 requests, 2 MB, 15 minutes, and `$0.00` downstream provider
cost. This is directionally relevant to the active data-admission bottleneck.

This content is not an accepted plan. It is evidence about the failed first
response only.

## Exact failure

The single tool call contained `rights_check` twice. The two values were not
identical. Replaying the immutable raw response through the published parser
raises:

`AdapterProtocolError: empty or duplicate GLM tool argument`

The protocol correctly refused to choose the first value, choose the last
value, merge them, or edit the model response. The prior v0.1.15 repair was
unrelated: it allowed one empty template terminator but deliberately retained
strict duplicate and undeclared-field rejection.

## Causal interpretation

The scientific choice was usable; the free-form safety field was the failure
surface. `rights_check` is not a scientific degree of freedom. Source access,
purchase prohibition, write prohibition, research-use verification, and
sealed-data boundaries are Supervisor policy. Letting the Controller rewrite
that policy adds format risk without adding useful research authority.

The bounded repair to test offline is therefore:

1. remove free-form `rights_check` from the model-authored submission;
2. bind a versioned, trusted rights-policy identifier in the packet and broker;
3. have trusted compilation attach the corresponding policy to the task;
4. keep duplicate/extra model fields fail-closed;
5. add regression tests using this exact failed response shape;
6. require a fresh packet, source release, independent zero-provider canary,
   fresh permanent ID, and separate authorization before any future sample.

This review does not authorize that future sample or a public data fetch.

## Evidence

- run result: `artifacts/market-rsi-gate1-controller-20260921-04/result.json`
- adapter result:
  `artifacts/market-rsi-gate1-controller-20260921-04/adapter/market-rsi-gate1-controller-20260921-04/result.json`
- immutable raw response:
  `artifacts/market-rsi-gate1-controller-20260921-04/adapter/market-rsi-gate1-controller-20260921-04/raw-response.txt`
- provider receipt:
  `artifacts/market-rsi-gate1-controller-20260921-04/adapter/market-rsi-gate1-controller-20260921-04/provider-receipt.json`
- Supervisor result:
  `artifacts/market-rsi-gate1-controller-20260921-04-supervisor/result.json`
- cleanup receipt:
  `artifacts/market-rsi-gate1-controller-20260921-04-supervisor/terminal-cleanup.json`
- budget receipt:
  `budget-authoritative-20260916-01/market-rsi-gate1-controller-20260921-04.metering.json`
