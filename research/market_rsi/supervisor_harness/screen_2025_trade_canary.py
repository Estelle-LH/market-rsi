"""One chronological 2025 NFL moneyline trade-availability canary.

Selection uses the earliest mapped game, never scores, prices, volumes or
model outcomes. This is a bounded public-source screen, not season coverage,
label admission, a trained model, or a scored trial.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from sports_event_research.fetch_polymarket_trade_canary import fetch_page, validate
from supervisor_harness.screen_2025_schedule import load_events


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def select(mapping_dir: Path, catalog: Path) -> dict:
    report = json.loads((mapping_dir / "manifest.json").read_text())
    if (report["formal_data_admitted"] or report["trade_coverage_verified"]
            or report["mapped_unique_games"] != report["schedule_games"]):
        raise ValueError("expected complete unadmitted 2025 schedule screen")
    raw = (mapping_dir / "mapping.json").read_bytes()
    if sha(raw) != report["mapping_sha256"]:
        raise ValueError("mapping hash changed")
    mapping = json.loads(raw)
    chosen = min(mapping, key=lambda row: (row["game_date"], row["event_id"]))
    events, _ = load_events(catalog)
    matches = [row for row in events if str(row["id"]) == chosen["event_id"]]
    if len(matches) != 1:
        raise ValueError("selected event missing or duplicate")
    event = matches[0]
    markets = [row for row in event.get("markets") or []
               if str(row.get("conditionId")) == chosen["condition_id"]]
    if len(markets) != 1:
        raise ValueError("selected moneyline missing or duplicate")
    tokens = markets[0].get("clobTokenIds")
    if isinstance(tokens, str):
        tokens = json.loads(tokens)
    if not isinstance(tokens, list) or len(tokens) != 2 or not all(tokens):
        raise ValueError("selected market lacks two tokens")
    start = str(event.get("eventStartTime") or event.get("startTime") or "")
    if not start:
        raise ValueError("selected game start missing")
    return {"selection_rule": "earliest mapped 2025 game by date and event ID",
            "game_id": chosen["game_id"], "event_id": chosen["event_id"],
            "event_start_utc": start, "condition_id": chosen["condition_id"],
            "clob_token_ids": [str(token) for token in tokens]}


def screen(mapping_dir: Path, catalog: Path, output: Path, timeout: float = 30) -> dict:
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    selection = select(Path(mapping_dir).resolve(), Path(catalog).resolve())
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    selection_bytes = (json.dumps(selection, indent=2, sort_keys=True) + "\n").encode()
    (output / "selection.json").write_bytes(selection_bytes)
    start = datetime.fromisoformat(selection["event_start_utc"].replace("Z", "+00:00"))
    lower = int((start - timedelta(hours=12)).timestamp())
    upper = int((start + timedelta(hours=5)).timestamp())
    pages, trades = [], []
    for page, offset in enumerate((0, 10000)):
        raw, url = fetch_page(selection["condition_id"], offset, lower, upper, timeout)
        (output / f"trades-page-{page:03d}.raw.json").write_bytes(raw)
        batch = json.loads(raw)
        if not isinstance(batch, list):
            raise ValueError("public trade endpoint did not return a list")
        pages.append({"url": url, "sha256": sha(raw), "bytes": len(raw), "rows": len(batch)})
        trades.extend(batch)
        if len(batch) < 10000:
            break
    if len(pages) == 2 and pages[-1]["rows"] == 10000:
        raise ValueError("trade canary hit 20,000-row cap; no completeness claim")
    summary = validate(trades, selection)
    if any(not lower <= int(row["timestamp"]) <= upper for row in trades):
        raise ValueError("trade endpoint ignored time bound")
    start_ts = int(start.timestamp())
    report = {"schema": "market_p0_2025_trade_canary_v1",
              "generated_utc": datetime.now(timezone.utc).isoformat(),
              "selection_sha256": sha(selection_bytes), "page_receipts": pages,
              "window": {"start_timestamp": lower, "game_start_timestamp": start_ts,
                         "end_timestamp": upper},
              "window_summary": summary,
              "pre_game_trades": sum(int(row["timestamp"]) < start_ts for row in trades),
              "game_plus_five_hours_trades": sum(int(row["timestamp"]) >= start_ts for row in trades),
              "season_trade_coverage_verified": False,
              "event_aligned_labels_verified": False,
              "formal_data_admitted": False, "provider_cost_usd": "0"}
    (output / "manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    print(json.dumps(screen(args.mapping, args.catalog, args.output, args.timeout), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
