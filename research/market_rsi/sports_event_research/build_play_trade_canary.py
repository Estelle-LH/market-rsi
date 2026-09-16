"""Align one historical NFL play stream with a public trade tape.

The result measures descriptive coverage only. Historical provider wall clocks
do not establish which live feed arrived first and trade prints are not BBO,
queue, or our fill evidence.
"""
from __future__ import annotations

import argparse
import bisect
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path


HORIZONS = (30, 60, 300)
NFL_TEAM_NAMES = {
    "ARI": {"ARI", "Cardinals"}, "ATL": {"ATL", "Falcons"},
    "BAL": {"BAL", "Ravens"}, "BUF": {"BUF", "Bills"},
    "CAR": {"CAR", "Panthers"}, "CHI": {"CHI", "Bears"},
    "CIN": {"CIN", "Bengals"}, "CLE": {"CLE", "Browns"},
    "DAL": {"DAL", "Cowboys"}, "DEN": {"DEN", "Broncos"},
    "DET": {"DET", "Lions"}, "GB": {"GB", "Packers"},
    "HOU": {"HOU", "Texans"}, "IND": {"IND", "Colts"},
    "JAC": {"JAC", "JAX", "Jaguars"}, "KC": {"KC", "Chiefs"},
    "LAC": {"LAC", "Chargers"}, "LAR": {"LA", "LAR", "Rams"},
    "LV": {"LV", "Raiders"}, "MIA": {"MIA", "Dolphins"},
    "MIN": {"MIN", "Vikings"}, "NE": {"NE", "Patriots"},
    "NO": {"NO", "Saints"}, "NYG": {"NYG", "Giants"},
    "NYJ": {"NYJ", "Jets"}, "PHI": {"PHI", "Eagles"},
    "PIT": {"PIT", "Steelers"}, "SEA": {"SEA", "Seahawks"},
    "SF": {"SF", "49ers"}, "TB": {"TB", "Buccaneers"},
    "TEN": {"TEN", "Titans"}, "WAS": {"WAS", "Commanders"},
}


