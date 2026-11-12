"""Tiny deterministic numerical checks; no downloads, datasets, or API calls."""
import io
import time


def run_checks():
    started = time.monotonic()
    import numpy as np
    import scipy.linalg
    from sklearn.linear_model import LinearRegression
    import joblib
    from threadpoolctl import threadpool_info, threadpool_limits

    checks = []
    with threadpool_limits(limits=1):
        actual = np.array([[1., 2.], [3., 4.]]) @ np.array([[5., 6.], [7., 8.]])
        np.testing.assert_allclose(actual, [[19., 22.], [43., 50.]], rtol=0, atol=1e-12)
        checks.append("numpy_matrix_product")
        matrix, rhs = np.array([[3., 1.], [1., 2.]]), np.array([9., 8.])
        solution = scipy.linalg.lu_solve(scipy.linalg.lu_factor(matrix), rhs)
        np.testing.assert_allclose(solution, [2., 3.], rtol=0, atol=1e-12)
        checks.append("scipy_lu_solve")
        x = np.arange(-2., 3.).reshape(-1, 1)
        model = LinearRegression().fit(x, 3 * x[:, 0] + 2)
        np.testing.assert_allclose(model.predict([[3.]]), [11.], rtol=0, atol=1e-12)
        checks.append("sklearn_linear_fit")
        stream = io.BytesIO()
        joblib.dump({"array": actual, "label": "synthetic"}, stream)
        stream.seek(0)
        restored = joblib.load(stream)
        np.testing.assert_array_equal(restored["array"], actual)
        if restored["label"] != "synthetic":
            raise ValueError("synthetic joblib roundtrip")
        checks.append("joblib_memory_roundtrip")
        pools = threadpool_info()
        if not pools or any(type(p.get("num_threads")) is not int or p["num_threads"] != 1 for p in pools):
            raise ValueError("single-thread numerical pools not observed")
        checks.append("threadpool_limit")
    return {"schema": "synthetic-native-math-v1", "passed": True, "checks": checks,
            "wall_seconds": round(time.monotonic() - started, 6),
            "external_model_api_calls": 0, "workload_admission": False}


if __name__ == "__main__":
    import json
    print(json.dumps(run_checks(), sort_keys=True))
