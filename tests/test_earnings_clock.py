"""Synthetic clock/boot probes only; no keys, ledger or host sysctl."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import earnings_clock as clock

BOOT = "11111111-1111-1111-1111-111111111111"


class ClockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / "loop"
        self.config = {"source_commit": "a" * 40, "new_request_cutoff_utc": "2099-01-01T00:00:00Z",
                       "deadline_utc": "2099-01-01T00:30:00Z"}
        self.wall = clock.utc_epoch(self.config["new_request_cutoff_utc"]) - 1
        self.mono = 100.0
        for p in (patch.object(clock, "boot_id", return_value=BOOT),
                  patch.object(clock.time, "time", side_effect=lambda: self.wall),
                  patch.object(clock.time, "monotonic", side_effect=lambda: self.mono)):
            p.start()
            self.addCleanup(p.stop)

    def test_capture_and_rollback_resume_keep_exact_original_window_and_files(self):
        value, bound = clock.capture_or_load(self.root, self.config)
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.assertEqual((value["cutoff_monotonic"], value["deadline_monotonic"]), (101, 1901))
        self.wall -= 3600
        self.mono += 2
        self.assertEqual(clock.capture_or_load(self.root, self.config), (value, bound))
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        self.assertGreater(self.mono, value["cutoff_monotonic"])

    def test_delayed_sample_does_not_add_time_authority(self):
        def delayed_wall():
            sampled = self.wall
            self.wall += 2
            self.mono += 2
            return sampled
        with patch.object(clock.time, "time", side_effect=delayed_wall):
            value, _ = clock.capture_or_load(self.root, self.config)
        self.assertLessEqual(value["cutoff_monotonic"], 101)
        self.assertGreaterEqual(self.mono, value["cutoff_monotonic"])

    def test_new_source_inherits_original_clock_without_creating_or_extending_it(self):
        original, bound = clock.capture_or_load(self.root, self.config)
        before = Path(bound["path"]).read_bytes()
        child = dict(self.config, source_commit="b" * 40,
            inherited_clock={"binding": bound, "source_commit": "a" * 40})
        self.wall -= 3600
        self.mono += 2
        new_root = self.root.parent / "new-reviewed-loop"
        self.assertEqual(clock.capture_or_load(new_root, child), (original, bound))
        self.assertFalse(new_root.exists())
        self.assertEqual(before, Path(bound["path"]).read_bytes())
        with self.assertRaises(ValueError):
            clock.capture_or_load(new_root, dict(child, inherited_clock=dict(child["inherited_clock"], source_commit="c" * 40)))
        with self.assertRaises(ValueError):
            clock.capture_or_load(new_root, dict(child, inherited_clock={}))

    def test_unknown_boot_or_reboot_refuses_without_replacing_origin(self):
        value, bound = clock.capture_or_load(self.root, self.config)
        before = Path(bound["path"]).read_bytes()
        with patch.object(clock, "boot_id", return_value="other-boot"):
            with self.assertRaises(ValueError):
                clock.capture_or_load(self.root, self.config)
        with patch.object(clock, "boot_id", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                clock.capture_or_load(self.root, self.config)
        self.assertEqual(before, Path(bound["path"]).read_bytes())

    def test_clock_schema_mapping_source_nonfinite_and_reversed_mono_refuse(self):
        value, _ = clock.capture_or_load(self.root, self.config)
        for field, replacement in (("source_commit", "b" * 40), ("cutoff_monotonic", 102),
                ("wall_origin", True), ("monotonic_origin", float("nan")), ("deadline_utc", "other")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                clock.validate(dict(value, **{field: replacement}), self.config, BOOT)
        self.mono = 99
        with self.assertRaises(ValueError):
            clock.validate(value, self.config, BOOT)

    def test_mutated_incomplete_symlink_or_missing_original_clock_refuses(self):
        with self.assertRaises(ValueError):
            clock.capture_or_load(self.root, self.config, create=False)
        self.assertFalse(self.root.exists())
        _, bound = clock.capture_or_load(self.root, self.config)
        path = Path(bound["path"])
        original = path.read_bytes()
        path.write_text("{}")
        with self.assertRaises(ValueError):
            clock.capture_or_load(self.root, self.config)
        path.write_bytes(original)
        path.rename(path.with_name("saved.json"))
        with self.assertRaises(ValueError):
            clock.capture_or_load(self.root, self.config)
        path.symlink_to(path.with_name("saved.json"))
        with self.assertRaises(ValueError):
            clock.capture_or_load(self.root, self.config)
        other = self.root.parent / "old-loop"
        other.mkdir()
        (other / "stage.json").write_text("{}")
        with self.assertRaises(ValueError):
            clock.capture_or_load(other, self.config)


if __name__ == "__main__":
    unittest.main()