def sha(path: Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def timestamp(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def clock_seconds(value: str) -> int:
    minutes, seconds = value.split(":", 1)
    return int(minutes) * 60 + int(seconds)


def field_yards_to_goal(possession: str, location: dict) -> int | None:
    alias, yardline = location.get("alias"), location.get("yardline")
    if not possession or not alias or yardline is None:
        return None
    yardline = int(yardline)
    if not 0 <= yardline <= 100:
        return None
    return 100 - yardline if alias == possession else yardline


def plays(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        game = json.load(stream)
    home_alias = ((game.get("summary") or {}).get("home") or {}).get("alias")
    away_alias = ((game.get("summary") or {}).get("away") or {}).get("alias")
    if not home_alias or not away_alias or home_alias == away_alias:
        raise ValueError("game summary lacks distinct home/away aliases")
    result = []
    for period in game.get("periods") or []:
        for item in period.get("pbp") or []:
            events = item.get("events") if item.get("type") == "drive" else [item]
            for event in events or []:
                if event.get("type") != "play" or not event.get("wall_clock"):
                    continue
                start = event.get("start_situation") or {}
                end = event.get("end_situation") or {}
                possession = (start.get("possession") or {}).get("alias")
                location = start.get("location") or {}
                post_possession = (end.get("possession") or {}).get("alias")
                post_location = end.get("location") or {}
                period_number = int(period.get("number"))
                seconds_in_period = clock_seconds(event.get("clock") or start.get("clock") or "0:00")
                post_clock = end.get("clock")
                post_seconds = clock_seconds(post_clock) if post_clock else None
                result.append({
                    "play_id": event["id"],
                    "play_timestamp": timestamp(event["wall_clock"]),
                    "play_sequence": event.get("sequence") or "",
                    "period": period_number,
                    "game_clock": event.get("clock") or "",
                    "regulation_seconds_remaining": (
                        (4 - period_number) * 900 + seconds_in_period if period_number <= 4 else 0
                    ),
                    "play_type": event.get("play_type") or "",
                    "home_points": int(event.get("home_points") or 0),
                    "away_points": int(event.get("away_points") or 0),
                    "possession": possession or "",
                    "possession_is_home": "" if possession not in {home_alias, away_alias}
                                              else int(possession == home_alias),
                    "down": start.get("down") if start.get("down") is not None else "",
                    "yards_to_first_down": start.get("yfd") if start.get("yfd") is not None else "",
                    "field_location_team": location.get("alias") or "",
                    "field_yardline": location.get("yardline") if location.get("yardline") is not None else "",
                    "yards_to_goal": ("" if field_yards_to_goal(possession, location) is None
                                      else field_yards_to_goal(possession, location)),
                    "official": int(bool(event.get("official"))),
                    "is_no_play": int(any(detail.get("category") == "no_play"
                                          for detail in event.get("details") or [])),
                    "is_scoring_play": int(bool(event.get("scoring_play"))),
                    "description": event.get("description") or "",
                    "post_regulation_seconds_remaining": (
                        "" if post_seconds is None else
                        ((4 - period_number) * 900 + post_seconds if period_number <= 4 else 0)
                    ),
                    "post_period": period_number if end else "",
                    "post_home_score_diff": (
                        "" if event.get("home_points") is None or event.get("away_points") is None
                        else int(event["home_points"]) - int(event["away_points"])
                    ),
                    "post_possession_is_home": (
                        "" if post_possession not in {home_alias, away_alias}
                        else int(post_possession == home_alias)
                    ),
                    "post_down": end.get("down") if end.get("down") is not None else "",
                    "post_yards_to_first_down": end.get("yfd") if end.get("yfd") is not None else "",
                    "post_yards_to_goal": (
                        "" if field_yards_to_goal(post_possession, post_location) is None
                        else field_yards_to_goal(post_possession, post_location)
                    ),
                })
    result.sort(key=lambda row: (row["play_timestamp"], row["play_id"]))
    if len(result) != len({row["play_id"] for row in result}):
        raise ValueError("duplicate play IDs")
    previous_home = previous_away = 0
    for row in result:
        row["home_points_pre"] = previous_home
        row["away_points_pre"] = previous_away
        row["home_score_diff_pre"] = previous_home - previous_away
        previous_home, previous_away = row["home_points"], row["away_points"]
    return result


def home_trade_series(path: Path, selection: dict) -> tuple[list[int], list[float]]:
    title_sides = (selection.get("event_title") or "").split(" vs. ")
    outcomes = selection.get("outcomes") or []
    away, home = selection.get("away_team"), selection.get("home_team")
    if away and home:
        expected = (NFL_TEAM_NAMES.get(away), NFL_TEAM_NAMES.get(home))
        if (len(title_sides) != 2 or len(outcomes) != 2 or not all(expected)
                or title_sides[0] not in expected[0] or title_sides[1] not in expected[1]
                or outcomes[0] not in expected[0] or outcomes[1] not in expected[1]):
            raise ValueError("cannot prove away/home outcome order from explicit NFL names")
    elif len(title_sides) != 2 or outcomes != title_sides:
        raise ValueError("cannot prove outcome order from event title")
    home_token = str(selection["clob_token_ids"][1])
    rows = []
    with Path(path).open(newline="") as stream:
        for row in csv.DictReader(stream):
            price = float(row["price"])
            home_price = price if str(row["asset"]) == home_token else 1.0 - price
            rows.append((int(row["timestamp"]), home_price))
    rows.sort()
    return [row[0] for row in rows], [row[1] for row in rows]


def last_observation(times: list[int], prices: list[float], moment: int,
                     max_age: int) -> tuple[int, float] | None:
    index = bisect.bisect_right(times, moment) - 1
    if index < 0 or moment - times[index] > max_age:
        return None
    return times[index], prices[index]


def align(play_rows: list[dict], trade_times: list[int], trade_prices: list[float]) -> list[dict]:
    output = []
    previous_home, previous_away = None, None
    for play in play_rows:
        moment = play["play_timestamp"]
        row = dict(play)
        row["home_score_change"] = (play["home_points"] - previous_home) if previous_home is not None else 0
        row["away_score_change"] = (play["away_points"] - previous_away) if previous_away is not None else 0
        previous_home, previous_away = play["home_points"], play["away_points"]
        base_observation = last_observation(trade_times, trade_prices, moment, 300)
        base = None if base_observation is None else base_observation[1]
        row["home_price_pre"] = "" if base is None else base
        row["home_price_pre_timestamp"] = "" if base_observation is None else base_observation[0]
        for horizon in HORIZONS:
            after_observation = last_observation(trade_times, trade_prices, moment + horizon, horizon)
            # A pre-play print carried forward to the endpoint is not a new
            # response label.  This prevents quiet windows from becoming
            # fabricated zero-change observations.
            if after_observation is not None and after_observation[0] <= moment:
                after_observation = None
            after = None if after_observation is None else after_observation[1]
            row[f"home_price_{horizon}s"] = "" if after is None else after
            row[f"home_price_{horizon}s_timestamp"] = "" if after_observation is None else after_observation[0]
            row[f"home_change_{horizon}s"] = "" if base is None or after is None else after - base
        output.append(row)
    return output


def summarize(rows: list[dict]) -> dict:
    result = {"plays": len(rows), "scoring_plays": sum(bool(row["home_score_change"] or row["away_score_change"]) for row in rows)}
    for horizon in HORIZONS:
        changes = [float(row[f"home_change_{horizon}s"]) for row in rows if row[f"home_change_{horizon}s"] != ""]
        result[f"covered_{horizon}s"] = len(changes)
        result[f"coverage_{horizon}s"] = len(changes) / len(rows) if rows else 0.0
        result[f"mean_absolute_change_{horizon}s"] = sum(map(abs, changes)) / len(changes) if changes else None
    return result


def build(pbp: Path, trades: Path, selection_path: Path, output: Path) -> dict:
    pbp, trades, selection_path = map(Path, (pbp, trades, selection_path))
    selection = json.loads(selection_path.read_text())
    play_rows = plays(pbp); trade_times, trade_prices = home_trade_series(trades, selection)
    rows = align(play_rows, trade_times, trade_prices)
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    panel = output / "play_trade_alignment.csv"
    with panel.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    result = {
        "schema": "historical_nfl_play_trade_alignment_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "pbp_path": str(pbp.resolve()), "pbp_sha256": sha(pbp),
        "trades_path": str(trades.resolve()), "trades_sha256": sha(trades),
        "selection_sha256": sha(selection_path), "panel_sha256": sha(panel),
        "summary": summarize(rows),
        "claim_layer": "descriptive_historical_market_response",
        "historical_provider_wall_clock_is_local_receive_time": False,
        "trade_print_is_bbo_or_fill_evidence": False,
        "scientific_score": False,
    }
    (output / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbp", type=Path, required=True)
    parser.add_argument("--trades", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.pbp, args.trades, args.selection, args.output), indent=2))


if __name__ == "__main__":
    main()
