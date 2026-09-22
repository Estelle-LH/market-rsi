# Supervisor data task — 2026-09-18

Status: **two bounded read-only audits completed; data admission remains closed. Neither is a GLM Controller decision or formal research round.**

Problem: The local B transport works, but prediction data have not passed admission. The old 2025 Final has only 11 distinct dates (minimum 20); 2023–2025 same-mechanism, event-aligned trade/PBP/label coverage and source-use rights are not verified. Prior 2025 Train and Dev exposure must not be called untouched.

Task for the data-audit worker:

1. Reconstruct an exposure/date ledger from existing *metadata and receipts only*. List opened Train, scored Dev, sealed Final, and unknown prior access separately. Do not read sealed prices, labels, outcomes, patches, or predictions.
2. For each 2023–2025 candidate season, reconcile scheduled NFL games to exact Polymarket market IDs, real timestamped fills, official play-by-play clocks, candidate 60-second and 300-second label availability, source hashes, and research-use rights. Preserve every scheduled game in the denominator and report zero-fill/missing games by week and date. Never treat price-history observations as real fills or impute a missing label.
3. Identify a genuinely untouched block of at least 20 dates, or report that none can be verified. Do not reopen or redefine the old Final. If the only option is prospective 2026 dates or a different market/target, present it as a scope decision, not a silent repair.
4. Return a source/row manifest, exposure status, missingness table, exact uncertainty, cost estimate, and pass/fail against the frozen data gates. No model fitting or scoring in this task.

Work limit: one bounded evidence pass from already local, nonsealed receipts. Stop after an hour without decision-relevant evidence and report the blocker. No data purchase, bulk download, paid model call, new sandbox, or benchmark opening. The trusted Supervisor reviews this audit before any GLM-led or paid prediction cycle.

Dispatch note: Initial new-subagent creation failed with `thread-store unsupported operation: paginated_threads`. The Supervisor then assigned both bounded read-only passes to the existing `/root/canary_review` subagent; both completed, with findings in `AGENT_LOG_DATA_ADMISSION_2026-09-18.md`. These were not GLM decisions or paid cycles.
