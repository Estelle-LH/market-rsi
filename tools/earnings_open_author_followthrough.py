"""Exact Controller11 -> Author12 -> reviewed candidate forecast13.

Reuse the original owner, roles, broker, Native selection and financial scorer.
No candidate code runs on host; no parent reforecast or forced adoption occurs.
Each new stage has an unused ID, one fixed shared window and the original ledger.
"""
from copy import deepcopy
from pathlib import Path
import sqlite3
import subprocess

import earnings_entry as e
import earnings_open_fresh_grant as fresh
import earnings_open_assembly as assembly
import earnings_live_capacity as original_capacity
import earnings_native_namespace as namespace
import earnings_open_researcher as researcher
import earnings_native_failure
import earnings_candidate_transfer as transfer
from edgar_forecast_tools import FilingTools
from earnings_controller import parse_capacity_decision
from earnings_controller_handoff import read, selected_sources, verify_current_python
from earnings_night_budget import history_snapshot
from earnings_open_capacity import ProgramCapacity
from earnings_open_program import program, candidate
from earnings_capacity_adapter import author_payload
from earnings_open_code import DockerRunner
from earnings_open_broker import ResearchBroker
from earnings_open_literature import LiteratureBroker
from earnings_open_source_review import ProgramSourceReview
from earnings_open_worker import ProgramWorker
from earnings_open_task import OpenTask
from earnings_research_state import ResearchState
from earnings_capacity_runtime import CORE, preflight_runtime, open_capacity_runtime
from earnings_clock import capture_or_load
from earnings_http import save_bytes
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch

ROOT=fresh.ROOT
SCOPE=e.REPO/'configs/earnings_coevolution/author_followthrough_scope.json'
CONTEXT=e.REPO/'configs/earnings_coevolution/author_followthrough_context.json'
AUTHORIZATION='那继续让 Author 实现 Controller 提出的表格解析修复，再验证新版本被下一轮真实预测实际使用。先给具体计划，开新的90分钟窗口，沿用剩余额度和原$200总预算，数据、scorer不变。每个改动单独提交、测试和独立审查，失败先诊断，不自动重试。'
CHILD='researcher_followthrough_child.py'
REVIEWER='trusted-host-followthrough-source-review'
PROPOSER='actual-model-author-edgar-research-20261015-12'
PARENT_RESULT_SHA='6f3727a9ebed116d297f565fef689051a98a811808301997275f5ed3dda59629'
PARENT_AUDIT_SHA='093af49695fd22246f502bf8db4286e37282cdf3cabb93751f085fe1eeb51d7e'
ALLOWED_CHANGED={'tools/earnings_open_assembly.py',
    'configs/earnings_coevolution/research_followup_authority.json'}


