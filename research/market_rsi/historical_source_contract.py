"""Source-aware projection and causal feature access, not training admission.

Raw timestamps/IDs remain evidence, never globally unique keys or filename-derived
clocks. These functions are the executable boundary for a future controller-chosen
data-use plan. They do not select dates, forecast targets, staleness or objectives.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import PurePosixPath
import re

from historical_ingest_controller import DATASET, REVISION
from market_rsi import digest


CANDLE_MS = {f"binance_candles_{k}": v for k, v in
             {"1s": 1000, "5s": 5000, "1m": 60_000, "5m": 300_000,
              "15m": 900_000, "1h": 3_600_000}.items()}
CLOCK_ASSUMPTION = "publisher_recorded_arrival_as_research_proxy"


def contract():
    value = {
        "schema": "historical_source_contract_v1", "dataset": DATASET, "revision": REVISION,
        "physical_identity": ["dataset", "revision", "relative_path", "sha256", "raw_row_ordinal"],
        "forbidden_join_or_dedup_keys": ["synthetic_id_alone", "filename_date_as_event_date"],
        "streams": {
            "polymarket_ticks_ms": {"types": ["reported_top_quote", "book_level_delta"],
                "midpoint": "derive_only_from_valid_reported_bid_and_ask",
                "price_change_price": "changed_book_level_not_trade_or_midpoint",
                "size": "changed_level_size_not_verified_top_depth_or_trade_volume",
                "arrival_clock": "ingest_ts_ms", "source_clock": "source_ts_ms"},
            "binance_ticks_ms": {"types": ["collector_trade_sample"], "price": "trade_price",
                "arrival_clock": "ingest_ts_ms", "source_clock": "source_ts_ms",
                "verified_bbo_available": False, "cross_stream_trade_join_key_available": False},
            "binance_trades": {"types": ["exchange_trade_record"], "price": "trade_price",
                "arrival_clock": "received_at", "source_clock": "trade_time",
                "trade_id_scope": "source_dataset_instrument_not_arbitrary_other_streams"},
            "binance_candles": {"types": ["recorded_final_candle"],
                "arrival_clock": "max(created_at,candle_end+1)",
                "reject_if_created_before_close": True, "start_is_not_availability": True},
        },
        "unavailable": ["pm_trade_tape", "pm_trade_vwap", "resolution_outcome",
                        "verified_binance_midpoint", "true_exchange_tie_order"],
        "same_receipt_timestamp_conflicting_quotes": "ambiguous_no_arbitrary_winner",
        "invalid_latest_quote": "unknown_no_fallback_to_older_valid_quote",
        "raw_records_deleted": False, "fill_missing_values": False,
        "requires_explicit_clock_assumption": CLOCK_ASSUMPTION,
        "historical_deployed_collector_verified": False,
        "numeric_quote_validity_proves_execution": False,
        "automatic_training_admission": False,
        "controller_chooses": ["data_use_and_dates", "sampling_clock_and_cadence", "max_age_ms",
                              "features", "training_objectives", "forecast_horizon"],
    }
    return {**value, "contract_sha256": digest(value)}


def physical_reference(item: dict, ordinal: int) -> dict:
    path = PurePosixPath(item["path"])
    if (path.is_absolute() or ".." in path.parts or len(path.parts) != 4
            or path.parts[0] != "unified" or not path.name.endswith(".parquet")
            or not re.fullmatch(r"[0-9a-f]{64}", item.get("lfs_sha256", ""))
            or type(ordinal) is not int or ordinal < 0):
        raise ValueError("invalid immutable source reference")
    value = {"dataset": DATASET, "revision": REVISION, "relative_path": str(path),
             "sha256": item["lfs_sha256"], "raw_row_ordinal": ordinal}
    return {**value, "physical_row_id": digest(value)}


def _ms(value):
    if type(value) is not int or not 946_684_800_000 <= value < 4_102_444_800_000:
        raise ValueError("integer epoch-ms clock required")
    return value


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def project(row: dict, item: dict, ordinal: int, *, metadata: dict | None = None) -> dict:
    """Project one row; invalid observations survive with flags and no feature value."""
    ref = physical_reference(item, ordinal)
    stream = PurePosixPath(item["path"]).parts[1]
    flags, values = [], {}
    entity = None
    if stream == "polymarket_ticks_ms":
        event, arrival = _ms(row["source_ts_ms"]), _ms(row["ingest_ts_ms"])
        market, asset = row.get("market_slug"), row.get("asset_id")
        entity = [market, asset]
        kind = row.get("event_type", "").lower()
        if kind not in {"book", "price_change"}:
            flags.append("unsupported_pm_event")
        if not metadata or not market or not asset or asset not in metadata.get(market, set()):
            flags.append("token_market_identity_unverified_or_mismatched")
        bid, ask = row.get("best_bid"), row.get("best_ask")
        if not (_finite(bid) and _finite(ask) and 0 <= bid <= ask <= 1):
            flags.append("reported_bbo_missing_nonfinite_out_of_range_or_crossed")
        else:
            values.update(reported_bid=float(bid), reported_ask=float(ask))
            if not flags:
                values["midpoint_from_reported_bbo"] = (float(bid) + float(ask)) / 2
        if kind == "price_change":
            price, size = row.get("price"), row.get("size")
            if not (_finite(price) and 0 <= price <= 1 and _finite(size) and size >= 0):
                flags.append("invalid_reported_book_level_delta")
            else:
                values.update(reported_level_price=float(price), reported_level_size=float(size))
        event_kind = "reported_top_quote_with_book_delta" if kind == "price_change" else "reported_book_quote"
    elif stream in {"binance_ticks_ms", "binance_trades"}:
        ticks = stream == "binance_ticks_ms"
        event = _ms(row["source_ts_ms"] if ticks else row["trade_time"])
        arrival = _ms(row["ingest_ts_ms"] if ticks else row["received_at"])
        price, quantity = row.get("price"), row.get("volume") if ticks else row.get("quantity")
        if not (_finite(price) and price > 0 and _finite(quantity) and quantity >= 0):
            flags.append("invalid_trade_price_or_quantity")
        else:
            values.update(trade_price=float(price), trade_quantity=float(quantity))
        if ticks and _ms(row["trade_time_ms"]) != event:
            flags.append("trade_time_source_time_disagreement")
        event_kind = "collector_trade_sample" if ticks else "exchange_trade_record"
    elif stream in CANDLE_MS:
        start, end, created = _ms(row["candle_start"]), _ms(row["candle_end"]), _ms(row["created_at"])
        event, arrival = end, max(created, end + 1)
        if end - start + 1 != CANDLE_MS[stream] or start % CANDLE_MS[stream]:
            flags.append("candle_interval_mismatch")
        if created < end + 1:
            flags.append("candle_recorded_before_final_close")
        o, h, l, c = (row.get(k + "_price") for k in ("open", "high", "low", "close"))
        if not all(_finite(v) and v > 0 for v in (o, h, l, c)) or not (l <= min(o, c) <= max(o, c) <= h):
            flags.append("invalid_candle_ohlc")
        else:
            values.update(open_price=float(o), high_price=float(h), low_price=float(l), close_price=float(c))
        values.update(candle_start_ms=start, candle_end_ms=end, recorded_created_at_ms=created)
        event_kind = "recorded_final_candle"
    else:
        raise ValueError("source stream has no executable semantic contract")
    if arrival < event:
        flags.append("arrival_precedes_source_event")
    return {"schema": "historical_record_projection_v1", "stream": stream, "event_kind": event_kind,
            "source": ref, "raw_source_id": row.get("id", row.get("trade_id")), "entity": entity,
            "source_event_ms": event, "recorded_available_ms": arrival,
            "event_utc_date": datetime.fromtimestamp(event / 1000, timezone.utc).date().isoformat(),
            "arrival_utc_date": datetime.fromtimestamp(arrival / 1000, timezone.utc).date().isoformat(),
            "source_partition_label": PurePosixPath(item["path"]).parts[2],
            "values": values, "quality_flags": flags,
            "publisher_clock_assumption_required": CLOCK_ASSUMPTION,
            "training_admitted": False, "executable_price_verified": False}


def require_causal_feature(record: dict, feature: str, decision_ms: int, *,
                           max_age_ms: int, clock_assumption: str):
    _ms(decision_ms)
    if clock_assumption != CLOCK_ASSUMPTION:
        raise ValueError("explicit publisher-clock research assumption required")
    if type(max_age_ms) is not int or max_age_ms < 0:
        raise ValueError("controller-selected nonnegative max_age_ms required")
    if record["recorded_available_ms"] > decision_ms:
        raise ValueError("future observation not yet available")
    if record["quality_flags"]:
        raise ValueError("flagged source observation cannot supply a feature")
    if max(decision_ms - record["source_event_ms"], decision_ms - record["recorded_available_ms"]) > max_age_ms:
        raise ValueError("observation exceeds declared staleness")
    if feature not in record["values"]:
        raise ValueError("feature unavailable for this source; no price alias or imputation")
    return record["values"][feature]


def latest_reported_midpoint(records: list[dict], entity: list[str], decision_ms: int, *,
                              max_age_ms: int, clock_assumption: str):
    """Bounded replay primitive; conflicting ties or invalid latest state stay unknown."""
    if len(records) > 100_000:
        raise ValueError("bounded replay batch required")
    visible = [r for r in records if r["stream"] == "polymarket_ticks_ms"
               and r["entity"] == entity and r["recorded_available_ms"] <= decision_ms]
    if not visible:
        return {"value": None, "reason": "no_visible_quote", "sources": []}
    latest = max(r["recorded_available_ms"] for r in visible)
    group = [r for r in visible if r["recorded_available_ms"] == latest]
    sources = [r["source"]["physical_row_id"] for r in group]
    try:
        quotes = [(require_causal_feature(r, "reported_bid", decision_ms, max_age_ms=max_age_ms,
                                          clock_assumption=clock_assumption),
                   require_causal_feature(r, "reported_ask", decision_ms, max_age_ms=max_age_ms,
                                          clock_assumption=clock_assumption)) for r in group]
    except ValueError as exc:
        return {"value": None, "reason": str(exc), "sources": sources}
    if len(set(quotes)) != 1:
        return {"value": None, "reason": "conflicting_same_receipt_timestamp_quotes", "sources": sources}
    return {"value": sum(quotes[0]) / 2, "reason": "reported_bbo_only_not_execution_proof",
            "sources": sources, "available_ms": latest}
