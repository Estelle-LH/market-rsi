"""Independent portable adversaries, not admission or live28 evidence.

RoleFixture explicitly substitutes historical admission, resident selection and
ledger admission. All current byte/path checks below are the actual helper.
Transport tests use original _OwnedHTTP and invented receipts/raw transport; no
provider, original data/ledger, labels, candidate execution or history replay.
"""
from contextlib import ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_capacity_runtime as owner
import earnings_entry as entry
import earnings_population_live_guard as guard
from edgar_forecast_budget import BudgetStop
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from test_earnings_population_role_validation import RoleFixture


class RoleValidationAdversarial(unittest.TestCase):
    def fixture(self):
        f = RoleFixture()
        self.addCleanup(f.close)
        stack = ExitStack()
        self.addCleanup(stack.close)
        for mocked in f.patches():
            stack.enter_context(mocked)
        return f

    def receipt(self, f, role='controller', arm=0):
        name = Path(f.value['slots'][role][arm]).name
        return entry.strict_json((f.root/'role-validation'/(name+'.json')).read_bytes())

    def mutate(self, path):
        """Same inode/length/restored times: a metadata cache must not suffice."""
        path = Path(path)
        before = path.stat()
        raw = path.read_bytes()
        self.assertTrue(raw)
        path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(path.stat().st_size, before.st_size)
        self.assertEqual(path.stat().st_mtime_ns, before.st_mtime_ns)

    def test_policy_amendment_and_placement_are_strict(self):
        f = self.fixture()
        self.assertTrue(guard.enabled(f.value))
        self.assertFalse(guard.enabled({'schema': 'legacy'}))
        cases = [None, {}, {'path': 1, 'sha256': 'a'*64},
                 {'path': '/invented', 'sha256': True},
                 {'path': '/invented', 'sha256': 'A'*64},
                 {'path': '/invented', 'sha256': 'a'*63},
                 {'path': '/invented', 'sha256': 'a'*64, 'extra': True}]
        for amendment in cases:
            with self.subTest(amendment=amendment), self.assertRaises(ValueError):
                guard.enabled(dict(f.value, budget_amendment=amendment))
        for schema in ('earnings_capacity_runtime_v1', None, True):
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                guard.enabled(dict(f.value, schema=schema))

    def test_all_current_bindings_rehash_same_size_restored_mtime(self):
        # QA here is an invented opaque byte string, never a real label read.
        for target in ('runtime', 'study', 'population', 'plan', 'review', 'packet',
                       'feedback', 'R', 'H', 'filing', 'SCORER', 'qa', 'FULL_PLAN',
                       'METADATA', 'MANIFEST', 'RUNTIME', 'forecaster'):
            with self.subTest(target=target):
                f = self.fixture()
                targets = dict(runtime=f.binding, study=f.value['forecast_study'],
                    population=f.value['initial_population'], plan=f.value['population_plan'],
                    review=f.value['review'], packet=engine.pin(f.root/'packet-01.json'),
                    feedback=f.feedback, **f.source, **f.metadata)
                def callback(*args):
                    f.manager.register_case(f.case(args[-1]))
                    f.manager.check(args[-1])
                    self.mutate(targets[target]['path'])
                    f.manager.check(args[-1])
                with self.assertRaises((ValueError, UnicodeError)):
                    f.manager.wrap('controller', callback)(*f.args('controller'))
                self.assertFalse(self.receipt(f)['output_accepted'])
                self.assertIsNone(f.manager.current)

    def test_native_source_copies_and_initial_state_are_fresh(self):
        for name in ('researcher_v0.py', 'harness_v0.py', 'evaluation_scorer.py',
                     'evaluation_qa.json', 'predictor.py', 'initial_state', 'context'):
            with self.subTest(name=name):
                f = self.fixture()
                def callback(*args):
                    case = f.case(args[-1])
                    f.manager.register_case(case)
                    f.manager.check(args[-1])
                    path = (case['initial_state']['path'] if name == 'initial_state'
                        else case['context']['path'] if name == 'context'
                        else f.native/Path(args[-1]).name/'source'/name)
                    self.mutate(path)
                    return 'must not be accepted'
                with self.assertRaises((ValueError, UnicodeError)):
                    f.manager.wrap('controller', callback)(*f.args('controller'))
                self.assertFalse(self.receipt(f)['output_accepted'])

    def test_native_registration_is_independent_not_self_consistent_substitution(self):
        for field in ('pool_version', 'authority', 'source_commit', 'company',
                      'runtime', 'kernel', 'case', 'data', 'manifest', 'initial_state'):
            with self.subTest(field=field):
                f = self.fixture()
                def callback(*args):
                    case = f.case(args[-1])
                    context = entry.strict_json(entry.checked(case['context']))
                    context[field] = {'substituted': True}
                    # Make the host-side declared case equally wrong where it
                    # overlaps: the independent selected resident must still win.
                    if field in case and field != 'manifest':
                        case[field] = deepcopy(context[field])
                    case['context'] = f.save('bad-context.json', context)
                    exact = f.native/Path(args[-1]).name/'context.json'
                    exact.write_bytes(Path(case['context']['path']).read_bytes())
                    case['context'] = engine.pin(exact)
                    f.manager.register_case(case)
                with self.assertRaises(ValueError):
                    f.manager.wrap('controller', callback)(*f.args('controller'))
                self.assertFalse(self.receipt(f)['output_accepted'])

    def test_current_packet_and_active_parent_selection_are_exact(self):
        for role in ('controller', 'author', 'review', 'forecast'):
            with self.subTest(role=role):
                f = self.fixture()
                args = list(f.args(role))
                if role == 'controller': args[0]['feedback'] = {'invented': True}
                elif role == 'author': args[1]['explorers'] = ['f'*64]
                elif role == 'review': args[0]['parent'] = 'f'*64
                else: args[1] = 'CIK0000004457'
                called = []
                with self.assertRaises(ValueError):
                    f.manager.wrap(role, lambda *a: called.append(a))(*args)
                self.assertEqual(called, [])

    def test_stale_author_feedback_and_forecast_frozen_source_cannot_enter(self):
        for mode in ('feedback', 'frozen', 'version_id'):
            with self.subTest(mode=mode):
                f = self.fixture()
                role = 'author' if mode == 'feedback' else 'forecast'
                args = list(f.args(role))
                if mode == 'feedback': args[0]['feedback_sha256'] = '0'*64
                elif mode == 'frozen': args[0]['extra'] = 'not exact frozen version'
                else: args[0]['id'] = '0'*64
                with self.assertRaises((ValueError, KeyError)):
                    f.manager.wrap(role, lambda *a: self.fail('callback entered'))(*args)

    def test_heldout_and_not_admitted_dev_company_refused_before_resident(self):
        for company in ('CIK0000021076', 'CIK0000003545'):
            with self.subTest(company=company):
                f = self.fixture()
                packet = dict(f.packet, company_id=company)
                f.save('packet-01.json', packet)
                with patch.object(guard.tasks, 'resident', side_effect=AssertionError('must not open')):
                    with self.assertRaises(ValueError):
                        f.manager.wrap('controller', lambda *a: None)(packet, f.args('controller')[-1])

    def test_each_forecast_arm_boundary_and_context_must_be_separate(self):
        f = self.fixture()
        for arm in range(3):
            args = f.args('forecast', arm)
            def callback(*actual):
                f.manager.register_case(f.case(actual[-1]))
                f.manager.check(actual[-1])
                wrong = f.value['slots']['forecast'][(arm+1) % 3]
                with self.assertRaises(ValueError): f.manager.check(wrong)
                return {'arm': arm}
            self.assertEqual(f.manager.wrap('forecast', callback)(*args), {'arm': arm})
            receipt = self.receipt(f, 'forecast', arm)
            self.assertTrue(receipt['output_accepted'])
            self.assertEqual(receipt['slot'], args[-1])
            self.assertEqual(receipt['selected_version_id'], f.version['id'])
        self.assertEqual(len(f.full_calls), 6)

    def test_reference_context_and_first_author_context_remain_hash_bound(self):
        for role in ('controller', 'author'):
            with self.subTest(role=role):
                f = self.fixture()
                reference = f.native/'controller-01-reference-context.json'
                reference.write_text('{"fixture":"original"}')
                def callback(*args):
                    f.manager.register_case(f.case(args[-1]))
                    actual = reference
                    if role == 'author':
                        actual = f.native/'author-01-context.json'
                        actual.write_text('{"fixture":"original"}')
                    f.manager.check(args[-1])
                    self.mutate(actual)
                    f.manager.check(args[-1])
                with self.assertRaises(ValueError):
                    f.manager.wrap(role, callback)(*f.args(role))
                self.assertFalse(self.receipt(f, role)['output_accepted'])

    def test_same_bytes_symlink_alias_is_not_fresh_canonical_source(self):
        f = self.fixture()
        def callback(*args):
            f.manager.register_case(f.case(args[-1])); f.manager.check(args[-1])
            source = Path(f.source['H']['path'])
            target = source.with_name('same-bytes-alias-target')
            target.write_bytes(source.read_bytes())
            source.unlink(); source.symlink_to(target)
            f.manager.check(args[-1])
        with self.assertRaises(ValueError):
            f.manager.wrap('controller', callback)(*f.args('controller'))
        self.assertFalse(self.receipt(f)['output_accepted'])

    def test_archived_semantic_tamper_is_deferred_but_exit_blocks_return(self):
        f = self.fixture()
        archive = f.raw('archived-not-in-fast-list.bin', b'old closed history')
        calls = []
        def full():
            calls.append('full')
            owner._read(archive)
            return deepcopy(f.value)
        f.manager.full_check = full
        def callback(*args):
            f.manager.register_case(f.case(args[-1]))
            self.mutate(archive['path'])
            f.manager.check(args[-1])  # Honest policy: no complete archive replay here.
            self.assertEqual(calls, ['full'])
            return 'never adopted'
        with self.assertRaises(ValueError):
            f.manager.wrap('controller', callback)(*f.args('controller'))
        self.assertEqual(calls, ['full', 'full'])
        receipt = self.receipt(f)
        self.assertFalse(receipt['output_accepted'])
        self.assertEqual(receipt['exit_full_audit'], 'FAILED')
        self.assertIn('not per-HTTP', receipt['archive_semantics'])

    def test_full_entry_failure_never_executes_role_or_auto_retries(self):
        f = self.fixture()
        calls = []
        def reject(): calls.append('audit'); raise BudgetStop('fixture closed')
        f.manager.full_check = reject
        with self.assertRaises(BudgetStop):
            f.manager.wrap('controller', lambda *a: calls.append('role'))(*f.args('controller'))
        self.assertEqual(calls, ['audit'])
        self.assertFalse((f.root/'role-validation').exists())

    def test_original_baseexception_survives_exit_audit_and_receipt_failure(self):
        f = self.fixture()
        original = KeyboardInterrupt('original opaque fixture')
        liability = {'reserved': 177, 'status': 'reserved'}
        calls = []
        def full():
            calls.append('full')
            if len(calls) > 1: raise BudgetStop('secondary audit')
            return deepcopy(f.value)
        f.manager.full_check = full
        def callback(*args): raise original
        with patch.object(entry, 'durable_json', side_effect=OSError('secondary receipt')):
            with self.assertRaises(KeyboardInterrupt) as caught:
                f.manager.wrap('controller', callback)(*f.args('controller'))
        self.assertIs(caught.exception, original)
        self.assertEqual(liability, {'reserved': 177, 'status': 'reserved'})
        self.assertEqual(calls, ['full', 'full'])
        self.assertIsNone(f.manager.current)

    def test_owner_exit_guard_failure_prevents_acceptance_and_is_recorded(self):
        f = self.fixture()
        calls = []
        def owner_check(slot): calls.append(slot); raise BudgetStop('owner expired')
        f.manager.owner_check = owner_check
        def callback(*args):
            f.manager.register_case(f.case(args[-1])); return 'not accepted'
        with self.assertRaises(BudgetStop):
            f.manager.wrap('controller', callback)(*f.args('controller'))
        self.assertEqual(calls, [f.args('controller')[-1]])
        receipt = self.receipt(f)
        self.assertEqual(receipt['exit_full_audit'], 'PASS')
        self.assertEqual(receipt['exit_current_guard'], 'NOT_PASSED')
        self.assertFalse(receipt['output_accepted'])

    def test_nested_role_and_multiple_registration_are_fail_closed(self):
        for mode in ('nested', 'register_twice', 'kwargs'):
            with self.subTest(mode=mode):
                f = self.fixture()
                def callback(*args):
                    case = f.case(args[-1]); f.manager.register_case(case)
                    if mode == 'nested':
                        f.manager.wrap('forecast', lambda *a: None)(*f.args('forecast'))
                    else: f.manager.register_case(case)
                with self.assertRaises(ValueError):
                    wrapped = f.manager.wrap('controller', callback)
                    if mode == 'kwargs': wrapped(*f.args('controller'), unexpected=True)
                    else: wrapped(*f.args('controller'))
                self.assertIsNone(f.manager.current)

    def test_original_loop_frozen_pool_producer_is_actual_selection_consumer(self):
        """Actual journal+pool producer, actual receiver; stop before scoring.

        No handcrafted frozen filename is supplied to the receiver. This proves
        the interface join only, not Native/live admission or financial results.
        """
        import earnings_population as population
        import earnings_population_loop as loop
        from supervisor_harness import feedback_linked_loop as journal
        f = self.fixture()
        initial = population.initialize(population.version(f.source['R'], f.source['H']),
            {'K': '1'*64, 'M': '2'*64, 'C': '3'*64})
        root = f.root/'actual-loop-producer'
        slot = str(root/'roles/forecast-01-00')
        f.manager.root = root
        f.manager.value['slots']['forecast'] = [slot]
        observed = []
        class JoinedBeforeScoring(Exception): pass
        def controller(packet, output):
            return engine.save(root/'synthetic-controller.json', dict(axis='continue',
                feedback_sha256=digest(packet['feedback']),
                parent_pair_sha256=packet['population']['stable_id'],
                hypothesis='Synthetic join only, no financial assertion.'))
        def unused(*args): self.fail('continue must skip Author/Review')
        def forecast(version, company, output):
            selected = f.manager._selection('forecast', (version, company, output), {})
            observed.append(selected['version'])
            self.assertIn(engine.pin(root/'frozen-pool-01.json'), selected['bindings'])
            raise JoinedBeforeScoring('join verified; no candidate/scorer execution')
        with self.assertRaises(journal.LoopHalted) as stopped:
            loop.run(root, initial, [f.packet['company_id']],
                dict(controller=controller, author=unused, review=unused, forecast=forecast),
                admit=lambda ctx: True, max_rounds=1)
        self.assertIsInstance(stopped.exception.__cause__, JoinedBeforeScoring)
        self.assertEqual(observed, [initial['versions'][initial['stable_id']]])
        self.assertTrue((root/'frozen-pool-01.json').is_file())
        self.assertFalse((root/'frozen-01.json').exists())


