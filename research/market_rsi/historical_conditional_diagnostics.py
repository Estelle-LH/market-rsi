"""Prior-fitted redundancy diagnostics on an existing, opened-Train protocol.

This is not a new prediction trial or classical same-sample partial Spearman:
two nuisance regressions in each of raw and prior-ECDF spaces are fitted only
on causal earlier rows. Later residual associations use these fixed fits.
Complete-case diagnostic support is explicit; evaluation rows are NOT removed.
"""
import numpy as np
from scipy.stats import rankdata

from historical_recorded_features import derive
from market_rsi import digest


def _corr(a, b):
    if len(a) < 3:
        return None
    a = a - np.mean(a); b = b - np.mean(b)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na <= 1e-12 * np.sqrt(len(a)) or nb <= 1e-12 * np.sqrt(len(b)):
        return None
    return float(np.clip(np.dot(a / na, b / nb), -1, 1))


def _ecdf(reference, values):
    ordered = np.sort(reference)
    return (np.searchsorted(ordered, values, side='left') +
            np.searchsorted(ordered, values, side='right')) / (2.0 * len(ordered))


def summarize(matrix, target, *, eligible_fit, check, label_available, dates, groups, names):
    """Column zero is candidate; the remaining columns are chosen controls."""
    matrix = np.asarray(matrix, dtype=float); target = np.asarray(target, dtype=float)
    n = len(target)
    if (matrix.ndim != 2 or matrix.shape[0] != n or not 1 <= matrix.shape[1] <= 13
            or len(names) != matrix.shape[1] or len(set(names)) != len(names)):
        raise ValueError('one candidate and zero to twelve distinct controls required')
    for a in (eligible_fit, check, label_available, dates, groups):
        if np.asarray(a).shape != (n,): raise ValueError('aligned row arrays required')
    if np.any(eligible_fit & check): raise ValueError('fit and check overlap')
    finite = np.all(np.isfinite(matrix), axis=1)
    labels = label_available & np.isfinite(target)
    fit = eligible_fit & finite & labels
    use = check & finite & labels
    if fit.sum() < matrix.shape[1] + 3:
        raise ValueError('insufficient causal complete cases for nuisance regression')
    raw = np.column_stack([matrix, target])
    # Values outside each prior empirical distribution map to its endpoints;
    # neither check features nor labels alter these reference distributions.
    ranked = np.column_stack([_ecdf(raw[fit, j], raw[:, j]) for j in range(raw.shape[1])])
    projections = {}
    residuals = {}
    for space, values in [('raw', raw), ('prior_ecdf', ranked)]:
        center = values[fit].mean(axis=0); scale = values[fit].std(axis=0)
        safe_scale = np.where(scale > 0, scale, 1.0)
        z = (values - center) / safe_scale
        controls = np.column_stack([np.ones(n), z[:, 1:-1]])
        outcomes = z[:, [0, -1]]
        coefficients, _, rank, singular = np.linalg.lstsq(controls[fit], outcomes[fit], rcond=None)
        residuals[space] = outcomes - controls @ coefficients
        design = np.column_stack([np.ones(int(fit.sum())), z[fit, :-1]])
        sv = np.linalg.svd(design, compute_uv=False)
        tol = np.finfo(float).eps * max(design.shape) * sv[0]
        singular_design = bool(sv[-1] <= tol)
        projections[space] = {'center': center.tolist(), 'scale': scale.tolist(),
            'constant_columns': [names[j] if j < len(names) else 'target'
                                 for j in np.flatnonzero(scale == 0)],
            'coefficients_candidate_then_target': coefficients.tolist(),
            'control_design_rank': int(rank), 'control_design_columns': controls.shape[1],
            'control_singular_values': singular.tolist(),
            'candidate_plus_controls_singular': singular_design,
            'candidate_plus_controls_condition_number': None if singular_design else float(sv[0] / sv[-1]),
            'fit_feature_control_correlations': [[_corr(values[fit, a], values[fit, b])
                for b in range(matrix.shape[1])] for a in range(matrix.shape[1])]}

    def stats(mask):
        count = int(mask.sum())
        candidate, outcome = matrix[mask, 0], target[mask]
        r = residuals['raw'][mask]; rr = residuals['prior_ecdf'][mask]
        variance = float(np.var(candidate)) if count else 0
        scaled_variance = variance / (projections['raw']['scale'][0] or 1.0) ** 2
        return {'rows': count, 'raw_pearson_ic': _corr(candidate, outcome),
            'raw_rank_ic': _corr(rankdata(candidate), rankdata(outcome)),
            'prior_linear_residual_ic': _corr(r[:, 0], r[:, 1]),
            'prior_rank_residual_ic': _corr(rr[:, 0], rr[:, 1]),
            'candidate_residual_variance_fraction': float(np.var(r[:, 0]) / scaled_variance)
                if count and scaled_variance > 1e-24 else None}

    by_date = {str(d): stats(use & (dates == d)) for d in sorted(set(dates[check]))}
    group_stats = [stats(use & (groups == g)) for g in sorted(set(groups[check]))]
    def breadth(rows):
        out = {'total': len(rows)}
        for metric in ('raw_pearson_ic', 'raw_rank_ic', 'prior_linear_residual_ic', 'prior_rank_residual_ic'):
            values = [r[metric] for r in rows if r[metric] is not None]
            out[metric] = {'defined': len(values), 'positive': sum(v > 0 for v in values),
                          'negative': sum(v < 0 for v in values),
                          'equal_group_mean': float(np.mean(values)) if values else None}
        return out
    return {'schema': 'historical_prior_conditional_diagnostic_v1', 'feature_order': names,
        'support': {'causally_eligible_fit_rows': int(eligible_fit.sum()), 'nuisance_fit_rows': int(fit.sum()),
            'check_population_rows': int(check.sum()), 'check_labelled_rows': int((check & labels).sum()),
            'check_diagnostic_rows': int(use.sum()), 'check_labelled_missing_inputs': int((check & labels & ~finite).sum()),
            'fit_mask_sha256': digest(np.flatnonzero(fit).tolist()),
            'check_mask_sha256': digest(np.flatnonzero(use).tolist())},
        'projection_fits': projections, 'fit': stats(fit), 'check': stats(use),
        'check_by_date': by_date, 'check_date_breadth': breadth(list(by_date.values())),
        'check_market_breadth': breadth(group_stats),
        'nuisance_regressions_fitted': 4, 'prediction_model_trials_started': 0,
        'paid_provider_calls': 0, 'evaluation_rows_removed': 0, 'source_values_imputed': False,
        'fresh_holdout': False, 'projection_weighting': 'equal_row',
        'limits': 'All periods already OPEN Train. Complete-case raw and residual IC use the SAME rows; '
            'not a full-population prediction score. Rank residual IC uses earlier-fit midpoint ECDF references, '
            'not classical partial Spearman fitted on check. Correlations of near-zero residuals are undefined. '
            'Prior-fit residual variance fractions on check may exceed one under drift. '
            'No confidence interval, horizon-decay test, feature selection, causal conclusion or promotion is supplied. '
            'No existing prediction control is used: saved trials lack earlier-fit predictions.'}


