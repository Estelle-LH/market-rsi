"""Runner-frozen evidence catalog for prediction-market data discovery.

This catalog is evidence, not a winner.  The controller must compare sources,
write an acquisition plan, and pass a local canary before a full download.
"""
from __future__ import annotations

import copy

from market_rsi import digest


SCHEMA = "market_data_source_catalog_v1"


_SOURCES = {
    "current-private-polymarket-capture": {
        "kind": "real_private_history",
        "provider": "existing project capture",
        "primary_evidence_url": None,
        "coverage": "measured from the bound local opened-Train audit",
        "available_streams": ["top_of_book_quotes"],
        "known_limitations": [
            "the current formal materialization spans only a small number of UTC days and games",
            "trade and resolution streams are not verified in the current source inventory",
        ],
        "access": "already local",
        "license_status": "private_project_data",
        "full_download_allowed_before_canary": False,
    },
    "openmarket-v0.4.3-unified": {
        "kind": "real_public_history",
        "provider": "OpenMarket",
        "primary_evidence_url": "https://github.com/gregyoung14/openmarket/blob/main/datasets/hf/README.md",
        "coverage": "202 SQLite snapshots; unified split has about 727M deduplicated rows and 504 Parquet files",
        "snapshot_archive_range": "2026-03-14T19:32:15Z through 2026-07-01T02:56:54Z",
        "verified_tick_partition_coverage": (
            "at revision 74502466d1a7cef56395bfd8d0b465fbebc849cf, "
            "54 Polymarket tick UTC-date partitions span 2026-02-12 through 2026-05-15"
        ),
        "available_streams": [
            "binance_trades", "binance_top_of_book", "polymarket_top_of_book",
            "synchronized_lag_pairs", "market_metadata",
        ],
        "known_limitations": [
            "BTC-linked binary markets rather than the full prediction-market universe",
            "2026-04-22 through 2026-05-12 is a documented collection gap",
            "top-of-book backtests may overstate executable fill quality",
            "collector clock drift and reconnect gaps require audit",
            "snapshot/export dates must not be mistaken for underlying tick coverage dates",
        ],
        "access": "public Hugging Face dataset with a 9,352-row sample split",
        "license_status": "apache-2.0_in_published_dataset_card",
        "full_download_allowed_before_canary": False,
    },
    "kalshi-historical-api": {
        "kind": "real_public_api_history",
        "provider": "Kalshi",
        "primary_evidence_url": "https://docs.kalshi.com/getting_started/historical_data",
        "coverage": "historical markets, trades, and market candlesticks; exact requested universe must be inventoried",
        "available_streams": ["trades", "candles_1m", "candles_60m", "candles_1d", "market_metadata"],
        "known_limitations": [
            "documented historical endpoint is not a full historical level-2 order-book replay",
            "the v1.1 Developer Agreement limits API use to a member's own trading",
            "the v1.1 Developer Agreement prohibits collecting, caching, aggregating, or storing API data except for one's own Kalshi trading",
            "academic model-research storage therefore requires prior written authorization from Kalshi",
            "pagination, rate limits, credentials, and exact retained history need a canary only after the terms gate passes",
        ],
        "access": "official historical API",
        "license_status": "written_authorization_required_for_nontrading_research_storage",
        "terms_evidence_url": "https://kalshi-public-docs.s3.amazonaws.com/Kalshi-Developer-Agreement.pdf",
        "terms_evidence_version": "v1.1",
        "research_data_access_status": "rejected_without_prior_written_authorization",
        "full_download_allowed_before_canary": False,
    },
    "polymarket-official-apis": {
        "kind": "real_public_api_history",
        "provider": "Polymarket",
        "primary_evidence_url": "https://institute.polymarket.com/data",
        "coverage": "market metadata, price history, trades, positions, and current order-book data; exact historical depth must be inventoried",
        "available_streams": ["price_history", "trades", "market_metadata", "resolution_metadata", "current_order_book"],
        "known_limitations": [
            "price history is not equivalent to a replayable historical order book",
            "the decentralized and US exchanges have separate APIs",
            "pagination, retention, and timestamp semantics need a canary",
            "the Institute advertises research access, but an explicit storage and redistribution license was not verified",
        ],
        "access": "official open data APIs",
        "license_status": "research_access_advertised_reuse_terms_unresolved",
        "research_data_access_status": "rejected_for_new_acquisition_until_reuse_terms_resolve",
        "full_download_allowed_before_canary": False,
    },
    "synthetic-market-simulator": {
        "kind": "synthetic_research_only",
        "provider": "not_implemented",
        "primary_evidence_url": None,
        "coverage": "none",
        "available_streams": [],
        "known_limitations": [
            "a simulator can reproduce its assumptions instead of real market behavior",
            "it cannot be the primary Train evidence or any Dev/Test evidence until validated against real held-out data",
        ],
        "access": "not available",
        "license_status": "not_applicable",
        "full_download_allowed_before_canary": False,
    },
}


def data_source_catalog() -> dict:
    sources = [
        {"source_id": source_id, **copy.deepcopy(spec)}
        for source_id, spec in sorted(_SOURCES.items())
    ]
    body = {
        "schema": SCHEMA,
        "sources": sources,
        "catalog_is_exhaustive": False,
        "catalog_selects_a_winner": False,
        "evidence_frozen_at": "2026-09-09",
        "admission_rule": (
            "No source enters a formal experiment until a bounded sample canary verifies "
            "access, license/terms status, schema, timestamps, gaps, duplication, and replayability."
        ),
    }
    return {**body, "catalog_sha256": digest(body)}


def get_data_source(source_id: str) -> dict:
    for source in data_source_catalog()["sources"]:
        if source["source_id"] == source_id:
            return source
    raise ValueError("unknown data source ID")
