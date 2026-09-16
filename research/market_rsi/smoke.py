"""Two-round fabricated-data plumbing check, never a market/agent result."""
import argparse
import math
import random
import inspect
from datetime import datetime, timezone
from pathlib import Path

from learner import fit_predict
from market_rsi import Round, digest, evaluator_hash, fresh_json


def fixture_rows():
    rng, rows = random.Random(23), []
    for split, day, games in [("train", 1, 4), ("dev", 2, 3)]:
        base = int(datetime(2026, 1, day, tzinfo=timezone.utc).timestamp() * 1000)
        for game in range(games):
            for i in range(60):
                x, z = rng.uniform(-2, 2), rng.uniform(-2, 2)
                t = base + game * 100000 + i * 1000
                rows.append(dict(row_id=f"{split}-{game}-{i}", game_id=f"{split}-{game}",
                                 market_id=f"m-{game}", side="bid", split=split,
                                 date=f"2026-01-{day:02}", decision_ms=t,
                                 feature_available_ms=t, label_end_ms=t + 250,
                                 features=dict(imbalance=x, depth=z),
                                 label=int(rng.random() < 1 / (1 + math.exp(-(1.6 * x - 0.2 * z - 1.2))))))
    return rows


def specs(parent_config, parent_id="fixture-parent"):
    protocol = dict(actors=["forecaster_a", "forecaster_b", "forecaster_c"], parent_id=parent_id,
                    parent_config=parent_config, primary_metric="brier", success_delta=0,
                    evidence_class="fixture", final_test_access=False, features=["imbalance", "depth"],
                    horizon_ms=250, alert_fraction=0.1, evaluator_sha256=evaluator_hash(fit_predict),
                    evaluator_source_path=inspect.getsourcefile(fit_predict))
    baseline = {s: digest(s) for s in ("raw_data", "raw_indicator_signal", "prediction", "objective", "pnl")}
    baseline["prediction"] = digest(parent_config)
    plans = []
    for name, steps, l2 in [("more_steps", 60, .01), ("strong_regularization", 30, 2.0), ("smaller_update", 10, .01)]:
        config = dict(steps=steps, learning_rate=.15, l2=l2)
        if "initial_checkpoint" in parent_config:
            config["initial_checkpoint"] = parent_config["initial_checkpoint"]
        components = dict(baseline, prediction=digest(config))
        plans.append(dict(id=name, parent_id=parent_id, changed_stage="prediction", config=config,
                          baseline_components=baseline, candidate_components=components,
                          author="fixture-generator", hypothesis="plumbing check only"))
    return protocol, plans


def run(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    data = root / "fabricated-observations.json"
    fresh_json(data, fixture_rows())
    parent_config = dict(steps=10, learning_rate=.1, l2=.01)
    history = []
    for number in (1, 2):
        protocol, plans = specs(parent_config, f"fixture-parent-{number}")
        forecasts = {a: dict(more_steps=.7, strong_regularization=.3, smaller_update=.45)
                     for a in protocol["actors"]}
        trades = [dict(actor=a, candidate="more_steps", side="yes", shares=1)
                  for a in protocol["actors"]]
        round_ = Round.create(root / f"round-{number:02}", protocol, plans, data)
        round_.commit_forecasts(data, forecasts, trades, "forecaster_a")
        result = round_.evaluate(data, fit_predict)
        chosen = result["choices"]["market"]
        if result["outcomes"][chosen] != 1:
            chosen = "parent"
        parent_config = dict(initial_checkpoint=result["candidates"][chosen]["metadata"]["checkpoint"],
                             frozen_parent=True)
        history.append(dict(round=number, selected=chosen, results_file=str(round_.root / "results.json")))
    fresh_json(root / "summary.json", dict(evidence_class="fixture", actual_agent_calls=0,
                                           market_result_claim=False, reused_dev_for_plumbing_only=True,
                                           rounds=history))
    print(root / "summary.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    run(parser.parse_args().output)
