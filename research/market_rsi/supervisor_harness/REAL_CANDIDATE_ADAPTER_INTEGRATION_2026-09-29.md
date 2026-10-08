# Synthetic local candidate adapter integration — 2026-09-29

## Verdict

`REPAIR_V4_INTEGRATION_PASS_PENDING_REREVIEW`

The first independent review of aggregate `4aa3ff64...a5625ba` returned
`REPLAN` with `2 P0 / 3 P1`; its immutable review-log SHA-256 is
`3a3d0ef6091df71b1fdf98e27eef6b600bf4ab10de342ef84784e482f880c8b2`.
The v2 snapshot repaired all five causal findings without widening scope:

- one pinned absolute Docker CLI hash, one frozen client environment, and one
  revalidated context/daemon identity now bind run, inspect and stop;
- post-`Popen` initialization failure and abort produce explicit reaping
  evidence, and uncertainty can never become success;
- staged source files are fsynced, changed to exact `0444`, restatted and
  reverified for container UID 65534 readability;
- a bounded pre-release quiet check plus output-first selector ordering rejects
  delayed unsolicited stdout before another row is released; and
- a post-completion adapter-receipt failure reopens and verifies the immutable
  protocol completion, records `prediction_complete=true`, and remains
  non-replayable.

The second independent review of v2 aggregate `5fcecc07...68ea1` returned
`REPLAN` with `0 P0 / 2 P1`; the cumulative review-log SHA-256 at that boundary
is `1145655b3a064563e84905411abe7dd46466c8c97c34b09c9ecbace823fad7d2`.
The v3 snapshot adds the two narrow evidence repairs:

- an immutable success marker and canonical terminal verifier require exactly
  one valid terminal result; any failure artifact, coexistence, missing marker,
  noncanonical content or hash mismatch rejects success; and
- temporary paths or injected transport/control/Docker bindings are explicitly
  `test_mode=true`, are rejected on persistent production paths, and are
  rejected by the verifier unless its caller explicitly opts into test mode.

The third independent review of v3 aggregate `f880ab38...16e720` returned
`REPLAN` with `0 P0 / 1 P1`; the cumulative review-log SHA-256 at that boundary
is `07f4670d70a47f21109ee50fc78136039bd6b72c003a5003396f3e835a967c66`.
The v4 terminal verifier now also requires the exact protocol root, synthetic
run key, candidate hash and public rows. It recomputes the deterministic run
identity, reads and validates the canonical adapter claim and its receipt
fingerprint, rehashes both staged sources and their `0444` modes, checks the
current guest source, resumes the immutable protocol, validates its complete
journal/checkpoint/receipt, and requires exact equality to the adapter receipt.
Regressions mutate the adapter claim, protocol completion, journal suffix and
staged candidate after a success-shaped test run; all four are rejected.

The exact snapshot below implements the smallest local-Docker bridge from the
label-free prediction protocol to an untrusted candidate process.  It is
deliberately synthetic-only.  It does not read, admit or score real data and it
does not establish that Docker isolation has passed a live canary.

The trusted host owns the complete row sequence, durable journal, response
validation, process reaping and exact cleanup check.  The candidate container:

- receives one exact public row at a time over stdin;
- cannot receive the next row until the prior prediction is durably committed;
- returns one strict JSON probability over stdout;
- gets exactly two read-only source mounts and no host data/artifact mount;
- runs with no network, a read-only root, all capabilities dropped,
  no-new-privileges, bounded pids/memory/CPU/tmpfs and UID/GID 65534;
- receives an exact allowlisted environment through `env -i`; and
- must exit cleanly and be proven absent before protocol completion is written.

Every success and failure artifact keeps `synthetic_only=true`, `scored=false`,
`real_data_admitted=false`, `real_isolation_admitted=false` and
`promotion_authorized=false`.

## Exact source and test identity

The aggregate is SHA-256 of the standard `shasum -a 256` output for these files
in the listed order:

`87a32217bca2919e1a4724785ef578a6b7cda23b10bf99c56319017235e9472b`

