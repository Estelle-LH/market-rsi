"""Read-only archive breadth audit; metadata is not valid quote coverage.

No market scores, labels, fitting, network, or writes. Event keys below are
candidate groups from the observed ticker convention, not proof of event identity
across market families. Detail is limited to one declared GAME series.
"""
import argparse
import collections
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path


COLUMNS = {"venue", "market", "outcome", "league", "matchup", "outcome_label", "game_start_utc", "market_slug"}


def summarize(daily, *, family="KXMLBGAME", provisional_boundary="2026-09-03"):
    date.fromisoformat(provisional_boundary)
    if not family.isalnum() or not family.endswith("GAME"):
        raise ValueError("explicit observed GAME series required")
    families, detail, sources = {}, {}, []
    last_day = None
    for item in daily:
        day, rows = item["day"], item["rows"]
        date.fromisoformat(day)
        if last_day is not None and day <= last_day:
            raise ValueError("unique chronological source days required")
        last_day = day
        native = [r for r in rows if r.get("venue", "").lower() == "kalshi"]
        bad = 0
        for row in native:
            if set(row) != COLUMNS:
                raise ValueError("unrecognized market metadata schema")
            parts = row["market"].split("-")
            if len(parts) != 3 or not all(parts) or parts[-1] != row["outcome"]:
                bad += 1
                continue
            series, event = parts[0], "-".join(parts[:-1])
            stats = families.setdefault(series, {"contracts": set(), "candidate_events": set(), "source_days": set()})
            stats["contracts"].add(row["market"])
            stats["candidate_events"].add(event)
            stats["source_days"].add(day)
            if series != family:
                continue
            group = detail.setdefault(event, {"event_key": event, "contracts": set(), "source_days": set(),
                "start_days": set(), "start_timestamps": set(), "matchups": set(), "leagues": set(),
                "invalid_or_missing_start_rows": 0})
            group["contracts"].add(row["market"])
            group["source_days"].add(day)
            group["matchups"].add(row["matchup"])
            group["leagues"].add(row["league"])
            try:
                start = datetime.fromisoformat(row["game_start_utc"].replace("Z", "+00:00"))
                if start.tzinfo is None:
                    raise ValueError("unqualified clock")
                start = start.astimezone(timezone.utc)
                group["start_days"].add(start.date().isoformat())
                group["start_timestamps"].add(start.isoformat())
            except ValueError:
                group["invalid_or_missing_start_rows"] += 1
        sources.append({k: item[k] for k in ("day", "path", "sha256", "bytes")})
        sources[-1].update(all_venue_rows=len(rows), native_kalshi_rows=len(native),
                           unrecognized_native_ticker_rows=bad)
    if not sources:
        raise ValueError("no source metadata")
    first, last = sources[0]["day"], sources[-1]["day"]
    by_start_day = collections.Counter()
    eligible_metadata = []
    for event, group in sorted(detail.items()):
        consistent = (group["invalid_or_missing_start_rows"] == 0 and len(group["start_timestamps"]) == 1
                      and len(group["matchups"]) == 1 and "" not in group["matchups"]
                      and len(group["leagues"]) == 1 and "" not in group["leagues"])
        group["metadata_consistent"] = consistent
        if consistent:
            day = next(iter(group["start_days"]))
            by_start_day[day] += 1
            eligible_metadata.append(group)
    starts_train = sum(1 for g in eligible_metadata if first <= next(iter(g["start_days"])) < provisional_boundary)
    starts_dev = sum(1 for g in eligible_metadata if provisional_boundary <= next(iter(g["start_days"])) <= last)
    shared = [g["event_key"] for g in detail.values()
              if any(d < provisional_boundary for d in g["source_days"])
              and any(d >= provisional_boundary for d in g["source_days"])]
    return {"schema": "market_metadata_breadth_diagnostic_v1", "scoring_ready": False,
        "evidence_class": "metadata_only_diagnostic", "family": family,
        "provisional_boundary_utc": provisional_boundary, "sources": sources,
        "families": {key: {name: len(value) for name, value in stats.items()}
                     for key, stats in sorted(families.items())},
        "family_summary": {"candidate_events": len(detail), "consistent_metadata_events": len(eligible_metadata),
            "inconsistent_metadata_events": len(detail) - len(eligible_metadata),
            "events_mentioned_on_multiple_capture_days": sum(len(g["source_days"]) > 1 for g in detail.values()),
            "candidate_start_dates_utc": dict(sorted(by_start_day.items())),
            "starts_in_provisional_train_date_range": starts_train,
            "starts_in_provisional_dev_date_range": starts_dev,
            "event_keys_in_both_provisional_file_partitions": sorted(shared)},
        "events": [{k: sorted(v) if isinstance(v, set) else v for k, v in group.items()}
                   for _, group in sorted(detail.items())],
        "limitations": ["A listed contract does not prove actual quotes, snapshot anchors or valid labels.",
            "game_start_utc is source-derived metadata, not independently verified event time.",
            "Distinct games can still be dependent; counts are not an effective sample size.",
            "Previously inspected history is not untouched final-test evidence.",
            "No source clock/session admission, final split, model result or PnL is established."]}


def inventory(root, start_day, end_day):
    start, end = date.fromisoformat(start_day), date.fromisoformat(end_day)
    if not 0 <= (end - start).days < 31:
        raise ValueError("bounded chronological date range required")
    rows = []
    for offset in range((end - start).days + 1):
        day = (start + timedelta(days=offset)).isoformat()
        path = Path(root) / day / f"markets_{day}.csv"
        if path.is_symlink() or path.parent.is_symlink() or path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("bounded regular metadata source required")
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
        if before.st_mtime_ns != after.st_mtime_ns or before.st_size != after.st_size or len(raw) != before.st_size:
            raise ValueError("metadata source changed during read")
        reader = csv.DictReader(io.StringIO(raw.decode()))
        if set(reader.fieldnames or []) != COLUMNS:
            raise ValueError("unknown source metadata header")
        rows.append({"day": day, "path": str(path), "bytes": len(raw),
                     "sha256": hashlib.sha256(raw).hexdigest(), "rows": list(reader)})
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("start_day")
    parser.add_argument("end_day")
    parser.add_argument("--family", default="KXMLBGAME")
    parser.add_argument("--boundary", default="2026-09-03")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    result = summarize(inventory(args.root, args.start_day, args.end_day),
                       family=args.family, provisional_boundary=args.boundary)
    if args.summary_only:
        result["event_detail_sha256"] = hashlib.sha256(json.dumps(result.pop("events"), sort_keys=True).encode()).hexdigest()
        result["event_detail_note"] = "Full details reproducible from these exact CSV hashes and this script; not copied in summary mode."
    print(json.dumps(result, sort_keys=True))
