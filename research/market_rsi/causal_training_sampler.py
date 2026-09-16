"""Train-only thinning of repeated observed states, never future-zero labels.

This operates on decision rows after raw events have been used for features.
It must not thin the event stream used to reconstruct books or features.
"""
from __future__ import annotations

import hashlib
import math

from market_rsi import digest


def sampling_contract(*, feature_names: list[str], quiet_keep_probability: float,
                      weighting: str, seed: int) -> dict:
    if (not feature_names or feature_names != sorted(set(feature_names))
            or any(not isinstance(name, str) or not name for name in feature_names)):
        raise ValueError("sorted unique feature names required")
    if (isinstance(quiet_keep_probability, bool)
            or not isinstance(quiet_keep_probability, (int, float))
            or not math.isfinite(quiet_keep_probability)
            or not 0 < quiet_keep_probability <= 1):
        raise ValueError("quiet inclusion probability must be in (0, 1]")
    if weighting not in {"inverse_probability", "unweighted"} or type(seed) is not int:
        raise ValueError("explicit weighting and integer seed required")
    body = {
        "schema": "causal_repeated_state_sampler_v1",
        "allowed_role": "opened_train", "seed": seed,
        "feature_names": feature_names,
        "quiet_definition": "all_declared_current_features_equal_previous_observed_row",
        "stream": ["game_id", "market_id", "decision_utc_day"],
        "first_or_changed_state_inclusion_probability": 1.0,
        "quiet_keep_probability": float(quiet_keep_probability),
        "selection": "sha256(seed, row_id) below inclusion probability",
        "weighting": weighting,
        "future_labels_used_for_selection": False,
        "raw_stream_modified": False,
    }
    return {**body, "policy_sha256": digest(body)}


def select_training_rows(rows: list[dict], *, contract: dict, role: str) -> list[dict]:
    if role != "opened_train":
        raise ValueError("sampler may only operate on opened_train")
    expected = sampling_contract(
        feature_names=contract["feature_names"],
        quiet_keep_probability=contract["quiet_keep_probability"],
        weighting=contract["weighting"], seed=contract["seed"],
    )
    if contract != expected:
        raise ValueError("sampling contract has changed")
    if not rows:
        raise ValueError("nonempty Train required")
    seen_ids, previous = set(), {}
    results = [None] * len(rows)
    for row in rows:
        for name in ("row_id", "game_id", "market_id"):
            if not isinstance(row.get(name), str) or not row[name]:
                raise ValueError("missing row or stream identity")
        if row["row_id"] in seen_ids:
            raise ValueError("duplicate row ID")
        seen_ids.add(row["row_id"])
        if (type(row.get("decision_ms")) is not int
                or type(row.get("feature_available_ms")) is not int
                or row["feature_available_ms"] > row["decision_ms"]):
            raise ValueError("invalid time or future feature")
    for ordinal in sorted(range(len(rows)), key=lambda i: (rows[i]["decision_ms"], i)):
        row = rows[ordinal]
        state = tuple(row["features"][name] for name in contract["feature_names"])
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) for value in state):
            raise ValueError("finite observed features required")
        stream = (row["game_id"], row["market_id"], row["decision_ms"] // 86_400_000)
        old_state = previous.get(stream)
        is_quiet = old_state == state
        probability = contract["quiet_keep_probability"] if is_quiet else 1.0
        token = hashlib.sha256(f'{contract["seed"]}\0{row["row_id"]}'.encode()).digest()
        kept = int.from_bytes(token[:8], "big") < int(probability * 2**64)
        results[ordinal] = {
            "row_id": row["row_id"], "original_ordinal": ordinal,
            "keep": kept, "inclusion_probability": probability,
            "loss_weight": (1.0 / probability if contract["weighting"] ==
                            "inverse_probability" else 1.0) if kept else 0.0,
            "state": "first" if old_state is None else "repeated" if is_quiet else "changed",
        }
        # Compare with the previous observed row, not the previous kept row.
        previous[stream] = state
    return results
