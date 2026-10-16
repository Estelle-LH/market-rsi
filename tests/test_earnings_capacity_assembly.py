"""Prospective real assembly readiness on owned synthetic financial fixtures.

Only financial-data admission is explicitly substituted by FixtureAdmissionTask.
Its ordinary task methods, source roles, worker, original forecast, scorer,
Native machinery and runtime owner remain real when used by integration tests.
No provider key, actual API ledger or outside Supervisor is accessed.
"""
from contextlib import contextmanager, ExitStack
from copy import deepcopy
from hashlib import sha256
import inspect
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import earnings_assembly_readiness as readiness
import earnings_capacity_assembly as assembly
import earnings_capacity_runtime as runtime
import earnings_capacity_task as task_module
import earnings_clock as clock
import earnings_controller as controller
import earnings_entry as entry
import earnings_native_namespace as namespace
from earnings_capacity_checks import MechanicalProbes
from earnings_effect_review import review as effect_review, SCOPES
from earnings_loop_policy import LIMITS
from earnings_research_state import ResearchState
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_capacity_forecast as raw_fixture


class FixtureAdmissionTask(task_module.EarningsTask):
    """Explicit invented-data admission only; no fabricated execution result."""
    def __init__(self, fixture):
        self.fixture, self.preflight_calls = fixture, []

    def preflight(self, envelope):
        self.preflight_calls.append(deepcopy(envelope))
        if (envelope != self.fixture.envelope
                or envelope['study'] != self.fixture.raw.study_binding
                or envelope['evaluation_kernel'] != self.fixture.raw.kernel):
            raise ValueError('Only this exact invented fixture is admitted')
        engine.read(envelope['initial_state'])
        self.company = self.fixture.raw.company
        self.state_api = ResearchState(self.company, envelope['id'])
        self.kernel = envelope['evaluation_kernel']
        task_module.measurement.kernel(self.kernel, self.state_api.tools.files['questions.md'])


