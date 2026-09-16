"""Materialize researcher-selected NFL targets on opened Train only.

The runner executes a frozen typed target spec.  It never evaluates a model,
selects a winning target, filters rows by realized outcomes, or reads
Route-Dev/Final.  Historical trade prints are labels, not BBO/fill evidence.
"""
from __future__ import annotations

import argparse
import bisect
from collections import defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np

from data_scientist_harness.target_discovery_contract import (
    verify_frozen_target_discovery_spec,
)
from market_rsi import digest, file_hash, fresh_json, load_json
from sports_event_research.build_play_trade_canary import (
    home_trade_series,
    last_observation,
)


def elapsed_endpoint(times: list[int], prices: list[float], decision: int,
                     horizon: int) -> tuple[int, float] | None:
    observation = last_observation(times, prices, decision + horizon, horizon)
    if observation is None or observation[0] <= decision:
        return None
    return observation


def event_endpoint(times: list[int], prices: list[float], decision: int,
                   trade_count: int, max_wall_seconds: int) -> tuple[int, float] | None:
    index = bisect.bisect_right(times, decision) + trade_count - 1
    if index >= len(times) or times[index] > decision + max_wall_seconds:
        return None
    return times[index], prices[index]


def transform_value(delta: float, transform: str, deadband_bps: int) -> float | int:
    if transform == "price_delta":
        return float(delta)
    deadband = deadband_bps / 10000.0
    return 1 if delta > deadband else (-1 if delta < -deadband else 0)


def target_names(spec: dict) -> list[tuple[str, str, int]]:
    suffix = "delta" if spec["target_transform"] == "price_delta" else "direction"
    return [
        *( (f"elapsed_{value}s_{suffix}", "elapsed", value)
           for value in spec["elapsed_horizons_seconds"] ),
        *( (f"event_{value}trades_{suffix}", "event", value)
           for value in spec["event_horizons_trade_count"] ),
    ]


def materialize_rows(play_rows: list[dict], trade_times: list[int], trade_prices: list[float],
                     spec: dict) -> tuple[list[dict], dict]:
    if len(trade_times) != len(trade_prices) or trade_times != sorted(trade_times):
        raise ValueError("ordered trade time/price series required")
    names = target_names(spec)
    output = []
    counts = {name: 0 for name, _, _ in names}
    values: dict[str, list[float]] = defaultdict(list)
    gaps: dict[str, list[int]] = defaultdict(list)
    common = 0
    for raw in play_rows:
        if "play_id" not in raw or "play_timestamp" not in raw:
            raise ValueError("play row lacks id or decision time")
        decision = int(raw["play_timestamp"])
        base = last_observation(
            trade_times, trade_prices, decision, spec["pre_price_max_age_seconds"]
        )
        row = {
            "play_id": raw["play_id"], "decision_time": decision,
            "pre_price": "" if base is None else base[1],
            "pre_price_time": "" if base is None else base[0],
        }
        available = []
        for name, kind, value in names:
            endpoint = None
            if base is not None and kind == "elapsed":
                endpoint = elapsed_endpoint(trade_times, trade_prices, decision, value)
                deadline = decision + value
            elif base is not None:
                endpoint = event_endpoint(
                    trade_times, trade_prices, decision, value,
                    spec["max_event_target_wall_seconds"],
                )
                deadline = decision + spec["max_event_target_wall_seconds"]
            else:
                deadline = (decision + value if kind == "elapsed"
                            else decision + spec["max_event_target_wall_seconds"])
            if endpoint is None:
                row[name] = row[name + "_trade_time"] = ""
                row[name + "_deadline_time"] = deadline
                available.append(False)
                continue
            if not decision < endpoint[0] <= deadline:
                raise ValueError("target endpoint violates frozen clock order")
            delta = endpoint[1] - base[1]
            target = transform_value(delta, spec["target_transform"],
                                     spec["direction_deadband_bps"])
            row[name] = target
            row[name + "_trade_time"] = endpoint[0]
            row[name + "_deadline_time"] = deadline
            counts[name] += 1
            values[name].append(float(target))
            gaps[name].append(endpoint[0] - decision)
            available.append(True)
        row["eligible_for_common_comparison"] = int(all(available))
        common += int(all(available))
        output.append(row)
    summary = {
        "plays": len(output),
        "common_support_rows": common,
        "common_support_fraction": common / len(output) if output else 0.0,
        "targets": {},
    }
    for name, _, _ in names:
        observed = values[name]
        summary["targets"][name] = {
            "eligible_rows": counts[name],
            "coverage": counts[name] / len(output) if output else 0.0,
            "mean": float(np.mean(observed)) if observed else None,
            "mean_absolute_value": float(np.mean(np.abs(observed))) if observed else None,
            "standard_deviation": float(np.std(observed)) if observed else None,
            "exact_zero_fraction": float(np.mean(np.asarray(observed) == 0)) if observed else None,
            "decision_to_label_trade_seconds": {
                "min": min(gaps[name]) if gaps[name] else None,
                "max": max(gaps[name]) if gaps[name] else None,
            },
        }
    return output, summary


