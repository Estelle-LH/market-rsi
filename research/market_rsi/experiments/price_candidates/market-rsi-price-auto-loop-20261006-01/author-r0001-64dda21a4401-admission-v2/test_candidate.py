import numpy as np
from candidate import fit_predict


def test_candidate():
    x = np.zeros((6, 13), dtype=object)
    x[:, 1] = [1.0, 2.0, None, np.nan, np.inf, -np.inf]
    x[:, 0] = np.nan
    x[:, 2:] = np.inf
    y = np.array([2.0, -1.0, 20.0, 30.0, 40.0, 50.0])
    weights = np.array([1.0, 3.0, 5.0, 7.0, 0.0, 11.0])
    xc = np.zeros((8, 13), dtype=object)
    xc[:, 1] = [1.0, -2.0, 0.0, None, np.nan, np.inf, -np.inf, 10.0]
    xc[:, 0] = np.inf
    xc[:, 2:] = np.nan
    history = [np.empty((0, 3)) for _ in range(len(x))]
    check_history = [np.empty((0, 3)) for _ in range(len(xc))]
    clean_check_gap = np.array([1.0, -2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 10.0])
    expected = (-2.0 / 13.0) * clean_check_gap
    prediction = fit_predict(x, y, weights, xc, history, check_history, seed=314159)
    assert prediction.ndim == 1 and prediction.shape == (len(xc),)
    assert np.all(np.isfinite(prediction))
    np.testing.assert_allclose(prediction, expected, rtol=1e-12, atol=1e-12)
    assert prediction[-1] < -1.0

    x_other = np.full(x.shape, 99.0, dtype=object)
    x_other[:, 1] = x[:, 1]
    xc_other = np.full(xc.shape, -99.0, dtype=object)
    xc_other[:, 1] = xc[:, 1]
    other_history = [np.array([[-900.0, 0.4, 1.0], [-30.0, 0.5, 2.0]]) for _ in range(len(x))]
    other_check_history = [np.array([[-60.0, 0.6, 1.0]]) for _ in range(len(xc))]
    unchanged = fit_predict(x_other, y, weights * 1000.0, xc_other, other_history, other_check_history, seed=7)
    np.testing.assert_allclose(unchanged, expected, rtol=1e-12, atol=1e-12)

    reversed_sign = fit_predict(x, -y, weights, xc, history, check_history, seed=314159)
    np.testing.assert_allclose(reversed_sign, -expected, rtol=1e-12, atol=1e-12)

    first_only = np.zeros_like(weights)
    first_only[0] = 7.0
    single_row = fit_predict(x, y, first_only, xc, history, check_history, seed=314159)
    np.testing.assert_allclose(single_row, clean_check_gap, rtol=1e-12, atol=1e-12)

    zero_gap = x.copy()
    zero_gap[:, 1] = 0.0
    zero_prediction = fit_predict(zero_gap, y, weights, xc, history, check_history, seed=314159)
    np.testing.assert_array_equal(zero_prediction, np.zeros(len(xc)))

    unavailable_gap = x.copy()
    unavailable_gap[:, 1] = [None, np.nan, np.inf, -np.inf, None, np.nan]
    unavailable_prediction = fit_predict(unavailable_gap, y, weights, xc, history, check_history, seed=314159)
    np.testing.assert_array_equal(unavailable_prediction, np.zeros(len(xc)))

    empty_prediction = fit_predict(x, y, weights, np.empty((0, 13)), history, [], seed=314159)
    assert empty_prediction.shape == (0,)
    assert np.all(np.isfinite(empty_prediction))


if __name__ == '__main__':
    test_candidate()
