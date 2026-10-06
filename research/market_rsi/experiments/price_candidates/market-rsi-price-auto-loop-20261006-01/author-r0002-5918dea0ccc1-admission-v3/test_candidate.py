import numpy as np
from candidate import fit_predict


def _features(gaps):
    gaps = np.asarray(gaps, dtype=np.float64)
    x = np.zeros((gaps.size, 13), dtype=np.float64)
    x[:, 1] = gaps
    return x


def _run(gaps, labels, weights, checks, *, seed=314159):
    x = _features(gaps)
    xc = _features(checks)
    history = [np.empty((0, 13)) for _ in range(x.shape[0])]
    check_history = [np.empty((0, 13)) for _ in range(xc.shape[0])]
    return fit_predict(x, labels, weights, xc, history, check_history, seed=seed)


def test_candidate():
    # Half-mass boundary and tied magnitudes: both signs at |g|=1 are lower.
    g = np.array([0.0, 1.0, -1.0, 3.0, -3.0])
    y = np.array([7.0, 2.0, -2.0, -6.0, 6.0])
    w = np.array([1.0, 2.0, 1.0, 1.0, 1.0])
    gc = np.array([0.0, 0.5, -1.0, 1.0, 2.0, -3.0, 3.0, np.nan, np.inf, -np.inf])
    expected = np.array([0.0, 0.5, -1.0, 1.0, -2.0, 3.0, -3.0, 0.0, 0.0, 0.0])
    actual = _run(g, y, w, gc)
    assert actual.shape == (gc.size,)
    assert np.all(np.isfinite(actual))
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)

    # Common weight scaling and fit-row permutation do not change the model.
    for scale in (1e-250, 1e250):
        np.testing.assert_allclose(_run(g, y, w * scale, gc), expected, rtol=1e-12, atol=1e-12)
    order = np.array([4, 2, 0, 3, 1])
    np.testing.assert_allclose(_run(g[order], y[order], w[order], gc), expected, rtol=1e-12, atol=1e-12)

    # Only column 1 is used; history and seed do not enter the closed-form fit.
    x = np.full((g.size, 13), np.nan)
    xc = np.full((gc.size, 13), np.inf)
    x[:, 1] = g
    xc[:, 1] = gc
    history = [np.zeros((1, 13)) for _ in range(g.size)]
    check_history = [np.zeros((1, 13)) for _ in range(gc.size)]
    np.testing.assert_allclose(
        fit_predict(x, y, w, xc, history, check_history, seed=7),
        expected, rtol=1e-12, atol=1e-12,
    )

    # Fitting weights, not an unweighted median or check magnitudes, set t=1.
    np.testing.assert_allclose(
        _run([1, 2, 3, 4], [4, -4, -6, -8], [5, 1, 1, 1], [0.5, 1, 1.5, 2, 4]),
        [1, 2, -1.5, -2, -4], rtol=1e-12, atol=1e-12,
    )

    # A zero lower-regime denominator gives zero there; t=0 is retained.
    np.testing.assert_allclose(
        _run([0, 0, 2, -2], [9, -9, 8, -8], [1, 1, 1, 1], [0, 0.5, -1, 2, np.nan]),
        [0, 1, -2, 4, 0], rtol=1e-12, atol=1e-12,
    )

    # All tied fitting magnitudes leave the upper coefficient at zero.
    np.testing.assert_allclose(
        _run([1, -1, 1, -1], [2, -2, 2, -2], [1, 1, 1, 1], [1, -1, 0, 2, -2]),
        [1, -1, 0, 0, 0], rtol=1e-12, atol=1e-12,
    )
    np.testing.assert_allclose(_run([0, 0], [10, -10], [1, 1], [0, 1, -2]), [0, 0, 0])

    # Nonfinite fitting gaps become zero before threshold and coefficient fitting.
    np.testing.assert_allclose(
        _run([np.nan, np.inf, -np.inf, 1, 3], [9, -4, 7, 2, -6], [1, 1, 1, 1, 1], [0, 0.5, -1, 3, np.nan]),
        [0, -0.4, 0.8, -2.4, 0], rtol=1e-12, atol=1e-12,
    )

    # Zero-weight fitting rows contribute no threshold mass or coefficient terms.
    np.testing.assert_allclose(
        _run([1, 2, 100], [2, -4, 10000], [1, 1, 0], [1, 2, 100]),
        [1, -2, -100], rtol=1e-12, atol=1e-12,
    )
    empty = _run(g, y, w, [])
    assert empty.shape == (0,)
    assert np.all(np.isfinite(empty))

    x = _features(g)
    xc = _features(gc)
    invalid = [
        (_features([]), np.array([]), np.array([]), xc),
        (x[:, :12], y, w, xc),
        (x.ravel(), y, w, xc),
        (x, y, w, xc[:, :12]),
        (x, y[:, None], w, xc),
        (x, y, w[:, None], xc),
        (x, y[:-1], w, xc),
        (x, y, w[:-1], xc),
        (x, np.array([np.nan, 2, -2, -6, 6]), w, xc),
        (x, np.array([np.inf, 2, -2, -6, 6]), w, xc),
        (x, y, np.zeros_like(w), xc),
        (x, y, np.array([-1, 2, 1, 1, 1]), xc),
        (x, y, np.array([np.nan, 2, 1, 1, 1]), xc),
        (x, y, np.array([np.inf, 2, 1, 1, 1]), xc),
    ]
    for xi, yi, wi, xci in invalid:
        try:
            fit_predict(xi, yi, wi, xci, [], [], seed=314159)
        except ValueError:
            pass
        else:
            raise AssertionError('Expected ValueError for invalid input.')


if __name__ == '__main__':
    test_candidate()
