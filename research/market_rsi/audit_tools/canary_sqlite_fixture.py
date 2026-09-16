"""Generate a tiny synthetic activity-only fixture and a durable canary receipt.

Not market data and not a simulator experiment. The three-table projection uses
the inspected publisher schema, without executing the publisher's document SQL.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from canary_sqlite_observations import canonical, inspect_archive


DDL = """
CREATE TABLE pm_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, received_at_ms INTEGER NOT NULL,
 subscription_id TEXT NOT NULL, event_type TEXT NOT NULL,
 asset_id TEXT, condition_id TEXT, payload_json TEXT NOT NULL);
CREATE TABLE heartbeats (
 id INTEGER PRIMARY KEY AUTOINCREMENT, emitted_at_ms INTEGER NOT NULL,
 source TEXT NOT NULL, subscription_id TEXT, last_message_age_sec REAL, metadata_json TEXT);
CREATE TABLE gaps (
 id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, subscription_id TEXT,
 gap_start_ms INTEGER NOT NULL, gap_end_ms INTEGER NOT NULL,
 duration_sec REAL NOT NULL, detected_at_ms INTEGER NOT NULL);
"""


def build_fixture(path):
    if path.exists():
        raise ValueError("fresh synthetic database path required")
    connection = sqlite3.connect(path)
    try:
        connection.executescript(DDL)
        connection.executemany(
            "INSERT INTO pm_events(received_at_ms,subscription_id,event_type,asset_id,condition_id,payload_json) VALUES(?,?,?,?,?,?)",
            [(0, "synthetic-sub-a", "book", "a", "c", "NOT_A_REAL_PAYLOAD"),
             (1, "synthetic-sub-a", "price_change", "a", "c", "NOT_A_REAL_PAYLOAD"),
             (120_000, "synthetic-sub-b", "market_resolved", "b", "d", "NOT_A_REAL_PAYLOAD")],
        )
        connection.executemany(
            "INSERT INTO heartbeats(emitted_at_ms,source,subscription_id,last_message_age_sec) VALUES(?,?,?,?)",
            [(0, "pm", "synthetic-sub-a", 0), (60_000, "pm", "synthetic-sub-a", 60),
             (120_000, "cex", None, None)],
        )
        connection.execute(
            "INSERT INTO gaps(source,subscription_id,gap_start_ms,gap_end_ms,duration_sec,detected_at_ms) VALUES(?,?,?,?,?,?)",
            ("cex", None, 60_000, 90_000, 30, 95_000),
        )
        connection.commit()
    finally:
        connection.close()
    path.chmod(0o444)
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    path = output / "synthetic.sqlite"
    digest, size = build_fixture(path)
    full = inspect_archive(path, expected_sha256=digest, expected_bytes=size,
                           start_ms=0, end_ms=180_000, recorder_scope="synthetic-one-recorder")
    partial = inspect_archive(path, expected_sha256=digest, expected_bytes=size,
                              start_ms=0, end_ms=180_000, recorder_scope="synthetic-one-recorder",
                              max_rows_per_table=1)
    assert full["all_window_queries_complete"] is True
    assert partial["all_window_queries_complete"] is False
    assert full["observations"]["minutes_with_heartbeat_but_no_pm_message"] == 1
    assert full["fresh_validation_admitted"] is False
    report = {
        "schema": "canary_sqlite_activity_fixture_v1", "passed": True,
        "evidence_mode": "synthetic_fixture_only", "real_market_rows_read": 0,
        "new_download_bytes": 0, "provider_cost_usd": "0", "new_model_calls": 0,
        "fixture_sha256": digest, "fixture_bytes": size, "full": full, "partial": partial,
        "code_sha256": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                        for name in ("canary_sqlite_fixture.py", "canary_sqlite_observations.py",
                                     "canary_activity_observations.py")},
        "not_proven": ["publisher raw-file compatibility", "clean historical sessions",
                       "model improvement", "data acquisition permission"],
    }
    report["result_sha256"] = hashlib.sha256(canonical(report).encode()).hexdigest()
    with (output / "canary.json").open("x") as stream:
        stream.write(canonical(report) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    result = run(parser.parse_args().output.resolve())
    print(json.dumps({k: result[k] for k in ("passed", "evidence_mode", "new_download_bytes",
                                           "provider_cost_usd", "result_sha256")}))
