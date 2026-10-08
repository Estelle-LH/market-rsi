# Prediction-first minimal loop integration — 2026-09-29

## Verdict

`INDEPENDENT_PASS`

The exact snapshot below runs a deterministic two-round synthetic loop without
PredictionMarketBench:

1. a label-free candidate produces probabilities one public row at a time;
2. the trusted host scores the exact complete mask against decision-time market
   probability with proper scores;
3. only a bounded aggregate score receipt enters the lineage;
4. round 1 improves equal-event Brier and is `KEEP`;
5. its consumed Dev commitment becomes later Train;
6. round 2 worsens Brier and is `REVERT`;
7. restart read-back preserves the parent, used IDs and completed prediction
   receipts; and
8. Final remains unseen, unopened and unscored.

The first independent attack review returned `REPLAN` with four P1 findings.
The v2 rereview confirmed those four repairs, then found one remaining P1:
the trusted-row hash was not required to equal the frozen Dev manifest content
hash, and the complete trusted score existed only in memory. This exact v3
snapshot adds the narrow causal repair:

- Dev promotion and its checkpoint now precede parent decision; the two safe
  cross-ledger crash windows recover without rescoring.
- Candidate score records are extracted from the verified prediction journal,
  and the compact receipt binds the protocol receipt, journal, public rows,
  trusted rows, candidate records, scorer specification and full score output.
- Memory is code-derived from the bound score and allowlisted decision codes;
  callers cannot supply memory.
- Both lineage and the loop's lifecycle adapter check a durable ledger head,
  byte count and whole-file hash on every restart; suffix truncation fails
  closed and final heads are bound into the integration receipt.
- The lifecycle adapter exposes the exact frozen Dev dataset commitment; the
  scorer's trusted-row commitment must equal it before score binding or Dev
  promotion, and recovery rechecks the same equality.
- The complete trusted score is persisted as canonical JSON under its own
  SHA-256. Recovery rejects missing, changed, noncanonical or symlinked score
  artifacts. A regression flips every outcome without changing public rows
  and proves the round fails closed before score binding, promotion or parent
  change.

The v3 rereview then found that a forged, internally consistent compact score
could cite the genuine full-score hash while carrying contradictory aggregate
metrics. In v4, the compact lineage receipt is derived only from the parsed,
canonical, hash-verified full-score artifact. Recovery reconstructs it again
and requires exact equality for every commitment and aggregate before Dev
promotion or lineage decision. A genuine `REVERT` artifact paired with forged
`KEEP` compact metrics now leaves Dev unpromoted and the parent unchanged.

This is an orchestration proof only.  It is not evidence of real-data quality,
predictive improvement, untrusted-code isolation, promotion, PnL, or PMB
compatibility.

## Exact source and test identity

The aggregate recipe is SHA-256 of the standard `shasum -a 256` output for the
following files in this exact order.  Aggregate:

`26059d5ce860e12b3f8c3e66466c78895a9431831d1ad08c1b978c0402707839`

| File | SHA-256 |
|---|---|
| `minimal_prediction_loop/__init__.py` | `74168733688dbe7299e6bf85f86d18de477ea985175b13c8bfd42bc8d380e620` |
| `minimal_prediction_loop/probability_contract.py` | `7ba4a32d3c3a2ab80ac17ca6c18ea29fe864b958de8a81ac2be59dba121e9d74` |
| `minimal_prediction_loop/proper_scoring.py` | `64165cbceb4bcba6d03b6b42402ea7a47790c9a57f9280b15bfe2fe57becc06b` |
| `minimal_prediction_loop/prediction_protocol.py` | `eb6bdc1367f62c2910225218389d7381cebb2477e92a523c83f0693ae21a5dd3` |
| `minimal_prediction_loop/lineage.py` | `7ef2a6742f96cf11e6a43f693d36761082db1e4ab7f8fc34b8825f03ddde3cff` |
| `minimal_prediction_loop/loop.py` | `879d0b1bf451b55888c19946234e03aa360fa81c18109d28a85fe3ff029d48a9` |
| `tests/test_minimal_probability_contract.py` | `b8e3e895843d87b564ddbcad2215295dc9e238e408b5a75c287cb11cf94a308f` |
| `tests/test_minimal_prediction_protocol.py` | `9931c44f8d689386b3cb134965bcf704743226c02f587ae6aa7aa5a79e38197a` |
| `tests/test_minimal_prediction_lineage.py` | `f770ab303e5f01f7593718c6d5434901f602a32c4e50460a2fdf1243a3e4e5f8` |
| `tests/test_minimal_prediction_loop_integration.py` | `008bf16ad9c03c35e401c33f745cbb02cb41d78e31b44e8e1310242dd9a134a9` |

