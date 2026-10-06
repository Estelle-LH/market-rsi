"""Feedback-linked service fixtures; real boundary code, synthetic science only."""
from copy import deepcopy
import csv
from datetime import date, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import Mock, patch

from supervisor_harness import price_loop_services as services
from supervisor_harness import price_loop_handoff as handoff
from supervisor_harness import feedback_loop_runtime as runtime_module
from supervisor_harness import test_price_loop_handoff as handoff_fixtures
from supervisor_harness import feedback_linked_loop as loop
from experiments import nfl_ingame_price_score as scorer

t, w = handoff.t, handoff.w


def population():
    """Exact frozen geometry, fabricated identities/prices, never actual Train."""
    rows = []
    for game in range(195):
        check = game >= 108
        index = game - 108 if check else game
        day = 22 + min(19, index * 20 // 87) if check else min(21, index * 22 // 108)
        fold = f'check_{1 + (day - 22) // 5}' if check else 'initial_fit'
        forecasts, labels = (15 + (index < 51), 11 + (index < 34)) if check else (23, 23)
        for anchor in range(23):
            eligible = anchor < forecasts
            rows.append({'row_id': f'SYNTHETIC-PRIVATE-NOT-TRAIN-{game}-{anchor}',
                'game_id': f'SYNTHETIC-GAME-{game}', 'game_date': (date(2025, 9, 4) + timedelta(days=day)).isoformat(),
                'game_week': f'week-{1 + (index * 7 // 87) if check else 1 + day // 3}',
                'fold': fold, 'anchor_s': 600 + 300 * anchor, 'p_current': .5 if eligible else None,
                'label': (.1 if anchor % 2 == 0 else -.1) if eligible and anchor < labels else None,
                'forecastable': eligible})
    return rows


def write_result(output, rows, columns, candidate_id, *, source='fixture-commit'):
    """Saved native artifacts, no trainer or candidate execution."""
    output.mkdir(parents=True)
    checks = [r for r in rows if r['fold'].startswith('check_') and r['forecastable']]
    predictions = {name: {row['row_id']: value for row in checks} for name, value in columns.items()}
    card = scorer.score(rows, predictions, seed=314159)
    card.update(task_id=handoff.TASK, candidate_id=candidate_id, source_commit=source, model_fits=4,
        historical_event_clock_only=True, provider_cost_usd='0', external_fetch=False, paid_provider=False,
        route_dev_opened=False, sealed_final_opened=False, promotion_authorized=False, prices_executable=False)
    exclusions = [{k: row[k] for k in ('row_id', 'game_id', 'game_date')} for row in rows
                  if not row['forecastable'] or row['label'] is None]
    with (output / 'predictions.csv').open('x', newline='') as stream:
        fields = ['row_id', 'game_id', 'game_date', 'game_week', 'fold', 'anchor_s', 'p_current', 'label', *columns]
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for row in checks:
            writer.writerow({**{key: row[key] for key in fields if key not in columns}, **columns})
    for name, obj in {'scorecard': card, 'exclusions': exclusions,
                      'pre_score_lock': {'synthetic': True, 'seed': 314159},
                      'input_receipts': {'synthetic': True, 'population_rows': rows}}.items():
        w.save(output / (name + '.json'), obj)
    manifest = {'schema': 'market_trade_price_manifest_v1', 'task_id': handoff.TASK,
        'complete': True, 'model_fits': 4, 'mode': 'ordinary' if candidate_id == 'B1-FixedHGBRegressor' else 'candidate',
        'source_commit': source, 'population_games': 195, 'historical_train_discovery_only': True,
        'provider_cost_usd': '0'}
    for name in ('pre_score_lock', 'input_receipts', 'exclusions', 'predictions', 'scorecard'):
        manifest[name + '_sha256'] = w.sha(output / (name + ('.csv' if name == 'predictions' else '.json')))
    w.save(output / 'manifest.json', manifest)
    w.save(output / 'fit_progress.json', {'fit_calls_entered': 4, 'fit_calls_completed': 4})
    return runtime_module.pin(output / 'manifest.json')


class PriceServiceTests(TestCase):
    def setUp(self):
        self.h = handoff_fixtures.HandoffTests(); self.h.setUp(); self.addCleanup(self.h.doCleanups)
        self.root, self.runtime = self.h.root, self.h.runtime
        self.rows = population()
        self.reference = write_result(self.root / 'ordinary', self.rows,
            {'B0-NoPriceChange': 0., 'B1-FixedHGBRegressor': .2}, 'B1-FixedHGBRegressor')
        parent = deepcopy(self.h.spec['archived_parents'][0])
        parent['candidate_id'] = 'B1-FixedHGBRegressor'
        self.baseline_review = self.h.f.write('baseline-review', {'passed': True, 'synthetic': True,
            'authorization_sha256': parent['authority_snapshot_sha256'], **{key: parent[key] for key in
                ('source_batch_id', 'source_attempt_id', 'question_digest_sha256', 'evidence_bundle_sha256',
                 'research_credit', 'research_outcome', 'route_action')}})
        parent.update(archive_manifest_sha256=self.reference['sha256'],
            independent_review_sha256=self.baseline_review['sha256'])
        baseline_parent = {**parent, 'candidate_id': 'B0-NoPriceChange',
            'candidate_sha256': self.h.spec['initial_incumbent']['candidate_sha256']}
        self.seed = {'feedback': self.h.f.write('service-feedback', {'schema': 'price_task_verified_aggregate_feedback_v1',
                'comparison_incumbent_sha256': self.h.spec['initial_incumbent']['candidate_sha256'],
                'candidate_id': 'B1-FixedHGBRegressor', 'independently_reviewed': True,
                'finding': 'Fixed HGB was worse than no-price-change.', 'task_id': handoff.TASK}),
            'memory': self.h.memory, 'history': self.h.f.write('service-history', {'synthetic': True, 'results': []}),
            'source_context': self.h.f.write('service-source-context', {'candidate_api': 'past-only arrays; synthetic fixture'}),
            'pool': self.h.f.write('service-pool', {'incumbent': self.h.spec['initial_incumbent'],
                'active_pool': [
                    {'parent_sha256': parent['candidate_sha256'], 'method_family': 'ordinary', 'reason': 'distinct negative followup'},
                    {'parent_sha256': self.h.spec['initial_incumbent']['candidate_sha256'], 'method_family': 'zero-change', 'reason': 'incumbent'}], 'archive': [
                    {'candidate_id': 'B0-NoPriceChange', 'candidate_sha256': self.h.spec['initial_incumbent']['candidate_sha256'],
                     'manifest': self.reference, 'model_column': 'B0-NoPriceChange', 'review': self.baseline_review, 'native_parent': baseline_parent},
                    {'candidate_id': 'B1-FixedHGBRegressor', 'candidate_sha256': parent['candidate_sha256'],
                     'manifest': self.reference, 'model_column': 'B1-FixedHGBRegressor', 'review': self.baseline_review, 'native_parent': parent}]})}
        excluded = {'native_name', 'attempt_id', 'candidate_binding', 'source_commit', 'files', 'memory_binding',
                    'method_family', 'initial_incumbent', 'archived_parents'}
        self.base = {key: value for key, value in self.h.spec.items() if key not in excluded}
        self.base['ordinary_reference_binding'] = self.reference
        self.calls_before = self.h.f.calls
        self.choice_packets, self.authored, self.reviews = [], [], []
        self.first_prediction = .2
        self.fail_first_child = False
        self.h.f.response = self.response
        self.callback_binding = runtime_module.pin(Path(__file__).resolve())

    def response(self, packet):
        self.choice_packets.append(deepcopy(packet))
        response = self.h.f.f.decision(packet)
        feedback = packet['feedback']
        prior = feedback.get('candidate_id', 'B1-FixedHGBRegressor')
        first = prior == 'B1-FixedHGBRegressor'
        failed = feedback.get('execution_outcome') == 'failed'
        index = len(self.choice_packets)
        if first:
            amplitude, direction = self.first_prediction, 'initial-correction'
            finding = 'Reviewed ordinary baseline was worse than zero-change.'
            consequence = 'Try a bounded correction using the existing information.'
        elif failed:
            amplitude, direction = .03, 'bounded-source-repair'
            finding = 'Previous child failed without valid prediction evidence.'
            consequence = 'Retain failed code; try a separate repair from reviewed B1 without scientific refutation.'
        else:
            previous_amplitude = float(packet['source_context']['candidate_source'].strip().rsplit(' ', 1)[1])
            current = feedback['equal_game_mse'][prior]
            best_other = min(value for model, value in feedback['equal_game_mse'].items() if model != prior)
            if feedback['decision'] == 'KEEP' and current < best_other:
                amplitude, direction = previous_amplitude * 10, 'probe-supported-correction'
                finding = f'Verified KEEP: candidate MSE {current:g} below earlier comparator {best_other:g}.'
                consequence = 'Probe stronger correction in a distinct branch; do not presume its improvement.'
            elif feedback['decision'] == 'REVERT' and current >= best_other - 1e-12:
                amplitude, direction = previous_amplitude * .2, 'shrink-harmful-correction'
                finding = f'Verified REVERT: candidate MSE {current:g} does not improve comparator {best_other:g}.'
                consequence = 'Reduce the preceding source correction amplitude to test overcorrection.'
            else:
                raise ValueError('Synthetic policy requires consistent verified decision and numeric evidence')
        response.update(candidate_id=f'C{index}-synthetic-' + ('negative' if first else 'repair' if failed else 'shrink' if index == 2 else 'finer-shrink'),
            question_id=f'synthetic-{direction}-{index}', recipe=f'synthetic amplitude {amplitude:g}',
            actual_parent_sha256=self.h.spec['archived_parents'][0]['candidate_sha256'] if first or failed else self.authored[-1]['candidate_binding']['sha256'],
            hypothesis=consequence,
            comparison_incumbent_sha256=feedback['comparison_incumbent_sha256'])
        response['evidence_used'] = [{'sha256': packet['bindings']['feedback']['sha256'],
            'finding': finding, 'choice_consequence': consequence}]
        response['active_pool'] = [{'parent_sha256': response['actual_parent_sha256'], 'method_family': 'correction', 'reason': 'specific next question'},
            {'parent_sha256': self.h.spec['initial_incumbent']['candidate_sha256'], 'method_family': 'zero-change', 'reason': 'incumbent separate'}]
        change = {name: 'REUSE; synthetic fixture does not claim R/H evolution' for name in t.CHANGE['required']}
        return {'schema': 'controller_coevolution_proposal_v1', 'input_sha256': t.c._digest(packet),
            'feedback_sha256': packet['bindings']['feedback']['sha256'], 'requested_model': t.c.MODEL,
            'serving_snapshot': 'unknown', 'researcher_change': change, 'harness_change': change,
            'candidate': response, 'attribution': 'synthetic transport; no actual model or Trainer'}

    def author(self, context):
        response = context['outputs']['controller']['decision']['candidate']
        path = self.h.runner.with_name(response['candidate_id'].replace('-', '_') + '.py')
        path.write_text("raise AssertionError('synthetic source is never imported')\n# " + response['recipe'] + '\n')
        result = {'candidate_binding': runtime_module.pin(path), 'source_commit': 'fixture-commit',
            'files': {str(file.relative_to(self.h.repo)): w.sha(file) for file in (self.h.runner, path)},
            'method_family': 'synthetic-correction'}
        self.authored.append(result)
        return result

    def child(self, *args, **kwargs):
        command = args[0]; output = Path(command[command.index('--output') + 1])
        operation = t._file(output.parent.parent / (output.name + '.price_operation.json'))
        name = operation['candidate_id']
        # Never derive forecasts from candidate ordinal: parse reviewed source
        # recipe without executing it, so fixture proposal/source/prediction agree.
        value = float(Path(operation['candidate']['path']).read_text().strip().rsplit(' ', 1)[1])
        if self.fail_first_child and name.startswith('C1'):
            output.mkdir(parents=True)
            w.save(output / 'fit_progress.json', {'fit_calls_entered': 0, 'fit_calls_completed': 0})
            return Mock(pid=1234, wait=Mock(return_value=1), poll=Mock(return_value=1))
        write_result(output, self.rows, {'B0-NoPriceChange': 0., 'B1-FixedHGBRegressor': .2, name: value}, name)
        return Mock(pid=1234, wait=Mock(return_value=0), poll=Mock(return_value=0))

    def service(self):
        return services.PriceLoopServices(self.runtime, self.base, author=self.author, reviewer=self.reviewer,
            callback_sources={'author': self.callback_binding, 'reviewer': self.callback_binding})

    def reviewer(self, stage, material):
        self.reviews.append((stage, deepcopy(material)))
        if stage == 'input':
            review = {'passed': True, 'authorization_sha256': self.runtime.authority['sha256'],
                'input_sha256': material['input']['sha256'], 'transaction_source_sha256': w.sha(t.__file__),
                'consumer_source_sha256': w.sha(t.c.__file__), 'cli_sha256': t.c.CLI_SHA,
                'requested_model': t.c.MODEL, 'configuration_sha256': self.runtime.configuration['sha256'],
                'source_commit': 'fixture-commit'}
        elif stage == 'source':
            core = t.c._read(material['operation_core'])
            review = {'passed': True, 'authorization_sha256': self.runtime.authority['sha256'],
                'request_sha256': material['request']['sha256'], 'execution_source_sha256': w.sha(runtime_module.__file__),
                'operation_core_sha256': handoff.operation_commitment(core)}
        elif stage == 'result':
            comparison = t.c._read(material['comparison']) if material['comparison'] else None
            keep = comparison is not None and comparison['decision'] == 'KEEP'
            review = {key: material[key] for key in ('candidate_sha256', 'execution_outcome', 'manifest', 'comparison',
                'question_digest_sha256', 'source_batch_id', 'source_attempt_id')}
            review['evidence_bundle_sha256'] = material['comparison']['sha256'] if material['comparison'] else None
            review.update(passed=True, authorization_sha256=self.runtime.authority['sha256'],
                research_credit=2 if comparison else 0,
                research_outcome=('support' if keep else 'refute') if comparison else 'invalid',
                route_action=('continue' if keep else 'branch') if comparison else 'stop',
                finding=('Synthetic correction improves the fixed incumbent.' if keep else 'Correction worsens zero-change; preserve exact negative evidence and branch.')
                    if comparison else 'Synthetic execution failed; no performance evidence.')
        else:
            raise AssertionError('Unknown reviewer stage')
        return self.h.f.write(f'service-review-{stage}-{len(self.reviews)}', review)

    def run_service(self, rounds=2):
        with patch.object(runtime_module, 'ContinuousDiscoveryBatch', side_effect=self.h.batch), \
             patch.object(w, 'datetime', handoff_fixtures.Clock), \
             patch.object(w, 'sample_rss', return_value=128), \
             patch.object(w.subprocess, 'Popen', side_effect=self.child) as child:
            result = self.service().run(self.seed, max_rounds=rounds)
            return result, child.call_count

    def test_two_rounds_actual_boundary_paths_feedback_revert_parent_and_restart(self):
        result, launches = self.run_service()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['completed_rounds'], 2)
        self.assertEqual(launches, 2)  # Synthetic children, actual native handoff/claim code.
        self.assertEqual(self.h.f.calls - self.calls_before, 2)
        self.assertEqual([p['feedback']['candidate_id'] for p in self.choice_packets],
            ['B1-FixedHGBRegressor', 'C1-synthetic-negative'])
        second = self.choice_packets[1]
        self.assertEqual(second['memory']['verified_finding']['candidate_id'], 'C1-synthetic-negative')
        self.assertEqual(second['memory']['verified_finding']['decision'], 'REVERT')
        self.assertIn(self.authored[0]['candidate_binding']['sha256'], second['provided_parents'])
        pool = t.c._read(result['result']['pool'])
        self.assertEqual(pool['incumbent']['candidate_id'], 'B0-NoPriceChange')
        self.assertEqual([r['candidate_id'] for r in pool['archive']],
            ['B0-NoPriceChange', 'B1-FixedHGBRegressor', 'C1-synthetic-negative', 'C2-synthetic-shrink'])
        negative = pool['archive'][-2]
        self.assertEqual(negative['native_parent']['route_action'], 'branch')
        ledger = t._file(self.root / 'ledger.json')
        self.assertEqual([a['status'] for a in ledger['attempts']], ['succeeded', 'succeeded'])
        self.assertEqual(sum(a['fits_reserved'] for a in ledger['attempts']), 8)
        # Counts reflect deliberately fabricated child progress, not actual ML fits.
        first, second_attempt = ledger['attempts']
        self.assertEqual(second_attempt['research_parent_sha256'], negative['candidate_sha256'])
        for attempt in ledger['attempts']:
            comparison_path = self.root / ('price-round-' + ('0001' if attempt == first else '0002') + '-comparison.json')
            comparison = t._file(comparison_path)
            self.assertEqual(comparison['coverage']['full_population']['population_games'], 195)
            self.assertEqual(comparison['coverage']['full_population']['population_rows'], 4485)
            self.assertEqual(comparison['coverage']['checks']['forecastable_rows'], 1356)
            self.assertEqual(comparison['coverage']['checks']['scorable_rows'], 991)
            self.assertEqual(len(comparison['per_fold']), 4)
            self.assertEqual(comparison['decision'], 'REVERT')
        snapshot = deepcopy(ledger)
        replay, repeated_launches = self.run_service()
        self.assertEqual(replay, result)
        self.assertEqual(repeated_launches, 0)
        self.assertEqual(self.h.f.calls - self.calls_before, 2)
        self.assertEqual(t._file(self.root / 'ledger.json'), snapshot)

    def test_packet_is_compact_aggregate_no_raw_population_and_closed_cap_stops(self):
        result, _ = self.run_service(rounds=1)
        packet = self.choice_packets[0]
        serialized = (json.dumps(packet, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
        self.assertLess(len(serialized) + 1, 32768)
        self.assertNotIn(b'SYNTHETIC-PRIVATE-NOT-TRAIN-', serialized)
        self.assertNotIn(b'SYNTHETIC-GAME-', serialized)
        self.assertNotIn('evidence_session', packet)
        self.assertFalse(packet['authority']['account_transfer']['tools_enabled'])
        ledger = t._file(self.root / 'ledger.json'); ledger['status'] = 'closed'
        self.h.f.write('ledger', ledger)
        # Fresh driver path is not needed: read-only admission is closed for next input.
        self.assertFalse(self.runtime.admit({'stage': 'input'}))
        self.assertEqual(result['completed_rounds'], 1)

    def test_next_input_carries_actual_accounting_capabilities_and_unknown_timings(self):
        result, _ = self.run_service()
        first, second = self.choice_packets
        self.assertIsNone(first['overhead']['last_process_feedback_sha256'])
        observed = second['history']['process_feedback']
        self.assertEqual(second['overhead']['last_process_feedback_sha256'], t.c._digest(observed))
        self.assertEqual(observed['execution']['actual_fits'], 4)  # Fixture progress, not actual ML fits.
        self.assertEqual(observed['execution']['fits_reserved'], 4)
        self.assertTrue(observed['execution']['performance_evidence'])
        self.assertFalse(observed['reconcile_timing_included'])
        self.assertTrue(all(item == {'measurement': None, 'evidence': None}
                            for item in observed['stages'].values()))
        capabilities = second['overhead']['implementation_capabilities']
        self.assertIn('cumsum', capabilities['numpy_attributes'])
        self.assertIn('searchsorted', capabilities['numpy_attributes'])
        self.assertFalse(second['overhead']['capacity_hooks_resolved'])
        self.assertEqual(second['overhead']['configured_research_pair'], self.base['identity_configuration']['pair'])
        self.assertNotIn('stdout', json.dumps(observed))
        replay, launches = self.run_service()
        self.assertEqual(replay, result)
        self.assertEqual(launches, 0)

    def test_large_aggregate_context_uses_exact_controller_grant(self):
        grant = deepcopy(self.runtime.fixed_grant)
        grant['account_transfer']['max_input_bytes'] = 262144
        self.runtime.authority = self.h.f.write('authorization', grant)
        self.runtime.fixed_grant = grant
        self.seed['source_context'] = self.h.f.write('large-synthetic-source-context',
            {'source': 'synthetic context, no data rows: ' + 'x' * 40000})
        ctx = {'round_index': 1, 'previous_result': self.seed}
        packet = self.service().prepare_packet(ctx)
        size = len((json.dumps(packet, sort_keys=True, indent=2) + '\n').encode())
        self.assertGreater(size, 32768); self.assertLess(size, 262144)
        grant['account_transfer']['max_input_bytes'] = 32768
        self.runtime.authority = self.h.f.write('authorization', grant)
        self.runtime.fixed_grant = grant
        with self.assertRaisesRegex(ValueError, 'input byte budget'):
            self.service().prepare_packet(ctx)
        self.assertEqual(t._file(self.root / 'ledger.json')['attempts'], [])
        self.assertEqual(self.h.f.calls, self.calls_before)

    def test_measured_timings_are_bound_to_previous_round_and_not_recounted(self):
        path = self.root / 'price-loop' / 'round-0001-implement.timing.json'
        path.parent.mkdir()
        w.save(path, {'wall_seconds': 7.5, 'completed': True})
        self.run_service()
        previous = self.choice_packets[1]['history']['process_feedback']
        stage = previous['stages']['implement']
        self.assertEqual(stage['measurement']['wall_seconds'], 7.5)
        self.assertEqual(stage['evidence'], runtime_module.pin(path))
        self.assertIsNone(previous['stages']['controller']['measurement'])
        changed_root = deepcopy(previous); changed_root['source_batch_root'] = str(self.root / 'different-root')
        with self.assertRaises(ValueError): services._process_evidence(changed_root)
        path.write_text(json.dumps({'wall_seconds': 1., 'completed': True}))
        with self.assertRaises(ValueError): services._process_evidence(previous)

    def test_missing_and_malformed_timing_differ_and_do_not_approve_feedback(self):
        path = self.root / 'price-loop' / 'round-0001-implement.timing.json'
        path.parent.mkdir()
        w.save(path, {'wall_seconds': True, 'completed': True})
        with self.assertRaises(loop.LoopHalted): self.run_service(rounds=1)
        self.assertFalse((self.root / 'price-round-0001-history.json').exists())
        self.assertEqual(len(t._file(self.root / 'ledger.json')['attempts']), 1)
        self.assertFalse(t._file(self.root / 'price-loop/round-0001-reconcile.failed.json')['retry_allowed'])

    def test_timing_symlink_is_not_followed(self):
        path = self.root / 'price-loop' / 'round-0001-implement.timing.json'
        path.parent.mkdir()
        original = self.h.f.write('timing-target', {'wall_seconds': 2., 'completed': True})
        path.symlink_to(original['path'])
        with self.assertRaises(loop.LoopHalted): self.run_service(rounds=1)
        self.assertFalse((self.root / 'price-round-0001-history.json').exists())

    def test_reviewer_failure_preserves_closed_stage_no_duplicate_original_or_worker(self):
        original = self.reviewer
        def bad_review(stage, material):
            binding = original(stage, material)
            if stage == 'source':
                review = t.c._read(binding); review['passed'] = False
                return self.h.f.write('failed-source-review', review)
            return binding
        self.reviewer = bad_review
        with self.assertRaises(loop.LoopHalted): self.run_service(rounds=1)
        calls = self.h.f.calls
        with patch.object(w.subprocess, 'Popen') as launch, self.assertRaises(loop.LoopHalted):
            self.service().run(self.seed, max_rounds=1)
        self.assertFalse(launch.called)
        self.assertEqual(self.h.f.calls, calls)
        self.assertEqual(t._file(self.root / 'ledger.json')['attempts'], [])

    def pair_records(self):
        pool = t.c._read(self.seed['pool'])
        manifest = write_result(self.root / 'paired-candidate', self.rows,
            {'B0-NoPriceChange': 0., 'B1-FixedHGBRegressor': .2, 'C-paired-fixture': .03}, 'C-paired-fixture')
        candidate = {'candidate_id': 'C-paired-fixture', 'candidate_sha256': 'f' * 64,
            'manifest': manifest, 'model_column': 'C-paired-fixture', 'review': self.baseline_review, 'native_parent': None}
        return candidate, pool['archive'][1], pool['archive'][0], pool['archive'][1]

    def rewrite_prediction(self, record, update):
        path = Path(record['manifest']['path']).parent / 'predictions.csv'
        with path.open(newline='') as stream:
            reader = csv.DictReader(stream); fields = reader.fieldnames; values = list(reader)
        update(values)
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(values)
        manifest = t.c._read(record['manifest'])
        manifest['predictions_sha256'] = w.sha(path)
        Path(record['manifest']['path']).write_text(json.dumps(manifest))
        record['manifest'] = runtime_module.pin(record['manifest']['path'])

    def test_pair_comparison_preserves_missing_label_forecasts_and_full_coverage(self):
        records = self.pair_records()
        comparison = services.paired_comparison(*records)
        self.assertEqual(comparison['coverage']['full_population']['population_rows'], 4485)
        self.assertEqual(comparison['coverage']['checks']['forecastable_rows'], 1356)
        self.assertEqual(comparison['coverage']['checks']['scorable_rows'], 991)
        self.assertEqual(comparison['coverage']['checks']['reason_counts']['NO_FUTURE_WINDOW_LABEL'], 365)
        self.assertIn('C-paired-fixture_minus_B1-FixedHGBRegressor', comparison['paired'])
        self.assertLess(comparison['paired']['C-paired-fixture_minus_B1-FixedHGBRegressor']['equal_game_mse_delta'], 0)
        self.assertGreater(comparison['paired']['C-paired-fixture_minus_B0-NoPriceChange']['equal_game_mse_delta'], 0)
        self.assertEqual(comparison['decision'], 'REVERT')

    def test_same_prior_identity_counterfactual_evidence_changes_recipe_and_forecasts(self):
        # Controlled policy unit test: these alternate scores are fabricated
        # counterfactual observations, not independently measured market results.
        base = deepcopy(self.h.f.packet)
        base['source_context'] = {'candidate_source': "raise AssertionError('never import')\n# synthetic amplitude .003\n"}
        self.authored.append({'candidate_binding': self.h.spec['candidate_binding']})
        responses = []
        for decision, mse in (('REVERT', .02), ('KEEP', .008)):
            packet = deepcopy(base)
            packet['feedback'] = {'candidate_id': 'SAME-PRIOR-CANDIDATE', 'decision': decision,
                'execution_outcome': 'succeeded', 'comparison_incumbent_sha256': self.h.spec['initial_incumbent']['candidate_sha256'],
                'equal_game_mse': {'SAME-PRIOR-CANDIDATE': mse, 'B0-NoPriceChange': .01},
                'synthetic_counterfactual': True}
            packet['bindings']['feedback'] = self.h.f.write('counterfactual-' + decision, packet['feedback'])
            responses.append(self.response(packet))
        negative, positive = (response['candidate'] for response in responses)
        self.assertEqual(negative['actual_parent_sha256'], positive['actual_parent_sha256'])
        self.assertNotEqual(negative['recipe'], positive['recipe'])
        self.assertIn('REVERT', negative['evidence_used'][0]['finding'])
        self.assertIn('KEEP', positive['evidence_used'][0]['finding'])
        self.assertIn('Reduce', negative['evidence_used'][0]['choice_consequence'])
        self.assertIn('Probe', positive['evidence_used'][0]['choice_consequence'])
        for index, (response, expected) in enumerate(zip(responses, (.0006, .03)), 1):
            authored = self.author({'outputs': {'controller': {'decision': response}}})
            native = self.root / f'counterfactual-native-{index}'; native.mkdir()
            attempt = f'counterfactual-{index}'; output = native / 'runs' / attempt
            w.save(native / (attempt + '.price_operation.json'), {
                'candidate_id': response['candidate']['candidate_id'], 'candidate': authored['candidate_binding']})
            self.child(['synthetic-not-executed', '--output', str(output)])
            with (output / 'predictions.csv').open(newline='') as stream:
                predictions = list(csv.DictReader(stream))
            self.assertEqual({float(row[response['candidate']['candidate_id']]) for row in predictions}, {expected})

    def test_pair_missing_label_row_cannot_be_silently_dropped(self):
        records = self.pair_records()
        def drop_missing(rows):
            row = next(row for row in rows if row['label'] == '')
            rows.remove(row)
        self.rewrite_prediction(records[0], drop_missing)
        with self.assertRaisesRegex(ValueError, 'row, label, clock or source drift'):
            services.paired_comparison(*records)

    def test_pair_label_clock_and_duplicate_row_drift_are_rejected(self):
        records = self.pair_records()
        self.rewrite_prediction(records[0], lambda rows: rows[0].update(anchor_s='601'))
        with self.assertRaisesRegex(ValueError, 'clock or source drift'):
            services.paired_comparison(*records)
        self.rewrite_prediction(records[0], lambda rows: rows.append(deepcopy(rows[0])))
        with self.assertRaisesRegex(ValueError, 'duplicate saved prediction IDs'):
            services.paired_comparison(*records)

    def test_saved_manifest_hash_drift_rejected(self):
        records = self.pair_records()
        path = Path(records[0]['manifest']['path']).parent / 'predictions.csv'
        with path.open('a') as stream: stream.write('\n')
        with self.assertRaisesRegex(ValueError, 'bound file drift'):
            services.paired_comparison(*records)

    def test_oversized_input_and_closed_ledger_stop_before_original_transport(self):
        self.seed['source_context'] = self.h.f.write('oversized-source-context', {'source': 'x' * 32768})
        calls = self.h.f.calls
        with self.assertRaises(loop.LoopHalted): self.run_service(rounds=1)
        self.assertEqual(self.h.f.calls, calls)
        self.assertFalse((self.root / 'price-round-0001-input.json').exists())
        self.assertEqual(t._file(self.root / 'ledger.json')['attempts'], [])

    def test_callback_binding_must_identify_actual_service_source(self):
        wrong = self.h.f.write('wrong-callback', {'not': 'callback source'})
        with self.assertRaisesRegex(ValueError, 'actual trusted service'):
            services.PriceLoopServices(self.runtime, self.base, author=self.author, reviewer=self.reviewer,
                callback_sources={'author': wrong, 'reviewer': self.callback_binding})

    def test_missing_active_continuation_provenance_rejected_before_original(self):
        pool = t.c._read(self.seed['pool'])
        pool['archive'][0]['native_parent'] = None
        self.seed['pool'] = self.h.f.write('missing-baseline-provenance', pool)
        calls = self.h.f.calls
        with self.assertRaises(loop.LoopHalted): self.run_service(rounds=1)
        self.assertEqual(self.h.f.calls, calls)
        self.assertEqual(t._file(self.root / 'ledger.json')['attempts'], [])

    def test_result_research_credit_binds_actual_question(self):
        original = self.reviewer
        def different_question(stage, material):
            binding = original(stage, material)
            if stage == 'result':
                review = t.c._read(binding); review['question_digest_sha256'] = 'e' * 64
                return self.h.f.write('wrong-result-question', review)
            return binding
        self.reviewer = different_question
        with self.assertRaises(loop.LoopHalted): self.run_service(rounds=1)
        self.assertFalse((self.root / 'price-round-0001-feedback.json').exists())
        self.assertEqual(self.h.f.calls - self.calls_before, 1)
        self.assertEqual(len(t._file(self.root / 'ledger.json')['attempts']), 1)

    def test_keep_then_feedback_continuation_preserves_baseline_and_new_incumbent(self):
        self.first_prediction = .003  # Fabricated predictor, not a fitted model.
        result, launches = self.run_service()
        self.assertEqual(result['completed_rounds'], 2)
        self.assertEqual(launches, 2)
        first_feedback, second_feedback = (packet['feedback'] for packet in self.choice_packets)
        self.assertEqual(second_feedback['decision'], 'KEEP')
        self.assertEqual(second_feedback['previous_comparator_sha256'], first_feedback['comparison_incumbent_sha256'])
        pool = t.c._read(result['result']['pool'])
        self.assertEqual(pool['incumbent']['candidate_id'], 'C1-synthetic-negative')
        self.assertEqual(t.c._read(result['result']['feedback'])['decision'], 'REVERT')
        self.assertIn(self.h.spec['initial_incumbent']['candidate_sha256'], self.choice_packets[1]['provided_parents'])
        self.assertEqual(t._file(self.root / 'ledger.json')['attempts'][1]['research_parent_sha256'],
            self.authored[0]['candidate_binding']['sha256'])

    def test_three_round_keep_revert_keep_and_cap_closed_replay(self):
        # A fresh synthetic grant has three originals. Preserve the unrelated
        # fixture original's ledger, rather than resetting or refunding it.
        old_ledger = t._file(self.root / 'ledger.json')
        temporary = TemporaryDirectory(prefix='price-three-round-', dir=self.root.parent)
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        config = deepcopy(self.runtime.config)
        config.update(batch_id=root.name, root=str(root))
        grant = deepcopy(self.runtime.fixed_grant); grant['batch_id'] = root.name
        w.save(root / 'configuration.json', config); w.save(root / 'authorization.json', grant)
        authority = runtime_module.pin(root / 'authorization.json')
        w.save(root / 'ledger.json', {'schema': 'market_rsi_coevo_pilot_ledger_v1', 'batch_id': root.name,
            'authorization_sha256': authority['sha256'], 'controller_decisions': [], 'attempts': [], 'status': 'open'})
        previous_root = self.root
        self.root = root
        self.runtime = runtime_module.PilotRuntime(root, self.h.repo, authority, runtime_module.pin(root / 'configuration.json'))
        self.base['identity_configuration']['fixed_context'].update(authority_sha256=authority['sha256'],
            resource_policy_sha256=self.runtime.configuration['sha256'])
        self.first_prediction = .003
        result, launches = self.run_service(rounds=3)
        self.assertEqual(result['completed_rounds'], 3)
        self.assertEqual(launches, 3)
        self.assertEqual([t._file(root / f'price-round-{i:04d}-comparison.json')['decision'] for i in (1, 2, 3)],
            ['KEEP', 'REVERT', 'KEEP'])
        pool = t.c._read(result['result']['pool'])
        self.assertEqual(pool['incumbent']['candidate_id'], 'C3-synthetic-finer-shrink')
        ledger = t._file(root / 'ledger.json')
        self.assertEqual(ledger['status'], 'closed_at_attempt_cap')
        self.assertEqual(len(ledger['controller_decisions']), 3)
        self.assertEqual(sum(attempt['fits_reserved'] for attempt in ledger['attempts']), 12)
        self.assertEqual(t._file(previous_root / 'ledger.json'), old_ledger)
        replay, launches = self.run_service(rounds=3)
        self.assertEqual(replay, result)
        self.assertEqual(launches, 0)
        self.assertEqual(t._file(root / 'ledger.json'), ledger)

    def test_failed_child_evidence_retained_without_scientific_refutation_then_continues(self):
        self.fail_first_child = True
        result, launches = self.run_service()
        self.assertEqual(result['completed_rounds'], 2)
        self.assertEqual(launches, 2)
        first_result = self.choice_packets[1]['feedback']
        self.assertEqual(first_result['execution_outcome'], 'failed')
        self.assertEqual(first_result['decision'], 'UNCHANGED')
        self.assertEqual(first_result['research_credit'], 0)
        self.assertIsNone(first_result['comparison'])
        self.assertFalse(first_result['exploration_eligible'])
        self.assertNotIn('equal_game_mse', first_result)
        process = self.choice_packets[1]['history']['process_feedback']
        self.assertEqual(process['execution']['outcome'], 'failed')
        self.assertEqual(process['execution']['actual_fits'], 0)
        self.assertFalse(process['execution']['performance_evidence'])
        pool = t.c._read(result['result']['pool'])
        failed_record = next(record for record in pool['archive'] if record['candidate_id'] == 'C1-synthetic-negative')
        self.assertIsNone(failed_record['manifest'])
        self.assertIsNone(failed_record['native_parent'])
        self.assertEqual(failed_record['candidate_sha256'], self.authored[0]['candidate_binding']['sha256'])
        self.assertTrue(Path(self.authored[0]['candidate_binding']['path']).exists())
        self.assertNotIn(failed_record['candidate_sha256'], self.choice_packets[1]['provided_parents'])
        ledger = t._file(self.root / 'ledger.json')
        self.assertEqual([attempt['status'] for attempt in ledger['attempts']], ['failed', 'succeeded'])
        self.assertEqual(sum(attempt['fits_reserved'] for attempt in ledger['attempts']), 8)
        self.assertEqual(ledger['attempts'][0]['actual_fits'], 0)
        self.assertEqual(self.h.f.calls - self.calls_before, 2)


if __name__ == '__main__': main()
