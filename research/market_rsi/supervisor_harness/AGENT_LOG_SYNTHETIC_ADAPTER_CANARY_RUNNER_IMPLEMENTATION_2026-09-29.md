# Synthetic adapter canary runner implementation — 2026-09-29

- Implementer: `synthetic_adapter_canary_runner_worker_20260929`
- Plan ID / authorized one-shot ID:
  `market-rsi-real-candidate-isolation-canary-20260929-01`
- Scope: implementation and static checks only. No Docker command, attempt
  directory, protocol run, provider, real/protected data, scorer, training,
  fetch, release, commit, tag or push was used.

## 2026-09-29 — implementation result

Status: `IMPLEMENTATION_COMPLETE_STATIC_PASS_PENDING_TEST_FREEZE_AND_REVIEW`

The fixed candidate and argument-free one-shot runner now implement the two
approved design reviews.  The production preflight remains intentionally
blocked by `EXPECTED_TEST_SHA256 = None` until the Supervisor finishes and
freezes the dedicated offline test at:

```text
research/market_rsi/supervisor_harness/test_run_synthetic_adapter_canary.py
```

This is a fail-closed integration gate, not a launch failure and not ID
consumption.  After inserting the final test hash, the Supervisor must also
recompute the runner normalized self-hash, run the offline suites, freeze the
new exact raw runner hash, and obtain the mandatory independent 0 P0 / 0 P1
prelaunch review.  No live dispatch is ready from this implementation log.

### Fixed synthetic candidate

`minimal_prediction_loop/synthetic_isolation_canary_candidate.py`:

- accepts exactly the two frozen synthetic public rows and returns only `0.25`
  then `0.75`;
- binds the exact row schema/content, deterministic row IDs, sequence and one
  stable deterministic run ID;
- rejects a buffered or kernel-readable next stdin row before each response;
- checks on each prediction that only the guest and candidate source files are
  visible under `/opt/market-rsi`, both are exact `0444` read-only bind mounts,
  and the root filesystem is read-only;
- rejects visibility of the exact two host decoys, Docker socket and a closed
  allowlist of credential/host paths;
- requires UID/GID `65534:65534`, no supplementary groups, `NoNewPrivs=1` and
  only loopback;
- performs bounded denial probes to RFC 5737 `192.0.2.1` and
  `/var/run/docker.sock` without DNS or fetch;
- requires cgroup pids `32`, memory `512 MiB`, exactly one CPU, and a
  `64 MiB rw,noexec,nosuid,nodev` tmpfs; and
- creates and deletes only one tiny in-container `/tmp` probe. It emits no
  diagnostics, authority fields or durable candidate output.

### One-shot runner and consumption boundary

`supervisor_harness/run_synthetic_adapter_canary.py`:

- exposes an argument-free production `main()` and one exact ID, run key,
  candidate, row sequence, persistent path, image and reviewed v4 aggregate;
- rejects an existing attempt root before any Docker access;
- completes source/self/test/path, Docker CLI/context/daemon, local pinned
  image and exact-name absence preflight before creating ID-scoped state;
- creates the exact persistent attempt directory exclusively; that directory
  is the irreversible replay tombstone even if the subsequent intent write,
  adapter setup or process construction is interrupted;
- writes and fsyncs canonical immutable `launch-intent.json`, then two fixed
  synthetic host decoys, before entering the adapter;
- calls `run_local_candidate_prediction()` exactly once with only its default
  production transport/control/binding path and without `allow_temporary`;
- contains no retry, fallback, recursive re-entry or cleanup-and-recreate path;
- writes a canonical failure receipt after any catchable post-consumption
  error, while retaining the attempt root as consumed/unknown if failure
  writing is itself interrupted; and
- keeps zero-provider, zero-cost and every real-data, protected-split, fetch,
  scoring, training, release and promotion authority false.

### Strict outer terminal verifier

The outer verifier supplements the reviewed v4 adapter verifier by requiring:

- exact canonical launch-intent and success schemas with failure dominance;
- exact source, runner, candidate, guest, row, deterministic run/name, pinned
  image and Docker client/context/daemon bindings;
- full reconstructed Docker argv and command hash, including exactly the two
  read-only source mounts, `--pull never`, no network and hardened limits;
- exact staged source hashes/modes and production `test_mode=false` by default;
- canonical alternating release/commit journal, exact two reconstructed stdout
  lines/bytes/hash, zero stderr, reaped process and exit zero;
- resumed protocol claim/journal/checkpoint/completion equality and fixed
  probabilities;
- unchanged host decoy hashes, a closed file and directory inventory, current
  pinned image observation, and a fresh exact-name container-absence check
  under the same Docker binding; and
- immutable outer success cross-binding to the intent, adapter receipt and
  protocol completion. A marked test-mode chain is accepted only when the
  verifier caller explicitly asks for offline test mode; the production
  default rejects it and test mode can never carry outer production success.

## Exact implementation identity

```text
synthetic_isolation_canary_candidate.py raw SHA-256
260165e6f2681ac5d4e93bd473bc15abca7bd4f70d10e469e7b875da4c09e80d

run_synthetic_adapter_canary.py raw SHA-256
0d18561485958e0fe5797e422bf35d48c168e9065679e8e54d7570287943026c

run_synthetic_adapter_canary.py normalized self SHA-256
92b9126c4327c18dbb42542d2ea62e7870239adb5351d71ed020b1ea12a33557

reviewed v4 six-file ordered aggregate
87a32217bca2919e1a4724785ef578a6b7cda23b10bf99c56319017235e9472b

deterministic protocol run ID
run-d3a2b3b31170f8bf5a611f8e913567d7553b8783152d7cad9152d01d1c495f26

boundary review SHA-256
650e1944bafe8f33d20f292ff42a7737b246d348d284d9446defdce5b0ba9918

one-shot review SHA-256
907c404b48998848f95ce76e5374f70ed81fc41eecf375fc8519f816c0f5f15f
```

The raw runner hash above is the exact pre-test-freeze implementation snapshot.
It will necessarily change once `EXPECTED_TEST_SHA256` is filled; do not reuse
this raw hash as the later launch snapshot.

## Checks performed

- Read `AGENTS.md` and both required synthetic canary design reviews fully.
- Applied `indicator-prediction-evals` and kept this work strictly before the
  prediction/objective/PnL evaluation stages.
- Python 3.12 AST parse plus in-memory `compile(...)` for candidate and runner:
  `PASS`.
- Imported the runner with `-B`; validated the fixed path boundary, exact two
  public rows, deterministic run ID and normalized self-hash: `PASS`.
- Invoked the source-snapshot check and required the exact current result
  `dedicated offline test hash is not frozen`: `PASS` for the deliberate
  fail-closed prelaunch gate.
- Scoped `git diff --check`: `PASS`.
- Static call scan: exactly one adapter invocation; no retry loop, provider,
  scorer, trainer, fetch, protected split or `subprocess.Popen` entry exists in
  the runner/candidate: `PASS`.
- Exact authorized attempt path and canary parent both remained absent after
  all checks: ID unconsumed.

No live Docker command or empirical test was performed. The next owner must
add/finalize the dedicated synthetic offline tests, fill their exact hash,
refresh the runner self/raw hashes, run the declared suites, and request a
fresh independent prelaunch review. Only a later 0 P0 / 0 P1 PASS permits the
single authorized live dispatch.