## Canonical synthetic receipt

The canonical invocation is:

```text
cd research/market_rsi
python3 -B -m minimal_prediction_loop.loop <new-local-persistent-output-directory>
```

Observed immutable receipt body commitment:

`receipt_sha256 = bfcc249db331b290881f24e8a8d4dd5ead711b4453b65b6090fef3acee385a4b`

Observed receipt-file SHA-256:

`129b20c47d32095fd69eb637272bf52348c6b3f3093b93144bfb2bce1de05ae6`

The receipt reports:

- decisions: `KEEP`, then `REVERT`;
- round-1 equal-event Brier delta: `-0.12000000000000004`;
- round-2 equal-event Brier delta: `0.4800000000000001`;
- final parent equals the round-1 candidate;
- used Dev IDs: `dev-1`, `dev-2` exactly once;
- promoted Dev IDs: `dev-1`, `dev-2`;
- each trusted-row hash equals its frozen Dev manifest commitment;
- persisted full-score artifact hashes: round 1
  `eb90d3192fc733526d7219e7f06f22bb3a4e6e77f9a77e606fe4f320764176f6`,
  round 2 `21837dbe72b9393a8bafc9dfb0c75c36da545775a0fd024df3e661571927abbc`;
- final lifecycle checkpoint: head `076d6b55b4ce12f3f1dcfd5ae835f0c3bcdcbc3dc89034089e25fcb831e49d26`,
  file `415278e278b2a625fe0f9db9cb8cd6bb0a6e1d2db6f429a2464f1f2166304ca3`;
- final lineage checkpoint: head `b6851a42d22ef1f68fd40b327a5a48bd3b8ba7f59d9f0cbf470789af6099a3c0`,
  file `fafe9cfd6337cbef7d5d9241edca69c1386496e851994d57e476eac8888f70b9`;
- candidate-visible Dev labels and Final: false in both rounds;
- real isolation, real data, provider, network, payment, promotion, PnL and PMB
  authority: false/zero.

## Verification

Focused implementation suite:

```text
python3 -B -m unittest -v \
  tests.test_minimal_probability_contract \
  tests.test_minimal_prediction_protocol \
  tests.test_minimal_prediction_lineage \
  tests.test_minimal_prediction_loop_integration
```

Result: `54 tests`, `PASS`.

Adjacent lifecycle, prior prediction-stream and supervisor gate suites:

```text
python3 -B -m unittest -v \
  tests.test_data_lifecycle \
  tests.test_prediction_stream \
  supervisor_harness.test_bottleneck_gate
```

Result: `33 tests`, `PASS`.

Scoped `py_compile` passed for all ten new source/test files.  A static scan
found no imports of network clients, process launchers, PMB or PnL replay code,
and no `os.system`, `eval` or `exec` use.

The repository-wide discovery command reached `878` tests but is not a green
gate in the current host environment: `43` existing modules cannot import
because `harbor`, `pyarrow` or `sklearn` is absent; one existing subprocess
test consequently observes `ModuleNotFoundError` instead of its expected
`RuntimeError`; one test is skipped.  The same run otherwise completed `833`
tests.  No dependency was downloaded or installed, and this environmental
result is not represented as a full-suite pass.

## Authority boundary

No network, provider, paid call, real or public dataset, PMB episode, Docker,
protected Dev, Final, training, empirical evaluation, release, Git commit,
tag, push or publication occurred.  `real_isolation_admitted` remains false.
Fresh non-author attack review returned `PASS` with `0 P0 / 0 P1`. It
reproduced the exact source/test aggregate, receipt body/file, score artifacts
and final ledger heads above; reran 54/54 focused and 33/33 adjacent tests; and
replayed all six former P1 attacks. The exact review is recorded in
`AGENT_LOG_PREDICTION_FIRST_MINIMAL_LOOP_REVIEW_2026-09-29.md`.

The synthetic-loop bottleneck is therefore closed. The next plan may inventory
already-opened local data for a non-promotional diagnostic and design a real
candidate isolation canary. Neither is authorized by this PASS to fetch data,
open protected splits, run training, call a provider, publish, or promote.
