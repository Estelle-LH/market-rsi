# PMB immutable experiment-spec implementation — 2026-09-28

- Assigned at `2026-09-28T23:15:34Z`; base HEAD `f06214b3bb521096078d897fe60ec9ba589c00c6`; dirty Market RSI diff digest `ec4ca5ae3a5975f4c5647e4e3126ef8d5c8810c0dbfb3ece20770ed135e84f6b`.
- Write scope: `pmb_simple_lane/experiment_spec.py`, one focused test and this log.
- Boundary: synthetic local bytes only; no evaluator, provider, data or protected state.

## Implementation record

- `2026-09-28T23:15:34Z` — Read the accepted PMB v1/v2 contract, the
  `indicator-prediction-evals` skill and its evaluation gates. Reused the
  already-recorded PMB research: this is an enforcement implementation, not a
  new empirical method or claim.
- Observed problem: the accepted design had no executable byte commitment that
  could prove one sentence, one changed causal stage, complete frozen fields,
  public-diagnostic non-promotion and a separate precommitted Track B.
- Alternatives considered: a mutable frozen dataclass of nested dictionaries
  (rejected because nested values remain mutable); schema-only validation
  (rejected because it cannot prove which causal stage changed); and canonical
  immutable bytes plus explicit baseline/candidate stage hashes (implemented).
- Implemented `pmb_simple_lane/experiment_spec.py` using only the Python
  standard library. It provides deterministic sorted compact UTF-8 JSON and
  SHA-256; detached immutable byte commitments; exact-key validation; complete
  non-empty target, horizon, executable price, maximum lateness, row mask,
  cadence, baseline, normalizer, trainer, loss, scorer, feature-sign, cost,
  latency, exclusion, missingness, seed, source, runtime and schema bindings;
  and baseline/candidate hashes for exactly the five causal stages.
- Track separation is fail-closed: Track A cannot change `pnl`; any Track B
  contract requires a caller-supplied used-ID ledger, a fresh ID different from
  Track A, `pnl` as its sole changed stage, a precommitted policy hash, the
  unchanged frozen Track A prediction hash and no Track B-to-A feedback.
- Public `public_diagnostic_train` evidence cannot set promotion eligibility.
- The trusted file boundary exclusively creates the canonical bytes, fsyncs the
  file and directory, removes all write bits, rejects symlinks/writable files,
  and can revalidate both bytes and original file/directory identities. A
  same-byte pathname replacement is therefore detected by the full commitment.
- Initial focused run had 15 tests with 2 fixture errors: the synthetic Track B
  helper did not make its prediction-stage component hash equal its declared
  frozen-prediction hash. The implementation correctly rejected it; the fixture
  was repaired rather than weakening validation.

## Final verification

- `python3 -m unittest discover -s research/market_rsi/tests -p
  'test_pmb_simple_lane_experiment_spec.py' -v` — **PASS**, 16/16 tests.
- `python3 -m py_compile
  research/market_rsi/pmb_simple_lane/experiment_spec.py
  research/market_rsi/tests/test_pmb_simple_lane_experiment_spec.py` — **PASS**.
- `git diff --check -- <the three assigned paths>` — **PASS**.
- Source SHA-256:
  `cd71a67345d58fd343f5620696b417a31f884a3d96c40af3a87826caa70dacb2`.
- Test SHA-256:
  `94a7df9ab52b25df2ea522664a21f09bce5cec6ddb88c35c690e9499479d32ed`.
- Final verification time: `2026-09-28T23:22:14Z`.

## Boundary and result

- No network, PMB/episode bytes, provider, Docker, protected state, training,
  evaluation, release or Git publication was used.
- The code grants no experiment authority; it only validates and freezes
  synthetic commitments. Fresh integration and independent review remain the
  Supervisor's next gates.

Result: **PASS for `implement_immutable_experiment_spec`**.
