"""Consumer dependency and snapshot tests; no market rows or paid calls."""
import builtins
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from data_scientist_harness import fixtures, profiles
from data_scientist_harness.core_dependency import CORE_FILES, REVISION, ROOT, dependency_identity
from data_scientist_harness.store import Store
from market_rsi import file_hash, load_json


class CoreAdoptionTests(unittest.TestCase):
    def test_cpu_controller_does_not_import_sandbox_executor(self):
        program = (
            "import sys; sys.path.insert(0,sys.argv[1]); "
            "from data_scientist_harness import run_controller; "
            "assert 'controller_execution_service' not in sys.modules; "
            "assert not any(n=='harbor' or n.startswith('harbor.') for n in sys.modules)"
        )
        done = subprocess.run([sys.executable, "-c", program, str(ROOT)], cwd="/private/tmp",
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True, text=True, timeout=20)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_formal_executor_dependency_fails_before_provider_construction(self):
        from data_scientist_harness.run_controller import harness
        original = builtins.__import__
        def importing(name, *args, **kwargs):
            if name == "controller_execution_service":
                raise ModuleNotFoundError("fixture unavailable executor")
            return original(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=importing), \
             patch.object(harness, "TinkerGLMBackend") as backend:
            with self.assertRaisesRegex(ModuleNotFoundError, "fixture unavailable"):
                harness.main(SimpleNamespace(controller_stage="model", tool_mode="formal"))
            backend.assert_not_called()

    def test_exact_pin_and_function_origin(self):
        identity = dependency_identity()
        self.assertEqual(identity["revision"], REVISION)
        self.assertEqual(identity["feature_batch_adapter_adopted"],"explicit_grid_adapter")
        self.assertEqual(profiles.moments.__module__, "ds_harness_core.moments")
        for name, sha in CORE_FILES.items():
            self.assertEqual(file_hash(ROOT / "ds_harness_core" / name), sha)

    def test_empty_missing_constant_and_float32_contract(self):
        for values in (np.array([], dtype=np.float32), np.full(3, np.nan)):
            self.assertEqual(profiles.moments(values),
                {"rows": len(values), "finite": 0, "missing": len(values), "constant": None})
        values = np.array([.1, .2, .4], dtype=np.float32)
        values.flags.writeable = False
        result = profiles.moments(values)
        self.assertEqual(result["mean"], float(np.mean(values)))
        self.assertEqual(result["std"], float(np.std(values, ddof=0)))
        self.assertEqual(result["mean"], 0.23333334922790527)
        self.assertEqual(profiles.moments(np.ones(4))["std"], 0.)

    def test_invalid_inputs_fail_without_fallback(self):
        for values in (np.array([np.inf]), np.array([1e308, -1e308]),
                       np.ma.array([1., 2.], mask=[False, True]), np.ones((2, 2))):
            with self.subTest(values=type(values)), self.assertRaises(ValueError):
                profiles.moments(values)

    def test_no_adjacent_pairs_preserve_empty_difference(self):
        result = profiles.shape(np.array([1., 2.]), np.array([0, 2000], dtype=np.int64),
                                np.array([0, 0]), np.array(["d", "d"]), 1000)
        self.assertEqual(result["first_difference"], {"rows": 0, "finite": 0, "missing": 0, "constant": None})

    def test_new_snapshot_binds_dependency_and_runs_without_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "run"
            manifest = fixtures.workspace(root)
            config = load_json(root / "workspace.json")
            self.assertEqual(config["runtime"]["shared_core"], dependency_identity())
            for name, sha in CORE_FILES.items():
                self.assertEqual(config["files"][str(root / "code/ds_harness_core" / name)], sha)
            program = (
                "import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
                "from data_scientist_harness.core_dependency import dependency_identity; "
                "from data_scientist_harness import profiles; import numpy as np; "
                "assert profiles.moments(np.array([1.,3.]))['mean']==2.; "
                "snapshot=Path(sys.argv[1]).resolve(); "
                "assert Path(profiles.__file__).resolve().is_relative_to(snapshot); "
                "assert Path(sys.modules['data_scientist_harness.core_dependency'].__file__).resolve().is_relative_to(snapshot); "
                "print(dependency_identity()['revision'])"
            )
            done = subprocess.run([sys.executable, "-c", program, str(root / "code")], cwd=tmp,
                env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
                capture_output=True, text=True, timeout=20)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stdout.strip(), REVISION)
            Store(root, manifest)

    def test_snapshot_dependency_mutation_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "run"
            manifest = fixtures.workspace(root)
            with (root / "code/ds_harness_core/moments.py").open("a") as stream:
                stream.write("\n# deliberate fixture corruption\n")
            with self.assertRaisesRegex(ValueError, "frozen data/code"):
                Store(root, manifest)

    def test_shadow_package_rejected_before_executing_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            package = root / "ds_harness_core"
            package.mkdir()
            (package / "__init__.py").write_text("raise RuntimeError('must not execute')\n")
            program = (
                "import sys; sys.path[:0]=sys.argv[1:]; "
                "from data_scientist_harness.core_dependency import load_moments; "
                "load_moments()"
            )
            done = subprocess.run([sys.executable, "-c", program, str(root), str(ROOT)], cwd=tmp,
                env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
                capture_output=True, text=True, timeout=20)
            self.assertNotEqual(done.returncode, 0)
            self.assertIn("import resolves outside", done.stderr)
            self.assertNotIn("must not execute", done.stderr)


if __name__ == "__main__":
    unittest.main()
