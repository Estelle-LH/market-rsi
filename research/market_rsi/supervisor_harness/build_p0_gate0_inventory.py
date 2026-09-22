"""Gate 0: derive conservative exposure inventory from metadata receipts only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_inventory(mapping: list[dict], audit: dict, *, proven_open_game: str) -> dict:
    ordered = sorted(mapping, key=lambda row: (row["game_date"], row["game_id"]))
    if len(ordered) != 285 or len({row["game_id"] for row in ordered}) != 285:
        raise ValueError("2025 mapping must contain 285 unique games")
    counts = audit["role_game_counts"]
    if counts != {"market_train": 195, "route_dev": 50, "sealed_final": 40}:
        raise ValueError("frozen role counts changed")
    rows = []
    for index, game in enumerate(ordered):
        role = "market_train" if index < 195 else "route_dev" if index < 245 else "sealed_final"
        rows.append({"game_id": game["game_id"], "game_date": game["game_date"],
                     "role": role, "exposure": "opened" if game["game_id"] == proven_open_game else "unknown",
                     "evidence": "one-game trade canary" if game["game_id"] == proven_open_game
                     else "no complete per-game access receipt"})
    if sum(row["exposure"] == "opened" for row in rows) != 1 or rows[0]["game_id"] != proven_open_game:
        raise ValueError("proven canary game does not match frozen first Train game")
    for role, expected in audit["role_distinct_date_counts"].items():
        observed = len({row["game_date"] for row in rows if row["role"] == role})
        if observed != expected:
            raise ValueError(f"{role}: role-date count differs from frozen audit")
    return {"schema": "market_p0_exposure_ledger_v1", "rows": rows,
            "policy_exposure": {"train_opened_documented_aggregate": 163,
                                "dev_scored_documented_aggregate": 50,
                                "identities_reconstructed": False},
            "per_game_counts": {"opened": 1, "verified_not_opened": 0, "unknown": 284},
            "formal_final_admitted": False}


def run(repo: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError("Gate 0 requires a fresh output ID")
    source_names = {
        "role_date_audit": "artifacts/p0-2025-schedule-role-date-audit-20260917-01/date-audit.json",
        "mapping": "artifacts/p0-polymarket-2025-schedule-screen-20260916-03/mapping.json",
        "trade_manifest": "artifacts/p0-polymarket-2025-trade-canary-20260916-01/manifest.json",
        "prior_audit": "research/market_rsi/supervisor_harness/AGENT_LOG_DATA_ADMISSION_2026-09-18.md",
    }
    paths = {key: repo / value for key, value in source_names.items()}
    hashes = {key: sha(path) for key, path in paths.items()}
    audit = json.loads(paths["role_date_audit"].read_text())
    mapping = json.loads(paths["mapping"].read_text())
    trade = json.loads(paths["trade_manifest"].read_text())
    if audit["actual_access_history_complete"] or audit["untouched_final_admitted"]:
        raise ValueError("source audit's exposure claim changed")
    if trade["window_summary"]["trades"] != 2148 or trade["formal_data_admitted"]:
        raise ValueError("one-game canary source changed")
    ledger = make_inventory(mapping, audit, proven_open_game="2025_01_DAL_PHI")
    baseline = {"schema": "market_p0_gate0_baseline_v1", "source_paths": source_names,
                "source_sha256": hashes, "data_roles": audit["role_game_counts"],
                "role_date_counts": audit["role_distinct_date_counts"],
                "new_raw_market_or_sealed_values_read": False, "provider_cost_usd": "0"}
    missing = {"schema": "market_p0_missing_receipts_v1",
               "missing": ["complete original per-game Train access ledger",
                           "original 50-game Dev scoring access receipts",
                           "independent never-opened proof for 40-game Final",
                           "at least 20 untouched dates in a same-mechanism Final block"],
               "cloud_archive_retrieval_attempted": False}
    verdict = {"schema": "market_p0_gate0_verdict_v1", "metadata_inventory_passed": True,
               "2025_formal_final_admitted": False,
               "reason": "All unknown access remains unknown; old Final has 11 dates, not 20.",
               "next_gate": "bounded public-source research; no paid fit or sealed read"}
    output.mkdir(parents=True)
    for name, value in (("admission-baseline.json", baseline), ("exposure-ledger.json", ledger),
                        ("missing-receipts.json", missing), ("gate0-verdict.json", verdict)):
        (output / name).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    if {key: sha(path) for key, path in paths.items()} != hashes:
        raise ValueError("source receipt changed during inventory")
    return verdict


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.repo.resolve(), args.output.resolve()), sort_keys=True))
