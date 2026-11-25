"""Verify an input-failed re-Review without re-authoring or adopting its code.

The original Author/Controller reuse bundle is independently replayed first.
Only the latest closed delivery diagnosis changes; no failed result is turned
into a completed campaign, quality verdict, score or a new model response.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

import earnings_population as pool
import earnings_population_continuation as history
import earnings_population_campaign_resume as resume
import earnings_population_recovery as recovery
import earnings_population_tasks as tasks
from earnings_native_failure import _cleanup, _owned_requests
from market_rsi import digest

MODE = 'review_reused_candidate_input_failure_v1'


def _attach(inherited, binding, *, audit, completed, limit, counts, probes, evidence):
    result=deepcopy(inherited);child=inherited['author_stage_reuse']['candidate']
    result['recovery_context']=dict(schema='earnings_population_delivery_failure_v1',failed_attempt=deepcopy(binding),audit=audit,
        candidate_id=child['id'],stage='source_review',error_type='BudgetStop',observed_input_tokens=deepcopy(counts),
        prior_input_limit=limit,review_assessment='not_completed',completed_Review_generations=completed,
        score_state='unscored',probes=deepcopy(probes),
        scope='Original successful Author/Controller stages are unchanged and explicitly reused. Latest genuine Review stopped at input packing, not a quality verdict or score. Fresh Review/tests/forecasts remain mandatory.')
    result['evidence']+=deepcopy(evidence)
    return result


def _review_result(reader, attempt, runtime, terminal):
    rows = terminal['roles']; folder = attempt/'roles/review-01'
    if (len(rows) != 1 or rows[0]['role'] != 'review-01'
            or rows[0]['binding'] != reader.pin(folder/'result.json')
            or rows[0]['value'] != reader.read(rows[0]['binding'])):
        raise ValueError('Exactly one original genuine Review result required')
    value = rows[0]['value']; last = value.get('final_numbered_response','')
    if (re.fullmatch('[0-9]{2}-response.json',last) is None
            or value.get('status') != 'FAILED_NO_RETRY' or value.get('error_type') != 'BudgetStop'
            or value.get('retry_allowed') is not False or type(value.get('turns')) is not int
            or not 2 <= value['turns'] <= 8 or int(last[:2])+1 != value['turns']
            or not 0 <= value.get('wall_seconds',-1) < runtime['limits']['review']['wall_seconds']):
        raise ValueError('Original next-turn Review packing failure, not a wall or quality outcome, required')
    blocked = value['turns']; completed = blocked-1
    if (any((folder/name).exists() for name in (f'{blocked:02d}-request.json',f'{blocked:02d}-response.json','review.json'))
            or reader.read(reader.pin(folder/'response.json')) != reader.read(reader.pin(folder/last))):
        raise ValueError('Only the unchanged latest tool-reply alias and no final Review verdict required')
    final = reader.read(reader.pin(folder/last))
    if final.get('status') != 'completed' or not any(x.get('type') == 'function_call' for x in final.get('output',[])):
        raise ValueError('Last completed Review must be a tool request, not a quality verdict')
    return completed, blocked


def _blocked_counts(reader, attempt, runtime, terminal, completed, blocked):
    folder = attempt/'roles/review-01'; prefix=f'{blocked:02d}-context-'
    rows = terminal['review_input_failure']
    originals = set(folder.glob(prefix+'*.json'))-set(folder.glob(prefix+'*-count.json'))
    if (not rows or len(rows) != len(originals) or {Path(r['context']['path']) for r in rows} != originals
            or {Path(r['count']['path']) for r in rows} != set(folder.glob(prefix+'*-count.json'))):
        raise ValueError('Exact complete blocked Review preparation/count set required')
    intents = [(reader.pin(p),reader.read(reader.pin(p))) for p in folder.glob('http-*.intent.json')]
    if len([v for _,v in intents if v.get('endpoint') == '/v1/responses']) != completed:
        raise ValueError('Blocked Review cannot have a new generation intent')
    counts=[]
    for row in rows:
        context, count = reader.read(row['context']), reader.read(row['count'])
        matches = [(b,v) for b,v in intents if v.get('endpoint') == '/v1/responses/input_tokens'
            and hashlib.sha256(json.dumps(v['payload'],sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
                == context.get('effective_request_sha256')]
        if (context != row['preparation'] or context.get('schema') != 'earnings_context_preparation_v1'
                or context.get('generation_not_sent') is not True or type(context.get('max_input_tokens')) is not int
                or context['max_input_tokens'] != runtime['limits']['review']['max_input_tokens']
                or type(count.get('input_tokens')) is not int or count['input_tokens'] <= context['max_input_tokens']
                or row['input_tokens'] != count['input_tokens'] or len(matches) != 1
                or row['count']['path'] != row['context']['path'].replace('.json','-count.json')):
            raise ValueError('Original strict overflowing Review count required')
        bound, intent = matches[0]; payload = intent['payload']
        if (payload.get('model') != runtime['rates']['api_model'] or intent.get('retry_allowed') is not False
                or payload.get('reasoning') != {'effort':runtime['role_efforts']['review']}
                or history.e.strict_json(payload['input'][0]['content']) != reader.read(reader.pin(folder/'effective-input.json'))
                or reader.read(reader.pin(Path(bound['path'].replace('.intent.json','.raw.bin')))) !=
                    {k:v for k,v in count.items() if k != '_request_id'}):
            raise ValueError('Original blocked Review payload/count transport differs')
        counts.append(count['input_tokens'])
    return counts


def _physical(reader, runtime, audit, completed):
    """Only genuine Review calls are billed; reused C/A have no HTTP originals."""
    from edgar_forecast_openai import token, unit
    attempt=Path(runtime['root']); folder=attempt/'roles/review-01'; snapshot=audit['checkpoints'][-1]
    rows, prepared, owned = snapshot['requests'], snapshot['prepared_counts'], _owned_requests(runtime)
    expected={str(folder/f'{n:02d}-request.json') for n in range(1,completed+1)}
    if (len(rows) != completed or len(prepared) != completed or len(owned) != completed
            or {r['binding']['path'] for r in rows} != expected or {r['request']['path'] for r in owned} != expected):
        raise ValueError('Only exact original settled Review generations required')
    evidence=[]; limits=runtime['limits']['review']; rates=runtime['rates']
    for own in owned:
        row=next(r for r in rows if r['binding'] == own['request']); number=Path(own['request']['path']).name[:2]
        request=reader.read(own['request']); payload=request['payload']; physical=row['physical']
        intent, raw, response, sidecar = [reader.read(physical[k]) for k in ('intent','raw','numbered_response','sidecar')]
        count_bound=reader.pin(folder/(number+'-count.json')); counted=reader.read(count_bound)
        if (row['role'] != 'review-01' or row['number'] != number or physical['failure'] is not None
                or physical['numbered_response'] != reader.pin(folder/(number+'-response.json'))
                or Path(physical['intent']['path']).parent != folder
                or physical['raw']['path'] != physical['intent']['path'].replace('.intent.json','.raw.bin')
                or physical['sidecar']['path'] != physical['intent']['path'].replace('.intent.json','.response.json')
                or physical['sidecar']['sha256'] != physical['numbered_response']['sha256'] or sidecar != response
                or intent.get('endpoint') != '/v1/responses' or intent.get('retry_allowed') is not False
                or intent.get('complete_reservation') != request or intent.get('budget_request_id') != own['request_id']
                or intent.get('request_receipt_sha256') != own['request']['sha256']
                or intent.get('payload') != dict(payload,max_output_tokens=limits['max_output_tokens'],service_tier='default',store=False)
                or {k:v for k,v in raw.items() if k != '_request_id'} != {k:v for k,v in response.items() if k != '_request_id'}
                or response.get('status') != 'completed' or response.get('error') is not None
                or response.get('model') != rates['api_model'] or response.get('service_tier') != 'default'
                or payload.get('model') != rates['api_model'] or payload.get('reasoning') != {'effort':runtime['role_efforts']['review']}
                or history.e.strict_json(payload['input'][0]['content']) != reader.read(reader.pin(folder/'effective-input.json'))):
            raise ValueError('Exact original physical Review payload/model/raw/response required')
        count=token(counted['input_tokens']);usage=response['usage']
        inp,out,cached=token(usage['input_tokens']),token(usage['output_tokens']),token(usage['input_tokens_details']['cached_tokens'])
        rate=max(unit(rates[k]) for k in ('input','cached','write') if rates[k] is not None)
        charge=(inp-cached)*rate+cached*unit(rates['cached'])+out*unit(rates['output'])
        if (count > limits['max_input_tokens'] or inp > count or cached > inp or out > limits['max_output_tokens']
                or token(usage['total_tokens']) != inp+out or own['status'] != 'settled'
                or request['reserved_nano_usd'] != count*rate+limits['max_output_tokens']*unit(rates['output'])
                or own['charged_nano_usd'] != charge or row['usage']['expected_conservative_charge_nano_usd'] != charge):
            raise ValueError('Original Review count/reservation/usage/settlement differs')
        matches=[r for r in prepared if r['role'] == 'review-01' and r['number'] == number]
        if len(matches) != 1:raise ValueError('One original Review count handoff required')
        prep=matches[0];reused=reader.read(prep['reuse_binding']);marker=reader.read(prep['consumed_marker']['binding'])
        if (prep['actual_generation_request'] != own['request'] or prep['actual_generation_completed'] is not True
                or prep['reuse_binding'] != reader.pin(folder/(number+'-prepared-count-reuse.json'))
                or reused.get('schema') != 'earnings_prepared_count_handoff_v1' or reused.get('slot') != str(folder)
                or type(reused.get('turn')) is not int or reused['turn'] != int(number)
                or reused.get('new_count_http_request') is not False or reused.get('reused_original_provider_count') is not True
                or reused['source_context'] != reader.pin(attempt/'context-review.json')
                or reused['producer_source'] != runtime['sources']['tools/earnings_open_context.py']
                or reused['consumer_source'] != runtime['sources']['tools/edgar_forecast_openai.py']
                or reused['request_sha256'] != hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
                or reader.read(reused['provider_count_intent'])['payload'] != payload
                or reader.read(reused['provider_count_response']) != counted or reader.read(reused['count_receipt']) != counted
                or reader.read(reused['provider_count_raw']) != {k:v for k,v in counted.items() if k != '_request_id'}
                or marker != prep['consumed_marker']['value']
                or prep['consumed_marker']['binding'] != reader.pin(folder/(number+'-prepared-count-consumed.json'))
                or marker.get('phase') != 'consumed_before_validation_and_reservation'):
            raise ValueError('Original Review prepared-count provenance differs')
        for key in ('source_context','context_receipt','count_receipt','provider_count_intent','provider_count_response',
                    'provider_count_raw','producer_source','consumer_source'):
            if reused[key] is not None:reader.read(reused[key],binary=True)
        evidence += [own['request'],physical['intent'],physical['raw'],physical['numbered_response'],prep['reuse_binding']]
    return evidence


def _fresh_evidence(reader, native, bundle, resident):
    from earnings_population_delta_author import assemble
    from earnings_open_program import candidate, program
    import earnings_open_researcher as researcher
    base_option={} if bundle.get('implementation_base') is None else {'implementation_base':bundle['implementation_base']}
    business=assemble(bundle['parent_source'],bundle['scientific_decision'],reader.read(bundle['raw_patch_response']),**base_option)
    if (reader.read(bundle['source'],binary=True) != business['source_text'].encode()
            or reader.read(bundle['tests'],binary=True) != business['test_text'].encode()):
        raise ValueError('Original verified reused source/tests changed')
    parsed=candidate(business,program(reader.read(bundle['parent_source'],binary=True),'R'),bundle['scientific_decision'])
    child=bundle['candidate'];cases_bound=reader.pin(native/'review-01-cases.json');cases=reader.read(cases_bound)
    if (cases.get('candidate_id') != child['id'] or len(cases['results']) != len(parsed['cases'])
            or not cases['results'] or any(r.get('passed') is not True for r in cases['results'])):
        raise ValueError('All fresh reused-source authored cases must pass')
    for case,row in zip(parsed['cases'],cases['results']):
        if digest(researcher.execution_value(row['execution'],business['source_text'],case['input'])) != digest(case['expected']):
            raise ValueError('Fresh original case source/input/output differs')
    evidence=[cases_bound];probes=[];parent=bundle['implementation_base']['comparison_parent']
    for stage in ('forecast','controller'):
        bound=reader.pin(native/f'review-01-{stage}-probe.json');probe=reader.read(bound)
        comparison_bound=reader.pin(native/f'review-01-parent-{stage}-comparison.json');comparison=reader.read(comparison_bound)
        if (probe.get('company_id') != resume.COMPANY or probe['input']['stage'] != stage or probe['input']['records'] != []
                or comparison['input'] != probe['input'] or comparison.get('company_id') != resume.COMPANY
                or comparison.get('parent_version_id') != parent['id'] or comparison.get('child_version_id') != child['id']
                or comparison.get('parent_programs') != {a:parent[a] for a in ('R','H')}
                or comparison.get('matched_child_probe') != bound or comparison.get('initial_input_sha256') != digest(probe['input'])):
            raise ValueError('Exact fresh matched child/active-parent initial inputs required')
        for value,source in ((probe,business['source_text']),(comparison,reader.read(parent['R'],binary=True).decode())):
            researcher.verify(value['execution'],source,value['input'],resident['company'])
            if (value['diagnostics']['source_sha256'] != hashlib.sha256(source.encode()).hexdigest()
                    or value['diagnostics']['execution_sha256'] != value['execution']['receipt']['sha256']):
                raise ValueError('Fresh exact-source probe diagnostic binding differs')
        probes.append(dict(company_id=resume.COMPANY,stage=stage,receipt=bound,diagnostics=deepcopy(probe['diagnostics'])))
        evidence += [bound,comparison_bound]
    return probes,evidence


def load(binding, *, root, ledger, repo, plan):
    from earnings_population_budget import AUTHORIZATION, amendment_binding
    from earnings_population_completed import _literal,_native,_budget
    if (type(binding) is not dict or set(binding) != {'path','sha256'} or type(binding['path']) is not str
            or type(binding['sha256']) is not str or re.fullmatch('[0-9a-f]{64}',binding['sha256']) is None):
        raise ValueError('Exact closed failed binding required before read')
    root,ledger,repo=map(Path,(root,ledger,repo));path=Path(binding['path']);ident=path.parent.name
    if (root != resume.OWNED or ledger != resume.LEDGER or repo != resume.REPO
            or any(p.resolve() != p for p in (root,ledger,repo,path))
            or path != root/'attempts'/ident/'population-run-failure.json'
            or re.fullmatch('edgar-population-20261016-[0-9]{2}',ident) is None
            or plan.get('id') != 'earnings-population-review-recovery-20261016'
            or plan.get('human_authorization') != AUTHORIZATION or plan.get('recovery_mode') != MODE
            or plan.get('failed_attempt') != binding):
        raise ValueError('Exact canonical closed reused-Review failure authority required before read')
    audit_bound,delivery_bound=plan['closed_failure_audit'],plan['stage_delivery_audit']
    if any(Path(b['path']).parent != root for b in (audit_bound,delivery_bound)):
        raise ValueError('Owned source-bound closure/delivery audits required')
    attempt=path.parent;reader=history._Reader(root,ledger,repo,ident);stamp=hashlib.sha256(ident.encode()).hexdigest()
    registry=ledger.parent/'.capacity-runtime-claims'
    owner_bound,claim_bound=[reader.pin(registry/(stamp+suffix))for suffix in ('.result.json','.json')]
    reader.extra.update(Path(b['path'])for b in (owner_bound,claim_bound,audit_bound,delivery_bound))
    owner,claim,audit,delivery=[reader.read(b)for b in (owner_bound,claim_bound,audit_bound,delivery_bound)]
    runtime_bound=owner['runtime'];runtime=reader.read(runtime_bound)
    if (runtime.get('id') != ident or runtime.get('schema') != 'earnings_population_runtime_v1'
            or runtime.get('root') != str(attempt) or runtime.get('ledger') != str(ledger)
            or re.fullmatch('[0-9a-f]{40}',runtime.get('source_commit','')) is None
            or runtime.get('companies') != [resume.COMPANY] or runtime.get('budget_amendment') != amendment_binding()
            or owner.get('status') != 'FAILED_NO_RETRY' or owner.get('error_type') != 'LoopHalted'
            or owner.get('retry_allowed') is not False or claim.get('runtime') != runtime_bound
            or claim.get('id') != ident or claim.get('source_commit') != runtime['source_commit'] or claim.get('retry_allowed') is not False
            or reader.read(binding) != dict(status='FAILED_NO_RETRY',error_type='LoopHalted',native_closure=None,retry_allowed=False)
            or (attempt/'population-run-result.json').exists() or any((attempt/'roles').glob('forecast-*')) or any(attempt.rglob('score.json'))):
        raise ValueError('Exact closed unscored reused-Review owner/runtime required')
    reader.register_sources(runtime)
    reader.extra.update(Path(runtime[k]['path'])for k in ('review','budget_amendment'))
    study=reader.read(runtime['forecast_study']);inherited=recovery._capacity_origin(reader,runtime,study,root=root,ledger=ledger,repo=repo)
    bundle=inherited.get('author_stage_reuse')
    if (type(bundle) is not dict or bundle.get('mode') != recovery.REVIEW_REUSE
            or bundle.get('new_model_Controller_called') is not False or bundle.get('new_model_Author_called') is not False
            or bundle.get('implementation_base') is None or inherited.get('controller_stage_import') is not None):
        raise ValueError('Independently verified original R/base Author reuse, not a new role result, required')
    resident=tasks.resident(resume.COMPANY)
    reader.extra.update(Path(b['path'])for b in (tasks.FULL_PLAN,tasks.SCORER,resident['kernel']['qa']))
    if (study.get('data') != tasks.FULL_PLAN or study.get('scorer') != tasks.SCORER or study.get('runtime_config') != resident['runtime']
            or study.get('cases') != [resident['case']] or runtime['rates'] != resident['runtime']['models']['gpt-6.1-sol']):
        raise ValueError('Unchanged original development data/scorer/model required')
    reader.scan(runtime);reader.scan(study);review=reader.read(runtime['review']);clock=reader.pair(attempt/'clock.json')
    if (review.get('verdict') != 'PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY' or review.get('blocking_findings') != []
            or review.get('source_commit') != reader.commit
            or review.get('reviewed_configuration_sha256') != digest({k:v for k,v in runtime.items()if k != 'review'})
            or clock != reader.read(owner['clock']) or clock.get('source_commit') != reader.commit
            or clock.get('cutoff_utc') != runtime['cutoff_utc'] or clock.get('deadline_utc') != runtime['deadline_utc']):
        raise ValueError('Original reviewed source/clock configuration differs')
    terminal=audit['terminal_evidence'];observed=delivery.get('runtime',{})
    if (audit.get('schema') != 'earnings_population_live_closure_audit_v1'
            or audit.get('status') != 'SEALED_TERMINAL_REVIEW_INPUT_DELIVERY_FAILURE_ALL_FEES_SETTLED'
            or audit.get('attempt_id') != ident or audit.get('source_commit') != reader.commit or audit.get('runtime') != runtime_bound
            or str(audit.get('auditor','')).lower() in {'','root','/root'}
            or terminal['owner'] != dict(binding=owner_bound,value=owner)
            or terminal['failure']['binding'] != binding or terminal['failure']['value'] != reader.read(binding)
            or delivery.get('schema') != 'earnings_population_live_role_links_audit_v1'
            or delivery.get('status') != 'SEALED_FAILED_REUSED_AUTHOR_REVIEW_INPUT_CAPACITY_NO_VERDICT'
            or delivery.get('attempt_id') != ident or delivery.get('source_commit') != reader.commit
            or set(observed) != {'path','sha256','run_closed'} or observed['run_closed'] is not True
            or {k:observed[k]for k in ('path','sha256')} != runtime_bound):
        raise ValueError('Exact original independently sealed reused-Review closure/delivery required')
    completed,blocked=_review_result(reader,attempt,runtime,terminal)
    counts=_blocked_counts(reader,attempt,runtime,terminal,completed,blocked)
    seed,outputs,evidence=recovery._prefix(reader,runtime,attempt)
    recovery.verify_reused_stages(reader,attempt,outputs,inherited)
    state=pool.validate(inherited['population']);child=bundle['candidate'];parent=state['versions'][child['parent']]
    if (seed['population'] != state or reader.read(seed['feedback']) != inherited['research_feedback']
            or seed['last_scored_feedback'] != inherited['last_scored_feedback'] or outputs['implement']['candidate'] != child
            or child['id'] in state['versions'] or child['axis'] != 'R' or child['H'] != parent['H']):
        raise ValueError('Original unchanged scientific seed/unadopted child required')
    expected_candidate=dict(id=child['id'],source_sha256=bundle['source']['sha256'],tests_sha256=bundle['tests']['sha256'],
        raw_patch_sha256=bundle['raw_patch_response']['sha256'],assembly_sha256=bundle['assembly']['sha256'])
    if plan.get('successful_candidate') != expected_candidate:
        raise ValueError('Source-bound original successful Author identities differ')
    native=Path('/private/tmp')/('market-rsi-'+ident);probes,fresh=_fresh_evidence(reader,native,bundle,resident);evidence+=fresh
    cleanup=_cleanup(attempt)
    if ([r['result']for r in cleanup] != [r['result']for r in terminal['code_cleanup_receipts']]
            or any(r.get('cleanup_verified')is not True or r.get('source_integrity_verified')is not True for r in terminal['code_cleanup_receipts'])):
        raise ValueError('Exact original fresh execution/cleanup set differs')
    evidence+=_physical(reader,runtime,audit,completed)
    evidence+=_budget(reader,runtime,owner,dict(budget=owner['budget_summary']))
    expected={name:dict(role=role,round_index=1,company_id=resume.COMPANY,version=version)
        for name,role,version in [('controller-01','controller',state['versions'][state['stable_id']]),
                                 ('author-01','author',parent),('review-01','review',child)]}
    evidence+=_native(reader,native,runtime_bound,runtime,expected,resident,
        _literal(reader,runtime['sources']['tools/earnings_population_run.py'],'PYTHON'))
    return _attach(inherited,binding,audit=audit_bound,completed=completed,
        limit=runtime['limits']['review']['max_input_tokens'],counts=counts,probes=probes,
        evidence=[binding,audit_bound,delivery_bound,owner_bound,claim_bound,runtime_bound,
                  *[r['result']for r in cleanup],*evidence])