def authority():
    scope=read(engine.pin(SCOPE));policy=fresh.policy()
    recovery=fresh.forecast_recovery(policy)
    if (scope.get('schema')!='earnings_author_followthrough_authority_v1'
            or scope.get('human_authorization')!=AUTHORIZATION or scope.get('no_retry') is not True
            or (scope.get('author_id'),scope.get('forecast_id')) not in {
                ('edgar-research-20261015-12','edgar-research-20261015-13'),
                ('edgar-research-20261015-14','edgar-research-20261015-15'),
                ('edgar-research-20261015-16','edgar-research-20261015-17'),
                ('edgar-research-20261015-18','edgar-research-20261015-19'),fresh.AUTHOR20_IDS,fresh.AUTHOR22_IDS,fresh.AUTHOR24_IDS,
                (fresh.AUTHOR24_IDS[0],fresh.FORECAST26_ID),
                (fresh.AUTHOR24_IDS[0],fresh.FORECAST27_ID),
                (fresh.AUTHOR24_IDS[0],fresh.FORECAST28_ID)}
            or scope.get('parent')!='edgar-feedback-20261015-11'
            or scope.get('parent_result',{}).get('sha256')!=PARENT_RESULT_SHA
            or scope.get('parent_audit',{}).get('sha256')!=PARENT_AUDIT_SHA
            or scope.get('baseline_row')!=fresh.BASELINE['max_rowid']
            or scope.get('continuation_cumulative_cap_nano_usd')!=fresh.pilot_cap(policy)
            or scope.get('original_total_cap_nano_usd')!=200_000_000_000
            or scope.get('window')!=fresh.current_window(policy)):
        raise ValueError('Exact latest human scope/window and original cumulative credit required')
    is_recovery=(scope['author_id'],scope['forecast_id']) in {
        (fresh.AUTHOR24_IDS[0],fresh.FORECAST26_ID),(fresh.AUTHOR24_IDS[0],fresh.FORECAST27_ID),
        (fresh.AUTHOR24_IDS[0],fresh.FORECAST28_ID)}
    if (is_recovery!=(recovery is not None) or is_recovery and (
            scope.get('closed_forecast_review')!=recovery['closed_forecast_review']
            or scope.get('native_failure_closure_review')!=recovery['native_failure_closure_review'])):
        raise ValueError('Only fresh26 may consume the exact reviewed failure recovery authority')
    successor=fresh.candidate_transfer_authority(policy)
    if ((scope['forecast_id'] in (fresh.FORECAST27_ID,fresh.FORECAST28_ID))!=(successor is not None)
            or successor is not None and scope.get('candidate_transfer_authority')!=successor):
        raise ValueError('Exact separately approved cross-window transfer successor required')
    headroom=fresh.forecast_headroom_authority(policy)
    if ((scope['forecast_id']==fresh.FORECAST28_ID)!=(headroom is not None)
            or headroom is not None and scope.get('forecast_headroom_authority')!=headroom):
        raise ValueError('Exact separately approved28 source/window/allocation child required')
    if scope['author_id'].endswith('-14'):
        if (scope.get('continuation_human_approval')!='允许，新ID修复后测试和独立审查，通过才预测'
                or scope.get('requires_cold_probe') is not True
                or read(scope['failed_author_result']).get('original',{}).get('sha256')!=
                    '9a08f43110c5b0837763cb451b96c5704a5d417376d4869e91b797af5b533334'
                or scope['failed_candidate_review']['sha256']!=
                    'bff68c403a47cd125ac16de73140b877acd5726d9172575b95eba7c6932af3dd'
                or read(scope['failed_candidate_review']).get('verdict')!='REJECT_AUTHOR_CANDIDATE_ONE_FORECAST'):
            raise ValueError('Exact diagnosed12 and human-approved14 continuation required')
    if scope['author_id'].endswith('-16'):
        if (scope.get('continuation_human_approval')!='允许，用新 ID 让 Author 修复这两条解析规则和测试预期，补真实财报表格测试，独立审查通过后才预测。沿用当前窗口和剩余额度，数据、scorer 和原 $200 总预算不变，每个改动单独提交，失败先诊断，不自动重试。'
                or scope.get('requires_cold_probe') is not True
                or read(scope['failed_author_result']).get('original',{}).get('sha256')!=
                    'ac37fa7729796edb19b18c5c66cbf3cfafdbb7f4e14ced415d47cc9ff0b950ba'
                or scope['failed_candidate_review']['sha256']!=
                    'd0cdab3bd66d0c26cbca234506670bbbad1ad64f250f81155eee362dd20b91e2'
                or read(scope['failed_candidate_review']).get('verdict')!='REJECT_AUTHOR_CANDIDATE_ONE_FORECAST'):
            raise ValueError('Exact diagnosed14 and human-approved16 continuation required')
    if scope['author_id'].endswith('-18'):
        observed=read(scope['observed_reconciliation']);review=read(scope['reconciliation_review'])
        reviewer=review.get('reviewer')
        if (scope.get('continuation_human_approval')!='先核清这 $0.3502 的未决费用，再给具体计划，开新的90分钟窗口，用新 ID 让 Author 修复解析规则和测试预期，补真实表格测试，独立审查通过后验证下一轮真实预测使用了新版本。沿用剩余额度和原 $200 累计预算，数据、scorer 不变，每个改动单独提交，失败先诊断，不自动重试。'
                or scope.get('operator_human_approval')!='允许全额保守记账后继续；子额度约余 $0.88'
                or scope.get('requires_cold_probe') is not True
                or read(scope['failed_author_result']).get('original',{}).get('sha256')!=
                    'ac37fa7729796edb19b18c5c66cbf3cfafdbb7f4e14ced415d47cc9ff0b950ba'
                or scope['failed_candidate_review']['sha256']!=
                    'd0cdab3bd66d0c26cbca234506670bbbad1ad64f250f81155eee362dd20b91e2'
                or read(scope['failed_candidate_review']).get('verdict')!='REJECT_AUTHOR_CANDIDATE_ONE_FORECAST'
                or scope['closed16_failure_review']['sha256']!=
                    'd621fe610cce92de1d1552a081562b5ca5a48032614afe7c4d154945e0b4c7ce'
                or read(scope['closed16_failure_review']).get('verdict')!=
                    'VERIFIED_CUTOFF_FAILURE_UNRESOLVED_FINANCIAL_LIABILITY_NO_RETRY'
                or observed.get('request_id')!='fa1f085d-9093-4cbe-ae3d-1c9ffcfb776c'
                or observed.get('full_liability_nano_usd')!=350207500
                or observed.get('actual_invoice')!='UNKNOWN'
                or observed.get('no_duplicate_operator_call') is not True
                or review.get('verdict')!='PASS_OBSERVED_FULL_CEILING_DISPOSITION_ONLY'
                or review.get('blocking_findings')!=[]
                or type(reviewer) is not str or not reviewer.strip()
                or reviewer.strip().lower() in {'root','/root'}
                or review.get('observed_reconciliation')!=scope['observed_reconciliation']):
            raise ValueError('Exact approved18, rejected14, closed16 and reviewed full-liability disposition required')
    is_output=(scope['author_id'],scope['forecast_id'])==fresh.AUTHOR24_IDS or is_recovery
    is_successor=(scope['author_id'],scope['forecast_id'])==fresh.AUTHOR22_IDS or is_output
    if fresh.output_followthrough(policy) is not None and not is_output:
        raise ValueError('Closed22 and earlier stages cannot use output followthrough authority')
    if fresh.successor(policy) is not None and not is_successor:
        raise ValueError('Closed20 and earlier stages cannot use successor authority')
    if (scope['author_id'],scope['forecast_id'])==fresh.AUTHOR20_IDS or is_successor:
        a=fresh.allocation(policy); context=read(engine.pin(CONTEXT))
        if (a is None or scope.get('allocation')!=a
                or scope.get('continuation_human_approval')!=(fresh.FORECAST28_AUTHORIZATION if headroom is not None else fresh.FORECAST27_AUTHORIZATION if successor is not None else fresh.FORECAST26_AUTHORIZATION if is_recovery else fresh.AUTHOR24_AUTHORIZATION if is_output else fresh.AUTHOR22_AUTHORIZATION
                    if is_successor else fresh.AUTHOR20_AUTHORIZATION)
                or scope.get('requires_cold_probe') is not True
                or scope.get('opening_rows')!=a['opening']['max_rowid']
                or scope.get('opening_rows_sha256')!=a['opening']['rows_sha256']
                or read(scope['failed_author_result']).get('original',{}).get('sha256')!=
                    '961e18a652ad91cbc0494111a435866e6414bdcaf327d028add2673329a7b9c2'
                or scope['failed_candidate_review']['sha256']!=
                    '5137791789fd295d2457ef8857bc92fbd279ef43237c66fb772270025bbf8caa'
                or read(scope['failed_candidate_review']).get('verdict')!='REJECT_AUTHOR_CANDIDATE_ONE_FORECAST'
                or context['prior_candidate']['source']['sha256']!=
                    'ef007c3b5a0366d6406c113aea1293c9d4d44ec310249febf727e9e5fbb2ea0c'
                or context['observations']['independent_review']!=scope['failed_candidate_review']
                or read(policy['continuation']['research_context'])!=context):
            raise ValueError('Exact approved20 allocation/latest18 source, rejection and delivered context required')
        if is_successor:
            successor=fresh.output_followthrough(policy) if is_output else fresh.successor(policy)
            closure=read(scope['closed_author_review'])
            reviewer=closure.get('reviewer')
            if (successor is None or scope.get('closed_author_review')!=(fresh.AUTHOR22_CLOSURE if is_output else fresh.AUTHOR20_CLOSURE)
                    or closure.get('verdict')!=('VERIFIED_AUTHOR22_OUTPUT_LIMIT_FAILURE_AND_ACCOUNTING_NO_RETRY'
                        if is_output else 'VERIFIED_AUTHOR20_CONTEXT_FAILURE_AND_ACCOUNTING_NO_RETRY')
                    or closure.get('blocking_findings')!=[] or type(reviewer) is not str
                    or not reviewer.strip() or reviewer.strip().lower() in {'root','/root'}
                    or scope.get('author_max_input_tokens')!=successor['author_max_input_tokens']):
                raise ValueError('Reviewed closed20 and approved Author24k successor required')
            if is_output and (type(scope.get('author_max_input_tokens')) is not int
                    or type(scope.get('author_max_output_tokens')) is not int
                    or scope['author_max_output_tokens']!=successor['author_max_output_tokens']):
                raise ValueError('Only the approved49152 Author output override is permitted')
    return scope


