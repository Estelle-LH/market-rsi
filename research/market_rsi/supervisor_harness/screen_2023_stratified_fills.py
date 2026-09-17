"""Execute the frozen 12-game, four-week-band 2023 source-density diagnostic.

Counts only revision-pinned public on-chain fills. No game score, price,
outcome, model, feature, Dev or Final data is inspected. This is not admission.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from supervisor_harness.plan_2023_density_audit import PER_STRATUM, STRATA
from supervisor_harness.screen_2023_archive_catalog import REVISION, encoded, sha
from supervisor_harness.screen_2023_fill_canary import count_fills, schedule_starts


def month_partitions(lower: int, upper: int) -> list[tuple[str, str]]:
    if upper <= lower or upper - lower > 24 * 3600:
        raise ValueError("expected positive fixed window of at most one day")
    first = datetime.fromtimestamp(lower, timezone.utc)
    last = datetime.fromtimestamp(upper - 1, timezone.utc)
    months = [(first.year, first.month)]
    if (last.year, last.month) != months[0]:
        months.append((last.year, last.month))
    return [(f"{year:04d}-{month:02d}",
             "https://huggingface.co/datasets/moose-code/polymarket-onchain-v1/resolve/"
             f"{REVISION}/order_filled/year={year}/month={month:02d}.parquet")
            for year, month in months]


def check_plan(plan_dir: Path, mapping_dir: Path) -> list[dict]:
    manifest = json.loads((plan_dir / "manifest.json").read_text())
    raw = (plan_dir / "selection.json").read_bytes()
    mapping_raw = (mapping_dir / "mapping.json").read_bytes()
    if (manifest.get("schema") != "market_p0_2023_stratified_density_plan_v1"
            or manifest.get("selection_sha256") != sha(raw)
            or manifest.get("mapping_sha256_verified") != sha(mapping_raw)
            or manifest.get("season_denominator") != 285
            or manifest.get("missing_market_games_retained") != 48
            or manifest.get("selected_games") != PER_STRATUM * len(STRATA)
            or manifest.get("formal_data_admitted") is not False):
        raise ValueError("frozen stratified plan changed")
    plan = json.loads(raw)
    selection = plan["selection"]
    mapping = {row["game_id"]: row for row in json.loads(mapping_raw)}
    if len(selection) != 12 or len({item["game_id"] for item in selection}) != 12:
        raise ValueError("sample not 12 distinct games")
    for item in selection:
        source = mapping.get(item["game_id"])
        if (source is None or source["condition_id"] != item["condition_id"]
                or source["token_ids"] != item["token_ids"]):
            raise ValueError("sample identity differs from source mapping")
    counts = {name: sum(item["stratum"] == name for item in selection)
              for _, _, name in STRATA}
    if any(value != PER_STRATUM for value in counts.values()):
        raise ValueError("sample no longer balanced by fixed band")
    return selection


def screen(plan_dir: Path, mapping_dir: Path, schedule: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(output)
    selection = check_plan(plan_dir, mapping_dir)
    starts = schedule_starts(schedule.read_bytes(), selection)
    results = []
    output.mkdir(parents=True, exist_ok=False)
    for item in selection:
        kickoff = starts[item["game_id"]]
        partitions = month_partitions(kickoff - 12 * 3600, kickoff + 5 * 3600)
        parts = [count_fills(url, item["token_ids"], kickoff) for _, url in partitions]
        result = {"game_id": item["game_id"], "stratum": item["stratum"],
                  "kickoff_epoch_utc": kickoff,
                  "partitions": [{"month": month, "url": url} for month, url in partitions],
                  "window_fills": sum(part["fixed_window_fills"] for part in parts),
                  "pregame_fills": sum(part["pre_game_fills"] for part in parts),
                  "in_game_fills": sum(part["game_to_plus_five_hours_fills"] for part in parts),
                  "distinct_window_seconds": sum(part["distinct_window_seconds"] for part in parts)}
        results.append(result)
        # A partial, clearly unadmitted receipt survives an infrastructure failure.
        (output / "progress.json").write_bytes(encoded({"completed_games": len(results),
                                                        "results": results,
                                                        "formal_data_admitted": False}))
    raw = encoded(results)
    report = {"schema": "market_p0_2023_stratified_fill_density_v1",
              "plan_selection_sha256_verified": sha((plan_dir / "selection.json").read_bytes()),
              "source_mapping_sha256_verified": sha((mapping_dir / "mapping.json").read_bytes()),
              "schedule_sha256_verified": sha(schedule.read_bytes()),
              "result_sha256": sha(raw), "completed_games": len(results),
              "season_denominator": 285, "mapped_games": 237,
              "unmatched_market_games_retained": 48,
              "remote_partition_objects_fully_downloaded_and_hashed": False,
              "prices_or_outcomes_read": False, "event_aligned_labels_verified": False,
              "formal_data_admitted": False, "provider_cost_usd": "0"}
    (output / "results.json").write_bytes(raw)
    (output / "manifest.json").write_bytes(encoded(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-public-archive-queries", action="store_true")
    args = parser.parse_args()
    if not args.execute_public_archive_queries:
        parser.error("refusing archive queries without explicit flag")
    print(json.dumps(screen(args.plan, args.mapping, args.schedule, args.output),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
