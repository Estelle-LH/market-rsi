# Portable deployment checks

These independent Python 3.12 utilities check synthetic deployment fixtures. They do not import the research runtime, access its state, call external model APIs, or create cloud resources. Fixture tests use only the standard library; the optional native numerical probe requires the installed scientific packages described below. These are supplementary engineering checks, not production admission or learning evidence.

From the repository root:

```sh
python3 -I -B -m unittest discover -s examples/deployment_checks -p 'test_*.py' -v
```

The suite contains 30 guest-probe tests, 13 identity-diagnostic tests, 31 bundle tests, 16 artifact-transport tests, 14 command-journal tests, 16 stop-sequence tests and 17 bounded-metadata tests (137 total). The complete public fixture revision passes under Python 3.12.3 both locally and on AWS. The stop sequence has synthetic adapter coverage only; no fixture performs a real cloud stop.

## Guest probe

`guest.py` exposes `collect()`, `validate(report)` and `main()`. Run the guest itself only inside an approved disposable Linux container. It inspects its own process status and mount table, network interface names, environment and Docker-socket existence, and makes unique write probes in `/` and `/tmp`. It removes only its own successfully created files and makes no network requests.

The guest expects nonroot UID/GID, zero effective capabilities, no-new-privileges, seccomp, loopback-only networking, a read-only root and a writable `/tmp` mounted with noexec/nosuid/nodev. It expects only the declared clean environment. It emits JSON and intentionally exits **37** when all assertions pass; failures exit 1. A wrapper must check both the JSON and the actual child exit code. This file does not create a container or select an image.

## Identity diagnostic

`identity_diag.py` freezes SHA256 hashes of synthetic initial CLI/context/daemon identities. Injected context and daemon observers receive `timeout_seconds=8`. Each `before_create()` persists a unique receipt containing initial/observed hashes before returning success or raising a failure. Timeouts leave observed hashes unknown; errors and context/daemon drift remain distinct.

Receipt publication uses file fsync, atomic hard-link publication and directory fsync. Observation or persistence failure blocks `guarded_create(fake_create)`. The frozen baseline is never refreshed and observations are never retried. CLI re-observation is not supplied and is explicitly marked `NOT_OBSERVED`.

Injected callbacks do not enforce an operating-system deadline. A real transport must retain its actual eight-second subprocess limits and original identity checks. Both `TimeoutError` and `subprocess.TimeoutExpired` are classified as timeouts. A successful observation proves only that instant, not long-term stability. The example has no Docker transport and creates no containers.

## Ordinary-file bundle installer

`bundle_io.py` accepts only an explicit manifest and payload mapping, authenticated by a separately held SHA256 of the canonical manifest. It checks every file's path, size and digest before creating a destination. It does not discover or execute files. Paths are relative, canonical and cannot occupy the completion-record namespace; the destination must be a new canonical absolute path under an existing trusted private directory.

Successful installation writes and fsyncs files, reads them back, and publishes a fully written/fsynced completion receipt with a no-overwrite hard link. A failed installation retains its directory and cannot resume or overwrite it. The receipt records file integrity, not workload permission. A local completion marker cannot establish cross-host ownership or financial/research closure. Fault-injection tests do not establish physical power-loss durability or resistance to a malicious process with access to the trusted parent.

Devin's first actual run found six failing cases across three defects: destination spelling normalization, a reserved namespace collision, and premature completion-marker publication. The corrected implementation passed all original cases plus two additional publication/sync failure cases: 31/31. No failed expectation was removed.

## Artifact transport

`artifact_transport.py` provides bounded binary/base64 parts, exclusive part-file writes, SHA256-checked ordered assembly, strict HTTPS fetching and bounded gzip/JSON decoding. Assembly accepts at most 512 parts; callers must choose an encoding chunk width that stays within that count. Fetching pins the exact HTTPS hostname and permits only the original final URL, rejects credentials and redirects, verifies byte count and SHA256, and suppresses exception text that could contain temporary URL credentials. Tests inject fake openers; they make no network requests.

