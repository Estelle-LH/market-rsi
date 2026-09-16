"""Runner-frozen primary-source literature snapshot for the controller."""
from __future__ import annotations

import hashlib


PAPERS = (
    ("gould-bonart-2015", "Queue Imbalance as a One-Tick-Ahead Price Predictor in a Limit Order Book",
     "https://arxiv.org/abs/1512.03492", 2015,
     "Studies logistic and local-logistic links between top-of-book queue imbalance and the next mid-price direction."),
    ("cont-kukanov-stoikov-2010", "The Price Impact of Order Book Events",
     "https://arxiv.org/abs/1011.6402", 2010,
     "Finds a robust short-horizon linear relation between order-flow imbalance and price changes, scaled by market depth."),
    ("zhang-zohren-roberts-deeplob-2018", "DeepLOB: Deep Convolutional Neural Networks for Limit Order Books",
     "https://arxiv.org/abs/1808.03668", 2018,
     "Uses past and future mid-price averages and a deadband to reduce noisy up, flat and down labels; also studies transferable order-book features."),
    ("kolm-turiel-westray-2021", "Deep Order Flow Imbalance: Extracting Alpha at Multiple Horizons from the Limit Order Book",
     "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3900141", 2021,
     "Forecasts high-frequency returns at multiple horizons and finds stationary order-flow inputs can outperform raw order-book states."),
    ("sirignano-cont-2018", "Universal Features of Price Formation in Financial Markets: Perspectives from Deep Learning",
     "https://arxiv.org/abs/1803.06917", 2018,
     "Studies out-of-sample price-move direction across assets and finds pooled price and order-flow history can transfer across instruments."),
    ("bergmeir-hyndman-koo-2018", "A Note on the Validity of Cross-Validation for Evaluating Autoregressive Time Series Prediction",
     "https://doi.org/10.1016/j.csda.2017.11.003", 2018,
     "Explains why serial correlation and nonstationarity make time-series validation nontrivial and studies conditions for valid cross-validation."),
    ("hyndman-koehler-2006", "Another Look at Measures of Forecast Accuracy",
     "https://doi.org/10.1016/j.ijforecast.2006.03.001", 2006,
     "Shows common forecast metrics can be degenerate and develops scale-free comparison through errors scaled by a naive forecast."),
    ("podolskij-vetter-2016", "Between Data Cleaning and Inference: Pre-Averaging and Robust Estimators of the Efficient Price",
     "https://doi.org/10.1016/j.jeconom.2016.05.005", 2016,
     "Studies pre-averaging and robust local M-estimation for reducing high-frequency microstructure noise while retaining economically meaningful jumps."),
    ("gneiting-raftery-2007", "Strictly Proper Scoring Rules, Prediction, and Estimation",
     "https://doi.org/10.1198/016214506000001437", 2007,
     "Develops proper scores that reward honest probability forecasts and separates calibration from sharpness."),
    ("guo-et-al-2017", "On Calibration of Modern Neural Networks",
     "https://proceedings.mlr.press/v70/guo17a.html", 2017,
     "Compares calibration behavior and shows that a simple held-out temperature-scaling step can be effective."),
    ("kuleshov-deshpande-2022", "Calibrated and Sharp Uncertainties in Deep Learning via Density Estimation",
     "https://proceedings.mlr.press/v162/kuleshov22a.html", 2022,
     "Separates calibration from sharpness and studies recalibration without giving up predictive performance."),
    ("arrieta-ibarra-et-al-2022", "Metrics of Calibration for Probabilistic Predictions",
     "https://www.jmlr.org/papers/v23/22-0658.html", 2022,
     "Explains finite-sample tradeoffs in calibration diagnostics and alternatives to arbitrary histogram bins."),
    ("waghmare-ziegel-2025", "Proper Scoring Rules for Estimation and Forecast Evaluation",
     "https://arxiv.org/abs/2504.01781", 2025,
     "Reviews why proper scores support honest probabilistic forecasts and how they are used for estimation and evaluation."),
    ("kagan-baiocchi-2026", "Calibration in Prediction Markets: Theory and Evidence",
     "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7355520", 2026,
     "Studies calibration and accuracy across a large set of resolved Kalshi markets and several market conditions."),
    ("turtel-et-al-2026", "How Proper Scoring Rules Shape LLM Forecasting",
     "https://arxiv.org/abs/2608.28482", 2026,
     "Reports that different proper-score training objectives can yield different calibration and error structures in LLM forecasters."),
)


def literature_snapshot() -> dict:
    papers = []
    for paper_id, title, url, year, summary in PAPERS:
        papers.append({
            "paper_id": paper_id,
            "title": title,
            "url": url,
            "year": year,
            "abstract": "Runner-authored synopsis: " + summary,
            "content_sha256": hashlib.sha256(summary.encode()).hexdigest(),
        })
    return {"schema": "market_public_literature_snapshot_v1", "papers": papers}
