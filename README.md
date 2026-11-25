# Market RSI

Market RSI studies whether an automated research system can improve earnings forecasts by changing how it finds and uses evidence. The harness proposes one change, builds and reviews a candidate, then evaluates the frozen candidate on a fixed training panel. Scores and evidence feed into the next research decision.

## Start here

| I want to… | Go to |
| --- | --- |
| Review the experiment that scored 3.18 / 5 | [Round 17 source and reproduction guide](https://github.com/Estelle-LH/market-rsi/blob/77dec3448530d0e667ab6a5967292b313b6c990e/README.md) · [Score record](https://github.com/Estelle-LH/market-rsi/blob/77dec3448530d0e667ab6a5967292b313b6c990e/reproduction/round17/evidence.json) · [Frozen R/H programs](https://github.com/Estelle-LH/market-rsi/tree/77dec3448530d0e667ab6a5967292b313b6c990e/reproduction/round17/frozen) |
| Run the public tests | [Offline quickstart](docs/QUICKSTART.md) |
| Understand the research loop | [Architecture](docs/ARCHITECTURE.md) |
| Debug the Q12 Review handoff | [Run 239 failure and offline test](https://github.com/Estelle-LH/market-rsi/blob/79ce87fbe375b22e04e297141cb3a9e04a5f4a5b/research/market_rsi/harness_review/README.md#current-q12-debug-snapshot) |
| Read the experiment notes | [Experiment index](docs/experiments/README.md) · [Documentation map](docs/README.md) |

## Results

| Snapshot | Measured outcome |
| --- | --- |
| **Round 17 · candidate 154** | **3.18 / 5** on 25 companies and 125 targets, from 79.5 points. It was selected as the incumbent. The saved Round 0 baseline was 3.00. |
| **Frozen candidate 222** | **3.04 / 5** on the complete training panel. The 3.18 incumbent was retained. [Run record](https://github.com/Estelle-LH/market-rsi/blob/3867a6e70dd56e0c9b53a0ec4740cf3b2a2586d7/research/market_rsi/harness_review/README.md) |
| **Q12 · run 239** | Controller and Author completed. Review stopped during local validation before its first model request. The candidate stayed unfrozen and received no score. |

These scores are from a reused training panel. Experiment 2 is an independent restart with its own 2.98 baseline. The [experiment index](docs/experiments/README.md) explains the two tracks and their evidence.

## Run and reproduce

Run the public smoke suite with Python 3.12 from the repository root.

```sh
python3.12 -B -m market_rsi check --suite smoke
```

The smoke suite uses synthetic fixtures and needs only the standard library. For Round 17, use the dedicated source branch, which includes the historical harness and the exact frozen R/H programs.

```sh
git clone --branch codex/harness-incumbent-318-full-source --single-branch \
  https://github.com/Estelle-LH/market-rsi.git market-rsi-round17
cd market-rsi-round17
python3.12 reproduction/round17/verify.py
```

The verifier checks the frozen program hashes. With the original comparison report supplied locally, it also recomputes the 3.18 score from the 125 target awards. A fresh model evaluation requires the local dataset, scorer and a newly reviewed runtime. Keep credentials, the ledger and sealed experiment inputs local. [Reproduction details](docs/REPRODUCIBILITY.md)

## How the harness works

```text
Controller proposes → Author implements → Review checks → Freeze → Evaluate
        ↑                                                          ↓
        └────────────── Evidence, scores and memory ─────────────────┘
```

The harness distinguishes changes to **C** (the prediction recipe), **R** (the research policy) and **H** (the tools and harness). The reports track forecast scores, observed research behavior and engineering fixes separately.

| Directory | Contents |
| --- | --- |
| [market_rsi/](market_rsi/) | Public CLI and test commands |
| [tools/](tools/) | Earnings roles, evaluation and runtime checks |
| [research/market_rsi/supervisor_harness/](research/market_rsi/supervisor_harness/) | Shared research engine and feedback loop |
| [tests/](tests/) | Software regressions and synthetic fixtures |
| [docs/](docs/README.md) | Architecture, research reports and development guides |

See [Development](docs/DEVELOPMENT.md) for wider checks and [Repository structure](docs/REPOSITORY_STRUCTURE.md) for active and legacy code.
