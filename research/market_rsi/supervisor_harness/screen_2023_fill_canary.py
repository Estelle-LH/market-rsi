"""Fixed first/middle/last 2023 game CLOB fill-density source canary.

Uses only the prior source-only identity mapping and schedule kickoff identity.
No price, outcome, score, feature, label, or protected evaluation data is read.
The three archive partitions are revision-pinned; their publisher LFS hashes
are recorded but not independently checked without a full download.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from supervisor_harness.screen_2023_archive_catalog import REVISION, SCHEDULE_SHA256, encoded, sha


PARTITION_HASHES = {
    "2023-09": "0759ef1db85d9a74f9a83d2ba05117ed86ad1ae2ab1102198e696c621035d6dc",
    "2023-10": "dc7f40f92269f4befe18d7c4e7b8faebfeacccf62982f74a31a6fed883064edf",
    "2024-01": "ba8ad5b664d34b028931f63442379d803f5a76827a108ac43a921aa4d1c02e3c",
}


def fixed_sample(mapping: list[dict]) -> list[dict]:
    if len(mapping) < 3 or len({row["game_id"] for row in mapping}) != len(mapping):
        raise ValueError("mapping must contain at least three distinct games")
    ordered = sorted(mapping, key=lambda row: (row["game_date"], row["game_id"]))
    return [ordered[0], ordered[len(ordered) // 2], ordered[-1]]


def schedule_starts(raw: bytes, chosen: list[dict]) -> dict[str, int]:
    if sha(raw) != SCHEDULE_SHA256:
        raise ValueError("schedule hash changed")
    ids = {row["game_id"] for row in chosen}
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not {"game_id", "season", "gameday", "gametime"}.issubset(reader.fieldnames or ()):
        raise ValueError("schedule kickoff fields missing")
    starts = {}
    for row in reader:
        if row["game_id"] not in ids:
            continue
        if row["season"] != "2023" or not row["gametime"]:
            raise ValueError("sample has missing or wrong-season kickoff")
        local = datetime.fromisoformat(f'{row["gameday"]}T{row["gametime"]}')
        starts[row["game_id"]] = int(local.replace(tzinfo=ZoneInfo("America/New_York")).timestamp())
    if set(starts) != ids:
        raise ValueError("sample kickoff not uniquely identified")
    return starts


def partition_for(kickoff: int) -> tuple[str, str]:
    lower = datetime.fromtimestamp(kickoff - 12 * 3600, timezone.utc)
    upper = datetime.fromtimestamp(kickoff + 5 * 3600, timezone.utc)
    if (lower.year, lower.month) != (upper.year, upper.month):
        raise ValueError("fixed window crosses a partition; include both before running")
    key = lower.strftime("%Y-%m")
    if key not in PARTITION_HASHES:
        raise ValueError("unexpected partition for the frozen sample")
    url = ("https://huggingface.co/datasets/moose-code/polymarket-onchain-v1/resolve/"
           f"{REVISION}/order_filled/year={lower.year}/month={lower.month:02d}.parquet")
    return key, url


def count_fills(url: str, token_ids: list[str], kickoff: int) -> dict:
    import duckdb

    if len(token_ids) != 2 or len(set(token_ids)) != 2:
        raise ValueError("expected two distinct market token IDs")
    connection = duckdb.connect()
    try:
        result = connection.execute(
            """SELECT count(*) AS all_partition_fills,
                      count(*) FILTER (WHERE ts >= ? AND ts < ?) AS fixed_window_fills,
                      count(*) FILTER (WHERE ts >= ? AND ts < ?) AS pre_game_fills,
                      count(*) FILTER (WHERE ts >= ? AND ts < ?) AS game_to_plus_five_hours_fills,
                      count(DISTINCT ts) FILTER (WHERE ts >= ? AND ts < ?) AS distinct_window_seconds,
                      min(ts) AS first_partition_fill_ts, max(ts) AS last_partition_fill_ts
                 FROM (SELECT try_cast(timestamp AS BIGINT) AS ts
                         FROM read_parquet(?)
                        WHERE makerAssetId IN (?,?) OR takerAssetId IN (?,?))""",
            [kickoff - 12 * 3600, kickoff + 5 * 3600,
             kickoff - 12 * 3600, kickoff, kickoff, kickoff + 5 * 3600,
             kickoff - 12 * 3600, kickoff + 5 * 3600,
             url, *token_ids, *token_ids],
        ).fetchone()
    finally:
        connection.close()
    keys = ("all_partition_fills", "fixed_window_fills", "pre_game_fills",
            "game_to_plus_five_hours_fills", "distinct_window_seconds",
            "first_partition_fill_ts", "last_partition_fill_ts")
    return dict(zip(keys, result, strict=True))


def screen(mapping_dir: Path, schedule: Path, output: Path) -> dict:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    report = json.loads((mapping_dir / "manifest.json").read_text())
    mapping_raw = (mapping_dir / "mapping.json").read_bytes()
    if (report.get("schema") != "market_p0_2023_archive_identity_v1"
            or report.get("matched_unique_games") != 237
            or report.get("mapping_sha256") != sha(mapping_raw)
            or report.get("formal_data_admitted") is not False):
        raise ValueError("expected verified, unadmitted 237-game 2023 mapping")
    sample = fixed_sample(json.loads(mapping_raw))
    schedule_raw = schedule.read_bytes()
    starts = schedule_starts(schedule_raw, sample)
    results = []
    for item in sample:
        kickoff = starts[item["game_id"]]
        key, url = partition_for(kickoff)
        counts = count_fills(url, item["token_ids"], kickoff)
        results.append({"game_id": item["game_id"], "game_date": item["game_date"],
                        "market_slug": item["market_slug"], "condition_id": item["condition_id"],
                        "kickoff_epoch_utc": kickoff, "partition": key,
                        "partition_url": url,
                        "partition_sha256_publisher_claim": PARTITION_HASHES[key],
                        **counts})
    result_raw = encoded(results)
    manifest = {"schema": "market_p0_2023_fixed_fill_canary_v1",
                "selection": "first, middle, last by (game_date, game_id) among 237 mapped candidates",
                "mapping_sha256_verified": sha(mapping_raw),
                "schedule_sha256_verified": sha(schedule_raw),
                "results_sha256": sha(result_raw), "sample_games": len(results),
                "partition_objects_downloaded_and_hashed": False,
                "labels_verified": False, "prices_read": False,
                "formal_data_admitted": False, "provider_cost_usd": "0"}
    output.mkdir(parents=True, exist_ok=False)
    (output / "results.json").write_bytes(result_raw)
    (output / "manifest.json").write_bytes(encoded(manifest))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-public-archive-queries", action="store_true")
    args = parser.parse_args()
    if not args.execute_public_archive_queries:
        parser.error("refusing public archive queries without explicit flag")
    print(json.dumps(screen(args.mapping, args.schedule, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
