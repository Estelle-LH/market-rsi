"""Prediction-first synthetic closed-loop primitives.

The package proves local orchestration and proper-score wiring only.  It does
not admit real data, untrusted execution, protected evaluation, promotion, or
PnL evidence.
"""

from .lineage import PredictionLineage
from .prediction_protocol import (
    LabelFreePredictionProtocol,
    prediction_submission,
    run_label_free_protocol,
)
from .probability_contract import (
    ProbabilityPolicy,
    build_candidate_views,
    validate_train_evaluation_rows,
)
from .proper_scoring import ProperScoreSpec, score_probability_forecasts

__all__ = [
    "LabelFreePredictionProtocol",
    "PredictionLineage",
    "ProbabilityPolicy",
    "ProperScoreSpec",
    "build_candidate_views",
    "prediction_submission",
    "run_label_free_protocol",
    "score_probability_forecasts",
    "validate_train_evaluation_rows",
]
