"""Closed, unscored forecast delivery after a genuine accepted Review.

This is one source-bound provenance transaction, not a second research loop.
Original C/A and Review authorship stay separate; a failed forecast never
becomes a scored campaign or a reason to regenerate the successful code.
"""
from copy import deepcopy
from earnings_population_window import start_utc
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re

import earnings_population as pool
import earnings_population_continuation as history
import earnings_population_campaign_resume as resume
import earnings_population_recovery as recovery
import earnings_population_reused_review_failure as prior
import earnings_population_tasks as tasks
from earnings_native_failure import _cleanup, _owned_requests
from earnings_population_roles import message
from market_rsi import digest

MODE = 'reviewed_candidate_forecast_deadline_failure_v1'
REUSE = 'reuse_accepted_review_v1'


def _accepted(reader, attempt, runtime, terminal, output, authored):
    folder=attempt/'roles/review-01';bound=reader.pin(folder/'result.json')
    sealed=terminal['role_results']['review'];value=reader.read(bound)
    turns=value.get('turns');wall=value.get('wall_seconds')
    if (sealed != dict(binding=bound,value=value) or value.get('status')!='COMPLETED_REVIEW'
            or value.get('error_type') is not None or value.get('retry_allowed') is not False
            or type(turns)is not int or not 1<=turns<=8 or value.get('final_numbered_response')!=f'{turns:02d}-response.json'
            or type(wall)not in (int,float) or not math.isfinite(wall)
            or not 0<=wall<=runtime['limits']['review']['wall_seconds']
            or output.get('accepted_for_exploration') is not True):
        raise ValueError('Exact original completed accepted Review required')
    raw=reader.pin(folder/'response.json');numbered=reader.pin(folder/value['final_numbered_response'])
    projection=reader.pin(folder/'review.json');reviewed=reader.read(projection)
    business=message(reader.read(raw));child=authored['candidate']
    if (reader.read(raw)!=reader.read(numbered) or reviewed!=dict(original=raw,review=business)
            or type(business)is not dict or set(business)!={'candidate_id','accepted_for_exploration','rationale'}
            or business['candidate_id']!=child['id'] or business['accepted_for_exploration'] is not True
            or type(business['rationale'])is not str or not 1<=len(business['rationale'])<=1000
            or output['evidence'].count(raw)!=1):
        raise ValueError('Accepted Review must be the exact original public model business')
    outcome=output['evidence'][0];public=reader.read(outcome)
    if (outcome!=reader.pin(Path('/private/tmp')/('market-rsi-'+attempt.name)/'review-01-outcome.json')
            or public!=dict(schema='earnings_population_exploration_review_v1',**business)):
        raise ValueError('Original accepted Review outcome differs')
    return dict(schema='earnings_population_review_stage_reuse_v1',mode=REUSE,
        source_attempt=reader.pin(attempt/'population-run-failure.json'),candidate=deepcopy(child),
        scientific_decision_sha256=digest(authored['scientific_decision']),
        original_response=raw,review_projection=projection,role_result=bound,
        source_review_output=reader.pin(attempt/'loop/round-0001-source_review.done.json'),
        evidence=deepcopy(output['evidence']),new_model_Review_called=False),turns


def _forecast_result(reader, attempt, runtime, terminal):
    folder=attempt/'roles/forecast-01-00';bound=reader.pin(folder/'result.json');value=reader.read(bound)
    sealed=terminal['role_results']['forecast'];wall=value.get('wall_seconds')
    responses=sorted(folder.glob('[0-9][0-9]-response.json'));completed=len(responses)
    if (sealed!=dict(binding=bound,value=value) or value.get('status')!='FAILED_NO_RETRY'
            or value.get('error_type')!='BudgetStop' or value.get('retry_allowed') is not False
            or value.get('planned_targets')!=5 or type(value.get('scored_targets'))is not int or value['scored_targets']!=0
            or type(wall)not in (int,float) or not math.isfinite(wall) or not 0<wall<=runtime['limits']['forecast']['wall_seconds']
            or not 1<=completed<24 or [p.name for p in responses]!=[f'{i:02d}-response.json'for i in range(1,completed+1)]
            or set(folder.glob('[0-9][0-9]-request.json'))!={folder/f'{i:02d}-request.json'for i in range(1,completed+1)}
            or {p.name for p in (attempt/'roles').glob('forecast-*')}!={'forecast-01-00'}
            or any(list(attempt.rglob(name))for name in ('score.json','predictions.json','population-public-feedback.json','population-run-result.json'))):
        raise ValueError('Only exact unscored first-arm forecast delivery failure required')
    return completed,value


