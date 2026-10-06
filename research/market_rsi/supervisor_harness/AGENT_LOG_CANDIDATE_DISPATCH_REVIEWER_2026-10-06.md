# Candidate dispatcher independent review

Registered by Root before dispatch. Read-only preflight and final stable source
review; own only this log and CANDIDATE_DISPATCH_INDEPENDENT_REVIEW_2026-10-06.json.
No production edits, real data/account/provider calls/fits or commits. Final review
follows Root verification and ready-step gate. Existing evidence-session ordering/
empty-read adversarial questions may be checked read-only in synthetic memory;
do not edit prior frozen receipts/logs or interrupt dispatcher implementation.

## 2026-10-06 04:19–04:20 UTC — independent read-only preflight

Read `research/market_rsi/AGENTS.md`, `RESEARCH_SUPERVISOR.md`,
`RESEARCH_STATE.md`, the complete research-progress skill and
`CANDIDATE_DISPATCH_SCOPE_2026-10-06.json`. The skill keeps an engineering
capability claim separate from prediction or researcher improvement. Current
scientific/account budgets are closed; this review uses synthetic fixtures only.
Dispatcher final review is pending Root's stable verification and ready gate.

Separately checked the two adversarial expectations relayed by the testing
chat. These are findings against the already-frozen evidence-session component,
not changes made by this dispatcher checkpoint. No source or prior receipt was
edited. Source identities at the test:

- `controller_evidence_session.py`: `bfa4844e47ef0f54c2bdce85ff3223e02b72febde8f2b1aadc978f607b5bde0f`.
- `account_controller_feedback_consumer.py`: `81c38bf354426543252e5df19e1f78ad9de5b1c7b7e46ae3a72b6e4d4c52868b`.
- `test_controller_evidence_session.py`: `f859cccf89e952df115be8ec0987ab497683108ba947a79fdec8a482b1f0d8a8`.

