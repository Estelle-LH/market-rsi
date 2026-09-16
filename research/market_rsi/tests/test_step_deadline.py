from datetime import datetime, timedelta, timezone
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from step_deadline import PROFILE, StepDeadline


class StepDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_immutable_nonrenewable_deadline_record(self):
        deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        value = StepDeadline.start(self.root / "deadline.json",
            study_deadline_utc=deadline, cap_seconds=300)
        record = json.loads((self.root / "deadline.json").read_text())
        self.assertEqual(record["profile"], PROFILE)
        self.assertFalse(record["renewable"])
        self.assertEqual(record["externally_active_stages"], ["research", "coding", "sandbox"])
        self.assertGreater(value.require(1, "research"), 299)
        with self.assertRaises(FileExistsError):
            StepDeadline.start(self.root / "deadline.json",
                study_deadline_utc=deadline, cap_seconds=300)

    def test_full_step_must_fit_study_window(self):
        deadline = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
        with self.assertRaisesRegex(TimeoutError, "complete step"):
            StepDeadline.start(self.root / "deadline.json",
                study_deadline_utc=deadline, cap_seconds=60)

    def test_later_stages_do_not_receive_a_new_clock(self):
        deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        value = StepDeadline.start(self.root / "deadline.json",
            study_deadline_utc=deadline, cap_seconds=60)
        with patch("step_deadline.time.monotonic", return_value=value.deadline_monotonic - 2):
            with self.assertRaisesRegex(TimeoutError, "sandbox"):
                value.require(3, "sandbox")


if __name__ == "__main__":
    unittest.main()
