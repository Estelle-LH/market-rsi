# Controller evidence tools implementation

Registered by Root for controller-enablement-p0-evidence-tools-20261005-01.
Allowed writes are the new standalone evidence-tools module, its test file,
and this dedicated log. No old source, live data, model calls or fits.
Record timestamped actions, exact files, tests, failures and remaining scope.

## 2026-10-06 01:16:42 UTC — first implementation checkpoint, unreviewed

Read AGENTS, RESEARCH_SUPERVISOR, current RESEARCH_STATE, the exact dispatch
contract and the existing broker's newline JSON-RPC transport. Reused that
unchanged operation pattern; no live literature, data or network retrieval.
Observed gap: active consumer currently rejects all tool events. This task
does not change that consumer; it prepares one independently testable read-only
evidence boundary for a later integration checkpoint.

New production module: controller_research_evidence_tools.py. New synthetic
test module: test_controller_research_evidence_tools.py. Protected modules and
experiments remain untouched by this agent. Manifest has reviewed source,
evidence or memory IDs, exact paths/hashes and a strict payload approval flag;
only the trusted Supervisor may classify/admit contents. Model arguments never
select a path. Directory/leaf descriptors use O_NOFOLLOW. Reads verify current
policy and content hashes. Tool-call and serialized-payload counters include
denials and cannot be reset by invalid input. One-process calls are serialized;
a used audit path cannot restart. Receipts hash output without duplicating
evidence text and require fsync before a response. Exhaustion/audit failure
poisons the session. JSON-RPC framing bytes are outside the declared tool-payload
budget; no claim of arbitrary-code/whole-host OS isolation is made.

Sent Root an explicit inseparability-review request: production source exceeds
the approximate 200-line warning (~250 lines). Descriptor security, policy,
budgets/audit and MCP framing jointly implement one component; splitting to a
second production module would broaden the allowed interface. This is a review
request, not acceptance. Tests are written but not yet run at this entry.

## 2026-10-06 01:19:52 UTC — focused verification PASS, not activation

Exact command, cwd /Users/estelle/Developer/market-rsi/research/market_rsi:

```
/Users/estelle/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest supervisor_harness.test_controller_research_evidence_tools -v
```

Initial 30 tests passed in 0.045s. Independent review found a malformed RPC
ID edge case: NaN could dispatch before response encoding failed. Repaired
before freeze with duplicate-key/nonfinite JSON rejection, legal ID validation,
null error IDs and terminal oversized framing. Added exact-output exhaustion
pre-read check. Later review flagged overflow syntax `1e9999`; strict float
parsing now rejects it too. This is an implementation defect and repair, not
a scientific finding. No failed experimental result or old score was changed.

Final 33 tests passed in 0.049s (previous 33-test run 0.050s). Actual coverage:
synthetic allowed/list/read and Unicode reconstruction; manifest/source drift;
unlisted/model-supplied paths; parent and leaf symlinks including post-admission
replacement; traversal; FIFO/nonregular/oversized/invalid-UTF8 denial; strict
policy approval/limits; invalid calls counted; exact aggregate exhaustion before
read; concurrent thread calls; used audit path restart denial; fsync/zero-write
and audit-path replacement failure; no source text duplication; malformed and
oversized RPC; actual local stdio subprocess roundtrip. Audit receipts include
prepared-payload hash, request hash, policy hash, approved evidence ID, pid and
sequence. Delivery is explicitly unconfirmed; no receipt claims consumer receipt.

`git diff --check` returned success/no output. Final production size is 284
lines; Root must explicitly review inseparability. The whole component is one
file, but below-200-line smallness is not claimed. Source identities:

- controller_research_evidence_tools.py SHA256:
  01980b4117b5242a16728bc60392623a5efd13dd48e0390ebf29fd810404f7c4
- test_controller_research_evidence_tools.py SHA256:
  84cb98d6b43fe3c6e13b16fd6dd43ebb6d974a4790ed3b33611e7beb9da056d8

Shortcomings/claim boundary: standalone code plus synthetic boundary evidence
only. No source snapshots, actual Train/Dev/Final, account sessions, provider
calls, statistical fits, external network or legacy imports used. Root owns
inherited suites, final integrated review and Git. No live consumer was modified
or enabled. Counters bound tool-call payload disclosure under one process;
MCP control/framing traffic is not claimed capped by that payload budget.
Same audit path prevents silent restart/reset rather than supplying recovery;
new sessions require a new trusted policy and fresh audit path. Content admission
relies on Supervisor review; hashes/approval flags alone do not classify secrets
or protected data. This is not arbitrary-code sandboxing, OS isolation,
automatic experiment continuation, research-capacity or prediction improvement.
