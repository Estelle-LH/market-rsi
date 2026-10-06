"""The same formal entry, with explicitly synthetic account/worker fixtures."""
from copy import deepcopy
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import Mock, patch

from supervisor_harness import run_price_discovery as entry
from supervisor_harness import test_price_loop_services as fixtures
from supervisor_harness import test_price_loop_handoff as handoff_fixtures


class EntryTests(TestCase):
    def setUp(self):
        self.f = fixtures.PriceServiceTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.service = self.f.service()
        self.config = {"schema": "price_discovery_launch_v1", "repo": str(self.f.h.repo),
            "root": str(self.f.root), "authorization": self.f.runtime.authority,
            "configuration": self.f.runtime.configuration, "role_authorization": self.f.runtime.authority,
            "base_spec": self.f.base,
            "source_files": {str(self.f.h.runner.relative_to(self.f.h.repo)): entry.r.w.sha(self.f.h.runner)},
            "service_sources": {}, "max_rounds": 2}
        self.config_binding = self.f.h.f.write("entry-config", self.config)
        self.seed_binding = self.f.h.f.write("entry-seed", self.f.seed)
        self.account = Mock(preflight=Mock(return_value={"operational_ready": True,
                                                       "synthetic_metadata_ack": True}))
        self.build = patch.object(entry, "build", return_value=(self.config, self.service, self.account))
        self.build.start()
        self.addCleanup(self.build.stop)
        def git(command, **kwargs):
            if command[:3] == ["git", "diff", "--cached"]:
                return ""
            if command[:2] == ["git", "show"]:
                relative = command[2].split(":", 1)[1]
                return (self.f.h.repo / relative).read_bytes()
            return "fixture-commit\n"
        mocked = patch.object(entry.r.t.c.subprocess, "check_output", side_effect=git)
        mocked.start()
        self.addCleanup(mocked.stop)

    def execute(self, *, preflight=False):
        with patch.object(entry.r, "ContinuousDiscoveryBatch", side_effect=self.f.h.batch), \
                patch.object(entry.r.w, "datetime", handoff_fixtures.Clock), \
                patch.object(entry.r.w, "sample_rss", return_value=128), \
                patch.object(entry.r.w.subprocess, "Popen", side_effect=self.f.child) as children:
            result = entry.run(self.config_binding, self.seed_binding, preflight_only=preflight)
        return result, children.call_count

    def test_same_entry_two_negative_rounds_feedback_parent_and_cold_replay(self):
        result, children = self.execute()
        self.assertTrue(result["complete"])
        self.assertEqual(children, 2)  # Fabricated predictions/counters, no ML fitting.
        self.assertEqual(result["loop"]["completed_rounds"], 2)
        second = self.f.choice_packets[1]
        self.assertEqual(second["feedback"]["candidate_id"], self.f.authored[0]["candidate_binding"]["path"].split("/")[-1].replace("_", "-")[:-3])
        self.assertEqual(second["feedback"]["decision"], "REVERT")
        self.assertEqual(second["source_context"]["candidate_sha256"],
                         self.f.authored[0]["candidate_binding"]["sha256"])
        calls = self.f.h.f.calls
        again, children = self.execute()
        self.assertTrue(again["complete"])
        self.assertEqual(children, 0)
        self.assertEqual(self.f.h.f.calls, calls)

    def test_same_entry_keep_updates_incumbent_without_erasing_branches(self):
        self.f.first_prediction = .003
        result, children = self.execute()
        self.assertTrue(result["complete"])
        self.assertEqual(children, 2)
        pool = entry.r.t.c._read(result["loop"]["result"]["pool"])
        self.assertNotEqual(pool["incumbent"]["candidate_id"], "B0-NoPriceChange")
        self.assertEqual(len(pool["active_pool"]), 2)
        self.assertEqual(len(pool["archive"]), 4)

    def test_same_entry_failed_worker_returns_feedback_not_scientific_refutation(self):
        self.f.fail_first_child = True
        result, children = self.execute()
        self.assertTrue(result["complete"])
        self.assertEqual(children, 2)
        first = self.f.choice_packets[1]["feedback"]
        self.assertEqual(first["execution_outcome"], "failed")
        self.assertEqual(first["decision"], "UNCHANGED")
        self.assertEqual(first["research_credit"], 0)
        self.assertIsNone(first["comparison"])

    def test_preflight_only_has_no_original_calls_workers_or_reservations(self):
        before = entry.r.w.sha(self.f.root / "ledger.json")
        calls = self.f.h.f.calls
        result, children = self.execute(preflight=True)
        self.assertEqual(result["status"], "PREFLIGHT_ONLY_NOT_REAL_CLOSURE")
        self.assertEqual(children, 0)
        self.assertEqual(self.f.h.f.calls, calls)
        self.assertEqual(entry.r.w.sha(self.f.root / "ledger.json"), before)

    def test_parent_or_native_fixed_identity_drift_precedes_original_call(self):
        original = deepcopy(self.config["base_spec"]["identity_configuration"])
        self.config["base_spec"]["identity_configuration"]["fixed_context"]["evaluation_sha256"] = "e" * 64
        calls = self.f.h.f.calls
        with self.assertRaisesRegex(ValueError, "native initialization"):
            self.execute()
        self.assertEqual(calls, self.f.h.f.calls)
        self.assertEqual(self.account.preflight.call_count, 0)
        self.config["base_spec"]["identity_configuration"] = original
        pool = entry.r.t.c._read(self.f.seed["pool"])
        pool["archive"][1]["native_parent"]["research_credit"] = 0
        self.f.seed["pool"] = self.f.h.f.write("bad-entry-parent", pool)
        self.seed_binding = self.f.h.f.write("bad-entry-seed", self.f.seed)
        with self.assertRaises(ValueError):
            self.execute()
        self.assertEqual(calls, self.f.h.f.calls)

    def test_unverified_runtime_stops_before_original_call(self):
        self.account.preflight.return_value = {"operational_ready": False}
        calls = self.f.h.f.calls
        with self.assertRaisesRegex(ValueError, "runtime text-only"):
            self.execute()
        self.assertEqual(calls, self.f.h.f.calls)

    def test_actual_service_construction_and_exact_fields_before_calls(self):
        from supervisor_harness import price_account_roles as roles
        from supervisor_harness import price_candidate_author as author
        from supervisor_harness import price_independent_review as reviewer
        self.build.stop()  # No production backend is called; only instantiate it.
        grant = entry.r.t.c._read(self.f.runtime.authority)
        grant["account_roles"] = {"approved": True, "destination": roles.DESTINATION,
            "requested_model": entry.r.t.c.MODEL, "serving_snapshot": "unknown",
            "max_input_bytes": 32768, "max_call_seconds": 120,
            "caps": {key: 2 for key in roles.ROLES}, "raw_train_transfer": False,
            "tools_enabled": False, "automatic_retry": False}
        binding = self.f.h.f.write("authorization", grant)
        config = deepcopy(self.config)
        config.update(authorization=binding, role_authorization=binding,
            service_sources={key: entry.r.pin(module.__file__) for key, module in
                (("author", author), ("reviewer", reviewer), ("roles", roles), ("entry", entry))})
        launch = self.f.h.f.write("actual-construction", config)
        with patch.object(entry.r.t, "ROOT", self.f.root.parent / "old-fixture"), \
                patch.object(roles, "native_transport", side_effect=AssertionError("no call")):
            _, actual, account = entry.build(launch)
            self.assertIsInstance(actual, entry.LivePriceServices)
            self.assertIsInstance(account, roles.AccountRoles)
            sources = actual.identity()["controller"]["source_dependencies"]
            self.assertIn(entry.r.pin(entry.__file__), sources)
            self.assertIn(entry.r.pin(roles.__file__), sources)
            config["max_rounds"] = True
            bad = self.f.h.f.write("bad-launch-fields", config)
            with self.assertRaisesRegex(ValueError, "exact two-round"):
                entry.build(bad)

    def test_known_prefix_callbacks_restore_once_into_fresh_timing_namespace(self):
        live = entry.LivePriceServices(self.f.runtime, self.f.base, author=self.f.author,
            reviewer=self.f.reviewer, callback_sources={key: self.f.callback_binding
                                                     for key in ("author", "reviewer")})
        live.recovery_binding = self.f.h.f.write("synthetic-recovery-pin", {"synthetic": True})
        live.completed_prefix = {"input": {"known_completed_original": True}}
        old = self.f.root / "price-loop"
        old.mkdir()
        old_time = self.f.h.f.write("old-timing-proof", {"immutable": True})
        fresh = self.f.root / "price-loop-admission-v2"
        fresh.mkdir()
        context = {"round_index": 1, "seed": self.f.seed, "previous_result": self.f.seed,
                   "previous_feedback_sha256": entry.r.t.c._digest(self.f.seed), "outputs": {}}
        review_count = len(self.f.reviews)
        output = live.handlers()["input"](context)
        self.assertEqual(output, live.completed_prefix["input"])
        self.assertEqual(len(self.f.reviews), review_count)
        self.assertTrue((fresh / "round-0001-input.timing.json").exists())
        self.assertEqual(entry.r.t.c._read(old_time), {"immutable": True})
        context["round_index"] = 2
        output = live.handlers()["input"](context)
        self.assertIn("input", output)  # Normal second-round reviewer is not bypassed.
        self.assertEqual(len(self.f.reviews), review_count + 1)

    def test_certain_prefix_rejects_unreviewed_or_wrong_schema_before_replay(self):
        binding = self.f.h.f.write("unreviewed-prefix", {"schema": "not-a-grant"})
        with self.assertRaisesRegex(ValueError, "exact certain-prefix"):
            entry.completed_prefix(self.f.runtime, binding)


if __name__ == "__main__":
    main()
