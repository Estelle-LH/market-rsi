"""Standalone offline entrypoint tests: synthetic code, mocked I/O, no network.

Only the reviewed entrypoint itself is loaded from disk. Worker source bytes,
plans, canary receipts, native decoder, locks, outputs and execution are mocked.
"""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import runpy
import socket
import stat
import sys
import types
import unittest
from unittest.mock import Mock, patch


SOURCE = Path(__file__).with_name("vantage_stage_entrypoint.py")
SOURCE_STAT = SOURCE.lstat()
if not stat.S_ISREG(SOURCE_STAT.st_mode) or getattr(SOURCE_STAT, "st_flags", 0) & 0x40000000:
    raise RuntimeError("entrypoint must be resident and regular before test import")
SCOPE = runpy.run_path(str(SOURCE))
ENTRY = SCOPE["run"]
ROOT = Path("/opt/market-rsi-historical-20260910-01")
WORKER_NAMES = {
    "pinned_archive_prefix", "canary_activity_observations",
    "canary_sqlite_observations", "guarded_sqlite_decode", "pinned_vantage_download",
}


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


class StageEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.sources = {name: b"raise AssertionError('verify only; do not execute')\n"
                        for name in SCOPE["CODE_FILES"]}
        self.sources.update({
            "pinned_archive_prefix.py": b"ORIGIN = 'fresh-prefix'\n",
            "canary_activity_observations.py": b"ORIGIN = 'fresh-activity'\n",
            "canary_sqlite_observations.py":
                b"from canary_activity_observations import ORIGIN\n",
            "guarded_sqlite_decode.py":
                b"import canary_sqlite_observations\nfrom _stage_test_hooks import decode\n",
            "pinned_vantage_download.py":
                b"import pinned_archive_prefix\nfrom _stage_test_hooks import download\n",
        })
        self.decoder_bytes = b"synthetic native decoder bytes; never executed"
        self.plan = {
            "prior_cumulative_bytes": 5_008_615_369, "cap_bytes": 15_000_000_000,
            "decoded_upper_bound_bytes": 39_315_099_648,
            "decode_reserve_bytes": 5_637_144_576,
            "code_hashes": {name: sha(raw) for name, raw in self.sources.items()},
            "decoder_sha256": sha(self.decoder_bytes), "decoder_version": "synthetic zstd version",
        }
        self.canary = {
            "passed": True, "decoder_sha256": self.plan["decoder_sha256"],
            "decoder_version": self.plan["decoder_version"],
            "code_sha256": {name: self.plan["code_hashes"][name] for name in SCOPE["CANARY_FILES"]},
        }
        self.download = Mock(return_value={"passed": True, "synthetic": True})
        self.decode = Mock(return_value={"decoded_bytes": 39_315_099_648, "synthetic": True})
        self.writes = []
        self.verified_paths = []
        self.output_error = None

    def frozen(self, path, expected):
        if path == ROOT / "plan.json":
            raw = encode(self.plan)
        elif path == ROOT / "canary/result.json":
            raw = encode(self.canary)
        elif path.parent == ROOT / "code":
            raw = self.sources[path.name]
        else:
            raise AssertionError("unexpected file read: " + str(path))
        if sha(raw) != expected:
            raise ValueError("input SHA mismatch")
        self.verified_paths.append(path)
        return raw

    def write_once(self, path, value):
        if self.output_error and path.name == "execution-claim.json":
            raise self.output_error
        self.writes.append((path.name, value))

    def invoke(self, *, preloaded=None):
        # Bind even a malformed/stale canary's exact receipt hash: these tests
        # exercise semantic composition, not an intentionally broken file hash.
        self.plan["canary_result_sha256"] = sha(encode(self.canary))
        expected_plan_sha = sha(encode(self.plan))
        hooks = types.ModuleType("_stage_test_hooks")
        hooks.download, hooks.decode = self.download, self.decode
        before_path = list(sys.path)
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, {"_stage_test_hooks": hooks}))
            for name in WORKER_NAMES:
                sys.modules.pop(name, None)
            if preloaded:
                sys.modules[preloaded] = types.ModuleType(preloaded)
            stack.enter_context(patch.dict(ENTRY.__globals__, {
                "frozen_bytes": self.frozen, "write_once": self.write_once,
            }))
            read_bytes = stack.enter_context(patch.object(Path, "read_bytes", return_value=self.decoder_bytes))
            stack.enter_context(patch.object(Path, "stat", return_value=types.SimpleNamespace(st_size=3_164_694_656)))
            stack.enter_context(patch.object(SCOPE["os"], "open", return_value=999))
            stack.enter_context(patch.object(SCOPE["os"], "fstat", return_value=types.SimpleNamespace(
                st_mode=stat.S_IFREG | 0o600, st_nlink=1)))
            stack.enter_context(patch.object(SCOPE["os"], "close"))
            stack.enter_context(patch.object(SCOPE["fcntl"], "flock"))
            stack.enter_context(patch.object(socket, "socket", side_effect=AssertionError("network prohibited")))
            stack.enter_context(patch.object(socket, "create_connection", side_effect=AssertionError("network prohibited")))
            try:
                ENTRY(ROOT / "plan.json", expected_plan_sha)
            finally:
                self.assertEqual(sys.path, before_path, "must not add a source-search directory")
                self.assertLessEqual(read_bytes.call_count, 1, "worker modules must execute hashed bytes, not reread paths")
        return expected_plan_sha

    def assert_rejected_before_acquisition(self, message, **kwargs):
        with self.assertRaisesRegex(ValueError, message):
            self.invoke(**kwargs)
        self.download.assert_not_called()
        self.decode.assert_not_called()
        self.assertEqual(self.writes, [])

    def test_empty_manifest_rejects_before_acquisition(self):
        self.plan["code_hashes"] = {}
        self.assert_rejected_before_acquisition("complete exact import closure")

    def test_missing_or_extra_module_manifest_rejects(self):
        correct = dict(self.plan["code_hashes"])
        for mode in ("missing", "extra"):
            with self.subTest(mode=mode):
                self.plan["code_hashes"] = dict(correct)
                if mode == "missing":
                    del self.plan["code_hashes"]["pinned_archive_prefix.py"]
                else:
                    self.plan["code_hashes"]["unreviewed.py"] = "0" * 64
                self.assert_rejected_before_acquisition("complete exact import closure")

    def test_non_boolean_or_false_canary_passed_rejects(self):
        for passed in ("false", "true", 1, 0, False, None, [], {}):
            with self.subTest(passed=passed):
                self.canary["passed"] = passed
                self.assert_rejected_before_acquisition("canary did not pass")

    def test_stale_canary_decoder_or_version_rejects(self):
        for field in ("decoder_sha256", "decoder_version"):
            with self.subTest(field=field):
                original = self.canary[field]
                self.canary[field] = "wrong"
                self.assert_rejected_before_acquisition("not bound")
                self.canary[field] = original

    def test_each_stale_canary_source_hash_rejects(self):
        for name in sorted(SCOPE["CANARY_FILES"]):
            with self.subTest(name=name):
                original = self.canary["code_sha256"][name]
                self.canary["code_sha256"][name] = "0" * 64
                self.assert_rejected_before_acquisition("not bound")
                self.canary["code_sha256"][name] = original

    def test_missing_or_extra_canary_source_binding_rejects(self):
        correct = dict(self.canary["code_sha256"])
        for mode in ("missing", "extra"):
            with self.subTest(mode=mode):
                self.canary["code_sha256"] = dict(correct)
                if mode == "missing":
                    del self.canary["code_sha256"]["remote_decode_canary.py"]
                else:
                    self.canary["code_sha256"]["unreviewed.py"] = "0" * 64
                self.assert_rejected_before_acquisition("not bound")

    def test_changed_worker_bytes_reject_before_compilation(self):
        self.sources["pinned_vantage_download.py"] += b"raise AssertionError('changed source executed')\n"
        self.assert_rejected_before_acquisition("input SHA mismatch")

    def test_previously_imported_worker_rejects(self):
        self.assert_rejected_before_acquisition("previously loaded", preloaded="pinned_archive_prefix")

    def test_correct_canary_manifest_and_fresh_bytes_handoff(self):
        expected_plan_sha = self.invoke()
        self.assertEqual(set(self.verified_paths), {ROOT / "plan.json", ROOT / "canary/result.json"} |
                         {ROOT / "code" / name for name in SCOPE["CODE_FILES"]})
        self.download.assert_called_once_with(ROOT / "acquisition", plan_sha256=expected_plan_sha,
                                               prior_cumulative_bytes=5_008_615_369, max_seconds=1800)
        archive = ROOT / "acquisition/polymarket-recorder-tape-vantage-b-20260603-20260701.db.zst"
        self.decode.assert_called_once_with(
            archive, ROOT / "decode",
            expected_sha256="9915c881cd5a598b831652664a1b761629c2c9303997332c9beef2af835d64a4",
            expected_bytes=3_164_694_656, decoder=Path("/usr/bin/zstd"),
            expected_decoder_sha256=self.plan["decoder_sha256"],
            decoded_upper_bound_bytes=39_315_099_648, reserve_bytes=5_637_144_576, max_seconds=1800)
        self.assertEqual([name for name, _ in self.writes],
                         ["execution-claim.json", "decode-stage-start.json", "result.json"])
        result = self.writes[-1][1]
        self.assertTrue(result["passed"])
        for name in ("fresh_validation_admitted", "clean_data_proven", "automatic_retry"):
            self.assertFalse(result[name])
        self.assertEqual(result["paid_model_calls"], 0)
        self.assertTrue(result["primary_pending"])

    def test_consumed_execution_claim_prevents_download(self):
        self.output_error = FileExistsError("already claimed")
        with self.assertRaises(FileExistsError):
            self.invoke()
        self.download.assert_not_called()
        self.decode.assert_not_called()

    def test_download_failure_never_decodes_or_publishes_success(self):
        self.download.side_effect = TimeoutError("synthetic timeout")
        with self.assertRaises(TimeoutError):
            self.invoke()
        self.decode.assert_not_called()
        self.assertEqual([name for name, _ in self.writes], ["execution-claim.json", "failure.json"])
        self.assertTrue(self.writes[-1][1]["reconciliation_required"])
        self.assertFalse(self.writes[-1][1]["automatic_retry"])

    def test_wrong_decoded_size_is_failure_not_staging_success(self):
        self.decode.return_value = {"decoded_bytes": 1}
        with self.assertRaisesRegex(ValueError, "decoded byte count"):
            self.invoke()
        self.assertEqual([name for name, _ in self.writes],
                         ["execution-claim.json", "decode-stage-start.json", "failure.json"])


if __name__ == "__main__":
    unittest.main()
