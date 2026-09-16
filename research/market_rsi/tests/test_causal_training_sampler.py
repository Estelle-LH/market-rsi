import copy
import unittest

from causal_training_sampler import sampling_contract, select_training_rows


def row(i, *, market="m", price=0.5, size=10.0):
    return {"row_id": f"r{i}", "game_id": "g", "market_id": market,
            "decision_ms": i * 1000, "feature_available_ms": i * 1000,
            "features": {"mid": price, "size": size}, "target": 0.6}


def policy(p=0.25, weighting="inverse_probability"):
    return sampling_contract(feature_names=["mid", "size"], quiet_keep_probability=p,
                             weighting=weighting, seed=23)


def choose(rows, contract=None):
    return select_training_rows(rows, contract=contract or policy(), role="opened_train")


class CausalTrainingSamplerTests(unittest.TestCase):
    def test_probability_one_keeps_all_with_unit_weight(self):
        masks = choose([row(i) for i in range(50)], policy(1))
        self.assertTrue(all(m["keep"] and m["loss_weight"] == 1 for m in masks))

    def test_changes_in_size_are_kept_even_when_price_does_not_move(self):
        masks = choose([row(i, size=float(i)) for i in range(50)])
        self.assertTrue(all(m["keep"] for m in masks))

    def test_future_targets_do_not_change_sampling(self):
        rows = [row(i) for i in range(100)]
        modified = copy.deepcopy(rows)
        for item in modified:
            item["target"] = 0.5
        self.assertEqual(choose(rows), choose(modified))

    def test_appending_future_rows_does_not_change_prefix(self):
        rows = [row(i) for i in range(100)]
        self.assertEqual(choose(rows[:50]), choose(rows)[:50])

    def test_input_is_not_changed(self):
        rows = [row(i) for i in range(100)]
        original = copy.deepcopy(rows)
        choose(rows)
        self.assertEqual(rows, original)

    def test_weights_restore_probability_for_selected_rows(self):
        masks = choose([row(i) for i in range(1000)])
        self.assertTrue(any(not m["keep"] for m in masks))
        self.assertTrue(any(m["keep"] and m["state"] == "repeated" for m in masks))
        for mask in masks:
            if mask["keep"]:
                self.assertAlmostEqual(mask["loss_weight"] * mask["inclusion_probability"], 1.)
            else:
                self.assertEqual(mask["loss_weight"], 0.)

    def test_different_weighting_uses_identical_membership(self):
        rows = [row(i) for i in range(1000)]
        a, b = choose(rows), choose(rows, policy(weighting="unweighted"))
        self.assertEqual([m["keep"] for m in a], [m["keep"] for m in b])
        self.assertTrue(all(m["loss_weight"] == 1 for m in b if m["keep"]))

    def test_dev_and_test_rejected(self):
        for role in ("dev", "final", "train", "raw_events"):
            with self.assertRaisesRegex(ValueError, "opened_train"):
                select_training_rows([row(1)], contract=policy(), role=role)

    def test_new_market_and_day_do_not_inherit_quiet_flag(self):
        rows = [row(1), row(2, market="other"), row(86401)]
        self.assertTrue(all(m["state"] == "first" for m in choose(rows)))

    def test_future_feature_is_rejected(self):
        value = row(1)
        value["feature_available_ms"] += 1
        with self.assertRaisesRegex(ValueError, "future feature"):
            choose([value])

    def test_duplicate_identity_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            choose([row(1), row(1)])

    def test_zero_probability_and_contract_mutation_rejected(self):
        for p in (0, -1, float("nan"), 2, True):
            with self.assertRaises(ValueError):
                policy(p)
        changed = policy()
        changed["future_labels_used_for_selection"] = True
        with self.assertRaisesRegex(ValueError, "contract has changed"):
            choose([row(1)], changed)


if __name__ == "__main__":
    unittest.main()
