# Earnings-event task boundary

This is the next task profile for Market RSI. It defines the boundary for the
new adapter; it does not authorize data collection, model calls or trading.

## Research question

Given information available before a scheduled corporate earnings event, can a
researcher find a repeatable signal in the subsequent earnings surprise or
post-announcement price response that survives costs and time-ordered
out-of-sample evaluation?

The task must keep two targets separate:

1. **Event prediction:** surprise or directional response relative to a frozen
   pre-event information cutoff.
2. **Trading value:** a position/exit rule evaluated only after the forecast is
   frozen, with spreads, fees, slippage, holding window and exposure recorded.

## Required adapter contract

The future adapter must declare, before a run:

- event identity, announcement timestamp and information cutoff;
- point-in-time inputs and their publication timestamps;
- target definition and forecast horizon;
- train/dev/final split by event date, with no issuer or announcement leakage;
- market, analyst-consensus and persistence baselines;
- statistical metrics, trading simulation assumptions and minimum coverage;
- missing-data, revision, duplicate-event and after-hours handling;
- candidate, parent and researcher/harness version hashes.

## Current state

The adapter and scorer are not implemented in this repository snapshot. The
existing NFL/prediction-market profiles remain under their historical paths for
replay and audit, but they are not the active benchmark or release target.
The next implementation should add one self-contained earnings adapter and
profile here, then add its tests to the developer suite without changing the
protected co-evolution kernel.

## Boundary with the engine

The task adapter owns rows, labels, baselines, scoring and trading assumptions.
The Supervisor engine owns review, execution, feedback, memory, R/H selection
and rollback. A task change must not silently change the engine, and an R/H
change must not rewrite the earnings data or scorer.
