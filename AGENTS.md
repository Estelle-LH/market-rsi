# Market RSI repository guidance

For requested repository cleanup, layout changes or maintenance refactoring,
read and use the local
[market-rsi-repo-hygiene skill](.agents/skills/market-rsi-repo-hygiene/SKILL.md).
It preserves the working core, bound source paths and replayable checkpoints
while organizing the developer interface. It does not trigger routine cleanup
during scientific research or add a runtime admission gate.

Read [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for the current layout and checks.
The root `market_rsi/` package is a developer interface; source-bound core
modules remain under `research/market_rsi/` pending separately verified moves.

Existing [research instructions](research/market_rsi/AGENTS.md) still govern
work in that subtree. This routing note does not replace scientific protocols,
change permissions/budgets, authorize live runs, or activate this candidate
branch in the Supervisor checkout.
