"""Runner-only chronological split checks; no model calls or market scoring.

Input is an index of example metadata, NOT labels, model features or code.
This validates declared provenance/chronology; it cannot establish that the
collector's clocks, game mapping, replay or labels are correct. Therefore every
output is diagnostic-only and cannot authorize a scored/paid market trial.
The live-data materializer and independent provenance gate remain separate work.
"""
from __future__ import annotations

import argparse
import copy
import re
import secrets
from pathlib import Path

from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json


DAY_MS = 86400000
SPLITS = ("train", "dev", "test")
INDEX_KEYS = {"schema", "evidence_class", "source_sha256", "market_games",
              "horizon_ms", "latency_ms", "max_label_lateness_ms", "rows", "tasks"}
ROW_KEYS = {"row_id", "game_id", "market_id", "decision_ms", "feature_available_ms",
            "label_end_ms", "label_available_ms", "input_source", "label_source"}


def sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("SHA-256 source commitment required")
    return value


def integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("integer milliseconds/ordinals required")
    return value


def fields(value, expected):
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("unexpected or missing metadata fields")


def source_key(value, sources):
    fields(value, {"sha256", "ordinal"})
    if sha(value["sha256"]) not in sources:
        raise ValueError("source not in frozen index")
    return value["sha256"], integer(value["ordinal"])