def _physical(reader, runtime, audit, review_count, forecast_count):
    """Reuse original Review verifier, then join every original forecast call."""
    from edgar_forecast_openai import token,unit
    snapshot=audit['checkpoints'][-1];owned=_owned_requests(runtime)
    rows=snapshot['requests'];expected={str(Path(runtime['root'])/'roles'/role/f'{n:02d}-request.json')
        for role,count in [('review-01',review_count),('forecast-01-00',forecast_count)]for n in range(1,count+1)}
    if (len(rows)!=len(expected) or len(owned)!=len(expected)
            or {r['binding']['path']for r in rows}!=expected or {r['request']['path']for r in owned}!=expected):
        raise ValueError('Only exact completed Review and failed-forecast owned requests required')
    # This derived subset selects original Review slots only; full original
    # accounting is independently verified below, never replaced by the subset.
    review_runtime=dict(runtime,slots={'review':runtime['slots']['review']})
    subset=dict(checkpoints=[dict(requests=[r for r in rows if r['role']=='review-01'],
        prepared_counts=snapshot['prepared_counts'])])
    evidence=prior._physical(reader,review_runtime,subset,review_count)
    folder=Path(runtime['root'])/'roles/forecast-01-00';rates=runtime['rates'];limits=runtime['limits']['forecast']
    rate=max(unit(rates[k])for k in ('input','cached','write')if rates[k]is not None)
    for own in owned:
        if Path(own['request']['path']).parent!=folder:continue
        row=next(r for r in rows if r['binding']==own['request']);number=Path(own['request']['path']).name[:2]
        request=reader.read(own['request']);payload=request['payload'];physical=row['physical']
        intent,raw,response,sidecar=[reader.read(physical[k])for k in ('intent','raw','numbered_response','sidecar')]
        count=reader.read(reader.pin(folder/(number+'-count.json')));origins=row['matching_actual_count_origins']
        if (row['role']!='forecast-01-00' or row['number']!=number or physical['failure']is not None
                or physical['numbered_response']!=reader.pin(folder/(number+'-response.json'))
                or Path(physical['intent']['path']).parent!=folder
                or physical['raw']['path']!=physical['intent']['path'].replace('.intent.json','.raw.bin')
                or physical['sidecar']['path']!=physical['intent']['path'].replace('.intent.json','.response.json')
                or physical['sidecar']['sha256']!=physical['numbered_response']['sha256']or sidecar!=response
                or intent.get('endpoint')!='/v1/responses'or intent.get('retry_allowed')is not False
                or intent.get('complete_reservation')!=request or intent.get('budget_request_id')!=own['request_id']
                or intent.get('request_receipt_sha256')!=own['request']['sha256']
                or intent.get('payload')!=dict(payload,max_output_tokens=limits['max_output_tokens'],service_tier='default',store=False)
                or {k:v for k,v in raw.items()if k!='_request_id'}!={k:v for k,v in response.items()if k!='_request_id'}
                or response.get('status')!='completed'or response.get('error')is not None or response.get('model')!=rates['api_model']or response.get('service_tier')!='default'
                or payload.get('model')!=rates['api_model']or payload.get('reasoning')!={'effort':runtime['role_efforts']['forecast']}
                or any(v.get('type')=='message'for v in response.get('output',[]))or len(origins)!=1):
            raise ValueError('Exact original nonfinal forecast physical payload/response required')
        origin=origins[0];count_intent=reader.read(origin)
        if (Path(origin['path']).parent!=folder or count_intent.get('endpoint')!='/v1/responses/input_tokens'
                or count_intent.get('payload')!=payload
                or reader.read(reader.pin(Path(origin['path'].replace('.intent.json','.raw.bin'))))!={k:v for k,v in count.items()if k!='_request_id'}):
            raise ValueError('Original forecast counted-payload transport differs')
        counted=token(count['input_tokens']);usage=response['usage'];inp,out,cached=token(usage['input_tokens']),token(usage['output_tokens']),token(usage['input_tokens_details']['cached_tokens'])
        charge=(inp-cached)*rate+cached*unit(rates['cached'])+out*unit(rates['output'])
        if (counted>limits['max_input_tokens']or inp>counted or cached>inp or out>limits['max_output_tokens']
                or token(usage['total_tokens'])!=inp+out or own['status']!='settled'
                or request['reserved_nano_usd']!=counted*rate+limits['max_output_tokens']*unit(rates['output'])
                or own['charged_nano_usd']!=charge or row['usage']['expected_conservative_charge_nano_usd']!=charge):
            raise ValueError('Original forecast count/reservation/settled usage differs')
        evidence += [own['request'],physical['intent'],physical['raw'],physical['numbered_response'],origin]
    return owned,evidence


