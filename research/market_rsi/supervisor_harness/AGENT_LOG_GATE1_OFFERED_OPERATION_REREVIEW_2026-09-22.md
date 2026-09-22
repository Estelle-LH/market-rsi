# Gate 1 offered-operation repair independent re-review

Read-only independent review completed on controlled-source digest `2544e25605a9c9d731784b492dc5c040f0b43aa47fc911b3f8a373db1312eb4e`. Verdict: **PASS for the bounded local offered-operation gate only**.

- The former crafted `fetch_fixed_public_sample` call against the no-catalog packet now fails in `p0_gate1_controller_adapter.py` before `decision.json` or `task.json` is written: `operation was not offered in this Controller turn`.
- The exact offered operation enum comes from the packet's actual tool parameters. The adapter checks against it rather than relying on JSON-schema compliance by the model.
- Document-plan and review-only-proposal paths still work. An explicitly test-scoped catalog-ready packet still compiles a synthetic, network-disabled trade plan; this does **not** advertise trade access in the current production packet.
- Independent reviewer recomputed the controlled-source digest before and after checks, reproduced the old counterexample rejection, ran the pinned-runtime Gate 1 suite (124/124), four focused cases, and `git diff --check`.
- Fresh production-path canary `market-rsi-gate1-offered-operation-fix-canary-20260922-01` passed with matching source and module hashes. Provider calls, actual provider cost, and public fetch were zero. Formal admission remains false. Its synthetic ledger amount is not actual spend.
- No new P0 was found in this narrow review. The reviewer made no edits and did not use provider/network/Dev/Final/release/push.

This does **not** authorize publication, paid Controller sampling, a real Train catalog, or a prediction-improvement claim. Those are separate gates.
