# Historical researcher and forecaster interface — superseded

Do not connect this virtual-market interface to the new paid experiment. Use
[the active Kalshi protocol](PILOT_PROTOCOL_2026-09-07.md). The new roles are GLM
researcher/controller, Codex coder, and independent runner/grader; no forecasters
trade on experiment outcomes. Existing fixtures below are retained for history.

The governing study is `RESEARCH_PROTOCOL.md`. Each arm has a separate history.
No cross-task model checkpoint is inherited. Transfer tasks receive a frozen
researcher snapshot, never feedback from another transfer task. The public input
is built from an allowlist, not a copy of the runner's internal manifest.

This document specifies the next adapter. It is not a claim that independent
agents are running. The current fixture driver has zero real agent calls.

## Researcher

Input: allowed training data and historical development experience, baseline
model/settings, method registry, source-quality findings, costs and failures.
No final labels, final scores, future event data, execution keys or grader code.

Output: a fresh proposal ID, shared parent checkpoint, hypothesis, changed causal
stage, data/feature/trainer settings, code digest, expected cost/compute bound,
and the evidence supporting the change. It may choose difficulty and generate
derived training examples. Generated data must retain source/timestamp lineage;
it is never a substitute for actual external evaluation outcomes.

Do not force a particular training method or require every proposal to train.
A justified no-change decision is permitted and recorded. A multi-stage idea
is decomposed into identifiable ablations before attributing its result.

## Forecasters

Input: the exact same frozen proposal slate, permitted past evidence, score
contract and declared costs. Independent calls first; no future results and no
other forecaster's initial answer. Fixed identities; model/version/context and
usage logged. Forecasters may not run or modify the experiments.

Output: probability each candidate beats its parent on the frozen metric;
brief rationale and explicit uncertainty. Then a bounded virtual trading phase.
The pilot uses independent binary LMSR contracts with liquidity 10 and starting
cash 10 per identity across the slate. Only buying YES/NO shares is implemented;
no borrowing, short-selling, identity resets or hidden capital top-ups.

Strictly better development Brier loss settles YES. Equal or worse settles NO.
An infrastructure failure or missing evaluation remains unresolved. Forecast
Brier, virtual P&L, and candidate model Brier are different metrics; retain all.
Do not assume LMSR prices are calibrated or agents are truth-telling.

## Runner/grader

Receives forecasts before starting model evaluation. Owns exact data manifests,
scoring, eligibility masks, independent labels, immutable run claims, source
hash checks and append-only outputs. Every admitted proposal is evaluated in
this pilot; an unchosen experiment is not presumed to have failed.

Each candidate consumes the same approved development rows. Equal alert rate
is a ranking diagnostic, not a live strategy threshold. Any live threshold
must be calibrated using earlier data and account for missed opportunities.

For future arbitrary-code proposals, run in a separate OS/container identity
with no access to hidden data and no outbound network by default. The current
trusted-callable adapter does not provide that isolation, so do not connect
untrusted arbitrary Python to it.

## Experience passed to the next round

Preserve every proposal, prediction, candidate outcome, failed attempt, source
manifest, compute charge/estimate/reservation, and checkpoint lineage. Return
training evidence and allowed development feedback only. Final-holdout results
do not return to researcher memory. Record whether the next checkpoint was
chosen by market, average, or single forecaster; never change the selector after
viewing results.