class AssemblyFixture:
    """Reusable fresh original-forecast fixture; no assembly owner is opened."""
    def __init__(self, owner, *, rounds=2):
        cleanups = []
        class Collector:
            def addCleanup(self, callback, *args, **kwargs):
                cleanups.append((callback, args, kwargs))
        self.raw = raw_fixture._ForecastFixture(Collector())
        # Close only the unused setup budget, once, before a later real owner.
        for callback, args, kwargs in cleanups:
            if getattr(callback, '__self__', None) is self.raw.budget:
                callback(*args, **kwargs)
            else:
                owner.addCleanup(callback, *args, **kwargs)
        self.home = self.raw.root / 'assembly-inputs'
        self.home.mkdir()
        self.id = 'earnings-coevolution-20261013-assembly-fixture'
        self.root = self.raw.root / '.codex' / 'worktrees' / 'financial-records' / self.id
        self.native_base = self.raw.root / 'external-native' / 'episodes'
        with self.scope():
            self.paths = namespace.native_paths(self.root, self.id)
        self.paths['source_root'].mkdir(parents=True)
        self.copies = {}
        for name in ('candidate.py', 'researcher_v1.py', 'harness_v1.py'):
            self.copy(name, self.raw.root / name)
        self.copy('evaluation_scorer.py', Path(self.raw.kernel['scorer']['path']))
        self.copy('evaluation_qa.json', Path(self.raw.kernel['qa']['path']))
        initial_api = ResearchState(self.raw.company, self.id)
        self.initial = initial_api.save(self.home / 'initial-state', initial_api.empty())
        original = self.raw.native.before
        self.baseline = engine.identity.manifest(
            kernel={'sources': {name: token for name, token in self.copies.items()
                                if name in {'evaluation_scorer.py', 'evaluation_qa.json'}},
                    'configuration_sha256': digest(self.raw.kernel)},
            predictor=original['components']['C'], harness=original['components']['H'],
            researcher=original['components']['R'], model=original['model'],
            memory=self.initial['sha256'], runtime=original['runtime'])
        self.slots = [{name: str(self.root / 'roles' / (name + f'-{index:02d}'))
                       for name in ('controller', 'author', 'review', 'forecast')}
                      for index in range(1, rounds + 1)]
        self.runtime_slots = {name: [row[name] for row in self.slots]
                              for name in ('controller', 'author', 'review')}
        self.plan_rows = [{'parent': str(self.root / 'roles' / f'parent-{index:02d}'),
                           'candidate': str(self.root / 'roles' / f'candidate-{index:02d}'),
                           'downstream': row['forecast']}
                          for index, row in enumerate(self.slots, 1)]
        self.runtime_slots['forecast'] = [row[name] for row in self.plan_rows
                                         for name in ('parent', 'candidate', 'downstream')]
        self.runtime = {
            'schema': 'earnings_capacity_runtime_v2', 'purpose': 'capacity_episode',
            'id': self.id, 'root': str(self.root), 'source_commit': raw_fixture.SOURCE_COMMIT,
            'ledger': str(self.raw.root / 'owned-ledger.sqlite3'),
            'baseline': deepcopy(self.raw.baseline),
            'cutoff_utc': self.raw.config['new_request_cutoff_utc'],
            'deadline_utc': self.raw.config['deadline_utc'],
            'additional_cap_nano_usd': 20_000_000_000,
            'rates': deepcopy(self.raw.rate),
            'limits': {**{name: deepcopy(LIMITS) for name in ('controller', 'author', 'review')},
                       'forecast': self.raw.limits()},
            'slots': self.runtime_slots, 'forecast_study': self.raw.study_binding,
            'sources': {**{name: engine.pin(path) for name, path in runtime.CORE.items()},
                        'forecast_entry': engine.pin(entry.__file__),
                        'forecaster': engine.pin(inspect.getsourcefile(entry.forecast)),
                        **{'factory_' + role: engine.pin(assembly.__file__)
                           for role in ('controller', 'author', 'review', 'forecast')}}}
        self.envelope = {
            'schema': 'earnings_capacity_episode_v1', 'mode': 'offline_replay',
            'grant': None, 'window': None, 'id': self.id, 'root': str(self.root),
            'source_commit': raw_fixture.SOURCE_COMMIT, 'max_rounds': rounds,
            'role_limits': {name: deepcopy(LIMITS) for name in ('controller', 'author', 'review')},
            'study': self.raw.study_binding, 'cik': self.raw.company['cik'],
            'evaluation_kernel': self.raw.kernel, 'initial_state': self.initial,
            'slots': self.slots,
            'sources': {name: bound['sha256'] for name, bound in task_module.EarningsTask().sources().items()}}
        self.review = {
            'schema': 'earnings_source_review_setup_v1', 'source_root': str(self.paths['source_root']),
            'proposer_id': 'fixture-model-proposer', 'reviewer_id': 'fixture-independent-reviewer',
            'slots': {row['review']: {'candidate_id': f'candidate-{index:02d}',
                    'R': f'researcher_new_{index:02d}.py', 'H': f'harness_new_{index:02d}.py'}
                    for index, row in enumerate(self.slots, 1)}}
        self.native = {
            'schema': 'earnings_native_setup_v1',
            **{key: str(self.paths[key]) for key in ('source_root', 'registry_root', 'batch_root')},
            'baseline': self.baseline, 'entrypoints': {'R': 'researcher_v1.py', 'H': 'harness_v1.py'},
            'batch_config': {'batch_id': self.id, 'start_utc': '2026-10-13T00:00:00Z',
                'deadline_utc': self.runtime['deadline_utc'], 'max_attempts': 3 * rounds,
                'initial_incumbent': {'candidate_id': 'fixture-baseline', 'candidate_sha256': self.baseline['C'],
                                     'scorecard_sha256': '0' * 64, 'review_sha256': '0' * 64},
                'active_pool_capacity': 2, 'learning_checkpoint_version': 1},
            'micro_config': {'pair': engine.activation.pair(self.baseline),
                'fixed_context': {},
                'allowed_write_paths': {
                    'researcher': ['researcher_v1.py', *[row['R'] for row in self.review['slots'].values()]],
                    'harness': ['harness_v1.py', *[row['H'] for row in self.review['slots'].values()]]},
                'protected_paths': ['candidate.py', 'evaluation_scorer.py', 'evaluation_qa.json'],
                'reviewer_id': self.review['reviewer_id']}}
        self.registration = {'schema': 'earnings_effect_review_registration_v1',
            'reviewer_id': self.review['reviewer_id'], 'proposer_id': self.review['proposer_id'],
            'review_source': engine.source_of(effect_review),
            'probe_source': engine.source_of(MechanicalProbes.run), 'scopes': deepcopy(SCOPES)}
        self.factory_calls, self.clients, self.sequence = 0, [], 0
        self.task = FixtureAdmissionTask(self)
        self.seal()

    def copy(self, name, original):
        data = original.read_bytes()
        (self.paths['source_root'] / name).write_bytes(data)
        self.copies[name] = sha256(data).hexdigest()

    @contextmanager
    def scope(self):
        with patch.object(namespace, 'NATIVE_RUNTIME_ROOT', self.native_base):
            yield

    def client_factory(self):
        self.factory_calls += 1
        client = type(self.raw.http)('', timeout=self.raw.runtime['request_timeout_seconds'])
        self.clients.append(client)
        return client

    def save(self, label, body):
        self.sequence += 1
        return engine.save(self.home / (label + f'-{self.sequence:03d}.json'), body)

    def seal(self):
        self.runtime_binding = self.save('runtime', self.runtime)
        self.episode_binding = self.save('episode', self.envelope)
        self.native['micro_config']['fixed_context'] = {
            'model_sha256': self.native['baseline']['M'],
            'evaluation_sha256': self.native['baseline']['K'],
            'data_scope_sha256': digest({'study': self.envelope['study'], 'cik': self.envelope['cik'],
                                        'kernel': self.envelope['evaluation_kernel']}),
            'authority_sha256': digest({key: self.envelope[key] for key in ('mode', 'grant', 'window')}),
            'resource_policy_sha256': digest(self.runtime_binding)}
        self.plan = {'schema': 'earnings_matched_plan_v1', 'episode': self.episode_binding,
                     'rounds': self.plan_rows}
        self.assembly = {'schema': 'earnings_capacity_assembly_v1', 'mode': 'offline_replay',
            'episode': self.episode_binding, 'runtime': self.runtime_binding,
            'native': self.save('native', self.native),
            'matched_plan': self.save('matched-plan', self.plan),
            'effect_registration': self.save('effect-registration', self.registration),
            'source_review': self.save('source-review', self.review),
            'constructors': assembly.constructor_sources(), 'transport': engine.source_of(self.client_factory),
            'claims': {'model_authorship': False, 'predictive_gain': False}}
        self.assembly_binding = self.save('assembly', self.assembly)

    def retained_tree(self):
        return {str(path): ('link', str(path.readlink())) if path.is_symlink()
                else ('file', path.read_bytes()) for path in self.raw.root.rglob('*')
                if path.is_symlink() or path.is_file()}

    def readiness(self, **changes):
        values = dict(envelope=self.envelope, assembly=self.assembly, runtime=self.runtime,
                      native=self.native, review=self.review)
        values.update(changes)
        with self.scope():
            return readiness.validate_setup(self.episode_binding, **values)

    @contextmanager
    def exchange(self, replies):
        """Fake only original HTTPS bytes; callable replies inspect real payloads."""
        values = [None] * len(replies)
        original = self.raw.fake_connection(values)
        fixture = self
        class Connection(original):
            def getresponse(self):
                if self.endpoint == '/v1/responses':
                    reply = replies[self.turn]
                    values[self.turn] = reply(deepcopy(fixture.raw.calls[-1][1])) if callable(reply) else reply
                return super().getresponse()
        def deadline_init(transport, client, **options):
            options.update(clock=lambda: fixture.raw.wall, monotonic=lambda: fixture.raw.monotonic)
            raw_fixture.DEADLINE_INIT(transport, client, **options)
        with ExitStack() as stack:
            stack.enter_context(self.scope())
            stack.enter_context(patch('earnings_http.http.client.HTTPSConnection', side_effect=Connection))
            stack.enter_context(patch.object(entry, 'credential', side_effect=AssertionError('No credentials')))
            stack.enter_context(patch.object(controller, 'credential', side_effect=AssertionError('No credentials')))
            stack.enter_context(patch.object(clock, 'boot_id', return_value=raw_fixture.BOOT))
            stack.enter_context(patch.object(entry.time, 'time', side_effect=lambda: fixture.raw.wall))
            stack.enter_context(patch.object(entry.time, 'monotonic', side_effect=lambda: fixture.raw.monotonic))
            stack.enter_context(patch.object(entry.DeadlineHTTP, '__init__', new=deadline_init))
            yield

    def ledger_rows(self):
        # Read this fixture's own ledger only; the real ledger is never inferred.
        with sqlite3.connect(Path(self.runtime['ledger']).as_uri() + '?mode=ro', uri=True) as db:
            return db.execute('SELECT id, model, reserved, charged, status FROM requests ORDER BY rowid').fetchall()

    def rebuild_baseline(self, **changes):
        old = self.native['baseline']
        args = {'kernel': old['components']['K'], 'predictor': old['components']['C'],
                'harness': old['components']['H'], 'researcher': old['components']['R'],
                'model': old['model'], 'memory': old['memory_sha256'], 'runtime': old['runtime']}
        args.update(changes)
        self.native['baseline'] = engine.identity.manifest(**args)


