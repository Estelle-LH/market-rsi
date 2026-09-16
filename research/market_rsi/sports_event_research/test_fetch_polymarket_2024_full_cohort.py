import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sports_event_research import fetch_polymarket_2024_full_cohort as cohort


def selections(count):
    return [{"nflverse_game_id": f"g{index:03}",
             "event_id": str(index), "condition_id": f"c{index}"}
            for index in range(count)]


class FullCohortTests(unittest.TestCase):
    def test_data_fetch_import_does_not_load_ml_stack(self):
        program = ("import sys; import sports_event_research.fetch_polymarket_2024_full_cohort; "
                   "assert not any(name == 'numpy' or name.startswith('numpy.') or "
                   "name == 'sklearn' or name.startswith('sklearn.') "
                   "for name in sys.modules)")
        result = subprocess.run([sys.executable, "-c", program],
                                env=dict(os.environ), capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_batches_cover_every_game_without_selection(self):
        rows = selections(49)
        with patch.object(cohort, "BATCH_SIZE", 24):
            groups = [cohort.batch_slice(rows, index) for index in range(3)]
            self.assertEqual([len(group) for group in groups], [24, 24, 1])
            self.assertEqual([row for group in groups for row in group], rows)
            with self.assertRaises(ValueError):
                cohort.batch_slice(rows, 3)

    def test_freeze_then_fetch_exact_batch_without_real_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = selections(3)
            proof = {"tag": "dsh-v1.6.16", "file_sha256": "receipt"}

            def fake_fetch(selection, _mapping, output, _timeout):
                output.mkdir(parents=True)
                (output / "manifest.json").write_text("{}\n")
                return {"frozen_window": {"trades": 1}}

            with (patch.object(cohort, "EXPECTED_GAMES", 3),
                  patch.object(cohort, "BATCH_SIZE", 2),
                  patch.object(cohort, "frozen_selections", return_value=rows),
                  patch.object(cohort, "verify_release", return_value=proof),
                  patch.object(cohort, "fetch_selected", side_effect=fake_fetch)):
                cohort.freeze(root / "mapping.csv", root / "release.json", root / "plan")
                result = cohort.fetch_batch(root / "mapping.csv",
                    root / "plan/cohort_plan.json", root / "release.json", 1,
                    root / "batch", pause_seconds=0)
                self.assertEqual(result["planned_games"], 1)
                self.assertEqual(result["completed_games"], 1)
                self.assertEqual(result["receipts"][0]["game_id"], "g002")
                self.assertFalse(result["train_admitted"])
                self.assertFalse(result["sealed_final_opened"])
                with self.assertRaisesRegex(ValueError, "exists"):
                    cohort.fetch_batch(root / "mapping.csv",
                        root / "plan/cohort_plan.json", root / "release.json", 1,
                        root / "batch", pause_seconds=0)

    def test_plan_mutation_rejected_before_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = selections(2)
            proof = {"tag": "dsh-v1.6.16", "file_sha256": "receipt"}
            with (patch.object(cohort, "EXPECTED_GAMES", 2),
                  patch.object(cohort, "BATCH_SIZE", 2),
                  patch.object(cohort, "frozen_selections", return_value=rows),
                  patch.object(cohort, "verify_release", return_value=proof)):
                cohort.freeze(root / "mapping.csv", root / "release.json", root / "plan")
                path = root / "plan/cohort_plan.json"
                plan = json.loads(path.read_text())
                plan["selections"].pop()
                path.write_text(json.dumps(plan))
                with self.assertRaisesRegex(ValueError, "immutable"):
                    cohort.fetch_batch(root / "mapping.csv", path,
                        root / "release.json", 0, root / "not_created")
                self.assertFalse((root / "not_created").exists())

    def test_exact_old_plan_survives_startup_only_release_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = selections(2)
            old_proof = {"tag": "dsh-v1.6.15", "file_sha256": "old"}
            new_proof = {"tag": "dsh-v1.6.16", "file_sha256": "new"}

            def fake_fetch(selection, _mapping, output, _timeout):
                output.mkdir(parents=True)
                (output / "manifest.json").write_text("{}\n")
                return {"frozen_window": {"trades": 0}}

            with (patch.object(cohort, "EXPECTED_GAMES", 2),
                  patch.object(cohort, "BATCH_SIZE", 2),
                  patch.object(cohort, "frozen_selections", return_value=rows),
                  patch.object(cohort, "verify_release", return_value=old_proof)):
                cohort.freeze(root / "mapping.csv", root / "release.json", root / "plan")
            plan_path = root / "plan/cohort_plan.json"
            with (patch.object(cohort, "EXPECTED_GAMES", 2),
                  patch.object(cohort, "BATCH_SIZE", 2),
                  patch.object(cohort, "EXPECTED_V15_COHORT_PLAN", cohort.sha256(plan_path)),
                  patch.object(cohort, "frozen_selections", return_value=rows),
                  patch.object(cohort, "verify_release", return_value=new_proof),
                  patch.object(cohort, "fetch_selected", side_effect=fake_fetch)):
                result = cohort.fetch_batch(root / "mapping.csv", plan_path,
                    root / "new_release.json", 0, root / "batch", pause_seconds=0)
                self.assertEqual(result["completed_games"], 2)
                lock = json.loads((root / "batch/pre_fetch_lock.json").read_text())
                self.assertEqual(lock["release"], new_proof)
                self.assertEqual(lock["cohort_plan_sha256"], cohort.sha256(plan_path))


if __name__ == "__main__":
    unittest.main()
