"""Predeclared, symmetric scoring for three memory arms and a fixed baseline."""
from __future__ import annotations

from itertools import combinations


ARMS = ("fresh", "archive", "compact", "baseline")


def _mean(values):
    return sum(values) / len(values) if values else None


def summarize(session_scores):
    if len(session_scores) < 20:
        raise ValueError("primary Final requires at least twenty complete sessions")
    for row in session_scores:
        if set(row) != set(ARMS):
            raise ValueError("every Final session must score every arm and baseline")
        dates = {row[arm]["date"] for arm in ARMS}
        counts = {row[arm]["n"] for arm in ARMS}
        if len(dates) != 1 or len(counts) != 1 or next(iter(counts)) <= 0:
            raise ValueError("arms must use the exact same session rows")
    equal = {arm: _mean([row[arm]["candidate_mse"] for row in session_scores])
             for arm in ARMS}
    weighted = {arm: sum(row[arm]["candidate_mse"] * row[arm]["n"]
                         for row in session_scores)
                / sum(row[arm]["n"] for row in session_scores) for arm in ARMS}
    pairwise = {}
    for left, right in combinations(ARMS, 2):
        deltas = [row[left]["candidate_mse"] - row[right]["candidate_mse"]
                  for row in session_scores]
        pairwise[f"{left}_minus_{right}"] = {
            "equal_session_mean_delta": _mean(deltas),
            "left_better_session_fraction": sum(delta < 0 for delta in deltas) / len(deltas),
            "session_deltas": deltas,
        }
    return {
        "schema": "memory_policy_final_summary_v1",
        "primary_equal_session_mse": equal,
        "secondary_row_weighted_mse": weighted,
        "pairwise": pairwise,
        "session_mean_pearson_ic": {arm: _mean([row[arm]["pearson_ic"]
            for row in session_scores if row[arm]["pearson_ic"] is not None]) for arm in ARMS},
        "session_mean_rank_ic": {arm: _mean([row[arm]["rank_ic"]
            for row in session_scores if row[arm]["rank_ic"] is not None]) for arm in ARMS},
        "session_mean_calibration_slope": {arm: _mean([row[arm]["calibration_slope"]
            for row in session_scores if row[arm]["calibration_slope"] is not None]) for arm in ARMS},
        "final_sessions": len(session_scores),
        "distinct_utc_dates": len({row["fresh"]["date"][:10] for row in session_scores}),
        "multiple_pairwise_comparisons_exploratory": True,
        "no_iid_confidence_claim": True,
    }
