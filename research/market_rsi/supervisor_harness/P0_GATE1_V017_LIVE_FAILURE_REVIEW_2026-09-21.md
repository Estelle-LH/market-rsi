# P0 Gate 1 v0.1.17 live failure review — 2026-09-21

## Outcome

Permanent ID `market-rsi-gate1-controller-20260921-05` used exactly one
Tinker-hosted GLM sample and was not retried. The provider returned normally
with `finish_reason=stop`:

- input tokens: `1468`
- output tokens: `349`
- metered cost, not invoice: `$0.01137483`
- requested and reported model: `zai-org/GLM-5.3:peft:262144`

The run failed closed. It created no `decision.json` or `task.json`, performed
no public fetch, admitted no formal data, and read no Dev or Final material.

## What the Controller selected

The Controller chose the useful current bottleneck:

- question: `2025_whole_season_trade_access`
- source: `polymarket_official_trades`
- fixed sample: at most three already scheduled 2025 NFL market identities
- bounds: 20 requests, 2,000,000 bytes, 20 minutes, `$0.05`
- operations: inspect official documentation and fetch a fixed public sample

All twelve scientific and operational fields were present and within the
frozen bounds.

## Exact failure

The frozen v2 contract also required the mechanical version field `schema`.
The Controller omitted only that field. Exact offline replay produced:

`ValueError: submitted fields differ from frozen contract`

Submitted fields had no extras; the only missing field was `schema`. Strict
review therefore rejected the whole plan instead of inventing or repairing a
model-authored value.

## Accounting and cleanup

- budget state: `metered_terminal`
- authoritative total metered spend after this run: `$85.087982132`
- authoritative available budget after this run: `$106.253436988`
- residual reservation from this run: none
- exact process and container check: clear
- Supervisor cleanup receipt: pass
- automatic retry: false

## Causal repair direction

`schema` is protocol metadata, not a scientific choice. The bounded offline
repair should remove it from model-authored fields and inject the one frozen
decision schema in trusted adapter code before contract validation. All real
research fields must remain model-authored and exact; missing, duplicate or
extra scientific fields must still fail closed. The preserved v0.1.17 response
must not be converted into an accepted decision or reused for execution.

Any future provider sample requires a new source version, fresh permanent ID,
post-publication zero-provider canary and separate explicit authorization.