class PhysicalTransportAdversarial(unittest.TestCase):
    def setUp(self):
        self.f = RoleFixture(); self.addCleanup(self.f.close)
        self.slot = Path(self.f.value['slots']['controller'][0])
        self.slot.mkdir(parents=True)
        self.rates = {'api_model': 'fixture', 'effort': 'max', 'input': '1',
                      'cached': '0.1', 'write': None, 'output': '2'}
        self.limits = {'max_input_tokens': 32000, 'max_output_tokens': 200}
        self.sent, self.checks = [], []
        test = self
        class Raw(owner.RawOpenAIHTTP):
            def post(self, endpoint, payload):
                test.sent.append((endpoint, deepcopy(payload)))
                return {'fixture': True}
        self.raw = Raw('no credential')
        self.http = owner._OwnedHTTP(self.raw, lambda loan: self.fail('legacy guard used'),
            {str(self.slot): self.limits}, self.rates,
            live_check=lambda loan, slot: self.checks.append((loan, slot)))

    def prepare(self, *, generation=False):
        counted = {'model': 'fixture', 'reasoning': {'effort': 'max'}, 'input': []}
        payload = counted if not generation else dict(counted, max_output_tokens=100,
            service_tier='default', store=False)
        prefix = self.slot/('http-generation-fixture' if generation else 'http-count-fixture')
        intent = {'endpoint': '/v1/responses' if generation else '/v1/responses/input_tokens',
                  'payload': payload}
        if generation:
            record = {'request_id': 'invented-loan', 'reserved_nano_usd': 1000000,
                      'payload': counted}
            request = engine.save(self.slot/'01-request.json', record)
            engine.save(self.slot/'01-count.json', {'input_tokens': 20})
            intent.update(complete_reservation=record, request_receipt_sha256=request['sha256'],
                          budget_request_id=record['request_id'])
        engine.save(prefix.with_suffix('.intent.json'), intent)
        self.raw.record_prefix = prefix
        return intent['endpoint'], payload

    def test_count_and_generation_have_two_current_checks_exact_slot_and_loan(self):
        for generation in (False, True):
            with self.subTest(generation=generation):
                endpoint, payload = self.prepare(generation=generation)
                self.http.post(endpoint, payload)
                expected = ('invented-loan', 'fixture', 1000000) if generation else None
                self.assertEqual(self.checks[-2:], [(expected, self.slot)]*2)
        self.assertEqual(len(self.sent), 2)

    def test_pre_send_guard_failure_dispatches_nothing(self):
        endpoint, payload = self.prepare()
        def reject(loan, slot): raise BudgetStop('current owner denied')
        self.http.live_check = reject
        with self.assertRaises(BudgetStop): self.http.post(endpoint, payload)
        self.assertEqual(self.sent, [])

    def test_post_send_guard_failure_preserves_one_dispatch_and_loan(self):
        endpoint, payload = self.prepare(generation=True)
        def fail_second(loan, slot):
            self.checks.append((loan, slot))
            if len(self.checks) == 2: raise BudgetStop('expired after original response')
        self.http.live_check = fail_second
        with self.assertRaises(BudgetStop): self.http.post(endpoint, payload)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(len(self.checks), 2)
        self.assertEqual(self.checks[0][0], ('invented-loan', 'fixture', 1000000))
        self.assertEqual(entry.strict_json((self.slot/'01-request.json').read_bytes())['reserved_nano_usd'], 1000000)

    def test_payload_model_effort_and_intent_drift_fail_before_any_check_or_send(self):
        for mode in ('payload', 'model', 'effort', 'intent', 'foreign_slot'):
            with self.subTest(mode=mode):
                # Fresh immutable receipts per subcase, no reused delivery ID.
                sub = self.slot/mode; sub.mkdir()
                original_slot = self.slot; self.slot = sub
                self.http.slots = {str(sub): self.limits}
                endpoint, payload = self.prepare()
                if mode == 'payload': payload['input'] = ['drift']
                elif mode == 'model': payload['model'] = 'other'
                elif mode == 'effort': payload['reasoning'] = {'effort': 'high'}
                elif mode == 'intent': self.mutate_intent()
                else: self.http.slots = {str(original_slot): self.limits}
                with self.assertRaises(ValueError): self.http.post(endpoint, payload)
                self.slot = original_slot
        self.assertEqual(self.sent, []); self.assertEqual(self.checks, [])

    def mutate_intent(self):
        path = self.raw.record_prefix.with_suffix('.intent.json')
        value = entry.strict_json(path.read_bytes()); value['endpoint'] = '/not-original'
        path.write_text(json.dumps(value))

    def test_reservation_count_or_payload_drift_is_not_a_new_loan(self):
        for mode in ('count', 'bool_count', 'reservation', 'output', 'store'):
            with self.subTest(mode=mode):
                sub = self.slot/mode; sub.mkdir()
                original_slot = self.slot; self.slot = sub
                self.http.slots = {str(sub): self.limits}
                endpoint, payload = self.prepare(generation=True)
                if mode in ('count', 'bool_count'):
                    (sub/'01-count.json').write_text(json.dumps({'input_tokens': 32001 if mode == 'count' else True}))
                elif mode == 'reservation':
                    value = entry.strict_json((sub/'01-request.json').read_bytes())
                    value['reserved_nano_usd'] += 1
                    (sub/'01-request.json').write_text(json.dumps(value))
                elif mode == 'output': payload['max_output_tokens'] = 201
                else: payload['store'] = True
                with self.assertRaises(ValueError): self.http.post(endpoint, payload)
                self.slot = original_slot
        self.assertEqual(self.sent, []); self.assertEqual(self.checks, [])


