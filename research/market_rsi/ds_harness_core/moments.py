"""Shared descriptive statistics; no target, time-window, fit or keep/drop rule.

Extracted from the consumer's pure profiles.moments implementation. Preserve
valid-input numerical operations; make invalid-input/overflow failure explicit.
"""
import numpy as np

from .feature_batch import validate_feature_batch


def moments(values):
    """Describe finite values without mutating or filling the input series.

    NaN counts as missing. Infinity is invalid, not missing. A summary omits
    mean/std/quantiles if there are no finite values. STD is population STD;
    quantiles use linear interpolation. Results are descriptive, never an SNR.
    """
    if type(values) is not np.ndarray or values.ndim != 1 or values.dtype.kind not in "fiu":
        raise ValueError("one-dimensional unmasked real numeric ndarray required")
    if np.any(np.isinf(values)):
        raise ValueError("infinity is invalid, not missing")
    finite = values[np.isfinite(values)]
    if not len(finite):
        return {"rows": len(values), "finite": 0, "missing": len(values), "constant": None}
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            result = {
                "rows": len(values), "finite": len(finite), "missing": len(values)-len(finite),
                "unique": int(len(np.unique(finite))), "constant": bool(np.all(finite == finite[0])),
                "mean": float(np.mean(finite)), "std": float(np.std(finite, ddof=0)),
                "quantiles": dict(zip(("min", "p10", "p50", "p90", "max"),
                    map(float, np.quantile(finite, [0, .1, .5, .9, 1], method="linear")))),
            }
    except FloatingPointError as exc:
        raise ValueError("nonfinite descriptive arithmetic; no clipping or fallback") from exc
    if not np.all(np.isfinite([result["mean"], result["std"], *result["quantiles"].values()])):
        raise ValueError("nonfinite descriptive output; no clipping or fallback")
    return result


def profile_feature_batch(batch):
    """Summarize available values only; preserve full population accounting.

    Caller still supplies/adopts a reviewed clock and mask contract. The
    returned statistics do not prove upstream kernel or downstream fit safety.
    """
    audit = validate_feature_batch(batch)
    rows = []
    for j, name in enumerate(batch["feature_names"]):
        values, available = batch["values"][:, j], batch["available"][:, j]
        rows.append({
            "name": name, "population_rows": len(values),
            "available_rows": int(available.sum()),
            "unavailable_rows": int((~available).sum()),
            "numeric_missing_rows": int(np.isnan(values).sum()),
            "unavailable_finite_rows": int((~available & np.isfinite(values)).sum()),
            "available_moments": moments(values[available]),
        })
    return {"schema": "feature_batch_profile_v1", "batch_audit": audit,
            "features": rows, "uses_target": False, "fitted": False,
            "statistic_population": "explicitly_available_cells_only"}
