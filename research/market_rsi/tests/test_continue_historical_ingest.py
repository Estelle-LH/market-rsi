import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from continue_historical_ingest import wait_for_controller


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "session").mkdir()
        (self.root / "runner-process.json").write_text(json.dumps({"pid": 99999}))

    def tearDown(self):
        self.temp.cleanup()

    def test_dead_controller_cannot_launch_download(self):
        with patch("continue_historical_ingest.os.kill", side_effect=ProcessLookupError):
            with self.assertRaisesRegex(ValueError, "without an assessment"):
                wait_for_controller(self.root)

    def test_finished_controller_still_requires_validated_manifest(self):
        (self.root / "session" / "assessment.json").write_text("{}")
        with patch("continue_historical_ingest.read_controller_plan", side_effect=ValueError("invalid")):
            with self.assertRaisesRegex(ValueError, "invalid"):
                wait_for_controller(self.root)

    def test_valid_plan_returned_without_new_controller(self):
        (self.root / "session" / "assessment.json").write_text("{}")
        with patch("continue_historical_ingest.read_controller_plan", return_value={"fixture": True}), \
                patch("continue_historical_ingest.os.kill") as alive:
            self.assertEqual(wait_for_controller(self.root), {"fixture": True})
            alive.assert_not_called()


if __name__ == "__main__":
    unittest.main()
