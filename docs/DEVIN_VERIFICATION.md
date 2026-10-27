# Independent public-clone verification

Date: 2026-10-27. Scope: the public onboarding path, not a paid scientific run.

## Why a repair was necessary

The documentation snapshot
[`153b6b22f913db10e2b320d8cf716c5a44e5cb70`](https://github.com/Estelle-LH/market-rsi/commit/153b6b22f913db10e2b320d8cf716c5a44e5cb70)
passed targeted checks in a fresh Mac Python venv. That environment still had
access to the original host's private files, so this was not sufficient evidence
of portability.

At the human's request, Devin independently cloned that exact GitHub commit on
Ubuntu 22.04.5 LTS x86_64, using Python 3.12.16 in a new venv with
`include-system-site-packages = false`; NumPy was absent. The two-round example
failed. Its generic sum/count fixture inherited an earnings setup that pinned
an unused scorer at an absolute private macOS path. This dependency was real,
even though those generic tasks use their own arithmetic scorer.

## Preserved initial results

Run from the repository root, with `PYTHONPATH=tools:tests:research/market_rsi`
for the unittest commands. Times below are rounded wall times from Devin's
record, not model execution times.

| Check | Original `153b6b2` result | Time |
| --- | --- | --- |
| `python -B -m market_rsi --help` | Exit 0 | 0.04 s |
| `python -B -m market_rsi check --suite smoke` | Exit 0; 69 tests passed | 1.4 s |
| `python -B -m unittest test_capacity_feedback_engine test_earnings_capacity_adapter -v` | Exit 1; 16 tests ran, nine errors | 0.45 s |
| `python -B -m unittest test_public_docs test_layout test_structure_contract test_cli test_check -v` | Exit 0; 27 tests passed | 0.18 s |
| `timeout 300 ... python -B -m unittest discover -s tests -v` | Exit 1; 643 tests ran, 199 errors, 11 skips; not a timeout | 21 s |

These selections overlap; their counts are not additive distinct-test coverage.

## Bounded repair

Devin proposed a patch confined to two test-fixture files. The reviewed
integration keeps that scope:

- [The earnings fixture](../tests/test_earnings_capacity_loop.py) exposes an
  overridable kernel setup method. Its default still calls the original
  earnings kernel loader; no empirical scorer or expected financial value changes.
- [The generic fixture](../tests/test_capacity_feedback_engine.py) binds no
  earnings kernel and removes that unused field from its execution envelope.
  Sum/count outputs are still actually calculated and scored.
- A regression guard rejects any attempt by generic fixture setup to call the
  private loader, even on a machine where that private file exists. The added
  test checks envelope paths and the unchanged default earnings-loader delegation.
- A boolean failure-injection flag is renamed so it no longer shadows
  `unittest.TestCase.fail`; genuine assertion failures remain readable.

The production engine, source-bound modules, scorer, data, model settings,
admission guards, adoption rules, live ledgers and both experiments are unchanged.
This is a portability repair, not an R/H scientific improvement.

## Retest evidence and limits

Devin's proposed patch passed the two-round selection (17 tests, 7.25 s), with
three additional successful reruns. Smoke (69) and focused developer checks
(27) also passed. The reviewed integration additionally passed the 17-test
selection locally on Python 3.12.3 without third-party packages. Those results
must not be confused with an independent checkout of a later published commit;
record that exact commit and fresh-clone result when retesting it.

The broader suite is **not green**. With Devin's proposed patch it ran 644
tests with 190 errors, one failure and 11 skips. A separate pinned-CPU-dependency
venv still had 180 errors, two failures and 11 skips. Known causes include
private scorer/data/runtime paths, hardcoded temporary-directory assumptions
and a floating-point exact-equality test that also failed on the unpatched
checkout. Do not substitute a fake empirical scorer, silently skip these cases
or enable Docker/resident-data opt-ins to turn this into a full-suite claim.

No LLM forecast, paid research batch, private-data evaluation or experiment
accounting write was run by the verification commands. Passing the minimal
path establishes synthetic calculation, feedback/state continuation and R/H
adapter mechanics. It does **not** reproduce the TRAIN25 3.18/5 result or prove
autonomous learning or generalization.

## Original audit artifacts

Devin cloud session: `devin-cf35926ec9c94459b6f2e1d2dc5a036f`
(“Test Public Market RSI”). No commit, push or PR was delegated to Devin.

- [Original proposed patch](https://app.devin.ai/attachments/6501e87c-e8b9-45f2-b203-3de9af64292b/market-rsi-portable-synthetic-fixture.patch)
- [Original cloud audit logs](https://app.devin.ai/attachments/d43a1f32-8c56-4b7f-8eae-7019e4bb58a1/market-rsi-devin-cloud-audit-logs.tgz)

These links retain their existing Devin access controls; they are not a promise
of anonymous access. The summary and repair are in this public repository.
See [Quickstart](QUICKSTART.md) for the runnable path and
[Reproducibility](REPRODUCIBILITY.md) for the missing scientific materials.
