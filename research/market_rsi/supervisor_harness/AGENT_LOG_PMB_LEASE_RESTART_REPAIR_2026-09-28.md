# AGENT LOG — PMB lease restart repair — 2026-09-28

## Verdict

**PASS** for `repair_lease_restart` in
`market-rsi-pmb-synthetic-foundation-repair-20260928-02`.

The exact P1-2 reproduction now fails closed: a directly reconstructed
`EpisodeLease(store, lease_id)` cannot invoke any live transition.  The
registration-only crash window remains recoverable solely by terminally
marking the exact active lease `unresolved`, and that recovery can occur only
once.

## Scope and reviewed input

- Base Git HEAD: `f06214b3bb521096078d897fe60ec9ba589c00c6`.
- Independent review log SHA-256:
  `fb8b18cf62650ffa63534710f62c56361eae7ac3f8f0cb353241f9756dd537c3`.
- Pre-repair `episode_lease.py` SHA-256:
  `fa3c9623e4e974294d977105211098b74ac46e2537d0b0a91742fdd4fc9c32a8`.
- Pre-repair focused-test SHA-256:
  `2ba1d2c3fb81f6af28ccf6edde248414f37df5bd7aab046ddfc5542cccc864ad`.
- `artifact_store.py` was read but not edited; SHA-256:
  `51434782911cefa261d125ec4d1d978ac6dea7a4e923b8b4b78765d91ecc90de`.

No binder, upstream-lock, manifest, experiment-spec or integration file was
edited by this worker.

## Repair

`EpisodeLease.create` now registers only the exact newly-created Python object
as a process-local live handle after both the global claim and per-lease
registration append succeed.  `_verify_live` rejects every other object before
it can inspect state or create an artifact.  Consequently:

- the original object returned by `create` can run the one-shot lifecycle;
- `EpisodeLease(store, lease_id)` is always read-only/inert, including inside
  the creator process;
- no live-handle registration survives a process restart; and
- restart recovery remains the explicit class method
  `mark_interrupted_unresolved`, which never resumes work.

The regression suite invokes all seven transition entry points on a directly
reconstructed handle: start snapshot, task, early stop, synthesis, terminal
review, close and live unresolved.  Every call raises
`reconstructed lease handle cannot advance` before writing an artifact.

A second regression injects a crash after the global claim append but before
the per-lease registration append.  Recovery reconstructs only the committed
registration record and produces exactly these event sequences:

- lease journal: `registered`, `unresolved`;
- global registry: `claimed`, `terminal`.

A second recovery attempt fails because the lease is no longer the exact
active registration.

## Verification

- Exact P1-2 and registration-window regressions: **2/2 PASS**.
- Focused artifact-store and episode-lease module: **11/11 PASS**.
- Combined PMB simple-lane discovery: **43/43 PASS**.
- `py_compile` for the repaired source and focused test: **PASS**.
- Scoped tracked and untracked whitespace/diff checks: **PASS**.
- Static capability scan for subprocess, socket, HTTP client, `Popen`,
  `os.system`, `exec` and `eval`: **no matches**.

Commands used:

```text
python3 -m unittest -v research.market_rsi.tests.test_pmb_simple_lane_episode_lease
python3 -m unittest -v research.market_rsi.tests.test_pmb_simple_lane_episode_lease.EpisodeLeaseTests.test_directly_reconstructed_handle_cannot_advance_any_transition research.market_rsi.tests.test_pmb_simple_lane_episode_lease.EpisodeLeaseTests.test_registration_only_crash_window_closes_unresolved_exactly_once
python3 -m unittest discover -v -s research/market_rsi/tests -p 'test_pmb_simple_lane_*.py'
python3 -m py_compile research/market_rsi/pmb_simple_lane/episode_lease.py research/market_rsi/tests/test_pmb_simple_lane_episode_lease.py
```

## Exact repaired identity

- `research/market_rsi/pmb_simple_lane/episode_lease.py`:
  `51ed71c543202e48127fbb17ebad56cdda86fa7e6dc3772a59f15a3248a18615`
- `research/market_rsi/tests/test_pmb_simple_lane_episode_lease.py`:
  `2f0549c742b7b31085fecddba42c56e1d4f41edb4380203b4ed7b17958011c95`

## Authority boundary

This repair used only local source, temporary synthetic fixtures and
`unittest`.  It performed no network access, clone/fetch, PMB or episode-byte
intake, Docker action, provider/payment action, protected-state access,
training, evaluation, release or Git mutation.  It grants none of those
authorities.
