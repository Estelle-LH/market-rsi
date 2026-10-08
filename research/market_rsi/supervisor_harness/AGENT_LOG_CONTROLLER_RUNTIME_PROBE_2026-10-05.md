# Controller runtime catalog probe

## 2026-10-05 dispatch

Owner `controller_runtime_probe`; Root owns integration and commits. Read the
actual AGENTS, RESEARCH_SUPERVISOR, current RESEARCH_STATE and integration scope.
The broker is frozen at `01980b4117b5242a16728bc60392623a5efd13dd48e0390ebf29fd810404f7c4`.
Scope is one new synthetic runtime test and this log, no production edits.

Reused official configuration reference, fetched from
https://learn.chatgpt.com/docs/config-file/config-reference after query
`Codex custom provider Responses MCP config`. Read provider auth/transport,
retry, feature controls, image controls and project instruction fields.
Documentation establishes configuration support, not effective denial.

Read-only `codex exec --ignore-user-config --help` and `codex features list`
confirm version-specific flag/feature names. No account or model session was
launched by these diagnostics. Next: synthetic local-loopback provider, isolated
child configuration/credentials, disabled discovery, and OS network confinement.
The actual tool catalog, not this static feature listing, is the acceptance
evidence. Default unittest must never bind a socket or launch a CLI session.

## Bounded fixture startup failures

Default test: two executions, one passing static assertion and one skipped
opt-in fixture, 0.000 seconds; no socket or child session. First explicit
fixture was denied by outer sandbox at localhost bind (zero requests/CLI
launches). An authorized escalated localhost-only attempt then failed before
launch at Seatbelt profile parsing: numeric host unsupported, must use
`localhost:*`. Changed only the diagnostic profile to the supported localhost
spelling, retaining deny-network default. These were operational startup
failures, not a Controller/scientific result or an account retry.

The next launch parsed Seatbelt but pinned CLI strict configuration rejected
official-documentation key `tools.view_image` as unknown. Zero provider requests
or MCP reads occurred. Removed that duplicate key, retained the supported
feature-list key `features.view_image=false`, and informed Root that current
docs and pinned binary differ.

The corrected strict-config fixture reached exactly one localhost request with
no Authorization header. Actual catalog uses a namespace rather than flattened
MCP functions; it also includes `list_mcp_resources`,
`list_mcp_resource_templates`, `read_mcp_resource`, `request_user_input`.
No shell/exec/browser/image/apps/delegation/code-mode tools were present.
The first catalog assertion failed because the diagnostic parser only handled
flat functions, so the fixture returned its final response without calling the
reader. Corrected parser to report these real adapters explicitly and request
the tool using the native function-call namespace. Built-in synthetic system
skills appear in the request, not host skill content; skip-host-discovery does
not remove built-in skill descriptions. Root was informed immediately.

The native namespaced tool request produced `mcp_tool_call` started/completed
events, but default MCP approval blocked its read under approval_policy=never:
status failed, result null, error `MCP tool call requires approval, but approval
policy is never`; zero audited reads. Retrieved exact documented per-server
`default_tools_approval_mode` field from the already-fetched config reference.
Next bounded fixture config explicitly sets auto approval only for the sole
two-tool read-only server. This is not permission for other host tools.

Per-server auto approval still returned the same pre-read denial (two synthetic
requests, zero audited reads), consistent with absent readOnlyHint annotations.
Read the official MCP page's exact per-tool override example. Changed fixture
to default prompt and explicit `approval_mode="approve"` for only list_evidence
and read_evidence. This is a configuration compatibility repair, not a broker
source/permission or scientific policy modification.

## Native observation verified

Explicit per-tool `approval_mode="approve"` passed: two localhost fixture
requests and one audited approved read, 2 tests in 0.685 seconds. Actual
completed event contains result.content[{type:text,text:<broker JSON>}],
structured_content:null, status:completed, error:null. Started event has
result/error:null and status:in_progress. The second provider input contains
the exact synthetic approved evidence. No scientific/account/model request,
Train fit, credential transfer or external network occurred. Root received
the working configuration and native event shape immediately. This is mock
transport/catalog evidence, not proof of account-serving tool catalog parity.

