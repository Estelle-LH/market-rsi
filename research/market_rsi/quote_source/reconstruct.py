"""Causal source BBO / depth separation. Standard library only; no I/O."""
from decimal import Decimal, InvalidOperation
import re

VERSION = "pm-source-quotes-v0.1.0"


def decimal_value(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("non-numeric")
    if len(str(value)) > 64:
        raise ValueError("numeric length")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("non-numeric") from exc
    if not result.is_finite() or abs(result) > Decimal("1e18"):
        raise ValueError("nonfinite or excessive numeric value")
    return result


def price(value):
    result = decimal_value(value)
    if not 0 <= result <= 1:
        raise ValueError("price outside probability-dollar bounds")
    return result


def timestamp(value):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]{13}", str(value)):
        raise ValueError("millisecond epoch required")
    return int(value)


def pair_status(bid, ask):
    if bid is None and ask is None:
        return "missing"
    if bid is None or ask is None:
        return "one_sided"
    if bid > ask:
        return "crossed"
    if bid == ask:
        return "locked"
    if bid in (0, 1) or ask in (0, 1):
        return "boundary_unknown"
    return "uncrossed"


def text_number(value):
    return None if value is None else str(value)


def snapshot_levels(message, max_levels):
    result = {}
    for side in ("bids", "asks"):
        levels = message.get(side)
        if not isinstance(levels, list) or len(levels) > max_levels:
            raise ValueError("complete bounded snapshot required")
        parsed = {}
        for level in levels:
            if not isinstance(level, dict):
                raise ValueError("level object required")
            px, quantity = price(level.get("price")), decimal_value(level.get("size"))
            if px in parsed or quantity < 0:
                raise ValueError("duplicate level or negative size")
            parsed[px] = quantity
        result[side] = {px: q for px, q in parsed.items() if q > 0}
    return result