def verify_sources(receipt_path: Path, panel_root: Path, selection_root: Path,
                   expected_sha: str) -> list[dict]:
    if file_hash(receipt_path) != expected_sha:
        raise ValueError("source receipt changed after target-spec freeze")
    receipt = load_json(receipt_path)
    games = receipt.get("games")
    if receipt.get("schema") != "nfl_train_local_projection_inputs_v1" or not isinstance(games, list):
        raise ValueError("known 163-game Train source receipt required")
    if len(games) != 163 or len({row.get("game") for row in games}) != 163:
        raise ValueError("exact 163-game Train source inventory required")
    checked = []
    for row in games:
        game = row["game"]
        panel = Path(panel_root) / game / "play_trade_alignment.csv"
        manifest = Path(panel_root) / game / "manifest.json"
        selection = Path(selection_root) / f"{game}.selection.json"
        if (file_hash(panel) != row["panel_sha256"]
                or file_hash(manifest) != row["alignment_manifest_sha256"]
                or file_hash(selection) != row["selection_sha256"]):
            raise ValueError(f"source hash mismatch for {game}")
        selected = load_json(selection)
        aligned = load_json(manifest)
        if (selected.get("split_role") != "market_train"
                or selected.get("price_history_opened") is not False
                or selected.get("trades_opened") is not False
                or aligned.get("scientific_score") is not False
                or aligned.get("selection_sha256") != row["selection_sha256"]):
            raise ValueError("non-Train or modified source receipt")
        pbp = Path(aligned["pbp_path"])
        trades = Path(aligned["trades_path"])
        if file_hash(pbp) != aligned["pbp_sha256"] or file_hash(trades) != aligned["trades_sha256"]:
            raise ValueError(f"raw source hash mismatch for {game}")
        checked.append({
            "game": game, "scheduled_utc": row["scheduled_utc"],
            "panel": panel, "panel_sha256": row["panel_sha256"],
            "manifest": manifest, "manifest_sha256": row["alignment_manifest_sha256"],
            "selection": selection, "selection_sha256": row["selection_sha256"],
            "pbp": pbp, "pbp_sha256": aligned["pbp_sha256"],
            "trades": trades, "trades_sha256": aligned["trades_sha256"],
        })
    checked.sort(key=lambda row: (row["scheduled_utc"], row["game"]))
    return checked


