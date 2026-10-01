# Independent synthetic adapter canary boundary review — 2026-09-29

- Reviewer: `synthetic_adapter_canary_boundary_reviewer_20260929`
- Plan ID: `market-rsi-real-candidate-isolation-canary-20260929-01`
- Scope: read-only launch-boundary design review. No Docker command, canary
  artifact, real/protected data, provider, scorer, training, fetch, release,
  commit or push was used. This review does not consume the authorized ID.

## 2026-09-29 12:11 EDT — boundary decision

### Verdict

`PASS` with **0 P0 / 0 P1 design findings**.

The one-shot live canary can remain entirely synthetic and zero-provider. It
needs no real input, outcome, Train/Dev/Final row, scorer, credential, network
fetch or writable host mount. The exact v4 adapter already exposes only two
read-only source files, stdin/stdout and bounded in-container tmpfs. The
smallest useful live exercise is one fixed self-checking candidate over two
fixed synthetic public rows, followed by independent terminal verification.

This is a **design-boundary PASS**, not launch readiness and not live
isolation evidence. The fixed candidate, one-shot runner, pre-launch manifest
and their offline tests do not exist in the reviewed snapshot yet; their
implementation and a fresh `0 P0 / 0 P1` pre-launch review are mandatory
dependencies in the supervisor plan. No live dispatch may occur merely from
this log.

Even a successful later run can establish only that this exact pinned
synthetic candidate traversed this exact local Docker boundary once. It must
keep `scored=false`, `real_data_admitted=false`,
`real_isolation_admitted=false` and `promotion_authorized=false`. It cannot
admit real data, authorize evaluation, establish forecast gain or promote a
model.

### Problem and unchanged experiment boundary

The problem is operational containment availability: the reviewed v4 adapter
has only fake-transport/static evidence for Docker Desktop bind semantics,
UID/GID 65534, actual stdin/stdout transport, cgroup/mount behavior and final
container absence. This canary changes no stage in the causal evaluation
ladder. It has no target, labels, metric or PnL and therefore is not an
empirical experiment.

The existing literature/research record applies unchanged; no live search was
needed or permitted. The evaluation skill's separation between prediction
transport and evaluation is preserved: this canary stops before outcomes and
scoring.

## Smallest live synthetic candidate

Use one reviewed source file with exactly `predict(public_row) -> probability`
and no dynamic code, file or environment input. Bind its bytes in the
pre-launch manifest and adapter claim. Use exactly two canonical rows so the
run exercises both the post-commit/pre-release boundary and the final
commit/exit/cleanup boundary:

- every `event_id` and `market_id` begins with `synthetic-`;
- timestamps and probabilities are fixed directly in the runner source;
- row schemas contain exactly the five `PUBLIC_AS_OF_FIELDS` before protocol
  expansion; and
- expected returned probabilities are two different interior constants, for
  example `0.25` and `0.75`, selected by the exact sequence. The terminal
  reviewer reconstructs the two canonical stdout response lines and requires
  their exact byte count and SHA-256 to equal the process receipt.

The candidate must keep only an in-memory expected sequence counter and, on
each call, fail before returning a probability unless all of these assertions
hold:

1. The received object has exactly `PUBLIC_RELEASE_FIELDS`, the correct
   synthetic identities, the expected sequence and the fixed row contents.
2. No next stdin line is already readable while `predict` is running. This is
   the live positive probe that the host did not pre-send row 2; the durable
   journal remains the authoritative A02 evidence.
3. `/opt/market-rsi` exposes only the staged guest and candidate files; both
   are readable, hash-matched by the guest, and not writable. The root and the
   two bind mounts are observed read-only through `/proc/self/mountinfo`.
4. The exact synthetic host decoy paths are absent in the container. The host
   creates only small synthetic marker files beside, not inside, the adapter
   artifact root and protocol root, records their hashes, and verifies them
   unchanged after the run. They are never mounted.
5. UID/GID are `65534:65534`, supplementary groups are empty,
   `NoNewPrivs` is set, and only loopback is present. The guest already makes
   these checks before importing the candidate; the fixed candidate may
   repeat them as defense-in-depth.
6. A bounded connect to an RFC 5737 TEST-NET address fails locally, and a Unix
   socket connect to `/var/run/docker.sock` fails. Do not resolve a real
   hostname and do not fetch anything. Because the namespace has only
   loopback, the TEST-NET attempt must not leave the container.
