# PMB synthetic foundation integration receipt v2 — 2026-09-28

## Verdict

Supervisor integration is **PASS, pending fresh independent rereview** for the
repaired zero-provider synthetic foundation.  V1 remains rejected.  V2 closes
both independently reproduced P1 bypasses and adds binder-level authenticity
and canonical-byte checks.  It still grants no PMB, data, runtime, provider,
experiment, payment, training, evaluation, publication or release authority.

## Repairs integrated

1. Direct `UpstreamLock`, `EpisodeManifest` and `ExposureRecord` instances are
   canonically serialized and replayed through their mapping validators.
2. `ProspectiveUpstreamVerification` and `ManifestSetValidation` are now
   validator-issued receipts. Public construction, `dataclasses.replace` and
   dataclass-shaped objects without the private issuance token fail closed.
3. `bind_synthetic_foundation` calls both receipt-authenticity checks before
   consuming any summary field. Its own receipt is binder-issued and cannot be
   constructed through the public class initializer.
4. The binder now rejects a hash-consistent but noncanonical directly-created
   `ExperimentSpec`.
5. Only the exact `EpisodeLease` object returned by `create` is process-locally
   live. A reconstructed handle cannot call any of seven transitions; a
   registration-only crash can only be terminally marked `unresolved` once.

All receipts continue to fix `runtime_admitted`, `data_admitted` and
`execution_authorized` to `false`.  They expose no paths, episode bytes,
process runner or provider token.

## Exact v2 identity

| Path | SHA-256 |
|---|---|
| `pmb_simple_lane/__init__.py` | `c9ba803c77716def751a162a9e7073e530d1d8b9719a31d1a15d802eaa430761` |
| `pmb_simple_lane/upstream_lock.py` | `ff655ca583816596d1603958e1ec1fd2d8aa2613fc6cec8061433f85c5c87e2e` |
| `pmb_simple_lane/episode_manifest.py` | `5039a3a6fd1eed1cac188a3e45fb35697d0c0ca44aac1f97116b427023690ba6` |
| `pmb_simple_lane/experiment_spec.py` | `cd71a67345d58fd343f5620696b417a31f884a3d96c40af3a87826caa70dacb2` |
| `pmb_simple_lane/artifact_store.py` | `51434782911cefa261d125ec4d1d978ac6dea7a4e923b8b4b78765d91ecc90de` |
| `pmb_simple_lane/episode_lease.py` | `51ed71c543202e48127fbb17ebad56cdda86fa7e6dc3772a59f15a3248a18615` |
| `tests/test_pmb_simple_lane_integration.py` | `274e2e8a2d225426c4d8a9e4957427a918e70117c89ef4105ce5dbccc1c62a30` |
| `tests/test_pmb_simple_lane_upstream_manifest.py` | `8730f9ef5b76ad5d008b1b1755e66cf3ee6fcd3900e1783eb1cd18afa7a24e74` |
| `tests/test_pmb_simple_lane_experiment_spec.py` | `94a7df9ab52b25df2ea522664a21f09bce5cec6ddb88c35c690e9499479d32ed` |
| `tests/test_pmb_simple_lane_episode_lease.py` | `2f0549c742b7b31085fecddba42c56e1d4f41edb4380203b4ed7b17958011c95` |

The aggregate SHA is
`e235b469b96510f578411a184286639a931e8f37aaf46091bf5a8d8ef31356d6`.
It is computed by running `shasum -a 256` on the ten paths in the table order
used by the command below—package order `__init__`, `artifact_store`,
`episode_lease`, `episode_manifest`, `experiment_spec`, `upstream_lock`, then
test order `integration`, `episode_lease`, `experiment_spec`,
`upstream_manifest`—and piping that exact textual output to
`shasum -a 256`:

```text
shasum -a 256 <the ten repo-relative paths above in stated order> | shasum -a 256
```

Absolute versus relative path text changes the aggregate; constituent hashes
are therefore authoritative and the exact command must be replayed from repo
root with the `research/market_rsi/...` path prefix.

The prospective upstream commit remains
`611d66941717310858683278940df21c33c406f2`; no clone or fetch occurred.

## Verification

- Six exact P1/integration adversarial regressions: **6/6 PASS**.
- Full PMB-focused discovery: **48/48 PASS**.
- `py_compile` over all package and focused test files: **PASS**.
- Supervisor bottleneck-gate regression: **6/6 PASS**.
- Scoped `git diff --check`: **PASS**.
- Static scan found no subprocess, socket, requests, urllib, httpx, aiohttp,
  `Popen`, `os.system`, `exec` or `eval` import/call capability.

An initial selector-only attempt used three stale guessed unittest method names
and returned three `AttributeError` loader errors while the other named probes
passed.  No code result was accepted from that command.  The exact current
method names were then enumerated from source; all six required probes passed,
followed by the complete 48-test discovery above.

## Residual gates

Fresh independent rereview must recompute every constituent hash and replay
both original v1 reproductions plus equivalent bypasses.  Until that returns
PASS, v2 is not an accepted durable snapshot.  Even after PASS, PMB
clone/fetch/submodule/package intake, episode acquisition/opening, Docker or
runtime construction, provider or paid Controller use, hidden Dev, sealed
Final, training, empirical evaluation, release, commit, tag, push and
publication remain separate blocked actions requiring their own gates and
applicable authorization.