def prior(scope):
    """Verify immutable closed originals, not an obsolete-window live validator."""
    result=read(scope['parent_result']);audit=read(scope['parent_audit'])
    if (audit.get('verdict')!='PASS_ACTUAL_CONTROLLER_FEEDBACK_DELIVERY_ONLY'
            or audit.get('blocking_findings')!=[] or result.get('decision_applied') is not False):
        raise ValueError('Independently audited, unapplied Controller11 required')
    old=read(engine.pin(ROOT/'inputs'/scope['parent']/'handoff.json'))
    original=read(result['original'])
    packet_binding=engine.pin(ROOT/'attempts'/scope['parent']/'roles/controller-01/effective-input.json')
    packet=read(packet_binding)
    if (packet_binding['sha256']!=audit['actual_transport']['packet_sha256']
            or result['original']['sha256']!=audit['actual_transport']['numbered_alias_and_physical_response_sha256']
            or result['owner_terminal']['sha256']!=audit['result']['owner_terminal_sha256']
            or read(result['owner_terminal'])['status']!='COMPLETED_COMPONENT_CONTEXT'
            or old['old_selected']['sha256']!='056a372c51d3e2aceafe67e512da8ba5131d9e8864387053210f2af0d4227fbb'
            or old['old_owner']['sha256']!='fef78af81de387d2c6e6021c32e9d6d77325383e9d37901ea9b4469415767ee8'
            or read(old['old_owner'])['status']!='FAILED_NO_RETRY'):
        raise ValueError('Original Controller/closed owner/current09 source bindings differ')
    choice=parse_capacity_decision(original,packet)
    selected=read(old['old_selected']);native=read(old['old_native'])
    if (choice['axis']!='R' or choice['component']!='research_policy'
            or digest(engine.activation.pair(selected['manifest']))!=choice['parent_pair_sha256']
            or digest(native['micro_evolution']['active_pair'])!=choice['parent_pair_sha256']
            or native['micro_evolution']['pending'] is not None):
        raise ValueError('Exact current09 R parent and original Controller11 R decision required')
    selected_sources(old)
    return {'handoff':old,'decision':choice,'selected':selected,'packet':packet_binding}


