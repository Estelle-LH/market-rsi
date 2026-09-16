from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_rsi import fresh_json
from memory_pilot import broker as runtime_base
from memory_policy.broker_v3 import (
    Broker, REFIT_MAX_RSS_GIB, REFIT_TIMEOUT_SECONDS,
    TRIAL_MAX_RSS_GIB, TRIAL_TIMEOUT_SECONDS, refit_worker, trial_worker,
)
import memory_policy.controller as controller


class BrokerV3Tests(unittest.TestCase):
    def test_controller_broker_path_is_configurable(self):
        self.assertTrue(controller.BROKER_SCRIPT.name.endswith("broker.py"))

    def test_import_does_not_mutate_old_worker(self):
        self.assertIsNot(runtime_base.run_worker, trial_worker)

    def test_resource_contract_is_reported_truthfully(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fresh_json(root / "config.json", {
                "fixture": True,
                "source_hashes": {},
                "train": [],
                "baseline": {},
                "archive": [],
                "public_context": {},
            })
            (root / "records").mkdir()
            (root / "trials").mkdir()
            from market_rsi import file_hash
            result = Broker(root, file_hash(root / "config.json")).call(
                "inspect_experiment", {})
            self.assertEqual(result["library"]["max_fit_rss_gib"],
                             TRIAL_MAX_RSS_GIB)
            self.assertEqual(result["library"]["cpu_seconds_per_fit"],
                             TRIAL_TIMEOUT_SECONDS)
            self.assertEqual(result["library"]["mandatory_refit_max_rss_gib"],
                             REFIT_MAX_RSS_GIB)
            self.assertEqual(result["library"]["mandatory_refit_cpu_seconds"],
                             REFIT_TIMEOUT_SECONDS)

    def test_wrappers_bind_distinct_limits(self):
        with patch("memory_policy.broker_v3.run_worker_bounded") as bounded:
            trial_worker({}, Path("trial"))
            self.assertEqual(bounded.call_args.kwargs, {
                "max_rss_gib": TRIAL_MAX_RSS_GIB,
                "timeout_seconds": TRIAL_TIMEOUT_SECONDS,
            })
        with patch("memory_policy.broker_v3.run_worker_bounded") as bounded:
            refit_worker({}, Path("refit"))
            self.assertEqual(bounded.call_args.kwargs, {
                "max_rss_gib": REFIT_MAX_RSS_GIB,
                "timeout_seconds": REFIT_TIMEOUT_SECONDS,
            })


if __name__ == "__main__":
    unittest.main()
