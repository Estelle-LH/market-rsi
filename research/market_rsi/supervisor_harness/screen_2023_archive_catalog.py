"""Source-only 2023 NFL CLOB identity screen from a pinned public archive.

This maps market metadata to schedule identities, never reads game scores,
prices, trades, or any protected evaluation result. It is not data admission.
The archive object SHA is publisher-declared until the full object is fetched;
the exact query result and schedule input get local SHA-256 receipts.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
import hashlib
import io
import json
from pathlib import Path
import re


REVISION = "7eeb860dea5b79d5c74f3182b70bd08c85c8f833"
MARKET_DATA_SHA256_PUBLISHER = "7db9694db9ec44c5f581e514811db69dd2f9d37d3fc7088ae390d0bf1c33a8cf"
MARKET_DATA_URL = (
    "https://huggingface.co/datasets/moose-code/polymarket-onchain-v1/resolve/"
    f"{REVISION}/market_data.parquet"
)
SCHEDULE_SHA256 = "bc87373a5d1a578ac07c71cb6a1e50a381d58fae393021b96853a4b8674ae8b8"
MARKET_SLUG = re.compile(r"^nfl-([a-z0-9]+)-([a-z0-9]+)-(2023-\d{2}-\d{2}|2024-\d{2}-\d{2})$")
ALIASES = {"JAX": "JAC", "WSH": "WAS", "LA": "LAR", "LAS": "LV"}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encoded(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def games_from_schedule(raw: bytes) -> list[dict]:
    if sha(raw) != SCHEDULE_SHA256:
        raise ValueError("nflverse schedule hash does not match the studied revision")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    required = {"game_id", "season", "gameday", "away_team", "home_team"}
    if not required.issubset(reader.fieldnames or ()):
        raise ValueError("schedule identity fields missing")
    games = []
    for row in reader:
        if row["season"] != "2023":
            continue
        games.append({"game_id": row["game_id"], "game_date": row["gameday"],
                      "away_team": ALIASES.get(row["away_team"], row["away_team"]),
                      "home_team": ALIASES.get(row["home_team"], row["home_team"])})
    if len(games) != 285 or len({g["game_id"] for g in games}) != 285:
        raise ValueError("2023 schedule not exactly 285 unique games")
    return games


def candidate_rows() -> list[dict]:
    """Read only five required metadata columns by HTTPS Parquet ranges."""
    import duckdb

    connection = duckdb.connect()
    try:
        rows = connection.execute(
            """SELECT condition, marketSlug, marketName, outcomes,
                      list(DISTINCT id) AS token_ids
                 FROM read_parquet(?)
                WHERE marketSlug ILIKE 'nfl-%'
                  AND endDate >= '2023-09-01' AND endDate < '2024-03-01'
                GROUP BY condition, marketSlug, marketName, outcomes
                ORDER BY marketSlug, condition""",
            [MARKET_DATA_URL],
        ).fetchall()
    finally:
        connection.close()
    return [{"condition_id": str(condition or ""), "slug": str(slug or ""),
             "name": str(name or ""), "outcomes": outcomes,
             "token_ids": sorted(str(token) for token in tokens or [])}
            for condition, slug, name, outcomes, tokens in rows]


def match(candidates: list[dict], games: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    """Map strictly by team pair and date, retaining ambiguous and absent rows."""
    index: dict[tuple[str, frozenset[str]], list[dict]] = {}
    for game in games:
        index.setdefault((game["game_date"], frozenset((game["away_team"], game["home_team"]))), []).append(game)
    by_game: dict[str, list[dict]] = {}
    failures: list[dict] = []
    for row in candidates:
        parts = MARKET_SLUG.fullmatch(row["slug"])
        if not parts:
            failures.append({"condition_id": row["condition_id"], "reason": "slug_shape"})
            continue
        if not row["condition_id"] or len(row["token_ids"]) != 2:
            failures.append({"condition_id": row["condition_id"], "reason": "token_pair_missing"})
            continue
        teams = frozenset(ALIASES.get(team.upper(), team.upper()) for team in parts.group(1, 2))
        center = date.fromisoformat(parts.group(3))
        found = []
        for offset in (0, -1, 1):
            day = (center + timedelta(days=offset)).isoformat()
            if index.get((day, teams)):
                found = index[(day, teams)]
                break
        if len(found) != 1:
            failures.append({"condition_id": row["condition_id"], "reason": "schedule_missing_or_ambiguous"})
            continue
        by_game.setdefault(found[0]["game_id"], []).append(row)
    matched: list[dict] = []
    for game in games:
        entries = by_game.get(game["game_id"], [])
        if len(entries) > 1:
            failures.extend({"condition_id": row["condition_id"], "reason": "multiple_markets_for_game"}
                            for row in entries)
        elif len(entries) == 1:
            row = entries[0]
            matched.append({"game_id": game["game_id"], "game_date": game["game_date"],
                            "condition_id": row["condition_id"], "market_slug": row["slug"],
                            "token_ids": row["token_ids"]})
    unmatched = [g["game_id"] for g in games if g["game_id"] not in {m["game_id"] for m in matched}]
    return matched, failures, unmatched


def screen(schedule: Path, output: Path, *, candidates_file: Path | None = None) -> dict:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    raw_schedule = schedule.read_bytes()
    games = games_from_schedule(raw_schedule)
    if candidates_file is None:
        candidates = candidate_rows()
        candidate_raw = encoded(candidates)
        candidate_input = "revision-pinned HTTPS Parquet range query"
    else:
        candidate_raw = candidates_file.read_bytes()
        candidates = json.loads(candidate_raw)
        if not isinstance(candidates, list) or encoded(candidates) != candidate_raw:
            raise ValueError("candidate replay file must be canonical JSON list")
        candidate_input = str(candidates_file.resolve())
    matched, failures, unmatched = match(candidates, games)
    mapping_raw, failures_raw, unmatched_raw = map(encoded, (matched, failures, unmatched))
    reasons = {reason: sum(f["reason"] == reason for f in failures)
               for reason in sorted({f["reason"] for f in failures})}
    manifest = {"schema": "market_p0_2023_archive_identity_v1", "season": 2023,
                "source": MARKET_DATA_URL, "revision": REVISION,
                "candidate_input": candidate_input,
                "source_object_sha256_publisher_claim": MARKET_DATA_SHA256_PUBLISHER,
                "full_source_object_downloaded_and_hashed": False,
                "schedule_sha256_verified": sha(raw_schedule),
                "schedule_games": len(games), "candidate_conditions": len(candidates),
                "matched_unique_games": len(matched), "unmatched_schedule_games": len(unmatched),
                "failure_reasons": reasons, "candidate_result_sha256": sha(candidate_raw),
                "mapping_sha256": sha(mapping_raw), "failures_sha256": sha(failures_raw),
                "unmatched_sha256": sha(unmatched_raw),
                "trades_verified": False, "labels_verified": False,
                "rights_independently_verified": False, "formal_data_admitted": False,
                "provider_cost_usd": "0"}
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (("candidates.json", candidate_raw), ("mapping.json", mapping_raw),
                        ("failures.json", failures_raw), ("unmatched.json", unmatched_raw),
                        ("manifest.json", encoded(manifest))):
        (output / name).write_bytes(value)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-public-metadata-query", action="store_true")
    parser.add_argument("--replay-candidates", type=Path,
                        help="reuse a prior canonical candidate result with no network query")
    args = parser.parse_args()
    if args.execute_public_metadata_query == (args.replay_candidates is not None):
        parser.error("choose exactly one: --execute-public-metadata-query or --replay-candidates")
    print(json.dumps(screen(args.schedule, args.output,
                            candidates_file=args.replay_candidates), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