7. The cgroup view proves `pids.max=32`, memory max `512 MiB`, and one CPU
   quota; `/tmp` is a `64 MiB` `rw,noexec,nosuid,nodev` tmpfs. A small file can
   be created and deleted in `/tmp`; no durable candidate output is created.
8. Common credential/host paths and the exact synthetic decoys are absent.
   This is an allowlisted probe list, not a recursive filesystem scan.

The candidate emits no diagnostics or authority fields. Any failed assertion
raises and therefore makes this one attempt terminally fail; the runner must
not weaken a probe or retry the same ID. Negative protocol/parser/lifecycle
attacks remain offline unit tests. A one-shot positive canary must not start
additional deliberately failing containers under the same authorization.

## Persistent path and launch contract

All durable state must be under the non-cloud, non-temporary tree:

```text
/Users/estelle/Library/Application Support/MarketRSI/
  synthetic-adapter-canaries/
    market-rsi-real-candidate-isolation-canary-20260929-01/
```

The one-shot state owner may create that directory, but the adapter artifact
child passed to `run_local_candidate_prediction` must be fresh and absent.
Use distinct children for the adapter artifacts and protocol state. Reject
symlinks in every existing component, unresolved `..`, temporary paths,
iCloud/Dropbox/Google Drive paths, non-local volumes, reused roots and any
pre-existing deterministic protocol run. Ephemeral `/tmp` exists only inside
the container; no important evidence is placed there.

Before process dispatch, an exclusively created and fsynced pre-launch
manifest must bind at least:

- authorization text, exact canary ID, `max_attempts=1`, `automatic_retry=false`
  and explicit zero-provider/zero-cost authority;
- the exact v4 six-file aggregate and individual hashes;
- exact fixed candidate bytes/hash, guest hash, adapter hash, protocol hash,
  pinned image digest, resolved Docker CLI path/hash, Docker environment hash,
  context and daemon identity hash;
- exact run key, two public rows, public-row hash, candidate hash,
  deterministic protocol run ID, exact container name, expected response
  lines/probabilities and exact command plus command hash;
- canonical absolute persistent base, artifact and protocol paths, and
  synthetic-decoy paths/hashes; and
- all authority fields false plus `live_canary_eligible=true` only for this
  exact non-test default transport path. It is not real-input eligibility.

Preflight may perform read-only Docker identity, image-presence and exact-name
absence checks. It must use `--pull never`; absence or identity drift fails
before dispatch. The separate one-shot review defines the exact consumption
boundary, but it must occur no later than the first real candidate-process
dispatch and must make same-ID replay impossible after any ambiguous launch.

No `transport_factory`, alternate `control_run`, injected
`DockerClientBinding`, `allow_temporary=true` or test-mode receipt is allowed
in the live runner.

## Required terminal verification

The independent terminal reviewer receives only the frozen manifest and the
durable canary roots. It must not trust success based only on an exit status or
the presence of `adapter-success.json`.

1. Verify one and only one terminal outcome. Any failure/ambiguity artifact
   dominates success; missing or coexisting terminals are failure.
2. Call `verify_adapter_terminal` with the exact manifest protocol root,
   synthetic run key, candidate hash and public rows, with
   `allow_test_mode=false`. This replays claim/staged-source/protocol/
   receipt/marker integrity.
3. Supplement that v4 API by independently requiring
   `claim.image ==` the pinned `IMAGE`, validating the exact Docker-client
   receipt schema, reconstructing the command from the frozen CLI,
   deterministic name/run ID, staged paths and source hashes, and matching the
   command hash. `verify_adapter_terminal` alone does not reconstruct those
   A18 commitments.
4. Recompute the expected two canonical stdout response lines from the
   verified journal. Require exact `responses=2`, byte count and stdout hash,
   `stderr_bytes=0`, `process_reaped=true` and `exit_code=0`.
5. Re-hash the immutable fixed candidate, current guest and staged copies;
   require exact `0444`, regular non-symlink files and only the two read-only
   source mounts in the reconstructed command.
6. Resume the exact protocol read-only and require the alternating journal
   order `release 0, commit 0, release 1, commit 1`, exact checkpoint and
   completion equality, label-free/scored-false fields and no replayable
   pending row.
