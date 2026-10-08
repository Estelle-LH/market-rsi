# Market RSI repository guidance

## Git and local configuration

Use descriptive branch names without the `codex/` prefix or other agent/tool
branding. Honor any exact branch name requested by the user.

Keep `.agents/` local and ignored by Git. Shared repository guidance belongs in
this `AGENTS.md`; reusable code and scientific harness policy remain versioned.

## Maintenance

For requested repository cleanup, layout changes or maintenance refactoring,
use the local `market-rsi-repo-hygiene` skill if available at
`.agents/skills/market-rsi-repo-hygiene/SKILL.md`. Otherwise follow the development
guide: preserve core behavior, source bindings and replayable checkpoints;
inspect the exact changed scope and run relevant regressions. Maintenance
guidance does not trigger routine cleanup during scientific research or add a
runtime admission gate.

Read [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for the current layout and checks.
The root `market_rsi/` package is a developer interface; source-bound core
modules remain under `research/market_rsi/` pending separately verified moves.

Existing [research instructions](research/market_rsi/AGENTS.md) still govern
work in that subtree. This routing note does not replace scientific protocols,
change permissions/budgets, authorize live runs, or activate this candidate
branch in the Supervisor checkout.