class AssemblyReadinessTests(unittest.TestCase):
    def fixture(self, *, rounds=2):
        return AssemblyFixture(self, rounds=rounds)

    def refuse(self, fixture, **changes):
        before = fixture.retained_tree()
        with patch.object(assembly, '_native', side_effect=AssertionError('No Native constructor')) as native, \
                patch.object(assembly, 'open_capacity_runtime', side_effect=AssertionError('No owner')) as owner:
            with self.assertRaises((ValueError, KeyError, TypeError, OSError)):
                fixture.readiness(**changes)
        native.assert_not_called()
        owner.assert_not_called()
        self.assertEqual(fixture.retained_tree(), before)
        self.assertEqual(fixture.factory_calls, 0)
        self.assertEqual(fixture.task.preflight_calls, [])

    def test_exact_one_and_two_round_setups_are_pure_with_unconsumed_native_paths(self):
        for rounds in (1, 2):
            with self.subTest(rounds=rounds):
                fixture = self.fixture(rounds=rounds)
                before = fixture.retained_tree()
                self.assertEqual(fixture.readiness(), fixture.paths)
                self.assertEqual(fixture.retained_tree(), before)
                self.assertEqual(fixture.factory_calls, 0)
                self.assertEqual(fixture.task.preflight_calls, [])
                self.assertFalse(fixture.paths['batch_root'].exists())
                self.assertFalse(fixture.paths['registry_root'].exists())

    def test_native_schema_and_undeclared_namespace_refuse_before_claims(self):
        for kind in ('schema', 'extra', 'missing', 'source', 'registry', 'batch'):
            fixture = self.fixture()
            changed = deepcopy(fixture.native)
            if kind == 'schema': changed['schema'] = 'unknown'
            elif kind == 'extra': changed['undeclared'] = True
            elif kind == 'missing': changed.pop('entrypoints')
            else: changed[kind + '_root'] = str(fixture.raw.root / 'outside' / kind)
            with self.subTest(kind=kind): self.refuse(fixture, native=changed)

    def test_consumed_empty_partial_batch_registry_and_probe_roots_are_never_reopened(self):
        for key in ('batch_root', 'registry_root', 'probe_root'):
            for occupied in (False, True):
                fixture = self.fixture()
                fixture.paths[key].mkdir(parents=True)
                if occupied: (fixture.paths[key] / 'retained.partial').write_bytes(b'failed original')
                with self.subTest(root=key, occupied=occupied): self.refuse(fixture)

    def test_exact_integer_round_count_refuses_bool_zero_and_more_than_two(self):
        for count in (True, False, 0, 3, 1.0):
            fixture = self.fixture(rounds=1)
            with self.subTest(count=count):
                self.refuse(fixture, envelope=dict(fixture.envelope, max_rounds=count))

    def test_physical_source_byte_drift_is_not_repaired_or_used(self):
        for name in ('candidate.py', 'researcher_v1.py', 'harness_v1.py',
                     'evaluation_scorer.py', 'evaluation_qa.json'):
            fixture = self.fixture()
            target = fixture.paths['source_root'] / name
            target.write_bytes(target.read_bytes() + b'\n# retained owned corruption\n')
            with self.subTest(source=name): self.refuse(fixture)

    def test_canonical_source_ancestry_and_pinned_python_bytes_are_checked_readonly(self):
        fixture = self.fixture()
        original = fixture.paths['source_root'] / 'candidate.py'
        retained = fixture.paths['source_root'] / 'retained-original-candidate.py'
        original.rename(retained)
        original.symlink_to(retained)
        self.refuse(fixture)
        fixture = self.fixture()
        python = Path(fixture.native['baseline']['runtime']['python']['path'])
        python.write_bytes(b'retained corrupted owned Python fixture')
        self.refuse(fixture)

    def test_self_consistent_wrong_model_memory_or_kernel_config_is_refused(self):
        for kind in ('model', 'memory', 'kernel'):
            fixture = self.fixture()
            if kind == 'model': fixture.rebuild_baseline(model=dict(fixture.baseline['model'], requested_model='gpt-5.5'))
            elif kind == 'memory': fixture.rebuild_baseline(memory='e' * 64)
            else: fixture.rebuild_baseline(kernel=dict(fixture.baseline['components']['K'], configuration_sha256='e' * 64))
            with self.subTest(kind=kind): self.refuse(fixture)

    def test_literal_profile_validation_is_not_merely_a_source_hash_check(self):
        fixture = self.fixture()
        target = fixture.paths['source_root'] / 'researcher_v1.py'
        target.write_bytes(b"import os\nPROFILE = {'axis':'R','research_instructions':'','reuse_facts':True}\n")
        fixture.rebuild_baseline(researcher={
            'sources': {'researcher_v1.py': sha256(target.read_bytes()).hexdigest()},
            'configuration_sha256': fixture.baseline['components']['R']['configuration_sha256']})
        self.refuse(fixture)

    def test_entrypoints_are_exact_axis_members_and_python_literals(self):
        for entries in ({'R': 'harness_v1.py', 'H': 'harness_v1.py'},
                        {'R': 'missing.py', 'H': 'harness_v1.py'}, {'R': 'researcher_v1.py'},
                        {'R': 'researcher_v1.py', 'H': 'harness_v1.py', 'K': 'evaluation_scorer.py'}):
            fixture = self.fixture()
            with self.subTest(entries=entries): self.refuse(fixture, native=dict(fixture.native, entrypoints=entries))

    def test_batch_identity_quota_pool_and_checkpoint_configuration_are_exact(self):
        changes = ({'batch_id': 'different-id'}, {'max_attempts': 7}, {'max_attempts': True},
                   {'active_pool_capacity': 4}, {'active_pool_capacity': True},
                   {'learning_checkpoint_version': 2}, {'learning_checkpoint_version': True},
                   {'extra': 'unreviewed'}, {'deadline_utc': '2099-01-01T00:06:00Z'})
        for change in changes:
            fixture = self.fixture()
            fixture.native['batch_config'].update(change)
            with self.subTest(change=change): self.refuse(fixture)

    def test_batch_start_cannot_extend_beyond_original_cutoff_or_terminal_deadline(self):
        for start in ('2099-01-01T00:05:00Z', '2099-01-01T00:00:01Z'):
            fixture = self.fixture()
            fixture.native['batch_config']['start_utc'] = start
            with self.subTest(start=start): self.refuse(fixture)
        fixture = self.fixture()
        fixture.native['batch_config']['initial_incumbent']['candidate_sha256'] = 'e' * 64
        self.refuse(fixture)

    def test_fixed_context_commits_actual_data_authority_model_and_runtime(self):
        for name in ('model_sha256', 'evaluation_sha256', 'data_scope_sha256',
                     'authority_sha256', 'resource_policy_sha256'):
            fixture = self.fixture()
            fixture.native['micro_config']['fixed_context'][name] = 'e' * 64
            with self.subTest(commitment=name): self.refuse(fixture)

    def test_mutable_scopes_exactly_cover_original_and_prospective_axis_files(self):
        for kind in ('extra', 'missing-original', 'missing-prospective', 'overlap-kernel'):
            fixture = self.fixture()
            scope = fixture.native['micro_config']['allowed_write_paths']['researcher']
            if kind == 'extra': scope.append('undeclared.py')
            elif kind == 'missing-original': scope.remove('researcher_v1.py')
            elif kind == 'missing-prospective': scope.pop()
            else: scope.append('evaluation_scorer.py')
            with self.subTest(kind=kind): self.refuse(fixture)

    def test_protected_paths_cover_all_original_kernel_and_predictor_sources(self):
        for name in ('candidate.py', 'evaluation_scorer.py', 'evaluation_qa.json'):
            fixture = self.fixture()
            fixture.native['micro_config']['protected_paths'].remove(name)
            with self.subTest(missing=name): self.refuse(fixture)

    def test_source_review_actor_slot_shape_names_and_candidate_ids_are_exact(self):
        for kind in ('actor', 'same-actor', 'missing-slot', 'extra-row-key', 'duplicate-id', 'duplicate-source', 'traversal'):
            fixture = self.fixture()
            rows = list(fixture.review['slots'].values())
            if kind == 'actor': fixture.review['reviewer_id'] = 'unregistered-reviewer'
            elif kind == 'same-actor': fixture.review['proposer_id'] = fixture.review['reviewer_id']
            elif kind == 'missing-slot': fixture.review['slots'].pop(next(iter(fixture.review['slots'])))
            elif kind == 'extra-row-key': rows[0]['extra'] = True
            elif kind == 'duplicate-id': rows[1]['candidate_id'] = rows[0]['candidate_id']
            elif kind == 'duplicate-source': rows[1]['R'] = rows[0]['R']
            else: rows[0]['R'] = '../outside.py'
            with self.subTest(kind=kind): self.refuse(fixture)

    def test_prospective_source_consumption_is_detected_before_native_registry(self):
        fixture = self.fixture()
        row = next(iter(fixture.review['slots'].values()))
        (fixture.paths['source_root'] / row['R']).write_bytes(b'retained prior candidate')
        self.refuse(fixture)

    def test_effect_registration_requires_exact_sources_actors_schema_and_scopes(self):
        for kind in ('schema', 'actor', 'probe', 'review', 'scope', 'extra'):
            fixture = self.fixture()
            changed = deepcopy(fixture.registration)
            if kind == 'schema': changed['schema'] = 'unknown'
            elif kind == 'actor': changed['proposer_id'] = changed['reviewer_id']
            elif kind in ('probe', 'review'): changed[kind + '_source']['module']['sha256'] = 'e' * 64
            elif kind == 'scope': changed['scopes']['restart'] = 'Claims provider restart'
            else: changed['unreviewed'] = True
            bound = fixture.save('bad-registration', changed)
            with self.subTest(kind=kind): self.refuse(fixture, assembly=dict(fixture.assembly, effect_registration=bound))

    def test_plan_named_order_is_independent_of_json_dictionary_order(self):
        fixture = self.fixture()
        plan = deepcopy(fixture.plan)
        plan['rounds'] = [{name: row[name] for name in ('downstream', 'candidate', 'parent')}
                          for row in plan['rounds']]
        changed = dict(fixture.assembly, matched_plan=fixture.save('reordered-plan', plan))
        before = fixture.retained_tree()
        self.assertEqual(fixture.readiness(assembly=changed), fixture.paths)
        self.assertEqual(fixture.retained_tree(), before)

    def test_plan_schema_episode_round_shape_and_downstream_are_prospective(self):
        for kind in ('schema', 'episode', 'round-count', 'extra-key', 'missing-key', 'downstream'):
            fixture = self.fixture()
            plan = deepcopy(fixture.plan)
            if kind == 'schema': plan['schema'] = 'unknown'
            elif kind == 'episode': plan['episode']['sha256'] = 'e' * 64
            elif kind == 'round-count': plan['rounds'].pop()
            elif kind == 'extra-key': plan['rounds'][0]['extra'] = 'unreviewed'
            elif kind == 'missing-key': plan['rounds'][0].pop('parent')
            else: plan['rounds'][0]['downstream'] = plan['rounds'][0]['parent']
            bound = fixture.save('bad-plan', plan)
            with self.subTest(kind=kind): self.refuse(fixture, assembly=dict(fixture.assembly, matched_plan=bound))

    def test_all_role_slots_are_new_flat_unique_and_canonical_before_claims(self):
        for kind in ('consumed-controller', 'consumed-author', 'consumed-review', 'consumed-forecast',
                     'duplicate', 'nested', 'traversal'):
            fixture = self.fixture()
            if kind.startswith('consumed-'):
                Path(fixture.slots[0][kind.removeprefix('consumed-')]).mkdir(parents=True)
                self.refuse(fixture)
                continue
            plan = deepcopy(fixture.plan)
            slots = deepcopy(fixture.runtime)
            new = (plan['rounds'][0]['candidate'] if kind == 'duplicate'
                   else str(fixture.root / 'roles' / 'nested' / 'parent-01') if kind == 'nested'
                   else str(fixture.root / 'roles') + '/../roles/parent-01')
            plan['rounds'][0]['parent'] = new
            slots['slots']['forecast'][0] = new
            changed = dict(fixture.assembly, matched_plan=fixture.save('bad-slots-plan', plan))
            with self.subTest(kind=kind): self.refuse(fixture, assembly=changed, runtime=slots)

    def test_missing_explicit_transport_refuses_before_read_task_native_or_owner(self):
        with patch.object(engine, 'read', side_effect=AssertionError('No configuration read')) as read, \
                patch.object(assembly, 'EarningsTask', side_effect=AssertionError('No Task constructor')) as task, \
                patch.object(assembly, '_native', side_effect=AssertionError('No Native constructor')) as native, \
                patch.object(assembly, 'open_capacity_runtime', side_effect=AssertionError('No owner')) as owner:
            with self.assertRaisesRegex(ValueError, 'transport'):
                assembly.validate_assembly({'path': 'not-even-read', 'sha256': 'e' * 64},
                    {'path': 'not-even-read', 'sha256': 'e' * 64}, client_factory=None)
        for call in (read, task, native, owner): call.assert_not_called()

    def test_default_task_admission_failure_remains_before_native_owner_and_factory(self):
        fixture = self.fixture()
        before = fixture.retained_tree()
        with fixture.scope(), \
                patch.object(entry, 'preflight_capacity_episode', side_effect=ValueError('Original data admission refused')) as preflight, \
                patch.object(assembly, '_native', side_effect=AssertionError('No Native constructor')) as native, \
                patch.object(assembly, 'open_capacity_runtime', side_effect=AssertionError('No owner')) as owner:
            with self.assertRaisesRegex(ValueError, 'Original data admission refused'):
                assembly.validate_assembly(fixture.episode_binding, fixture.assembly_binding,
                                           client_factory=fixture.client_factory)
        preflight.assert_called_once_with(fixture.envelope)
        native.assert_not_called()
        owner.assert_not_called()
        self.assertEqual(fixture.retained_tree(), before)
        self.assertEqual(fixture.factory_calls, 0)

    def test_assembly_uses_explicit_fixture_admission_only_after_pure_readiness(self):
        fixture = self.fixture()
        before = fixture.retained_tree()
        with fixture.scope(), patch.object(assembly, '_native', side_effect=AssertionError('No Native constructor')) as native, \
                patch.object(assembly, 'open_capacity_runtime', side_effect=AssertionError('No owner')) as owner:
            result = assembly.validate_assembly(fixture.episode_binding, fixture.assembly_binding,
                client_factory=fixture.client_factory, task=fixture.task)
        self.assertEqual(result, (fixture.envelope, fixture.assembly, fixture.native, fixture.review, fixture.task))
        self.assertEqual(fixture.task.preflight_calls, [fixture.envelope])
        self.assertEqual(fixture.retained_tree(), before)
        self.assertEqual(fixture.factory_calls, 0)
        native.assert_not_called()
        owner.assert_not_called()

    def test_consumed_owner_claim_or_terminal_id_refuses_before_task_native_or_transport(self):
        for suffix in ('.json', '.result.json'):
            fixture = self.fixture()
            claims = Path(fixture.runtime['ledger']).parent / '.capacity-runtime-claims'
            claims.mkdir()
            retained = claims / (sha256(fixture.id.encode()).hexdigest() + suffix)
            retained.write_bytes(b'{"original_consumed_id": true}\n')
            before = fixture.retained_tree()
            with fixture.scope(), \
                    patch.object(assembly, '_native', side_effect=AssertionError('No Native constructor')) as native, \
                    patch.object(assembly, 'open_capacity_runtime', side_effect=AssertionError('No owner')) as owner:
                with self.assertRaisesRegex(ValueError, 'Consumed runtime ID'):
                    assembly.validate_assembly(fixture.episode_binding, fixture.assembly_binding,
                        client_factory=fixture.client_factory, task=fixture.task)
            self.assertEqual(fixture.retained_tree(), before)
            self.assertEqual(fixture.task.preflight_calls, [])
            self.assertEqual(fixture.factory_calls, 0)
            native.assert_not_called()
            owner.assert_not_called()

    def test_assembly_rejects_source_identity_transport_and_claim_drift_before_admission(self):
        for kind in ('schema', 'mode', 'constructors', 'transport', 'claims', 'extra'):
            fixture = self.fixture()
            changed = deepcopy(fixture.assembly)
            if kind == 'schema': changed['schema'] = 'unknown'
            elif kind == 'mode': changed['mode'] = 'live'
            elif kind == 'constructors': changed['constructors']['controller']['module']['sha256'] = 'e' * 64
            elif kind == 'transport': changed['transport']['module']['sha256'] = 'e' * 64
            elif kind == 'claims': changed['claims']['predictive_gain'] = True
            else: changed['undeclared'] = True
            bound = fixture.save('bad-assembly', changed)
            before = fixture.retained_tree()
            with fixture.scope(), \
                    patch.object(assembly, '_native', side_effect=AssertionError('No Native constructor')) as native, \
                    patch.object(assembly, 'open_capacity_runtime', side_effect=AssertionError('No owner')) as owner:
                with self.assertRaises((ValueError, KeyError, TypeError, OSError)):
                    assembly.validate_assembly(fixture.episode_binding, bound,
                        client_factory=fixture.client_factory, task=fixture.task)
            self.assertEqual(fixture.retained_tree(), before)
            self.assertEqual(fixture.task.preflight_calls, [])
            self.assertEqual(fixture.factory_calls, 0)
            native.assert_not_called()
            owner.assert_not_called()

    def test_bad_prospective_inputs_fail_at_actual_assembly_before_task_or_owners(self):
        for kind in ('physical-source', 'review-actor', 'plan', 'effect-registration', 'consumed-slot'):
            fixture = self.fixture()
            if kind == 'physical-source':
                target = fixture.paths['source_root'] / 'researcher_v1.py'
                target.write_bytes(target.read_bytes() + b'\n# retained bad original\n')
            elif kind == 'review-actor': fixture.review['reviewer_id'] = 'wrong-actor'
            elif kind == 'plan': fixture.plan_rows[0]['unreviewed'] = 'extra'
            elif kind == 'effect-registration': fixture.registration['probe_source']['module']['sha256'] = 'e' * 64
            else: Path(fixture.slots[0]['forecast']).mkdir(parents=True)
            fixture.seal()
            before = fixture.retained_tree()
            with fixture.scope(), \
                    patch.object(assembly, 'EarningsTask', side_effect=AssertionError('No Task constructor')) as task, \
                    patch.object(assembly, '_native', side_effect=AssertionError('No Native constructor')) as native, \
                    patch.object(assembly, 'open_capacity_runtime', side_effect=AssertionError('No owner')) as owner:
                with self.assertRaises((ValueError, KeyError, TypeError, OSError)):
                    assembly.validate_assembly(fixture.episode_binding, fixture.assembly_binding,
                        client_factory=fixture.client_factory)
            self.assertEqual(fixture.retained_tree(), before)
            self.assertEqual(fixture.factory_calls, 0)
            self.assertEqual(fixture.task.preflight_calls, [])
            task.assert_not_called()
            native.assert_not_called()
            owner.assert_not_called()


if __name__ == '__main__':
    unittest.main()
