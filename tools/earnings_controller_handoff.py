"""One new Controller-only consumption of immutable closed09 feedback.

No Author, forecasting, scoring, candidate execution or adoption occurs here.
The existing owner, ledger, captured clock and raw transport remain authoritative.
"""
from copy import deepcopy
from pathlib import Path
import re

import earnings_entry as e
from earnings_open_broker import DEFINITIONS, program_references
from earnings_open_resources import role_limits
from earnings_open_task import controller_packet_view
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine

AUTHORIZATION='允许，先修 Controller 初始输入包的源码引用和结果去重，补大源码首包测试并独立审查。通过后用新 ID 单独验证反馈被下一次 Controller 实际消费，不重跑已有预测。沿用剩余额度和原 $200 总预算，数据、scorer 不变，每个改动单独提交，失败先诊断，不自动重试。'
ROOT=e.PILOT.parent.parent/'edgar-research-objective-20261014'
PRIOR='edgar-research-20261015-09'
ALLOWED_H={'tools/earnings_open_task.py','tools/earnings_open_broker.py','tools/earnings_capacity_runtime.py'}
PIN_PACKET='2b9540d700412469a18333c7a68b500617abd4d43a4dac0fa276991959a803f9'
PIN_SELECTED='056a372c51d3e2aceafe67e512da8ba5131d9e8864387053210f2af0d4227fbb'
PIN_EPISODE='2e0c1b0069d2b115538633c604a7edc57681fd1cf5049fb429535a6485a5b7de'
PIN_OWNER='fef78af81de387d2c6e6021c32e9d6d77325383e9d37901ea9b4469415767ee8'
PIN_NATIVE='d9d43c61bf8938da85a4aa3d23410fe8b64b5d6f2437a95fa02a5161bb64579b'
PIN_CLOCK_SEAL='c08c2234ca7785ce8aeb6f711f69ab2bba196b3289e7cd5dcc28d7e181415e01'


def read(binding):
    from earnings_capacity_runtime import _read
    return e.strict_json(_read(binding).decode())


def verify_current_python(binding):
    """Retain original exact interpreter alias and byte hash, not arbitrary files."""
    if binding.get('path')!=str(Path(e.sys.executable).absolute()):
        raise ValueError('Exact original interpreter path required')
    return engine.activation._read(binding,allow_alias=True)


def inherited_clock(runtime):
    value=read(runtime['feedback_handoff']);old=read(value['old_runtime'])
    owner=read(value['old_owner'])
    if owner['clock']['path']!=str(Path(old['root'])/'clock.json'):
        raise ValueError('Original owned clock path required')
    e.checked(owner['clock'])
    seal=engine.pin(Path(old['root'])/'clock.binding.json')
    if seal['sha256']!=PIN_CLOCK_SEAL or read(seal)!=owner['clock']:
        raise ValueError('Original clock seal must authenticate the owned clock')
    return {'binding':owner['clock'],'source_commit':old['source_commit']}