7. Rebind the same CLI/environment/context/daemon identity and perform a fresh
   exact-name inspect. The exact labelled candidate container must be absent;
   unknown, foreign, permission-denied or daemon drift is failure. Preserve
   the read-only post-run absence observation in the independent review log.
8. Re-hash every synthetic host decoy and require it unchanged. Inventory the
   canary directory against a closed artifact allowlist; reject candidate
   durable output, Docker log files or unexpected files.
9. Require zero provider calls, zero cost, no scorer/evaluation receipt, no
   data-admission receipt and all external authority booleans false.
10. Hash the final immutable evidence set and append a terminal `PASS` or
    `REPLAN` to this review log. Failure consumes the ID and grants no retry.

## A01–A22 evidence matrix

| ID | Launch evidence | Terminal evidence / pass rule |
|---|---|---|
| A01 | Two exact synthetic rows; closed schemas; runner has no outcome, scorer, data or protected-path parameter. | Journal releases contain only `PUBLIC_RELEASE_FIELDS`; no forbidden alias or extra field. |
| A02 | Two rows and fixed candidate stdin-readiness assertion; reviewed v4 commit/quiet ordering. | Alternating release/commit journal; row 1 release follows durable row 0 commit. |
| A03 | Exactly two source binds; unmounted synthetic host decoys; no home/data/key/protocol/artifact bind. | Candidate self-check passed, decoy hashes unchanged, mount allowlist exact. This remains synthetic-path evidence only. |
| A04 | Exact no-network/read-only/cap-drop/NNP/IPC/user flags; TEST-NET and Docker-socket denial probes. | Successful fixed probabilities imply probes passed; guest runtime checks passed; no network fetch or socket mount. |
| A05 | Fixed run/row/sequence commitments and two expected probabilities. | Canonical protocol resume verifies every identity and prediction ID; exact stdout reconstruction matches. |
| A06 | Protocol root is host-owned and absent from command mounts. | Journal/checkpoint/completion all verify and are equal to the adapter receipt. |
| A07 | Exact candidate/guest hashes, regular-file reads, `0444` staging and immutable command mounts. | Current and staged hashes/modes rechecked; command reconstruction matches claim hash. |
| A08 | Runner imports no scorer/outcome path; adapter ordering is hash-bound. | Reaped exit and exact container absence precede verified completion; no score/evaluation artifact exists. |
| A09 | Fresh exact name, one daemon binding, one-shot state and bounded timeouts. | Process reaped, cleanup verified, fresh independent absence check passes; any uncertainty is terminal failure. |
| A10 | Candidate schema permits probability only; manifest authority fields are false. | Claim, receipt and marker have exact all-false authority; candidate cannot add fields. |
| A11 | Reconstructed command has only two `readonly` binds and bounded tmpfs. | Closed artifact inventory and unchanged decoys prove no candidate-writable host channel was used. |
| A12 | Fixed candidate sends exactly one response per row; v4 quiet check active. | Exact two-line stdout byte count/hash; no extra/trailing output and correct alternating journal. |
| A13 | Existing strict UTF-8/duplicate/non-finite/parser regressions pass on exact source. | Only the two canonical finite interior probabilities appear in verified journal. |
| A14 | Exact byte/time/pids/memory/CPU/tmpfs flags and candidate cgroup/mount probes. | Probe-bearing candidate hash is bound; clean bounded process receipt; zero stderr. |
| A15 | Fixed candidate exits after EOF; adapter finish/abort source and regressions are bound. | Exit 0, reaped, two responses, no hang/EOF ambiguity and exact absence. |
| A16 | Fresh never-used ID/run key and absent protocol run at preflight. | Completed deterministic run is non-replayable; one-shot state is terminal and ID consumed. |
| A17 | Expected probabilities are fixed, finite and strictly within epsilon bounds. | Exact values and response identities verified from journal and stdout. |
| A18 | Pinned image, CLI bytes, environment, context/daemon, argv and command hash in manifest. | Independent image/client schema and full command reconstruction match claim/receipt; no test injection. |
| A19 | Exact name absent before launch; labels bind run ID; foreign state blocks. | Same-daemon exact-name inspect proves absence; unknown/foreign/drift rejects. |
| A20 | `--log-driver none`, zero candidate host-writable mounts, bounded stderr. | `stderr_bytes=0`, no Docker/candidate log artifact and closed directory allowlist. |
| A21 | Fixed source implements only `predict(public_row)` and keeps a two-row in-memory sequence counter. | Candidate/guest hashes match; exactly two one-row releases, no fit/full-sequence message. |
| A22 | One-shot claim is durable before dispatch; every boundary failure produces dominating terminal failure. | Canonical verifier plus failure precedence; exact ID is never retried regardless of PASS/FAIL/ambiguous result. |

