"""Program-source versions on existing Native selection; no host code imports."""
from copy import deepcopy

from earnings_capacity_adapter import EarningsCapacity
from earnings_open_program import program
from market_rsi import digest
from supervisor_harness import research_capacity_activation as activation


class ProgramCapacity(EarningsCapacity):
    def _validate_version(self, value, entrypoints):
        activation.CapacityActivation._validate_version(self, value, entrypoints)
        for axis, name in entrypoints.items():
            program(activation._read({'path':str(self.source_root/name),
                'sha256':value['components'][axis]['sources'][name]}), axis)

    def _store(self, value, entrypoints, static_review=None):
        return activation.CapacityActivation._store(self, value, entrypoints, static_review)

    def propose(self, after, proposal, entrypoints, *, static_review, expected_state_sha256):
        return activation.CapacityActivation.propose(self, after, proposal, entrypoints,
            static_review=static_review, expected_state_sha256=expected_state_sha256)

    def resolve(self, axis, *, expected_pair_sha256, shadow_proposal_sha256=None):
        if axis not in {'R','H'}:
            raise ValueError('Program R/H axis required')
        state = self.batch.snapshot()
        micro = state['micro_evolution']
        if digest(micro['active_pair']) != expected_pair_sha256:
            raise ValueError('Stale program selected pair')
        selected = micro['active_pair']
        if shadow_proposal_sha256 is not None:
            pending = micro['pending']
            if pending is None or pending['record_sha256'] != shadow_proposal_sha256:
                raise ValueError('Exact pending program required for shadow')
            selected = pending['pair']
        body = self._version(selected)
        name = body['entrypoints'][axis]
        bound = {'path':str(self.source_root/name), 'sha256':body['manifest']['components'][axis]['sources'][name]}
        metadata = program(activation._read(bound), axis)
        if self.batch.snapshot()['state_sha256'] != state['state_sha256']:
            raise ValueError('Program selection changed during metadata resolution')
        return {'profile':metadata,'receipt':{'axis':axis,'source':bound,
            'selected_pair_sha256':digest(selected),'active_pair_sha256':expected_pair_sha256,
            'shadow':shadow_proposal_sha256 is not None,'model_code_executed':False}}

    def prepare(self, *, expected_pair_sha256, questions, state_message=None, shadow_proposal_sha256=None):
        options = {'expected_pair_sha256':expected_pair_sha256,'shadow_proposal_sha256':shadow_proposal_sha256}
        selected = [self.resolve(axis,**options) for axis in ('R','H')]
        messages = [{'role':'user','content':questions}]
        if state_message is not None:
            messages.append(deepcopy(state_message))
        context = {'messages':messages,'tool_bounds':{'axis':'H','read_chunk_limit':20000,'search_hit_limit':50},
            'receipts':[item['receipt'] for item in selected], 'payload_sha256':digest(messages),
            'live_dispatch':False}
        if shadow_proposal_sha256 is not None:
            context['shadow_proposal_sha256'] = shadow_proposal_sha256
        return context
