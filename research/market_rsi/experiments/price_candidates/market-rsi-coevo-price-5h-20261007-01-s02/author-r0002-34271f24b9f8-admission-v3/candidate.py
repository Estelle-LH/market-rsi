import numpy as np
from sklearn.linear_model import Ridge


def _features(value):
    array = np.asarray(value, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 13:
        raise ValueError('Expected a two-dimensional 13-feature array.')
    return array


def fit_predict(x, y, weights, xc, history, check_history, *, seed=314159):
    x = _features(x)
    xc = _features(xc)
    y = np.asarray(y, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    if y.ndim != 1 or w.ndim != 1 or y.size != x.shape[0] or w.size != x.shape[0]:
        raise ValueError('Fit labels and weights must be matching one-dimensional arrays.')
    if x.shape[0] == 0:
        raise ValueError('The fit population must be nonempty.')
    if not np.all(np.isfinite(y)):
        raise ValueError('Fit labels must be finite.')
    if not np.all(np.isfinite(w)) or np.any(w < 0.0):
        raise ValueError('Fit weights must be finite and nonnegative.')
    largest = float(np.max(w))
    if largest == 0.0:
        raise ValueError('Fit weights must have positive total mass.')
    w = w / largest
    w = w / np.sum(w)

    finite = np.isfinite(x)
    mass = np.sum(w[:, None] * finite, axis=0)
    totals = np.sum(w[:, None] * np.where(finite, x, 0.0), axis=0)
    means = np.zeros(13, dtype=np.float64)
    observed = mass > 0.0
    means[observed] = totals[observed] / mass[observed]
    if not np.all(np.isfinite(means)):
        raise ValueError('Nonfinite fit means.')

    fit_filled = np.where(finite, x, means)
    check_filled = np.where(np.isfinite(xc), xc, means)
    centered = fit_filled - means
    scales = np.sqrt(np.sum(w[:, None] * (centered * centered), axis=0))
    if not np.all(np.isfinite(scales)):
        raise ValueError('Nonfinite fit scales.')
    active = scales > 1e-12
    z = np.zeros(x.shape, dtype=np.float64)
    zc = np.zeros(xc.shape, dtype=np.float64)
    z[:, active] = centered[:, active] / scales[active]
    zc[:, active] = (check_filled[:, active] - means[active]) / scales[active]
    if not np.all(np.isfinite(z)) or not np.all(np.isfinite(zc)):
        raise ValueError('Nonfinite standardized features.')

    design = np.column_stack((z, np.ones(x.shape[0], dtype=np.float64)))
    check_design = np.column_stack((zc, np.ones(xc.shape[0], dtype=np.float64)))
    model = Ridge(alpha=1.0, fit_intercept=False, solver='cholesky')
    model.fit(design, y, sample_weight=w)
    if xc.shape[0] == 0:
        return np.empty(0, dtype=np.float64)
    prediction = np.asarray(model.predict(check_design), dtype=np.float64)
    if prediction.shape != (xc.shape[0],) or not np.all(np.isfinite(prediction)):
        raise ValueError('Expected finite one-dimensional check predictions.')
    return prediction
