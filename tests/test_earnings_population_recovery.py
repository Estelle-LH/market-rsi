"""Independent recovery contracts; no paid/candidate/scorer execution.

Portable prefix fixtures use real bound reads, durable seals and journal locks.
The opt-in local test reconstructs actual closed05 and projects its next role
context under dev-only read guards. Temporary context envelopes are not a new
runtime admission or evidence of a model having consumed that future context.
"""
from contextlib import ExitStack
from copy import deepcopy
import builtins
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import earnings_population_recovery as recovery
import earnings_population_campaign_context as contexts
import earnings_population_continuation as history
import earnings_population_tasks as tasks
from earnings_population_broker import public_feedback
from earnings_population_roles import PopulationController
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine

DEV = frozenset({'CIK0000003545', 'CIK0000004457', 'CIK0000017313'})
IDENT = 'edgar-population-20261016-05'
FAILURE_SHA = '9f781795ffb9d54442e3625d98876fb978db4045a8a5bcd7cb24195933c0a5f5'


class FailedPrefixContracts(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.attempt = self.root/'attempts'/IDENT
        self.path = self.attempt/'loop'; self.path.mkdir(parents=True)
        (self.path/'.loop.lock').touch()
        self.reader = history._Reader(self.root, self.root/'unused.sqlite3', self.root/'repo', IDENT)
        source = lambda name: dict(path=str(self.root/'repo'/name), sha256='a'*64)
        names = [history.DRIVER, 'tools/earnings_population_loop.py',
                 'tools/earnings_population_run.py', 'tools/earnings_population_services.py',
                 'tools/earnings_population_campaign.py']
        self.runtime = dict(companies=['CIK0000017313']*2,
            initial_population=self.save('initial.json', {'retained_seed': True}),
            sources={name: source(name) for name in names},
            forecast_study=self.save('study.json', {'campaign': {'opaque': 'fixture'}}))
        seed = dict(population={'retained_seed': True}, companies=self.runtime['companies'],
                    feedback={'unchanged_scientific_feedback': True})
        handlers = {stage: dict(stage=stage,
            adapter=self.runtime['sources']['tools/earnings_population_loop.py'],
            admission={'function': 'execute.<locals>.admit', 'module': self.runtime['sources']['tools/earnings_population_run.py']},
            services={role: {'function': 'Services.'+role, 'module': self.runtime['sources']['tools/earnings_population_services.py']}
                      for role in ('controller', 'author', 'review', 'forecast')},
            campaign_policy=self.runtime['sources']['tools/earnings_population_campaign.py'],
            campaign={'opaque': 'fixture'}) for stage in history.STAGES}
        manifest = dict(schema='feedback_linked_loop_v1', seed=seed, seed_sha256=digest(seed),
            max_rounds=2, handler_identity=handlers, driver_source_sha256='a'*64)
        self.seal(self.path/'manifest.json', manifest)
        outputs = {}
        for stage in history.STAGES[:4]:
            prefix = self.path/f'round-0001-{stage}'
            current = dict(round_index=1, seed=seed, previous_result=seed,
                previous_feedback_sha256=digest(seed), outputs=outputs)
            claim = dict(round_index=1, stage=stage, context_sha256=digest(current),
                manifest_sha256=engine.pin(self.path/'manifest.json')['sha256'],
                previous_feedback_sha256=digest(seed))
            self.replace(prefix.with_suffix('.claim.json'), claim)
            if stage == 'source_review':
                self.replace(prefix.with_suffix('.failed.json'),
                    dict(claim_sha256=engine.pin(prefix.with_suffix('.claim.json'))['sha256'],
                         exception_type='RuntimeError', retry_allowed=False))
                break
            output = {'stage': stage, 'fixture_only': True}
            self.seal(prefix.with_suffix('.done.json'),
                dict(claim_sha256=engine.pin(prefix.with_suffix('.claim.json'))['sha256'],
                     output=output, output_sha256=digest(output)))
            outputs[stage] = output

    @staticmethod
    def replace(path, value):
        path.write_text(json.dumps(value, sort_keys=True))

    def save(self, name, value):
        path = self.attempt/name; self.replace(path, value); return engine.pin(path)

    def seal(self, path, value):
        self.replace(path, value)
        self.replace(path.with_suffix('.binding.json'), engine.pin(path))

    def load(self):
        return recovery._prefix(self.reader, self.runtime, self.attempt)

    def test_exact_three_completed_stages_and_fourth_failed_are_read_only(self):
        before = {str(p): p.read_bytes() for p in self.attempt.rglob('*') if p.is_file()}
        seed, outputs, evidence = self.load()
        self.assertEqual(set(outputs), set(history.STAGES[:3]))
        self.assertEqual(seed['population'], {'retained_seed': True})
        self.assertEqual(len(evidence), 9)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.attempt.rglob('*') if p.is_file()})

    def test_added_execute_or_later_round_claim_cannot_be_recovered_as_unscored_prefix(self):
        for name in ('round-0001-execute.claim.json', 'round-0002-input.claim.json'):
            with self.subTest(name=name):
                path = self.path/name; self.replace(path, {})
                with self.assertRaisesRegex(ValueError, 'first-review failure'):
                    self.load()
                path.unlink()

    def test_failure_kind_or_retry_permission_tamper_is_rejected(self):
        path = self.path/'round-0001-source_review.failed.json'
        original = json.loads(path.read_text())
        for changes in ({'exception_type': 'ValueError'}, {'retry_allowed': True}):
            self.replace(path, dict(original, **changes))
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'failure record'):
                self.load()

    def test_completed_source_review_is_not_this_delivery_failure_mode(self):
        self.seal(self.path/'round-0001-source_review.done.json', {'accepted_for_exploration': True})
        with self.assertRaisesRegex(ValueError, 'first-review failure'):
            self.load()

    def test_claim_context_cannot_be_resealed_with_different_parent_feedback(self):
        path = self.path/'round-0001-implement.claim.json'
        self.replace(path, dict(json.loads(path.read_text()), context_sha256='0'*64))
        with self.assertRaisesRegex(ValueError, 'claim changed'):
            self.load()

    def test_completed_output_digest_or_durable_seal_must_match(self):
        path = self.path/'round-0001-implement.done.json'
        self.seal(path, dict(json.loads(path.read_text()), output_sha256='0'*64))
        with self.assertRaisesRegex(ValueError, 'completed prefix seal'):
            self.load()

    def test_manifest_seed_and_handler_campaign_identity_are_checked(self):
        path = self.path/'manifest.json'; original = json.loads(path.read_text())
        bad = deepcopy(original); bad['seed_sha256'] = '0'*64; self.seal(path, bad)
        with self.assertRaisesRegex(ValueError, 'seed/driver'):
            self.load()
        bad = deepcopy(original); bad['handler_identity']['input']['admission']['function'] = 'foreign'
        self.seal(path, bad)
        with self.assertRaisesRegex(ValueError, 'handler identity'):
            self.load()


