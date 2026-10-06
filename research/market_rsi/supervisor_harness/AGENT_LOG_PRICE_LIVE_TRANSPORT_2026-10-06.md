# Price live role transport — integration agent log

Scope: human-directed `H` integration for one two-round price Discovery pilot.
Owner: `/root/price_live_transport_20261006`; Git checkpoints owned by Supervisor.
Owned files: `supervisor_harness/price_account_roles.py`,
`supervisor_harness/test_price_account_roles.py`, and this log. No other source,
data, historical result, permission or ledger edited by this agent.

## Source and authority inspected

Read local `AGENTS.md`, `RESEARCH_STATE.md`, `RESEARCH_SUPERVISOR.md`, existing
account Controller consumer/transaction, the dispatched integration plan,
Market RSI research-progress skill and OpenAI-docs skill. Existing old batches,
caps and permission history are not reset. The role extension requires a new
whole-role exact grant; the transport does not infer one from implementation
authorization or the old Controller-only grant.

Pinned local CLI: `/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex`.
SHA256: `6b582e8813ce7e8ed4c52814ee5cf230dba647bf2292df747a4003f2657ef201`.
Requested model: `gpt-6.1-sol`; serving snapshot remains `unknown`.
No credential/config-secret reads or output, live account calls, real Train
reads, fits, external data/literature acquisition or Git commits performed.

## Local capability investigation and rejected route

Read-only CLI help/features and local app-server JSON-schema generation were
used to inspect the actual installed interface. The app-server schema was
generated under `/private/tmp/price-cli-schema-20261006`; this local generation
does not initialize an account thread or call a model.

Official primary references read:

- https://developers.openai.com/codex/config-reference/
- https://learn.chatgpt.com/docs/hooks
- https://developers.openai.com/codex/app-server/

Initial hook-only route was rejected during Supervisor review. Hook errors can
fail open, untrusted hooks can be skipped, and hosted search does not traverse
local execution hooks. Parsing strict config and executing an inert deny
program were therefore insufficient to prove complete execution closure.
`--ignore-rules` and `--dangerously-bypass-hook-trust` were removed; neither is
part of the final route. The unused hook helper/tests were removed rather than
retained as an alternate fallback. This finding is a limitation, not a live
canary or scientific experiment.

An empty-stdin local exec config probe returned `No prompt provided via stdin.`;
it established parsing only. App-server schema generation with `--strict-config`
is unsupported, so generation did not establish an actual startup policy.
App-server help does not expose `--ignore-user-config`; the final command does
not invent that flag. No config/trust/safety bypass is used.

## Implemented route

The single live route is pinned CLI app-server JSON-RPC over stdio, with hosted
search/apps/plugins/MCP-related features off, no dynamic tools, and explicit
`environments: []` at both thread/start and turn/start. Installed generated
ThreadStartParams/TurnStartParams schemas describe empty environments as
disabling environment access; ThreadStartResponse distinguishes `[]` from
unknown `null`. Before any turn, the original response must acknowledge empty
environments, the exact configured model, and no loaded instruction sources.

The batch preflight performs a fresh, explicitly authorized metadata-only
initialize/thread/start and saves actual wire acknowledgement. It sends no
turn/start and no private evidence. Failed or uncertain originals are retained
without automatic retry. Completed source/grant-bound replay creates no thread,
including after the selection deadline. Actual CLI initialization remains
unexecuted pending the fresh merged grant; no operational readiness claim is
made from synthetic fixtures alone.

`AccountRoles(root, authorization_binding).call(...)` and `role_call(...)`
share exactly the same implementation and immutable claims. Per-role caps are
two authors, two input reviews, two source reviews and two result reviews;
Controller's two decisions stay in the existing Supervisor transaction. Whole
batch maximum is ten original model turns. Each full actual input is bounded
to 32 KiB, each support call to 120 seconds and the fresh window to 45 minutes.
Calls retain claim/input/schema, actual process command/PID, raw native wire,
normalized compatibility events, runtime acknowledgement, final JSON and
completion hashes. Protocol completion and actual OS process exit are recorded
separately because the persistent app-server is reaped after its completed turn.

Raw native replay validates the original thread/turn environment selection,
model, exact prompt/schema and thread ID, final response and normalized event
projection. Any tool/approval server request, non-text item, failed/interrupted
turn or error terminates the original without reissue. This does not claim the
model's entire schema is empty or that arbitrary candidate code is contained.
Candidate source is only returned as text; existing implementation/worker
controls are separate. Paid-provider calls/spend are zero; account token usage
is recorded when available and account dollar cost is unknown/unmetered.
Internal provider connection retries are not independently observed; the
adapter itself issues exactly one turn/start and never retries/resamples.

## Verification timeline

- By 22:23 UTC: native transport replaced the inadequate hook route; 19 focused
  synthetic fixtures checked bounded grants/claims, caps, drift, replay and
  text-only projection. A new raw-wire binding test exposed insertion-order
  prompt drift between in-memory and canonically persisted JSON. Fixed by
  deriving both Controller and support prompt text from canonical JSON.
- 22:27:21 UTC: 25 tests passed after adding real inert Python subprocess/stdio
  exercises of the production parser, handshake, turn dispatch, output capture,
  termination and replay. These children are explicitly not Codex and do not
  call accounts/models. ResourceWarnings exposed open pipes; fixed finally
  cleanup and reran with ResourceWarning treated as error.
- Final focused suite: 23 tests passed after removing the two unused hook-only
  tests. Coverage includes complete original/replay, per-role caps, expired
  fresh windows, unknown runtime policy, oversized input before reservation,
  failed/uncertain execution retained, artifact/input/source drift, server
  tool/approval failure, exact numeric schema, actual stdio synthetic completion,
  metadata-only acknowledgement, wrong model/nonempty environment rejection
  before turn/start, failed turn and completed preflight replay after deadline.

Exact focused command:

```sh
env PYTHONDONTWRITEBYTECODE=1 '/Users/estelle/Library/Application Support/MarketRSI/runtimes/ds-py312-20260912-01/bin/python' -B -W error::ResourceWarning -m unittest supervisor_harness.test_price_account_roles -v
```

No real Controller, author, reviewer or training attempt was consumed during
this agent's work. Synthetic verification is engineering evidence only. This
source exceeds the 200-line warning: the immutable role claims, native RPC,
preflight and raw replay form one inseparable transport component; Supervisor
must independently review that scope before activation. This is not autonomous
researcher or harness evolution, and it is not completion of the two-real-round
pilot. Parent remains responsible for integration, version binding, fresh
permission and actual end-to-end evidence.