class QuoteReconstructor:
    """One historically named asset/market pair; inputs never come from Gamma.

    Rows returned by process() contain local source identifiers/values. They
    belong in the runner's data store, NOT in an external-controller prompt.
    The validation runner only exports aggregate counts and provenance hashes.
    """
    def __init__(self, asset_id, market, *, max_levels=10000):
        if not isinstance(asset_id, str) or not asset_id or not isinstance(market, str) or not market:
            raise ValueError("exact asset and market required")
        self.asset_id, self.market, self.max_levels = asset_id, market, max_levels
        self.book = None
        self.last_ordinal = 0
        self.clock_highwater = {}

    def _clocks(self, record, message):
        issues, clocks = [], {}
        for name, value in (("capture_ms", record.get("t")), ("source_ms", message.get("timestamp"))):
            try:
                clocks[name] = timestamp(value)
                prior = self.clock_highwater.get(name)
                if prior is not None and clocks[name] < prior:
                    issues.append(name + "_regression")
                self.clock_highwater[name] = max(prior or clocks[name], clocks[name])
            except ValueError:
                clocks[name] = None
                issues.append(name + "_missing_or_invalid")
        return clocks, issues

    def _row(self, key, sha, kind, clocks, issues, bid, ask, origin,
             *, snapshot=None, snapshot_equal=None):
        depth_bid = max(self.book["bids"], default=None) if self.book is not None else None
        depth_ask = min(self.book["asks"], default=None) if self.book is not None else None
        source_status = pair_status(bid, ask)
        depth_status = pair_status(depth_bid, depth_ask) if self.book is not None else "unanchored"
        match = (depth_bid, depth_ask) == (bid, ask) if self.book is not None and bid is not None and ask is not None else None
        # Never borrow quantities from a delta-reconstructed book for source BBO.
        sizes = {"bid_size": None, "ask_size": None}
        if snapshot is not None:
            sizes = {"bid_size": text_number(snapshot["bids"].get(bid)),
                     "ask_size": text_number(snapshot["asks"].get(ask))}
        return {"schema": "polymarket_source_quote_v1", "adapter_version": VERSION,
            "key": list(key), "raw_record_sha256": sha, "asset_id": self.asset_id,
            "market": self.market, "kind": kind, **clocks,
            "clock_semantics_attested": False, "issues": list(issues),
            "source": {"origin": origin, "bid": text_number(bid), "ask": text_number(ask),
                       "status": source_status, **sizes},
            "depth": {"bid": text_number(depth_bid), "ask": text_number(depth_ask),
                      "status": depth_status, "bbo_matches_source": match,
                      "full_map_equals_next_snapshot": snapshot_equal,
                      "executable_certified": False},
            "price_candidate": source_status == "uncrossed" and not issues,
            "source_admitted": False}

    def process(self, record, ordinal, raw_sha256):
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal <= self.last_ordinal:
            raise ValueError("unique strictly increasing raw ordinal required")
        if not isinstance(raw_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", raw_sha256):
            raise ValueError("raw-record sha256 required")
        self.last_ordinal = ordinal
        messages = record.get("m")
        messages = messages if isinstance(messages, list) else [messages]
        rows = []
        for mi, message in enumerate(messages):
            if not isinstance(message, dict):
                # Unknown identity cannot safely be assigned to this asset.
                raise ValueError("message object required")
            kind = message.get("event_type")
            if kind == "price_change":
                changes = message.get("price_changes")
                if not isinstance(changes, list) or any(not isinstance(c, dict) for c in changes):
                    raise ValueError("change array required")
                selected = [(ci, c) for ci, c in enumerate(changes) if c.get("asset_id") == self.asset_id]
            else:
                selected = [(0, message)] if message.get("asset_id") == self.asset_id else []
            if not selected:
                continue
            if message.get("market") != self.market:
                raise ValueError("historical token-market mismatch; no current-cache fallback")
            if kind in ("last_trade_price", "tick_size_change"):
                # Not a quote. Do not invent an observation or infer book changes.
                continue
            clocks, clock_issues = self._clocks(record, message)
            if clock_issues:
                self.book = None
            for ci, change in selected:
                issues = list(clock_issues)
                bid = ask = None
                fresh = equal = None
                origin = "none"
                if kind == "book" or record.get("src") == "rest":
                    origin = "complete_snapshot_levels"
                    try:
                        fresh = snapshot_levels(message, self.max_levels)
                        equal = self.book == fresh if self.book is not None else None
                        bid, ask = max(fresh["bids"], default=None), min(fresh["asks"], default=None)
                        self.book = fresh if not clock_issues else None
                    except ValueError:
                        self.book = None
                        issues.append("malformed_snapshot")
                elif kind in ("price_change", "best_bid_ask"):
                    origin = "same_message_best_bid_ask"
                    if kind == "price_change":
                        try:
                            if change.get("side") not in ("BUY", "SELL"):
                                raise ValueError("side")
                            px, quantity = price(change.get("price")), decimal_value(change.get("size"))
                            if quantity < 0:
                                raise ValueError("negative quantity")
                            if self.book is not None:
                                side = "bids" if change["side"] == "BUY" else "asks"
                                if quantity == 0:
                                    self.book[side].pop(px, None)
                                else:
                                    self.book[side][px] = quantity
                                if len(self.book[side]) > self.max_levels:
                                    raise ValueError("level limit")
                        except ValueError:
                            self.book = None
                            issues.append("malformed_delta")
                    try:
                        bid = price(change["best_bid"]) if change.get("best_bid") is not None else None
                        ask = price(change["best_ask"]) if change.get("best_ask") is not None else None
                    except ValueError:
                        bid = ask = None
                        issues.append("malformed_source_bbo")
                else:
                    self.book = None
                    issues.append("unsupported_target_event")
                rows.append(self._row((ordinal, mi, ci), raw_sha256, kind, clocks, issues,
                    bid, ask, origin, snapshot=fresh, snapshot_equal=equal))
        return rows
