# Gate 1 offered-operation mismatch — local causal repair

Status: unpublished candidate; independent post-fix review pending. This is an operational contract repair, not a scientific Controller decision or prediction result.

## Observation

An independent read-only agent reproduced a mismatch on the 324-file controlled-source digest `48b7b78f2839dc1a215cce28627956f890359ad23bf21a63b4fe5e7fcb614afa`: the no-catalog packet offered only `inspect_official_documentation`, but a crafted terminal call with `fetch_fixed_public_sample` passed `_submitted_action` and became a `bounded_plan`. The GLM response parser coerced arguments but did not enforce the JSON Schema enum. Outer review later rejected the plan for missing catalog, so this was not a network or protected-data bypass, but it could waste a paid Controller attempt. The original independent report is `AGENT_LOG_GATE1_FRESH_BOUNDARY_REVIEW_2026-09-22.md`.

## Repair and verification

- Added `test_hidden_trade_operation_fails_at_adapter_boundary` in `test_p0_gate1_controller_adapter.py`; it failed before the repair because `valid_plan_only_decision` was true.
- `p0_gate1_controller_adapter.py` now checks submitted operations against the operation enum actually offered in that turn before it returns `bounded_plan`. Unknown/unoffered operations fail at the adapter, and their raw response remains archived by the existing run path.
- Updated outer tests to expect current no-catalog packet rejection at the adapter. Future catalog-ready trade behavior remains covered only by an explicitly test-scoped packet, not by pretending the current production packet offers trade. Existing compiler tests separately cover exact catalog binding and plan tampering.
- After repair, 124/124 Gate 1 related unit tests pass and `git diff --check` passes. Fresh zero-provider, zero-network production-path canary `market-rsi-gate1-offered-operation-fix-canary-20260922-01` passes; provider calls, real cost, fetch and formal admission are all zero. The synthetic test ledger `$0.00005103` is not actual spend.
- Controlled-source digest after repair: `2544e25605a9c9d731784b492dc5c040f0b43aa47fc911b3f8a373db1312eb4e`. This is local and not the prior published version.

## Remaining gates

An independent reviewer must inspect this exact post-fix source, repeat the hidden-operation counterexample and check the offline catalog-ready positive path. Source freeze, controlled-file/dirty-scope review, publication, post-publication canary, a fresh paid Controller decision, and real Train catalog admission are separate gates. No paid call, public fetch, Dev/Final read or push occurred in this repair.