class RecoveryScopeContracts(unittest.TestCase):
    def test_invalid_shapes_foreign_roots_aliases_and_filenames_fail_before_reader(self):
        exact = dict(path=str(recovery.resume.OWNED/'attempts'/IDENT/'population-run-failure.json'), sha256=FAILURE_SHA)
        plan = dict(path=str(recovery.resume.REPO/recovery.PLAN), sha256='a'*64)
        cases = [({'path': exact['path']}, {}), (dict(exact, sha256='bad'), {}),
            (dict(exact, path='/private/tmp/foreign/population-run-failure.json'), {}),
            (dict(exact, path=exact['path'].replace('/attempts/', '/attempts/../attempts/')), {}),
            (dict(exact, path=exact['path'].replace('failure.json', 'result.json')), {}),
            (exact, {'root': Path('/private/tmp/foreign')}),
            (exact, {'ledger': Path('/private/tmp/foreign.sqlite3')}),
            (exact, {'repo': Path('/private/tmp/foreign-repo')})]
        with patch.object(history, '_Reader', side_effect=AssertionError('Scope must fail before read')):
            for binding, changes in cases:
                kwargs = dict(root=recovery.resume.OWNED, ledger=recovery.resume.LEDGER,
                              repo=recovery.resume.REPO, plan_binding=plan); kwargs.update(changes)
                with self.subTest(binding=binding, changes=changes), self.assertRaises(ValueError):
                    recovery.load(binding, **kwargs)

    def test_foreign_plan_is_not_opened(self):
        binding = dict(path=str(recovery.resume.OWNED/'attempts'/IDENT/'population-run-failure.json'), sha256=FAILURE_SHA)
        with patch.object(history, '_Reader', side_effect=AssertionError('No reader before plan scope')):
            with self.assertRaisesRegex(ValueError, 'Canonical owned'):
                recovery.load(binding, root=recovery.resume.OWNED, ledger=recovery.resume.LEDGER,
                    repo=recovery.resume.REPO, plan_binding=dict(path='/private/tmp/foreign-plan.json', sha256='a'*64))

    def test_autonomous_first_controller_keeps_R_H_and_continue_choices(self):
        role = object.__new__(PopulationController)
        captured = {}
        def no_dispatch(prompt, slot, instructions, response_format, decode, artifact, status):
            captured.update(prompt=prompt, response_format=response_format)
        role._run_open = no_dispatch
        role.propose(dict(active_versions=['stable', 'explorer'], explorers=['explorer'],
            feedback_sha256='a'*64, repair_assignment=None), '/private/tmp/inert-controller-slot')
        fields = captured['response_format']['schema']['properties']
        self.assertEqual(fields['axis']['enum'], ['R', 'H', 'continue'])


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_RECOVERY05') == '1',
                     'Explicit guarded read-only closed05 audit opt-in required')
