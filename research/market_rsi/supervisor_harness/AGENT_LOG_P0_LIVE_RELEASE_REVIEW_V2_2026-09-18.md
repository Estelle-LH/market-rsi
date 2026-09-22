# P0 live adapter v2 independent release review

- Status: completed — conditional pass for a code-only release; live/formal admission remains blocked
- Owner: independent reviewer (`canary_review`)
- Scope: read-only review of the one-task guest, production-capable adapter, publication manifest, tests, and code-only release boundary.
- Forbidden: source edits, external calls, model/container/data execution, protected-state or budget mutation, commit, tag, or push.
- Required verdict: whether the exact code-only diff is ready for release; this review cannot admit a live canary or a prediction claim.

## Independent result

- The reviewer ran 40 focused tests plus 29 adjacent tests under the pinned `runtime-py312`; 69/69 passed. No Docker, provider, E2B, data, budget or protected-state call occurred.
- The release manifest resolves 296 canonical files (295 Python files and one requirements file), SHA-256 `801a257a99071d0bf90b12c91d9df2e39c3370f32089f47096e34b9277a3cf44`, and includes the new adapters.
- One-task execution is launch-pinned to exact integer `1`; only the historical synthetic canary may use `20`. The live adapter always launches `1`.
- The evidence path fails closed and retains the first raw model response, requested/reported model and sessions, exact token counts/hash, frozen-rate cost, task/order/binding, raw ACK/event, process receipt, cleanup receipt and artifact hashes.
- Strict exact-type fakes and patches show the offline success path cannot reach Tinker, subprocess, Docker, E2B, budget or protected state.

## Release boundary

Code-only release verdict: **pass, conditional on inspecting an explicit staged-path allowlist before commit and tag**. The publication verifier binds its 296-file runtime list but does not prove that the whole Git commit excludes unrelated dirty files. The worktree also contains protected state, plans, logs and artifacts; those must remain unstaged. Raw process stdout/stderr are retained as length and hash rather than replayable raw streams; this is a nonblocking source-release caveat but must remain explicit. Public/synthetic classification still depends on the outer gate.

Live/formal verdict: **blocked as intended**. No outer publication/global-state/budget runner has passed, and `formal_admission=false` remains binding.
