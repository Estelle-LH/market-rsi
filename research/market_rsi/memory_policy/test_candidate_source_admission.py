import unittest

from memory_policy.candidate_source_admission import (
    require_unchanged, select, validate_plan,
)


def rows(day, hours):
    return [{"session": f"{day}T{hour:02d}", "compressed_bytes": hour + 1}
            for hour in hours]


def plan():
    return {
        "schema": "memory_policy_candidate_pool_v1",
        "selection_rule": "first passing candidates in each ordered group; no target statistics",
        "prior_exposure": ["2026-01-01T00"],
        "groups": [
            {"name": "train", "role": "initial_train", "required": 1,
             "candidates": rows("2026-02-01", [0, 1])},
            {"name": "dev", "role": "dev", "required": 8,
             "candidates": rows("2026-02-02", range(8))},
            {"name": "final-a", "role": "final", "required": 10,
             "candidates": rows("2026-02-03", range(12))},
            {"name": "final-b", "role": "final", "required": 10,
             "candidates": rows("2026-02-04", range(12))},
        ],
    }


def report(row, complete=True):
    value = {
        "complete": complete, "session": row["session"], "role": row["role"],
        "advertised_bytes": row["compressed_bytes"],
        "transport": {"complete": complete,
                      "compressed_bytes_read": row["compressed_bytes"],
                      "decoded_records": 2},
        "semantic_receipt": {
            "selected_observations": 2 if complete else 0,
            "entities": 1 if complete else 0,
            "last_attempted_record": 2,
            "message_selection_kernel": "CacheProfile.consume",
            "summary_or_cache_called": False,
        },
        "raw_rows_exported": 0, "target_statistics_computed": 0,
        "fits": 0, "provider_calls": 0,
    }
    if not complete:
        value["consumer_failure"] = {"reason": "source_semantics"}
    return value


class CandidateSourceAdmissionTests(unittest.TestCase):
    def test_stratified_first_pass_selection(self):
        groups = validate_plan(plan())
        results = {row["session"]: report(row)
                   for group in groups for row in group["candidates"]}
        first_final = groups[2]["candidates"][0]
        results[first_final["session"]] = report(first_final, False)
        selected, rejected = select(groups, results)
        self.assertEqual(len(selected["initial_train"]), 1)
        self.assertEqual(len(selected["dev"]), 8)
        self.assertEqual(len(selected["final"]), 20)
        self.assertEqual(selected["final"][0]["session"],
                         groups[2]["candidates"][1]["session"])
        self.assertEqual(len(rejected), 1)

    def test_exposed_duplicate_and_bad_order_are_rejected(self):
        value = plan()
        value["groups"][0]["candidates"][0]["session"] = value["prior_exposure"][0]
        with self.assertRaises(ValueError):
            validate_plan(value)
        value = plan()
        value["groups"][0]["candidates"].reverse()
        with self.assertRaises(ValueError):
            validate_plan(value)

    def test_too_few_passing_in_one_stratum_stops(self):
        groups = validate_plan(plan())
        results = {row["session"]: report(row)
                   for group in groups for row in group["candidates"]}
        for row in groups[3]["candidates"][:3]:
            results[row["session"]] = report(row, False)
        with self.assertRaises(ValueError):
            select(groups, results)

    def test_source_or_plan_mutation_stops(self):
        with self.assertRaises(ValueError):
            require_unchanged({"not": "current"}, __file__, "a" * 64)


if __name__ == "__main__":
    unittest.main()
