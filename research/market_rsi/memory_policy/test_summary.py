import unittest

from market_rsi import digest
from memory_policy.summary import compact_archive, memory_payload, payload_size


def record(index, tool, args, result=None, error=None):
    value = dict(index=index, tool=tool, args=args, result=result, error=error,
                 previous_sha256=None, unix_ns=1)
    value["sha256"] = digest(value)
    return value


class SummaryTests(unittest.TestCase):
    def history(self):
        rows = [
            record(0, "read_public_source", {"url": "https://example.test", "offset": 0},
                   {"text": "large untrusted page"}),
            record(1, "record_research", {"note": "Ridge may stabilize this feature family."},
                   {"research_record": "0001"}),
            record(2, "train_candidate", dict(trial_id="ridge", parent_trial_id="baseline",
                   plan_json="{}", research_record="0001", question="Does ridge help?",
                   hypothesis="It reduces check MSE.", support_criterion="MSE lower.",
                   refute_criterion="MSE not lower."),
                   {"trial_id": "ridge", "success": True,
                    "result_sha256": "a" * 64, "result": {"check_mse": 1.0}}),
            record(3, "interpret_result", dict(trial_id="ridge", result_sha256="a" * 64,
                   interpretation="Supported.", next_step="Submit."), {"archived": True}),
        ]
        return [dict(round=1, records=rows,
            submission={"trial_id": "ridge", "plan": {"model": "ridge"}, "reason": "lower MSE"},
            own_dev={"candidate_mse": 1.0}, common_baseline_dev={"candidate_mse": 2.0},
            cost={"metered_usd": "0.25"})]

    def test_compact_is_deterministic_and_keeps_measured_decision(self):
        history = self.history()
        first = compact_archive(history)
        self.assertEqual(first, compact_archive(history))
        self.assertEqual(first["rounds"][0]["submission"]["trial_id"], "ridge")
        self.assertEqual(first["rounds"][0]["candidates"][0]["research_note"],
                         "Ridge may stabilize this feature family.")
        self.assertNotIn("large untrusted page", str(first))
        self.assertEqual(first["rounds"][0]["full_round_sha256"], digest(history[0]))

    def test_three_modes_and_compaction(self):
        history = self.history()
        self.assertEqual(memory_payload("fresh", history), [])
        self.assertIs(memory_payload("archive", history), history)
        self.assertLess(payload_size("compact", history), payload_size("archive", history))
        with self.assertRaises(ValueError):
            memory_payload("unknown", history)


if __name__ == "__main__":
    unittest.main()
