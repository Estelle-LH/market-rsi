"""Explicit probability-DELTA metrics on the full declared evaluation population.

No fitting, implicit target changes, score-driven row selection or clipping.
Prediction zero means unchanged quote, NOT a filled missing source price.
"""
import numpy as np
from scipy.stats import rankdata


def correlation(x, y):
    if len(x) < 2:
        return None
    a = x - np.mean(x); b = y - np.mean(y)
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b)/denominator) if denominator > 0 else None


def raw_feature_diagnostic(feature, target, available, dates):
    n = len(target)
    if (any(v.ndim != 1 or len(v) != n for v in [feature, target, available, dates])
            or available.dtype != np.dtype(bool)
            or np.any(available & ~np.isfinite(target)) or np.any(np.isinf(feature))):
        raise ValueError('aligned finite covered target and explicit feature missingness required')
    usable = available & np.isfinite(feature)

    def describe(mask):
        matched = mask & usable
        x, y = feature[matched], target[matched]
        return {'population_rows': int(mask.sum()), 'label_rows': int((mask & available).sum()),
                'paired_rows': int(matched.sum()),
                'pearson_ic': correlation(x, y),
                'rank_ic': correlation(rankdata(x), rankdata(y)) if len(x) else None,
                'feature_variance': float(np.var(x)) if len(x) else None,
                'target_variance': float(np.var(y)) if len(y) else None}
    return {'all_rows': describe(np.ones(n, dtype=bool)),
            'by_date': {str(d): describe(dates == d) for d in sorted(set(dates))},
            'claim': 'reusable opened-Train association, not new out-of-sample prediction or PnL',
            'model_fitted': False, 'full_population_preserved': True}


def score_delta(target, prediction, *, label_available, dates, groups, aggregation):
    """Require one finite prediction for EVERY covered label; never drop failures."""
    n = len(target)
    if (any(v.ndim != 1 or len(v) != n for v in [target, prediction, label_available, dates, groups])
            or label_available.dtype != np.dtype(bool)
            or np.any(label_available & (~np.isfinite(target) | ~np.isfinite(prediction)))):
        raise ValueError('all covered labels must have finite predictions; no selective omission')
    if aggregation not in {'equal_row', 'equal_day', 'equal_group'}:
        raise ValueError('explicit primary metric aggregation required')
    usable = label_available
    if not np.any(usable):
        raise ValueError('no covered labels to evaluate')
    error = (prediction[usable] - target[usable])**2
    baseline = target[usable]**2
    if not np.all(np.isfinite(error)):
        raise ValueError('prediction error overflow')
    weights = np.ones(int(usable.sum()), dtype=float)
    if aggregation != 'equal_row':
        keys = dates[usable] if aggregation == 'equal_day' else groups[usable]
        unique, inverse, count = np.unique(keys, return_inverse=True, return_counts=True)
        weights = 1 / count[inverse].astype(float)
    weights /= weights.sum()
    mse = float(np.dot(weights, error)); persistence = float(np.dot(weights, baseline))
    mae = float(np.dot(weights, np.abs(prediction[usable]-target[usable])))
    # Scale-free comparison is meaningful only for this SAME frozen target and
    # SAME rows/weights. Changing horizons can still change the research question.
    value = {'population_rows': n, 'label_rows': int(usable.sum()),
             'missing_label_rows': int((~usable).sum()), 'aggregation': aggregation,
             'model_mse_probability': mse, 'persistence_mse_probability': persistence,
             'mse_skill_vs_persistence': 1-mse/persistence if persistence > 0 else None,
             'model_rmse_probability_bps': float(np.sqrt(mse)*10000),
             'persistence_rmse_probability_bps': float(np.sqrt(persistence)*10000),
             'model_mae_probability_bps': mae*10000,
             'pearson_ic': correlation(prediction[usable], target[usable]),
             'rank_ic': correlation(rankdata(prediction[usable]), rankdata(target[usable])),
             'output_clipping_applied_by_scorer': False, 'unit': 'absolute_probability_delta',
             'profitability_evidence': False}
    p = prediction[usable]; y = target[usable]
    variance = np.var(p)
    slope = float(np.mean((p-np.mean(p))*(y-np.mean(y)))/variance) if variance > 0 else None
    value['unweighted_calibration_slope'] = slope
    value['unweighted_calibration_intercept'] = float(np.mean(y)-slope*np.mean(p)) if slope is not None else None
    return value
