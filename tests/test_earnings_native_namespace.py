"""Pure namespace mapping and unchanged Native guard regressions; no inference.

The default-path test does not create the application-support directory or
admit financial data. Activation tests stop at its first attempted directory
write, after the original root guards and before registry/baseline mutation.
"""
from hashlib import sha256
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import earnings_native_namespace as namespace
from supervisor_harness import continuous_discovery_batch as native_batch
from supervisor_harness import research_capacity_activation as activation


EPISODE_ID = "earnings-coevolution-20261013-namespace-fixture"
ORIGINAL_EPISODE_BASE = Path(
    "/Users/estelle/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/"
    "earnings-coevolution-plan-20261013/episodes"
)
DEFAULT_NATIVE_BASE = Path(
    "/Users/estelle/Library/Application Support/MarketRSI/"
    "co-evo-earnings/episodes"
)
PATH_KEYS = {"native_root", "source_root", "registry_root", "batch_root", "probe_root"}


class BeforeRegistryWrite(RuntimeError):
    """Sentinel: the unchanged Activation constructor reached its first write."""


class NativeNamespaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.episode = self.root / ".codex" / "worktrees" / "artifact-records" / EPISODE_ID
        self.runtime = self.root / "native-runtime" / "episodes"

    def paths(self, episode=None):
        with patch.object(namespace, "NATIVE_RUNTIME_ROOT", self.runtime):
            return namespace.native_paths(episode or self.episode, EPISODE_ID)

    def validate(self, candidate, episode=None):
        with patch.object(namespace, "NATIVE_RUNTIME_ROOT", self.runtime):
            return namespace.validate_native_root(episode or self.episode, candidate, EPISODE_ID)

    def test_default_actual_worktree_episode_maps_to_exact_external_paths_without_writes(self):
        episode = ORIGINAL_EPISODE_BASE / EPISODE_ID
        expected = DEFAULT_NATIVE_BASE / EPISODE_ID
        self.assertEqual(namespace.NATIVE_RUNTIME_ROOT, DEFAULT_NATIVE_BASE)
        with patch.object(Path, "mkdir", side_effect=AssertionError("No mkdir in pure mapping")), \
                patch.object(Path, "open", side_effect=AssertionError("No open in pure mapping")), \
                patch.object(Path, "write_bytes", side_effect=AssertionError("No write in pure mapping")), \
                patch.object(Path, "write_text", side_effect=AssertionError("No write in pure mapping")):
            paths = namespace.native_paths(episode, EPISODE_ID)
            self.assertEqual(set(paths), PATH_KEYS)
            self.assertTrue(all(type(path) is type(expected) for path in paths.values()))
            self.assertEqual(paths, {
                "native_root": expected, "source_root": expected / "source",
                "registry_root": expected / "versions", "batch_root": expected / "batch",
                "probe_root": expected / "probe-scratch",
            })
            self.assertEqual(namespace.validate_native_root(episode, expected, EPISODE_ID), expected)
            self.assertEqual(native_batch._safe_root(paths["batch_root"], allow_temporary=False),
                             paths["batch_root"])
        self.assertFalse(expected.is_relative_to(episode))
        self.assertFalse(episode.is_relative_to(expected))

    def test_original_worktree_batch_path_remains_forbidden_with_temporary_allowance(self):
        episode = ORIGINAL_EPISODE_BASE / EPISODE_ID
        for allowance in (False, True):
            with self.subTest(allow_temporary=allowance), \
                    self.assertRaisesRegex(native_batch.DiscoveryBatchError, "worktree"):
                native_batch._safe_root(episode / "native" / "batch", allow_temporary=allowance)

    def test_default_external_registry_passes_original_activation_guards_before_write(self):
        # Default source is prospective and is not claimed to exist. A real
        # owned canonical source directory exercises the unchanged strict guard.
        source = self.root / "owned-source"
        source.mkdir()
        paths = namespace.native_paths(ORIGINAL_EPISODE_BASE / EPISODE_ID, EPISODE_ID)
        with patch.object(Path, "mkdir", side_effect=BeforeRegistryWrite("write boundary")) as mkdir:
            with self.assertRaises(BeforeRegistryWrite):
                activation.CapacityActivation(object(), source_root=source,
                    registry_root=paths["registry_root"], baseline={}, entrypoints={})
        mkdir.assert_called_once_with(parents=True, exist_ok=True, mode=0o700)
        self.assertEqual(list(source.iterdir()), [])

    def test_owned_temporary_mapping_is_exact_and_does_not_create_any_paths(self):
        before = set(self.root.rglob("*"))
        paths = self.paths()
        self.assertEqual(set(paths), PATH_KEYS)
        self.assertEqual(paths["native_root"], self.runtime / EPISODE_ID)
        for key, child in (("source_root", "source"), ("registry_root", "versions"),
                           ("batch_root", "batch"), ("probe_root", "probe-scratch")):
            self.assertEqual(paths[key], paths["native_root"] / child)
        self.assertEqual(self.validate(paths["native_root"]), paths["native_root"])
        self.assertEqual(set(self.root.rglob("*")), before)
        self.assertTrue(all(not path.exists() for path in paths.values()))

    def test_temporary_native_root_still_requires_original_explicit_test_allowance(self):
        path = self.paths()["batch_root"]
        with self.assertRaisesRegex(native_batch.DiscoveryBatchError, "temporary"):
            native_batch._safe_root(path, allow_temporary=False)
        self.assertEqual(native_batch._safe_root(path, allow_temporary=True), path)

    def test_undeclared_and_sibling_native_roots_are_refused_without_creation(self):
        declared = self.paths()["native_root"]
        for candidate in (self.root / "somewhere-else" / EPISODE_ID,
                          declared.parent / (EPISODE_ID + "-different"),
                          declared / "extra", declared.parent):
            with self.subTest(candidate=str(candidate)), self.assertRaises(ValueError):
                self.validate(candidate)
            self.assertFalse(candidate.exists())

    def test_relative_traversing_and_malformed_episode_ids_are_refused(self):
        for candidate in (Path("relative") / EPISODE_ID,
                          self.runtime / ".." / "episodes" / EPISODE_ID):
            with self.subTest(candidate=str(candidate)), self.assertRaises(ValueError):
                self.validate(candidate)
        with patch.object(namespace, "NATIVE_RUNTIME_ROOT", self.runtime):
            for episode_id in ("", ".", "..", "escape/path", "/absolute", "x" * 200):
                with self.subTest(episode_id=episode_id), self.assertRaises(ValueError):
                    namespace.native_paths(self.episode, episode_id)

    def test_native_overlap_with_original_episode_is_refused_in_both_directions(self):
        cases = (
            (self.episode, self.episode.parent),
            (self.episode, self.episode / "native-runtime"),
            (self.root / "native" / EPISODE_ID / EPISODE_ID, self.root / "native"),
        )
        for episode, runtime in cases:
            with self.subTest(episode=str(episode), runtime=str(runtime)), \
                    patch.object(namespace, "NATIVE_RUNTIME_ROOT", runtime), \
                    self.assertRaises(ValueError):
                namespace.native_paths(episode, EPISODE_ID)

    def test_protected_ancestry_is_refused_even_if_configured_as_runtime_root(self):
        for part in (".codex", ".git", ".agents", "worktrees", ".CODEX", "WORKTREES"):
            with self.subTest(part=part), \
                    patch.object(namespace, "NATIVE_RUNTIME_ROOT", self.root / part / "episodes"), \
                    self.assertRaises(ValueError):
                namespace.native_paths(self.episode, EPISODE_ID)

    def test_cloud_ancestry_is_refused_even_if_configured_as_runtime_root(self):
        for part in ("Dropbox", "Google Drive", "iCloud Drive", "Mobile Documents",
                     "OneDrive", "Box", "Dropbox (Personal)", "OneDrive - Personal"):
            with self.subTest(part=part), \
                    patch.object(namespace, "NATIVE_RUNTIME_ROOT", self.root / part / "episodes"), \
                    self.assertRaises(ValueError):
                namespace.native_paths(self.episode, EPISODE_ID)

    def test_configured_runtime_symlink_is_refused_without_following_or_writes(self):
        actual = self.root / "actual-runtime"
        actual.mkdir()
        alias = self.root / "runtime-alias"
        alias.symlink_to(actual, target_is_directory=True)
        with patch.object(namespace, "NATIVE_RUNTIME_ROOT", alias), self.assertRaises(ValueError):
            namespace.native_paths(self.episode, EPISODE_ID)
        self.assertEqual(list(actual.iterdir()), [])
        self.assertTrue(alias.is_symlink())

    def test_late_ancestor_alias_is_detected_again_before_native_use(self):
        self.runtime = self.root / "runtime-parent" / "episodes"
        native = self.paths()["native_root"]
        actual = self.root / "aliased-parent"
        actual.mkdir()
        (self.root / "runtime-parent").symlink_to(actual, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.validate(native)
        self.assertEqual(list(actual.iterdir()), [])

    def test_existing_non_directory_native_ancestor_is_refused_without_modification(self):
        blocker = self.root / "file-ancestor"
        blocker.write_bytes(b"retained fixture bytes")
        with patch.object(namespace, "NATIVE_RUNTIME_ROOT", blocker / "episodes"), \
                self.assertRaises(ValueError):
            namespace.native_paths(self.episode, EPISODE_ID)
        self.assertEqual(blocker.read_bytes(), b"retained fixture bytes")

    def test_original_activation_protected_registry_guard_remains_before_any_write(self):
        source = self.root / "source"
        source.mkdir()
        for part in (".codex", ".git", ".agents"):
            with self.subTest(part=part), \
                    patch.object(Path, "mkdir", side_effect=AssertionError("Forbidden root write")) as mkdir:
                with self.assertRaises(ValueError):
                    activation.CapacityActivation(object(), source_root=source,
                        registry_root=self.root / part / "versions", baseline={}, entrypoints={})
                mkdir.assert_not_called()

    def test_original_activation_source_alias_guard_remains_before_any_write(self):
        source = self.root / "source"
        source.mkdir()
        alias = self.root / "source-alias"
        alias.symlink_to(source, target_is_directory=True)
        with patch.object(Path, "mkdir", side_effect=AssertionError("Aliased source write")) as mkdir:
            with self.assertRaises(ValueError):
                activation.CapacityActivation(object(), source_root=alias,
                    registry_root=self.root / "versions", baseline={}, entrypoints={})
            mkdir.assert_not_called()


class ProbeNamespaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.capacity = SimpleNamespace(registry=self.root / "native" / "versions")
        self.output = self.root / ".codex" / "worktrees" / "records" / EPISODE_ID / "effects" / "probe-01"

    def test_codex_shaped_effect_records_derive_external_exact_hashed_cold_roots(self):
        token = sha256(str(self.output).encode()).hexdigest()
        expected = self.capacity.registry.parent / "probe-scratch" / token
        before = set(self.root.rglob("*"))
        paths = namespace.probe_paths(self.capacity, self.output)
        self.assertEqual(paths, {"native_root": expected, "batch_root": expected / "cold-batch",
                                 "registry_root": expected / "cold-versions"})
        self.assertTrue(all(type(p) is type(expected) for p in paths.values()))
        self.assertFalse(expected.is_relative_to(self.output))
        self.assertEqual(native_batch._safe_root(paths["batch_root"], allow_temporary=True),
                         paths["batch_root"])
        with self.assertRaisesRegex(native_batch.DiscoveryBatchError, "worktree"):
            native_batch._safe_root(self.output / "cold-batch", allow_temporary=True)
        self.assertEqual(set(self.root.rglob("*")), before)

    def test_probe_namespace_is_deterministic_and_different_outputs_remain_disjoint(self):
        first = namespace.probe_paths(self.capacity, self.output)
        self.assertEqual(first, namespace.probe_paths(self.capacity, self.output))
        second = namespace.probe_paths(self.capacity, self.output.parent / "probe-02")
        self.assertNotEqual(first["native_root"], second["native_root"])
        self.assertEqual(first["native_root"].parent, second["native_root"].parent)

    def test_consumed_probe_namespace_is_refused_without_erasing_originals(self):
        root = namespace.probe_paths(self.capacity, self.output)["native_root"]
        root.mkdir(parents=True)
        original = root / "retained.json"
        original.write_bytes(b'{"consumed": true}\n')
        with self.assertRaisesRegex(ValueError, "Consumed"):
            namespace.probe_paths(self.capacity, self.output)
        self.assertEqual(original.read_bytes(), b'{"consumed": true}\n')

    def test_protected_registry_parent_and_cloud_scratch_ancestry_are_refused(self):
        for part in (".codex", ".git", ".agents", "Dropbox", "OneDrive - Personal"):
            capacity = SimpleNamespace(registry=self.root / part / "versions")
            with self.subTest(part=part), self.assertRaises(ValueError):
                namespace.probe_paths(capacity, self.output)
            self.assertFalse((self.root / part).exists())

    def test_noncanonical_output_or_registry_ancestry_is_refused_before_scratch(self):
        for output in (Path("relative-output"), self.output.parent / ".." / "effects" / "probe-01"):
            with self.subTest(output=str(output)), self.assertRaises(ValueError):
                namespace.probe_paths(self.capacity, output)
        actual = self.root / "actual-native"
        actual.mkdir()
        alias = self.root / "native-alias"
        alias.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(ValueError):
            namespace.probe_paths(SimpleNamespace(registry=alias / "versions"), self.output)
        self.assertEqual(list(actual.iterdir()), [])

    def test_late_scratch_parent_alias_is_refused_without_following_it(self):
        paths = namespace.probe_paths(self.capacity, self.output)
        actual = self.root / "actual-scratch"
        actual.mkdir()
        self.capacity.registry.parent.mkdir(parents=True)
        paths["native_root"].parent.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(ValueError):
            namespace.probe_paths(self.capacity, self.output)
        self.assertEqual(list(actual.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
