"""Source-bound open-role ceilings; no new global window or spending credit."""
from copy import deepcopy
from pathlib import Path

import earnings_entry as e
from earnings_loop_policy import LIMITS

ROLE_EFFORTS={'controller':'max','author':'high','review':'max','forecast':'max'}
REVIEW200_POLICY='review_input_200000_v1'
REVIEW200_ROOT=e.PILOT.parent.parent/'edgar-population-20261016'
REVIEW200_AUTHORITY=dict(path=str(REVIEW200_ROOT/'TRAIN25-DIRECT-REVIEW200K-REUSE37-AUTHORITY.json'),
    sha256='aef9fa092ceeb4afe4b1ee22f288df5b9d660f8419fdd84f2b866ae8885aa959')


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
    return {'controller':dict(deepcopy(LIMITS),max_input_tokens=32000,wall_seconds=900),
        'review':dict(deepcopy(LIMITS),max_input_tokens=32000,wall_seconds=900),
        'author':{'max_input_tokens':96000,'max_output_tokens':49152,'wall_seconds':1200}}


def review_input_policy(value):
    """Select a resource overlay, not runtime/stage admission or new credit."""
    if type(value) is not dict:raise ValueError('Exact Review resource policy object required')
    if 'review_input_policy' not in value:return None
    if type(value['review_input_policy']) is not str or value['review_input_policy']!=REVIEW200_POLICY:
        raise ValueError('Only the explicit Review200k input policy is authorized')
    if (type(REVIEW200_AUTHORITY) is not dict or set(REVIEW200_AUTHORITY)!={'path','sha256'}
            or any(type(REVIEW200_AUTHORITY[k]) is not str for k in ('path','sha256'))):
        raise ValueError('Exact original Review200k authority binding required')
    path=Path(REVIEW200_AUTHORITY['path'])
    if (path!=REVIEW200_ROOT/'TRAIN25-DIRECT-REVIEW200K-REUSE37-AUTHORITY.json'
            or str(path)!=REVIEW200_AUTHORITY['path'] or not path.is_absolute()
            or path.resolve()!=path or path.is_symlink() or not path.is_file() or path.stat().st_nlink!=1):
        raise ValueError('Exact canonical original Review200k authority required')
    authority=e.strict_json(e.checked(REVIEW200_AUTHORITY))
    fixed={'model':'gpt-6.1-sol','controller_input_tokens':32000,'Author_input_tokens':96000,
        'Author_output_tokens':49152,'Review_output_tokens':16384,'Review_wall_seconds':900,
        'window_minutes':90,'stage_additional_nano_usd':200000000000,
        'cumulative_cap_nano_usd':400000000000,'named_model_cap_nano_usd':300000000000}
    if (type(authority) is not dict or authority.get('schema')!='earnings_training25_direct_review200k_reuse37_authority_v1'
            or type(authority.get('old_review_max_input_tokens')) is not int or authority['old_review_max_input_tokens']!=32000
            or type(authority.get('new_review_max_input_tokens')) is not int or authority['new_review_max_input_tokens']!=200000
            or type(authority.get('unchanged')) is not dict
            or any(type(authority['unchanged'].get(k)) is not type(v) or authority['unchanged'][k]!=v for k,v in fixed.items())
            or authority.get('status')!='DIRECTLY_AUTHORIZED_NOT_IMPLEMENTED_OR_ACTIVATED'):
        raise ValueError('Original Review200k authority changed another resource or scope')
    return REVIEW200_POLICY


def population_role_limits(value):
    """Fresh expected limits; callers still authenticate and compare runtime."""
    result=role_limits()
    if review_input_policy(value) is not None:result['review']['max_input_tokens']=200000
    return result


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

    Explicit open-role input/wall ceilings do not change history or spending.
    Ordinary Controller runtimes retain the generic10000-token ceiling.
    """
    if author_ceiling(runtime,study) is None:return None
    factory=runtime.get('sources',{}).get('factory_controller')
    path=e.REPO/'tools/earnings_open_assembly.py'
    if (type(factory) is not dict or factory.get('path')!=str(path)
            or e.checked(factory)!=path.read_bytes()):
        raise ValueError('Controller input headroom requires the exact opt-in source factory')
    return role_limits()['controller']
