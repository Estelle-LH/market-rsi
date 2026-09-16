"""Causal Polymarket US book materialization and whole-game splitting.

The collector writes full HTTP book snapshots.  Information is usable only at
the post-response ``observed_at`` time; ``receive_ns`` is an audit cross-check
and exchange ``transact_time`` is never an availability clock.  Labels use the
first valid snapshot at or after
the frozen 60-second horizon and are censored when it is too late.  Missing or
invalid books are never imputed.

This module contains no network, model, scoring, or Test-opening code.  A live
experiment still needs immutable source manifests and an outer admission
receipt before these rows can be called scientific evidence.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


NS = 1_000_000_000
SPLITS = ("train", "route_dev", "audit_dev", "test")
ISO_UTC = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T(?P<clock>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d{1,9}))?Z$"
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _integer(value, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("nonnegative integer required")
    return value


def _identifier(value, name):
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError(f"bounded {name} required")
    return value


def iso_utc_ns(value):
    """Parse a UTC ISO timestamp without using floating-point epoch math."""
    from calendar import timegm
    from datetime import datetime

    if not isinstance(value, str):
        raise ValueError("UTC timestamp string required")
    match = ISO_UTC.fullmatch(value)
    if match is None:
        raise ValueError("strict Z-suffixed UTC timestamp required")
    base = datetime.strptime(
        f"{match.group('date')}T{match.group('clock')}", "%Y-%m-%dT%H:%M:%S"
    )
    fraction = (match.group("fraction") or "").ljust(9, "0")
    return timegm(base.timetuple()) * NS + int(fraction or 0)


def information_available_ns(record, *, maximum_clock_disagreement_ns=5 * NS):
    """Return the conservative collector availability time.

    ``observed_at`` is written after the request completes, while ``receive_ns``
    is only the response receipt cross-check.  A pre-receipt or substantially
    disagreeing observed clock fails closed instead of being repaired.
    """
    request = _integer(record.get("request_start_ns"))
    receive = _integer(record.get("receive_ns"))
    observed = iso_utc_ns(record.get("observed_at"))
    if request > receive:
        raise ValueError("request starts after receipt")
    if observed < receive:
        raise ValueError("observed_at precedes response receipt")
    if observed - receive > _integer(maximum_clock_disagreement_ns):
        raise ValueError("collector clocks disagree beyond frozen tolerance")
    return observed


def _scaled(value, scale, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError(f"numeric {name} required")
    try:
        number = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"numeric {name} required") from error
    if not number.is_finite():
        raise ValueError(f"finite {name} required")
    return int((number * scale).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class Game:
    event_slug: str
    event_id: str
    venue_game_id: str
    start_ns: int
    league: str

    @property
    def game_id(self):
        # The venue and grouping convention stay explicit in every row.
        return f"polymarket:{self.event_slug}"


def build_event_catalog(records):
    """Build a stable event_slug -> Game map from event snapshots.

    A slug changing event, venue-game, start-time, or league identity is an
    error.  The latest score/live state is intentionally ignored.
    """
    catalog = {}
    seen_event_ids = {}
    counts = Counter()
    for ordinal, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"event row {ordinal} is not an object")
        try:
            information_available_ns(record)
        except ValueError:
            counts["invalid_collector_clock"] += 1
            continue
        if record.get("slug") is None or record.get("event_id") is None or record.get("game_id") is None:
            counts["null_watchlist_identity"] += 1
            continue
        slug = _identifier(record.get("slug"), "event slug")
        event_id = _identifier(str(record.get("event_id", "")), "event ID")
        venue_game_id = _identifier(str(record.get("game_id", "")), "venue game ID")
        league = _identifier(record.get("league"), "league")
        game = Game(slug, event_id, venue_game_id, iso_utc_ns(record.get("start_time")), league)
        if slug in catalog and catalog[slug] != game:
            raise ValueError("event identity changed across observations")
        if event_id in seen_event_ids and seen_event_ids[event_id] != slug:
            raise ValueError("event ID maps to multiple slugs")
        catalog[slug] = game
        seen_event_ids[event_id] = slug
        counts["event_observations"] += 1
    if not catalog:
        raise ValueError("nonempty event catalog required")
    return catalog, dict(counts, games=len(catalog))


@dataclass(frozen=True)
class MaterializationPolicy:
    horizon_ns: int = 60 * NS
    max_label_lateness_ns: int = 5 * NS
    decision_interval_ns: int = 60 * NS
    max_pregame_lead_ns: int = 6 * 60 * 60 * NS
    maximum_clock_disagreement_ns: int = 5 * NS

    def __post_init__(self):
        for name, value in asdict(self).items():
            _integer(value, minimum=1)
        if self.max_label_lateness_ns >= self.horizon_ns:
            raise ValueError("label lateness must be shorter than horizon")


@dataclass(frozen=True)
class Quote:
    source_ordinal: int
    available_ns: int
    game: Game
    market_slug: str
    bid_1e4: int
    ask_1e4: int
    bid_size_1e2: int
    ask_size_1e2: int

    @property
    def mid_2e4(self):
        return self.bid_1e4 + self.ask_1e4


def _quote(record, ordinal, catalog, policy, counts):
    """Validate one book row, returning None only for declared censor reasons."""
    if not isinstance(record, dict):
        raise ValueError("book row is not an object")
    counts["book_observations"] += 1
    try:
        available = information_available_ns(
            record, maximum_clock_disagreement_ns=policy.maximum_clock_disagreement_ns
        )
    except ValueError:
        counts["invalid_collector_clock"] += 1
        return None
    if record.get("event_slug") is None or record.get("event_id") is None:
        counts["null_watchlist_identity"] += 1
        return None
    slug = _identifier(record.get("event_slug"), "event slug")
    game = catalog.get(slug)
    if game is None:
        counts["event_not_in_catalog"] += 1
        return None
    if str(record.get("event_id", "")) != game.event_id:
        raise ValueError("book event identity disagrees with event catalog")
    if record.get("http_status") != 200:
        counts["non_200"] += 1
        return None
    if record.get("state") != "MARKET_STATE_OPEN":
        counts["market_not_open"] += 1
        return None
    flags = record.get("qa_flags")
    if not isinstance(flags, list):
        raise ValueError("qa_flags list required")
    if flags:
        counts["qa_flagged"] += 1
        return None
    if record.get("market_slug") is None:
        counts["null_watchlist_identity"] += 1
        return None
    market = _identifier(record.get("market_slug"), "market slug")
    try:
        bid, ask = _scaled(record.get("best_bid"), 10_000, "bid"), _scaled(
            record.get("best_ask"), 10_000, "ask"
        )
        bid_size, ask_size = _scaled(record.get("bid_qty_l1"), 100, "bid size"), _scaled(
            record.get("ask_qty_l1"), 100, "ask size"
        )
    except ValueError:
        counts["missing_or_invalid_bbo"] += 1
        return None
    if not 0 < bid <= ask < 10_000 or min(bid_size, ask_size) <= 0:
        counts["missing_or_invalid_bbo"] += 1
        return None
    if available >= game.start_ns:
        counts["not_pregame"] += 1
        return None
    if game.start_ns - available > policy.max_pregame_lead_ns:
        counts["outside_pregame_window"] += 1
        return None
    counts["valid_books"] += 1
    return Quote(ordinal, available, game, market, bid, ask, bid_size, ask_size)


def _source(source_sha256, quote):
    if not isinstance(source_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ValueError("source SHA-256 required")
    return {"sha256": source_sha256, "ordinal": quote.source_ordinal}


def _labeled(decision, future, source_sha256, policy):
    bid, ask = decision.bid_1e4 / 10_000, decision.ask_1e4 / 10_000
    bid_size, ask_size = decision.bid_size_1e2 / 100, decision.ask_size_1e2 / 100
    mid = (bid + ask) / 2
    future_midpoint = future.mid_2e4 / 20_000
    mid_change = future_midpoint - mid
    return {
        "row_id": _digest({"source": source_sha256, "ordinal": decision.source_ordinal,
                           "market": decision.market_slug}),
        "game_id": decision.game.game_id,
        "event_slug": decision.game.event_slug,
        "market_id": decision.market_slug,
        "game_start_ms": decision.game.start_ns // 1_000_000,
        "decision_ms": decision.available_ns // 1_000_000,
        "decision_ns": decision.available_ns,
        "feature_available_ms": decision.available_ns // 1_000_000,
        "label_target_ns": decision.available_ns + policy.horizon_ns,
        "entry_ms": decision.available_ns // 1_000_000,
        "label_end_ms": future.available_ns // 1_000_000,
        "label_available_ms": future.available_ns // 1_000_000,
        "input_source": _source(source_sha256, decision),
        "label_source": _source(source_sha256, future),
        "features": {"bid": bid, "ask": ask, "mid": mid, "spread": ask - bid,
                     "bid_size": bid_size, "ask_size": ask_size,
                     "imbalance": (bid_size - ask_size) / (bid_size + ask_size)},
        # The model predicts the future midpoint directly. Persistence is the
        # current midpoint. ``mid_change`` is retained only as an auditable
        # equivalent label.
        "target": future_midpoint,
        "labels": {
            "future_midpoint": future_midpoint,
            "mid_change": mid_change,
            "buy_yes_gross_price_change": future.bid_1e4 / 10_000 - ask,
            "buy_no_gross_price_change": bid - future.ask_1e4 / 10_000,
        },
        "runner_endpoints": {
            "entry_bid_1e4": decision.bid_1e4, "entry_ask_1e4": decision.ask_1e4,
            "exit_bid_1e4": future.bid_1e4, "exit_ask_1e4": future.ask_1e4,
            "entry_bid_size_1e2": decision.bid_size_1e2,
            "entry_ask_size_1e2": decision.ask_size_1e2,
            "exit_bid_size_1e2": future.bid_size_1e2,
            "exit_ask_size_1e2": future.ask_size_1e2,
        },
    }


def materialize_books(records, catalog, source_sha256, policy=MaterializationPolicy()):
    """Stream valid observations into independently timed 60-second labels."""
    if not isinstance(catalog, dict) or not catalog:
        raise ValueError("nonempty audited event catalog required")
    _source(source_sha256, Quote(0, 0, next(iter(catalog.values())), "check", 1, 1, 1, 1))
    counts = Counter()
    pending, last_decision, last_market_time = {}, {}, {}
    rows = []
    for ordinal, record in enumerate(records):
        quote = _quote(record, ordinal, catalog, policy, counts)
        if quote is None:
            continue
        # Independent REST requests for different markets can complete a few
        # milliseconds out of order. Causality requires strict order within a
        # market, while the finished rows are sorted globally below.
        if quote.available_ns <= last_market_time.get(quote.market_slug, -1):
            raise ValueError("duplicate or reversed market availability time")
        last_market_time[quote.market_slug] = quote.available_ns
        waiting = pending.setdefault(quote.market_slug, [])
        still_waiting = []
        for decision in waiting:
            target = decision.available_ns + policy.horizon_ns
            if quote.available_ns < target:
                still_waiting.append(decision)
            elif quote.available_ns <= target + policy.max_label_lateness_ns:
                rows.append(_labeled(decision, quote, source_sha256, policy))
                counts["labeled_rows"] += 1
            else:
                counts["label_missing_within_lateness"] += 1
        pending[quote.market_slug] = still_waiting
        previous = last_decision.get(quote.market_slug)
        if previous is None or quote.available_ns - previous >= policy.decision_interval_ns:
            pending[quote.market_slug].append(quote)
            last_decision[quote.market_slug] = quote.available_ns
            counts["scheduled_decisions"] += 1
    counts["capture_tail_censored"] += sum(map(len, pending.values()))
    rows.sort(key=lambda row: (row["decision_ns"], row["row_id"]))
    return {"schema": "polymarket_midpoint_labels_v1", "policy": asdict(policy),
            "availability_clock": "observed_at",
            "receive_ns_role": "audit_cross_check_only",
            "exchange_transact_time_used": False, "source_sha256": source_sha256,
            "rows": rows, "counts": dict(counts), "imputation_count": 0,
            "collector_transport": "independent_rest_full_book_poll",
            "sequence_or_reconnect_state_required": False,
            "scoring_ready": False}


@dataclass(frozen=True)
class SplitCounts:
    train: int
    route_dev: int
    audit_dev: int
    test: int

    def __post_init__(self):
        for value in asdict(self).values():
            _integer(value, minimum=1)


def whole_game_chronological_split(rows, counts):
    """Split complete event groups and require strict label-time chronology.

    Counts are frozen before scoring.  Same-start games may not straddle a
    boundary.  The strict availability condition makes callers leave a temporal
    embargo between partitions rather than silently fitting on late Train labels.
    """
    if not isinstance(counts, SplitCounts) or not rows:
        raise ValueError("nonempty rows and frozen split counts required")
    by_game, starts, market_games = {}, {}, {}
    for row in rows:
        game, market = row.get("game_id"), row.get("market_id")
        _identifier(game, "game ID")
        _identifier(market, "market ID")
        start = _integer(row.get("game_start_ms"), minimum=1)
        if starts.setdefault(game, start) != start:
            raise ValueError("game start time changed")
        if market_games.setdefault(market, game) != game:
            raise ValueError("market appears in multiple games")
        if not (row["feature_available_ms"] <= row["decision_ms"]
                < row["label_available_ms"] < start):
            raise ValueError("row is not a causal pregame label")
        by_game.setdefault(game, []).append(row)
    games = sorted(by_game, key=lambda game: (starts[game], game))
    wanted = sum(asdict(counts).values())
    if wanted != len(games):
        raise ValueError("split counts must assign every eligible game exactly once")
    assignments, cursor = {}, 0
    for split in SPLITS:
        size = getattr(counts, split)
        assigned = games[cursor:cursor + size]
        assignments[split] = assigned
        cursor += size
    for earlier, later in zip(SPLITS, SPLITS[1:]):
        a, b = assignments[earlier], assignments[later]
        if max(starts[g] for g in a) >= min(starts[g] for g in b):
            raise ValueError("split boundary crosses simultaneous or reversed game starts")
        earlier_rows = [row for game in a for row in by_game[game]]
        later_rows = [row for game in b for row in by_game[game]]
        if max(row["label_available_ms"] for row in earlier_rows) >= min(
                row["feature_available_ms"] for row in later_rows):
            raise ValueError("split needs a wider information-time embargo")
    split_rows = {split: sorted(
        [row for game in assignments[split] for row in by_game[game]],
        key=lambda row: (row["decision_ms"], row["row_id"]),
    ) for split in SPLITS}
    return {"schema": "polymarket_whole_game_split_v1", "assignments": assignments,
            "rows": split_rows, "counts": {split: {"games": len(assignments[split]),
                "rows": len(split_rows[split])} for split in SPLITS},
            "whole_game_disjoint": True, "strict_information_chronology": True}


def public_projection(split, test_nonce):
    """Return Train/Dev data plus only a salted commitment for hidden Test."""
    if not isinstance(test_nonce, str) or len(test_nonce) < 32:
        raise ValueError("independent secret Test nonce required")
    rows = split.get("rows", {})
    if set(rows) != set(SPLITS):
        raise ValueError("complete four-way split required")
    evaluation_keys = {"row_id", "game_id", "market_id", "decision_ms",
                       "feature_available_ms", "features"}
    training_keys = evaluation_keys | {"target", "label_available_ms"}
    project = lambda row, keys: {key: row[key] for key in keys}
    return {
        "schema": "polymarket_public_train_dev_v1",
        "train": [project(row, training_keys) for row in rows["train"]],
        "route_dev": [project(row, evaluation_keys) for row in rows["route_dev"]],
        "audit_dev": [project(row, evaluation_keys) for row in rows["audit_dev"]],
        "test_commitment": _digest({"nonce": test_nonce, "rows": rows["test"]}),
        "test_rows_exposed": False,
    }


def scorer_rows(rows):
    """Project private materialized rows into the frozen midpoint scorer."""
    result = []
    for row in rows:
        if not isinstance(row, dict) or "future_midpoint" not in row.get("labels", {}):
            raise ValueError("materialized future-midpoint label required")
        result.append({
            "row_id": row["row_id"],
            "game_id": row["game_id"],
            "market_id": row["market_id"],
            "decision_ms": row["decision_ms"],
            "target_ms": row["label_target_ns"] // 1_000_000,
            "midpoint": row["features"]["mid"],
            "target_midpoint": row["labels"]["future_midpoint"],
        })
    result.sort(key=lambda row: (row["decision_ms"], row["row_id"]))
    return result