def accounting(scope, ledger):
    with sqlite3.connect(Path(ledger).as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        if (db.execute('SELECT * FROM config').fetchall()!=[(1,200_000_000_000,100_000_000_000,0)]
                or history_snapshot(db,4283)!=fresh.BASELINE
                or history_snapshot(db,scope['opening_rows'])['rows_sha256']!=scope['opening_rows_sha256']
                or db.execute("SELECT 1 FROM requests WHERE status NOT IN ('settled','settled_upper_bound')").fetchone()):
            raise ValueError('Original settled ledger/caps/prefix required; never rebase credit')
        current=history_snapshot(db)
        if scope.get('allocation') is not None:
            if history_snapshot(db,scope['opening_rows'])!=scope['allocation']['opening']:
                raise ValueError('Allocated original opening changed; never refresh or refund')
        if scope.get('author_id')==fresh.AUTHOR24_IDS[0]:
            policy=fresh.policy()
            original=policy['continuation']['allocation']['opening']
            if history_snapshot(db,original['max_rowid'])!=original:
                raise ValueError('Original4955 allocation history must remain intact')
            if scope.get('forecast_id') in (fresh.FORECAST26_ID,fresh.FORECAST27_ID,fresh.FORECAST28_ID):
                previous=policy['continuation']['output_followthrough']['allocation']['opening']
                if history_snapshot(db,previous['max_rowid'])!=previous:
                    raise ValueError('Original5229 allocation history must remain intact')
            if scope.get('forecast_id')==fresh.FORECAST28_ID:
                previous=policy['forecast_recovery']['allocation']['opening']
                if history_snapshot(db,previous['max_rowid'])!=previous:
                    raise ValueError('Original5419 allocation and exhausted charges must remain intact')
    remaining=scope.get('continuation_cumulative_cap_nano_usd',10_000_000_000)-(current['charged_nano_usd']-fresh.BASELINE['charged_nano_usd'])
    if remaining<=0:raise ValueError('Existing continuation allowance consumed')
    return dict(current,remaining_nano_usd=remaining,pending=0)


def containers_remaining():
    """One original80-call envelope across both serial stages and offline cases."""
    scope=authority()
    roots=[ROOT/'attempts'/scope['author_id']/name for name in ('code','review-code','cold-probe-code')]
    roots.append(ROOT/'attempts'/scope['forecast_id']/'code')
    if scope.get('requires_cold_probe'):
        roots.extend(ROOT/'attempts/edgar-research-20261015-12'/name for name in ('code','review-code'))
    if scope['author_id'].endswith(('-16','-18')):
        roots.extend(ROOT/'attempts/edgar-research-20261015-14'/name
            for name in ('code','review-code','cold-probe-code'))
    if scope['author_id'].endswith('-18'):
        roots.extend(ROOT/'attempts/edgar-research-20261015-16'/name
            for name in ('code','review-code','cold-probe-code'))
    if scope['author_id'] in (fresh.AUTHOR20_IDS[0],fresh.AUTHOR22_IDS[0],fresh.AUTHOR24_IDS[0]):
        roots.extend(ROOT/'attempts'/('edgar-research-20261015-'+identifier)/name
            for identifier in ('14','16','18') for name in ('code','review-code','cold-probe-code'))
        roots.extend(ROOT/'attempts'/('edgar-research-20261015-'+identifier)/'code'
            for identifier in ('13','15','17','19'))
    if scope['author_id'] in (fresh.AUTHOR22_IDS[0],fresh.AUTHOR24_IDS[0]):
        roots.extend(ROOT/'attempts'/fresh.AUTHOR20_IDS[0]/name
            for name in ('code','review-code','cold-probe-code'))
        roots.append(ROOT/'attempts'/fresh.AUTHOR20_IDS[1]/'code')
    if scope['author_id']==fresh.AUTHOR24_IDS[0]:
        roots.extend(ROOT/'attempts'/fresh.AUTHOR22_IDS[0]/name
            for name in ('code','review-code','cold-probe-code'))
        roots.append(ROOT/'attempts'/fresh.AUTHOR22_IDS[1]/'code')
        if scope['forecast_id'] in (fresh.FORECAST26_ID,fresh.FORECAST27_ID,fresh.FORECAST28_ID):
            roots.append(ROOT/'attempts'/fresh.AUTHOR24_IDS[1]/'code')
        if scope['forecast_id'] in (fresh.FORECAST27_ID,fresh.FORECAST28_ID):
            roots.append(ROOT/'attempts'/fresh.FORECAST26_ID/'code')
        if scope['forecast_id']==fresh.FORECAST28_ID:
            roots.append(ROOT/'attempts'/fresh.FORECAST27_ID/'code')
    consumed=sum(len(list(path.glob('call-*'))) for path in roots if path.exists())
    if consumed>=80:raise ValueError('Original shared80 container allowance exhausted')
    return 80-consumed


def source_bindings(old, *, scope=None):
    names=set(old['sources'])|{str(Path(__file__).relative_to(e.REPO)),
        str(SCOPE.relative_to(e.REPO)),str(CONTEXT.relative_to(e.REPO))}
    if scope is not None and scope.get('forecast_id') in (fresh.FORECAST26_ID,fresh.FORECAST27_ID,fresh.FORECAST28_ID):
        names.add('tools/earnings_native_failure.py')
        if scope['forecast_id'] in (fresh.FORECAST27_ID,fresh.FORECAST28_ID):
            names.add('tools/earnings_candidate_transfer.py')
    result={name:engine.pin(e.REPO/name) for name in sorted(names)}
    approved={} if scope is None or scope['author_id']!=fresh.AUTHOR20_IDS[0] else {
        'tools/earnings_open_context.py':'07a655e977b084c1baed5e009aeed6159b4288cf5e90418d13282e848665725c',
        'tools/earnings_open_broker.py':'a2e6d408037a924d18cb881c404ad9169375ad460424a0375c806ab3316fdc88'}
    if scope is not None and scope['author_id']==fresh.AUTHOR22_IDS[0]:
        approved={
            'tools/earnings_open_context.py':'ab025592fab39640422fbcce6ac8e27d7f917d9552ba8fec04d07c3342da7bd8',
            'tools/earnings_open_resources.py':'2f2b646a77067ed72bfeb6f1511f0138de3a891715160f2704c4d04051616d27',
            'tools/earnings_open_broker.py':'a2e6d408037a924d18cb881c404ad9169375ad460424a0375c806ab3316fdc88'}
    if scope is not None and scope['author_id']==fresh.AUTHOR24_IDS[0]:
        approved={
            'tools/earnings_open_context.py':'ab025592fab39640422fbcce6ac8e27d7f917d9552ba8fec04d07c3342da7bd8',
            'tools/earnings_open_broker.py':'a2e6d408037a924d18cb881c404ad9169375ad460424a0375c806ab3316fdc88',
            'tools/earnings_open_resources.py':'864a0ab4c8326d7c4542b3355373c9ad25bf497609bcf0630424b42f62658032',
            'tools/earnings_capacity_runtime.py':'9b37f21dbbf4541a96b3029ccd772741fbe9daa8af113e013b248a91d560ff28',
            'tools/earnings_night_budget.py':'0167e78735d6d886c695b3cf4dedd81675b859f05c73fb17c1fa60dd3549f923'}
        if scope.get('forecast_id') in (fresh.FORECAST26_ID,fresh.FORECAST27_ID,fresh.FORECAST28_ID):
            approved['research/market_rsi/supervisor_harness/continuous_discovery_batch.py']='8bc7a9072d7f7f5d18f1f852bd0de9d0b288190c4e94c16b49c2ff61aee2d03b'
        if scope.get('forecast_id')==fresh.FORECAST28_ID:
            approved['tools/edgar_forecast_openai.py']='8bf7e32e7d3d4e73530b6458222a1ceb48add4ea3a18521aa7252282abaf0777'
    allowed=ALLOWED_CHANGED|({'tools/earnings_open_fresh_grant.py'} if approved else set())
    for name,binding in old['sources'].items():
        if name in approved:
            if result[name]['sha256']!=approved[name]:raise ValueError('Reviewed offline delivery source drift')
        elif name not in allowed and binding!=result[name]:
            raise ValueError('Undeclared original trusted source change: '+name)
    return result


def verify_sources(bindings,commit):
    for name,binding in bindings.items():
        if binding!=engine.pin(e.REPO/name):raise ValueError('Followthrough source drift')
        committed=subprocess.run(['git','show',commit+':'+name],cwd=e.REPO,
            check=True,capture_output=True).stdout
        if e.digest(committed)!=binding['sha256']:raise ValueError('Uncommitted followthrough source')


def candidate_gate(author_result, specification, review):
    """No candidate import/execution; review exact unchanged model business bytes."""
    chosen=author_result['decision'];original=read(author_result['original'])
    authored=author_payload(original)
    decoded=candidate(original,{'axis':'R'},chosen)
    cases=read(read(specification['static_review'])['program_cases'])
    rows=cases.get('cases')
    reviewer=review.get('reviewer')
    if (cases.get('passed') is not True or cases.get('source_sha256')!=decoded['source_sha256']
            or cases.get('error_type') is not None or type(rows) is not list
            or len(rows)!=len(decoded['cases'])
            or any(type(row) is not dict or row.get('passed') is not True for row in rows)
            or specification.get('review_receipt') is not None
            or specification['after']['components']['R']['sources']!={CHILD:decoded['source_sha256']}
            or review.get('verdict')!='PASS_AUTHOR_CANDIDATE_ONE_FORECAST'
            or review.get('blocking_findings')!=[] or type(reviewer) is not str
            or not reviewer.strip() or reviewer.strip().lower() in {'root','/root'}
            or review.get('author_original')!=author_result['original']
            or review.get('candidate_source_sha256')!=decoded['source_sha256']
            or review.get('test_source_sha256')!=decoded['test_source_sha256']):
        raise ValueError('Exact successful authored cases and distinct candidate review required')
    return authored,decoded


def prepare(stage):
    """Create each exact newID once. No owner, provider, candidate or scorer run."""
    if stage not in {'author','forecast'}:raise ValueError('Exact followthrough stage required')
    scope=authority()
    if scope['forecast_id'] in (fresh.FORECAST26_ID,fresh.FORECAST27_ID,fresh.FORECAST28_ID) and stage!='forecast':
        raise ValueError('Fresh26 is forecast-only; closed Author24 cannot be reopened')
    old=prior(scope);identifier=scope[stage+'_id']
    root=ROOT/'attempts'/identifier;home=ROOT/'inputs'/identifier
    original=read(old['handoff']['old_runtime']);old_episode=read(old['handoff']['old_episode'])
    grant=read(old_episode['grant'])
    accounting(scope,grant['ledger']);verify_current_python(grant['python'])
    native_paths=namespace.native_paths(root,identifier)
    claim=Path(grant['ledger']).parent/'.capacity-runtime-claims'/e.digest(identifier.encode())
    if (root.exists() or home.exists() or any(path.exists() for path in native_paths.values())
            or any(Path(str(claim)+suffix).exists() for suffix in ('.json','.result.json'))):
        raise FileExistsError('Consumed or partially prepared followthrough ID stays closed')
    if subprocess.run(['git','status','--porcelain'],cwd=e.REPO,check=True,capture_output=True).stdout:
        raise ValueError('Commit source and exact configuration before preparation')
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=e.REPO,check=True,capture_output=True,text=True).stdout.strip()
    bindings=source_bindings(old['handoff'],scope=scope);verify_sources(bindings,commit)
    candidate_fields={}
    if stage=='forecast':
        ar=engine.pin(ROOT/'attempts'/scope['author_id']/'author-result.json')
        spec=engine.pin(ROOT/'attempts'/scope['author_id']/'candidate-specification.json')
        cr=engine.pin(ROOT/('AUTHOR'+scope['author_id'].rsplit('-',1)[1]+'-CANDIDATE-REVIEW.json'))
        authored,decoded=candidate_gate(read(ar),read(spec),read(cr))
        if scope.get('requires_cold_probe'):
            probe_binding=engine.pin(ROOT/'attempts'/scope['author_id']/'cold-probe.json')
            cold_probe_check(probe_binding,read(ar))
            if read(cr).get('cold_probe')!=probe_binding:raise ValueError('Distinct exact cold-probe review required')
            candidate_fields['cold_probe']=probe_binding
        archive=e.REPO/'configs/earnings_coevolution/program_archive'/scope['author_id']
        for name,value in (('researcher.py',authored['source_text']),('cases.py',authored['test_text'])):
            if (archive/name).read_bytes()!=value.encode():raise ValueError('Candidate archive differs from exact Author')
            raw=subprocess.run(['git','show',commit+':'+str((archive/name).relative_to(e.REPO))],
                cwd=e.REPO,check=True,capture_output=True).stdout
            if raw!=value.encode():raise ValueError('Candidate must have its own exact Git checkpoint')
        candidate_fields.update({'author_result':ar,'candidate_specification':spec,'candidate_review':cr,
            'candidate_git_source':engine.pin(archive/'researcher.py'),'candidate_git_tests':engine.pin(archive/'cases.py')})
    home.mkdir(parents=True,exist_ok=False)
    save=lambda name,value:engine.save(home/name,value)
    grant=deepcopy(grant)
    grant.update(id=identifier,root=str(root),source_commit=commit,
        sources={name:value['sha256'] for name,value in bindings.items()},
        cutoff_utc=scope['window']['cutoff_utc'],deadline_utc=scope['window']['deadline_utc'])
    if scope['author_id'] in (fresh.AUTHOR20_IDS[0],fresh.AUTHOR22_IDS[0],fresh.AUTHOR24_IDS[0]):
        grant['additional_cap_nano_usd']=scope['continuation_cumulative_cap_nano_usd']
    fresh.validate(grant)
    granted=save('grant.json',grant)
    study=read(old_episode['study']);study.pop('program_lineage',None)
    study.update(new_live_grant=granted,new_episode_deadline=grant['deadline_utc'])
    study_binding=save('study.json',study)
    runtime=deepcopy(original)
    runtime.update(id=identifier,root=str(root),source_commit=commit,forecast_study=study_binding,
        cutoff_utc=grant['cutoff_utc'],deadline_utc=grant['deadline_utc'],
        slots={role:[str(root/'roles'/(role+'-01'))] for role in ('controller','author','review','forecast')},
        sources={**{name:engine.pin(path) for name,path in CORE.items()},'forecast_entry':engine.pin(e.__file__),
            'forecaster':engine.pin(e.REPO/'tools/edgar_forecast_openai.py'),
            **{'factory_'+role:engine.pin(assembly.__file__) for role in ('controller','author','review','forecast')}})
    if scope['author_id'] in (fresh.AUTHOR20_IDS[0],fresh.AUTHOR22_IDS[0],fresh.AUTHOR24_IDS[0]):
        runtime['additional_cap_nano_usd']=grant['additional_cap_nano_usd']
    if scope['author_id'] in (fresh.AUTHOR22_IDS[0],fresh.AUTHOR24_IDS[0]):
        runtime['limits']['author']['max_input_tokens']=scope['author_max_input_tokens']
    if scope['author_id']==fresh.AUTHOR24_IDS[0]:
        runtime['limits']['author']['max_output_tokens']=scope['author_max_output_tokens']
    runtime_binding=save('runtime.json',runtime);preflight_runtime(runtime_binding)
    transport=save('forecast-transport.json',{'schema':'edgar_foreground_slow_call_policy_v1',
        'source_commit':commit,'original_runtime_request_timeout_seconds':study['runtime_config']['request_timeout_seconds'],
        'effective_socket_timeout_seconds':600,'role_and_global_deadlines_unchanged':True,'retry_allowed':False})
    value={'schema':'earnings_author_followthrough_prepared_v1','stage':stage,
        'scope':engine.pin(SCOPE),'runtime':runtime_binding,'study':study_binding,'grant':granted,
        'source_commit':commit,'sources':bindings,'prior':old,'forecast_transport':transport,
        **candidate_fields,'provider_calls':0,'status':'AWAITING_DISTINCT_REVIEW'}
    if identifier in (fresh.FORECAST27_ID,fresh.FORECAST28_ID):
        record=transfer.derive(value['candidate_specification'],scope_binding=value['scope'],
            runtime_binding=value['runtime'],fixed_context=native_config(value)['fixed_context'])
        preview_candidate(value,record)
        value['candidate_transfer']=save('candidate-transfer.json',record)
    return save('prepared.json',value)


