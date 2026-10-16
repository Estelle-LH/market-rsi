"""Candidate-bound local mechanism probes, with deliberately narrow meanings."""
from copy import deepcopy
from pathlib import Path
import shutil

from earnings_capacity_adapter import EarningsCapacity, profile
from earnings_capacity_worker import CapacityWorker
from earnings_effect_review import SCOPES
from earnings_feedback import project_feedback
from earnings_shadow_measurement import compare
from earnings_native_namespace import probe_paths
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


class MechanicalProbes:
    def __init__(self, task):
        self.task = task

    def run(self, capacity, comparison_binding, output_root):
        """No inference or real transition; every probe original stays on disk."""
        before = capacity.batch.snapshot()
        micro, pending = before['micro_evolution'], before['micro_evolution']['pending']
        if pending is None or before['active_attempt_ids']:
            raise ValueError('Exact idle pending candidate required for probes')
        measured = engine.read(comparison_binding)
        trial = engine.read(measured['trial_claim'])
        engine.driver._artifacts(measured)
        engine.driver._artifacts(trial)
        parent = capacity._selected(before)['manifest']
        child = capacity._version(pending['pair'])['manifest']
        binding = {'proposal_sha256': pending['record_sha256'],
            'before_identity_sha256': digest(parent), 'after_identity_sha256': digest(child),
            'tested_pair_sha256': digest(pending['pair']), 'anchor_pair_sha256': digest(micro['anchor_pair'])}
        if (trial['pending_proposal_sha256'] != pending['record_sha256']
                or trial['initial_state']['sha256'] != measured['originals']['child']['consumed']['state_sha256']
                or self.task.kernel != trial['kernel'] or self.task.state_api.task_id != trial['episode']['id']
                or digest(engine.read(trial['criterion'])) != digest(measured['declaration'])
                or trial['before_identity_sha256'] != digest(parent) or trial['after_identity_sha256'] != digest(child)):
            raise ValueError('Probe task/trial does not bind this pending candidate')
        works = {row['work_id']: row for row in before.get('capacity_work', [])}
        if len(measured['work_ids']) != 2 or len(set(measured['work_ids'])) != 2:
            raise ValueError('Exact two distinct completed trial work IDs required')
        for arm, work_id in zip(('parent', 'child'), measured['work_ids']):
            original = engine.pin(Path(comparison_binding['path']).parent/(arm+'.json'))
            row = works.get(work_id)
            if (engine.read(original) != measured['originals'][arm] or row is None
                    or row['status'] != 'completed' or row['pair_sha256'] != digest(micro['active_pair'])
                    or row['output_evidence_sha256'] != original['sha256']):
                raise ValueError('Native trial completion does not bind exact retained arm originals')
        resources, identities = [], []
        good_resources = True
        for arm in ('parent', 'child'):
            slot = Path(measured['originals'][arm]['result']['path']).parent
            originals = {b['path']: b for b in measured['originals'][arm]['artifacts']}
            identity = originals[str(slot/'identity.json')]; budget = originals[str(slot/'budget-summary.json')]
            identities.append(engine.read(identity)); engine.read(budget); resources.extend([identity, budget])
            engine.driver._artifacts(identities[-1])
            context = engine.read(identities[-1]['context']); study = engine.read(identities[-1]['study'])
            config = study['runtime_config']
            good_resources &= identities[-1]['kernel'] == self.task.kernel and context['limits'] == {
                'max_input_tokens': config['max_input_tokens'],
                'max_output_tokens': max(config['max_output_tokens'], config.get('final_max_output_tokens', 0)),
                'wall_seconds': config['company_wall_seconds']} and context['rates'] == config['models'][study['model']['requested_model']]
        root = Path(output_root)
        if (not root.is_absolute() or root.resolve() != root or root.exists()
                or not root.is_relative_to(Path(trial['episode']['root'])/'effects')):
            raise ValueError('New canonical owned probe root required')
        scratch = probe_paths(capacity, root)
        root.mkdir(parents=True, exist_ok=False)
        observations = {}
        def record(name, facts, originals):
            receipt = engine.save(root/(name+'.json'), {'scope': SCOPES[name],
                'binding': binding, 'facts': facts, 'originals': originals})
            observations[name] = {'facts': facts, 'artifacts': [receipt, *originals]}
        snapshot = engine.save(root/'native-before.json', before)
        again = compare(measured['originals']['parent'], measured['originals']['child'],
                        declaration=measured['declaration'])
        consumption = measured['originals']['child']['consumed']
        record('success_replay', {'originals_recomputed': all(measured.get(k) == v for k, v in again.items()),
            'tested_consumption': consumption['tested_pair_sha256'] == binding['tested_pair_sha256']},
            [comparison_binding, measured['trial_claim']])

        # Copy only the owned small native journal and version registry. A cold
        # object may repair the scratch snapshot; it never repairs the real one.
        scratch['native_root'].mkdir(parents=True, exist_ok=False)
        scratch_binding = engine.save(root/'native-scratch.json', {k: str(v) for k, v in scratch.items()})
        shutil.copytree(capacity.batch.root, scratch['batch_root'], symlinks=True)
        shutil.copytree(capacity.registry, scratch['registry_root'], symlinks=True)
        options = {'allow_temporary': True}
        if capacity.batch._clock is not None:
            options.update(test_clock=capacity.batch._clock, allow_test_clock=True)
        batch = type(capacity.batch)(scratch['batch_root'], **options)
        from earnings_open_capacity import ProgramCapacity
        program_route = type(capacity) is ProgramCapacity
        capacity_type = ProgramCapacity if program_route else EarningsCapacity
        cold = capacity_type(batch, source_root=capacity.source_root, registry_root=scratch['registry_root'],
            baseline=capacity.baseline, entrypoints=capacity.initial_entrypoints)
        restored = engine.save(root/'native-cold.json', batch.snapshot())
        state = self.task.load_state(trial['initial_state'])
        factory = getattr(self.task, 'make_worker', None)
        options = {'shadow_proposal_sha256':pending['record_sha256']}
        worker = (factory(trial['episode']['id'], cold, digest(micro['active_pair']),
                root/'cold-memory', trial['initial_state'], **options)
            if callable(factory) else CapacityWorker(self.task.company, trial['episode']['id'], cold,
                digest(micro['active_pair']), root/'cold-memory', trial['initial_state'], **options))
        effective = engine.read(engine.pin(Path(measured['originals']['child']['result']['path']).parent/'effective-capacity.json'))
        record('restart', {'cold_identity_equal': worker.context == effective['context'],
            'cold_state_equal': worker.state == state and batch.snapshot() == before}, [snapshot, restored, scratch_binding, worker.state_binding])
        def journal_tokens(location):
            return {p.name: engine.pin(p)['sha256'] for p in sorted((location/'journal').iterdir())}
        historical = engine.save(root/'journal-comparison.json', {
            'original': journal_tokens(capacity.batch.root), 'cold': journal_tokens(batch.root)})
        final = self.task.load_state(measured['originals']['child']['state'])
        record('historical_replay', {'journal_equal': engine.read(historical)['original'] == engine.read(historical)['cold'],
            'prior_records_preserved': final['records'][:len(state['records'])] == state['records']},
            [historical, snapshot, restored, trial['initial_state'], measured['originals']['child']['state']])

        denied = False
        error_type = None
        try:
            worker.dispatch('read_file', {'path': '__not_a_public_filing__', 'offset': 0, 'characters': 256})
        except (ValueError, KeyError) as error:
            denied, error_type = True, type(error).__name__
        feedback = project_feedback({'status': 'FAILED_NO_RETRY', 'planned_targets': 5,
            'scored_targets': 0, 'error_type': error_type}, None,
            task_id=trial['episode']['id'], cik=self.task.company['cik']) if denied else None
        failure = engine.save(root/'tool-denial.json', {'denied': denied, 'error_type': error_type, 'feedback': feedback})
        record('failure_feedback', {'tool_denied': denied,
            'feedback_safe': feedback is not None and feedback['execution']['error_type'] == error_type}, [failure])

        axis = engine.identity.change_axis(parent, child)
        changed = {name for name in set(parent['components'][axis]['sources']) | set(child['components'][axis]['sources'])
            if parent['components'][axis]['sources'].get(name) != child['components'][axis]['sources'].get(name)}
        record('protected_boundaries', {
            'fixed_context': all(parent[k] == child[k] for k in ('K', 'M', 'C', 'memory_sha256', 'runtime_sha256')),
            'single_axis': axis in {'R', 'H'}, 'actual_write_scope': changed == set(pending['write_paths'])},
            [snapshot, engine.pin(capacity.registry/(digest(pending['pair'])+'.json'))])
        projected = deepcopy(micro)
        projected.update(active_pair=deepcopy(pending['pair']), previous_pair=deepcopy(micro['active_pair']), pending=None)
        projected.pop('record_sha256')
        projected = engine.activation.micro._seal(projected)
        rolled = engine.activation.micro.rollback_micro_evolution(projected, {
            'reviewer_id': micro['reviewer_id'], 'reason': 'Conditional pure pre-adoption rollback probe',
            'evidence_sha256': comparison_binding['sha256']})
        rollback = engine.save(root/'conditional-rollback.json', {'conditional': True,
            'production_adoption': False, 'before': projected, 'after': rolled})
        record('rollback', {'conditional_projection': projected['active_pair'] == pending['pair'],
            'parent_restored': rolled['active_pair'] == micro['active_pair'] and len(rolled['history']) == len(micro['history'])+1,
            'real_state_unchanged': capacity.batch.snapshot() == before}, [rollback, snapshot])

        anchor = capacity._version(micro['anchor_pair'])
        from earnings_open_program import program
        parser = program if program_route else profile
        anchor_profiles = {a: parser(engine.activation._read({'path': str(capacity.source_root/n),
            'sha256': anchor['manifest']['components'][a]['sources'][n]}), a) for a, n in anchor['entrypoints'].items()}
        anchor_receipt = engine.save(root/'anchor-interfaces.json', anchor_profiles)
        interface_ok = (set(t['name'] for t in worker.program_definitions()) >=
            {'read_file','search_files','calculate','save_research_record'}) if program_route else True
        record('anchor_compatibility', {'anchor_files_verified': engine.activation.pair(anchor['manifest']) == micro['anchor_pair'],
            'interfaces_compatible': interface_ok and all(set(anchor_profiles[a]) == set(cold.resolve(a,
                expected_pair_sha256=digest(micro['active_pair']), shadow_proposal_sha256=pending['record_sha256'])['profile']) for a in ('R','H'))}, [anchor_receipt])
        record('bounded_trial', {'original_resources': bool(good_resources and identities[0]['clock'] == identities[1]['clock']),
            'completed_claims': len(measured['work_ids']) == 2 and all(works[w]['status'] == 'completed'
                and works[w]['pair_sha256'] == digest(micro['active_pair']) for w in measured['work_ids']),
            'declared_slots': trial['slots'] == [str(Path(measured['originals'][a]['result']['path']).parent) for a in ('parent','child')]}, resources)
        if capacity.batch.snapshot() != before:
            raise ValueError('Mechanical probes changed the real native state')
        return engine.save(root/'observations.json', {'schema': 'earnings_mechanical_checks_v1',
            'binding': binding, 'scopes': SCOPES, 'observations': observations,
            'sources': {'producer': engine.source_of(self.run), 'task': self.task.sources()},
            'native_state_sha256': before['state_sha256']})
