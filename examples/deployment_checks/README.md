# Portable deployment checks

These independent, standard-library Python 3.12 utilities test synthetic fixtures. They do not import the research runtime, access its state, call models, or create cloud resources. They are supplementary engineering checks, not production admission or learning evidence.

From the repository root:

```sh
python3 -I -B -m unittest discover -s examples/deployment_checks -p 'test_*.py' -v
```

The suite contains 30 guest-probe fixture tests and 13 identity-diagnostic fixture tests. Tests mock Linux inspection; running this command does not inspect a live container or Docker daemon. Identity tests create and remove temporary receipt files under the current directory.

## Guest probe

`guest.py` exposes `collect()`, `validate(report)` and `main()`. Run the guest itself only inside an approved disposable Linux container. It inspects its own process status and mount table, network interface names, environment and Docker-socket existence, and makes unique write probes in `/` and `/tmp`. It removes only its own successfully created files and makes no network requests.

The guest expects nonroot UID/GID, zero effective capabilities, no-new-privileges, seccomp, loopback-only networking, a read-only root and a writable `/tmp` mounted with noexec/nosuid/nodev. It expects only the declared clean environment. It emits JSON and intentionally exits **37** when all assertions pass; failures exit 1. A wrapper must check both the JSON and the actual child exit code. This file does not create a container or select an image.

## Identity diagnostic

`identity_diag.py` freezes SHA256 hashes of synthetic initial CLI/context/daemon identities. Injected context and daemon observers receive `timeout_seconds=8`. Each `before_create()` persists a unique receipt containing initial/observed hashes before returning success or raising a failure. Timeouts leave observed hashes unknown; errors and context/daemon drift remain distinct.

Receipt publication uses file fsync, atomic hard-link publication and directory fsync. Observation or persistence failure blocks `guarded_create(fake_create)`. The frozen baseline is never refreshed and observations are never retried. CLI re-observation is not supplied and is explicitly marked `NOT_OBSERVED`.

Injected callbacks do not enforce an operating-system deadline. A real transport must retain its actual eight-second subprocess limits and original identity checks. Both `TimeoutError` and `subprocess.TimeoutExpired` are classified as timeouts. A successful observation proves only that instant, not long-term stability. The example has no Docker transport and creates no containers.

These files were authored and fixture-tested by Devin, then reviewed for a finite deployment exercise. The publication package is tested again independently of the original research checkout. No real infrastructure identifiers, account data or private research receipts accompany them.