def validate_handoff(runtime):
    """Opt in16k only for exact source-bound single-Controller historical handoff."""
    from earnings_open_fresh_grant import BASELINE, policy, pilot_cap
    value=read(runtime['feedback_handoff'])
    fields={'schema','human_authorization','id','root','source_commit','old_runtime','old_episode',
        'old_packet','old_owner','old_selected','old_native','old_reconciled','sources'}
    if (type(value) is not dict or set(value)!=fields
            or value['schema']!='earnings_controller_feedback_handoff_v1'
            or value['human_authorization']!=AUTHORIZATION
            or runtime['schema']!='earnings_capacity_runtime_v1' or runtime['purpose']!='controller_protocol'
            or any(value[k]!=runtime[k] for k in ('id','root','source_commit'))
            or not re.fullmatch(r'edgar-feedback-[0-9]{8}-[0-9]{2}',runtime['id'])
            or runtime['root']!=str(ROOT/'attempts'/runtime['id'])
            or runtime['limits']!={'controller':role_limits()['controller']}
            or runtime['slots']!={'controller':[str(Path(runtime['root'])/'roles/controller-01')]}
            or runtime['sources']['factory_controller']!=engine.pin(__file__)):
        raise ValueError('Exact single-Controller feedback handoff required')
    if value['old_episode']['sha256']!=PIN_EPISODE or value['old_owner']['sha256']!=PIN_OWNER:
        raise ValueError('Original closed09 episode and owner pins required')
    original=read(value['old_runtime']);episode=read(value['old_episode']);grant=read(episode['grant'])
    authority=policy()
    if (original['id']!=PRIOR or episode['id']!=PRIOR or original['root']!=str(ROOT/'attempts'/PRIOR)
            or runtime['ledger']!=original['ledger'] or runtime['baseline']!=BASELINE
            or original['baseline']!=BASELINE or runtime['additional_cap_nano_usd']!=pilot_cap(authority)
            or runtime['rates']!=original['rates']
            or runtime['rates']['api_model']!='gpt-6.1-sol' or runtime['rates']['effort']!='max'
            or any(runtime[k]!=original[k] or runtime[k]!=authority['window'][k]
                   for k in ('cutoff_utc','deadline_utc'))):
        raise ValueError('Original model, sole ledger, cumulative budget and window must remain exact')
    # Hash verification only: no hidden evaluator content is projected or interpreted.
    for name in ('data','runtime','qa','scorer'):
        e.checked(grant[name])
    verify_current_python(grant['python'])
    expected=grant['sources']
    if set(value['sources'])!=set(expected)|{'tools/earnings_controller_handoff.py'}:
        raise ValueError('Complete original source closure plus exact bridge required')
    for name,binding in value['sources'].items():
        if binding!=engine.pin(e.REPO/name):raise ValueError('Current handoff source drift')
        if name in expected and name not in ALLOWED_H and binding['sha256']!=expected[name]:
            raise ValueError('Undeclared original source change')
    owner=read(value['old_owner'])
    expected_owner=Path(original['ledger']).parent/'.capacity-runtime-claims'/(e.digest(PRIOR.encode())+'.result.json')
    if (value['old_owner']['path']!=str(expected_owner) or owner['status']!='FAILED_NO_RETRY'
            or owner.get('retry_allowed') is not False or owner['runtime']!=value['old_runtime']
            or owner['budget_summary']['blocked'] is not False
            or owner['budget_summary']['unresolved_reserved_usd']!=0):
        raise ValueError('Original09 owner must remain closed with no unresolved loan')
    packet=read(value['old_packet']);selected=read(value['old_selected']);native=read(value['old_native'])
    previous=read(value['old_reconciled'])['output']
    if (value['old_packet']['path']!=str(Path(original['root'])/'terminal-controller-packet.json')
            or value['old_packet']['sha256']!=PIN_PACKET or value['old_selected']['sha256']!=PIN_SELECTED
            or value['old_native']['sha256']!=PIN_NATIVE
            or value['old_native']['path']!=str(Path(value['old_selected']['path']).parent.parent/'batch/batch.json')
            or value['old_reconciled']['path']!=str(Path(original['root'])/'loop/round-0001-reconcile.done.json')
            or packet['task_id']!=PRIOR or digest(previous)!=packet['feedback_sha256']
            or packet['parent_feedback_sha256']!=packet['feedback_sha256']
            or previous['feedback']!=packet['feedback']
            or previous['pair_sha256']!=packet['parent_pair_sha256']
            or digest(native['micro_evolution']['active_pair'])!=packet['parent_pair_sha256']
            or native['micro_evolution']['pending'] is not None):
        raise ValueError('Exact existing feedback and active selected09 pair required')
    sources=selected_sources(value)
    if sources!=packet['program_sources']:
        raise ValueError('Saved source differs from actual selected09 source')
    inherited_clock(runtime)
    return value


def selected_sources(value):
    selected=read(value['old_selected']);manifest=selected['manifest']
    source_root=Path(value['old_selected']['path']).parent.parent/'source'
    result={}
    for axis in ('R','H'):
        name=selected['entrypoints'][axis]
        if Path(name).name!=name:raise ValueError('Selected source basename required')
        binding={'path':str(source_root/name),'sha256':manifest['components'][axis]['sources'][name]}
        result[axis]=e.checked(binding).decode('utf-8')
    return result


def packet_view(value):
    result=controller_packet_view(read(value['old_packet']))
    # An old first-slot human repair assignment must not be reissued merely
    # because the next Controller has a fresh single-slot namespace.
    context=result.get('research_context')
    if type(context) is dict and 'dispatch' in context:
        removed=context.pop('dispatch')
        result['historical_dispatch']={'sha256':digest(removed),
            'status':'completed_original09_assignment_not_reissued'}
    result['feedback_handoff']={'id':value['id'],'original_packet':value['old_packet'],
        'scope':'Existing09feedback, one new Controller decision only; no new forecast or applied proposal'}
    return result


