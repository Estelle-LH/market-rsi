"""Read bounded activity diagnostics from one frozen, read-only SQLite archive.

Not a downloader or admission gate. The caller owns acquisition permission,
decompressed-file provenance and exposure logging. Only activity metadata from
three tables is read; payloads, prices, targets and models are not inspected.
SQLite immutable mode requires a genuinely quiescent archive: this reader rejects
writable files and sidecars, and rechecks identity/hash after inspection. These
checks are not a substitute for OS isolation against concurrent hostile writers.

References: https://www.sqlite.org/uri.html (immutable and mode=ro)
https://www.sqlite.org/pragma.html#pragma_trusted_schema
"""
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import time

from canary_activity_observations import summarize


# Literal, reviewed field projection of the pinned publisher schema. We never
# execute publisher SQL or accept SQL/table names from the caller or the model.
FIELDS = {
    "pm_events": {
        "id": "INTEGER", "received_at_ms": "INTEGER", "subscription_id": "TEXT",
        "event_type": "TEXT", "asset_id": "TEXT", "condition_id": "TEXT",
    },
    "heartbeats": {
        "id": "INTEGER", "emitted_at_ms": "INTEGER", "source": "TEXT",
        "subscription_id": "TEXT", "last_message_age_sec": "REAL",
    },
    "gaps": {
        "id": "INTEGER", "source": "TEXT", "subscription_id": "TEXT",
        "gap_start_ms": "INTEGER", "gap_end_ms": "INTEGER", "detected_at_ms": "INTEGER",
    },
}
PREDICATES = {
    "pm_events": "received_at_ms >= ? AND received_at_ms < ?",
    "heartbeats": "emitted_at_ms >= ? AND emitted_at_ms < ?",
    "gaps": "gap_end_ms > ? AND gap_start_ms < ?",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(s):
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_mode)


def _deadline(end):
    if time.monotonic() >= end:
        raise TimeoutError("bounded SQLite diagnostic deadline exceeded; no completed result")


def _hash_fd(fd, end):
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    while True:
        _deadline(end)
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)


def _check_path(path):
    if not path.is_absolute() or path != path.resolve(strict=True):
        raise ValueError("canonical absolute file path required; no symlink ancestors")
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_mode & 0o222 or s.st_nlink != 1:
        raise ValueError("single-link read-only regular archive required")
    for suffix in ("-wal", "-shm", "-journal"):
        side = Path(str(path) + suffix)
        if side.exists() or side.is_symlink():
            raise ValueError("archive has SQLite sidecar; not a standalone quiescent file")
    return _identity(s)


def _schema(connection):
    result = {}
    for table, fields in FIELDS.items():
        row = connection.execute(
            "SELECT type, sql FROM sqlite_schema WHERE name = ?", (table,)
        ).fetchone()
        if not row or row[0] != "table" or not row[1].lstrip().upper().startswith("CREATE TABLE"):
            raise ValueError(f"{table}: ordinary table required, not view/virtual table")
        columns = {r[1]: r for r in connection.execute(f'PRAGMA table_xinfo("{table}")')}
        for name, kind in fields.items():
            col = columns.get(name)
            if col is None or col[2].upper() != kind or col[6] != 0:
                raise ValueError(f"{table}.{name}: missing/wrong/generated field")
        if columns["id"][5] != 1 or "AUTOINCREMENT" not in row[1].upper() \
                or any(c[5] for name, c in columns.items() if name != "id"):
            raise ValueError(f"{table}: local INTEGER primary key required")
        result[table] = {name: list(columns[name]) for name in fields}
    return result


