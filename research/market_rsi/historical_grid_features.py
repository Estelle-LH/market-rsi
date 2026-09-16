"""Explicit researcher-selected causal transforms of the recorded input grid.

No feature, lag, sampling rule or normalizer is selected by default. Labels
are intentionally absent from this API. Missing grid points are not bridged.
"""
import math

import numpy as np


TRANSFORMS = {'identity', 'log1p', 'square', 'lag_delta', 'lag_log_return',
              'trailing_mean_delta', 'trailing_std'}
FIELDS = {'name', 'source', 'transform', 'lookback_ms', 'minimum_observations',
          'minimum_window_coverage'}


def validate_feature(spec, names, cadence_ms):
    if not isinstance(spec, dict) or set(spec) != FIELDS:
        raise ValueError('complete explicit feature spec required; no hidden fields')
    from market_rsi import identifier
    identifier(spec['name'])
    if spec['source'] not in names or spec['transform'] not in TRANSFORMS:
        raise ValueError('unimplemented source/transform; extend the library explicitly')
    lag = spec['lookback_ms']
    if (type(cadence_ms) is not int or cadence_ms <= 0 or type(lag) is not int
            or lag < 0 or lag % cadence_ms or lag > 86400000):
        raise ValueError('nonnegative causal lookback aligned to the actual grid required')
    count = spec['minimum_observations']; coverage = spec['minimum_window_coverage']
    if (type(count) is not int or count <= 0 or type(coverage) not in (int, float)
            or not 0 < coverage <= 1):
        raise ValueError('explicit positive coverage and count required')
    transform = spec['transform']
    if transform in {'identity', 'log1p', 'square'}:
        if lag != 0 or count != 1 or coverage != 1:
            raise ValueError('point transform requires zero lookback and one observation')
    elif transform in {'lag_delta', 'lag_log_return'}:
        if lag == 0 or count != 2 or coverage != 1:
            raise ValueError('lag transform requires current and exact past point')
    elif lag == 0 or lag // cadence_ms + 1 > 256 or count > lag // cadence_ms + 1:
        raise ValueError('trailing window requires positive lookback and at most256 actual grid points')
    return spec


def derive(entity, decision_ms, values, names, *, spec, cadence_ms):
    validate_feature(spec, names, cadence_ms)
    n = len(decision_ms)
    if (not 0 < n <= 500000 or values.shape != (n, len(names)) or entity.shape != (n,)
            or decision_ms.shape != (n,) or len(set(names)) != len(names)
            or not np.issubdtype(entity.dtype, np.integer)
            or not np.issubdtype(decision_ms.dtype, np.signedinteger)
            or np.any(entity < 0) or np.any(decision_ms < 0)
            or np.any(decision_ms % cadence_ms)):
        raise ValueError('bounded aligned unique numeric input panel required')
    current = values[:, names.index(spec['source'])]
    if np.any(np.isinf(current)):
        raise ValueError('infinite source is invalid, not missing')
    lag = spec['lookback_ms']; transform = spec['transform']
    lower = int(decision_ms.min()) - lag
    span = int(decision_ms.max()) - lower + cadence_ms
    if (int(entity.max()) + 1) * span >= np.iinfo(np.int64).max:
        raise ValueError('bounded feature lookup key overflow')
    keys = entity.astype(np.int64) * span + decision_ms - lower
    if len(np.unique(keys)) != n:
        raise ValueError('duplicate entity/time in feature input')
    order = np.argsort(keys); ordered = keys[order]

    def past(offset):
        desired = keys - offset
        found = np.searchsorted(ordered, desired)
        safe = np.minimum(found, n-1)
        same = (found < n) & (ordered[safe] == desired)
        # Namespace span includes lookback padding; negative lookup cannot
        # accidentally read another market, and exact gaps are kept missing.
        return np.where(same, current[order[safe]], np.nan)

    if transform in {'identity', 'log1p', 'square'}:
        result = current.copy()
        if transform == 'log1p':
            eligible = np.isfinite(current) & (current >= 0)
            result[:] = np.nan; result[eligible] = np.log1p(current[eligible])
        elif transform == 'square':
            with np.errstate(over='ignore'):
                result = current**2
            if np.any(np.isinf(result)):
                raise ValueError('feature square overflow; no silent saturation')
        count = np.isfinite(current).astype(np.int64)
    elif transform in {'lag_delta', 'lag_log_return'}:
        previous = past(lag)
        count = np.isfinite(current).astype(np.int64) + np.isfinite(previous).astype(np.int64)
        result = current - previous
        if transform == 'lag_log_return':
            good = np.isfinite(current) & np.isfinite(previous) & (current > 0) & (previous > 0)
            result[:] = np.nan
            # Difference of logs avoids overflow in the price ratio.
            result[good] = np.log(current[good]) - np.log(previous[good])
    else:
        offsets = range(0, lag+1, cadence_ms)
        matrix = np.stack([past(offset) for offset in offsets], axis=1)
        count = np.isfinite(matrix).sum(axis=1)
        # Centre first, so a constant quote path is exactly zero change/std.
        matrix -= current[:, None]
        mean = np.full(n, np.nan)
        np.divide(np.nansum(matrix, axis=1), count, out=mean, where=count > 0)
        if transform == 'trailing_mean_delta':
            result = -mean  # current minus mean of past/current observations
        else:
            centred = matrix - mean[:, None]
            variance = np.full(n, np.nan)
            np.divide(np.nansum(centred**2, axis=1), count, out=variance, where=count > 0)
            result = np.sqrt(variance)  # Population, not sample standard deviation.
        required = max(spec['minimum_observations'], math.ceil(len(offsets)*spec['minimum_window_coverage']))
        result[~np.isfinite(current) | (count < required)] = np.nan
    if np.any(np.isinf(result)):
        raise ValueError('nonfinite transformed output')
    return {'values': result, 'available': np.isfinite(result),
            'observations_used': count, 'feature_available_ms': decision_ms.copy(),
            'spec': dict(spec), 'full_population_rows': n,
            'future_labels_used': False, 'normalizer_fitted': False}