def validate_selection(trial, feature_name, control_names):
    named = {f['name']: f for f in trial['plan']['features']}
    if (not isinstance(feature_name, str) or not isinstance(control_names, list)
            or any(not isinstance(c, str) for c in control_names) or len(control_names) > 12
            or feature_name in control_names or len(set(control_names)) != len(control_names)
            or any(n not in named for n in [feature_name] + control_names)):
        raise ValueError('choose a trial feature and zero to twelve distinct other trial features as controls')
    return [named[n] for n in [feature_name] + control_names]


def diagnose_conditional(inputs, trial, feature_name, control_names):
    specs = validate_selection(trial, feature_name, control_names)
    x, y = inputs['x'], inputs['y']; plan = trial['plan']
    matrix = np.column_stack([derive(x['entity'], x['decision_ms'], x['values'], inputs['names'],
        spec=f, cadence_ms=inputs['cadence_ms'], recorded_events=inputs.get('recorded_events'))['values'] for f in specs])
    check = np.isin(x['date'], plan['check_utc_dates'])
    cutoff = int(np.datetime64(min(plan['check_utc_dates']), 'ms').astype(np.int64))
    eligible = np.isin(x['date'], plan['train_utc_dates']) & y['available']
    eligible &= (x['decision_ms'] < cutoff) & (y['label_available_ms'] < cutoff)
    eligible &= ~np.isin(x['market'], np.unique(x['market'][check]))
    result = summarize(matrix, y['delta_probability'], eligible_fit=eligible, check=check,
        label_available=y['available'], dates=x['date'], groups=x['market'], names=[f['name'] for f in specs])
    result.update({'trial_id': trial['trial_id'], 'trial_result_sha256': trial['result_sha256'],
        'selected_specs_sha256': digest(specs), 'strict_label_cutoff_ms': cutoff,
        'latest_nuisance_fit_label_available_ms': int(y['label_available_ms'][eligible & np.all(np.isfinite(matrix), axis=1)].max())})
    return result
