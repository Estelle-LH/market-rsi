"""Fail nested fixture setup before any account, worker or filesystem work."""
import importlib
import sys
import unittest
from unittest import mock

from tools import check


class NestedFixtureCleanupTests(unittest.TestCase):
    def assert_failed_setup_is_cleaned(self, parent_module, parent_class,
                                      child_module, child_class, entry="setUp"):
        # Existing fixture modules use project-local imports. Keep that path
        # change scoped to this test, independent of the caller's cwd.
        with mock.patch.object(sys, "path", [str(check.PROJECT_ROOT), *sys.path]):
            parent_type = getattr(importlib.import_module("supervisor_harness." + parent_module), parent_class)
            child_type = getattr(importlib.import_module("supervisor_harness." + child_module), child_class)
            roles = importlib.import_module("supervisor_harness.price_account_roles")
            original = roles._recover
            patches = []

            def failing_setup(child):
                patch = mock.patch.object(roles, "_recover", new=object())
                patch.start()
                patches.append(patch)
                child.addCleanup(patch.stop)
                raise RuntimeError("synthetic child setup failure")

            parent = parent_type()
            try:
                with mock.patch.object(child_type, "setUp", failing_setup):
                    with self.assertRaisesRegex(RuntimeError, "synthetic child setup failure"):
                        getattr(parent, entry)()
                parent.doCleanups()
                self.assertEqual(len(patches), 1)
                self.assertIs(roles._recover, original, "child patch survived parent cleanup")
            finally:
                # A red regression must not itself leak the mock to other tests.
                parent.doCleanups()
                for patch in reversed(patches):
                    patch.stop()

    def test_child_setup_failure_does_not_leak_across_parent_fixtures(self):
        cases = (
            ("test_run_price_discovery", "EntryTests", "test_price_loop_services", "PriceServiceTests"),
            ("test_price_loop_services", "PriceServiceTests", "test_price_loop_handoff", "HandoffTests"),
            ("test_price_loop_handoff", "HandoffTests", "test_coevo_pilot_configuration", "ConfigurationTests"),
            ("test_price_independent_review", "IndependentReviewTests", "test_price_loop_services", "PriceServiceTests"),
            ("test_price_capacity_services", "CapacityAuthorTests", "test_coevo_pilot_transaction", "TypedActionTests"),
            ("test_price_capacity_review", "CapacityReviewTests", "test_price_capacity_services", "CapacityAuthorTests"),
            ("test_price_capacity_trial", "TrialTests", "test_price_capacity_review", "CapacityReviewTests"),
            ("test_price_capacity_loop", "HookTests", "test_price_capacity_trial", "TrialTests"),
        )
        for case in cases:
            with self.subTest(parent=case[1], child=case[3]):
                self.assert_failed_setup_is_cleaned(*case)

    def test_child_setup_failure_inside_test_methods_also_cleans(self):
        for entry in (
            "test_typed_original_author_consumes_actual_hook_context_without_legacy_rewrap",
            "test_typed_author_rejects_substituted_input_before_account_call",
        ):
            with self.subTest(entry=entry):
                self.assert_failed_setup_is_cleaned(
                    "test_price_candidate_author", "AuthorServiceTests",
                    "test_coevo_pilot_transaction", "TypedActionTests", entry,
                )


if __name__ == "__main__":
    unittest.main()