def _native_failure(reader, native, runtime_bound, runtime, expected, resident, python, closure_bound, owner_bound, owned, *, claim_bound, cleanup):
    """Read/replay failed Native work; never call the mutating close routine."""
    from earnings_population_completed import _native_identity
    from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
    from supervisor_harness import capacity_feedback_engine as engine
    paths=sorted(native.glob('*/context.json'))
    if {p.parent.name for p in paths}!=set(expected):
        raise ValueError('Exact original role and first-arm Native context set required')
    closure=reader.read(closure_bound);failure=reader.read(closure['failure_evidence'])
    if (closure.get('schema')!='earnings_native_failure_closure_v1'or closure.get('status')!='FAILED_WORK_CLOSED_NO_RETRY'
            or closure.get('runtime')!=runtime_bound or closure.get('owner_terminal')!=owner_bound
            or closure.get('candidate_adopted')is not False or closure.get('retry_allowed')is not False
            or closure.get('own_request_count')!=len(owned)or closure.get('own_charge_nano_usd')!=sum(r['charged_nano_usd']for r in owned)
            or failure.get('owned_requests')!=owned or failure.get('runtime')!=runtime_bound
            or failure.get('owner_terminal')!=owner_bound or failure.get('owner_claim')!=claim_bound
            or failure.get('candidate_adopted')is not False or failure.get('retry_allowed')is not False
            or failure.get('error_type')!='LoopHalted' or failure.get('cleanup')!=cleanup
            or any(failure.get(k)!=closure[k]for k in ('work_id','pair_sha256','before_native_snapshot','before_native_journal'))):
        raise ValueError('Original failed Native work accounting/runtime differs')
    evidence=[closure_bound,closure['failure_evidence']];start=start_utc(runtime)
    for path in paths:
        name=path.parent.name
        selected=expected[name];value=reader.read(reader.pin(path))
        if (value.get('schema')!='earnings_population_native_case_v1'or value.get('authority')!=runtime_bound or value.get('source_commit')!=runtime['source_commit']
                or value.get('pool_version')!=selected['version']or value.get('company',{}).get('cik')!=resume.COMPANY
                or value.get('window')!=dict(start_utc=start,deadline_utc=runtime['deadline_utc'])
                or str(Path(runtime['root'])/'roles'/name)not in runtime['slots'][selected['role']]):
            raise ValueError('Original failed-work Native role/source/company/window differs')
        fixed=_native_identity(reader,path,value,selected,runtime_bound,runtime,resident,python)
        batch=ContinuousDiscoveryBatch(path.parent/'batch',allow_temporary=True)
        with os.fdopen(os.open(batch.lock_path,os.O_RDONLY|os.O_NOFOLLOW),'rb')as stream:
            fcntl.flock(stream,fcntl.LOCK_SH|fcntl.LOCK_NB)
            records=batch._read_records();saved=batch._read_snapshot();replayed=batch._replay(records)
        if (saved!=replayed or not saved['initialized']or saved['active_attempt_ids']or saved['active_attempt_id']is not None
                or saved['attempts_claimed']!=0 or saved['micro_evolution']['pending']is not None
                or saved['micro_evolution']['active_pair']!=engine.activation.pair(value['manifest'])or saved['micro_evolution']['fixed_context']!=fixed):
            raise ValueError('Original Native source context is not durably idle')
        works=saved.get('capacity_work',[])
        if selected['role']!='forecast':
            if works:raise ValueError('Reused nonforecast Native role cannot own forecast work')
        else:
            slot=Path(runtime['root'])/'roles'/name;pair=digest(engine.activation.pair(value['manifest']))
            expected_work=dict(work_id='capacity-'+digest([str(slot),selected['version']['id'],resume.COMPANY])[:32],
                pair_sha256=pair,evidence_sha256=digest(dict(context=reader.pin(path),slot=str(slot),version=selected['version'])),
                status='failed',failure_evidence_sha256=closure['failure_evidence']['sha256'])
            before=reader.read(closure['before_native_snapshot']);after=reader.read(closure['after_native_snapshot']);prefix=reader.read(closure['before_native_journal'])
            if (len(works)!=1 or any(works[0].get(k)!=v for k,v in expected_work.items())or closure['work_id']!=expected_work['work_id']
                    or closure['pair_sha256']!=pair or after!=saved or len(records)!=len(prefix)+1
                    or [reader.pin(batch.journal_dir/f'{i:08d}.json')for i in range(1,len(prefix)+1)]!=prefix
                    or batch._replay(records[:-1])!=before or records[-1]['event']!='capacity_work_failed'
                    or records[-1]['payload']['evidence_sha256']!=closure['failure_evidence']['sha256']
                    or any(after[k]!=before[k]for k in ('attempts_claimed','branches','incumbent','micro_evolution'))):
                raise ValueError('Exact original first-arm claim/failure journal required')
            evidence += [closure[k]for k in ('before_native_snapshot','after_native_snapshot','before_native_journal')]
        evidence += [reader.pin(path),reader.pin(batch.snapshot_path)]
    return evidence


