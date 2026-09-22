"""Offline candidate verifier for preserved 2024 NFL outcome orientation.

The public entry point is pinned to the exact preserved Gamma event catalog and
candidate mapping.  It performs no I/O and emits candidate receipts only.  In
particular, it never invents an orientation for a catalog event absent from the
mapping and grants no data-admission, rights, network, Dev, or Final authority.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from types import MappingProxyType

from market_rsi import digest


RECEIPT_SET_SCHEMA = "market_2024_outcome_orientation_receipt_set_v1"
RECEIPT_SCHEMA = "market_2024_outcome_orientation_candidate_v1"

PRESERVED_CATALOG_SHA256 = (
    "c89f097b6538ceee46bb7b2950c3fd9ab6971fc5a39ddf00da61e5f589a3c0eb"
)
PRESERVED_MAPPING_SHA256 = (
    "a8621f15ed703f01add64aaf4869b2ef262b4762d7bd241ba3168d040942008b"
)
PRESERVED_CATALOG_EVENTS = 285
PRESERVED_MAPPED_EVENTS = 284
PRESERVED_UNORIENTED_EVENT = MappingProxyType({
    "event_id": "17330",
    "event_slug": "nfl-kc-phi-2025-02-09",
    "reason": "absent_from_candidate_mapping",
})

# Exact outcome vocabulary observed in the preserved catalog.  This table is
# intentionally narrow: no fuzzy, substring, city, or nickname inference.
TEAM_NAME_ALIASES = MappingProxyType({
    "ARI": ("Cardinals",),
    "ATL": ("Falcons",),
    "BAL": ("Ravens",),
    "BUF": ("Bills",),
    "CAR": ("Panthers",),
    "CHI": ("Bears",),
    "CIN": ("Bengals",),
    "CLE": ("Browns",),
    "DAL": ("Cowboys",),
    "DEN": ("Broncos",),
    "DET": ("Lions",),
    "GB": ("Packers",),
    "HOU": ("Texans",),
    "IND": ("Colts",),
    "JAC": ("Jaguars",),
    "KC": ("Chiefs",),
    "LAC": ("Chargers",),
    "LAR": ("Rams",),
    "LV": ("Raiders",),
    "MIA": ("Dolphins",),
    "MIN": ("Vikings",),
    "NE": ("Patriots",),
    "NO": ("Saints",),
    "NYG": ("Giants",),
    "NYJ": ("Jets",),
    "PHI": ("Eagles",),
    "PIT": ("Steelers",),
    "SEA": ("Seahawks",),
    "SF": ("49ers",),
    "TB": ("Buccaneers",),
    "TEN": ("Titans",),
    "WAS": ("Commanders",),
})

# Provider and nflverse identifiers use a few distinct abbreviations.  These
# explicit tables validate identity only; neither table determines orientation.
SLUG_TEAM_ALIASES = MappingProxyType({
    "LA": "LAR", "LAR": "LAR", "LAS": "LV", "LV": "LV",
    "JAX": "JAC", "WSH": "WAS", "WAS": "WAS",
})
GAME_ID_TEAM_ALIASES = MappingProxyType({"LA": "LAR", "JAX": "JAC"})

MAPPING_FIELDS = (
    "polymarket_event_id", "event_slug", "event_start_utc",
    "nflverse_game_id", "nflverse_game_date", "away_team", "home_team",
    "slug_order", "date_resolution", "moneyline_market_id", "condition_id",
    "outcomes_json", "tokens_json",
)

_EVENT_ID = re.compile(r"[1-9][0-9]{0,19}\Z")
_MARKET_ID = re.compile(r"[1-9][0-9]{0,19}\Z")
_CONDITION_ID = re.compile(r"0x[0-9a-f]{64}\Z")
_TOKEN_ID = re.compile(r"[1-9][0-9]{0,99}\Z")
_GAME_ID = re.compile(r"2024_[0-9]{2}_([A-Z]{2,3})_([A-Z]{2,3})\Z")
_SLUG = re.compile(r"nfl-([a-z]+)-([a-z]+)-(\d{4}-\d{2}-\d{2})\Z")
_DATE = re.compile(r"202[45]-\d{2}-\d{2}\Z")
_UTC = re.compile(r"202[45]-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


def _sha256(raw: object, label: str) -> str:
    if not isinstance(raw, bytes):
        raise ValueError(f"{label} must be exact bytes")
    return hashlib.sha256(raw).hexdigest()


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON member: {key}")
        value[key] = item
    return value


def _json_bytes(raw: bytes, label: str) -> object:
    try:
        text = raw.decode("utf-8", errors="strict")
        return json.loads(text, object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not strict JSON") from exc


def _json_array_text(value: object, label: str) -> list[str]:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a JSON-encoded string array")
    try:
        parsed = json.loads(value, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not a valid JSON-encoded array") from exc
    if (not isinstance(parsed, list) or len(parsed) != 2
            or any(not isinstance(item, str) for item in parsed)):
        raise ValueError(f"{label} must contain exactly two strings")
    return parsed


def _alias_material(alias_table: object) -> dict[str, list[str]]:
    if not isinstance(alias_table, dict) and not isinstance(alias_table, MappingProxyType):
        raise ValueError("team alias table must be a mapping")
    material: dict[str, list[str]] = {}
    reverse: dict[str, str] = {}
    for team, aliases in alias_table.items():
        if (not isinstance(team, str) or not re.fullmatch(r"[A-Z]{2,3}", team)
                or not isinstance(aliases, (tuple, list)) or not aliases):
            raise ValueError("team alias table has an invalid team entry")
        normalized = []
        for alias in aliases:
            if (not isinstance(alias, str) or not alias or alias != alias.strip()
                    or any(ord(character) < 32 for character in alias)):
                raise ValueError("team alias must be one exact printable name")
            if alias in normalized:
                raise ValueError("duplicate team-name alias within one team")
            if alias in reverse:
                raise ValueError("ambiguous team-name alias across teams")
            reverse[alias] = team
            normalized.append(alias)
        material[team] = sorted(normalized)
    return {team: material[team] for team in sorted(material)}


def _alias_index(alias_table: object) -> tuple[dict[str, str], str]:
    material = _alias_material(alias_table)
    expected = _alias_material(TEAM_NAME_ALIASES)
    if material != expected:
        raise ValueError("team alias table differs from the reviewed code-owned table")
    return ({alias: team for team, aliases in material.items() for alias in aliases},
            digest(material))


def _csv_rows(raw: bytes) -> list[dict[str, str]]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("candidate mapping is not strict UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != MAPPING_FIELDS:
        raise ValueError("candidate mapping CSV fields differ from the frozen schema")
    rows = list(reader)
    if not rows:
        raise ValueError("candidate mapping CSV is empty")
    if any(set(row) != set(MAPPING_FIELDS) or any(value is None for value in row.values())
           for row in rows):
        raise ValueError("candidate mapping CSV row shape differs from its header")
    return rows


def _canonical_slug_team(raw: str) -> str:
    canonical = SLUG_TEAM_ALIASES.get(raw, raw)
    if canonical not in TEAM_NAME_ALIASES:
        raise ValueError("event slug contains an unknown team abbreviation")
    return canonical


def _canonical_game_team(raw: str) -> str:
    canonical = GAME_ID_TEAM_ALIASES.get(raw, raw)
    if canonical not in TEAM_NAME_ALIASES:
        raise ValueError("nflverse game ID contains an unknown team abbreviation")
    return canonical


def _validate_mapping_identity(row: dict[str, str], event: dict) -> None:
    event_id = row["polymarket_event_id"]
    market_id = row["moneyline_market_id"]
    if (not _EVENT_ID.fullmatch(event_id) or not _MARKET_ID.fullmatch(market_id)
            or not _CONDITION_ID.fullmatch(row["condition_id"])):
        raise ValueError("mapping event/market/condition identity is noncanonical")
    if (str(event.get("id")) != event_id
            or event.get("slug") != row["event_slug"]
            or event.get("startTime") != row["event_start_utc"]
            or not _UTC.fullmatch(row["event_start_utc"])
            or not _DATE.fullmatch(row["nflverse_game_date"])
            or row["date_resolution"] != "exact"):
        raise ValueError("mapping row differs from the preserved source event")
    away_team, home_team = row["away_team"], row["home_team"]
    if (away_team not in TEAM_NAME_ALIASES or home_team not in TEAM_NAME_ALIASES
            or away_team == home_team):
        raise ValueError("mapping home/away team identity is invalid")
    game_match = _GAME_ID.fullmatch(row["nflverse_game_id"])
    if (game_match is None
            or _canonical_game_team(game_match.group(1)) != away_team
            or _canonical_game_team(game_match.group(2)) != home_team):
        raise ValueError("mapping home/away order differs from nflverse game ID")
    slug_match = _SLUG.fullmatch(row["event_slug"])
    if slug_match is None:
        raise ValueError("event slug shape is invalid")
    first = _canonical_slug_team(slug_match.group(1).upper())
    second = _canonical_slug_team(slug_match.group(2).upper())
    if row["slug_order"] == "away_home":
        slug_away, slug_home = first, second
    elif row["slug_order"] == "home_away":
        slug_home, slug_away = first, second
    else:
        raise ValueError("slug order is neither away_home nor home_away")
    if slug_away != away_team or slug_home != home_team:
        raise ValueError("event slug teams/order differ from mapped home/away teams")


def _event_market(event: dict, row: dict[str, str]) -> dict:
    markets = event.get("markets")
    if not isinstance(markets, list):
        raise ValueError("source event markets must be a list")
    matching = [market for market in markets if isinstance(market, dict)
                and str(market.get("id")) == row["moneyline_market_id"]]
    if len(matching) != 1:
        raise ValueError("mapping market ID is missing or ambiguous in source event")
    market = matching[0]
    moneylines = [item for item in markets if isinstance(item, dict)
                  and item.get("sportsMarketType") == "moneyline"]
    event_slug = _SLUG.fullmatch(row["event_slug"])
    market_slug = _SLUG.fullmatch(market.get("slug") or "")
    market_slug_teams = (set() if market_slug is None else {
        _canonical_slug_team(market_slug.group(1).upper()),
        _canonical_slug_team(market_slug.group(2).upper()),
    })
    if (len(moneylines) != 1 or moneylines[0] is not market
            or market.get("conditionId") != row["condition_id"]
            or event_slug is None or market_slug is None
            or market_slug.group(3) != event_slug.group(3)
            or market_slug_teams != {row["away_team"], row["home_team"]}):
        raise ValueError("source moneyline identity differs from candidate mapping")
    return market


def _orientation_receipt(row: dict[str, str], event: dict,
                         alias_index: dict[str, str], alias_sha256: str,
                         catalog_sha256: str, mapping_sha256: str) -> dict:
    _validate_mapping_identity(row, event)
    market = _event_market(event, row)
    outcomes = _json_array_text(market.get("outcomes"), "source outcomes")
    tokens = _json_array_text(market.get("clobTokenIds"), "source tokens")
    mapped_outcomes = _json_array_text(row["outcomes_json"], "mapping outcomes")
    mapped_tokens = _json_array_text(row["tokens_json"], "mapping tokens")
    if outcomes != mapped_outcomes or tokens != mapped_tokens:
        raise ValueError("mapping outcome/token pairs differ from source market")
    if len(set(outcomes)) != 2:
        raise ValueError("source moneyline has duplicate outcome names")
    if (len(set(tokens)) != 2
            or any(not _TOKEN_ID.fullmatch(token) for token in tokens)):
        raise ValueError("source moneyline token IDs are duplicate or noncanonical")
    teams = []
    for outcome in outcomes:
        team = alias_index.get(outcome)
        if team is None:
            raise ValueError("source moneyline outcome is absent from alias table")
        teams.append(team)
    if len(set(teams)) != 2:
        raise ValueError("source moneyline outcome aliases are ambiguous or duplicate")
    away_team, home_team = row["away_team"], row["home_team"]
    if set(teams) != {away_team, home_team}:
        raise ValueError("source outcomes do not name the mapped home and away teams")
    away_index = teams.index(away_team)
    home_index = teams.index(home_team)
    return {
        "schema": RECEIPT_SCHEMA,
        "status": "candidate_only",
        "catalog_sha256": catalog_sha256,
        "mapping_sha256": mapping_sha256,
        "alias_table_sha256": alias_sha256,
        "source_event_sha256": digest(event),
        "mapping_row_sha256": digest(row),
        "polymarket_event_id": row["polymarket_event_id"],
        "event_slug": row["event_slug"],
        "nflverse_game_id": row["nflverse_game_id"],
        "moneyline_market_id": row["moneyline_market_id"],
        "condition_id": row["condition_id"],
        "away_team": away_team,
        "away_outcome": outcomes[away_index],
        "away_outcome_index": away_index,
        "away_token_id": tokens[away_index],
        "home_team": home_team,
        "home_outcome": outcomes[home_index],
        "home_outcome_index": home_index,
        "home_token_id": tokens[home_index],
        "orientation_basis": "reviewed_exact_team_name_alias_table",
        "source_rights_verified": False,
        "provider_origin_authenticated": False,
        "formal_train_admitted": False,
        "dev_data_opened": False,
        "final_data_opened": False,
    }


def _verify_bound_orientation(catalog_raw: object, mapping_raw: object, *,
                              expected_catalog_sha256: str,
                              expected_mapping_sha256: str,
                              expected_catalog_events: int,
                              expected_mapped_events: int,
                              alias_table: object = TEAM_NAME_ALIASES) -> dict:
    """Verify exact bound bytes; intended for the pinned wrapper and tests."""
    catalog_sha256 = _sha256(catalog_raw, "catalog")
    mapping_sha256 = _sha256(mapping_raw, "mapping")
    if catalog_sha256 != expected_catalog_sha256:
        raise ValueError("catalog bytes differ from their trusted source hash")
    if mapping_sha256 != expected_mapping_sha256:
        raise ValueError("mapping bytes differ from their trusted mapping hash")
    if (type(expected_catalog_events) is not int or expected_catalog_events <= 0
            or type(expected_mapped_events) is not int or expected_mapped_events <= 0
            or expected_mapped_events > expected_catalog_events):
        raise ValueError("expected source/mapping counts are invalid")
    events = _json_bytes(catalog_raw, "catalog")
    rows = _csv_rows(mapping_raw)
    if not isinstance(events, list) or len(events) != expected_catalog_events:
        raise ValueError("catalog event count differs from the bound source")
    if len(rows) != expected_mapped_events:
        raise ValueError("mapping row count differs from the bound mapping")
    event_index: dict[str, dict] = {}
    slug_index: set[str] = set()
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("catalog event must be an object")
        event_id, slug = str(event.get("id")), event.get("slug")
        if (not _EVENT_ID.fullmatch(event_id) or not isinstance(slug, str)
                or event_id in event_index or slug in slug_index):
            raise ValueError("catalog event ID/slug is invalid or duplicated")
        event_index[event_id] = event
        slug_index.add(slug)
    alias_index, alias_sha256 = _alias_index(alias_table)
    receipts = []
    mapped_event_ids: set[str] = set()
    mapped_game_ids: set[str] = set()
    conditions: set[str] = set()
    token_ids: set[str] = set()
    for row in rows:
        event_id = row["polymarket_event_id"]
        game_id = row["nflverse_game_id"]
        if (event_id in mapped_event_ids or game_id in mapped_game_ids
                or row["condition_id"] in conditions):
            raise ValueError("candidate mapping repeats an event/game/condition")
        event = event_index.get(event_id)
        if event is None:
            raise ValueError("candidate mapping references an absent source event")
        receipt = _orientation_receipt(
            row, event, alias_index, alias_sha256,
            catalog_sha256, mapping_sha256)
        row_tokens = {receipt["away_token_id"], receipt["home_token_id"]}
        if row_tokens & token_ids:
            raise ValueError("candidate mapping reuses a token across games")
        token_ids.update(row_tokens)
        mapped_event_ids.add(event_id)
        mapped_game_ids.add(game_id)
        conditions.add(row["condition_id"])
        receipts.append(receipt)
    receipts.sort(key=lambda item: item["nflverse_game_id"])
    unoriented = [{
        "event_id": event_id,
        "event_slug": event_index[event_id]["slug"],
        "reason": "absent_from_candidate_mapping",
    } for event_id in sorted(set(event_index) - mapped_event_ids, key=int)]
    return {
        "schema": RECEIPT_SET_SCHEMA,
        "status": "candidate_only",
        "catalog_sha256": catalog_sha256,
        "mapping_sha256": mapping_sha256,
        "alias_table_sha256": alias_sha256,
        "catalog_event_count": len(events),
        "candidate_orientation_count": len(receipts),
        "unoriented_source_event_count": len(unoriented),
        "unoriented_source_events": unoriented,
        "candidate_orientation_receipts": receipts,
        "all_source_events_oriented": not unoriented,
        "missing_orientation_inferred": False,
        "source_rights_verified": False,
        "provider_origin_authenticated": False,
        "formal_train_admitted": False,
        "network_execution_authorized": False,
        "dev_data_opened": False,
        "final_data_opened": False,
    }


def verify_preserved_2024_orientation(catalog_raw: object,
                                      mapping_raw: object) -> dict:
    """Verify the exact preserved 2024 source and emit candidate receipts."""
    result = _verify_bound_orientation(
        catalog_raw, mapping_raw,
        expected_catalog_sha256=PRESERVED_CATALOG_SHA256,
        expected_mapping_sha256=PRESERVED_MAPPING_SHA256,
        expected_catalog_events=PRESERVED_CATALOG_EVENTS,
        expected_mapped_events=PRESERVED_MAPPED_EVENTS,
    )
    if result["unoriented_source_events"] != [dict(PRESERVED_UNORIENTED_EVENT)]:
        raise ValueError("preserved missing event differs; orientation is not inferred")
    return result