def validate_prepared(binding, review_binding):
    value=read(binding);scope=authority();stage=value['stage']
    runtime=preflight_runtime(value['runtime']);grant=read(value['grant'])
    old=value['prior']['handoff'];old_episode=read(old['old_episode'])
    original_grant=read(old_episode['grant']);original_runtime=read(old['old_runtime'])
    expected_limits=deepcopy(original_runtime['limits'])
    if scope['author_id'] in (fresh.AUTHOR22_IDS[0],fresh.AUTHOR24_IDS[0]):
        expected_limits['author']['max_input_tokens']=scope['author_max_input_tokens']
    if scope['author_id']==fresh.AUTHOR24_IDS[0]:
        expected_limits['author']['max_output_tokens']=scope['author_max_output_tokens']
    expected_study=read(old_episode['study']);expected_study.pop('program_lineage',None)
    expected_study.update(new_live_grant=value['grant'],new_episode_deadline=runtime['deadline_utc'])
    if (stage not in {'author','forecast'} or value['scope']!=engine.pin(SCOPE)
            or runtime['id']!=scope[stage+'_id'] or value['prior']!=prior(scope)
            or runtime['root']!=str(ROOT/'attempts'/runtime['id'])
            or value['sources']!=source_bindings(old,scope=scope)
            or grant['sources']!={name:bound['sha256'] for name,bound in value['sources'].items()}
            or any(grant[k]!=original_grant[k] for k in ('data','runtime','qa','scorer','python',
                'cik','ledger','baseline','human_authorization','allowed_egress','bootstrap_no_model_call'))
            or any(runtime[k]!=original_runtime[k] for k in ('rates','role_efforts'))
            or runtime['limits']!=expected_limits
            or runtime['slots']!={role:[str(Path(runtime['root'])/'roles'/(role+'-01'))]
                for role in ('controller','author','review','forecast')}
            or read(value['study'])!=expected_study
            or runtime['forecast_study']!=value['study'] or grant['source_commit']!=value['source_commit']
            or any(runtime[k]!=grant[k] for k in ('id','root','source_commit','ledger','baseline',
                'additional_cap_nano_usd','cutoff_utc','deadline_utc'))):
        raise ValueError('Exact new stage/task/model/window/ledger commitment required')
    fresh.validate(grant);verify_sources(value['sources'],value['source_commit'])
    accounting(scope,grant['ledger'])
    review=read(review_binding)
    reviewer=review.get('reviewer')
    if (review.get('verdict')!='PASS_AUTHOR_FOLLOWTHROUGH_STAGE' or review.get('blocking_findings')!=[]
            or type(reviewer) is not str or not reviewer.strip()
            or reviewer.strip().lower() in {'root','/root'} or review.get('prepared')!=binding
            or review.get('reviewed_sources')!=value['sources']):
        raise ValueError('Distinct exact prepared/source review before stage launch required')
    if runtime['id'] in (fresh.FORECAST27_ID,fresh.FORECAST28_ID):
        record=transfer.validate(value['candidate_transfer'],specification_binding=value['candidate_specification'],
            scope_binding=value['scope'],runtime_binding=value['runtime'],fixed_context=native_config(value)['fixed_context'])
        preview_candidate(value,record)
    return value,runtime