def inspect_archive(path, *, expected_sha256, expected_bytes, start_ms, end_ms,
                    recorder_scope, max_rows_per_table=10_000, max_seconds=30):
    """Inspect only the chosen window and a bounded PK-ordered prefix per table.

    Reaching a row bound reports partial inspection, never a complete window.
    A query timeout raises and produces no result. Even a complete window query
    does not establish feed quality, role mapping or fresh-test eligibility.
    """
    path = Path(path)
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("exact SHA256 commitment required")
    for value, label in ((expected_bytes, "expected_bytes"), (max_rows_per_table, "row bound")):
        if type(value) is not int or value <= 0:
            raise ValueError(f"positive integer {label} required")
    if max_rows_per_table > 100_000:
        raise ValueError("diagnostic row bound exceeds tested memory limit")
    if type(max_seconds) not in (int, float) or not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError("positive finite deadline required")
    # Validate window/scope before opening any database, including empty cases.
    summarize([], [], [], start_ms=start_ms, end_ms=end_ms, recorder_scope=recorder_scope)
    identity = _check_path(path)
    if identity[2] != expected_bytes:
        raise ValueError("file byte size does not match commitment")
    end = time.monotonic() + max_seconds
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    connection = None
    try:
        if _identity(os.fstat(fd)) != identity or _hash_fd(fd, end) != expected_sha256:
            raise ValueError("file identity/hash does not match commitment")
        connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1&cache=private", uri=True)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute("PRAGMA mmap_size=0")
        connection.execute("PRAGMA cache_size=-8192")
        if connection.execute("PRAGMA query_only").fetchone() != (1,) or \
                connection.execute("PRAGMA trusted_schema").fetchone() != (0,):
            raise ValueError("required SQLite read protections unavailable")
        if hasattr(connection, "setconfig"):
            connection.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
        # Extension loading is disabled by default. Some Python builds omit it.
        if hasattr(connection, "enable_load_extension"):
            connection.enable_load_extension(False)
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_048_576)
        connection.set_progress_handler(lambda: int(time.monotonic() >= end), 1000)
        schema = _schema(connection)
        tables, query_reports = {}, {}
        for table, fields in FIELDS.items():
            _deadline(end)
            names = list(fields)
            # Fixed rowid scan avoids an unbounded temporary sort. It may time out
            # for a late window in a large file; timeout is not a complete scan.
            query = f'SELECT {", ".join(names)} FROM "{table}" NOT INDEXED WHERE {PREDICATES[table]} ORDER BY id LIMIT ?'
            cursor = connection.execute(query, (start_ms, end_ms, max_rows_per_table + 1))
            fetched, projection_bytes = [], 0
            for projected in cursor:
                _deadline(end)
                projection_bytes += len(canonical(projected).encode())
                if projection_bytes > 16 * 1024 * 1024:
                    raise ValueError("metadata projection exceeds 16MiB memory guard; no completed result")
                fetched.append(projected)
            inspected = fetched[:max_rows_per_table]
            rows = [dict(zip(names, row)) for row in inspected]
            prior_id = None
            for row in rows:
                if type(row["id"]) is not int or (prior_id is not None and row["id"] <= prior_id):
                    raise ValueError("local row identity changed or is not unique")
                prior_id = row["id"]
                for name in ("source", "subscription_id", "asset_id", "condition_id"):
                    if name in row and row[name] is not None and not isinstance(row[name], str):
                        raise ValueError(f"{table}.{name}: non-text identity")
                required_identity = "subscription_id" if table == "pm_events" else "source"
                if not isinstance(row[required_identity], str) or not row[required_identity]:
                    raise ValueError(f"{table}.{required_identity}: required identity absent")
            tables[table] = rows
            query_reports[table] = {
                "rows_counted": len(rows), "rows_read_including_limit_probe": len(fetched),
                "window_query_complete": len(fetched) <= max_rows_per_table,
                "order": "local_primary_key_id_not_exchange_order",
                "first_local_id": rows[0]["id"] if rows else None,
                "last_local_id": rows[-1]["id"] if rows else None,
                "counted_projection_sha256": hashlib.sha256(canonical(rows).encode()).hexdigest(),
                "projection_columns": names,
                "projection_bytes_including_probe": projection_bytes,
            }
        observations = summarize(tables["pm_events"], tables["heartbeats"], tables["gaps"],
                                 start_ms=start_ms, end_ms=end_ms, recorder_scope=recorder_scope)
        pm_groups = Counter((r["subscription_id"], r["asset_id"], r["condition_id"]) for r in tables["pm_events"])
        gap_groups = Counter((r["source"], r["subscription_id"]) for r in tables["gaps"])
        # Group identities remain separate: no matching across sources is inferred.
        observations["pm_identity_groups"] = [
            {"subscription_id": k[0], "asset_id": k[1], "condition_id": k[2], "messages": n}
            for k, n in pm_groups.items()
        ]
        observations["recorded_gap_groups"] = [
            {"source": k[0], "subscription_id": k[1], "records": n} for k, n in gap_groups.items()
        ]
        connection.close()
        connection = None
        if _check_path(path) != identity or _identity(os.fstat(fd)) != identity \
                or _hash_fd(fd, end) != expected_sha256:
            raise ValueError("archive changed during diagnostic; discard result")
        return {
            "schema": "canary_sqlite_activity_diagnostic_v1",
            "archive_sha256": expected_sha256, "archive_bytes": expected_bytes,
            "source_unchanged": True, "schema_projection": schema,
            "queries": query_reports, "observations": observations,
            "all_window_queries_complete": all(q["window_query_complete"] for q in query_reports.values()),
            "global_database_integrity_checked": False,
            "raw_payloads_read": False, "prices_read": False, "model_called": False,
            "clean_session_admitted": False, "fresh_validation_admitted": False,
            "acquisition_admitted": False, "new_download_bytes": 0,
            "uninspected": ["payload contents", "CEX trades", "market scans", "price changes",
                            "subscription health", "outside-window projected rows"],
            "probe_disclosure": "The extra limit-probe row is read as metadata but not counted or returned.",
            "claim_limit": "Activity-only metadata QA; incomplete queries are bounded diagnostics, not population counts.",
        }
    except sqlite3.OperationalError as exc:
        if time.monotonic() >= end:
            raise TimeoutError("SQLite query deadline exceeded; no completed result") from exc
        raise
    finally:
        if connection is not None:
            connection.close()
        os.close(fd)