class ActualClosed05RecoveryAudit(unittest.TestCase):
    def test_actual05_and_next_context_keep_scientific03_with_reference_only_R5(self):
        opened, residents = [], []
        original_resident = tasks.resident
        def resident(cik):
            if cik not in DEV:
                raise AssertionError('Non-development resident forbidden: '+str(cik))
            residents.append(cik); return original_resident(cik)
        def guard(function):
            def check(path, *args, **kwargs):
                if not isinstance(path, int):
                    text = os.fsdecode(path)
                    if set(re.findall(r'CIK[0-9]{10}', text))-DEV:
                        raise AssertionError('Non-development open forbidden: '+text)
                    opened.append(text)
                return function(path, *args, **kwargs)
            return check
        plan = engine.pin(recovery.resume.REPO/recovery.PLAN)
        binding = dict(path=str(recovery.resume.OWNED/'attempts'/IDENT/'population-run-failure.json'), sha256=FAILURE_SHA)
        with ExitStack() as stack:
            stack.enter_context(patch.object(tasks, 'resident', side_effect=resident))
            for module in (builtins, io, os):
                stack.enter_context(patch.object(module, 'open', guard(module.open)))
            origin = recovery.load(binding, root=recovery.resume.OWNED,
                ledger=recovery.resume.LEDGER, repo=recovery.resume.REPO, plan_binding=plan)
            self.assertEqual(digest(origin['population']), 'b4b657f387462a49f6a52bc964d8922d73d886b90fd6b6e95ad6f596a7370ce9')
            self.assertEqual(origin['feedback']['sha256'], '533fd0bd5772b827bd5c5c9110122781e497ae0b7633b660d7661fa94951c1ea')
            self.assertEqual(origin['last_scored_feedback']['sha256'], '25898533b7b23f63f16b56ca35a4eaaab9919141e7e89b19d4329dd04e552e92')
            ref = origin['reference_candidate']; rc = origin['recovery_context']
            self.assertTrue(ref['reference_only']); self.assertNotIn(ref['id'], origin['population']['versions'])
            self.assertEqual(ref['source']['sha256'], 'e5dd63e0b144f6e335e4dec3acda32566b93a7ad4892d3351755bba3835c7d74')
            self.assertEqual(rc['error_type'], 'BudgetStop'); self.assertEqual(rc['review_assessment'], 'not_generated')
            self.assertEqual(rc['score_state'], 'unscored'); self.assertNotIn('accepted_for_exploration', rc)
            self.assertTrue(all(IDENT in p['receipt']['path'] for p in rc['probes']))
            public = public_feedback(origin['feedback'], origin['population']['versions'])
            # Inert temporary role-context envelopes only; no prepare/owner/API.
            with tempfile.TemporaryDirectory() as name:
                temp = Path(name).resolve()
                ob = engine.save(temp/'origin.json', origin)
                cb = engine.save(temp/'campaign.json', {'schema': 'inert_context_fixture'})
                rb = engine.save(temp/'resume.json', {'repair': None})
                sb = engine.save(temp/'study.json', {'campaign': cb, 'campaign_origin': ob, 'campaign_resume': rb})
                projected = contexts.prepare({'forecast_study': sb},
                    {'campaign': cb, 'feedback': origin['feedback'], 'round_index': 1}, public)
            self.assertIsNone(projected['repair_assignment'])
            self.assertEqual(projected['prior_candidate'], ref)
            self.assertEqual(projected['research_context']['observations']['prior_delivery_failure'], rc)
            self.assertEqual(projected['research_context']['observations']['current_public_diagnostics'], rc['probes'])
            examples = projected['failure_evidence_context']['examples']
            self.assertEqual(len(examples), 3)
            self.assertTrue(all(len(x['outer_public_context']['read_result']['text'])==4000 for x in examples))
            full = deepcopy(projected['research_context']); brief = contexts.controller_view(full)
            self.assertEqual(full, projected['research_context'])
            self.assertEqual(brief['planning_view']['omitted_nearby_text_characters'], [4000]*3)
        self.assertTrue(opened); self.assertTrue(residents); self.assertLessEqual(set(residents), DEV)


if __name__ == '__main__':
    unittest.main()
