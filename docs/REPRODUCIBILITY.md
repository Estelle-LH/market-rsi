# What can a new reader reproduce?

A public clone currently supports **offline engineering and mechanism checks**.
It does **not** yet contain a complete package for independently rerunning the
reported 25-company financial results. This page makes that boundary explicit
rather than treating a passing test suite or a saved prompt as score reproduction.

## Three reproduction levels

| Level | Available today? | What it establishes |
| --- | --- | --- |
| Public software checks | Yes: [Quickstart](QUICKSTART.md) | CLI, synthetic review/feedback/state/identity and R/H adapter behavior |
| A synthetic two-round example | Yes: [engine fixture](../tests/test_capacity_feedback_engine.py) and [adapter fixture](../tests/test_earnings_capacity_adapter.py) | Actual fixture calculation, feedback consumption, state continuation, R/H selection and rollback |
| The empirical TRAIN25 result or autonomous paid trajectory | Not from this clone alone | Requires the exact scientific source, data/scorer, configuration, model and authority bundle below |

The first two levels use human-authored/deterministic fixtures. They do not
reproduce model-generated hypotheses, a financial score, or an independent
demonstration that a researcher improves.

## Which version are you looking at?

The published earnings source is the reviewed source/contract snapshot described
in [Earnings development](EARNINGS_DEVELOPMENT.md), through private checkpoint
`c1b644b`. Later experiment results and the October 27 continuation prompt
describe newer local experiment checkpoints; that private ancestry is not merged
into public main.

For example, the public population implementation keeps one stable version and
up to two explorers. The newer prompt's three-child/depth-layered search policy
is an experiment requirement, not a claim that this published source already
enforces the latest scheduler. Documentation publication, source implementation,
runtime activation and empirical validation are separate statuses.

## What a complete scientific reproduction package still needs

| Material | Required record | Current public boundary |
| --- | --- | --- |
| Scientific source | Exact frozen candidate R/H, actual parent and comparator source/hashes; engineering deltas and test versions | Code framework is public; later experiment-specific candidates/bindings remain local |
| Task and data | Ordered 25 company/task identities, target definitions, cutoffs, dataset version/hash and lawful acquisition instructions | Task scope and aggregate report are public; protected task bodies, data and answers are not included |
| Scorer | Original version, metrics, fractional-award rule and frozen per-target definitions | Aggregate convention is documented; original empirical scorer checkout is local |
| Model and runtime | Requested model, verified serving snapshot where known, effort, prompts, tools, resource limits and dependency versions | Some historical constants are in source; they are not a complete current run configuration |
| Execution policy | Attempts/retries, concurrency, deadlines, review, selection and failure handling | Source contracts and prospective prompt are public; experiment authority/configuration is local |
| Results and lineage | Complete 25-company outputs, awards, regressions, actual parent edges, feedback and adoption/growth decisions | Dated aggregate snapshots, report link and evidence hashes are public; complete run evidence is local |
| Resources and intervention | All generation/review/failure/evaluation costs, full pending, wall time and human repairs | Accounting code is public; live ledgers, grants and credentials remain local |

These are missing-material requirements, not instructions to copy protected
answers, grant files or credentials into Git. A later public package needs a
separately reviewed, lawful data/scorer distribution or acquisition path and
sanitized experiment manifests. Runtime authority must be obtained anew.

## How to interpret the present results

[Experiment 1](experiments/experiment-01-open-research/README.md) supplies the
current advisor report: the recorded R17 is 3.18/5 versus its own 3.00 baseline.
[Experiment 2](experiments/experiment-02-framework-restart/README.md) has its own
2.98 baseline and independent state. A baseline is not automatically the score
of an unmeasured code parent, and the two baselines are not interchangeable.

The repeated TRAIN25 trajectory is adaptive Discovery. Its public report is
evidence about that recorded execution, not a matched rerun or proof of
generalization. Model calls can also vary even when the requested model name
matches; an unverified serving snapshot stays unknown. Score reproduction
means a fully specified comparable procedure, not a promise of identical future
model responses.

## Record your own offline reproduction

Record the public commit, OS, Python version, exact command, exit status,
test count and explicit skips. A clean standard-library Python 3.12.3 venv was
used for this publication's quickstart checks; no provider calls or private
experiment ledger writes were needed.

If a command fails, preserve that result and report the missing dependency or
binding. Do not substitute another scorer, fabricate zeros for missing companies,
replay paid requests or enable external data paths to make the run appear complete.

The [comparison plan](experiments/COMPARISON_PLAN.zh-CN.md) describes how to
compare the two actual experiments after complete results exist. This page
does not launch either experiment or expose heldout data.
