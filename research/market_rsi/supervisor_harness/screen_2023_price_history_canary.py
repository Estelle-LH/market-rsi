"""Three fixed 2023 NFL markets: public minute-price availability diagnostic.

The endpoint's price semantics are not assumed to equal trades or executable
quotes. Save raw responses only to ignored local artifacts; the public report
contains counts and hashes, never prices or game outcomes. No model is scored.
"""

from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from statistics import median
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from supervisor_harness.screen_2023_archive_catalog import encoded, sha


BASE_URL = "https://clob.polymarket.com/prices-history"
MAX_RESPONSE_BYTES = 2_000_000


def summarize(raw: bytes, lower: int, kickoff: int, upper: int) -> dict:
    doc = json.loads(raw)
    history = doc.get("history")
    if not isinstance(history, list):
        raise ValueError("price-history response lacks history array")
    stamps: list[int] = []
    prices: list[Decimal] = []
    for item in history:
        stamp = int(item["t"])
        price = Decimal(str(item["p"]))
        if not lower <= stamp <= upper or not price.is_finite() or not 0 <= price <= 1:
            raise ValueError("invalid price-history timestamp or price")
        if stamps and stamp <= stamps[-1]:
            raise ValueError("timestamps must strictly increase")
        stamps.append(stamp)
        prices.append(price)
    changes = sum(a != b for a, b in zip(prices, prices[1:]))
    run = longest = 0
    for index, price in enumerate(prices):
        run = run + 1 if index and price == prices[index - 1] else 1
        longest = max(longest, run)
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    return {"points": len(stamps), "pre_game_points": sum(t < kickoff for t in stamps),
            "game_to_plus_five_hours_points": sum(t >= kickoff for t in stamps),
            "unique_price_values": len(set(prices)), "consecutive_price_changes": changes,
            "max_flat_run_points": longest,
            "median_gap_seconds": median(gaps) if gaps else None,
            "max_gap_seconds": max(gaps, default=None),
            "first_timestamp": stamps[0] if stamps else None,
            "last_timestamp": stamps[-1] if stamps else None}


def fetch(token: str, lower: int, upper: int) -> tuple[bytes, str]:
    url = BASE_URL + "?" + urlencode({"market": token, "startTs": lower,
                                      "endTs": upper, "fidelity": 1})
    req = Request(url, headers={"User-Agent": "market-rsi-p0-price-canary/1.0"})
    with urlopen(req, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"price-history HTTP {response.status}")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("price-history response exceeds cap")
    return raw, url


def screen(mapping_dir: Path, fills_dir: Path, output: Path) -> dict:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    mapping_raw = (mapping_dir / "mapping.json").read_bytes()
    fill_manifest = json.loads((fills_dir / "manifest.json").read_text())
    fill_raw = (fills_dir / "results.json").read_bytes()
    if (fill_manifest.get("schema") != "market_p0_2023_fixed_fill_canary_v1"
            or fill_manifest.get("results_sha256") != sha(fill_raw)
            or fill_manifest.get("mapping_sha256_verified") != sha(mapping_raw)):
        raise ValueError("fixed fill canary or identity mapping changed")
    mapping = {row["game_id"]: row for row in json.loads(mapping_raw)}
    fill_rows = json.loads(fill_raw)
    if len(fill_rows) != 3:
        raise ValueError("expected exactly three preselected games")
    results, bodies = [], []
    for item in fill_rows:
        tokens = mapping[item["game_id"]]["token_ids"]
        if len(tokens) != 2:
            raise ValueError("candidate does not have exactly two tokens")
        token = sorted(tokens)[0]  # fixed before reading any price value
        kickoff = item["kickoff_epoch_utc"]
        lower, upper = kickoff - 12*3600, kickoff + 5*3600
        raw, url = fetch(token, lower, upper)
        metrics = summarize(raw, lower, kickoff, upper)
        results.append({"game_id": item["game_id"], "token_selection": "lexicographically first",
                        "token_id": token, "source_url": url, "response_bytes": len(raw),
                        "response_sha256": hashlib.sha256(raw).hexdigest(), **metrics})
        bodies.append(raw)
    result_raw = encoded(results)
    report = {"schema": "market_p0_2023_fixed_price_history_canary_v1",
              "mapping_sha256_verified": sha(mapping_raw),
              "fill_canary_sha256_verified": sha(fill_raw),
              "results_sha256": sha(result_raw), "games": len(results),
              "history_price_semantics_verified": False,
              "executable_quote_history_verified": False,
              "event_aligned_labels_verified": False,
              "formal_data_admitted": False, "provider_cost_usd": "0"}
    output.mkdir(parents=True, exist_ok=False)
    for index, body in enumerate(bodies):
        (output / f"price-{index:02d}.raw.json").write_bytes(body)
    (output / "results.json").write_bytes(result_raw)
    (output / "manifest.json").write_bytes(encoded(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--fills", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-public-price-requests", action="store_true")
    args = parser.parse_args()
    if not args.execute_public_price_requests:
        parser.error("refusing public price requests without explicit flag")
    print(json.dumps(screen(args.mapping, args.fills, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
