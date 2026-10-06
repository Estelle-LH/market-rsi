"""Controller-proposed score/time semantic checks, independent of builder algebra.

Numeric fixtures are an independent oracle at declared points, not a proof for
every input or a data/scoring/permission change. Called before any model fit.
"""
import math
from numbers import Real

VERSION = "derived_feature_semantic_contract_v1"
FORMULA_VERSION = "score_time_v1"
FIXTURES = (
    (0, 0, 0), (0, 1800, 0), (0, 3600, 0),
    (14, 0, 1), (-14, 0, -1), (14, 1800, .5), (-14, 1800, -.5),
    (14, 3600, 0), (-14, 3600, 0), (7, 1800, .25), (-7, 1800, -.25),
    (28, 900, .75), (-28, 900, -.75), (3.5, 2700, .0625), (-3.5, 2700, -.0625),
    (14, -100, 1), (-14, -100, -1), (14, 7200, 0), (-14, 7200, 0),
)
INVALID = ((float("nan"), 1800), (float("inf"), 1800),
           (14, float("nan")), (14, float("inf")), (True, 1800), (14, True))


def validate_feature(builder):
    """Return a receipt or fail; never fit, read data, or run candidate main."""
    if not callable(builder): raise ValueError("scalar feature builder required")
    for score, seconds, expected in FIXTURES:
        value = builder(score, seconds)
        if (isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value)
                or not -1 <= value <= 1 or not math.isclose(value, expected, rel_tol=0, abs_tol=1e-12)):
            raise ValueError(f"score-time semantic disagreement at score={score}, seconds={seconds}")
    for score, seconds in INVALID:
        try: builder(score, seconds)
        except (ValueError, TypeError): pass
        else: raise ValueError("nonfinite/non-numeric feature inputs must fail before fitting")
    return {"schema": VERSION, "passed": True, "formula_version": FORMULA_VERSION,
        "clipping_constants": {"score_divisor": 14, "regulation_seconds": 3600},
        "numeric_fixtures": len(FIXTURES), "invalid_input_fixtures": len(INVALID),
        "checked": ["finite inputs", "fixed clipping", "bounds", "tied-score zero",
                    "home-score antisymmetry", "remaining-time magnitude", "independent numeric values"],
        "statistical_fits": 0, "scope": "fixed synthetic semantic points; not all-input proof"}