At Root's request, final fixture additionally attempts built-in
read_mcp_resource on the sole reader with a file URI to an unapproved synthetic
sentinel, then checks no sentinel content reaches the next input and no second
broker evidence read is audited. No second driver or production edit.

## Final frozen diagnostic result

Final strengthened native catalog/observation/resource-denial test PASS, 2 test
executions in 0.683 seconds, three synthetic localhost requests (ceiling eight).
Source pins remained CLI `6b582e8813ce7e8ed4c52814ee5cf230dba647bf2292df747a4003f2657ef201`
and reader `01980b4117b5242a16728bc60392623a5efd13dd48e0390ebf29fd810404f7c4`.
One approved reader response matched its exact audited SHA; file-URI resource
read returned status failed, result:null, error `Mcp error: -32600: invalid RPC
request`. Unapproved sentinel content never entered any provider request; audit
retained exactly the one approved evidence read. No host personal files were
read by the fixture; the child Seatbelt rule denied /Users/estelle reads except
the pinned broker script and bundled runtime. It also denied non-loopback
network, independent of the CLI's model configuration.

Exact command, working directory and static configuration are reproducible in
the test's `probe()` and `overrides()` functions:

```
MARKET_RSI_RUN_CATALOG_PROBE=1 /Users/estelle/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -B -m unittest supervisor_harness.test_controller_account_runtime_catalog
```

Working directory `/Users/estelle/Developer/market-rsi/research/market_rsi`.
Invocation was escalated only because outer sandbox forbids even localhost
socket binding. Child remained independently Seatbelt-restricted. Runtime
CLI0.160.0, stdlib fixture, unknown-model fallback metadata; no real scientific
model/server snapshot was involved. Fixture token usage was simulated, not an
account resource measurement. Ephemeral synthetic input files were removed by
TemporaryDirectory cleanup, not stored as important research artifacts.

Observed effective tool catalog:

```
list_mcp_resource_templates
list_mcp_resources
mcp__controller_evidence__list_evidence
mcp__controller_evidence__read_evidence
read_mcp_resource
request_user_input
```

Native approved completed item shape (literal synthetic payload):

```json
{"id":"item_2","type":"mcp_tool_call","server":"controller_evidence","tool":"read_evidence","arguments":{"evidence_id":"fixture"},"result":{"content":[{"type":"text","text":"{\"eof\": true, \"evidence_id\": \"fixture\", \"next_offset\": 33, \"ok\": true, \"sha256\": \"6d5da7188255c8aa3e8826528756437a843000c763321d89a2632e973173d6ae\", \"text\": \"SYNTHETIC_APPROVED_EVIDENCE_ONLY\\n\"}"}],"structured_content":null},"error":null,"status":"completed"}
```

Final observation binding:

```json
{"thread_id":"01a10edd-6001-79b2-b033-764988aa7c9c","policy_sha256":"f747faef240ac773e4d5a326f5ba9dccd85d3c9412908f4f31d98ca8ed667d30","tool_request_sha256":"7d83baad06b52eb8e0b62226343490c1b9286af9cfb9d66e3a7d5dcdb2f0f952","payload_bytes":194,"payload_sha256":"e2c19071242c8617f316579220cfd5c4a0fed7066b0a349cf5e8498f63cab64b","broker_pid":29686,"fixture_request_sha256":["85f2e8ea9137201e619f8ea95609b7fc81d02bd6cea0e7ba35f075a9c43ba273","d67ecb66a1e7a81b8b06d830583b1e0fb3424daf0e5428bbde659e613366d48c","9f87e96c1aac9c4232a6ce505eef228bccb8df3d92b41fc2c73cc71ecbd173ee"]}
```

