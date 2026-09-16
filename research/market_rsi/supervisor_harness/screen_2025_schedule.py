"""Match 2025 public NFL market metadata to schedule identities, not scores.

This P0 screen never reads price history or outputs game results. The upstream
schedule CSV contains score columns, but only identity fields are parsed and
the raw CSV is not saved. Output is diagnostic, never Train/Dev admission.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta, datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen


SCHEDULE_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
SLUG = re.compile(r"^nfl-([a-z0-9]+)-([a-z0-9]+)-(2025-\d{2}-\d{2}|2026-\d{2}-\d{2})$")
ALIASES = {"LA": "LAR", "JAX": "JAC", "WSH": "WAS"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def schedule_identities(raw: bytes) -> list[dict]:
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    needed = {"game_id", "season", "gameday", "away_team", "home_team"}
    if not needed.issubset(reader.fieldnames or ()):
        raise ValueError("schedule missing identity fields")
    games = []
    for row in reader:
        if row["season"] == "2025":
            games.append({"game_id": row["game_id"], "game_date": row["gameday"],
                          "away_team": ALIASES.get(row["away_team"], row["away_team"]),
                          "home_team": ALIASES.get(row["home_team"], row["home_team"])})
    if not games or len({row["game_id"] for row in games}) != len(games):
        raise ValueError("2025 schedule empty or duplicated")
    return games


def load_events(catalog: Path) -> tuple[list[dict], list[dict]]:
    manifest = json.loads((catalog / "manifest.json").read_text())
    season = manifest["seasons"]["2025"]
    if (not season["complete_keyset_pagination"] or season["series_slug"] != "nfl-2025"
            or manifest["trades_opened"] or manifest["scores_opened"]):
        raise ValueError("2025 metadata inventory is not a clean complete screen")
    events = []
    for receipt in season["pages"]:
        raw = (catalog / f"2025-page-{receipt['page']:03d}.raw.json").read_bytes()
        if sha(raw) != receipt["sha256"]:
            raise ValueError("catalog page hash changed")
        events.extend(json.loads(raw)["events"])
    if len(events) != season["events"]:
        raise ValueError("catalog event count changed")
    return events, season["pages"]


def match(events: list[dict], games: list[dict]) -> tuple[list[dict], list[dict]]:
    index: dict[tuple[str, frozenset[str]], list[dict]] = {}
    for game in games:
        index.setdefault((game["game_date"], frozenset((game["away_team"], game["home_team"]))), []).append(game)
    mapped, failures = [], []
    used_games: set[str] = set()
    for event in events:
        event_id = str(event.get("id") or "")
        slug = str(event.get("slug") or "")
        parts = SLUG.fullmatch(slug)
        if not parts:
            failures.append({"event_id": event_id, "reason": "slug_shape"})
            continue
        teams = frozenset(ALIASES.get(x.upper(), x.upper()) for x in parts.group(1, 2))
        center = date.fromisoformat(parts.group(3))
        candidates = []
        for offset in (0, -1, 1):
            day = (center + timedelta(days=offset)).isoformat()
            found = index.get((day, teams), [])
            if found:
                candidates = found
                break
        if len(candidates) != 1:
            failures.append({"event_id": event_id, "reason": "schedule_missing_or_ambiguous"})
            continue
        game = candidates[0]
        if game["game_id"] in used_games:
            failures.append({"event_id": event_id, "reason": "duplicate_game_market"})
            continue
        markets = []
        for market in event.get("markets") or []:
            if market.get("sportsMarketType") == "moneyline" and market.get("conditionId"):
                outcomes = market.get("outcomes")
                tokens = market.get("clobTokenIds")
                if isinstance(outcomes, str):
                    outcomes = json.loads(outcomes)
                if isinstance(tokens, str):
                    tokens = json.loads(tokens)
                if isinstance(outcomes, list) and len(outcomes) == 2 and isinstance(tokens, list) and len(tokens) == 2 and all(tokens):
                    markets.append(market)
        if len(markets) != 1:
            failures.append({"event_id": event_id, "reason": "moneyline_missing_or_ambiguous"})
            continue
        used_games.add(game["game_id"])
        mapped.append({"event_id": event_id, "game_id": game["game_id"],
                       "game_date": game["game_date"], "event_slug": slug,
                       "market_id": str(markets[0]["id"]),
                       "condition_id": str(markets[0]["conditionId"])})
    return mapped, failures


def fetch_schedule(timeout: float) -> tuple[bytes, str]:
    request = Request(SCHEDULE_URL, headers={"User-Agent": "market-rsi-p0-inventory/1.0"})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"schedule source HTTP {response.status}")
        raw = response.read(10_000_001)
    if len(raw) > 10_000_000:
        raise ValueError("schedule exceeded 10 MB safety limit")
    return raw, SCHEDULE_URL


def screen(catalog: Path, output: Path, timeout: float = 30) -> dict:
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    events, receipts = load_events(Path(catalog).resolve())
    schedule_raw, url = fetch_schedule(timeout)
    games = schedule_identities(schedule_raw)
    mapped, failures = match(events, games)
    mapping_bytes = (json.dumps(mapped, indent=2, sort_keys=True) + "\n").encode()
    failures_bytes = (json.dumps(failures, indent=2, sort_keys=True) + "\n").encode()
    (output / "mapping.json").write_bytes(mapping_bytes)
    (output / "failures.json").write_bytes(failures_bytes)
    reasons = {reason: sum(row["reason"] == reason for row in failures)
               for reason in sorted({row["reason"] for row in failures})}
    report = {"schema": "market_p0_2025_schedule_screen_v1",
              "generated_utc": datetime.now(timezone.utc).isoformat(),
              "source": {"url": url, "raw_sha256": sha(schedule_raw),
                         "identity_fields_only": True, "raw_scores_not_saved": True},
              "catalog_page_sha256": [row["sha256"] for row in receipts],
              "schedule_games": len(games), "catalog_events": len(events),
              "mapped_unique_games": len(mapped), "unmatched_schedule_games": len(games) - len(mapped),
              "failure_reasons": reasons, "mapping_sha256": sha(mapping_bytes),
              "failures_sha256": sha(failures_bytes), "trade_coverage_verified": False,
              "formal_data_admitted": False, "provider_cost_usd": "0"}
    (output / "manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    print(json.dumps(screen(args.catalog, args.output, args.timeout), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
