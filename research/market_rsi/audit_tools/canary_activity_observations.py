"""Count observed activity, heartbeat and outage evidence without admitting data.

Pure, offline diagnostics for one recorder archive. No download, filtering,
forward fill, fitting, source selection or clean-session decision is provided.
The caller must bind the source hash and disclose inspected dates separately.
"""
from collections import Counter


MINUTE_MS = 60_000


def _integer(value, field):
    if type(value) is not int:
        raise ValueError(f"{field} must be an integer, not a coerced timestamp")
    return value


def summarize(pm_events, heartbeats, gaps, *, start_ms, end_ms, recorder_scope):
    """Report a half-open, UTC-minute-aligned window for ONE recorder only.

    Heartbeats use emitted_at_ms; PM messages use received_at_ms. Their presence
    is observed separately. A recorder heartbeat is not proof of a live market
    subscription, and an absent message is not proof of an unchanged price.
    No row or date eligibility mask is returned.
    """
    start_ms = _integer(start_ms, "start_ms")
    end_ms = _integer(end_ms, "end_ms")
    if start_ms >= end_ms or start_ms % MINUTE_MS or end_ms % MINUTE_MS:
        raise ValueError("window must be positive and UTC-minute aligned")
    if not isinstance(recorder_scope, str) or not recorder_scope.strip():
        raise ValueError("one explicitly identified recorder archive is required")
    event_minutes, heartbeat_minutes, logged_gap_minutes = set(), set(), set()
    rows = Counter()
    event_types = Counter()
    heartbeat_groups = {}
    for event in pm_events:
        ts = _integer(event["received_at_ms"], "received_at_ms")
        kind = event["event_type"]
        if not isinstance(kind, str) or not kind:
            raise ValueError("event_type must be preserved")
        rows["pm_seen"] += 1
        if not start_ms <= ts < end_ms:
            rows["pm_outside_window"] += 1
            continue
        rows["pm_in_window"] += 1
        event_types[kind] += 1
        event_minutes.add((ts - start_ms) // MINUTE_MS)
    for heartbeat in heartbeats:
        ts = _integer(heartbeat["emitted_at_ms"], "emitted_at_ms")
        source = heartbeat["source"]
        subscription = heartbeat.get("subscription_id")
        if not isinstance(source, str) or not source or (
            subscription is not None and not isinstance(subscription, str)
        ):
            raise ValueError("heartbeat source/subscription must be preserved")
        rows["heartbeat_seen"] += 1
        if not start_ms <= ts < end_ms:
            rows["heartbeat_outside_window"] += 1
            continue
        rows["heartbeat_in_window"] += 1
        minute = (ts - start_ms) // MINUTE_MS
        heartbeat_minutes.add(minute)
        heartbeat_groups.setdefault((source, subscription), set()).add(minute)
    for gap in gaps:
        lo = _integer(gap["gap_start_ms"], "gap_start_ms")
        hi = _integer(gap["gap_end_ms"], "gap_end_ms")
        if hi < lo:
            raise ValueError("reversed recorded gap")
        rows["gap_seen"] += 1
        if lo == hi:
            rows["zero_duration_gaps"] += 1
        lo, hi = max(lo, start_ms), min(hi, end_ms)
        if lo >= hi:
            continue
        rows["gaps_overlapping_window"] += 1
        first = (lo - start_ms) // MINUTE_MS
        last = (hi - start_ms - 1) // MINUTE_MS
        logged_gap_minutes.update(range(first, last + 1))
    total = (end_ms - start_ms) // MINUTE_MS
    return {
        "schema": "canary_activity_observations_v1",
        "recorder_scope": recorder_scope,
        "window_start_ms": start_ms,
        "window_end_ms_exclusive": end_ms,
        "calendar_minutes": total,
        "observed_rows": dict(rows),
        "event_type_counts": dict(sorted(event_types.items())),
        "minutes_with_pm_messages": len(event_minutes),
        "minutes_with_any_recorder_heartbeat": len(heartbeat_minutes),
        "minutes_with_heartbeat_but_no_pm_message": len(heartbeat_minutes - event_minutes),
        "minutes_with_neither_message_nor_heartbeat": total - len(event_minutes | heartbeat_minutes),
        "minutes_overlapping_any_recorded_gap": len(logged_gap_minutes),
        "heartbeat_groups": [
            {"source": source, "subscription_id": subscription, "observed_minutes": len(minutes)}
            for (source, subscription), minutes in sorted(
                heartbeat_groups.items(), key=lambda item: (item[0][0], item[0][1] or "")
            )
        ],
        "clean_session_admitted": False,
        "fresh_validation_admitted": False,
        "rows_deleted": 0,
        "rows_imputed": 0,
        "claim_limits": [
            "Message activity is not price movement or feed completeness.",
            "A recorder heartbeat does not prove market-subscription health.",
            "No recorded gaps does not prove no outages.",
            "Minute counts do not order same-timestamp events across recorders.",
            "No dates or quiet observations are excluded by this diagnostic.",
            "Resolution messages may be counted for QA only, never used as features.",
        ],
    }
