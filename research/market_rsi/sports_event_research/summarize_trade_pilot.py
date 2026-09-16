"""Summarize a frozen Train-only NFL trade/alignment pilot without scoring."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


HORIZONS = (30, 60, 300)


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summarize(trade_manifests: list[dict], alignment_manifests: list[dict]) -> dict:
    if not trade_manifests or len(trade_manifests) != len(alignment_manifests):
        raise ValueError("trade and alignment manifest counts must match and be nonzero")
    trades = {row["selection_sha256"]: row for row in trade_manifests}
    alignments = {row["selection_sha256"]: row for row in alignment_manifests}
    if len(trades) != len(trade_manifests) or set(trades) != set(alignments):
        raise ValueError("trade/alignment selection hashes are not one-to-one")
    if any(row["canonical_game"]["split_role"] != "market_train" for row in trades.values()):
        raise ValueError("pilot contains a non-Train game")
    if any(row.get("possibly_truncated_at_20000") for row in trades.values()):
        raise ValueError("pilot contains a possibly truncated trade tape")
    if any(row.get("scientific_score") is not False for row in (*trades.values(), *alignments.values())):
        raise ValueError("pilot manifest unexpectedly contains a scientific score")
    total_plays = sum(row["summary"]["plays"] for row in alignments.values())
    horizons = {}
    for horizon in HORIZONS:
        covered = sum(row["summary"][f"covered_{horizon}s"] for row in alignments.values())
        weighted_abs = sum(
            row["summary"][f"covered_{horizon}s"]
            * row["summary"][f"mean_absolute_change_{horizon}s"]
            for row in alignments.values()
        ) / covered
        horizons[f"{horizon}s"] = {
            "covered_plays": covered,
            "coverage": covered / total_plays,
            "minimum_single_game_coverage": min(
                row["summary"][f"coverage_{horizon}s"] for row in alignments.values()
            ),
            "play_weighted_mean_absolute_price_change": weighted_abs,
        }
    return {
        "games": len(trades),
        "window_trades": sum(row["frozen_window"]["trades"] for row in trades.values()),
        "window_distinct_timestamp_sum": sum(
            row["frozen_window"]["distinct_timestamps"] for row in trades.values()
        ),
        "plays": total_plays,
        "horizons": horizons,
    }


def build(trade_paths: list[Path], alignment_paths: list[Path], output: Path) -> dict:
    trade_paths, alignment_paths = list(map(Path, trade_paths)), list(map(Path, alignment_paths))
    summary = summarize(
        [json.loads(path.read_text()) for path in trade_paths],
        [json.loads(path.read_text()) for path in alignment_paths],
    )
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    result = {
        "schema": "polymarket_nfl_trade_alignment_pilot_summary_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        **summary,
        "trade_manifest_receipts": [
            {"path": str(path.resolve()), "sha256": sha(path)} for path in sorted(trade_paths)
        ],
        "alignment_manifest_receipts": [
            {"path": str(path.resolve()), "sha256": sha(path)} for path in sorted(alignment_paths)
        ],
        "split_role": "market_train",
        "route_dev_opened": False,
        "sealed_final_opened": False,
        "claim_layer": "descriptive_historical_market_response",
        "historical_l2_or_fill_claim": False,
        "scientific_score": False,
    }
    (output / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-manifest", action="append", type=Path, required=True)
    parser.add_argument("--alignment-manifest", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.trade_manifest, args.alignment_manifest, args.output), indent=2))


if __name__ == "__main__":
    main()