def prepare(identifier,source_commit):
    """Offline preparation, not a launch or clock/budget renewal."""
    from earnings_capacity_runtime import CORE,preflight_runtime
    home=ROOT/'inputs'/identifier
    if (not re.fullmatch(r'edgar-feedback-[0-9]{8}-[0-9]{2}',identifier)
            or not re.fullmatch(r'[0-9a-f]{40}',source_commit)):
        raise ValueError('Exact fresh handoff ID and committed source required')
    oldhome=ROOT/'inputs'/PRIOR
    original=read(engine.pin(oldhome/'runtime.json'))
    selected=Path.home()/'Library/Application Support/MarketRSI/co-evo-earnings/episodes'/PRIOR
    owner=Path(original['ledger']).parent/'.capacity-runtime-claims'/(e.digest(PRIOR.encode())+'.result.json')
    oldgrant=read(read(engine.pin(oldhome/'episode.json'))['grant'])
    value={'schema':'earnings_controller_feedback_handoff_v1','human_authorization':AUTHORIZATION,
        'id':identifier,'root':str(ROOT/'attempts'/identifier),'source_commit':source_commit,
        'old_runtime':engine.pin(oldhome/'runtime.json'),'old_episode':engine.pin(oldhome/'episode.json'),
        'old_packet':engine.pin(Path(original['root'])/'terminal-controller-packet.json'),
        'old_owner':engine.pin(owner),
        'old_selected':{'path':str(selected/'versions/7639473675b41296abbd1a20e529d357bc544f726134ed52c6118dbc1c3e2482.json'),'sha256':PIN_SELECTED},
        'old_native':engine.pin(selected/'batch/batch.json'),
        'old_reconciled':engine.pin(Path(original['root'])/'loop/round-0001-reconcile.done.json'),
        'sources':{name:engine.pin(e.REPO/name) for name in set(oldgrant['sources'])|{'tools/earnings_controller_handoff.py'}}}
    if Path(value['root']).exists():raise FileExistsError('Handoff root already exists')
    claim=owner.parent/(e.digest(identifier.encode())+'.json')
    if claim.exists() or claim.with_suffix('.result.json').exists():
        raise FileExistsError('Consumed handoff ID remains closed')
    home.mkdir(parents=True,exist_ok=False)
    binding=engine.save(home/'handoff.json',value)
    runtime={'schema':'earnings_capacity_runtime_v1','purpose':'controller_protocol',
        **{k:value[k] for k in ('id','root','source_commit')},
        **{k:original[k] for k in ('ledger','baseline','cutoff_utc','deadline_utc','rates','additional_cap_nano_usd')},
        'limits':{'controller':role_limits()['controller']},
        'slots':{'controller':[str(Path(value['root'])/'roles/controller-01')]},
        'sources':{**{key:engine.pin(path) for key,path in CORE.items()},'factory_controller':engine.pin(__file__)},
        'feedback_handoff':binding}
    runtime_binding=engine.save(home/'runtime.json',runtime)
    preflight_runtime(runtime_binding)
    packet=engine.save(home/'packet-view.json',packet_view(value))
    return engine.save(home/'prepared.json',{'runtime':runtime_binding,'packet':packet,
        'source_commit':source_commit,'provider_calls':0,'status':'AWAITING_DISTINCT_REVIEW'})


class HandoffBroker:
    """Read-only selected source channel. Live one-turn Controller closes tools."""
    def __init__(self,value):
        self.value=deepcopy(value)
        self.definitions=[deepcopy(row) for row in DEFINITIONS if row['name']=='read_current_program']
    def research_context(self):
        return packet_view(self.value).get('research_context')
    def dispatch(self,name,args):
        if name!='read_current_program' or type(args) is not dict or set(args)!={'axis'} or args['axis'] not in ('R','H'):
            raise ValueError('Only exact selected source reading allowed')
        sources=selected_sources(self.value);axis=args['axis']
        return {'value':{'axis':axis,'source_text':sources[axis],**program_references(sources)[axis]}}


def run(runtime_binding,review_binding):
    """Exactly one generation through original owner; failed slots never reopen."""
    from earnings_capacity_runtime import preflight_runtime,open_capacity_runtime
    from earnings_live_capacity import provider_client
    from earnings_open_roles import OpenController
    runtime=preflight_runtime(runtime_binding);value=validate_handoff(runtime);review=read(review_binding)
    if (review.get('verdict')!='PASS_CONTROLLER_FEEDBACK_HANDOFF_ONLY' or review.get('blocking_findings')!=[]
            or type(review.get('reviewer')) is not str or not review['reviewer'].strip()
            or review['reviewer'].strip().lower() in ('root','/root') or review.get('runtime')!=runtime_binding
            or review.get('reviewed_sources')!=value['sources']):
        raise ValueError('Distinct exact-source and payload review required')
    root=Path(runtime['root'])
    root.mkdir(parents=True,exist_ok=False)
    (root/'roles').mkdir()
    broker=HandoffBroker(value)
    def factory(context,*,budget,client_factory):
        return OpenController(context,budget=budget,client_factory=client_factory,
            broker=broker,max_turns=1,max_tool_calls=1).propose
    prompt=packet_view(value)
    with open_capacity_runtime(runtime_binding,client_factory=provider_client,
                               role_factories={'controller':factory}) as owner:
        original=owner['roles']['controller'](prompt,runtime['slots']['controller'][0])
        result={'schema':'earnings_controller_feedback_handoff_result_v1',
            'original':original,'old_packet':value['old_packet'],
            'feedback_sha256':prompt['feedback_sha256'],'parent_pair_sha256':prompt['parent_pair_sha256'],
            'decision_applied':False,'new_forecasts':0,'claims':{'predictive_gain':False,'joint_coevolution':False}}
        engine.save(root/'handoff-decision.json',result)
    terminal=engine.pin(Path(runtime['ledger']).parent/'.capacity-runtime-claims'/(
        e.digest(runtime['id'].encode())+'.result.json'))
    if read(terminal)['status']!='COMPLETED_COMPONENT_CONTEXT':
        raise ValueError('Original runtime owner did not close successfully')
    return engine.save(root/'handoff-result.json',dict(result,owner_terminal=terminal))
