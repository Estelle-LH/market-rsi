"""Audit historical 60/300-second trade-label support for all 2024 NFL candidates.

This does not admit Train, score a prediction, or prove provider/live receipt
timing. Every mapped game remains in the denominator, including quiet games.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path
from statistics import median

from data_scientist_harness import VERSION
from data_scientist_harness.release import source_hashes, verify_git_publication
from market_rsi import digest
from sports_event_research.audit_2024_pbp_trade_support import timestamp


EXPECTED_NFLVERSE = "23370d5d10f8104d80d46a1fc5e61f4f6f5a3263fe96fe2dd629913cfcb08c06"
EXPECTED_COHORT_PLAN = "e06e112f057d5b1f1749f668c2a9f2ceabcee662464da521335e1b8aba1987c2"
GAMES = 284
BATCHES = 12
MAX_PRE_AGE = 300
HORIZONS = (60, 300)
REASONS = ("no_prior_trade", "stale_prior_trade", "no_new_trade", "covered")


def sha(path: Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def reason(play: int, trades: list[int], horizon: int) -> str:
    prior = bisect_right(trades, play) - 1
    if prior < 0:
        return "no_prior_trade"
    if play - trades[prior] > MAX_PRE_AGE:
        return "stale_prior_trade"
    post = bisect_right(trades, play)
    if post >= len(trades) or trades[post] > play + horizon:
        return "no_new_trade"
    return "covered"


def published_release(path: Path) -> dict:
    path = Path(path).resolve()
    value = json.loads(path.read_text())
    publication = value.get("publication") or {}
    sources = source_hashes()
    tag = "dsh-v" + VERSION.rsplit("-v", 1)[1]
    if (value.get("schema") != "data_scientist_release_v1"
            or value.get("harness_version") != VERSION
            or value.get("source_hashes") != sources
            or value.get("release_sha256") != digest({k: v for k, v in value.items() if k != "release_sha256"})
            or publication.get("tag") != tag):
        raise ValueError("exact published audit source required")
    checked = verify_git_publication(sources, commit=publication.get("commit"))
    if any(checked[key] != publication[key] for key in ("tag", "commit", "tag_object", "tree")):
        raise ValueError("published audit source differs")
    return {"path": str(path), "file_sha256": sha(path),
            "release_sha256": value["release_sha256"], "commit": publication["commit"]}


def verify_batches(plan_path: Path, batch_roots: list[Path]) -> tuple[list[dict], dict, dict]:
    plan_path = Path(plan_path).resolve()
    if sha(plan_path) != EXPECTED_COHORT_PLAN:
        raise ValueError("frozen full-cohort plan changed")
    plan = json.loads(plan_path.read_text())
    selections = plan.get("selections")
    if (plan.get("schema") != "polymarket_2024_full_train_source_plan_v1"
            or plan.get("planned_games") != GAMES or plan.get("batch_count") != BATCHES
            or plan.get("batch_size") != 24 or not isinstance(selections, list)
            or len(selections) != GAMES
            or len({row["nflverse_game_id"] for row in selections}) != GAMES
            or plan.get("train_admitted") is not False):
        raise ValueError("full-cohort plan scope changed")
    if len(batch_roots) != BATCHES:
        raise ValueError("all fixed batches required")
    indexed = {}
    manifest_hashes = {}
    for raw_root in batch_roots:
        root = Path(raw_root).resolve()
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        index = manifest.get("batch_index")
        if index in indexed or not isinstance(index, int) or not 0 <= index < BATCHES:
            raise ValueError("batch index duplicate or invalid")
        chosen = selections[index * 24:(index + 1) * 24]
        ids = [row["nflverse_game_id"] for row in chosen]
        receipts = manifest.get("receipts")
        lock_path = root / "pre_fetch_lock.json"
        lock = json.loads(lock_path.read_text())
        if (manifest.get("schema") != "polymarket_2024_full_train_source_batch_manifest_v1"
                or lock.get("schema") != "polymarket_2024_full_train_source_batch_lock_v1"
                or manifest.get("complete") is not True
                or manifest.get("planned_games") != len(chosen)
                or manifest.get("completed_games") != len(chosen)
                or manifest.get("automatic_retries") != 0
                or manifest.get("train_admitted") is not False
                or manifest.get("route_dev_opened") is not False
                or manifest.get("sealed_final_opened") is not False
                or manifest.get("cohort_plan_sha256") != EXPECTED_COHORT_PLAN
                or manifest.get("pre_fetch_lock_sha256") != sha(lock_path)
                or lock.get("cohort_plan_sha256") != EXPECTED_COHORT_PLAN
                or lock.get("planned_games") != ids
                or not isinstance(receipts, list)
                or [row["game_id"] for row in receipts] != ids):
            raise ValueError("batch does not reproduce frozen cohort order")
        indexed[index] = (root, manifest)
        manifest_hashes[str(index)] = sha(manifest_path)
    if set(indexed) != set(range(BATCHES)):
        raise ValueError("batch index missing")
    return selections, indexed, manifest_hashes


def audit(nflverse: Path, plan_path: Path, batch_roots: list[Path],
          release: Path, output: Path) -> dict:
    nflverse = Path(nflverse).resolve()
    if sha(nflverse) != EXPECTED_NFLVERSE:
        raise ValueError("2024 PBP source changed")
    proof = published_release(release)
    selections, indexed, batch_hashes = verify_batches(plan_path, batch_roots)
    plan = json.loads(Path(plan_path).read_text())
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("audit output exists; use fresh ID")
    output.mkdir(parents=True, exist_ok=False)
    try:
        lock = {"schema": "nfl_2024_full_cohort_support_lock_v1",
                "release": proof, "cohort_plan_sha256": EXPECTED_COHORT_PLAN,
                "nflverse_sha256": EXPECTED_NFLVERSE, "batch_manifest_sha256": batch_hashes,
                "mapped_games": GAMES, "horizons_seconds": list(HORIZONS),
                "max_pre_trade_age_seconds": MAX_PRE_AGE,
                "denominator": "all timed, typed PBP plays in all 284 mapped games; quiet games retained",
                "no_missing_target_imputation": True,
                "route_dev_opened": False, "sealed_final_opened": False,
                "train_admitted": False, "model_fits": 0, "provider_cost_usd": "0"}
        write_json(output / "pre_analysis_lock.json", lock)

        selected = {row["nflverse_game_id"] for row in selections}
        play_times = defaultdict(list)
        typed = Counter()
        missing_time = Counter()
        play_ids = defaultdict(set)
        with gzip.open(nflverse, "rt", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not {"game_id", "play_id", "play_type", "time_of_day"}.issubset(reader.fieldnames or ()):
                raise ValueError("frozen PBP schema changed")
            for row in reader:
                game = row["game_id"]
                if game not in selected or not row["play_type"]:
                    continue
                typed[game] += 1
                play_id = row["play_id"]
                if not play_id or play_id in play_ids[game]:
                    raise ValueError("duplicate or missing typed play ID")
                play_ids[game].add(play_id)
                if row["time_of_day"]:
                    play_times[game].append(timestamp(row["time_of_day"]))
                else:
                    missing_time[game] += 1

        by_game = []
        for index in range(BATCHES):
            root, manifest = indexed[index]
            for selection, receipt in zip(selections[index * 24:(index + 1) * 24],
                                          manifest["receipts"]):
                game = selection["nflverse_game_id"]
                game_root = root / game
                game_manifest_path = game_root / "manifest.json"
                if sha(game_manifest_path) != receipt["manifest_sha256"]:
                    raise ValueError("game receipt changed")
                game_manifest = json.loads(game_manifest_path.read_text())
                if (game_manifest.get("schema") != "polymarket_2024_nfl_trade_canary_manifest_v1"
                        or json.loads((game_root / "selection.json").read_text()) != selection
                        or sha(game_root / "selection.json") != game_manifest["selection_sha256"]
                        or game_manifest["mapping_sha256"] != plan["mapping_sha256"]
                        or game_manifest.get("train_admitted") is not False):
                    raise ValueError("game selection or source mapping changed")
                trade_path = game_root / "trade_window.csv"
                if sha(trade_path) != game_manifest["safe_trade_window_sha256"]:
                    raise ValueError("safe trade file changed")
                times = []
                with trade_path.open(newline="") as handle:
                    for trade in csv.DictReader(handle):
                        if trade["asset"] not in selection["clob_token_ids"]:
                            raise ValueError("trade token does not match mapped outcomes")
                        times.append(int(trade["timestamp"]))
                times.sort()
                if len(times) != receipt["trade_rows"]:
                    raise ValueError("game trade count differs from receipt")
                horizon_counts = {str(h): Counter(reason(play, times, h)
                                  for play in play_times[game]) for h in HORIZONS}
                by_game.append({"game_id": game, "event_start_utc": selection["event_start_utc"],
                    "typed_plays": typed[game], "timed_typed_plays": len(play_times[game]),
                    "typed_plays_missing_time": missing_time[game],
                    "trade_rows": len(times),
                    "reasons_by_horizon": {str(h): {name: horizon_counts[str(h)][name]
                        for name in REASONS} for h in HORIZONS}})
        if len(by_game) != GAMES or any(not row["typed_plays"] for row in by_game):
            raise ValueError("mapped game missing typed PBP plays")
        total = {str(h): {name: sum(row["reasons_by_horizon"][str(h)][name]
                      for row in by_game) for name in REASONS} for h in HORIZONS}
        denominators = sum(row["timed_typed_plays"] for row in by_game)
        if any(sum(total[str(h)].values()) != denominators for h in HORIZONS):
            raise ValueError("coverage does not reconcile to denominator")
        write_json(output / "per_game.json", by_game)
        result = {"schema": "nfl_2024_full_cohort_support_result_v1",
            "pre_analysis_lock_sha256": sha(output / "pre_analysis_lock.json"),
            "games": len(by_game), "games_with_trades": sum(row["trade_rows"] > 0 for row in by_game),
            "trade_rows": sum(row["trade_rows"] for row in by_game),
            "typed_plays": sum(row["typed_plays"] for row in by_game),
            "timed_typed_plays": denominators,
            "typed_plays_missing_time": sum(row["typed_plays_missing_time"] for row in by_game),
            "reasons_by_horizon": total,
            "coverage_by_horizon": {str(h): total[str(h)]["covered"] / denominators
                                    for h in HORIZONS},
            "median_game_coverage_by_horizon": {str(h): median(
                row["reasons_by_horizon"][str(h)]["covered"] / row["timed_typed_plays"]
                for row in by_game if row["timed_typed_plays"]) for h in HORIZONS},
            "per_game_sha256": sha(output / "per_game.json"),
            "interpretation_boundary": "historical event-clock/trade-print support only; not provider publish/local receive, model score, Train admission or tradable edge",
            "route_dev_opened": False, "sealed_final_opened": False,
            "train_admitted": False, "model_fits": 0, "provider_cost_usd": "0"}
        write_json(output / "result.json", result)
        write_json(output / "manifest.json", {
            "schema": "nfl_2024_full_cohort_support_manifest_v1", "complete": True,
            "pre_analysis_lock_sha256": sha(output / "pre_analysis_lock.json"),
            "per_game_sha256": sha(output / "per_game.json"),
            "result_sha256": sha(output / "result.json"),
            "route_dev_opened": False, "sealed_final_opened": False,
            "train_admitted": False, "model_fits": 0, "provider_cost_usd": "0"})
        return result
    except Exception as error:
        write_json(output / "failure.json", {
            "schema": "nfl_2024_full_cohort_support_failure_v1",
            "error_type": type(error).__name__, "error": str(error)[:1200],
            "route_dev_opened": False, "sealed_final_opened": False,
            "train_admitted": False})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nflverse", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--batch", type=Path, nargs="+", required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.nflverse, args.plan, args.batch, args.release, args.output)
    print(json.dumps({"games": result["games"],
                      "timed_typed_plays": result["timed_typed_plays"],
                      "coverage_by_horizon": result["coverage_by_horizon"],
                      "model_fits": 0, "provider_cost_usd": "0"}, indent=2))


if __name__ == "__main__":
    main()
