"""Time-series shape diagnostics on predeclared opened Train only.

No inferred staleness, fills, automatic feature rejection or effective-sample-size
claim. Adjacent pairs require exact cadence, same entity and same UTC date.
"""
import numpy as np

from historical_delta_evaluation import raw_feature_diagnostic
from historical_recorded_features import derive, validate_feature
from data_scientist_harness.core_dependency import load_moments


moments = load_moments()


def shape(values, times, entities, dates, cadence_ms, detail=False):
    values, times, entities, dates = map(np.asarray, (values, times, entities, dates))
    if (values.ndim != 1 or not len(values) or any(a.shape != values.shape for a in (times, entities, dates))
            or not np.issubdtype(times.dtype, np.integer) or type(cadence_ms) is not int or cadence_ms <= 0
            or np.any(np.isinf(values))):
        raise ValueError("aligned bounded numeric series and explicit cadence required")
    order = np.lexsort((times, entities, dates))
    v, t, e, d = (a[order] for a in (values, times, entities, dates))
    same = (e[1:] == e[:-1]) & (d[1:] == d[:-1])
    if np.any(same & (np.diff(t) <= 0)):
        raise ValueError("duplicate/non-increasing entity timestamps")
    adjacent = same & (np.diff(t) == cadence_ms)
    finite = np.isfinite(v)
    pairs = adjacent & finite[1:] & finite[:-1]
    equal = pairs & (v[1:] == v[:-1])
    longest = run = 0
    for stays in equal:
        run = run + 1 if stays else 0
        longest = max(longest, run)
    delta = v[1:][pairs] - v[:-1][pairs]
    corr = None
    left, right = v[:-1][pairs], v[1:][pairs]
    if len(left) >= 3 and np.std(left) > 0 and np.std(right) > 0:
        corr = float(np.corrcoef(left, right)[0, 1])
    boundaries = np.r_[0, np.flatnonzero(~same)+1, len(v)]
    grouped = [{"entity": str(e[a]), "date": str(d[a]), **moments(v[a:b])}
               for a, b in zip(boundaries[:-1], boundaries[1:])]
    result = {"distribution": moments(v), "adjacent_valid_pairs": int(pairs.sum()),
            "exact_unchanged_fraction": float(equal.sum()/pairs.sum()) if pairs.any() else None,
            "longest_observed_unchanged_span_ms": int(longest*cadence_ms),
            "lag1_pair_correlation": corr, "first_difference": moments(delta),
            "noncadence_same_entity_intervals": int((same & ~adjacent).sum()),
            "by_date": {str(day): moments(v[d == day]) for day in sorted(set(d))},
            "entity_date_series": len(grouped),
            "constant_entity_date_series": sum(bool(g["constant"]) for g in grouped),
            "limitations": ["Exact equality only; no selected near-flat threshold.",
                "Run spans end at gaps/missing values; a single observation has zero observed duration.",
                "Pair correlation pools valid within-series pairs, not a stationarity test or independent-sample count.",
                "Flatness does not identify stale feeds or predictiveness; no rows/features were removed."]}
    if detail:
        result["by_entity_date"] = grouped
    return result


def raw_profiles(inputs):
    x = inputs["x"]
    return {"scope": "opened_train_only", "field_count": len(inputs["names"]),
            "rows": len(x["row_id"]), "fields": {name: shape(x["values"][:, j], x["decision_ms"],
                x["entity"], x["date"], inputs["cadence_ms"]) for j, name in enumerate(inputs["names"])},
            "uses_target_values": False, "new_fit": False, "rows_removed": 0}


def feature_profile(inputs, spec):
    validate_feature(spec, inputs["names"], inputs["cadence_ms"])
    x, y = inputs["x"], inputs["y"]
    values = derive(x["entity"], x["decision_ms"], x["values"], inputs["names"], spec=spec,
                    cadence_ms=inputs["cadence_ms"], recorded_events=inputs.get("recorded_events"))["values"]
    return {"spec": spec, "shape": shape(values, x["decision_ms"], x["entity"], x["date"], inputs["cadence_ms"], detail=True),
            "target_diagnostic": raw_feature_diagnostic(values, y["delta_probability"], y["available"], x["date"]),
            "objective_sha256": inputs["objective"]["proposal_sha256"],
            "scope": "opened_train_only", "automatic_keep_drop": False, "rows_removed": 0}