Devin's first 16-method run exposed two failing subcases: response userinfo and a changed same-host destination. The fix retained the original assertions. The unchanged suite then passed 16/16 both locally and on the exact cloud Python 3.12.3. The tested fetch/decode helper was also used in an actual private ordinary-code installation; private URLs and bindings are excluded here.

## Command journal

`command_journal.py` fsyncs a new per-key dispatch intent before calling the injected submitter. A duplicate key cannot submit again, including when the acknowledgement is missing or malformed. A persisted acknowledgement binds the original intent hash and command/target identity; observation checks the returned identity, state and real response code. Unknown acknowledgements remain unknown and do not invoke the observer or resubmit.

Devin independently wrote and ran 14 tests for duplicate calls, uncertain acknowledgements, partial or modified journals, symlinks, sync ordering, status handling and exception redaction. The helper was then used for a real finite deployment-test dispatch and observation. These are local dispatch semantics, not cross-host ownership, physical crash durability or production scientific closure.

## Stop sequence

`stop_sequence.py` holds the caller's dispatch-exclusion context across two stable terminal/idle observations, an original-closure verifier callback, and journal-protected stop submission. It requires complete named receipt bindings for terminal, finance, requests, cleanup, private seal and memory. These digests are only adapter bindings: the callback must run the original validators. The module supplies no cloud client, real lock, state reader or default verifier, so it cannot establish real scientific closure or cross-host exclusion itself.

Pre-submit errors remain blocked. If stop was submitted without a known acknowledgement, the state remains unknown and cannot resubmit. A late exclusion-release error after a known acknowledgement raises `StopReleaseFailed` carrying that exact acknowledgement, allowing observation of the existing request. Exception suppression by the context manager cannot silently turn a failure into success.

The first 15-method test run retained one failure against an overbroad requirement that even a release error after submission must imply zero prior stop calls. That temporal requirement was corrected explicitly, with the first source/test/report preserved. The implementation now preserves the known/unknown outcome after late release errors. The other 14 original methods are unchanged; the corrected case and one small regression method bring this unit to 16/16. Tests use local fakes and ordinary journal I/O, with no cloud or research-state operations.

## Bounded metadata adapter

`bound_metadata.py` adapts `pin(path)` and `read(binding)` to a separately authenticated, explicit manifest of ordinary JSON metadata. It rejects noncanonical paths, symlinks, unlisted reads, changed sizes/hashes, duplicate JSON fields and nonfinite values. It uses bounded regular-file reads, keeps a defensive audit of verified files, and never follows references stored inside JSON. Exceptions suppress filesystem error messages that might contain private data. The private root and manifest are trusted inputs; this is not a boundary against a malicious process with the same filesystem authority.

Devin independently wrote and ran 17 tests. The same tests pass under the exact cloud Python 3.12.3. A separate isolated integration uses the adapter to execute the authenticated original memory-gate functions unchanged over fresh synthetic metadata. Its 18 cases, including stop-sequence wiring, pass locally and on AWS. That private integration is not included in this public fixture directory: the original module is not imported, real research state is not read, and the other five closure verifiers remain synthetic callbacks. These results do not grant production admission.

## Optional native numerical probe

`native_math_probe.py` performs a fixed NumPy matrix product, SciPy LU solve, scikit-learn affine fit, in-memory joblib round trip, and threadpoolctl limit check. It requires an already approved environment with those packages; it downloads and installs nothing. Run it in its own process with numerical thread limits set before imports:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -I -B examples/deployment_checks/native_math_probe.py
```

A successful result shows those small synthetic operations worked in that process. The metadata field `external_model_api_calls=0` does not count the local synthetic estimator fit. This probe is not an end-to-end research benchmark, a sustained stability test, or runtime admission.

The guest and identity utilities were authored and fixture-tested by Devin. The bundle installer and native probe were written for this deployment exercise; Devin independently wrote and ran the bundle regression tests and statically reviewed the native arithmetic. The publication package is tested again independently of the original research checkout. No real infrastructure identifiers, account data or private research receipts accompany it.