def reuse_receipt(review, authored, child, slot):
    """Validate the current receiver against the independently verified bundle."""
    from supervisor_harness import capacity_feedback_engine as engine
    fields={'schema','mode','source_attempt','candidate','scientific_decision_sha256','original_response',
        'review_projection','role_result','source_review_output','evidence','new_model_Review_called'}
    if (set(review)!=fields or review.get('schema')!='earnings_population_review_stage_reuse_v1'or review.get('mode')!=REUSE
            or review.get('new_model_Review_called')is not False or review.get('candidate')!=child
            or authored.get('candidate')!=child or review.get('scientific_decision_sha256')!=digest(authored['scientific_decision'])):
        raise ValueError('Exact independently verified accepted Review reuse required')
    raw=engine.read(review['original_response']);business=message(raw);projection=engine.read(review['review_projection'])
    done=engine.read(review['source_review_output'])['output'];role=engine.read(review['role_result'])
    original=Path(review['source_attempt']['path']).parent/'roles/review-01'
    if (business.get('candidate_id')!=child['id']or business.get('accepted_for_exploration')is not True
            or projection!=dict(original=review['original_response'],review=business)
            or done!=dict(accepted_for_exploration=True,evidence=review['evidence'])
            or role.get('status')!='COMPLETED_REVIEW'or role.get('error_type')is not None or role.get('retry_allowed')is not False
            or any(Path(review[key]['path'])!=original/name for key,name in (
                ('original_response','response.json'),('review_projection','review.json'),('role_result','result.json')))
            or Path(review['source_review_output']['path'])!=original.parent.parent/'loop/round-0001-source_review.done.json'):
        raise ValueError('Original accepted Review business/evidence changed')
    return dict(schema='earnings_population_Review_stage_reuse_v1',mode=REUSE,
        new_model_called=False,routing_author='trusted_recovery_adapter',current_slot=str(slot),
        source_attempt=deepcopy(review['source_attempt']),candidate_id=child['id'],
        scientific_decision_sha256=review['scientific_decision_sha256'],
        original_response=deepcopy(review['original_response']),review_projection=deepcopy(review['review_projection']),
        role_result=deepcopy(review['role_result']),source_review_output=deepcopy(review['source_review_output']),
        evidence=deepcopy(review['evidence']),
        qualification='Original accepted research-code Review under its original closing policy; not a new Review, adoption, score or review of a later forecast-closing policy.')


