"""Bind unchanged reviewed code to a new approved execution context.

Original proposals remain immutable. This record is execution provenance, not
new scientific authorship, adoption, permission, or a weaker Native validator.
"""
from copy import deepcopy
import re

from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine

RESOURCE_FIELDS=('limits','rates','baseline','additional_cap_nano_usd',
                 'cutoff_utc','deadline_utc','role_efforts')
CONTEXT_FIELDS={'model_sha256','evaluation_sha256','data_scope_sha256',
                'authority_sha256','resource_policy_sha256'}
SCIENTIFIC_FIELDS={'model_sha256','evaluation_sha256','data_scope_sha256'}


def derive(specification_binding, *, scope_binding, runtime_binding, fixed_context):
    spec=engine.read(specification_binding)
    scope=engine.read(scope_binding); runtime=engine.read(runtime_binding)
    proposal=deepcopy(spec['proposal']); old=proposal['fixed_context']
    if (type(fixed_context) is not dict or set(fixed_context)!=CONTEXT_FIELDS
            or type(old) is not dict or set(old)!=CONTEXT_FIELDS
            or any(type(v) is not str or re.fullmatch(r'[0-9a-f]{64}',v) is None
                   or v=='0'*64 for context in (old,fixed_context) for v in context.values())
            or any(old[k]!=fixed_context[k] for k in SCIENTIFIC_FIELDS)
            or fixed_context['authority_sha256']!=scope_binding['sha256']
            or fixed_context['resource_policy_sha256']!=digest({k:runtime[k] for k in RESOURCE_FIELDS})
            or runtime['id']!=scope['forecast_id']
            or any(runtime[k]!=scope['window'][k] for k in ('cutoff_utc','deadline_utc'))):
        raise ValueError('Exact approved execution context only; scientific context stays fixed')
    proposal['fixed_context']=deepcopy(fixed_context)
    return {'schema':'earnings_candidate_execution_transfer_v1',
        'original_specification':deepcopy(specification_binding),
        'scope':deepcopy(scope_binding),'runtime':deepcopy(runtime_binding),
        'proposal':proposal}


def validate(binding, *, specification_binding, scope_binding, runtime_binding, fixed_context):
    expected=derive(specification_binding,scope_binding=scope_binding,
                    runtime_binding=runtime_binding,fixed_context=fixed_context)
    if engine.read(binding)!=expected:
        raise ValueError('Exact immutable original-to-stage candidate transfer required')
    return expected