def native_config(value):
    """One exact configuration for both preflight projection and live Native."""
    runtime=read(value['runtime']);old=value['prior']
    baseline=old['selected']['manifest'];entries=old['selected']['entrypoints']
    return {'pair':engine.activation.pair(baseline),'fixed_context':{
        'model_sha256':baseline['M'],'evaluation_sha256':baseline['K'],
        'data_scope_sha256':digest(read(value['study'])['cases']),
        'authority_sha256':value['scope']['sha256'],'resource_policy_sha256':digest({
            key:runtime[key] for key in transfer.RESOURCE_FIELDS})},
        'allowed_write_paths':{'researcher':[entries['R'],CHILD],'harness':[entries['H']]},
        'protected_paths':sorted(name for axis in ('K','C') for name in baseline['components'][axis]['sources']),
        'reviewer_id':REVIEWER}


def preview_candidate(value, record):
    """Real pure Native reducer; no operational files, owner, or provider."""
    state=engine.activation.micro.initialize_micro_evolution(native_config(value))
    return engine.activation.micro.propose_micro_evolution(state,record['proposal'])


def native(value, *, create):
    runtime=read(value['runtime']);root=Path(runtime['root']);old=value['prior']
    selected=old['selected'];baseline=selected['manifest'];entries=selected['entrypoints']
    paths=namespace.native_paths(root,runtime['id'])
    source,registry=paths['source_root'],paths['registry_root']
    if create:
        source.mkdir(parents=True,exist_ok=False)
        origin=Path(old['handoff']['old_selected']['path']).parent.parent/'source'
        for part in baseline['components'].values():
            for name,token in part['sources'].items():
                save_bytes(source/name,e.checked({'path':str(origin/name),'sha256':token}))
    batch=ContinuousDiscoveryBatch(paths['batch_root'],allow_temporary=
        namespace.NATIVE_RUNTIME_ROOT!=Path.home()/'Library/Application Support/MarketRSI/co-evo-earnings/episodes')
    if create:
        batch.initialize(batch_id=runtime['id'],start_utc=authority()['window']['issued_utc'],
            deadline_utc=runtime['deadline_utc'],max_attempts=1,active_pool_capacity=2,learning_checkpoint_version=1,
            initial_incumbent={'candidate_id':'inherited-parent','candidate_sha256':baseline['C'],
                'scorecard_sha256':'0'*64,'review_sha256':'0'*64})
        micro=native_config(value)
        batch.record_micro_evolution('initialize',micro,expected_state_sha256=batch.snapshot()['state_sha256'])
    return ProgramCapacity(batch,source_root=source,registry_root=registry,baseline=baseline,entrypoints=entries)


