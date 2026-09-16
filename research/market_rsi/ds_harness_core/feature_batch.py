"""Check a domain-neutral feature output without sorting, filling or fitting.

This validates *declared* lineage. It cannot prove that a feature kernel did not
read future data. Availability ordinals must use the same ordering domain as
decision ordinals. Provider arrival-time evidence belongs to the data adapter.
"""
from collections.abc import Mapping

import numpy as np


SCHEMA = "feature_batch_v1"
FIELDS = {
    "schema", "row_id", "entity_id", "session_id", "decision_ns", "event_ordinal",
    "feature_names", "values", "available", "feature_available_ns",
    "feature_available_ordinal",
}


def validate_feature_batch(batch):
    """Return a small audit; leave every input byte and row unchanged.

    `available=False` retains the original value (finite or NaN). Unknown
    availability uses -1 for both availability-clock fields. No implicit
    feature-count limit, target, date convention or market holdout rule.
    """
    if not isinstance(batch, Mapping) or set(batch) != FIELDS or batch["schema"] != SCHEMA:
        raise ValueError("exact feature-batch schema required")
    names = batch["feature_names"]
    if (not isinstance(names, (list, tuple)) or not names
            or any(not isinstance(x, str) or not x.strip() for x in names)
            or len(set(names)) != len(names)):
        raise ValueError("unique nonempty feature names required")
    values = batch["values"]
    if (not isinstance(values, np.ndarray) or values.ndim != 2
            or values.dtype.kind != "f" or values.dtype.itemsize not in (4, 8)
            or values.shape[0] == 0 or values.shape[1] != len(names)
            or np.any(np.isinf(values))):
        raise ValueError("nonempty floating values matrix; infinity is not missing")
    n, p = values.shape
    for field in ("row_id", "entity_id", "session_id"):
        a = batch[field]
        if (not isinstance(a, np.ndarray) or a.shape != (n,) or a.dtype.kind != "U"
                or any(not str(x).strip() for x in a)):
            raise ValueError(f"{field}: aligned nonempty string identifiers required")
    if len(set(batch["row_id"])) != n:
        raise ValueError("duplicate immutable row ID")
    for field, shape in (("decision_ns", (n,)), ("event_ordinal", (n,)),
                         ("feature_available_ns", (n, p)),
                         ("feature_available_ordinal", (n, p))):
        a = batch[field]
        if not isinstance(a, np.ndarray) or a.shape != shape or a.dtype != np.dtype("int64"):
            raise ValueError(f"{field}: exact int64 clock/order required; no implicit conversion")
    t, order = batch["decision_ns"], batch["event_ordinal"]
    if np.any(t < 0) or np.any(order < 0):
        raise ValueError("decision clock and ordinal must be nonnegative")
    previous = {}
    for entity, session, timestamp, ordinal in zip(batch["entity_id"], batch["session_id"], t, order):
        key = (str(entity), str(session))
        current = (int(timestamp), int(ordinal))
        if key in previous and current <= previous[key]:
            raise ValueError("non-increasing entity/session event key; no automatic sorting")
        previous[key] = current
    available = batch["available"]
    if (not isinstance(available, np.ndarray) or available.shape != (n, p)
            or available.dtype != np.dtype(bool)):
        raise ValueError("explicit boolean availability matrix required")
    if np.any(available & ~np.isfinite(values)):
        raise ValueError("available values must be finite")
    at, ao = batch["feature_available_ns"], batch["feature_available_ordinal"]
    unknown = (at == -1) & (ao == -1)
    known = (at >= 0) & (ao >= 0)
    if np.any(~(unknown | known)) or np.any(available & ~known):
        raise ValueError("availability clock must be known for available values")
    later = (at > t[:, None]) | ((at == t[:, None]) & (ao > order[:, None]))
    if np.any(available & later):
        raise ValueError("feature unavailable at decision event (future timestamp or ordinal)")
    return {
        "schema": SCHEMA, "rows": n, "features": p,
        "entity_sessions": len(previous),
        "available_per_feature": available.sum(axis=0).tolist(),
        "missing_numeric_per_feature": np.isnan(values).sum(axis=0).tolist(),
        "rows_removed": 0, "rows_reordered": False, "values_imputed": False,
        "lineage_claim": "declared_clock_checked_not_kernel_causality_proof",
    }
