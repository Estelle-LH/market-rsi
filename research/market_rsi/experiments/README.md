# Task adapters and candidates

This directory contains task-specific prediction code. It is downstream of the
Supervisor loop: the Controller proposes a recipe, while the task adapter
defines rows, targets, baselines and scoring semantics.

## Current contents

- `nfl_ingame_price_data.py` — historical trade-VWAP rows and availability
  checks.
- `nfl_ingame_price_change_train_diagnostic.py` — opened-Train diagnostic
  runner for the current NFL price-change task.
- `nfl_ingame_price_score.py` — paired, game-equal scoring and baseline
  comparison.
- `nfl_ingame_candidate_evidence_adapter*.py` — evidence/feature adapters used
  by the price path.
- `price_candidates/` — versioned candidate sources and their local tests;
  these are experiment outputs, not another production entrypoint.
- `extract_*.R` and feasibility audits — historical data preparation and
  diagnostic support, not live acquisition.

## Boundary

The current task predicts a historical trade-VWAP change, not an executable
quote or guaranteed trading profit. The adapter must not silently change the
target, horizon, row availability, split or scorer. A new task such as
equities/earnings should receive its own adapter and benchmark profile rather
than being mixed into the NFL modules.

## How this connects to the loop

```text
supervisor_harness/
  → candidate author and bounded worker
experiments/
  → task rows, target, candidate and score
data_scientist_harness/
  → release, provenance and researcher-facing controls
```

Use the root [Architecture](../../../docs/ARCHITECTURE.md) for the complete
round flow and [Repository structure](../../../docs/REPOSITORY_STRUCTURE.md)
for placement rules. Raw data, generated receipts and run logs remain local.