## Severity-ranked blockers

There are no P0 or P1 findings in the proposed boundary.

The following are mandatory launch gates, not findings against the design:

- implement the fixed probe candidate and persistent one-shot runner;
- add offline regressions proving exact ID/path/schema/hook rejection and
  terminal image/client/command/stdout/decoy verification;
- freeze their exact hashes in a pre-launch manifest; and
- obtain the plan's independent pre-launch review at `0 P0 / 0 P1`.

If any gate is absent, changed after review or requires a real input or
writable host mount, the verdict for launch becomes `REPLAN`; do not dispatch.

## Exact files inspected

| File | SHA-256 |
|---|---|
| `research/market_rsi/AGENTS.md` | `4e0ac2d5a17f0c19e05582ccbb93482cb6db690b01fbf570689b6226360f39f0` |
| `minimal_prediction_loop/container_adapter.py` | `34d4df25da4cea9807a39874cf04c0ed52af1c83f23d3851476a947f998590c9` |
| `minimal_prediction_loop/container_candidate_guest.py` | `d79d927d0ca3affda43639455c18b164c59014186092a2183fe765fcf4ac7b36` |
| `minimal_prediction_loop/prediction_protocol.py` | `eb6bdc1367f62c2910225218389d7381cebb2477e92a523c83f0693ae21a5dd3` |
| `supervisor_harness/local_b_container.py` | `76b0420fdd9c0fdc6b90cbfdc35979e5c196f0917102936edb9ea3f03e8525be` |
| `supervisor_harness/AGENT_LOG_REAL_CANDIDATE_ADAPTER_THREAT_MODEL_2026-09-29.md` | `3a60f92a1f39253702ec8bf2c7ce735fe33c4d8927a0a547b79f979c2f99b41b` |
| `supervisor_harness/REAL_CANDIDATE_ADAPTER_INTEGRATION_2026-09-29.md` | `f59c5d541470b2c776c8a2ea30e38fb4518ed2543e09f6c7584d111df8c0d52a` |
| `supervisor_harness/AGENT_LOG_REAL_CANDIDATE_ADAPTER_INDEPENDENT_REVIEW_2026-09-29.md` | `b33146f3eb59909a1b83c314a0f1dfc9a0ef35482716d04afc13aeaf7180957b` |
| `supervisor_harness/SUPERVISOR_SYNTHETIC_ADAPTER_CANARY_2026-09-29-v1.json` | `5e7d293cfb4224b2bd87903a240594dc684bd44386ab7799263e1743d3e735e0` |
| `indicator-prediction-evals/SKILL.md` | `923a3bd1916d4c520cc7b768f8f14682c7781b012402921f93d4f663a0413d64` |
| `indicator-prediction-evals/references/evaluation-gates.md` | `fa268c203455d13e40e19e274d6d57a3f991d9aeea6e83b8f29b01bb99322fad` |

The v4 six-file ordered aggregate was independently confirmed from the prior
review as
`87a32217bca2919e1a4724785ef578a6b7cda23b10bf99c56319017235e9472b`.

## Checks performed

- Focused adapter suite under the persistent local Python 3.12 runtime:
  `26/26 PASS`, synthetic/fake transport only.
- Supervisor canary plan parsed as valid JSON: PASS.
- Scoped `git diff --check` over all inspected project files: PASS.
- Exact SHA-256 recomputation for every file listed above: PASS.
- Static command review: pinned image, exactly two read-only source mounts,
  no writable host mount, no network, read-only root, all capabilities
  dropped, no-new-privileges, private IPC, bounded pids/memory/CPU/tmpfs,
  UID/GID 65534, no Docker logging and exact guest environment: PASS.
- Static capability review: adapter/guest accept no dataset, outcome, scorer,
  trainer, provider, credential or protected-split parameter: PASS.

No Docker CLI command was executed by this reviewer. No canary artifact or
protocol run was created, and the authorized one-shot ID remains unconsumed.
