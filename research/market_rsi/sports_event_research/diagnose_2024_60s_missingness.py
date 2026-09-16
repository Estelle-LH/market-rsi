"""Diagnose why the frozen 2024 NFL sample lacks 60-second trade labels.

This is a read-only, Train-source data-quality audit. It reports mutually
exclusive missingness reasons, not model scores or live-availability claims.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
import gzip
import json
from pathlib import Path

from sports_event_research.audit_2024_pbp_trade_support import sha, timestamp
from sports_event_research.run_train_method_screen import write_json


EXPECTED_SCREEN_MANIFEST = "44be88eeafd316cd2792810a754b54ff7b5eeee158d5acad638608f2c409c89b"
EXPECTED_SELECTION_MANIFEST = "0e83ce7f1ad0907ce062c911458f9193749e584bf55a87881ecdfc0604416956"
EXPECTED_SUPPORT_MANIFEST = "0ab1735aaa9245e0780b08f76b4cd1fd1fe9a9e82b4361a139a640414a390e3d"
EXPECTED_NFLVERSE = "23370d5d10f8104d80d46a1fc5e61f4f6f5a3263fe96fe2dd629913cfcb08c06"
HORIZON_SECONDS = 60
MAX_PRE_AGE_SECONDS = 300
REASONS = ("no_prior_trade", "stale_prior_trade", "recent_prior_no_post_trade", "covered")


def classify(play_time: int, trade_times: list[int]) -> str:
    if trade_times != sorted(trade_times):
        raise ValueError("trade times must be sorted")
    prior = bisect_right(trade_times, play_time) - 1
    if prior < 0:
        return "no_prior_trade"
    if play_time - trade_times[prior] > MAX_PRE_AGE_SECONDS:
        return "stale_prior_trade"
    future = bisect_right(trade_times, play_time)
    if future >= len(trade_times) or trade_times[future] > play_time + HORIZON_SECONDS:
        return "recent_prior_no_post_trade"
    return "covered"


def read_bound_inputs(nflverse: Path, screen: Path, support_root: Path) -> tuple[dict, dict, list]:
    nflverse, screen, support_root = map(lambda p: Path(p).resolve(),
                                         (nflverse, screen, support_root))
    selection_path = screen / "selection_manifest.json"
    screen_path = screen / "manifest.json"
    support_path = support_root / "manifest.json"
    for path, expected in ((nflverse, EXPECTED_NFLVERSE),
                           (selection_path, EXPECTED_SELECTION_MANIFEST),
                           (screen_path, EXPECTED_SCREEN_MANIFEST),
                           (support_path, EXPECTED_SUPPORT_MANIFEST)):
        if sha(path) != expected:
            raise ValueError(f"frozen input changed: {path.name}")
    selection = json.loads(selection_path.read_text())
    screen_manifest = json.loads(screen_path.read_text())
    support = json.loads(support_path.read_text())
    games = selection.get("selections") or []
    if (len(games) != 12 or len({row["nflverse_game_id"] for row in games}) != 12
            or screen_manifest.get("completed_games") != 12
            or screen_manifest.get("selection_manifest_sha256") != EXPECTED_SELECTION_MANIFEST
            or support.get("schema") != "nfl_2024_pbp_trade_timing_support_v1"
            or support.get("train_admitted") is not False
            or support.get("scientific_score") is not False
            or support.get("historical_event_clock_only") is not True
            or support.get("nflverse_sha256") != EXPECTED_NFLVERSE
            or support.get("screen_manifest_sha256") != EXPECTED_SCREEN_MANIFEST
            or support.get("selection_manifest_sha256") != EXPECTED_SELECTION_MANIFEST
            or support.get("totals", {}).get("timed_typed_play_rows") != 2027
            or support.get("totals", {}).get("covered_60s") != 1400):
        raise ValueError("source or support receipt changed scope")
    per_game_path = support_root / "per_game.json"
    if sha(per_game_path) != support.get("per_game_sha256"):
        raise ValueError("prior per-game support changed")
    per_game = json.loads(per_game_path.read_text())
    if len(per_game) != 12:
        raise ValueError("prior support must contain 12 games")
    return screen_manifest, {row["game_id"]: row for row in per_game}, games


def diagnose(nflverse: Path, screen: Path, support_root: Path, output: Path) -> dict:
    screen_manifest, prior_support, selections = read_bound_inputs(nflverse, screen, support_root)
    receipts = {row["game_id"]: row for row in screen_manifest["receipts"]}
    if set(receipts) != set(prior_support):
        raise ValueError("screen and prior support games differ")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        lock = {
            "schema": "nfl_2024_60s_missingness_lock_v1",
            "source_role": "opened Train-source diagnostic; no new Train admission",
            "source_hashes": {
                "nflverse": EXPECTED_NFLVERSE,
                "screen_manifest": EXPECTED_SCREEN_MANIFEST,
                "selection_manifest": EXPECTED_SELECTION_MANIFEST,
                "prior_support_manifest": EXPECTED_SUPPORT_MANIFEST,
            },
            "diagnostic_source_sha256": sha(Path(__file__)),
            "games": 12, "expected_timed_typed_plays": 2027,
            "horizon_seconds": HORIZON_SECONDS,
            "max_pre_trade_age_seconds": MAX_PRE_AGE_SECONDS,
            "exclusive_reasons": list(REASONS),
            "no_missing_target_imputation": True,
            "route_dev_opened": False, "sealed_final_opened": False,
            "provider_cost_usd": "0", "model_fits": 0,
        }
        write_json(output / "pre_analysis_lock.json", lock)

        selected = {row["nflverse_game_id"] for row in selections}
        play_times: dict[str, list[int]] = defaultdict(list)
        play_ids: dict[str, set[str]] = defaultdict(set)
        with gzip.open(nflverse, "rt", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not {"game_id", "play_id", "play_type", "time_of_day"}.issubset(reader.fieldnames or ()):
                raise ValueError("nflverse source fields changed")
            for row in reader:
                game = row["game_id"]
                if game not in selected or not row["play_type"]:
                    continue
                if not row["play_id"] or row["play_id"] in play_ids[game]:
                    raise ValueError("missing or duplicate selected play ID")
                play_ids[game].add(row["play_id"])
                if row["time_of_day"]:
                    play_times[game].append(timestamp(row["time_of_day"]))

        by_game = []
        for selection in selections:
            game = selection["nflverse_game_id"]
            game_dir = Path(screen) / game
            trade_manifest_path = game_dir / "manifest.json"
            trade_path = game_dir / "trade_window.csv"
            if sha(trade_manifest_path) != receipts[game]["manifest_sha256"]:
                raise ValueError("game trade receipt changed")
            trade_manifest = json.loads(trade_manifest_path.read_text())
            if sha(trade_path) != trade_manifest["safe_trade_window_sha256"]:
                raise ValueError("game trade CSV changed")
            if json.loads((game_dir / "selection.json").read_text())["nflverse_game_id"] != game:
                raise ValueError("game selection changed")
            times = []
            with trade_path.open(newline="") as handle:
                for trade in csv.DictReader(handle):
                    if trade["asset"] not in selection["clob_token_ids"]:
                        raise ValueError("trade asset does not belong to selected market")
                    times.append(int(trade["timestamp"]))
            times.sort()
            counts = Counter(classify(play, times) for play in play_times[game])
            if (sum(counts.values()) != prior_support[game]["timed_typed_play_rows"]
                    or counts["covered"] != prior_support[game]["covered_60s"]
                    or len(times) != prior_support[game]["trade_rows"]):
                raise ValueError("missingness diagnosis fails prior support crosscheck")
            by_game.append({"game_id": game, "timed_typed_plays": len(play_times[game]),
                            "trade_rows": len(times),
                            "reasons": {reason: counts[reason] for reason in REASONS}})
        total = Counter()
        for row in by_game:
            total.update(row["reasons"])
        if sum(total.values()) != 2027 or total["covered"] != 1400:
            raise ValueError("overall missingness fails frozen 2024 support crosscheck")
        result = {
            "schema": "nfl_2024_60s_missingness_result_v1",
            "pre_analysis_lock_sha256": sha(output / "pre_analysis_lock.json"),
            "games": len(by_game), "timed_typed_plays": 2027,
            "reasons": {reason: total[reason] for reason in REASONS},
            "per_game": sorted(by_game, key=lambda row: row["game_id"]),
            "interpretation_boundary": "historical play event clock and trade timestamps only; no provider publish/local receive, model score, live lead or Train admission",
            "route_dev_opened": False, "sealed_final_opened": False,
            "provider_cost_usd": "0", "model_fits": 0,
        }
        write_json(output / "result.json", result)
        write_json(output / "manifest.json", {
            "schema": "nfl_2024_60s_missingness_manifest_v1",
            "complete": True, "pre_analysis_lock_sha256": sha(output / "pre_analysis_lock.json"),
            "result_sha256": sha(output / "result.json"),
            "route_dev_opened": False, "sealed_final_opened": False,
            "provider_cost_usd": "0", "model_fits": 0,
        })
        return result
    except Exception as error:
        write_json(output / "failure.json", {"schema": "nfl_2024_60s_missingness_failure_v1",
                                               "error_type": type(error).__name__,
                                               "error": str(error)[:1200],
                                               "route_dev_opened": False,
                                               "sealed_final_opened": False})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nflverse", type=Path, required=True)
    parser.add_argument("--screen", type=Path, required=True)
    parser.add_argument("--support-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = diagnose(args.nflverse, args.screen, args.support_root, args.output)
    print(json.dumps({"games": result["games"], "reasons": result["reasons"],
                      "route_dev_opened": False, "sealed_final_opened": False}, indent=2))


if __name__ == "__main__":
    main()
