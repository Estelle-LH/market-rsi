"""Freeze a source-only 2023 game sample before reading any additional fills.

This is a diagnostic acquisition plan, never a training subset or a held-out
model evaluation. Missing market identities remain in the season denominator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from supervisor_harness.screen_2023_archive_catalog import encoded, sha


SEED = "market-p0-2023-density-audit-v1"
WEEK = re.compile(r"^2023_(\d{2})_[A-Z]+_[A-Z]+$")
STRATA = ((1, 6, "weeks_01_06"), (7, 12, "weeks_07_12"),
          (13, 18, "weeks_13_18"), (19, 22, "weeks_19_22"))
PER_STRATUM = 3


def stratum(game_id: str) -> str:
    match = WEEK.fullmatch(game_id)
    if not match:
        raise ValueError(f"invalid 2023 game ID: {game_id!r}")
    week = int(match.group(1))
    for lower, upper, name in STRATA:
        if lower <= week <= upper:
            return name
    raise ValueError(f"week outside season: {week}")


def sample(mapping: list[dict], unmatched: list[str]) -> dict:
    ids = [row["game_id"] for row in mapping]
    if len(ids) != len(set(ids)) or len(unmatched) != len(set(unmatched)):
        raise ValueError("duplicate game ID")
    if set(ids) & set(unmatched):
        raise ValueError("mapped and unmatched overlap")
    by_stratum: dict[str, list[dict]] = {name: [] for _, _, name in STRATA}
    missing: dict[str, int] = {name: 0 for _, _, name in STRATA}
    for row in mapping:
        by_stratum[stratum(row["game_id"])].append(row)
    for game_id in unmatched:
        missing[stratum(game_id)] += 1
    selection = []
    summary = []
    for _, _, name in STRATA:
        available = by_stratum[name]
        if len(available) < PER_STRATUM:
            raise ValueError(f"not enough mapped games in {name}")
        ordered = sorted(available, key=lambda row:
                         (hashlib.sha256(f'{SEED}:{row["game_id"]}'.encode()).hexdigest(),
                          row["game_id"]))
        selection.extend({"game_id": row["game_id"], "stratum": name,
                          "condition_id": row["condition_id"],
                          "token_ids": row["token_ids"]}
                         for row in ordered[:PER_STRATUM])
        summary.append({"stratum": name, "scheduled_games": len(available) + missing[name],
                        "mapped_games": len(available), "unmatched_games": missing[name],
                        "selected_mapped_games": PER_STRATUM})
    return {"selection": selection, "stratum_summary": summary,
            "scheduled_games": len(ids) + len(unmatched)}


def plan(mapping_dir: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(output)
    mapping_raw = (mapping_dir / "mapping.json").read_bytes()
    unmatched_raw = (mapping_dir / "unmatched.json").read_bytes()
    prior = json.loads((mapping_dir / "manifest.json").read_text())
    if (prior.get("schema") != "market_p0_2023_archive_identity_v1"
            or prior.get("schedule_games") != 285
            or prior.get("matched_unique_games") != 237
            or prior.get("unmatched_schedule_games") != 48
            or prior.get("mapping_sha256") != sha(mapping_raw)
            or prior.get("unmatched_sha256") != sha(unmatched_raw)
            or prior.get("formal_data_admitted") is not False):
        raise ValueError("not the fixed unadmitted 2023 identity screen")
    result = sample(json.loads(mapping_raw), json.loads(unmatched_raw))
    if result["scheduled_games"] != 285:
        raise ValueError("schedule denominator changed")
    selection_raw = encoded(result)
    report = {"schema": "market_p0_2023_stratified_density_plan_v1",
              "selection_rule": "3 SHA-256(seed:game_id) lowest mapped IDs in each fixed week band",
              "seed": SEED, "mapping_sha256_verified": sha(mapping_raw),
              "unmatched_sha256_verified": sha(unmatched_raw),
              "selection_sha256": sha(selection_raw),
              "selected_games": len(result["selection"]),
              "season_denominator": 285, "missing_market_games_retained": 48,
              "training_or_evaluation_subset": False,
              "trades_prices_or_outcomes_read": False, "formal_data_admitted": False,
              "provider_cost_usd": "0"}
    output.mkdir(parents=True, exist_ok=False)
    (output / "selection.json").write_bytes(selection_raw)
    (output / "manifest.json").write_bytes(encoded(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(plan(args.mapping, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
