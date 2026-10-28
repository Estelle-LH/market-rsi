# Portable deployment checks

These independent Python 3.12 utilities check synthetic deployment fixtures. They do not import the research runtime, access its state, call external model APIs, or create cloud resources. Fixture tests use only the standard library; the optional native numerical probe requires the installed scientific packages described below. These are supplementary engineering checks, not production admission or learning evidence.

From the repository root:

```sh
python3 -I -B -m unittest discover -s examples/deployment_checks -p 'test_*.py' -v
```

The suite contains 30 guest-probe fixture tests, 13 identity-diagnostic fixture tests and 31 ordinary-file bundle tests (74 total). Tests mock Linux inspection; running this command does not inspect a live container or Docker daemon. Identity tests create and remove temporary receipt files under the current directory.

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

## Optional native numerical probe

`native_math_probe.py` performs a fixed NumPy matrix product, SciPy LU solve, scikit-learn affine fit, in-memory joblib round trip, and threadpoolctl limit check. It requires an already approved environment with those packages; it downloads and installs nothing. Run it in its own process with numerical thread limits set before imports:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -I -B examples/deployment_checks/native_math_probe.py
```

A successful result shows those small synthetic operations worked in that process. The metadata field `external_model_api_calls=0` does not count the local synthetic estimator fit. This probe is not an end-to-end research benchmark, a sustained stability test, or runtime admission.

The guest and identity utilities were authored and fixture-tested by Devin. The bundle installer and native probe were written for this deployment exercise; Devin independently wrote and ran the bundle regression tests and statically reviewed the native arithmetic. The publication package is tested again independently of the original research checkout. No real infrastructure identifiers, account data or private research receipts accompany it.
