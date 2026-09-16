"""Research-backed sports method choices and their executable status.

This catalog does not activate dependencies or pick a winner.  A controller
must change one causal stage at a time and use request_capability for methods
that are not already implemented by the frozen trainer.
"""
from market_rsi import digest


SOURCES = [
    {
        "id": "yurko-ventura-horowitz-2019",
        "url": "https://doi.org/10.1515/jqas-2018-0010",
        "finding": "NFL play value and win probability can be estimated from public PBP; their WP example uses a generalized additive model and checks calibration.",
        "transfer_limit": "Player WAR is not a prediction-market response study; team strength and market prices require separate controls.",
    },
    {
        "id": "baldwin-nflfastr-models-2021",
        "url": "https://opensourcefootball.com/posts/2020-09-28-nflfastr-ep-wp-and-cp-models/",
        "finding": "nflfastR uses tree-based state models and reports calibration, including a spread-aware WP variant.",
        "transfer_limit": "Package model quality does not prove prediction-market alpha and its pregame spread is a separate input family.",
    },
    {
        "id": "jorda-2005-local-projections",
        "url": "https://doi.org/10.1257/0002828053828518",
        "finding": "Separate horizon regressions estimate dynamic responses without committing to one full multivariate dynamic system.",
        "transfer_limit": "Our plays are clustered within games and not exogenous macro shocks; use game-level blocks and descriptive language first.",
    },
    {
        "id": "chen-guestrin-2016-xgboost",
        "url": "https://doi.org/10.1145/2939672.2939785",
        "finding": "Regularized tree boosting captures nonlinear interactions and sparse inputs at scale.",
        "transfer_limit": "Adding XGBoost changes the trainer and dependency surface; it needs a separate canary and same-data comparison.",
    },
    {
        "id": "guo-et-al-2017-calibration",
        "url": "https://proceedings.mlr.press/v70/guo17a.html",
        "finding": "Post-hoc temperature scaling can improve probabilistic calibration using held-out calibration data.",
        "transfer_limit": "It was studied on neural classifiers; it cannot be fitted on Final and may not help tree or regression outputs.",
    },
]


METHODS = [
    {
        "id": "zero_change_persistence",
        "stage": "market_response",
        "status": "executable_baseline",
        "changes": "none",
        "target": "future home-outcome trade-price delta",
        "reason": "A learned model must beat predicting no market change on exactly the same game-play rows.",
        "primary_metrics": ["paired_mse_delta", "calibration_slope", "game_block_interval"],
    },
    {
        "id": "ridge_response",
        "stage": "market_response",
        "status": "executable_now",
        "trainer_key": "ridge",
        "changes": "prediction",
        "reason": "Low-variance linear baseline with auditable coefficients.",
        "primary_metrics": ["paired_mse_delta", "pearson_ic", "rank_ic", "positive_game_fraction"],
    },
    {
        "id": "elastic_net_response",
        "stage": "market_response",
        "status": "executable_now",
        "trainer_key": "elastic_net",
        "changes": "prediction",
        "reason": "Sparse linear alternative when correlated state features are present.",
        "primary_metrics": ["paired_mse_delta", "selected_feature_stability", "game_block_interval"],
    },
    {
        "id": "random_forest_response",
        "stage": "market_response",
        "status": "executable_now",
        "trainer_key": "random_forest",
        "changes": "prediction",
        "reason": "Bounded nonlinear comparison without adding a new dependency.",
        "primary_metrics": ["paired_mse_delta", "rank_ic", "game_block_interval"],
    },
    {
        "id": "hist_gradient_boosting_response",
        "stage": "market_response",
        "status": "executable_now",
        "trainer_key": "hist_gradient_boosting",
        "changes": "prediction",
        "reason": "Captures nonlinear interactions among score, clock, field position and pre-play market state.",
        "primary_metrics": ["paired_mse_delta", "calibration_slope", "game_block_interval"],
    },
    {
        "id": "generalized_additive_win_probability",
        "stage": "state_prediction",
        "status": "capability_required",
        "research_source_ids": ["yurko-ventura-horowitz-2019"],
        "changes": "prediction",
        "reason": "Interpretable nonlinear state baseline for time, score and field position.",
        "primary_metrics": ["brier_score", "log_loss", "reliability_curve", "game_block_interval"],
    },
    {
        "id": "xgboost_win_probability",
        "stage": "state_prediction",
        "status": "capability_required",
        "research_source_ids": ["baldwin-nflfastr-models-2021", "chen-guestrin-2016-xgboost"],
        "changes": "prediction",
        "reason": "High-capacity nonlinear state model after the simpler calibrated baseline is established.",
        "primary_metrics": ["brier_score", "log_loss", "reliability_curve", "game_block_interval"],
    },
    {
        "id": "game_clustered_local_projection",
        "stage": "market_response",
        "status": "implemented_unreleased",
        "research_source_ids": ["jorda-2005-local-projections"],
        "changes": "evaluation",
        "reason": "Estimate separate 30s, 60s and 300s descriptive response curves on common play support with game-level dependence preserved.",
        "primary_metrics": ["horizon_response", "game_clustered_interval", "coverage_by_horizon"],
        "interpretation": "Score changes are endogenous events, so coefficients are descriptive adjusted associations, not causal effects.",
    },
    {
        "id": "heldout_temperature_calibration",
        "stage": "calibration",
        "status": "capability_required",
        "research_source_ids": ["guo-et-al-2017-calibration"],
        "changes": "calibration",
        "reason": "Separate probability calibration after a state model is frozen, using Route-Dev only.",
        "primary_metrics": ["brier_score", "log_loss", "calibration_slope", "expected_calibration_error"],
    },
]


STAGES = ("state_prediction", "market_response", "calibration")


def inspect(stage: str) -> dict:
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {', '.join(STAGES)}")
    methods = [method for method in METHODS if method["stage"] == stage]
    result = {
        "schema": "sports_method_library_v1",
        "stage": stage,
        "methods": methods,
        "research_sources": SOURCES,
        "selection_rule": "Compare methods on identical data, target, horizon and game split; change one causal stage per candidate.",
        "unsupported_method_rule": "status=capability_required must go through request_capability and tests; status=implemented_unreleased has tests but still requires a new harness release before controller execution.",
        "controller_selects_method": True,
        "library_selects_winner": False,
        "scientific_result": False,
    }
    result["library_sha256"] = digest(result)
    return result
