"""Matched pending policy evaluation; returns review data, never adopts it."""
from pathlib import Path

from earnings_capacity_checks import MechanicalProbes
from earnings_effect_review import effect_criterion, review, SCOPES
from earnings_shadow_trial import run_matched
from earnings_round_plan import round_count, declared_slots
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


class PendingEvolution:
    def __init__(self, envelope_binding, capacity, task, forecast, *, plan_binding, registration_binding):
        self.envelope_binding, self.plan_binding = envelope_binding, plan_binding
        self.registration_binding, self.capacity = registration_binding, capacity
        self.task, self.forecast = task, forecast
        self.envelope, self.plan = engine.read(envelope_binding), engine.read(plan_binding)
        self.probes = MechanicalProbes(task)
        plan = self.plan
        plan_bound = self.envelope.get('schema') in {'earnings_capacity_episode_v2', 'earnings_capacity_episode_v3'}
        if plan_bound:
            round_count(self.envelope, legacy_ceiling=2)
        if (type(plan) is not dict or set(plan) != {'schema', 'episode', 'rounds'}
                or plan['schema'] != 'earnings_matched_plan_v1' or plan['episode'] != envelope_binding
                or type(plan['rounds']) is not list or len(plan['rounds']) != self.envelope['max_rounds']
                or (not plan_bound and not 1 <= len(plan['rounds']) <= 2)):
            raise ValueError('Prospective declared finite matched plan required')
        slots = []
        for index, row in enumerate(plan['rounds']):
            if (type(row) is not dict or set(row) != {'parent', 'candidate', 'downstream'}
                    or row['downstream'] != self.envelope['slots'][index]['forecast']):
                raise ValueError('Exact three forecast slots per round required')
            slots.extend(row.values())
        context = getattr(getattr(forecast, '__self__', None), 'context', {})
        if (plan_bound
                and context.get('slots') != declared_slots(self.envelope, plan)['forecast']):
            raise ValueError('Forecast context must equal the finite matched plan')
        root = Path(self.envelope['root'])
        if (len(set(slots)) != len(slots) or context.get('root') != str(root)
                or any(p not in context.get('slots', []) or Path(p).parent != root/'roles'
                       or not Path(p).is_absolute() or Path(p).resolve() != Path(p) for p in slots)):
            raise ValueError('All matched slots must be original declared forecast slots')
        self.sources()

    def sources(self):
        from earnings_shadow_measurement import compare
        values = {'episode': self.envelope_binding, 'plan': self.plan_binding,
            'registration': self.registration_binding, 'trial': engine.source_of(run_matched),
            'measurement': engine.source_of(compare), 'reviewer': engine.source_of(review),
            'probes': engine.source_of(self.probes.run), 'forecast': engine.source_of(self.forecast)}
        engine.driver._artifacts(values)
        return values

    def handle(self, chosen, parent_state, *, round_index):
        self.sources()
        if engine.read(self.envelope_binding) != self.envelope or engine.read(self.plan_binding) != self.plan:
            raise ValueError('Prospective pending plan drift')
        if type(round_index) is not int or not 1 <= round_index <= len(self.plan['rounds']):
            raise ValueError('Undeclared matched round')
        native = self.capacity.batch.snapshot()
        micro, pending = native['micro_evolution'], native['micro_evolution']['pending']
        if (pending is None or chosen['parent_pair_sha256'] != digest(micro['active_pair'])
                or chosen['expected_effect'] != pending['behavior_change']
                or chosen['component'] != pending['component']
                or {'R': 'researcher', 'H': 'harness'}.get(chosen['axis']) != pending['axis']
                or chosen['feedback_sha256'] != pending['problem_evidence_sha256']):
            raise ValueError('Current decision/pending candidate required')
        slots = self.plan['rounds'][round_index-1]
        if (native['active_attempt_ids'] or native['max_attempts']-len(native.get('capacity_work', [])) < 3
                or any(Path(p).exists() for p in slots.values())):
            raise ValueError('Three fresh slots and idle prospective work items required before trial')
        registration = engine.read(self.registration_binding)
        if (type(registration) is not dict or set(registration) != {
                'schema', 'reviewer_id', 'proposer_id', 'review_source', 'probe_source', 'scopes'}
                or registration['schema'] != 'earnings_effect_review_registration_v1'
                or registration['reviewer_id'] != micro['reviewer_id']
                or registration['proposer_id'] != pending['proposer_id']
                or registration['reviewer_id'] == registration['proposer_id']
                or registration['review_source'] != engine.source_of(review)
                or registration['probe_source'] != engine.source_of(self.probes.run)
                or registration['scopes'] != SCOPES):
            raise ValueError('Exact host review registration required before trial')
        root = Path(self.envelope['root'])
        target = root/'effects'/f'round-{round_index:02d}'
        comparison_root = root/'shadow'/f'round-{round_index:02d}'
        criterion_path = root/f'criterion-{round_index:02d}.json'
        if any(p.exists() for p in (target, comparison_root, criterion_path)):
            raise ValueError('Consumed pending effect/criterion/trial roots stay closed')
        try:
            criterion = effect_criterion(chosen['expected_effect'], chosen['component'])
        except ValueError:
            if target.exists(): raise ValueError('Consumed effect root stays closed')
            target.mkdir(parents=True, exist_ok=False)
            receipt = engine.save(target/'review.json', {'review': {
                'reviewer_id': micro['reviewer_id'], 'proposal_sha256': pending['record_sha256'],
                'decision': 'reject', 'reason': 'UNKNOWN_EFFECT_SEMANTICS',
                'tested_pair_sha256': digest(pending['pair']), 'anchor_pair_sha256': digest(micro['anchor_pair']),
                'checks': {}, 'benefit_observed': False, 'benefit_evidence_sha256': None,
                'actual_write_paths': pending['write_paths']}, 'evidence': {}})
            return {'schema': 'earnings_pending_effect_result_v1', 'comparison': None,
                    'review_receipt': receipt, 'artifacts': [receipt]}
        criterion_binding = engine.save(criterion_path, criterion)
        comparison = run_matched(self.task, self.envelope, self.capacity, parent_state,
            pending_proposal_sha256=pending['record_sha256'], forecast=self.forecast,
            parent_slot=slots['parent'], child_slot=slots['candidate'],
            comparison_root=comparison_root, criterion_binding=criterion_binding)
        receipt = review(self.capacity, comparison, registration_binding=self.registration_binding,
                         probe=self.probes.run, output_root=target)
        artifacts = [criterion_binding, comparison, *[engine.pin(p) for p in sorted(target.rglob('*.json'))]]
        return {'schema': 'earnings_pending_effect_result_v1', 'comparison': comparison,
                'review_receipt': receipt, 'artifacts': artifacts}
