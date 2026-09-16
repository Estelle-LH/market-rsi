"""Bounded, index-aware metadata QA; never a source-admission/model decision.

Run under a separate OS timeout (30 seconds). A progress handler is additional
protection, not a substitute for that timeout. The previously recorded decode
hash is NOT recomputed by this probe; metadata identity is its weaker binding.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import stat
import time


PARTITIONS = {
    "pm_events": ("event_type", "received_at_ms", "ix_pm_events_type_time"),
    "cex_trades": ("symbol", "received_at_ms", "ix_cex_trades_symbol_time"),
    "heartbeats": ("source", "emitted_at_ms", "ix_heartbeats_source_time"),
    "gaps": ("source", "gap_start_ms", "ix_gaps_source_start"),
}


def identity(path):
    p = Path(path)
    if not p.is_absolute() or str(p.resolve()) != str(p):
        raise ValueError("canonical absolute path required")
    s = p.stat()
    if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or s.st_mode & 0o222:
        raise ValueError("single-link read-only regular archive required")
    for suffix in ("-wal", "-shm", "-journal"):
        if os.path.lexists(str(p) + suffix):
            raise ValueError("archive sidecar present")
    return {k: getattr(s, k) for k in
            ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_mode")}


def utc(milliseconds):
    return dt.datetime.fromtimestamp(milliseconds / 1000, dt.timezone.utc).isoformat()


class Audit:
    def __init__(self, path, seconds=20, expected_bytes=None):
        self.path = path
        self.before = identity(path)
        if expected_bytes is not None and self.before["st_size"] != expected_bytes:
            raise ValueError("size differs from decode receipt")
        self.deadline = time.monotonic() + seconds
        self.db = sqlite3.connect(Path(path).as_uri() + "?mode=ro&immutable=1", uri=True)
        self.db.execute("PRAGMA query_only=ON")
        self.db.execute("PRAGMA trusted_schema=OFF")
        self.db.execute("PRAGMA mmap_size=0")
        self.db.execute("PRAGMA cache_size=-8192")
        self.db.execute("PRAGMA temp_store=MEMORY")
        self.db.set_progress_handler(lambda: int(time.monotonic() >= self.deadline), 1000)
        self.plans = []

    def rows(self, sql, args=()):
        if time.monotonic() >= self.deadline:
            raise TimeoutError("metadata audit deadline")
        return self.db.execute(sql, args).fetchall()

    def indexed(self, sql, args, index):
        plan = [r[3] for r in self.rows("EXPLAIN QUERY PLAN " + sql, args)]
        if not any(index in p for p in plan):
            raise ValueError("required index absent from query plan")
        if plan not in self.plans:
            self.plans.append(plan)
        return self.rows(sql, args)

    def keys(self, table):
        key, clock, index = PARTITIONS[table]
        base = f"SELECT {key} FROM {table} INDEXED BY {index}"
        result = []
        for _ in range(33):
            clause = f" WHERE {key} > ?" if result else ""
            values = self.indexed(base + clause + f" ORDER BY {key} LIMIT 1",
                                  (result[-1],) if result else (), index)
            if not values:
                return result
            value = values[0][0]
            if not isinstance(value, str) or not value or len(value) > 160:
                raise ValueError("unexpected partition key")
            result.append(value)
        raise ValueError("partition cardinality exceeds bounded inventory")

    def inventory(self):
        output = {}
        for table, (key, clock, index) in PARTITIONS.items():
            parts = []
            for value in self.keys(table):
                ends = [self.indexed(
                    f"SELECT {clock} FROM {table} INDEXED BY {index} "
                    f"WHERE {key}=? ORDER BY {clock} {order} LIMIT 1", (value,), index)[0][0]
                    for order in ("ASC", "DESC")]
                parts.append({key: value, "first_ms": ends[0], "last_ms": ends[1],
                              "first_utc": utc(ends[0]), "last_utc": utc(ends[1])})
            output[table] = parts
        return output

    def day(self, date):
        day = dt.date.fromisoformat(date)
        if not dt.date(2026, 5, 16) <= day <= dt.date(2026, 6, 30):
            raise ValueError("date outside controller source-QA window")
        start = int(dt.datetime.combine(day, dt.time(), dt.timezone.utc).timestamp() * 1000)
        stop = start + 86_400_000
        output = {}
        for table, (key, clock, index) in PARTITIONS.items():
            all_minutes = set()
            parts = []
            for value in self.keys(table):
                # COUNT reads only the covering index. Minute occupancy seeks
                # directly past each occupied minute, avoiding an N-row GROUP BY
                # temporary B-tree on archives with millions of events per hour.
                clause = (f"FROM {table} INDEXED BY {index} "
                          f"WHERE {key}=? AND {clock}>=? AND {clock}<?")
                count = self.indexed("SELECT COUNT(*) " + clause,
                                     (value, start, stop), index)[0][0]
                minutes = set()
                cursor = start
                while cursor < stop and count:
                    rows = self.indexed(f"SELECT {clock} " + clause +
                                        f" ORDER BY {clock} LIMIT 1",
                                        (value, cursor, stop), index)
                    if not rows:
                        break
                    minute = rows[0][0] // 60000
                    minutes.add(minute)
                    cursor = (minute + 1) * 60000
                if len(minutes) > 1440 or bool(minutes) != bool(count):
                    raise ValueError("invalid UTC minute count")
                all_minutes.update(minutes)
                parts.append({key: value, "rows": count,
                              "occupied_minutes": len(minutes)})
            output[table] = {"partitions": parts, "rows": sum(p["rows"] for p in parts),
                             "occupied_minutes_union": len(all_minutes),
                             "absent_minutes": 1440 - len(all_minutes)}
        return {"date_utc": date, "tables": output,
                "interpretation": "Activity only; not uptime, usable labels, independent samples, or admission. "
                "Gap counts refer to starts inside this date, not overlaps from earlier dates."}

    def calendar(self):
        """Exact day presence from index seeks; min/max span is not coverage."""
        first = dt.date(2026, 5, 16)
        last_exclusive = dt.date(2026, 7, 1)
        start = int(dt.datetime.combine(first, dt.time(), dt.timezone.utc).timestamp() * 1000)
        stop = int(dt.datetime.combine(last_exclusive, dt.time(), dt.timezone.utc).timestamp() * 1000)
        dates = [(first + dt.timedelta(days=i)).isoformat()
                 for i in range((last_exclusive - first).days)]
        output = {}
        for table, (key, clock, index) in PARTITIONS.items():
            union = set()
            partitions = []
            for value in self.keys(table):
                cursor = start
                found = []
                while cursor < stop:
                    rows = self.indexed(
                        f"SELECT {clock} FROM {table} INDEXED BY {index} "
                        f"WHERE {key}=? AND {clock}>=? AND {clock}<? ORDER BY {clock} LIMIT 1",
                        (value, cursor, stop), index)
                    if not rows:
                        break
                    day_start = (rows[0][0] // 86_400_000) * 86_400_000
                    found.append(utc(day_start)[:10])
                    cursor = day_start + 86_400_000
                union.update(found)
                partitions.append({key: value, "present_dates": found})
            output[table] = {"partitions": partitions, "present_dates_union": sorted(union),
                             "absent_dates": [d for d in dates if d not in union]}
        return {"window_first_utc": first.isoformat(), "window_end_exclusive_utc": last_exclusive.isoformat(),
                "tables": output, "interpretation": "Record presence, not a complete session or validation admission."}

    def finish(self):
        self.db.close()
        after = identity(self.path)
        if self.before != after:
            raise ValueError("archive identity changed during read")
        return after


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--expected-bytes", type=int, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--date", help="UTC date; otherwise indexed inventory only")
    mode.add_argument("--calendar", action="store_true")
    args = parser.parse_args()
    started = time.monotonic()
    report = {"stage": "source_metadata_qa", "source_admitted": False,
              "prices_payloads_labels_read": False, "fresh_validation_claim": False,
              "full_sha256_recomputed": False, "path": args.path,
              "audit_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    audit = None
    try:
        audit = Audit(args.path, expected_bytes=args.expected_bytes)
        report["observations"] = (audit.calendar() if args.calendar else
                                  audit.day(args.date) if args.date else audit.inventory())
        report["status"] = "complete"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        if audit:
            report["query_plans"] = audit.plans
            try:
                report["unchanged_identity"] = audit.finish()
            except Exception as exc:
                report["status"] = "failed"
                report["identity_error"] = type(exc).__name__ + ": " + str(exc)
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