def owner_terminal(runtime):
    bound=engine.pin(Path(runtime['ledger']).parent/'.capacity-runtime-claims'/(
        e.digest(runtime['id'].encode())+'.result.json'))
    if read(bound)['status']!='COMPLETED_COMPONENT_CONTEXT':raise ValueError('Exact stage owner did not close successfully')
    return bound


def archive(author_result):
    """Mechanical export of unchanged public Author code, never host execution."""
    result=read(author_result);value=read(result['prepared']);runtime=read(value['runtime'])
    if result['owner_terminal']!=owner_terminal(runtime):raise ValueError('Author owner not reconciled')
    candidate(read(result['original']),{'axis':'R'},result['decision'])
    authored=author_payload(read(result['original']))
    root=e.REPO/'configs/earnings_coevolution/program_archive'/authority()['author_id']
    root.mkdir(parents=True,exist_ok=False)
    for name,key in (('researcher.py','source_text'),('cases.py','test_text')):
        save_bytes(root/name,authored[key].encode())
    return {'source':engine.pin(root/'researcher.py'),'tests':engine.pin(root/'cases.py'),
        'author_original':result['original'],'source_modified_by_Root':False}


def run_author(prepared, review):
    value,runtime=validate_prepared(prepared,review)
    if value['stage']!='author':raise ValueError('Author stage required')
    root=Path(runtime['root']);root.mkdir(parents=True,exist_ok=False)
    _,clock=capture_or_load(root,{'source_commit':runtime['source_commit'],
        'new_request_cutoff_utc':runtime['cutoff_utc'],'deadline_utc':runtime['deadline_utc']})
    capacity=native(value,create=True)
    company,_=original_capacity.task(read(value['grant']))
    runner=DockerRunner(root/'code',max_calls=containers_remaining())
    broker=ResearchBroker(root/'research-actions',company=company,capacity=capacity,runner=runner,
        literature=LiteratureBroker(root/'literature',max_requests=8),
        trace_slots={'ordinary09':str(ROOT/'attempts/edgar-research-20261015-09/roles/forecast-01')},
        research_context_binding=engine.pin(CONTEXT))
    factories=assembly.followthrough_factories(enabled='author',broker=broker,study=value['study'],
        kernel={k:read(value['grant'])[k] for k in ('scorer','qa')},clock=clock,transport=value['forecast_transport'])
    chosen=value['prior']['decision']
    with open_capacity_runtime(value['runtime'],client_factory=assembly.provider_client,role_factories=factories) as owner:
        original=owner['roles']['author'](chosen,{'axis':'R'},runtime['slots']['author'][0])
        candidate(read(original),{'axis':'R'},chosen)
    return engine.save(root/'author-result.json',{'schema':'earnings_author_followthrough_result_v1',
        'prepared':prepared,'decision':chosen,'original':original,'owner_terminal':owner_terminal(runtime),
        'candidate_applied':False,'new_forecasts':0})


def materialize(author_result):
    """Offline unchanged-source cases; no owner/provider/adoption or parser edits."""
    result=read(author_result);value=read(result['prepared']);runtime=read(value['runtime'])
    if result['owner_terminal']!=owner_terminal(runtime):raise ValueError('Author owner not reconciled')
    original=read(result['original']);chosen=result['decision']
    decoded=candidate(original,{'axis':'R'},chosen)
    root=Path(runtime['root']);capacity=native(value,create=False);snapshot=capacity.batch.snapshot()
    slot=str(root/'roles/review-01')
    review=ProgramSourceReview(capacity.source_root,slots={slot:{'candidate_id':'followthrough-candidate',
        'R':CHILD,'H':'unused_harness_child.py'}},proposer_id='actual-model-author-'+runtime['id'],reviewer_id=REVIEWER,
        runner=DockerRunner(root/'review-code',max_calls=containers_remaining()))
    descriptor={'schema':'capacity_review_context_v1','decision_sha256':digest(chosen),
        'author_original':result['original'],'candidate':engine.save(root/'decoded-candidate.json',decoded),
        'parent_pair_sha256':chosen['parent_pair_sha256'],'parent_identity':capacity.baseline,
        'parent_entrypoints':capacity.initial_entrypoints,'state_sha256':snapshot['state_sha256'],
        'micro_evolution':snapshot['micro_evolution']}
    spec=review.review(chosen,original,descriptor,slot)
    return engine.save(root/'candidate-specification.json',spec)


def cold_payload(company):
    files=FilingTools(company).files
    return {'stage':'forecast','questions':files['questions.md'],
        'filing_index':files['filing_index.tsv'],'records':[]}


def cold_probe_check(binding,result):
    """Verify original executions and data, not an injected observation claim."""
    value=read(binding);prepared=read(result['prepared'])
    company,_=original_capacity.task(read(prepared['grant']))
    authored=author_payload(read(result['original']));payload=cold_payload(company)
    advice=researcher.verify(value['execution'],authored['source_text'],payload,company)
    rows=researcher.evidence_rows(value['execution'])
    if (value.get('author_original')!=result['original'] or value.get('payload')!=payload
            or value.get('source_sha256')!=e.digest(authored['source_text'].encode())
            or not any(row['request']['tool']=='read_file'
                and row['request']['arguments'].get('path','').startswith('filings/')
                and type(row['output']) is dict and bool(row['output'].get('text')) for row in rows)
            or type(advice) is not dict or type(advice.get('historical_cells')) is not list
            or not advice['historical_cells']):
        raise ValueError('Actual empty-state original read-to-parser proof required')
    return advice


def cold_probe(author_result):
    """One offline actual empty-state acquisition, no model/scorer/state edits."""
    result=read(author_result);prepared=read(result['prepared']);runtime=read(prepared['runtime'])
    if result['owner_terminal']!=owner_terminal(runtime):raise ValueError('Reconciled Author required')
    company,_=original_capacity.task(read(prepared['grant']))
    source=author_payload(read(result['original']))['source_text'];payload=cold_payload(company)
    root=Path(runtime['root'])
    runner=DockerRunner(root/'cold-probe-code',max_calls=containers_remaining())
    execution=researcher.run(runner,source,payload,FilingTools(company))
    binding=engine.save(root/'cold-probe.json',{'author_original':result['original'],
        'source_sha256':e.digest(source.encode()),'payload':payload,'execution':execution})
    cold_probe_check(binding,result)
    return binding


