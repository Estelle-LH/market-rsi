"""Audit whether the original Train-only state delta used future rows.

This reads only the already-open Train panels and their bound historical PBP.
It computes no predictive score and never reads Route-Dev or Final.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np

from sports_event_research.run_train_method_screen import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET,
    sha256,
    write_json,
)


def run(panel_root: Path, output: Path) -> dict:
    panel_root, output = Path(panel_root).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("fresh availability-audit output required")
    output.mkdir(parents=True)
    gaps, before_label, games, eligible_rows = [], 0, 0, 0
    for game_root in sorted(path for path in panel_root.iterdir() if path.is_dir()):
        panel, manifest = game_root / "play_trade_alignment.csv", game_root / "manifest.json"
        if not panel.is_file() or not manifest.is_file():
            continue
        binding = json.loads(manifest.read_text())
        if binding.get("panel_sha256") != sha256(panel):
            raise ValueError("Train panel changed after its alignment manifest")
        with panel.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        required = set(NUMERIC_FEATURES + CATEGORICAL_FEATURES + (
            TARGET, "play_timestamp", "home_price_60s_timestamp"))
        if not rows or not required.issubset(rows[0]):
            raise ValueError("Train panel lacks availability-audit fields")
        eligible = [row for row in rows if row[TARGET] != ""
                    and all(row[name] != "" for name in NUMERIC_FEATURES + CATEGORICAL_FEATURES)]
        eligible_rows += len(eligible); games += 1
        for current, successor in zip(eligible, eligible[1:]):
            gap = int(successor["play_timestamp"]) - int(current["play_timestamp"])
            if gap < 0:
                raise ValueError("play timestamps are not chronological")
            gaps.append(gap)
            before_label += int(successor["play_timestamp"]) <= int(current["home_price_60s_timestamp"])
    if not gaps:
        raise ValueError("no eligible Train successors to audit")
    values = np.asarray(gaps, dtype=float)
    result = {
        "schema": "state_surprise_availability_audit_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "train_games": games,
        "eligible_rows": eligible_rows,
        "rows_using_a_later_eligible_row": len(gaps),
        "later_row_gap_seconds": {
            "median": float(np.median(values)),
            "p90": float(np.quantile(values, 0.90)),
            "p99": float(np.quantile(values, 0.99)),
            "over_60_count": int(np.sum(values > 60)),
            "over_60_fraction": float(np.mean(values > 60)),
        },
        "later_row_at_or_before_60s_label_trade_count": before_label,
        "later_row_at_or_before_60s_label_trade_fraction": before_label / len(gaps),
        "causal_availability_passed": False,
        "reason": (
            "The original representation used the next target-eligible row, not the current "
            "event's end_situation. Every nonterminal delta therefore depended on a later row."
        ),
        "required_fix": "Use only the current play record's end_situation and post-play score.",
        "predictive_scores_computed": False,
        "route_dev_opened": False,
        "sealed_final_opened": False,
    }
    write_json(output / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(run(**vars(parser.parse_args())), indent=2))