def summarize(rows):
    return {"rows": len(rows), "games": len({r["game_id"] for r in rows}),
            "first_decision_ms": min(r["decision_ms"] for r in rows),
            "last_decision_ms": max(r["decision_ms"] for r in rows),
            "last_label_available_ms": max(r["label_available_ms"] for r in rows),
            "utc_days": sorted({r["decision_ms"] // DAY_MS for r in rows})}


def validate_index(index):
    """Validate one immutable, outcome-free index of independently grouped tasks.

    Distinct tasks in this first diagnostic suite have disjoint game groups.
    This does not constrain a researcher's downstream selection/augmentation of
    its assigned Train examples. Task/date choices must be made before scores.
    """
    fields(index, INDEX_KEYS)
    if index["schema"] != "market_split_index_v1":
        raise ValueError("unknown split index schema")
    if index["evidence_class"] not in {"fixture", "diagnostic"}:
        raise ValueError("verified live-source gate is not implemented")
    sources = index["source_sha256"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("source commitments required")
    for source in sources:
        sha(source)
    if len(set(sources)) != len(sources):
        raise ValueError("duplicate source commitment")
    market_games = index["market_games"]
    if not isinstance(market_games, dict) or not market_games:
        raise ValueError("runner market-to-game mapping required")
    for market, game in market_games.items():
        identifier(market)
        identifier(game)
    horizon = integer(index["horizon_ms"], 1)
    latency = integer(index["latency_ms"])
    lateness = integer(index["max_label_lateness_ms"])
    rows = index["rows"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("nonempty example index required")
    by_game, row_ids, observations, last_decisions = {}, set(), set(), {}
    for row in rows:
        fields(row, ROW_KEYS)
        for key in ("row_id", "game_id", "market_id"):
            identifier(row[key])
        if row["row_id"] in row_ids:
            raise ValueError("duplicate row ID")
        row_ids.add(row["row_id"])
        if market_games.get(row["market_id"]) != row["game_id"]:
            raise ValueError("market relabeled as another game")
        t, available, end, label_available = [integer(row[key]) for key in
            ("decision_ms", "feature_available_ms", "label_end_ms", "label_available_ms")]
        expected_end = t + latency + horizon
        if available > t:
            raise ValueError("feature arrives after decision")
        if not expected_end <= end <= expected_end + lateness:
            raise ValueError("label horizon/lateness mismatch")
        if label_available < end:
            raise ValueError("label unavailable at declared time")
        input_key = source_key(row["input_source"], sources)
        label_key = source_key(row["label_source"], sources)
        if input_key == label_key:
            raise ValueError("same observation used as input and future label")
        observation = row["market_id"], t, input_key
        if observation in observations:
            raise ValueError("duplicate indexed observation")
        observations.add(observation)
        market = row["market_id"]
        if t < last_decisions.get(market, t):
            raise ValueError("out-of-order decision stream")
        last_decisions[market] = t
        by_game.setdefault(row["game_id"], []).append(row)
    tasks = index["tasks"]
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("task assignments required")
    assigned, task_ids, seen_transfer, previous = set(), set(), False, None
    validated = []
    for task in tasks:
        fields(task, {"task_id", "phase", "splits"})
        identifier(task["task_id"])
        if task["task_id"] in task_ids:
            raise ValueError("duplicate task ID")
        task_ids.add(task["task_id"])
        if task["phase"] not in {"learning", "transfer"}:
            raise ValueError("unknown task phase")
        if seen_transfer and task["phase"] != "transfer":
            raise ValueError("learning task follows transfer")
        seen_transfer |= task["phase"] == "transfer"
        fields(task["splits"], set(SPLITS))
        parts, summaries = {}, {}
        for split in SPLITS:
            games = task["splits"][split]
            if not isinstance(games, list) or not games:
                raise ValueError("each split needs whole games")
            for game in games:
                identifier(game)
            if len(set(games)) != len(games) or assigned.intersection(games):
                raise ValueError("game reused across splits/tasks")
            if not set(games) <= set(by_game):
                raise ValueError("assigned game has no observations")
            assigned.update(games)
            parts[split] = [r for game in games for r in by_game[game]]
            summaries[split] = summarize(parts[split])
        for earlier, later in zip(SPLITS, SPLITS[1:]):
            a, b = summaries[earlier], summaries[later]
            if a["last_label_available_ms"] >= b["first_decision_ms"]:
                raise ValueError("label availability crosses split boundary")
            if max(a["utc_days"]) >= min(b["utc_days"]):
                raise ValueError("split must use strictly earlier UTC dates")
        if previous is not None:
            if previous["last_label_available_ms"] >= summaries["train"]["first_decision_ms"]:
                raise ValueError("research tasks not chronological")
            if max(previous["utc_days"]) >= min(summaries["train"]["utc_days"]):
                raise ValueError("research tasks share a UTC date")
        previous = summaries["test"]
        validated.append({"task_id": task["task_id"], "phase": task["phase"],
                          "summaries": summaries, "rows": parts})
    if assigned != set(by_game):
        raise ValueError("unassigned games cannot silently disappear")
    canonical(index)  # Reject nonfinite JSON and unserializable metadata.
    return validated


def freeze_diagnostic_index(source_path, output):
    """Persist once; retain a permanent claim if a later write/check fails.

    The public projection contains only Train/Dev metadata plus a salted Test
    commitment. It is not model input until the real worker enforces file access.
    Never mount the runner file or this whole output directory into a candidate.
    """
    source_path, output = Path(source_path), Path(output)
    before = file_hash(source_path)
    index = load_json(source_path)
    validated = validate_index(index)
    if file_hash(source_path) != before:
        raise ValueError("split index changed during validation")
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    fresh_json(output / "claim.json", {"source_index_sha256": before,
               "code_sha256": file_hash(__file__), "evidence_class": index["evidence_class"],
               "scoring_ready": False})
    runner = {"index": copy.deepcopy(index), "test_commitment_nonces": {}}
    public = {"schema": "market_split_public_v1", "evidence_class": index["evidence_class"],
              "scoring_ready": False, "tasks": []}
    for task in validated:
        nonce = secrets.token_hex(32)
        runner["test_commitment_nonces"][task["task_id"]] = nonce
        public["tasks"].append({"task_id": task["task_id"], "phase": task["phase"],
            "train_rows": task["rows"]["train"], "dev_rows": task["rows"]["dev"],
            "train_summary": task["summaries"]["train"],
            "dev_summary": task["summaries"]["dev"],
            "test_commitment": digest({"nonce": nonce, "rows": task["rows"]["test"]})})
    fresh_json(output / "runner-only.json", runner)
    fresh_json(output / "public-train-dev.json", public)
    if file_hash(source_path) != before:
        raise ValueError("split index changed while freezing; no complete receipt")
    receipt = {"structural_checks_pass": True, "scoring_ready": False,
        "research_result": False, "source_index_sha256": before,
        "runner_sha256": file_hash(output / "runner-only.json"),
        "public_sha256": file_hash(output / "public-train-dev.json"),
        "remaining_gates": ["collector_clock_and_session_provenance", "raw_replay_and_game_mapping",
                            "actual_label_materializer", "isolated_research_worker"]}
    fresh_json(output / "complete.json", receipt)
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source_index", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    print(canonical(freeze_diagnostic_index(args.source_index, args.output)))
