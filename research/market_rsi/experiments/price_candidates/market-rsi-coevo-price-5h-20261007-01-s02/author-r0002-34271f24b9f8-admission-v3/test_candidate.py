import numpy as np
from candidate import fit_predict


def test_candidate():
    history = [np.zeros((2, 13), dtype=np.float64)]
    check_history = [np.ones((2, 13), dtype=np.float64)]

    # Orthogonal standardized columns: every feature and the constant shrink by half.
    basis = np.vstack((np.eye(13), -np.eye(13)))
    offsets = np.linspace(-3.0, 3.0, 13)
    multipliers = np.arange(1.0, 14.0)
    beta = np.linspace(-0.02, 0.04, 13)
    x = offsets + basis * multipliers
    y = 0.03 + np.sqrt(13.0) * (basis @ beta)
    weights = np.ones(26)
    check_basis = np.vstack((np.zeros(13), np.full(13, 0.25), np.full(13, -0.5)))
    xc = offsets + check_basis * multipliers
    expected = 0.5 * (0.03 + np.sqrt(13.0) * (check_basis @ beta))
    prediction = fit_predict(x, y, weights, xc, history, check_history, seed=7)
    assert prediction.shape == (3,)
    assert np.all(np.isfinite(prediction))
    assert np.allclose(prediction, expected, rtol=1e-11, atol=1e-12)
    permuted = fit_predict(x[:, ::-1], y, weights, xc[:, ::-1], [], [], seed=19)
    assert np.allclose(permuted, expected, rtol=1e-11, atol=1e-12)
    zero = fit_predict(x, np.zeros(26), weights, xc, history, check_history)
    assert np.array_equal(zero, np.zeros(3))

    # Unequal weights, missing entries, and a column with zero finite weighted mass.
    x = np.zeros((5, 13))
    x[:, 0] = [1.0, 3.0, np.nan, np.inf, -np.inf]
    x[:, 4] = [-1.0, 2.0, 1.0, np.nan, 4.0]
    x[:, 7] = [np.nan, np.inf, -np.inf, 9.0, np.nan]
    y = np.array([0.04, -0.02, 0.01, 0.99, -0.03])
    weights = np.array([1.0, 3.0, 2.0, 0.0, 4.0])
    xc = np.zeros((4, 13))
    xc[:, 0] = [np.nan, 3.5, 2.5, -2.0]
    xc[:, 4] = [1.0, np.inf, 2.3, 4.5]
    xc[:, 7] = [100.0, -100.0, np.nan, np.inf]
    originals = (x.copy(), y.copy(), weights.copy(), xc.copy())

    # Fit means are 2.5 and 2.3; post-imputation variances are 0.3 and 2.61.
    correlation = 0.45 / np.sqrt(0.3 * 2.61)
    b0 = -0.009 / np.sqrt(0.3)
    b4 = -0.0344 / np.sqrt(2.61)
    denominator = 4.0 - correlation * correlation
    coefficient0 = (2.0 * b0 - correlation * b4) / denominator
    coefficient4 = (2.0 * b4 - correlation * b0) / denominator
    expected = (
        np.array([0.0, 1.0, 0.0, -4.5]) / np.sqrt(0.3) * coefficient0
        + np.array([-1.3, 0.0, 0.0, 2.2]) / np.sqrt(2.61) * coefficient4
        - 0.006
    )
    prediction = fit_predict(x, y, weights, xc, history, check_history)
    assert prediction.shape == (4,)
    assert np.allclose(prediction, expected, rtol=1e-11, atol=1e-12)
    for actual, original in zip((x, y, weights, xc), originals):
        assert np.array_equal(actual, original, equal_nan=True)
    for factor in (1e200, 1e-200):
        scaled = fit_predict(x, y, weights * factor, xc, history, check_history)
        assert np.allclose(scaled, expected, rtol=1e-11, atol=1e-12)
    changed_y = y.copy()
    changed_y[3] = -100.0
    unchanged = fit_predict(x, changed_y, weights, xc, [], [])
    assert np.allclose(unchanged, expected, rtol=1e-11, atol=1e-12)
    extended = np.vstack((xc, np.full((2, 13), 1e6)))
    extended_prediction = fit_predict(x, y, weights, extended, [], [], seed=99)
    assert np.allclose(extended_prediction[:4], expected, rtol=1e-11, atol=1e-12)
    empty = fit_predict(x, y, weights, np.empty((0, 13)), [], [])
    assert empty.shape == (0,)
    assert np.all(np.isfinite(empty))

    # Constant, all-missing, and at/below-threshold columns must be zeroed.
    tiny = np.full((4, 13), 2.0)
    signs = np.array([-1.0, 1.0, -1.0, 1.0])
    tiny[:, 0] = signs * 1e-13
    tiny[:, 1] = signs * 1e-12
    tiny[:, 2] = np.nan
    tiny_y = np.array([0.1, -0.2, 0.4, 0.5])
    far_check = np.full((3, 13), 1e9)
    far_check[0, 2] = np.nan
    constant = fit_predict(tiny, tiny_y, np.ones(4), far_check, [], [])
    assert np.allclose(constant, np.full(3, 0.1), rtol=1e-11, atol=1e-12)
    negative = fit_predict(tiny, np.full(4, -0.6), np.ones(4), far_check, [], [])
    assert np.allclose(negative, np.full(3, -0.3), rtol=1e-11, atol=1e-12)

    def reject(a, b, c, d):
        try:
            fit_predict(a, b, c, d, history, check_history)
        except ValueError:
            return
        raise AssertionError('Expected invalid fit input to raise ValueError.')

    a = np.zeros((3, 13))
    b = np.array([0.01, -0.02, 0.03])
    c = np.ones(3)
    d = np.zeros((2, 13))
    invalid_cases = (
        (a[:, :12], b, c, d),
        (a, b, c, d[:, :12]),
        (a.ravel(), b, c, d),
        (a, b[:, None], c, d),
        (a, b[:-1], c, d),
        (a, b, c[:, None], d),
        (a, b, c[:-1], d),
        (a[:0], b[:0], c[:0], d),
        (a, np.array([np.nan, 0.0, 0.0]), c, d),
        (a, np.array([np.inf, 0.0, 0.0]), c, d),
        (a, b, np.zeros(3), d),
        (a, b, np.array([1.0, -1.0, 1.0]), d),
        (a, b, np.array([1.0, np.nan, 1.0]), d),
        (a, b, np.array([1.0, np.inf, 1.0]), d),
    )
    for bad_x, bad_y, bad_w, bad_xc in invalid_cases:
        reject(bad_x, bad_y, bad_w, bad_xc)


if __name__ == '__main__':
    test_candidate()