Exact runtime/entry: repository cwd `/Users/estelle/Developer/market-rsi`;
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/market_rsi
/Users/estelle/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -`.
The in-memory script instantiated existing `SessionTests`, called `setUp()`,
wrapped `fixture.transport` and used `fixture.consume(transport)`, then
`doCleanups()`. Actual broker calls produced the audited payload; no mock was
substituted for the broker. Synthetic process/model response only, as in the
existing test. Fixture source is 75 characters with SHA
`2e426430d8fc95830841799b8417333ec93226ccfbc60e904b9ee91b3f4828c6`.

Three minimal counterexamples were **accepted by native recovery**, each with
one transport invocation and a newly created `ack.json`:

| Case | Minimal fixture delta before resealing | Observed result |
| --- | --- | --- |
| Empty EOF alone | `read_evidence({'evidence_id':'finding','offset':len(fixture.source.read_text())})`; replace the otherwise-empty `evidence_used[0].finding` with a nonempty adversarial synthetic assertion in both response and final message | Payload `ok=true`, `text=''`, `eof=true`, `next_offset=75`; cited source SHA accepted |
| Read after final message | Reorder original `[tool, agent_message, turn.completed]` to `[agent_message, tool, turn.completed]` | Source SHA accepted despite read completing after decision |
| Read after terminal | Reorder to `[agent_message, turn.completed, tool]` | Source SHA accepted despite post-terminal read |

For all three, the wrapper rewrote only temporary synthetic `events.jsonl`
(and the EOF fixture's temporary response), then called `fixture.seal(directory)`
to bind the changed bytes with the existing synthetic completion format. The
first EOF probe incorrectly used exclusive `c.save` on an existing fixture
response and raised `EEXIST`; a corrected temporary `write_bytes(broker.encode
(response))` rerun demonstrated the acceptance above. This fixture repair was
not an application change or scientific experiment retry.

Cause: `verify_events` collects every completed MCP event without checking its
position relative to the final decision or terminal completion, then credits
every successful approved `read_evidence` hash regardless of empty text.
`_recover` independently accepts a final-message/completion pair without
requiring terminal finality. Hash/audit matching works, but does not establish
that informative evidence preceded the decision. Existing positive and
mutation tests do not cover these ordering/empty cases.

Interpretation: original account evidence activation is already hard-closed,
so these probes did not enable or execute a live account decision. They are
unresolved evidence-provenance gaps for future activation, not evidence of real
leakage or scientific harm. Reported exact counterexamples to Root; the current
dispatcher work may continue under its unchanged no-live-activation boundary.
No speculative patch and no modification of historical integration PASS
receipts. No protected data, account/provider calls, fits or external network;
temporary synthetic artifacts removed by fixture cleanup.

## 2026-10-06 04:20 UTC — inherited native baseline

Ran `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/market_rsi
/Users/estelle/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
-m unittest supervisor_harness.test_controller_evidence_session
supervisor_harness.test_opened_train_discovery_worker` from the repository root.
46 test executions passed in 1.362 seconds; imported test cases may overlap,
so this is not a unique-test count. Read the unchanged native worker and the
recorder's pool-selection/implementation/claim/terminal seams. Native worker
has no arbitrary-code containment or OS-hard RSS isolation and retains its own
two-slot/aggregate-fit reservation guards; the new dispatcher must not upgrade
those claims or retry a claimed attempt. Final new-source inspection pending.

## 2026-10-06 04:22–04:23 UTC — provisional dispatcher checks

Inspected the author's first helper/test draft, not a stable final snapshot.
Ran the same Python/environment with
`-m unittest supervisor_harness.test_reviewed_candidate_dispatch`:
15 executions in 0.410s, 14 passed and one fixture setup error. The symlink
test attempted to create `dispatch/a.lock` after prior denied calls had already
created it; the fixture raised `EEXIST`, not an application boundary failure.
Reported author for a fresh isolated symlink fixture. Do not count this as a
passing final suite.

Concrete draft counterexample: initialized `DispatchTests`, patched existing
worker `Popen` to a synthetic child `pid=1234`, exit/poll7, invoked the native
handoff once, removed only temporary `worker/a.process.json`, then invoked
recovery again. Recovery **accepted** the unchanged failed receipt with
`exit_code=7,error=null`, spawn count remained1. The receipt is durable and no
retry occurred, but recovery omitted a native process record that should exist
for this completed nonzero child. Author notified to retain pre-spawn failures
(`exit_code=null` with an actual error) while rejecting missing post-spawn
process provenance. No production changes made by reviewer.

Root separately identified that fresh dispatches could repeatedly trust an
unchanged outer authority snapshot. Root requested a conservative same-helper
batch-local reservation/accounting guard and exact distinct-ID cap regression.
Reviewer will inspect that bounded update on the final snapshot; cross-batch
ledger synchronization remains Supervisor-owned. This is pending validation,
not already implemented or evidence of any real budget overrun.

## 2026-10-06 04:25 UTC — draft output commitment limitation

Another concrete synthetic check used `DispatchTests` and the actual native
worker with `Popen=fixture.completed_child`. After a successful first `invoke`,
changed only temporary `runs/a/predictions.csv` and updated its
`predictions_sha256` in temporary `manifest.json`, then called `invoke` again.
Recovery accepted the same native receipt with spawn count1 and
`metrics_independently_reviewed=false`. The existing native receipt contains
no original manifest/output hash, so consistency against a jointly rewritten
manifest is not proof of original output bytes. Reported to Root and author;
this distinction must be explicit in final claims or receive a bounded original
artifact commitment. The review does not authorize a worker/scorer rewrite.
Preserving the same execution receipt and retaining metrics-review=false is
not itself performance-review fraud, and no real prediction output was touched.

## 2026-10-06 04:27–04:29 UTC — independent final exact snapshot review

Root supplied stable verification SHA
`19e0c1589a8b3638316bd7dfb97dd45fea9dea78d45bb7dc9072bc69a673fd13`.
Read complete206-line helper and402-line tests plus implementer repair log.
Independently reran review-ready gate: `ready=true`. Helper/test remained
`172bb56467bb0a241c34f20949da7453133ed9861a50fe34fd1af531703eb02c`
and `468b80365e532e3c03d9502f8700d8cada64c3bc4d4079106874c8a00ea32c5e`;
implementer log `f5d78632e7b542a3abb7c23d5d05b15865a6fc59f3195e814fda3d0543cb1b6e`.

Independently ran complete relevant synthetic suite: exact bundled Python,
repository-root cwd, `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/market_rsi`,
and `-m unittest` with modules `test_reviewed_candidate_dispatch`,
`test_controller_research_evidence_tools`, `test_controller_evidence_session`,
`test_controller_failure_feedback`, `test_controller_account_runtime_catalog`,
`test_account_controller_feedback_consumer`, `test_opened_train_discovery_worker`,
`test_continuous_discovery_batch`, `test_continuous_discovery_branch_retention`,
`test_continuous_discovery_small_steps`, `test_learning_checkpoint_assessment`,
`test_bottleneck_gate` (all under `supervisor_harness`).
**229executions passed4.516s, one deliberate opt-in CLI/socket probe skipped**.
Executions may overlap; not229unique tests or the entire repository. Protected
experiment subtree, consumer, worker, recorder, learning policy, decision state
and existing evidence/failure helpers have an empty diff from484ab30. Exact
protected hashes match Root. Rechecked helper/test hashes after tests.

Missing-process completed-nonzero regression now fails closed; genuine
pre-spawn failure still returns factual error without fabricated process or
predictions. Short admission lock counts immutable dispatch records AND native
claimed IDs missing from stale authority, including terminal/failed consumed
reservations. Four fits conservatively reserved, never falsely measured.
Active-ID union bounded2; lock released before native execution. Actual tests
demonstrate concurrent same-ID spawn1, distinct-ID overlap, and a first
admission consuming the final allowance before a second stale-snapshot spawn.
Original claim/schema/decision/request/review/parent/comparator, runtime paths,
logs and native receipt are bound. No model recipe is executed and metrics
review is not granted by handoff.

**Explicit inseparability exception accepted:**206lines/one new production
module form one native handoff boundary. Admission, conservative reservation,
at-most-once fence and terminal reconciliation share the same per-attempt
identity. Removing a guard loses the declared benefit; splitting only6lines
adds an interface without reducing blast radius. Warning threshold review,
not size as safety proof. No second production module, evaluator, provider,
permission, dependency, base-model or researcher-policy change.

**Verdict PASS, execution-only synthetic native boundary.** H benefit observed
on native synthetic fixtures, not real account/Train operation or C/R benefit.
Root owns local checkpoint/staged-scope checks. Material limits retained:

- Native receipt lacks manifest commitment; the coordinated output/manifest
  rewrite above remains. Separate independent output/metric review mandatory
  before scientific feedback; no incumbent/KEEP change here.
- Trusted admission/selection are caller inputs; recipe-to-module and question/
  hypothesis semantics unverified. Existing fixture decision question
  `distinct-synthetic-question` differs from branch `question-a`; exact parent/
  comparator validation is not full research-question provenance or a compiler.
- Outer cross-batch ledger stays Supervisor-owned; local fence cannot grant
  a fresh window, calls, restored budget or rights.
- Frozen evidence EOF/order counterexamples are outside this component.
  Account evidence activation stays hard closed; separately contracted repair
  follows, without retroactively changing old reviews.
- Clocks/model transport/children scripted; no real data/account/provider/
  network calls, fits or researcher improvement. Reviewer AI cost unknown.
