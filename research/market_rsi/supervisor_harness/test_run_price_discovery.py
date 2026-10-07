"""The same formal entry, with explicitly synthetic account/worker fixtures."""
from copy import deepcopy
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import Mock, patch

from supervisor_harness import run_price_discovery as entry
from supervisor_harness import test_price_loop_services as fixtures
from supervisor_harness import test_price_loop_handoff as handoff_fixtures
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch as RealBatch

REAL_CHECK_OUTPUT = entry.r.t.c.subprocess.check_output
REAL_POPEN = entry.r.w.subprocess.Popen


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

    def execute(self, *, preflight=False, real_auxiliary=False):
        def child(*args, **kwargs):
            if real_auxiliary and '--output' not in args[0]:
                return REAL_POPEN(*args, **kwargs)
            return self.f.child(*args, **kwargs)
        with patch.object(entry.r, "ContinuousDiscoveryBatch", side_effect=self.f.h.batch), \
                patch.object(entry.r.w, "datetime", handoff_fixtures.Clock), \
                patch.object(entry.r.w, "sample_rss", return_value=128), \
                patch.object(entry.r.w.subprocess, "Popen", side_effect=child) as children:
            result = entry.run(self.config_binding, self.seed_binding, preflight_only=preflight)
        count = sum('--output' in call.args[0] for call in children.call_args_list) if real_auxiliary else children.call_count
        return result, count

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

    def test_typed_two_round_entry_consumes_real_hooks_and_keeps_native_pair_on_replay(self):
        """Account/worker remain synthetic; hooks and typed original replay are real."""
        from supervisor_harness import price_capacity_loop as capacity
        from supervisor_harness import research_capacity_identity as identity
        from supervisor_harness import research_capacity_activation as activation
        repo, runtime = self.f.h.repo, self.f.runtime
        grant = deepcopy(runtime.fixed_grant)
        grant['account_transfer']['max_input_bytes'] = 262144
        grant['account_roles'] = {'capacity_changes_approved': True, 'max_input_bytes': 262144}
        runtime.authority = self.f.h.f.write('authorization', grant); runtime.fixed_grant = grant
        ledger = entry.r.t._file(runtime.root / 'ledger.json')
        ledger['authorization_sha256'] = runtime.authority['sha256']; entry.r.t._ledger(runtime.root / 'ledger.json', ledger)
        names = {'K': 'synthetic-kernel.py', 'C': 'synthetic-predictor.py',
                 'R': 'synthetic-researcher.py', 'H': 'synthetic-harness.py'}
        hook = "def apply(context):\n    return {'previous_decision': context.get('feedback', {}).get('decision', 'unscored')}\n"
        for axis, name in names.items():
            (repo / name).write_text(hook if axis in {'R', 'H'} else '# inert identity source\n')
        bindings = {axis: {'sources': {name: entry.r.w.sha(repo / name)}, 'configuration_sha256': 'f' * 64}
                    for axis, name in names.items()}
        python = entry.r.pin('/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12')
        before = identity.manifest(kernel=bindings['K'], predictor=bindings['C'], researcher=bindings['R'],
            harness=bindings['H'], memory='e' * 64, runtime={'python': python, 'dependencies': {}},
            model={'requested_model': entry.r.t.c.MODEL, 'serving_snapshot': 'unknown', 'serving_snapshot_verified': False})
        config = self.f.base['identity_configuration']
        config['pair'] = activation.pair(before)
        config['fixed_context'].update(authority_sha256=runtime.authority['sha256'], model_sha256=before['M'])
        self.f.base['python_binding'] = python
        binding = self.f.h.f.write('capacity-configuration', {'schema': 'price_capacity_loop_configuration_v1',
            'baseline': before, 'entrypoints': {axis: names[axis] for axis in ('H', 'R')},
            'replay_cases': {name: {} for name in capacity.trial.CASES}, 'hook_seconds': 2})
        self.service.capacity = capacity.PriceCapacityLoop(self.service, binding, Mock(), Mock())
        ordinary_response, ordinary_review = self.f.response, self.f.reviewer
        def response(packet):
            old = ordinary_response(packet)
            return {key: old[key] for key in ('input_sha256', 'feedback_sha256', 'requested_model',
                'serving_snapshot', 'candidate', 'attribution')} | {'schema': 'controller_coevolution_action_v2',
                'action': 'prediction', 'capacity': None, 'authority_request': None}
        def review(stage, material):
            bound = ordinary_review(stage, material)
            if stage != 'input': return bound
            value = entry.r.t.c._read(bound); packet = entry.r.t.c._read(material['input'])
            value.update(action_context_sha256=entry.r.t.c._digest(packet['action_context']),
                         decision_schema_sha256=entry.r.t.c._digest(entry.r.t.SCHEMA_V2))
            return self.f.h.f.write('typed-entry-review-' + str(len(self.f.reviews)), value)
        self.f.h.f.response = response; self.service.reviewer = review
        self.service.callbacks['reviewer'] = entry.r.pin(__file__)
        self.service.base = self.f.base
        result, workers = self.execute(real_auxiliary=True)
        self.assertTrue(result['complete']); self.assertEqual(workers, 2)
        self.assertEqual(len(self.f.choice_packets), 2)
        second = self.f.choice_packets[1]
        self.assertEqual(second['feedback']['decision'], 'REVERT')
        proof = second['source_context']['capacity_hook_outputs']
        self.assertEqual(proof['actual_invocations']['R']['output']['previous_decision'], 'REVERT')
        self.assertEqual(proof['selected_pair'], second['action_context']['identity_configuration']['pair'])
        native = next(runtime.root.glob('price-native-r0002-*/batch.json'))
        self.assertEqual(entry.r.t._file(native)['micro_evolution']['active_pair'], proof['selected_pair'])
        calls = self.f.h.f.calls
        again, workers = self.execute(real_auxiliary=True)
        self.assertTrue(again['complete']); self.assertEqual(workers, 0)
        self.assertEqual(calls, self.f.h.f.calls)

    def test_preflight_only_has_no_original_calls_workers_or_reservations(self):
        before = entry.r.w.sha(self.f.root / "ledger.json")
        calls = self.f.h.f.calls
        result, children = self.execute(preflight=True)
        self.assertEqual(result["status"], "PREFLIGHT_ONLY_NOT_REAL_CLOSURE")
        self.assertEqual(children, 0)
        self.assertEqual(self.f.h.f.calls, calls)
        self.assertEqual(entry.r.w.sha(self.f.root / "ledger.json"), before)

    def test_official_entry_accepts_larger_bound_context_without_scientific_calls(self):
        grant = deepcopy(self.f.runtime.fixed_grant)
        grant['account_transfer']['max_input_bytes'] = 262144
        self.f.runtime.authority = self.f.h.f.write('authorization', grant)
        self.f.runtime.fixed_grant = grant
        self.config['base_spec']['identity_configuration']['fixed_context']['authority_sha256'] = self.f.runtime.authority['sha256']
        self.f.seed['source_context'] = self.f.h.f.write('larger-entry-context', {'synthetic': 'x' * 40000})
        self.seed_binding = self.f.h.f.write('larger-entry-seed', self.f.seed)
        result, children = self.execute(preflight=True)
        self.assertGreater(result['input_bytes'], 32768)
        self.assertEqual(result['authorized_input_bytes'], 262144)
        self.assertEqual(children, 0)
        self.assertEqual(self.f.h.f.calls, self.f.calls_before)
        self.assertEqual(result['scientific_reservations'], 0)
        self.assertEqual(result['model_calls'], 0)

    def test_full_rendered_prompt_not_only_packet_is_checked_before_backend(self):
        packet = self.service.prepare_packet({'round_index': 1, 'previous_result': self.f.seed})
        from supervisor_harness import price_account_roles as roles
        rendered = len(roles._prompt(packet, controller=True).encode('utf-8'))
        # Packet-construction denial is covered separately. Isolate the wire
        # check here without making the earlier guard share a mocked ceiling.
        with patch.object(self.service, 'prepare_packet', return_value=packet), \
                patch.object(entry.r.t, 'input_limit', return_value=rendered - 1):
            with self.assertRaisesRegex(ValueError, 'before account preflight'):
                self.execute(preflight=True)
        self.assertEqual(self.account.preflight.call_count, 0)
        self.assertEqual(self.f.h.f.calls, self.f.calls_before)
        self.assertEqual(entry.r.t._file(self.f.root / 'ledger.json')['attempts'], [])

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

    def test_actual_opt_in_capacity_services_construct_without_role_call(self):
        from supervisor_harness import price_account_roles as roles
        from supervisor_harness import price_candidate_author as author
        from supervisor_harness import price_independent_review as reviewer
        from supervisor_harness import price_capacity_services as capacity_author
        from supervisor_harness import price_capacity_loop as capacity_loop
        from supervisor_harness.test_price_capacity_loop import HookTests
        self.build.stop()
        fixture = HookTests(); self.addCleanup(fixture.doCleanups)
        with patch.object(entry.r.t.c.subprocess, 'check_output', REAL_CHECK_OUTPUT), \
                patch.object(capacity_loop.native, 'ContinuousDiscoveryBatch', RealBatch):
            fixture.setUp()
        original = fixture.f.f.f
        root, repo = fixture.f.runtime.root, fixture.f.runtime.repo
        grant = deepcopy(fixture.f.runtime.fixed_grant)
        grant['account_roles'] = {'approved': True, 'capacity_changes_approved': True,
            'destination': roles.DESTINATION, 'requested_model': entry.r.t.c.MODEL,
            'serving_snapshot': 'unknown', 'max_input_bytes': 262144, 'max_call_seconds': 120,
            'caps': {key: 2 for key in roles.ROLES}, 'raw_train_transfer': False,
            'tools_enabled': False, 'automatic_retry': False}
        authority = original.h.write('authorization', grant)
        ledger = entry.r.t._file(root / 'ledger.json')
        ledger['authorization_sha256'] = authority['sha256']; entry.r.t._ledger(root / 'ledger.json', ledger)
        base = deepcopy(self.config['base_spec'])
        base['identity_configuration'] = deepcopy(fixture.service.base['identity_configuration'])
        base['identity_configuration']['fixed_context'].update(authority_sha256=authority['sha256'],
            evaluation_sha256=base['plan_binding']['sha256'])
        base['python_binding'] = fixture.hooks.config['baseline']['runtime']['python']
        config = {**self.config, 'schema': 'price_discovery_launch_v2', 'repo': str(repo), 'root': str(root),
            'authorization': authority, 'role_authorization': authority,
            'configuration': original.h.configuration_binding, 'base_spec': base,
            'source_files': {'fixed.py': entry.r.w.sha(original.fixed)},
            'capacity_configuration': fixture.hooks.binding,
            'service_sources': {key: entry.r.pin(module.__file__) for key, module in
                (('author', author), ('reviewer', reviewer), ('roles', roles), ('entry', entry),
                 ('capacity_author', capacity_author), ('capacity_loop', capacity_loop))}}
        launch = original.h.write('capacity-entry', config)
        with patch.object(entry.r.t, 'ROOT', root.parent / 'old-fixture'), \
                patch.object(roles, 'native_transport', side_effect=AssertionError('no role call')):
            _, actual, account = entry.build(launch)
        self.assertIsInstance(actual.capacity, capacity_loop.PriceCapacityLoop)
        self.assertIsInstance(actual.capacity.author, capacity_author.CapacityAuthor)
        self.assertIsInstance(actual.capacity.reviewer, reviewer.IndependentPriceReviewer)
        self.assertIn('capacity_service', actual.identity()['controller'])
        self.assertTrue((root / 'price-capacity-native' / 'batch.json').exists())

    def test_native_controller_accepts_capacity_feedback_evidence_without_dummy_candidate(self):
        from supervisor_harness import price_account_roles as roles
        runtime = object.__new__(entry.PricePilotRuntime)
        runtime.root, runtime.repo = self.f.root, self.f.h.repo
        runtime.authority, runtime.configuration = self.f.runtime.authority, self.f.runtime.configuration
        packet = self.service.prepare_packet({'round_index': 1, 'previous_result': self.f.seed})
        binding = self.f.h.f.write('typed-controller-input', packet)
        response = {'candidate': None, 'capacity': {'evidence_used': [
            {'sha256': packet['bindings']['feedback']['sha256']}]}}
        prepared = {'input': binding, 'authorization': runtime.authority,
            'configuration': runtime.configuration, 'review': self.f.callback_binding}
        with patch.object(roles, 'AccountRoles'), patch.object(entry.r.t, 'call', return_value=response), \
                patch.object(entry.r, 'pin', return_value=self.f.callback_binding):
            returned = runtime.controller({'outputs': {'input': prepared}})
        self.assertEqual(returned['decision'], response)

    def test_certain_prefix_rejects_unreviewed_or_wrong_schema_before_replay(self):
        binding = self.f.h.f.write("unreviewed-prefix", {"schema": "not-a-grant"})
        with self.assertRaisesRegex(ValueError, "exact certain-prefix"):
            entry.completed_prefix(self.f.runtime, binding)

    def test_completed_round2_restoration_is_context_bound_not_a_role_retry(self):
        live = entry.LivePriceServices(self.f.runtime, self.f.base, author=self.f.author,
            reviewer=self.f.reviewer, callback_sources={key: self.f.callback_binding
                                                     for key in ("author", "reviewer")})
        live.recovery_binding = self.f.h.f.write("round2-recovery-pin", {"synthetic": True})
        live.recovery_directory = "price-loop-admission-v3"
        (self.f.root / live.recovery_directory).mkdir()
        context = {"round_index": 2, "seed": self.f.seed, "previous_result": self.f.seed,
                   "previous_feedback_sha256": entry.r.t.c._digest(self.f.seed), "outputs": {}}
        saved = {"context_sha256": entry.r.t.c._digest(context), "output": {"known_original": True}}
        live.restored_stages = {(2, "input"): saved}
        reviews = len(self.f.reviews)
        self.assertEqual(live.handlers()["input"](context), saved["output"])
        self.assertEqual(len(self.f.reviews), reviews)
        bad = deepcopy(context)
        bad["previous_feedback_sha256"] = "f" * 64
        live.recovery_directory = "price-loop-admission-v3-drift-fixture"
        (self.f.root / live.recovery_directory).mkdir()
        with self.assertRaisesRegex(ValueError, "restoration context"):
            live.handlers()["input"](bad)
        live.recovery_directory = "price-loop-admission-v3"
        live.recovered_seed_sha256 = entry.r.t.c._digest(self.f.seed)
        def inspect_admission(root, handlers, *, admit, **kwargs):
            self.assertEqual(root.name, "price-loop-admission-v3")
            self.assertTrue(admit({**context, "stage": "input"}))
            self.assertFalse(admit({**context, "stage": "execute"}))
            return {"status": "synthetic-inspection-only"}
        with patch.object(live.runtime, "admit", return_value=False), \
                patch.object(entry.s.loop, "run", side_effect=inspect_admission):
            live.run(self.f.seed, max_rounds=2)

    def test_round2_prefix_rejects_wrong_schema_before_any_replay(self):
        binding = self.f.h.f.write("round2-wrong-schema", {"schema": "not-a-grant"})
        with self.assertRaisesRegex(ValueError, "exact completed round2"):
            entry.completed_round2_prefix(self.f.runtime, binding)


if __name__ == "__main__":
    main()
