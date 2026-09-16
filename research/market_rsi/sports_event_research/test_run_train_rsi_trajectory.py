import unittest

from sports_event_research.run_train_rsi_trajectory import (
    BASE_RF,
    build_estimator,
    changed_parameters,
    choose_champion,
    initial_plans,
    next_rf_plan,
)


def evaluated_rf(candidate_id, mse, parameters):
    return {
        "plan": {
            "candidate_id": candidate_id,
            "family": "random_forest",
            "parameters": dict(parameters),
        },
        "mse": mse,
    }


class TrainRsiTrajectoryTests(unittest.TestCase):
    def test_initial_plans_are_frozen_and_unique(self):
        plans = initial_plans()
        self.assertEqual([plan["round"] for plan in plans], [1, 2, 3])
        self.assertEqual(len({plan["candidate_id"] for plan in plans}), 3)
        self.assertEqual(plans[2]["parameters"], BASE_RF)

    def test_adaptive_plan_uses_best_rf_and_changes_one_parameter(self):
        evaluated = {
            "zero-change": {"plan": {"family": "zero_change"}, "mse": 0.2},
            "rf-a": evaluated_rf("rf-a", 0.10, BASE_RF),
            "rf-b": evaluated_rf("rf-b", 0.09, {**BASE_RF, "max_depth": 12}),
        }
        plan = next_rf_plan(5, evaluated)
        self.assertEqual(plan["parent_id"], "rf-b")
        self.assertEqual(plan["parameters"]["min_samples_leaf"], 25)
        self.assertEqual(changed_parameters(evaluated["rf-b"]["plan"]["parameters"], plan["parameters"]),
                         ["min_samples_leaf"])

    def test_each_later_mutation_changes_one_parameter(self):
        evaluated = {"rf-a": evaluated_rf("rf-a", 0.1, BASE_RF)}
        for round_number, key, value in (
            (4, "max_depth", 12),
            (5, "min_samples_leaf", 25),
            (6, "max_features", 1.0),
            (7, "n_estimators", 400),
        ):
            plan = next_rf_plan(round_number, evaluated)
            self.assertEqual(plan["parameters"][key], value)
            self.assertEqual(len(changed_parameters(BASE_RF, plan["parameters"])), 1)

    def test_champion_retains_lowest_mse(self):
        evaluated = {
            "a": {"mse": 0.2},
            "b": {"mse": 0.1},
            "c": {"mse": 0.3},
        }
        self.assertEqual(choose_champion(evaluated), "b")

    def test_all_model_families_construct(self):
        for plan in initial_plans():
            model = build_estimator(plan)
            self.assertIsNotNone(model)


if __name__ == "__main__":
    unittest.main()
