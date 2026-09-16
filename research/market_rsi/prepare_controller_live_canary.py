#!/usr/bin/env python3
"""Materialize one synthetic, score-free workspace for the live GLM harness canary."""
from __future__ import annotations

import argparse
from pathlib import Path

from market_rsi import fresh_json, identifier


PROMPT = """This is a synthetic controller-harness canary. It is not market evidence and cannot
support a research or profitability claim.

Use each available controller tool at least once. Inspect the Train/Dev summary, search the public
literature fixture for `probability calibration`, write a small candidate named `candidate.py`, run
that candidate on the synthetic Train-CV fixture, and read your own research history. After you
have read every returned result, call `submit_decision` exactly once with exactly these fields:
`action`, `question`, `hypothesis`, `evidence`, `candidate_artifact`, and
`expected_failure_condition`. Make every field a short string and clearly label the evidence as
synthetic canary evidence. Then return one short sentence saying the harness canary is complete.
"""


def main(workspace: Path) -> None:
    workspace = workspace.resolve()
    identifier(workspace.name)
    workspace.mkdir(parents=True, mode=0o700, exist_ok=False)
    fresh_json(workspace / "train-dev-summary.json", {
        "schema": "synthetic_controller_canary_v1",
        "research_evidence": False,
        "train": {"rows": 20, "positive_rate": 0.50},
        "dev": {"rows": 10, "positive_rate": 0.50},
        "instruction": "Exercise the harness only; do not infer performance.",
    })
    fresh_json(workspace / "own-history.json", {
        "schema": "synthetic_controller_history_v1",
        "research_evidence": False,
        "rounds": [],
    })
    (workspace / "prompt.md").write_text(PROMPT, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    main(parser.parse_args().workspace)
