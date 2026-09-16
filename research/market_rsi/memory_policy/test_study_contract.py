from pathlib import Path
import tempfile
import unittest

from market_rsi import file_hash, fresh_json, load_json
from memory_pilot.learning import BASE
from memory_pilot.test_learning import fixture_cache
from memory_policy.study import ARMS, heldout_gate, workspace


class StudyContractTests(unittest.TestCase):
    def test_workspace_changes_only_memory_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "data"
            data.mkdir()
            train = [fixture_cache(data, "2026-01-01"), fixture_cache(data, "2026-01-02")]
            history = [{"round": 1, "records": [], "submission": {"trial_id": "baseline"},
                        "own_dev": {"candidate_mse": 1.0},
                        "common_baseline_dev": {"candidate_mse": 1.0},
                        "cost": {"metered_usd": "0"}}]
            configs = {}
            for arm in ("fresh", "archive", "compact"):
                directory = root / arm
                workspace(directory, train, {"success": True}, history, 2, arm, 8,
                          {"market_rsi.py": file_hash(Path(__file__).resolve().parents[1] / "market_rsi.py")},
                          fixture=True)
                configs[arm] = load_json(directory / "config.json")
            self.assertEqual(configs["fresh"]["archive"], [])
            self.assertEqual(configs["archive"]["archive"], history)
            self.assertEqual(configs["compact"]["archive"]["schema"],
                             "controller_compact_archive_v1")
            for key in ("train", "baseline", "source_hashes"):
                self.assertEqual(configs["fresh"][key], configs["archive"][key])
                self.assertEqual(configs["fresh"][key], configs["compact"][key])

    def test_heldout_needs_all_three_submissions_and_four_models(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            commitments = []
            for arm in ("fresh", "archive", "compact"):
                path = root / (arm + ".json")
                fresh_json(path, {"arm": arm})
                commitments.append({"path": str(path), "sha256": file_hash(path)})
            commitments.sort(key=lambda item: item["path"])
            (root / "round-1").mkdir()
            fresh_json(root / "round-1/paired-freeze.json", {
                "commitments": commitments, "models": {arm: arm for arm in ARMS},
            })
            spec = {"dev": [{"session": "2026-01-01T00", "compressed_bytes": 1}],
                    "final": [], "rounds": 1}
            heldout_gate(root, "2026-01-01T00", "dev", commitments, spec)
            with self.assertRaises(ValueError):
                heldout_gate(root, "2026-01-01T00", "dev", commitments[:2], spec)


if __name__ == "__main__":
    unittest.main()
