# Outer data-audit rule: sample and clean without selecting an easy benchmark

Status: **P0 diagnostic rule, not a released model experiment or an admitted
dataset.** The supervisor authored this bounded source diagnostic and its
safety constraints; it was **not** a controller decision or a self-improvement
round. For future scientific sampling/cleaning choices the controller makes
the proposal, the inner researcher executes it, and the supervisor checks
these constraints. The user does not choose each routine step. Material scope
changes, a data purchase, or waiving the protected-test gate still require
their own authorization.

## Observed problem and source research

The 2023 archive has 237/285 strict market-to-schedule identities; 48 are
unmatched, including **47/92 scheduled games in Weeks 13–18**. Three fixed
markets have 0/6/137 in-game fills in a 5h window. The official
[historical-price API](https://docs.polymarket.com/api-reference/markets/get-prices-history)
returns about 1,020 one-minute points for the same windows, but only
41/34/133 adjacent value changes and long flat runs. Its documentation calls
these historical prices, not one executed trade or firm quote per minute.
Treating every minute as a distinct fill or silently dropping inactive games
would redefine the experiment. The existing 2025 sealed 40-game block has
only 11 dates, below our predeclared >=20 untouched-date gate.

The current [benchmark contract](../PREDICTION_BENCHMARK_V0_2026-09-16.md)
already requires chronological whole-game/date splits, the exact same eligible
rows, event-time label windows, zero-change baseline, and game-equal scoring.
The project's [rolling-origin source](https://otexts.com/fpp3/tscv.html)
supports past-only model fitting; it does **not** prove that these market
observations are complete or that missing trades can be filled with zeros.
This policy is a supervisor inference from those rules and the new source
audit, not an empirical result or a new literature claim.

## Sampling decision

1. **Population first.** Start from all 285 scheduled 2023 games, not only
   markets found by a search. Every game remains in the denominator with an
   explicit `mapped`, `ambiguous`, or `unmatched` status. Keep source revision,
   schedule hash, market token pair, game ID, and join reason. The 48 unmatched
   games are *missing in this archive classifier*, not proven absent from the
   exchange.
2. **Bounded diagnostic sample, not training/Test.** Before reading more
   fills, choose three mapped games from each of four predeclared week bands
   (1–6, 7–12, 13–18, 19–22) by ascending SHA-256 of a fixed seed and game
   ID. This yields 12 frozen games and preserves *all* unmapped games in the
   band denominators. It cannot be reselected after prices, fills, grades or
   errors. The frozen ignored receipt is
   `artifacts/p0-polymarket-2023-stratified-density-plan-20260917-01/`,
   selection SHA-256
   `69bbc3f4579e08e744eff31d042386185058c648890910f5b5d68f8e9116487e`.
   The 12 selected games were later queried once for fill counts; results and
   the first pre-query dependency failure are recorded in
   `DAILY_LOG_2026-09-17.md`. A 12-game diagnostic can rule out an implausible
   source; it cannot admit a season.
3. **All official plays for an admitted game.** Never choose a play because
   its *future* price moved, a label exists, or the model did well. If Train
   computation later needs fewer games, use a frozen date/week-stratified,
   outcome-blind hash sample from opened Train only, retain all predeclared
   play rows within a sampled game, and publish selection probabilities.
   Main evaluation uses the whole frozen cohort and each game/date, not the
   sampled Train subset. Any high-activity-only score is a labelled
   sensitivity, never the primary score.

## Cleaning and label rules

1. Preserve raw objects and immutable IDs/hash receipts. Normalize timestamp
   timezone and price/size units; map the YES token to the **home team** only
   after checking market identity. Keep exchange time, event time and any
   provider-publish/local-receive time separate. Historical event time alone
   is not proof of live availability.
2. Sort by event time plus an immutable tie-breaker. De-duplicate only the
   *same source trade ID/revision*, with a count and reason; do not merge
   separate same-second fills. Quarantine impossible prices outside [0,1],
   nonpositive sizes, contradictory token/market identities, corrupt records,
   reversed or unresolvable timestamps. Do not silently clip, interpolate or
   substitute a new source. Keep every exclusion reason and source hash.
3. Apply the **already declared** 60-second trade-price target unchanged:
   pre-play last true fill within 300 seconds; post target last true fill in
   the 60-second window ending at `t+60s`, strictly after the play. If either
   is absent or event ordering cannot be established, mark the label
   **missing with a reason**, not zero. A valid observed price change of zero
   stays in the sample. A minute-history point is not a true fill unless the
   source semantics are independently established; its long flat stretches
   are not deleted simply because they look uninformative.
4. Keep a row for each scheduled game/play and a separate `label_eligible`
   mask. Report reasons by season, week, date, game, play type, time-in-game
   and market-activity band defined from past-only data. Compare zero-change,
   ordinary strong baseline, and any candidate on the exact same eligible
   rows, and report both MSE and coverage over the **full intended universe**.
   Do not let a model improve MSE merely by abstaining on difficult rows.
5. If the original 60-second target is too sparse, stop that admission claim.
   A 300-second trade label, a historical minute-price label, or a quote
   target is a **new predeclared benchmark version** with its own semantics,
   baseline, cost/latency caveat and still-untouched test. No Dev/Final-driven
   target selection. Flat, quiet and zero-move segments stay in coverage
   accounting; filters/weights may be compared *only* as Train-only changes.

## Gatekeeper's stop/continue rule

The schedule-only 2025 role/date audit and frozen 12-game 2023 fill diagnostic
are now complete. Next audit the *actual* prior access receipts, to the extent
they exist locally, without opening protected prices or labels. A full
season-wide event-aligned support report would still be required for admission.
Compute coverage and paired precision by date/week, not by minute point or
play as if independent. The old 2025 Final cannot be promoted as a >=20-date
confirmation. If no independent >=20-date block or comparable target is
available, the supervisor records the exact gap, does not burn the $200
Tinker model cap, and returns the gap to the controller for a proposed new
time period/target version. It asks the user only for a genuine scope, rights
or spending decision—not for routine sampling or cleaning choices.