Root should use per-tool approve overrides (default auto failed), nested MCP
namespace response decoding, and the literal native completed-item result.
Replacing the complete mcp_servers table is critical; adding this server beside
inherited servers would not have the demonstrated catalog. Missing proof for
the actual account/runtime profile must keep live activation closed. A fake
provider demonstrates the pinned local dispatch, not account-specific parity,
global sandboxing, researcher autonomy or predictive/research-process gain.

Status DONE within allotted 20 minutes. Only own test/log changed, no commits
or production edits; Root owns verification, integration and checkpoint.

Probe accounting: nine explicit fixture test attempts, six preliminary
operational failures preserved above and three subsequent successful versions.
Three startup failures made zero requests; six actual synthetic CLI transport
sessions made 13 total localhost fixture requests (individual maximum three,
each below eight). This is diagnostic startup/protocol repair, not scientific
candidate attempts or account retries. Real account/provider calls, fits and
protected data reads: zero. Default unit tests additionally passed with the
actual fixture skipped. No fixture process or socket remains running.

## Bounded exact-production-profile follow-up

Root requested one additional probe against stable production session helper
SHA `bfa4844e47ef0f54c2bdce85ff3223e02b72febde8f2b1aadc978f607b5bde0f`.
Read helper and focused tests first, then changed only this test/log. The test
now calls the production `config_overrides(session,directory)` directly; the
duplicated prototype config compiler is removed. Original prototype observations
above remain historical evidence, not silently replaced by this new observation.

The compiled production PROFILE, full single-server MCP override, reader
`-I -S -B`, explicit cwd/empty env_vars, per-tool approval, and 10-second startup /
5-second tool timeouts were actually exercised by pinned CLI. Only the synthetic
loopback provider, ephemeral credential storage and isolated child configuration
were appended. Test session attestation is declared synthetic fixture input, not
an independently issued live authority receipt; account=True still hard-fails.

One opt-in invocation PASS, 2 tests in 0.691 seconds, three synthetic localhost
requests, one audited read and denied unapproved resource URI, unchanged catalog
and native event shape. Default invocation additionally PASS with fixture skip;
no socket. Exact production-profile observation bindings:

```json
{"session_sha256":"bfa4844e47ef0f54c2bdce85ff3223e02b72febde8f2b1aadc978f607b5bde0f","profile_sha256":"39170f3dc756aa24401b5ca71a80067f54769dda374a0bb8bc667eca4d75469b","thread_id":"01a10ee2-cd85-71a2-b474-8972e1cc94dc","policy_sha256":"47f87dc6701326a35fb71655328f7a62682494638911505eccd844d084a95df8","tool_request_sha256":"7d83baad06b52eb8e0b62226343490c1b9286af9cfb9d66e3a7d5dcdb2f0f952","payload_sha256":"e2c19071242c8617f316579220cfd5c4a0fed7066b0a349cf5e8498f63cab64b","broker_pid":30361,"requests":3,"fixture_request_sha256":["b01c9fd6701c893b54fdb171cf8bb81b378daa2ac5aaca3b0e4e26048eb8db2c","ce1ef4edc0798c40c26d77c05dd04c08fd84b19b5218f74a8a30fa97a4ea0a6a","c9ea5f3e2030dd949f2536d09f3176f234222fcf51f40f50e3a76b9a6c7112ac"]}
```

All diagnostic work now totals 16 localhost requests across seven actual mock
transport sessions, plus the three earlier zero-request startup failures.
Individual maximum three; this follow-up introduced zero failures/retries.
Production source untouched; real account/provider calls, Train fits, protected
reads and Git changes remain zero. Profile SHA and separate helper source SHA
must both bind the observation: profile_sha256 alone does not hash every literal
server transport field. Account parity remains unproved and activation closed.

Provenance limitation: the final opt-in probe preceded removal of the unused
prototype config compiler; the exercised production probe function/config did
not change. Final default tests were rerun after that inert cleanup. The exact
test-file SHA at opt-in time was not separately captured; do not relabel final
test SHA as that execution identity. Root may independently rerun the final
test if required. Helper source, profile, CLI/reader and input/output bindings
above were checked and retained.