class OwnerBoundaryAdversarial(unittest.TestCase):
    """Real original owner/clock/NightBudget; explicit admission/grant seams.

    This isolates that the new live-check routing still reaches old ownership
    and accounting safeguards. Selection is independently exercised above; this
    test does not pretend a fabricated population grant is actually admitted.
    """
    def setUp(self):
        from test_earnings_capacity_runtime import CapacityRuntimeOwnerTests
        self.harness = CapacityRuntimeOwnerTests('runTest')
        self.harness.setUp()
        self.initial_mono = self.harness.mono
        self.addCleanup(self.harness.doCleanups)

    def setup_owner(self, name):
        from earnings_night_budget import NightBudget
        f = self.harness.fixture(name, purpose='controller_protocol')
        f.spec.update(schema='earnings_population_runtime_v1', validation_policy=guard.POLICY,
            budget_amendment={'path': str(f.home/'invented-amendment.json'), 'sha256': 'a'*64})
        f.binding = f.save_spec(lambda value: None)
        # f.save_spec returns fresh bytes of f.spec (including explicit policy).
        selected = []
        class SelectionSeam:
            def __init__(self, binding, value, full_check, *, owner_check):
                self.owner_check = owner_check
            def wrap(self, role, callback): return callback
            def register_case(self, case): pass
            def check(self, slot): selected.append(str(slot))
        class GrantSeam(NightBudget):
            def __init__(self, *args, amendment_binding, **kwargs):
                # Test uses the original synthetic200 NightBudget, not real400.
                super().__init__(*args, **kwargs)
        stack = ExitStack(); self.addCleanup(stack.close)
        stack.enter_context(patch.object(owner, 'preflight_runtime', return_value=deepcopy(f.spec)))
        stack.enter_context(patch.object(guard, 'RoleValidation', SelectionSeam))
        stack.enter_context(patch('earnings_population_budget.PopulationBudget', GrantSeam))
        return f, selected

    def test_opted_in_http_retains_original_clock_claim_context_and_budget_checks(self):
        for target in ('clock', 'claim', 'role_context', 'blocked', 'prefix', 'monotonic'):
            with self.subTest(target=target):
                f, selected = self.setup_owner('role-policy-'+target)
                with self.assertRaises((ValueError, BudgetStop)), f.open() as owned:
                    client = owned['roles']['controller'].__self__.factory()
                    slot = Path(f.slots['controller'][0]); slot.mkdir(parents=True)
                    request = {'model': f.rates['api_model'], 'reasoning': {'effort': f.rates['effort']}}
                    prefix = slot/'http-original-owned-count'
                    engine.save(prefix.with_suffix('.intent.json'),
                        {'endpoint': '/v1/responses/input_tokens', 'payload': request})
                    client.record_prefix = prefix
                    if target in ('clock', 'claim', 'role_context'):
                        path = (Path(owned['clock_binding']['path']) if target == 'clock'
                            else f.claim_path() if target == 'claim'
                            else Path(owned['context_bindings']['controller']['path']))
                        path.write_bytes(b'changed synthetic owned bytes')
                    elif target == 'blocked': owned['budget'].db.execute('UPDATE config SET blocked=1')
                    elif target == 'prefix':
                        owned['budget'].db.execute("UPDATE requests SET charged=1001 WHERE id='fixture-prior'")
                    else: self.harness.mono = owned['window']['cutoff_monotonic'] + 1
                    with f.exchange():
                        client.post('/v1/responses/input_tokens', request)
                self.assertEqual(selected, [str(slot)])
                self.assertEqual(f.calls, [])
                self.assertEqual(len(f.rows()), 1)
                self.assertEqual(f.terminal()['status'], 'FAILED_NO_RETRY')
                self.harness.assert_closed_once(owned['budget'])
                # Restore synthetic clock for the next independent owner.
                self.harness.mono = self.initial_mono

    def test_opted_in_generation_exact_loan_drift_preserves_original_liability(self):
        f, selected = self.setup_owner('role-policy-loan')
        with self.assertRaises(BudgetStop), f.open() as owned:
            client = owned['roles']['controller'].__self__.factory()
            slot = Path(f.slots['controller'][0]); slot.mkdir(parents=True)
            counted = {'model': f.rates['api_model'], 'reasoning': {'effort': f.rates['effort']}}
            record = {'request_id': 'invented-exact-loan', 'reserved_nano_usd': 2000000, 'payload': counted}
            owned['budget'].reserve(record['request_id'], counted['model'], record['reserved_nano_usd'])
            request_bound = engine.save(slot/'01-request.json', record)
            engine.save(slot/'01-count.json', {'input_tokens': 20})
            payload = dict(counted, max_output_tokens=100, service_tier='default', store=False)
            prefix = slot/'http-original-loan'
            engine.save(prefix.with_suffix('.intent.json'), dict(endpoint='/v1/responses', payload=payload,
                complete_reservation=record, request_receipt_sha256=request_bound['sha256'],
                budget_request_id=record['request_id']))
            client.record_prefix = prefix
            owned['budget'].db.execute("UPDATE requests SET reserved=2000001 WHERE id='invented-exact-loan'")
            with f.exchange(): client.post('/v1/responses', payload)
        self.assertEqual(selected, [str(slot)])
        self.assertEqual(f.calls, [])
        self.assertEqual(f.rows()[-1][2:], (2000001, 0, 'reserved'))
        self.assertEqual(f.terminal()['status'], 'FAILED_NO_RETRY')
        self.harness.assert_closed_once(owned['budget'])

    def test_retained_opted_in_client_and_factory_do_not_outlive_original_owner(self):
        f, selected = self.setup_owner('role-policy-owner-closed')
        with f.open() as owned:
            factory = owned['roles']['controller'].__self__.factory
            client = factory()
            slot = Path(f.slots['controller'][0]); slot.mkdir(parents=True)
            request = {'model': f.rates['api_model'], 'reasoning': {'effort': f.rates['effort']}}
            prefix = slot/'http-original-retained-count'
            engine.save(prefix.with_suffix('.intent.json'),
                {'endpoint': '/v1/responses/input_tokens', 'payload': request})
            client.record_prefix = prefix
        with f.exchange(), self.assertRaises(BudgetStop):
            client.post('/v1/responses/input_tokens', request)
        with self.assertRaises(BudgetStop): factory()
        self.assertEqual(selected, [])
        self.assertEqual(f.calls, [])
        self.assertEqual(len(f.rows()), 1)
        self.assertEqual(f.terminal()['status'], 'COMPLETED_COMPONENT_CONTEXT')
        self.harness.assert_closed_once(owned['budget'])


if __name__ == '__main__':
    unittest.main()