def run_forecast(prepared, review):
    value,runtime=validate_prepared(prepared,review)
    if value['stage']!='forecast':raise ValueError('Forecast stage required')
    authored,decoded=candidate_gate(read(value['author_result']),read(value['candidate_specification']),read(value['candidate_review']))
    if authority().get('requires_cold_probe'):
        cold_probe_check(value['cold_probe'],read(value['author_result']))
        if read(value['candidate_review']).get('cold_probe')!=value['cold_probe']:
            raise ValueError('Exact independently reviewed cold probe required')
    if e.checked(value['candidate_git_source'])!=authored['source_text'].encode():raise ValueError('Reviewed source drift')
    spec=read(value['candidate_specification']);proposal=spec['proposal']
    if runtime['id'] in (fresh.FORECAST27_ID,fresh.FORECAST28_ID):
        record=transfer.validate(value['candidate_transfer'],specification_binding=value['candidate_specification'],
            scope_binding=value['scope'],runtime_binding=value['runtime'],fixed_context=native_config(value)['fixed_context'])
        preview_candidate(value,record)
        proposal=record['proposal']
    root=Path(runtime['root']);root.mkdir(parents=True,exist_ok=False)
    _,clock=capture_or_load(root,{'source_commit':runtime['source_commit'],
        'new_request_cutoff_utc':runtime['cutoff_utc'],'deadline_utc':runtime['deadline_utc']})
    capacity=native(value,create=True);spec=read(value['candidate_specification'])
    save_bytes(capacity.source_root/CHILD,authored['source_text'].encode())
    before=capacity.batch.snapshot()
    capacity.propose(spec['after'],proposal,spec['entrypoints'],static_review=spec['static_review'],
        expected_state_sha256=before['state_sha256'])
    pending=capacity.batch.snapshot()['micro_evolution']['pending'];pair=digest(before['micro_evolution']['active_pair'])
    company,_=original_capacity.task(read(value['grant']))
    task=OpenTask();task.company=company;task.state_api=ResearchState(company,runtime['id'])
    task.kernel={k:read(value['grant'])[k] for k in ('scorer','qa')}
    initial=task.state_api.save(root/'initial-state',task.state_api.empty())
    runner=DockerRunner(root/'code',max_calls=containers_remaining())
    factories=assembly.followthrough_factories(enabled='forecast',broker=None,study=value['study'],
        kernel=task.kernel,clock=clock,transport=value['forecast_transport'])
    work_id='candidate-'+digest(prepared)
    claimed=False
    try:
        with open_capacity_runtime(value['runtime'],client_factory=assembly.provider_client,role_factories=factories) as owner:
            snap=capacity.batch.snapshot()
            capacity.batch.record_capacity_work('claim',work_id=work_id,pair_sha256=pair,
                evidence_sha256=digest({'prepared':prepared,'tested_pair':digest(pending['pair'])}),
                expected_state_sha256=snap['state_sha256'])
            claimed=True
            worker=ProgramWorker(company,runtime['id'],capacity,pair,root/'memory',initial,
                shadow_proposal_sha256=pending['record_sha256'],runner=runner)
            output=owner['roles']['forecast'](worker,runtime['slots']['forecast'][0])
            verified=task.shadow_execution(output,worker,runtime['slots']['forecast'][0],active_pair_sha256=pair,
                tested_pair_sha256=digest(pending['pair']),pending_proposal_sha256=pending['record_sha256'],initial_state=initial)
            measured=engine.save(root/'verified-forecast.json',verified)
        # Do not credit success before the owner's final settlement/guard exits.
        terminal=owner_terminal(runtime)
        snap=capacity.batch.snapshot()
        capacity.batch.record_capacity_work('complete',work_id=work_id,pair_sha256=pair,
            evidence_sha256=measured['sha256'],expected_state_sha256=snap['state_sha256'])
    except BaseException as failure:
        if claimed:
            try:
                earnings_native_failure.close_failed_work(capacity.batch,runtime_binding=value['runtime'],
                    work_id=work_id,pair_sha256=pair,output_root=root/'native-failure',error_type=type(failure).__name__)
            except BaseException as closure_error:
                try:
                    engine.save(root/'native-failure-unclosed.json',{
                        'schema':'earnings_native_failure_unclosed_v1','runtime':value['runtime'],
                        'work_id':work_id,'original_error_type':type(failure).__name__,
                        'closure_error_type':type(closure_error).__name__,'retry_allowed':False})
                except BaseException:
                    # Even a full disk must not replace the original failure.
                    failure.add_note('Native closure/diagnostic unavailable; claim may remain active. Inspect originals; no retry.')
        raise
    return engine.save(root/'followthrough-result.json',{'schema':'earnings_author_forecast_followthrough_v1',
        'prepared':prepared,'candidate_source_sha256':decoded['source_sha256'],'verified_forecast':measured,
        **({'candidate_transfer':value['candidate_transfer']} if runtime['id'] in (fresh.FORECAST27_ID,fresh.FORECAST28_ID) else {}),
        'owner_terminal':terminal,'native':engine.pin(capacity.batch.root/'batch.json'),
        'candidate_adopted':False,'claim':'One original scored candidate forecast; exact source use needs final audit. Not matched benefit or joint coevolution.'})


if __name__=='__main__':
    import argparse,json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare-author','prepare-forecast','author','archive','materialize','probe','forecast'])
    parser.add_argument('--prepared');parser.add_argument('--review');args=parser.parse_args()
    if args.action.startswith('prepare-'):result=prepare(args.action.split('-')[1])
    elif args.action in {'archive','materialize','probe'}:
        result={'archive':archive,'materialize':materialize,'probe':cold_probe}[args.action](
            engine.pin(ROOT/'attempts'/authority()['author_id']/'author-result.json'))
    else:
        if not args.prepared or not args.review:parser.error('Exact prepared and distinct review bindings required')
        result=(run_author if args.action=='author' else run_forecast)(engine.pin(args.prepared),engine.pin(args.review))
    print(json.dumps(result))