def run(spec_path: Path, source_receipt: Path, panel_root: Path,
        selection_root: Path, output: Path) -> dict:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        frozen = load_json(spec_path)
        spec = verify_frozen_target_discovery_spec(frozen)
        sources = verify_sources(source_receipt, panel_root, selection_root,
                                 spec["source_receipt_sha256"])
        names = target_names(spec)
        combined = []
        game_summaries = []
        evidence = []
        for source in sources:
            trade_times, trade_prices = home_trade_series(source["trades"], load_json(source["selection"]))
            with source["panel"].open(newline="") as stream:
                play_rows = list(csv.DictReader(stream))
            rows, summary = materialize_rows(play_rows, trade_times, trade_prices, spec)
            for row in rows:
                row.update(game=source["game"], scheduled_utc=source["scheduled_utc"])
                combined.append(row)
            game_summaries.append({"game": source["game"], **summary})
            evidence.append({key: (str(value.resolve()) if isinstance(value, Path) else value)
                             for key, value in source.items()})
        if len({(row["game"], row["play_id"]) for row in combined}) != len(combined):
            raise ValueError("duplicate target row")
        fields = ["game", "scheduled_utc", "play_id", "decision_time", "pre_price",
                  "pre_price_time"]
        for name, _, _ in names:
            fields.extend((name, name + "_trade_time", name + "_deadline_time"))
        fields.append("eligible_for_common_comparison")
        panel = output / "target_panel.csv"
        with panel.open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader(); writer.writerows(combined)
        aggregate = {
            "schema": "controller_target_materialization_summary_v1",
            "frozen_target_spec_sha256": frozen["record_sha256"],
            "target_spec_file_sha256": file_hash(spec_path),
            "materializer_source_sha256": file_hash(Path(__file__)),
            "games": len(sources), "plays": len(combined),
            "comparison_support": spec["comparison_support"],
            "common_support_rows": sum(row["eligible_for_common_comparison"] for row in combined),
            "targets": {}, "game_summaries": game_summaries,
            "route_dev_opened": False, "sealed_final_opened": False,
            "scientific_score": False, "provider_cost_usd": "0",
            "historical_provider_and_exchange_timestamps_are_live_arrival_proof": False,
            "historical_trade_print_is_bbo_or_fill_evidence": False,
        }
        for name, _, _ in names:
            observed = [float(row[name]) for row in combined if row[name] != ""]
            aggregate["targets"][name] = {
                "eligible_rows": len(observed), "coverage": len(observed) / len(combined),
                "mean": float(np.mean(observed)) if observed else None,
                "mean_absolute_value": float(np.mean(np.abs(observed))) if observed else None,
                "standard_deviation": float(np.std(observed)) if observed else None,
                "exact_zero_fraction": float(np.mean(np.asarray(observed) == 0)) if observed else None,
            }
        fresh_json(output / "input_receipts.json", {
            "schema": "controller_target_materialization_inputs_v1",
            "source_receipt_path": str(Path(source_receipt).resolve()),
            "source_receipt_sha256": file_hash(source_receipt), "games": evidence,
        })
        aggregate["target_panel_sha256"] = file_hash(panel)
        aggregate["input_receipts_sha256"] = file_hash(output / "input_receipts.json")
        fresh_json(output / "summary.json", aggregate)
        manifest = {
            "schema": "controller_target_materialization_manifest_v1", "complete": True,
            "frozen_target_spec_sha256": frozen["record_sha256"],
            "target_spec_file_sha256": file_hash(spec_path),
            "materializer_source_sha256": file_hash(Path(__file__)),
            "target_panel_sha256": file_hash(panel),
            "summary_sha256": file_hash(output / "summary.json"),
            "input_receipts_sha256": file_hash(output / "input_receipts.json"),
            "route_dev_opened": False, "sealed_final_opened": False,
            "scientific_score": False, "provider_cost_usd": "0",
        }
        fresh_json(output / "manifest.json", manifest)
        return aggregate
    except Exception as error:
        fresh_json(output / "failure.json", {
            "error_type": type(error).__name__, "error": str(error)[:2000],
            "automatic_retry": False, "route_dev_opened": False,
            "sealed_final_opened": False, "provider_cost_usd": "0",
        })
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--source-receipt", type=Path, required=True)
    parser.add_argument("--panel-root", type=Path, required=True)
    parser.add_argument("--selection-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.spec, args.source_receipt, args.panel_root, args.selection_root, args.output)
    print(json.dumps({
        "games": result["games"], "plays": result["plays"],
        "common_support_rows": result["common_support_rows"],
        "targets": result["targets"], "provider_cost_usd": result["provider_cost_usd"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
