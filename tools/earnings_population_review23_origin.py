"""Closed23 Author reuse: original imported22 science, never new C23 success.

Only inert original artifacts are verified. Fresh tests/Review and any forecasts
belong to the next authorized window; the failed23 owner remains failed.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import earnings_population as pool
import earnings_population_continuation as history
import earnings_population_campaign_resume as resume
import earnings_population_recovery as recovery
import earnings_population_tasks as tasks
from earnings_native_failure import _cleanup, _owned_requests
from market_rsi import digest

IDENT = 'edgar-population-20261016-23'
SOURCE = '4c73652f14b26fd3d4845435d779984e5d124487'
RUNTIME_SHA = 'd7039c39b287db719a469857026d256e7501c09052cd74fe2a7679b7e9913a38'
AUDIT_SHA = '25df2a250cb9f45986df7e293dbdb5de8af17c1a4702774c9f02772d83d9b4a8'
DELIVERY_SHA = '98eaee6496216bb538dc0891da5397f3da661685297a5fc0b1e226d12b2fa9fe'
FAILURE_SHA = '9f781795ffb9d54442e3625d98876fb978db4045a8a5bcd7cb24195933c0a5f5'


def _delivery_identity(delivery, runtime_bound):
    observed = delivery.get('runtime', {})
    return (delivery.get('status') == 'SEALED_FAILED_REVIEW_INPUT_CAPACITY_AFTER_GOOD_AUTHOR_NO_QUALITY_VERDICT'
        and delivery.get('attempt_id') == IDENT and delivery.get('source_commit') == SOURCE
        and set(observed) == {'path','sha256','run_closed'} and observed['run_closed'] is True
        and {key:observed[key] for key in ('path','sha256')} == runtime_bound)


def _roles(reader, attempt, audit):
    rows = audit['terminal_evidence']['roles']
    if len(rows) != 2 or {r['role'] for r in rows} != {'author-01','review-01'}:
        raise ValueError('Only genuine Author and Review result originals required')
    result = {}
    for row in rows:
        bound = reader.pin(attempt/'roles'/row['role']/'result.json')
        if row['binding'] != bound or row['value'] != reader.read(bound):
            raise ValueError('Sealed original role-result binding differs')
        result[row['role']] = row['value']
    author, review = result['author-01'], result['review-01']
    if (author.get('status') != 'COMPLETED_CANDIDATE' or author.get('error_type') is not None
            or author.get('turns') != 8 or author.get('final_numbered_response') != '08-response.json'
            or review.get('status') != 'FAILED_NO_RETRY' or review.get('error_type') != 'BudgetStop'
            or review.get('turns') != 7 or review.get('final_numbered_response') != '06-response.json'
            or any(type(r['turns']) is not int or r.get('retry_allowed') is not False for r in result.values())):
        raise ValueError('Exact good Author and blocked seventh Review turn required')
    return result


def _physical(reader, runtime, audit):
    """Reuse original reservations/usage; no fabricated Controller HTTP row."""
    from edgar_forecast_openai import token, unit
    attempt = Path(runtime['root']); final = audit['checkpoints'][-1]
    rows, prepared, owned = final['requests'], final['prepared_counts'], _owned_requests(runtime)
    expected = {str(attempt/'roles'/role/f'{turn:02d}-request.json')
                for role, turns in [('author-01',8),('review-01',6)] for turn in range(1,turns+1)}
    if (len(rows) != 14 or len(prepared) != 14 or len(owned) != 14
            or {r['binding']['path'] for r in rows} != expected
            or {r['request']['path'] for r in owned} != expected):
        raise ValueError('Exactly eight Author and six Review settled generations required')
    evidence = []
    for own in owned:
        matches = [r for r in rows if r['binding'] == own['request']]
        if len(matches) != 1: raise ValueError('One sealed original generation required')
        row = matches[0]; folder = Path(own['request']['path']).parent; number = row['number']
        role = folder.name.split('-')[0]; limits = runtime['limits'][role]
        request = reader.read(row['binding']); payload = request['payload']; physical = row['physical']
        intent, raw, response = [reader.read(physical[k]) for k in ('intent','raw','numbered_response')]
        counted = reader.read(reader.pin(folder/(number+'-count.json')))
        if (row['role'] != folder.name or row['binding']['path'] != str(folder/(number+'-request.json'))
                or physical['failure'] is not None
                or physical['sidecar']['path'] != physical['intent']['path'].replace('.intent.json','.response.json')
                or physical['sidecar']['sha256'] != physical['numbered_response']['sha256']
                or reader.read(physical['sidecar']) != response
                or physical['numbered_response'] != reader.pin(folder/(number+'-response.json'))
                or Path(physical['intent']['path']).parent != folder
                or physical['raw']['path'] != physical['intent']['path'].replace('.intent.json','.raw.bin')
                or intent.get('endpoint') != '/v1/responses' or intent.get('retry_allowed') is not False
                or intent.get('complete_reservation') != request or intent.get('budget_request_id') != own['request_id']
                or intent.get('request_receipt_sha256') != row['binding']['sha256']
                or intent.get('payload') != dict(payload,max_output_tokens=limits['max_output_tokens'],service_tier='default',store=False)
                or {k:v for k,v in raw.items() if k != '_request_id'} != {k:v for k,v in response.items() if k != '_request_id'}
                or response.get('status') != 'completed' or response.get('error') is not None
                or response.get('model') != runtime['rates']['api_model'] or response.get('service_tier') != 'default'
                or payload.get('model') != runtime['rates']['api_model']
                or payload.get('reasoning') != {'effort':runtime['role_efforts'][role]}
                or history.e.strict_json(payload['input'][0]['content']) != reader.read(reader.pin(folder/'effective-input.json'))):
            raise ValueError('Original counted physical payload/model/response differs')
        count = token(counted['input_tokens']); usage = response['usage']
        inp, out, cached = token(usage['input_tokens']), token(usage['output_tokens']), token(usage['input_tokens_details']['cached_tokens'])
        rates = runtime['rates']; rate = max(unit(rates[k]) for k in ('input','cached','write') if rates[k] is not None)
        charge = (inp-cached)*rate+cached*unit(rates['cached'])+out*unit(rates['output'])
        if (count > limits['max_input_tokens'] or inp > count or cached > inp or out > limits['max_output_tokens']
                or token(usage['total_tokens']) != inp+out or own['status'] != 'settled'
                or request['reserved_nano_usd'] != count*rate+limits['max_output_tokens']*unit(rates['output'])
                or own['charged_nano_usd'] != charge or row['usage']['expected_conservative_charge_nano_usd'] != charge):
            raise ValueError('Original count/usage/settled charge differs')
        prep = [r for r in prepared if r['role'] == folder.name and r['number'] == number]
        if len(prep) != 1: raise ValueError('One original prepared-count handoff required')
        prep = prep[0]; reused = reader.read(prep['reuse_binding'])
        marker = reader.read(prep['consumed_marker']['binding'])
        if (prep['actual_generation_request'] != own['request'] or prep['actual_generation_completed'] is not True
                or prep['reuse_binding'] != reader.pin(folder/(number+'-prepared-count-reuse.json'))
                or reused.get('schema') != 'earnings_prepared_count_handoff_v1'
                or reused.get('slot') != str(folder) or type(reused.get('turn')) is not int or reused['turn'] != int(number)
                or reused.get('new_count_http_request') is not False or reused.get('reused_original_provider_count') is not True
                or reused['source_context'] != reader.pin(attempt/('context-'+role+'.json'))
                or reused['producer_source'] != runtime['sources']['tools/earnings_open_context.py']
                or reused['consumer_source'] != runtime['sources']['tools/edgar_forecast_openai.py']
                or reused['request_sha256'] != hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
                or reader.read(reused['provider_count_intent'])['payload'] != payload
                or reader.read(reused['provider_count_response']) != counted or reader.read(reused['count_receipt']) != counted
                or reader.read(reused['provider_count_raw']) != {k:v for k,v in counted.items() if k != '_request_id'}
                or marker != prep['consumed_marker']['value']
                or prep['consumed_marker']['binding'] != reader.pin(folder/(number+'-prepared-count-consumed.json'))
                or marker.get('phase') != 'consumed_before_validation_and_reservation'):
            raise ValueError('Original single-use provider count provenance differs')
        for key in ('source_context','context_receipt','count_receipt','provider_count_intent','provider_count_response',
                    'provider_count_raw','producer_source','consumer_source'):
            if reused[key] is not None: reader.read(reused[key],binary=True)
        evidence += [own['request'],physical['intent'],physical['raw'],physical['numbered_response'],prep['reuse_binding']]
    return evidence


def _review_stop(reader, attempt, runtime, audit):
    folder = attempt/'roles/review-01'; rows = audit['terminal_evidence']['review_input_failure']
    if (audit['terminal_evidence']['seventh_review_generation_sent'] is not False
            or any((folder/name).exists() for name in ('07-request.json','07-response.json','review.json'))
            or {Path(r['context']['path']) for r in rows} != set(folder.glob('07-context-*.json'))-
                set(folder.glob('07-context-*-count.json'))
            or not rows):
        raise ValueError('Only an ungenerated next Review packing stop may transfer')
    # OpenRole aliases the latest completed tool reply even when final packing
    # fails. Preserve that original alias; it is not a decoded quality verdict.
    last = reader.read(reader.pin(folder/'06-response.json'))
    if (reader.read(reader.pin(folder/'response.json')) != last
            or last.get('status') != 'completed'
            or not any(item.get('type') == 'function_call' for item in last.get('output', []))):
        raise ValueError('Exact last completed tool-reply alias, not a Review verdict, required')
    intents = [(reader.pin(p),reader.read(reader.pin(p))) for p in folder.glob('http-*.intent.json')]
    if len([v for _,v in intents if v.get('endpoint') == '/v1/responses']) != 6:
        raise ValueError('Blocked Review has an additional generation intent')
    for row in rows:
        context, count = reader.read(row['context']), reader.read(row['count'])
        matches = [(b,v) for b,v in intents if v.get('endpoint') == '/v1/responses/input_tokens'
            and hashlib.sha256(json.dumps(v['payload'],sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
                == context['effective_request_sha256']]
        if (len(matches) != 1 or row['count']['path'] != row['context']['path'].replace('.json','-count.json')
                or context != row['preparation'] or context.get('schema') != 'earnings_context_preparation_v1'
                or context.get('generation_not_sent') is not True
                or type(context.get('max_input_tokens')) is not int
                or context['max_input_tokens'] != runtime['limits']['review']['max_input_tokens']
                or type(count.get('input_tokens')) is not int or count['input_tokens'] <= context['max_input_tokens']
                or row['input_tokens'] != count['input_tokens']):
            raise ValueError('Exact original overflowing Review count required')
        bound, intent = matches[0]
        if (intent['payload'].get('model') != runtime['rates']['api_model']
                or intent['payload'].get('reasoning') != {'effort':runtime['role_efforts']['review']}
                or history.e.strict_json(intent['payload']['input'][0]['content']) != reader.read(reader.pin(folder/'effective-input.json'))
                or reader.read(reader.pin(Path(bound['path'].replace('.intent.json','.raw.bin')))) !=
                    {k:v for k,v in count.items() if k != '_request_id'}):
            raise ValueError('Original blocked Review transport differs')
    return [r['input_tokens'] for r in rows]


def _authored(reader, attempt, runtime, state, child, chosen):
    from earnings_population_delta_author import assemble
    from earnings_population_roles import scientific, message
    from earnings_open_program import candidate, program
    parent = state['versions'].get(chosen['parent_pair_sha256']); folder = attempt/'roles/author-01'
    if (parent is None or parent['id'] not in [state['stable_id'],*state['explorers']]
            or child.get('axis') != 'R' or child.get('parent') != parent['id'] or child['H'] != parent['H']
            or child['id'] in state['versions'] or child.get('author') != 'model:DeltaAuthor'
            or child != pool.version(**{k:child[k] for k in ('R','H','parent','axis','method','author','evidence')})):
        raise ValueError('Exact unadopted R child of admitted active parent required')
    selected = scientific(chosen); raw_bound = reader.pin(folder/'response.json'); raw = reader.read(raw_bound)
    assembly_bound = reader.pin(folder/'delta-assembly.json'); assembly = reader.read(assembly_bound)
    projection = reader.read(reader.pin(folder/'scientific-decision-projection.json')); tests = reader.pin(folder/'cases.py')
    base = assembly.get('implementation_base')
    business = assemble(parent['R'],selected,raw,implementation_base=base)
    if (reader.read(reader.pin(folder/'08-response.json')) != raw
            or reader.read(reader.pin(folder/'delta.json')) != dict(delta=message(raw),original=raw_bound)
            or projection.get('population_decision') != chosen or projection.get('scientific_decision') != selected
            or projection.get('scientific_decision_sha256') != digest(selected)
            or assembly.get('schema') != 'earnings_population_delta_assembly_v2'
            or assembly.get('parent_source') != parent['R'] or assembly.get('parent_version_id') != parent['id']
            or assembly.get('comparison_parent_source') != parent['R'] or assembly.get('comparison_parent_version_id') != parent['id']
            or assembly.get('raw_patch_response') != raw_bound or assembly.get('source') != child['R']
            or assembly.get('tests') != tests or assembly.get('assembled_business_sha256') != digest(business)
            or assembly.get('scientific_decision_sha256') != digest(selected)
            or assembly.get('scientific_decision') != reader.pin(folder/'scientific-decision-projection.json')
            or assembly['assembly_source'] != dict(function='assemble',module=runtime['sources']['tools/earnings_population_delta_author.py'])
            or reader.read(child['R'],binary=True) != business['source_text'].encode()
            or reader.read(tests,binary=True) != business['test_text'].encode()):
        raise ValueError('Original v2 raw/base/comparison/assembly/source/test identities differ')
    parsed = candidate(business,program(reader.read(parent['R'],binary=True),'R'),selected)
    return parent, selected, raw_bound, assembly_bound, tests, base, business, parsed


def load(binding, *, root, ledger, repo, plan):
    """Authenticate this closed prefix; return unchanged science plus explicit reuse."""
    from earnings_population_budget import AUTHORIZATION, amendment_binding
    from earnings_population_completed import _literal, _native, _budget
    from earnings_population_controller_delivery import verify
    import earnings_open_researcher as researcher
    root, ledger, repo = map(Path,(root,ledger,repo)); attempt = root/'attempts'/IDENT
    if (root != resume.OWNED or ledger != resume.LEDGER or repo != resume.REPO
            or any(p.resolve() != p for p in (root,ledger,repo))
            or binding != dict(path=str(attempt/'population-run-failure.json'),sha256=FAILURE_SHA)
            or plan.get('id') != 'earnings-population-review-recovery-20261016'
            or plan.get('human_authorization') != AUTHORIZATION or plan.get('failed_attempt') != binding
            or plan.get('recovery_mode') != recovery.REVIEW_REUSE):
        raise ValueError('Exact owned closed23 good-Author reuse authority required before read')
    audit_bound, delivery_bound = plan['closed_failure_audit'], plan['stage_delivery_audit']
    if (audit_bound != dict(path=str(root/'CUMULATIVE400-LIVE23-CLOSURE-AUDIT.json'),sha256=AUDIT_SHA)
            or delivery_bound != dict(path=str(root/'CUMULATIVE400-LIVE23-ROLE-LINKS.json'),sha256=DELIVERY_SHA)):
        raise ValueError('Exact sealed23 closure and stage-delivery audits required')
    reader = history._Reader(root,ledger,repo,IDENT); stamp = hashlib.sha256(IDENT.encode()).hexdigest()
    registry = ledger.parent/'.capacity-runtime-claims'
    owner_bound, claim_bound = [reader.pin(registry/(stamp+suffix)) for suffix in ('.result.json','.json')]
    reader.extra.update(Path(b['path']) for b in (owner_bound,claim_bound,audit_bound,delivery_bound))
    owner, claim, audit, delivery = [reader.read(b) for b in (owner_bound,claim_bound,audit_bound,delivery_bound)]
    runtime_bound = owner['runtime']; runtime = reader.read(runtime_bound)
    if (runtime_bound != dict(path=str(root/'inputs'/IDENT/'runtime-reviewed.json'),sha256=RUNTIME_SHA)
            or runtime.get('id') != IDENT or runtime.get('schema') != 'earnings_population_runtime_v1'
            or runtime.get('source_commit') != SOURCE or runtime.get('root') != str(attempt)
            or runtime.get('ledger') != str(ledger) or runtime.get('companies') != [resume.COMPANY]
            or runtime.get('budget_amendment') != amendment_binding()
            or owner.get('status') != 'FAILED_NO_RETRY' or owner.get('error_type') != 'LoopHalted'
            or owner.get('retry_allowed') is not False or claim.get('retry_allowed') is not False
            or claim.get('runtime') != runtime_bound or claim.get('id') != IDENT or claim.get('source_commit') != SOURCE
            or reader.read(binding) != dict(status='FAILED_NO_RETRY',error_type='LoopHalted',native_closure=None,retry_allowed=False)
            or (attempt/'population-run-result.json').exists() or any((attempt/'roles').glob('forecast-*'))
            or any(attempt.rglob('score.json'))):
        raise ValueError('Exact original closed unscored23 owner/runtime required')
    reader.register_sources(runtime)
    reader.extra.update(Path(runtime[k]['path']) for k in ('review','budget_amendment'))
    study = reader.read(runtime['forecast_study'])
    inherited = recovery._capacity_origin(reader,runtime,study,root=root,ledger=ledger,repo=repo)
    resident = tasks.resident(resume.COMPANY)
    reader.extra.update(Path(b['path']) for b in (tasks.FULL_PLAN,tasks.SCORER,resident['kernel']['qa']))
    if (study.get('data') != tasks.FULL_PLAN or study.get('scorer') != tasks.SCORER
            or study.get('runtime_config') != resident['runtime'] or study.get('cases') != [resident['case']]
            or runtime['rates'] != resident['runtime']['models']['gpt-6.1-sol']):
        raise ValueError('Original development data/scorer/model differs')
    reader.scan(runtime); reader.scan(study); review = reader.read(runtime['review'])
    if (review.get('verdict') != 'PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY' or review.get('blocking_findings') != []
            or review.get('source_commit') != SOURCE
            or review.get('reviewed_configuration_sha256') != digest({k:v for k,v in runtime.items() if k != 'review'})
            or reader.pair(attempt/'clock.json') != reader.read(owner['clock'])):
        raise ValueError('Original23 reviewed source/configuration/clock differs')
    terminal = audit['terminal_evidence']
    if (audit.get('schema') != 'earnings_population_live_closure_audit_v1'
            or audit.get('status') != 'SEALED_TERMINAL_REVIEW_INPUT_DELIVERY_FAILURE_ALL_FEES_SETTLED'
            or audit.get('attempt_id') != IDENT or audit.get('source_commit') != SOURCE or audit.get('runtime') != runtime_bound
            or str(audit.get('auditor','')).lower() in {'','root','/root'}
            or terminal['owner'] != dict(binding=owner_bound,value=owner)
            or terminal['failure']['binding'] != binding or terminal['failure']['value'] != reader.read(binding)
            or not _delivery_identity(delivery,runtime_bound)):
        raise ValueError('Exact sealed failed23 delivery/closure identity required')
    _roles(reader,attempt,audit); counts = _review_stop(reader,attempt,runtime,audit)
    seed, outputs, evidence = recovery._prefix(reader,runtime,attempt)
    verify(reader,attempt,outputs,inherited,runtime)  # Explicit imported22, not a C23 model result.
    state = pool.validate(inherited['population']); child = outputs['implement']['candidate']
    chosen = reader.read(outputs['controller']['decision'])
    if (seed['population'] != state or reader.read(seed['feedback']) != inherited['research_feedback']
            or seed['last_scored_feedback'] != inherited['last_scored_feedback']):
        raise ValueError('Unchanged original scientific pool/feedback/lastscore required')
    parent, selected, raw_bound, assembly_bound, tests, base, business, parsed = _authored(reader,attempt,runtime,state,child,chosen)
    if plan.get('successful_candidate') != dict(id=child['id'],source_sha256=child['R']['sha256'],
            tests_sha256=tests['sha256'],raw_patch_sha256=raw_bound['sha256'],assembly_sha256=assembly_bound['sha256']):
        raise ValueError('Committed successful23 source/Delta/test identities differ')
    native = Path('/private/tmp')/('market-rsi-'+IDENT); cases_bound = reader.pin(native/'review-01-cases.json')
    cases = reader.read(cases_bound); probes = []
    if (cases.get('candidate_id') != child['id'] or len(cases['results']) != len(parsed['cases'])
            or not cases['results'] or any(r.get('passed') is not True for r in cases['results'])):
        raise ValueError('All original authored cases must have passed')
    for case, result in zip(parsed['cases'],cases['results']):
        if digest(researcher.execution_value(result['execution'],business['source_text'],case['input'])) != digest(case['expected']):
            raise ValueError('Original case execution/source/input/output differs')
    for stage in ('forecast','controller'):
        bound = reader.pin(native/f'review-01-{stage}-probe.json'); probe = reader.read(bound)
        other_bound = reader.pin(native/f'review-01-parent-{stage}-comparison.json'); other = reader.read(other_bound)
        if (probe.get('company_id') != resume.COMPANY or probe['input']['stage'] != stage or probe['input']['records'] != []
                or probe['diagnostics'].get('source_sha256') != child['R']['sha256']
                or other['input'] != probe['input'] or other.get('company_id') != resume.COMPANY
                or other.get('parent_version_id') != parent['id'] or other.get('child_version_id') != child['id']
                or other.get('parent_programs') != {axis:parent[axis] for axis in ('R','H')}
                or other.get('matched_child_probe') != bound or other.get('initial_input_sha256') != digest(probe['input'])
                or other['diagnostics'].get('source_sha256') != parent['R']['sha256']):
            raise ValueError('Matched original child/active-parent public cold inputs required')
        for value, source in ((probe,business['source_text']),(other,reader.read(parent['R'],binary=True).decode())):
            researcher.verify(value['execution'],source,value['input'],resident['company'])
            if value['diagnostics']['execution_sha256'] != value['execution']['receipt']['sha256']:
                raise ValueError('Original cold execution diagnostic receipt differs')
        probes.append(dict(company_id=resume.COMPANY,stage=stage,receipt=bound,diagnostics=deepcopy(probe['diagnostics'])))
        evidence += [bound,other_bound]
    cleanup = _cleanup(attempt)
    if ([r['result'] for r in cleanup] != [r['result'] for r in terminal['code_cleanup_receipts']]
            or any(r.get('cleanup_verified') is not True or r.get('source_integrity_verified') is not True
                   for r in terminal['code_cleanup_receipts'])):
        raise ValueError('Sealed exact original isolated code cleanup differs')
    evidence += _physical(reader,runtime,audit)
    evidence += _budget(reader,runtime,owner,dict(budget=owner['budget_summary']))
    expected = {name:dict(role=role,round_index=1,company_id=resume.COMPANY,version=version)
        for name,role,version in [('controller-01','controller',state['versions'][state['stable_id']]),
                                 ('author-01','author',parent),('review-01','review',child)]}
    evidence += _native(reader,native,runtime_bound,runtime,expected,resident,
                        _literal(reader,runtime['sources']['tools/earnings_population_run.py'],'PYTHON'))
    result = deepcopy(inherited)
    result.pop('controller_stage_import')  # Preserve its evidence, not an active second routing instruction.
    result['author_stage_reuse'] = dict(schema='earnings_population_author_stage_reuse_v1',mode=recovery.REVIEW_REUSE,
        candidate=deepcopy(child),decision=outputs['controller']['decision'],scientific_decision=selected,
        raw_patch_response=raw_bound,assembly=assembly_bound,tests=tests,source=child['R'],parent_source=parent['R'],
        implementation_base=deepcopy(base),cases=cases_bound,probes=probes,failed_attempt=deepcopy(binding),
        original_controller_import=outputs['controller']['proposal_import'],
        new_model_Controller_called=False,new_model_Author_called=False)
    result.update(pre_recovery_reference_candidate=deepcopy(inherited['reference_candidate']),
        reference_candidate=dict(axis='R',source=child['R'],source_delivery='paged_reference',reference_only=True,
            id=child['id'],parent=child['parent'],tests=tests),
        recovery_context=dict(schema='earnings_population_delivery_failure_v1',failed_attempt=deepcopy(binding),
            audit=audit_bound,candidate_id=child['id'],stage='source_review',error_type='BudgetStop',
            observed_input_tokens=counts,prior_input_limit=runtime['limits']['review']['max_input_tokens'],
            review_assessment='not_completed',completed_Review_generations=6,score_state='unscored',probes=probes,
            scope='Original23 Author Delta/tests and imported22 public Controller science only. Failed23 Review was not a quality verdict. Fresh real Review/tests/forecasts remain mandatory.'))
    result['evidence'] += [binding,audit_bound,delivery_bound,owner_bound,claim_bound,runtime_bound,raw_bound,
        assembly_bound,tests,cases_bound,*[r['result'] for r in cleanup],*evidence]
    return result
