"""Read-only layout/config checks; never import the native live entry."""
import ast
import inspect
import json
from pathlib import Path
import unittest

import market_rsi
from market_rsi import checks


class LayoutTests(unittest.TestCase):
    def test_legacy_api_is_forwarded_without_copying_or_moving_its_source(self):
        from research.market_rsi import market_rsi as legacy

        tree = ast.parse(Path(legacy.__file__).read_text())
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                with self.subTest(name=node.name):
                    self.assertIs(getattr(market_rsi, node.name), getattr(legacy, node.name))
                    self.assertEqual(Path(inspect.getsourcefile(getattr(market_rsi, node.name))),
                                     checks.PROJECT_ROOT / "market_rsi.py")
        self.assertEqual(market_rsi.digest({"a": 1}), legacy.digest({"a": 1}))
        with self.assertRaises(AttributeError):
            getattr(market_rsi, "missing_legacy_helper")

    def test_suite_configuration_is_the_single_selection_source(self):
        configured = json.loads((checks.CHECKOUT_ROOT / "configs" / "checks.json").read_text())
        self.assertEqual(checks.SUITES, {key: tuple(value) for key, value in configured.items()})
        self.assertEqual({key: len(value) for key, value in configured.items()},
                         {"smoke": 5, "price": 24})

    def test_active_task_index_points_to_existing_canonical_sources(self):
        profile = json.loads((checks.CHECKOUT_ROOT / "benchmarks" / "nfl_price" / "profile.json").read_text())
        self.assertEqual(profile["role"], "read_only_source_index_not_launch_configuration")
        for relative in profile["source_paths"].values():
            self.assertFalse(Path(relative).is_absolute())
            self.assertNotIn("..", Path(relative).parts)
            path = checks.CHECKOUT_ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertEqual(path, path.resolve())
        runner = checks.CHECKOUT_ROOT / profile["source_paths"]["runner"]
        constants = {}
        for node in ast.parse(runner.read_text()).body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        constants[target.id] = node.value.value
        self.assertEqual(profile["task_id"], constants["TASK"])
        self.assertEqual(profile["baseline_ids"], [constants["ZERO"], constants["ORDINARY"]])
        self.assertEqual(profile["horizon_seconds"], 300)


if __name__ == "__main__":
    unittest.main()