| File | SHA-256 |
|---|---|
| `minimal_prediction_loop/container_adapter.py` | `34d4df25da4cea9807a39874cf04c0ed52af1c83f23d3851476a947f998590c9` |
| `minimal_prediction_loop/container_candidate_guest.py` | `d79d927d0ca3affda43639455c18b164c59014186092a2183fe765fcf4ac7b36` |
| `minimal_prediction_loop/prediction_protocol.py` | `eb6bdc1367f62c2910225218389d7381cebb2477e92a523c83f0693ae21a5dd3` |
| `supervisor_harness/local_b_container.py` | `76b0420fdd9c0fdc6b90cbfdc35979e5c196f0917102936edb9ea3f03e8525be` |
| `tests/test_minimal_prediction_container_adapter.py` | `98cda5b55bad2b29e4fd6f139125ced9abc740a4500fe2e85770c185610dfc2d` |
| `tests/test_minimal_prediction_protocol.py` | `9931c44f8d689386b3cb134965bcf704743226c02f587ae6aa7aa5a79e38197a` |

## Verification

Focused adapter suite after the final nonblocking-FIFO repair:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/market_rsi \
  <pinned-local-python> -B -m unittest -v \
  research.market_rsi.tests.test_minimal_prediction_container_adapter
```

Result: `26/26 PASS` using synthetic fixtures only.

Focused plus adjacent prediction protocol, minimal loop, local-container,
containment and prediction-stream suites:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/market_rsi \
  <pinned-local-python> -B -m unittest -v \
  research.market_rsi.tests.test_minimal_prediction_container_adapter \
  research.market_rsi.tests.test_minimal_prediction_protocol \
  research.market_rsi.tests.test_minimal_prediction_loop_integration \
  research.market_rsi.supervisor_harness.test_local_b_container \
  research.market_rsi.supervisor_harness.test_local_b_containment_canary \
  research.market_rsi.tests.test_prediction_stream
```

Result: `85/85 PASS`.

Repository-level discovery under the existing persistent local runtime
`/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python`:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/market_rsi \
  <pinned-local-python> -B -m unittest discover \
  -s research/market_rsi -p 'test*.py' -q
```

Result: `516/516 PASS`, `2` designed skips.

`git diff --check` passed.  A source-only static capability scan found no data
reader, scorer, trainer, provider, credential or network-client import in the
two new runtime modules.  The guest imports `socket` only to assert that its
network namespace contains loopback and nothing else.  The adapter necessarily
uses the Docker subprocess transport and imports only the frozen image identity
plus the label-free prediction protocol from project code.

The focused negative cases cover real/non-synthetic identities, forbidden
fields, response identity/authority injection, endpoint and boolean
probabilities, candidate hash mismatch, symlink and FIFO paths, premature and
delayed output, multiple output, timeout, fsync failure, staged-source
mutation/mode, unpinned or changed Docker CLI, changed daemon identity,
post-`Popen` failure, unreaped abort uncertainty, post-completion receipt
failure, success/failure coexistence, missing terminal marker, unmarked test
hooks, nonzero exit, replay, foreign container identity and ambiguous cleanup.
During initial integration, the FIFO case exposed a potential
blocking open; the source reader uses `O_NONBLOCK` and retains that regression.
After the independent REPLAN, all five reviewer reproductions were converted
to v2 regressions; the second REPLAN's two evidence findings became the v3
terminal-precedence and test-mode regressions; the third REPLAN's claim and
protocol read-back gap became the v4 claim/completion/journal/staging mutation
regressions. Both focused and repository suites were rerun on the exact hashes
in this report.

## Limitations and closed gates

- No live Docker candidate canary was run.  Static command construction and
  fake-control lifecycle tests do not prove the actual daemon boundary.
- No real input, real outcome, Route-Dev, Audit-Dev or Final row was opened.
- Synthetic identity prefixes are a test-only admission rule, not proof of
  real-source provenance or rights.
- No scoring, empirical evaluation, training, provider call, payment, fetch,
  release, commit, tag, push, publication or promotion occurred.
- The already-opened 2024 diagnostic cohort remains blocked on rights,
  provenance, materialization and formal admission despite adequate aggregate
  coverage.  The 2023 cohort remains coverage-inadequate; opened 2025 Train is
  not an untouched evaluation cohort.

The next gate is a fresh non-author adversarial rereview of this exact v4 snapshot.
Only a review result with `0 P0 / 0 P1` may make a separately authorized,
fresh-ID, synthetic zero-provider Docker canary the next request.  This report
itself grants no canary or real-data authority.