def verify_reused_review(reader,attempt,rows,origin):
    review=origin.get('review_stage_reuse')
    if review is None:return
    folder=attempt/'roles/review-01';bound=reader.pin(folder/'review-stage-reuse.json')
    expected=reuse_receipt(review,origin['author_stage_reuse'],rows['implement']['candidate'],folder)
    if (reader.read(bound)!=expected or rows['source_review']!=dict(accepted_for_exploration=True,evidence=[bound,*review['evidence']])
            or any((folder/name).exists()for name in ('response.json','review.json','result.json'))
            or list(folder.glob('http-*'))or list(folder.glob('[0-9][0-9]-request.json'))):
        raise ValueError('Durable honest accepted-Review reuse/no-model receipt differs')


def load(binding,*,root,ledger,repo,plan):
    from earnings_population_budget import AUTHORIZATION,amendment_binding
    from earnings_population_completed import _literal,_budget
    if (type(binding)is not dict or set(binding)!={'path','sha256'}or type(binding.get('path'))is not str
            or type(binding.get('sha256'))is not str or re.fullmatch('[0-9a-f]{64}',binding['sha256'])is None):
        raise ValueError('Exact failed forecast binding required before read')
    root,ledger,repo=map(Path,(root,ledger,repo));path=Path(binding['path']);ident=path.parent.name
    if (root!=resume.OWNED or ledger!=resume.LEDGER or repo!=resume.REPO or any(p.resolve()!=p for p in (root,ledger,repo,path))
            or path!=root/'attempts'/ident/'population-run-failure.json'or re.fullmatch('edgar-population-20261016-[0-9]{2}',ident)is None
            or plan.get('id')!='earnings-population-review-recovery-20261016'or plan.get('human_authorization')!=AUTHORIZATION
            or plan.get('recovery_mode')!=MODE or plan.get('failed_attempt')!=binding):
        raise ValueError('Exact source-bound closed forecast-recovery authority required')
    audit_bound,delivery_bound=plan['closed_failure_audit'],plan['stage_delivery_audit']
    if any(Path(b['path']).parent!=root for b in (audit_bound,delivery_bound)):raise ValueError('Owned original closure/delivery audits required')
    attempt=path.parent;reader=history._Reader(root,ledger,repo,ident);registry=ledger.parent/'.capacity-runtime-claims';stamp=hashlib.sha256(ident.encode()).hexdigest()
    owner_bound,claim_bound=[reader.pin(registry/(stamp+suffix))for suffix in ('.result.json','.json')]
    reader.extra.update(Path(b['path'])for b in (owner_bound,claim_bound,audit_bound,delivery_bound))
    owner,claim,audit,delivery=[reader.read(b)for b in (owner_bound,claim_bound,audit_bound,delivery_bound)]
    runtime_bound=owner['runtime'];runtime=reader.read(runtime_bound);failure=reader.read(binding)
    if (runtime.get('id')!=ident or runtime.get('schema')!='earnings_population_runtime_v1'or runtime.get('root')!=str(attempt)
            or runtime.get('ledger')!=str(ledger)or runtime.get('companies')!=[resume.COMPANY]
            or runtime.get('budget_amendment')!=amendment_binding()or re.fullmatch('[0-9a-f]{40}',runtime.get('source_commit',''))is None
            or owner.get('status')!='FAILED_NO_RETRY'or owner.get('error_type')!='LoopHalted'or owner.get('retry_allowed')is not False
            or claim.get('runtime')!=runtime_bound or claim.get('id')!=ident or claim.get('source_commit')!=runtime['source_commit']
            or claim.get('retry_allowed')is not False or failure!=dict(status='FAILED_NO_RETRY',error_type='LoopHalted',native_closure=reader.pin(attempt/'native-failure/result.json'),retry_allowed=False)):
        raise ValueError('Exact closed first-forecast owner/runtime/failure required')
    reader.register_sources(runtime)
    reader.extra.update(Path(runtime[k]['path'])for k in ('review','budget_amendment'))
    study=reader.read(runtime['forecast_study']);inherited=recovery._capacity_origin(reader,runtime,study,root=root,ledger=ledger,repo=repo)
    authored=inherited.get('author_stage_reuse')
    if (type(authored)is not dict or authored.get('mode')!=recovery.REVIEW_REUSE or authored.get('implementation_base')is None
            or authored.get('new_model_Controller_called')is not False or authored.get('new_model_Author_called')is not False
            or inherited.get('review_stage_reuse')is not None or inherited.get('controller_stage_import')is not None):
        raise ValueError('Original independently replayed C/A reuse without a fabricated prior Review required')
    resident=tasks.resident(resume.COMPANY);reader.extra.update(Path(b['path'])for b in (tasks.FULL_PLAN,tasks.SCORER,resident['kernel']['qa']))
    if (study.get('data')!=tasks.FULL_PLAN or study.get('scorer')!=tasks.SCORER or study.get('runtime_config')!=resident['runtime']
            or study.get('cases')!=[resident['case']]or runtime['rates']!=resident['runtime']['models']['gpt-6.1-sol']):
        raise ValueError('Unchanged original development data/scorer/model required')
    reader.scan(runtime);reader.scan(study);review_config=reader.read(runtime['review']);clock=reader.pair(attempt/'clock.json')
    if (review_config.get('verdict')!='PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY'or review_config.get('blocking_findings')!=[]
            or review_config.get('source_commit')!=reader.commit or review_config.get('reviewed_configuration_sha256')!=digest({k:v for k,v in runtime.items()if k!='review'})
            or clock!=reader.read(owner['clock'])or clock.get('source_commit')!=reader.commit
            or clock.get('cutoff_utc')!=runtime['cutoff_utc']or clock.get('deadline_utc')!=runtime['deadline_utc']):
        raise ValueError('Original independently reviewed source/clock differs')
    terminal=audit['terminal_evidence'];observed=delivery.get('runtime',{})
    if (audit.get('schema')!='earnings_population_live_closure_audit_v1'or audit.get('status')!='SEALED_TERMINAL_FORECAST_WALL_DELIVERY_FAILURE_ALL_FEES_SETTLED'
            or audit.get('attempt_id')!=ident or audit.get('source_commit')!=reader.commit or audit.get('runtime')!=runtime_bound
            or str(audit.get('auditor','')).lower()in {'','root','/root'}or terminal['owner']!=dict(binding=owner_bound,value=owner)
            or terminal['failure']['binding']!=binding or terminal['failure']['value']!=failure
            or terminal['native_closure']['binding']!=failure['native_closure']or terminal['native_closure']['value']!=reader.read(failure['native_closure'])
            or delivery.get('schema')!='earnings_population_live_role_links_audit_v1'
            or delivery.get('status')!='SEALED_FAILED_FIXED_CONTROL_FORECAST_COMPANY_DEADLINE_REVIEW_ACCEPTED_NO_SCORES'
            or delivery.get('attempt_id')!=ident or delivery.get('source_commit')!=reader.commit
            or {k:observed.get(k)for k in ('path','sha256')}!=runtime_bound or type(observed.get('run_closed'))is not bool
            or delivery['actual']['failure']['failure']['binding']!=binding
            or delivery['actual']['failure']['forecast_result']['binding']!=terminal['role_results']['forecast']['binding']):
        raise ValueError('Exact sealed forecast deadline closure/delivery required')
    seed,outputs,evidence=recovery._prefix(reader,runtime,attempt,failed_stage='execute');recovery.verify_reused_stages(reader,attempt,outputs,inherited)
    state=pool.validate(inherited['population']);child=authored['candidate'];chosen=reader.read(outputs['controller']['decision'])
    if (seed['population']!=state or reader.read(seed['feedback'])!=inherited['research_feedback']or seed['last_scored_feedback']!=inherited['last_scored_feedback']
            or outputs['implement']['candidate']!=child or child['id']in state['versions']or child['parent']not in [state['stable_id'],*state['explorers']]):
        raise ValueError('Original unchanged scientific pool/feedback/unadopted child required')
    if plan.get('successful_candidate')!=dict(id=child['id'],source_sha256=authored['source']['sha256'],tests_sha256=authored['tests']['sha256'],raw_patch_sha256=authored['raw_patch_response']['sha256'],assembly_sha256=authored['assembly']['sha256']):
        raise ValueError('Source-bound successful Author identities differ')
    accepted,review_count=_accepted(reader,attempt,runtime,terminal,outputs['source_review'],authored)
    public=delivery['actual']['completed_review']
    if public['review']['binding']!=accepted['review_projection']or public['role_result']['binding']!=accepted['role_result']:
        raise ValueError('Sealed role delivery must identify the exact accepted original Review')
    count,forecast_result=_forecast_result(reader,attempt,runtime,terminal)
    native=Path('/private/tmp')/('market-rsi-'+ident);probes,fresh=prior._fresh_evidence(reader,native,authored,resident)
    if any(outputs['source_review']['evidence'].count(b)!=1 for b in fresh):raise ValueError('Accepted Review lost its actual financial case/probe evidence')
    cleanup=_cleanup(attempt)
    if [r['result']for r in cleanup]!=[r['result']for r in terminal['code_cleanup_receipts']]:raise ValueError('Original isolated cleanup set differs')
    owned,physical=_physical(reader,runtime,audit,review_count,count);evidence+=fresh+physical+_budget(reader,runtime,owner,dict(budget=owner['budget_summary']))
    selected=deepcopy(state)
    if chosen.get('retire_branch_id')is not None:selected=pool.retire(selected,chosen['retire_branch_id'],reason=chosen['hypothesis'],evidence=[outputs['controller']['decision']])
    selected=pool.retain(selected,child,reason=chosen['hypothesis'],evidence=outputs['source_review']['evidence'])
    if reader.read(reader.pin(attempt/'frozen-pool-01.json'))!=selected:raise ValueError('Original temporary forecast selection differs')
    campaign=reader.read(study['campaign']);baseline=state['versions'][campaign['baseline_version_id']]
    expected={name:dict(role=role,round_index=1,company_id=resume.COMPANY,version=version)for name,role,version in (
        ('controller-01','controller',state['versions'][state['stable_id']]),('author-01','author',state['versions'][child['parent']]),
        ('review-01','review',child),('forecast-01-00','forecast',baseline))}
    evidence+=_native_failure(reader,native,runtime_bound,runtime,expected,resident,
        _literal(reader,runtime['sources']['tools/earnings_population_run.py'],'PYTHON'),failure['native_closure'],owner_bound,owned,
        claim_bound=claim_bound,cleanup=cleanup)
    result=deepcopy(inherited);result['review_stage_reuse']=accepted
    result['recovery_context']=dict(schema='earnings_population_delivery_failure_v1',mode=MODE,failed_attempt=deepcopy(binding),audit=audit_bound,
        stage='execute',error_type='BudgetStop',company_wall_seconds=runtime['limits']['forecast']['wall_seconds'],
        observed_wall_seconds=forecast_result['wall_seconds'],completed_forecast_generations=count,review_assessment='accepted_for_exploration',
        score_state='unscored',candidate_id=child['id'],probes=probes,previous_delivery_failure=deepcopy(inherited.get('recovery_context')),
        scope='Original accepted Review permits exploration only. First fixed-control forecast expired without predictions/score; original C/A/Review are explicitly reused, all three forecast arms must run fresh under the prospective closing policy.')
    result['evidence']+=[binding,audit_bound,delivery_bound,owner_bound,claim_bound,runtime_bound,*accepted['evidence'],
        accepted['review_projection'],accepted['role_result'],accepted['source_review_output'],*[r['result']for r in cleanup],*evidence]
    return result
