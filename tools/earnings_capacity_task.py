"""Filing/state/task hooks for the common offline capacity feedback engine."""
from pathlib import Path

import earnings_entry as e
import earnings_controller as controller
import earnings_loop_policy as policy
from earnings_feedback import project_feedback
from earnings_capacity_adapter import author_candidate
from earnings_capacity_worker import CapacityWorker
import earnings_execution_receipt as measurement
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


class EarningsTask:
    def admit_live(self,envelope):
        from earnings_live_capacity import admit
        admit(envelope)
        return True

    def bootstrap_control(self,envelope,prompt,index):
        if envelope.get('schema') != 'earnings_capacity_episode_v3' or index != 1:
            return None
        self.admit_live(envelope)
        return {'schema':'earnings_capacity_decision_v1','axis':'continue','component':'none',
            'parent_pair_sha256':prompt['parent_pair_sha256'],'feedback_sha256':prompt['feedback_sha256'],
            'hypothesis':'Human-declared fixed R0/H0 baseline; no model decision claimed',
            'expected_effect':'Run the unchanged initial pair and return its actual feedback/state'}

    def preflight(self, envelope):
        self.micro_policy = envelope.get('schema') == 'earnings_capacity_episode_v3'
        self.company, self.state_api = e.preflight_capacity_episode(envelope)
        self.kernel = envelope.get('evaluation_kernel')
        measurement.kernel(self.kernel, self.state_api.tools.files['questions.md'])

    def sources(self):
        return {name: engine.pin(e.REPO / name) for name in policy.capacity_sources()}

    def seed(self, envelope):
        observation = project_feedback({'status': 'FAILED_NO_RETRY', 'planned_targets': 5,
            'scored_targets': 0, 'error_type': 'NoForecastYet'}, None,
            task_id=envelope['id'], cik=envelope['cik'])
        return {'feedback': {'observation': observation, 'baseline_score_out_of_5': None},
                'state': envelope['initial_state'], 'artifacts': [envelope['initial_state']]}

    def role_slot(self, envelope, index, name):
        return envelope['slots'][index-1]['forecast' if name == 'execute' else name]

    def load_state(self, bound): return self.state_api.load(bound)

    def packet(self, envelope, ctx, profiles, pair):
        value = {'task_id': envelope['id'], 'questions': self.state_api.tools.files['questions.md'],
                 'parent_feedback_sha256': ctx['previous_feedback_sha256'], 'parent_pair_sha256': pair,
                 'feedback': ctx['previous_result']['feedback'], 'prior_recipe': None}
        return controller.capacity_input(value, profiles)

    def decision(self, original, prompt): return controller.parse_capacity_decision(original, prompt)
    def candidate(self, original, before, choice):
        candidate = author_candidate(original, before, choice)
        if getattr(self,'micro_policy',False):
            from earnings_capacity_adapter import micro_delta
            micro_delta(before,candidate['profile'],choice['axis'])
        return candidate

    def worker(self, envelope, capacity, pair, state):
        return self.make_worker(envelope['id'], capacity, pair, Path(envelope['root'])/'memory', state)

    def make_worker(self, task_id, capacity, pair, state_root, state, *, shadow_proposal_sha256=None):
        return CapacityWorker(self.company, task_id, capacity, pair, state_root, state,
            shadow_proposal_sha256=shadow_proposal_sha256)

    def execution(self, output, worker, slot):
        if (type(output) is not dict or set(output) != {'result', 'score'}
                or engine.read(output['result']).get('status') != 'COMPLETED_SCORED'):
            raise RuntimeError('Forecast failed once; preserve originals and diagnose before fresh attempt')
        if any(output[k].get('path') != str(Path(slot)/f'{k}.json') for k in ('result', 'score')):
            raise ValueError('Forecast originals outside declared role slot')
        effective = engine.pin(Path(slot)/'effective-capacity.json')
        finished = engine.pin(Path(slot)/'research-state-output.json')
        used, terminal = engine.read(effective), engine.read(finished)
        if (used['context'] != worker.context or used['initial_state']['sha256'] != worker.state_receipt['state_sha256']
                or terminal['state'] != worker.state_binding):
            raise ValueError('Actual worker capacity/state consumption differs')
        actual_pairs = {receipt['selected_pair_sha256'] for receipt in used['context']['receipts']}
        if len(actual_pairs) != 1: raise ValueError('Worker consumed different R/H selections')
        originals = measurement.verify(output, worker, slot, self.kernel)
        return dict(output, state=worker.state_binding, consumed={'pair_sha256': actual_pairs.pop(),
                    'state_sha256': used['initial_state']['sha256']},
                    artifacts=[output['result'], output['score'], effective, finished, worker.state_binding, *originals])

    def feedback(self, output, envelope):
        from earnings_research_diagnostics import project_diagnostics
        observed = project_feedback(engine.read(output['result']), engine.read(output['score']),
                                    task_id=envelope['id'], cik=envelope['cik'])
        return {'observation': observed, 'baseline_score_out_of_5': None,
                'research_diagnostics': project_diagnostics(output, observed)}

    def shadow_execution(self, output, worker, slot, *, active_pair_sha256,
                         tested_pair_sha256, pending_proposal_sha256, initial_state):
        """Reverify originals with separate active ownership and tested identity."""
        snapshot = worker.capacity.batch.snapshot()
        micro = snapshot['micro_evolution']
        pending = micro['pending']
        for value in (active_pair_sha256, tested_pair_sha256, pending_proposal_sha256):
            engine.identity.sha(value)
        if (digest(micro['active_pair']) != active_pair_sha256 or pending is None
                or pending['record_sha256'] != pending_proposal_sha256
                or worker.pair != active_pair_sha256 or worker.tested_pair != tested_pair_sha256):
            raise ValueError('Exact current active/pending/tested shadow identities required')
        child = worker.shadow_proposal_sha256 is not None
        if ((child and (worker.shadow_proposal_sha256 != pending_proposal_sha256
                        or tested_pair_sha256 != digest(pending['pair'])))
                or (not child and tested_pair_sha256 != active_pair_sha256)):
            raise ValueError('Parent worker cannot be relabelled as a pending child')
        worker._check()
        worker.state_api.load(initial_state)
        verified = self.execution(output, worker, slot)
        effective = engine.read(engine.pin(Path(slot)/'effective-capacity.json'))
        shadow = {'active_pair_sha256': active_pair_sha256,
                  'tested_pair_sha256': tested_pair_sha256,
                  'pending_proposal_sha256': pending_proposal_sha256}
        if ((child and effective.get('shadow') != shadow)
                or (not child and 'shadow' in effective)
                or e.checked(effective['initial_state']) != e.checked(initial_state)
                or verified['consumed'] != {'pair_sha256': tested_pair_sha256,
                                            'state_sha256': initial_state['sha256']}
                or worker.capacity.batch.snapshot()['state_sha256'] != snapshot['state_sha256']):
            raise ValueError('Original shadow metadata/state or native context differs')
        return dict(verified, consumed=dict(shadow, state_sha256=initial_state['sha256']),
                    artifacts=[*verified['artifacts'], engine.pin(Path(slot)/'identity.json'),
                               engine.pin(Path(slot)/'budget-summary.json')])
