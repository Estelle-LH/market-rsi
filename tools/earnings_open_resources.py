"""Scoped open-role resources, never new spending or time credit."""
from copy import deepcopy
from pathlib import Path

import earnings_entry as e
from earnings_loop_policy import LIMITS

ROLE_EFFORTS={'controller':'max','author':'high','review':'max','forecast':'max'}


def validate_role_efforts(runtime,study):
    """Explicit human-authorized Author computation, never a forecast override."""
    from supervisor_harness import capacity_feedback_engine as engine
    import earnings_open_fresh_grant as fresh
    mapping=runtime.get('role_efforts')
    if (runtime.get('schema')!='earnings_capacity_runtime_v2'
            or runtime.get('purpose')!='capacity_episode' or type(mapping) is not dict
            or mapping!=ROLE_EFFORTS or any(type(v) is not str for v in mapping.values())
            or runtime.get('rates',{}).get('effort')!='max'
            or runtime['rates'].get('api_model')!='gpt-6.1-sol'):
        raise ValueError('Only exact Author-high/other-max role computation is permitted')
    grant=engine.read(study['new_live_grant'])
    if (grant.get('schema')!=fresh.SCHEMA
            or any(grant.get(k)!=runtime.get(k) for k in ('id','root','source_commit','ledger',
                'baseline','cutoff_utc','deadline_utc','additional_cap_nano_usd'))
            or runtime.get('sources',{}).get('factory_author')!=engine.pin(e.REPO/'tools/earnings_open_assembly.py')
            or grant.get('sources',{}).get('configs/earnings_coevolution/research_followup_authority.json')!=
                e.digest(Path(fresh.CONFIG).read_bytes())
            or fresh.policy().get('author_configuration')!=fresh.AUTHOR_CONFIGURATION):
        raise ValueError('Author effort requires the exact approved fresh grant/source/configuration')
    return deepcopy(mapping)


def role_limits():
    return {'controller':dict(deepcopy(LIMITS),max_input_tokens=16000),'review':deepcopy(LIMITS),
        'author':{'max_input_tokens':24000,'max_output_tokens':49152,'wall_seconds':900}}


def author_ceiling(runtime,study):
    """Only the exact source-bound open factory/grant can use this ceiling.

    Ordinary legacy runtimes keep LIMITS. This is preparation validation, not
    permission: OpenTask still admits exact data/source/window/sole-ledger caps.
    """
    if runtime.get('schema')!='earnings_capacity_runtime_v2':return None
    binding=study.get('new_live_grant')
    if type(binding) is not dict:return None
    grant=e.strict_json(e.checked(binding))
    if type(grant) is not dict:raise ValueError('Exact bound open resource grant required')
    if grant.get('schema') not in {'earnings_open_grant_v1','earnings_research_followup_grant_v1'}:return None
    names=('id','root','source_commit','ledger','baseline','cutoff_utc','deadline_utc','additional_cap_nano_usd')
    if any(grant.get(k)!=runtime.get(k) for k in names):
        raise ValueError('Open Author resources require the exact original runtime grant')
    factory=runtime.get('sources',{}).get('factory_author')
    path=e.REPO/'tools/earnings_open_assembly.py'
    if (type(factory) is not dict or factory.get('path')!=str(path)
            or e.checked(factory)!=path.read_bytes()):
        raise ValueError('Larger Author completion requires the exact opt-in source factory')
    return role_limits()['author']


def controller_ceiling(runtime,study):
    """Only the same exact open grant plus Controller factory permits headroom.

    Input capacity changes, not history, output/time, other roles or spending.
    Ordinary Controller runtimes retain the generic10000-token ceiling.
    """
    if author_ceiling(runtime,study) is None:return None
    factory=runtime.get('sources',{}).get('factory_controller')
    path=e.REPO/'tools/earnings_open_assembly.py'
    if (type(factory) is not dict or factory.get('path')!=str(path)
            or e.checked(factory)!=path.read_bytes()):
        raise ValueError('Controller input headroom requires the exact opt-in source factory')
    return role_limits()['controller']
