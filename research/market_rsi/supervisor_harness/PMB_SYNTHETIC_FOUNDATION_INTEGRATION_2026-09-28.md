# PMB synthetic foundation integration receipt — 2026-09-28

## Verdict

Supervisor integration is **PASS, pending fresh independent review** for the
zero-provider synthetic foundation only.  This snapshot validates local
commitments and a one-shot artifact lifecycle; it does not clone, fetch,
install, import or execute PredictionMarketBench, and it does not open any
real episode, invoke a provider, train, evaluate, publish or grant admission.

## Integrated contract

`pmb_simple_lane.__init__` adds one cross-component boundary:
`bind_synthetic_foundation`.  It revalidates the immutable experiment spec and
requires exact agreement between its source commitments and the prospective
upstream-lock plus episode-manifest-set hashes.  It rejects empty or malformed
commitments, role mismatches, Final sets below 20 untouched dates, and every
attempt to set upstream runtime admission, data admission or execution
authority.  Its receipt exposes no paths, data bytes, process runner or token;
all three authority bits are fixed to `false`.

The integration test then binds that zero-authority receipt into an
append-only synthetic episode lease, exercises early stop followed by the
mandatory taskless slot-5 synthesis, obtains an independent terminal-review
record, and proves the terminal lease is read-only and cannot resume.

## Exact reviewed inputs

| Path | SHA-256 |
|---|---|
| `pmb_simple_lane/__init__.py` | `1d33bc169a7d06839d24a1cd7987823dea5eb1719aa3ff3cf2c39550dbe62081` |
| `pmb_simple_lane/upstream_lock.py` | `970feed94a3f258d6a624794540e7da4f1faf9665f206e2a9544619271db42f1` |
| `pmb_simple_lane/episode_manifest.py` | `44f1cfdf9ea70815846bf61e7eee9607712e10d09895f5079ce8eb03f4a8481f` |
| `pmb_simple_lane/experiment_spec.py` | `cd71a67345d58fd343f5620696b417a31f884a3d96c40af3a87826caa70dacb2` |
| `pmb_simple_lane/artifact_store.py` | `51434782911cefa261d125ec4d1d978ac6dea7a4e923b8b4b78765d91ecc90de` |
| `pmb_simple_lane/episode_lease.py` | `fa3c9623e4e974294d977105211098b74ac46e2537d0b0a91742fdd4fc9c32a8` |
| `tests/test_pmb_simple_lane_integration.py` | `5c885042f47084b44a60b4e0f98b6b9fc21614d4ace3803c433a4fa90253927e` |
| `tests/test_pmb_simple_lane_upstream_manifest.py` | `fdb0cda1f5a8500df70f895a94d87a11ad8ffd049b4989915ffad285430c413e` |
| `tests/test_pmb_simple_lane_experiment_spec.py` | `94a7df9ab52b25df2ea522664a21f09bce5cec6ddb88c35c690e9499479d32ed` |
| `tests/test_pmb_simple_lane_episode_lease.py` | `2ba1d2c3fb81f6af28ccf6edde248414f37df5bd7aab046ddfc5542cccc864ad` |

The prospective upstream commit remains
`611d66941717310858683278940df21c33c406f2`.  It is an identity commitment,
not an admitted checkout; this integration performed no clone or fetch.

## Replayed verification

- `python3 -m unittest discover -s research/market_rsi/tests -p 'test_pmb_simple_lane_*.py'`
  — **41/41 PASS** on the integrated snapshot.
- `python3 -m py_compile research/market_rsi/pmb_simple_lane/*.py research/market_rsi/tests/test_pmb_simple_lane_*.py`
  — **PASS**.
- `python3 -m unittest supervisor_harness.test_bottleneck_gate` from
  `research/market_rsi` — **6/6 PASS**.
- `git diff --check -- research/market_rsi/pmb_simple_lane research/market_rsi/tests/test_pmb_simple_lane_*.py`
  — **PASS**.
- Static import/call scan found no subprocess, socket, requests, urllib, httpx,
  `os.system` or `Popen` capability in the package or focused tests.

The first pre-integration combined discovery exposed a test import-path
mismatch after 30 tests; the lease worker made a test-only path setup repair,
after which 38/38 passed with unchanged source hashes.  A later root-context
invocation of `test_bottleneck_gate` likewise failed because that legacy test
expects `research/market_rsi` on `sys.path`; the exact test passed 6/6 from its
declared package root.  Neither failure was suppressed or treated as a code
PASS before the corrected deterministic rerun.

## Residual gates

Independent review is still mandatory for these exact hashes.  Even after a
PASS, actual PMB checkout/package intake, episode acquisition or opening,
Docker/runtime construction, paid Controller use, hidden Dev, sealed Final,
training, empirical evaluation, a release, commit, tag or push all remain
separate blocked actions requiring their own reviewed plan and applicable
authorization.
