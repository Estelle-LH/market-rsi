import numpy as np


def _gap(features):
    features = np.asarray(features)
    if features.ndim != 2 or features.shape[1] != 13:
        raise ValueError('Expected a two-dimensional 13-feature array.')
    g = np.asarray(features[:, 1], dtype=np.float64)
    return np.where(np.isfinite(g), g, 0.0)


def fit_predict(x, y, weights, xc, history, check_history, *, seed=314159):
    g = _gap(x)
    gc = _gap(xc)
    y = np.asarray(y, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    if y.ndim != 1 or w.ndim != 1 or y.size != g.size or w.size != g.size:
        raise ValueError('Fit labels and weights must be matching one-dimensional arrays.')
    if g.size == 0:
        raise ValueError('The fit population must be nonempty.')
    if not np.all(np.isfinite(y)):
        raise ValueError('Fit labels must be finite.')
    if not np.all(np.isfinite(w)) or np.any(w < 0.0):
        raise ValueError('Fit weights must be finite and nonnegative.')
    weight_scale = float(np.max(w))
    if weight_scale == 0.0:
        raise ValueError('Fit weights must have positive total mass.')
    w = w / weight_scale
    w = w / np.sum(w)

    magnitude = np.abs(g)
    order = np.argsort(magnitude, kind='mergesort')
    cumulative = np.cumsum(w[order])
    half_mass = 0.5 * float(np.sum(w))
    cut = int(np.searchsorted(cumulative, half_mass, side='left'))
    threshold = float(magnitude[order[cut]])
    lower = magnitude <= threshold

    # One joint diagonal normal-equation solve: regressors have disjoint support.
    coefficients = np.zeros(2, dtype=np.float64)
    for k, mask in enumerate((lower, ~lower)):
        gr = g[mask]
        yr = y[mask]
        wr = w[mask]
        s = float(np.sum(wr * (gr * gr)))
        c = float(np.sum(wr * gr * yr))
        if not np.isfinite(s) or not np.isfinite(c):
            raise ValueError('Nonfinite coefficient statistics.')
        coefficients[k] = (0.5 * c) / s if s > 0.0 else 0.0
    if not np.all(np.isfinite(coefficients)):
        raise ValueError('Nonfinite coefficients.')

    prediction = np.where(np.abs(gc) <= threshold, coefficients[0], coefficients[1]) * gc
    if not np.all(np.isfinite(prediction)):
        raise ValueError('Nonfinite predictions.')
    return prediction
