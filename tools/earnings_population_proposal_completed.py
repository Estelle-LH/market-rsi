"""Authenticate a stopped four-stage proposal; never a scored/population origin."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

import earnings_population as pool
import earnings_population_completed as completed
import earnings_population_continuation as history
import earnings_population_runtime as runtime_module
import earnings_population_tasks as tasks
import earnings_open_researcher as researcher
from earnings_entry import strict_json
from earnings_native_failure import _cleanup, _owned_requests
from earnings_population_delta_author import assemble
from earnings_population_roles import scientific, message, decode_proposal
from earnings_open_program import candidate, program
from edgar_forecast_openai import token, unit
from edgar_forecast_tools import FilingTools
from market_rsi import digest

SCHEMA = 'earnings_training25_verified_proposal_v1'
STAGES = ('input','controller','implement','source_review')


def _prefix(reader, attempt, runtime, study, bindings):
    path=attempt/'loop'; outputs={}; evidence=[]; files=set()
    with history._journal_lock(path):
        manifest=reader.pair(path/'manifest.json'); seed=manifest['seed']
        if (set(manifest) != {'schema','seed','seed_sha256','handler_identity','driver_source_sha256','max_rounds'}
                or manifest['schema'] != 'feedback_linked_loop_v1' or manifest['max_rounds'] != 1
                or manifest['seed_sha256'] != digest(seed) or seed['companies'] != runtime['companies']
                or manifest['driver_source_sha256'] != runtime['sources'][history.DRIVER]['sha256']
                or set(manifest['handler_identity']) != set(history.STAGES)):
            raise ValueError('Original proposal manifest/seed/driver differs')
        for stage,identity in manifest['handler_identity'].items():
            if identity != dict(stage=stage,adapter=runtime['sources']['tools/earnings_population_loop.py'],
                    admission=dict(function='execute.<locals>.admit',module=runtime['sources']['tools/earnings_population_run.py']),
                    services=history.expected_services(runtime),campaign_policy=runtime['sources']['tools/earnings_population_campaign.py'],campaign=study['campaign']):
                raise ValueError('Original proposal callback identity differs')
        for stage,bound in zip(STAGES,bindings,strict=True):
            prefix=path/('round-0001-'+stage); claim=prefix.with_suffix('.claim.json'); done=prefix.with_suffix('.done.json')
            current=dict(round_index=1,seed=seed,previous_result=seed,previous_feedback_sha256=digest(seed),outputs=outputs)
            expected=dict(round_index=1,stage=stage,context_sha256=digest(current),
                manifest_sha256=reader.pin(path/'manifest.json')['sha256'],previous_feedback_sha256=digest(seed))
            row=reader.pair(done)
            if (bound != reader.pin(done) or reader.read(reader.pin(claim)) != expected
                    or set(row) != {'claim_sha256','output','output_sha256'}
                    or row['claim_sha256'] != reader.pin(claim)['sha256'] or row['output_sha256'] != digest(row['output'])):
                raise ValueError('Exact original four-stage claim/output seals required')
            outputs[stage]=row['output']; files.update((claim.name,done.name,done.with_suffix('.binding.json').name))
            evidence += [reader.pin(claim),bound,reader.pin(done.with_suffix('.binding.json'))]
        if {p.name for p in path.glob('round-*')} != files:
            raise ValueError('Proposal must stop BEFORE execute claim with no later or failed stages')
    return seed,outputs,[reader.pin(path/'manifest.json'),*evidence]


def _physical(reader, runtime, task, summary, roles, *, completed_generations=None):
    owned=_owned_requests(runtime); evidence=[]
    generation_counts = ({name:value['turns'] for name,value in roles.items()}
              if completed_generations is None else completed_generations)
    if (type(generation_counts) is not dict or set(generation_counts) != set(roles)
            or any(type(n) is not int or not 1 <= n <= roles[name]['turns'] for name,n in generation_counts.items())
            or len(owned) != sum(generation_counts.values())):
        raise ValueError('Every genuine original model generation must be settled exactly once')
    seen=set()
    for own in owned:
        bound=own['request']; folder=Path(bound['path']).parent; role=folder.name.split('-')[0]; number=Path(bound['path']).name[:2]
        if (role not in roles or str(folder) != runtime['slots'][role][0]
                or number not in {f'{i:02d}' for i in range(1,generation_counts[role]+1)} or (role,number) in seen):
            raise ValueError('Foreign or duplicate proposal model slot/generation')
        seen.add((role,number))
        request=reader.read(bound); payload=request['payload']; limits=runtime['limits'][role]
        response_bound=reader.pin(folder/(number+'-response.json')); response=reader.read(response_bound)
        matches=[p for p in folder.glob('http-*.intent.json') if reader.read(reader.pin(p)).get('budget_request_id') == own['request_id']]
        if len(matches) != 1: raise ValueError('One original physical generation intent required')
        intent_bound=reader.pin(matches[0]); intent=reader.read(intent_bound)
        sibling=lambda suffix:matches[0].with_name(matches[0].name.removesuffix('.intent.json')+suffix)
        raw_bound,side_bound=reader.pin(sibling('.raw.bin')),reader.pin(sibling('.response.json'))
        if (intent.get('endpoint') != '/v1/responses' or intent.get('retry_allowed') is not False
                or intent.get('complete_reservation') != request or intent.get('request_receipt_sha256') != bound['sha256']
                or intent.get('payload') != dict(payload,max_output_tokens=limits['max_output_tokens'],service_tier='default',store=False)
                or reader.read(side_bound) != response or reader.read(raw_bound) != {k:v for k,v in response.items() if k!='_request_id'}
                or response.get('status') != 'completed' or response.get('model') != runtime['rates']['api_model'] or response.get('service_tier') != 'default'
                or payload.get('reasoning') != {'effort':runtime['role_efforts'][role]}):
            raise ValueError('Original physical role request/response/model differs')
        first=strict_json(payload['input'][0]['content'])
        if first != reader.read(reader.pin(folder/'effective-input.json')): raise ValueError('Original physical first packet differs')
        research=first.get('research_context',{})
        if role in ('controller','author'):
            actual=(research.get('observations',{}).get('training_comparator') if role=='controller' else research.get('training_comparator'))
            delivered=first.get('proposal_task') if role=='controller' else research.get('proposal_task')
            goal=first.get('research_objective','') if role=='controller' else research.get('task','')
            if actual != summary or delivered != task or task['primary_task'] not in goal:
                raise ValueError('Whole25 task and all125 original pairs must reach actual C/A')
        counted_bound=reader.pin(folder/(number+'-count.json')); counted=reader.read(counted_bound)
        reuse_path=folder/(number+'-prepared-count-reuse.json')
        if reuse_path.exists():
            reuse=reader.read(reader.pin(reuse_path)); marker=reader.read(reader.pin(folder/(number+'-prepared-count-consumed.json')))
            if (reuse.get('schema') != 'earnings_prepared_count_handoff_v1' or reuse.get('slot') != str(folder)
                    or type(reuse.get('turn')) is not int or reuse['turn'] != int(number)
                    or reuse.get('new_count_http_request') is not False or reuse.get('reused_original_provider_count') is not True
                    or reuse.get('source_context') != reader.pin(Path(runtime['root'])/('context-'+role+'.json'))
                    or reuse.get('producer_source') != runtime['sources']['tools/earnings_open_context.py']
                    or reuse.get('consumer_source') != runtime['sources']['tools/edgar_forecast_openai.py']
                    or reuse.get('request_sha256') != hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
                    or reader.read(reuse['provider_count_response']) != counted or reader.read(reuse['count_receipt']) != counted
                    or marker.get('phase') != 'consumed_before_validation_and_reservation'):
                raise ValueError('Original prepared-count handoff differs')
            count_intent=reader.read(reuse['provider_count_intent']); count_raw=reader.read(reuse['provider_count_raw']); reader.scan(reuse)
        else:
            counts=[p for p in folder.glob('http-*.intent.json') if reader.read(reader.pin(p)).get('endpoint') == '/v1/responses/input_tokens'
                and reader.read(reader.pin(p)).get('payload') == payload
                and reader.read(reader.pin(p.with_name(p.name.removesuffix('.intent.json')+'.response.json'))) == counted]
            if len(counts) != 1: raise ValueError('One original default provider count required')
            count_intent=reader.read(reader.pin(counts[0])); count_raw=reader.read(reader.pin(counts[0].with_name(counts[0].name.removesuffix('.intent.json')+'.raw.bin')))
        if count_intent.get('endpoint') != '/v1/responses/input_tokens' or count_intent.get('payload') != payload or count_raw != {k:v for k,v in counted.items() if k!='_request_id'}:
            raise ValueError('Original counted winning payload differs')
        count=token(counted['input_tokens']); usage=response['usage']; inp,out,cached=token(usage['input_tokens']),token(usage['output_tokens']),token(usage['input_tokens_details']['cached_tokens'])
        rates=runtime['rates']; rate=max(unit(rates[k]) for k in ('input','cached','write') if rates[k] is not None)
        if (count>limits['max_input_tokens'] or inp>count or cached>inp or out>limits['max_output_tokens']
                or token(usage['total_tokens'])!=inp+out or own['status']!='settled'
                or request['reserved_nano_usd']!=count*rate+limits['max_output_tokens']*unit(rates['output'])
                or own['charged_nano_usd']!=(inp-cached)*rate+cached*unit(rates['cached'])+out*unit(rates['output'])):
            raise ValueError('Original role count/usage/reservation/settlement differs')
        evidence += [bound,response_bound,intent_bound,raw_bound,side_bound,counted_bound]
    return evidence


def _packet_identity(packet, role, selected, parent_source, child, *, base=None):
    if role == 'review':
        valid=packet.get('candidate_id')==child['id'] and packet.get('decision')==selected
    else:
        valid=packet.get('decision')==selected and packet.get('decision_sha256')==digest(selected)
        if base is None:
            valid=valid and packet.get('parent_source')==parent_source and packet.get('parent_source_sha256')==parent_source['sha256']
        else:
            valid=valid and packet.get('comparison_parent')==dict(version_id=selected['parent_pair_sha256'],source=parent_source) and packet.get('comparison_parent_source_sha256')==parent_source['sha256'] and packet.get('implementation_base')==base and packet.get('implementation_base_source_sha256')==base['source']['sha256']
    if not valid:raise ValueError('Original '+role+' physical packet decision/parent/child identity differs')


def _authored(reader, attempt, state, chosen, child, runtime):
    parent=state['versions'][chosen['parent_pair_sha256']]; axis=chosen['axis']; other='H' if axis=='R' else 'R'
    folder=attempt/'roles/author-01'; raw=reader.pin(folder/'response.json'); assembly_bound=reader.pin(folder/'delta-assembly.json')
    assembly=reader.read(assembly_bound); base=assembly.get('implementation_base'); selected=scientific(chosen)
    business=assemble(parent[axis],selected,reader.read(raw),implementation_base=base)
    parsed=candidate(business,program(reader.read(parent[axis],binary=True),axis),selected)
    projection=reader.pin(folder/'scientific-decision-projection.json'); tests=reader.pin(folder/'cases.py')
    if (child.get('parent') != parent['id'] or child.get('axis') != axis or child.get(other) != parent[other]
            or child.get('method') != chosen['hypothesis'] or child.get('author') != 'model:DeltaAuthor'
            or child['id'] in state['versions'] or child != pool.version(**{k:child[k] for k in ('R','H','parent','axis','method','author','evidence')})
            or assembly.get('schema') != ('earnings_population_delta_assembly_v1' if base is None else 'earnings_population_delta_assembly_v2')
            or assembly.get('axis') != axis or assembly.get('parent_source') != parent[axis] or assembly.get('parent_version_id') != parent['id']
            or assembly.get('raw_patch_response') != raw or assembly.get('source') != child[axis] or assembly.get('tests') != tests
            or assembly.get('scientific_decision') != projection or assembly.get('scientific_decision_sha256') != digest(selected)
            or assembly.get('assembled_business_sha256') != digest(business) or assembly.get('host_candidate_execution') is not False
            or assembly.get('assembly_source') != dict(function='assemble',module=runtime['sources']['tools/earnings_population_delta_author.py'])
            or reader.read(projection) != dict(population_decision=chosen,scientific_decision=selected,scientific_decision_sha256=digest(selected),
                scope='Explicitly removed retirement field only; no parent or feedback rewrite')
            or reader.read(reader.pin(folder/'delta.json')) != dict(original=raw,delta=message(reader.read(raw)))
            or reader.read(child[axis],binary=True) != business['source_text'].encode() or reader.read(tests,binary=True) != business['test_text'].encode()
            or base is not None and (assembly.get('comparison_parent_source') != parent[axis] or assembly.get('comparison_parent_version_id') != parent['id'])):
        raise ValueError('Original fresh R/H Delta/assembly/source/test ancestry differs')
    _packet_identity(reader.read(reader.pin(folder/'effective-input.json')),'author',selected,parent[axis],child,base=base)
    return parent,selected,business,parsed,[raw,assembly_bound,projection,tests,child[axis]]


def _proposal_prefix(reader, runtime, study, task, *, root, ledger, repo):
    """Explicit failed37 prefix only; absent policy preserves fresh-only ABI."""
    key='proposal_prefix_reuse'; path=root/'inputs'/runtime['id']/'proposal-prefix-reuse.json'
    if not (key in runtime or key in study or path.exists()):return None
    bound=runtime.get(key)
    if (type(bound) is not dict or set(bound)!={'path','sha256'} or bound!=study.get(key)
            or bound.get('path')!=str(path) or path.resolve()!=path
            or 'training_stage_attachment' in study or any(k in runtime or k in study
                for k in ('frozen_panel','frozen_panel_policy','frozen_panel_window'))):
        raise ValueError('Exact canonical mirrored proposal prefix reuse required')
    metadata=getattr(runtime_module,'_proposal_prefix_metadata',None)
    if not callable(metadata):raise ValueError('Original proposal prefix metadata receiver is not implemented')
    saved=metadata(runtime,study,company_id=task['smoke_company_id'])
    original=load_failed37_prefix(FAILED37,consumer_attempt_id=runtime['id'],root=root,ledger=ledger,repo=repo)
    if (saved is None or reader.read(bound)!=saved or saved!=original or saved['task']!=task
            or saved['base_origin']['previous_result']!=runtime_module.PROPOSAL_ORIGIN):
        raise ValueError('Saved prefix differs from original failed37 authentication/task/base36')
    return saved


def _reused_authored(reader, attempt, outputs, origin, imported, child):
    """Current adapter stages, original37 science; no new C/A transcript."""
    from earnings_population_recovery import verify_reused_stages
    bundle=imported['author_stage_reuse']; parent=imported['parent']; selected=imported['scientific_decision']
    verify_reused_stages(reader,attempt,outputs,dict(origin,author_stage_reuse=bundle))
    expected={'controller':{'population-decision.json','controller-stage-reuse.json'},
              'author':{'author-stage-reuse.json'}}
    evidence=[]
    for role,stage,name in (('controller','controller','controller-stage-reuse.json'),
                            ('author','implement','author-stage-reuse.json')):
        folder=attempt/'roles'/(role+'-01'); bound=reader.pin(folder/name)
        artifacts=([outputs['controller']['decision'],bound] if role=='controller' else [bound])
        if (outputs[stage].get('stage_reuse')!=bound or outputs[stage].get('artifacts')!=artifacts
                or {p.name for p in folder.iterdir()}!=expected[role]):
            raise ValueError('Imported C/A require exact durable artifacts and no new model files')
        evidence.append(bound)
    if (child!=imported['candidate'] or selected!=bundle['scientific_decision']
            or scientific(reader.read(bundle['decision']))!=selected or child['parent']!=parent['id']):
        raise ValueError('Original37 scientific decision/candidate/parent differs')
    options={} if bundle.get('implementation_base') is None else {'implementation_base':bundle['implementation_base']}
    business=assemble(parent[child['axis']],selected,reader.read(bundle['raw_patch_response']),**options)
    parsed=candidate(business,program(reader.read(parent[child['axis']],binary=True),child['axis']),selected)
    if (reader.read(child[child['axis']],binary=True)!=business['source_text'].encode()
            or reader.read(bundle['tests'],binary=True)!=business['test_text'].encode()):
        raise ValueError('Imported source/tests cannot be regenerated or changed')
    return parent,selected,business,parsed,evidence


def load_proposal(binding, *, root, ledger, repo):
    if (type(binding) is not dict or set(binding) != {'path','sha256'} or type(binding.get('path')) is not str
            or type(binding.get('sha256')) is not str or re.fullmatch('[0-9a-f]{64}',binding['sha256']) is None):
        raise ValueError('Exact original proposal-result binding required')
    path=Path(binding['path']); ident=path.parent.name; attempt=path.parent
    if (root!=completed.bootstrap.OWNED or ledger!=completed.bootstrap.LEDGER or repo!=completed.bootstrap.REPO
            or any(p.resolve()!=p for p in (root,ledger,repo,path)) or path!=root/'attempts'/ident/'training-proposal-result.json'
            or re.fullmatch('edgar-population-20261016-[0-9]{2}',ident) is None):raise ValueError('Canonical owned proposal required')
    reader=history._Reader(root,ledger,repo,ident); result=reader.read(binding)
    if (set(result)!={'schema','runtime','status','result','proposal_stages','budget','improvement_proven','retry_allowed'}
            or result['schema']!='earnings_training25_proposal_result_v1' or result['status'] not in {'PROPOSAL_REVIEWED_ACCEPTED','PROPOSAL_NOT_ACCEPTED'}
            or result['result']!=dict(status='stopped',completed_rounds=0,round_index=1,stage='execute')
            or result['retry_allowed'] is not False or result['improvement_proven'] is not False
            or type(result['proposal_stages']) is not list or len(result['proposal_stages'])!=4
            or any((attempt/name).exists() for name in ('training-proposal-failure.json','population-run-result.json','population-run-failure.json','frozen-pool-01.json'))
            or any((attempt/'roles').glob('forecast-*')) or any(attempt.rglob('score.json')) or any(attempt.rglob('predictions.json'))):
        raise ValueError('Exact clean stopped proposal with no forecast/score/adoption required')
    registry=ledger.parent/'.capacity-runtime-claims'; key=hashlib.sha256(ident.encode()).hexdigest()
    claim_bound,owner_bound=[reader.pin(registry/(key+suffix)) for suffix in ('.json','.result.json')]
    reader.extra.update(Path(b['path']) for b in (claim_bound,owner_bound,tasks.FULL_PLAN,tasks.SCORER))
    claim,owner=reader.read(claim_bound),reader.read(owner_bound); runtime_bound=result['runtime']; runtime=reader.read(runtime_bound)
    if (runtime_bound.get('path')!=str(root/'inputs'/ident/'runtime-reviewed.json') or owner.get('runtime')!=runtime_bound
            or owner.get('status')!='COMPLETED_COMPONENT_CONTEXT' or owner.get('error_type') is not None or owner.get('retry_allowed') is not False
            or claim.get('runtime')!=runtime_bound or claim.get('id')!=ident or claim.get('retry_allowed') is not False
            or claim.get('source_commit')!=runtime.get('source_commit') or runtime.get('schema')!='earnings_population_runtime_v1'
            or runtime.get('id')!=ident or runtime.get('root')!=str(attempt) or runtime.get('ledger')!=str(ledger)
            or runtime.get('training_proposal_policy')!=runtime_module.PROPOSAL_POLICY
            or runtime.get('forecast_study',{}).get('path')!=str(root/'inputs'/ident/'study.json')
            or runtime.get('initial_population',{}).get('path')!=str(root/'inputs'/ident/'initial-population.json')):
        raise ValueError('Original closed proposal owner/claim/runtime differs')
    reader.register_sources(runtime); reader.extra.update(Path(runtime[k]['path']) for k in ('review','budget_amendment','model_budget_amendment'))
    study=reader.read(runtime['forecast_study']); scope,_=completed._training(reader,runtime,study,preview=True)
    task=runtime_module.proposal_task(runtime)
    if scope is None or task is None:raise ValueError('Original explicit training proposal admission required')
    imported=_proposal_prefix(reader,runtime,study,task,root=root,ledger=ledger,repo=repo)
    base=(completed.load(runtime_module.PROPOSAL_ORIGIN,root=root,ledger=ledger,repo=repo)
          if imported is None else imported['base_origin'])
    if base['previous_result']!=runtime_module.PROPOSAL_ORIGIN:raise ValueError('Genuine completed36 predecessor required')
    completed._register(reader,base,training_scope=scope); _,evidence=completed._training(reader,runtime,study,inherited=base)
    if imported is not None:
        # Only the original authenticator grants these exact older namespaces.
        completed._register(reader,dict(base,evidence=imported['evidence']),training_scope=scope)
        evidence += [runtime['proposal_prefix_reuse'],*imported['evidence']]
    seed,outputs,prefix_evidence=_prefix(reader,attempt,runtime,study,result['proposal_stages']); evidence+=prefix_evidence
    if imported is not None and (outputs['source_review'].get('stage_reuse') is not None
            or (attempt/'roles/review-01/review-stage-reuse.json').exists()):
        raise ValueError('Imported C/A never imports a successful old Review')
    if (seed['population']!=base['population'] or reader.read(seed['feedback'])!=base['research_feedback']
            or seed['last_scored_feedback']!=base['last_scored_feedback']):raise ValueError('Original immutable predecessor seed differs')
    packet=reader.read(outputs['input']['packet']); state=pool.validate(base['population']); chosen_bound=outputs['controller']['decision']; chosen=reader.read(chosen_bound)
    parent=state['versions'].get(chosen.get('parent_pair_sha256')); child=outputs['implement']['candidate']; accepted=outputs['source_review']['accepted_for_exploration']
    if (packet.get('population')!=state or packet.get('feedback')!=seed['feedback'] or packet.get('company_id')!=task['smoke_company_id']
            or packet.get('round_index')!=1 or packet.get('parent_feedback_sha256')!=digest(seed['feedback']) or packet.get('campaign')!=study['campaign']
            or chosen.get('feedback_sha256')!=digest(seed['feedback']) or parent is None or parent['id'] not in [state['stable_id'],*state['explorers']]
            or parent['id'] in task['archive_only_version_ids'] or chosen.get('axis') not in {'R','H','continue'}
            or imported is None and (reader.read(reader.pin(attempt/'roles/controller-01/decision.json'))!=dict(original=reader.pin(attempt/'roles/controller-01/response.json'),decision=chosen)
                or decode_proposal(reader.read(reader.pin(attempt/'roles/controller-01/response.json')),
                    reader.read(reader.pin(attempt/'roles/controller-01/effective-input.json')))!=chosen)
            or accepted is not (result['status']=='PROPOSAL_REVIEWED_ACCEPTED')):raise ValueError('Actual new Controller/parent/proposal outcome differs')
    resident=tasks.resident(task['smoke_company_id']); native=Path('/private/tmp')/('market-rsi-'+ident)
    expected={'controller-01':dict(role='controller',company_id=task['smoke_company_id'],version=state['versions'][state['stable_id']])}
    review=outputs['source_review']; role_names={} if imported is not None else {'controller':'COMPLETED_DECISION'}
    if child is None:
        if imported is not None or chosen['axis']!='continue' or review!=dict(accepted_for_exploration=False,evidence=[]):raise ValueError('Continue has no fabricated Author/Review')
    else:
        if chosen['axis']=='continue':raise ValueError('Continue cannot deliver a candidate')
        parent,selected,business,parsed,authored_evidence=(_authored(reader,attempt,state,chosen,child,runtime)
            if imported is None else _reused_authored(reader,attempt,outputs,base,imported,child))
        evidence+=authored_evidence
        cases_bound=reader.pin(native/'review-01-cases.json'); cases=reader.read(cases_bound)
        if cases.get('candidate_id')!=child['id'] or len(cases['results'])!=len(parsed['cases']):raise ValueError('Exact actual authored cases required')
        for case,row in zip(parsed['cases'],cases['results'],strict=True):
            if row.get('passed') is not (digest(researcher.execution_value(row['execution'],business['source_text'],case['input']))==digest(case['expected'])):raise ValueError('Original isolated case result differs')
        outcome_bound=reader.pin(native/'review-01-outcome.json'); review=reader.read(outcome_bound)
        if (review.get('schema')!='earnings_population_exploration_review_v1' or review.get('candidate_id')!=child['id']
                or review.get('accepted_for_exploration') is not accepted or outputs['source_review']['evidence'][0]!=outcome_bound):raise ValueError('Original public Review outcome differs')
        if imported is None:role_names['author']='COMPLETED_CANDIDATE'
        evidence += [cases_bound,outcome_bound]
        for name,version in (('author',parent),('review',child)):expected[name+'-01']=dict(role=name,company_id=task['smoke_company_id'],version=version)
        if all(row['passed'] for row in cases['results']):
            role_names['review']='COMPLETED_REVIEW'; raw=reader.pin(attempt/'roles/review-01/response.json'); business_review=message(reader.read(raw))
            _packet_identity(reader.read(reader.pin(attempt/'roles/review-01/effective-input.json')),'review',selected,parent[chosen['axis']],child)
            if (set(business_review)!={'candidate_id','accepted_for_exploration','rationale'} or business_review.get('candidate_id')!=child['id']
                    or type(business_review.get('accepted_for_exploration')) is not bool or type(business_review.get('rationale')) is not str
                    or not 1<=len(business_review['rationale'])<=1000 or review!=dict(schema='earnings_population_exploration_review_v1',**business_review)
                    or reader.read(reader.pin(attempt/'roles/review-01/review.json'))!=dict(original=raw,review=business_review)):raise ValueError('Genuine literal independent Review differs')
            if child['axis']=='R':
                for stage in ('forecast','controller'):
                    p,c=[reader.pin(native/name) for name in (f'review-01-{stage}-probe.json',f'review-01-parent-{stage}-comparison.json')]; probe,comparison=reader.read(p),reader.read(c)
                    tools=FilingTools(resident['company']); payload=probe['input']
                    if payload!=comparison['input'] or payload.get('records')!=[] or payload.get('stage')!=stage or payload.get('questions')!=tools.files['questions.md'] or payload.get('filing_index')!=tools.files['filing_index.tsv'] or comparison.get('parent_version_id')!=parent['id']:raise ValueError('Original matched smoke probe input differs')
                    researcher.verify(probe['execution'],business['source_text'],payload,resident['company']);researcher.verify(comparison['execution'],reader.read(parent['R'],binary=True).decode(),payload,resident['company']);evidence += [p,c]
        elif accepted or not str(review.get('rationale','')).startswith('MODEL_CASES_FAILED'):raise ValueError('Failed cases cannot forge model acceptance')
    roles={}
    for role,status in role_names.items():
        folder=attempt/'roles'/(role+'-01'); value=reader.read(reader.pin(folder/'result.json')); turns=value.get('turns'); wall=value.get('wall_seconds')
        if (value.get('status')!=status or value.get('error_type') is not None or value.get('retry_allowed') is not False or type(turns) is not int or not 1<=turns<=8
                or type(wall) not in (int,float) or not math.isfinite(wall) or not 0<=wall<=runtime['limits'][role]['wall_seconds']
                or value.get('final_numbered_response')!=f'{turns:02d}-response.json' or reader.read(reader.pin(folder/'response.json'))!=reader.read(reader.pin(folder/value['final_numbered_response']))
                or {p.name for p in folder.glob('[0-9][0-9]-request.json')}!={f'{i:02d}-request.json' for i in range(1,turns+1)}
                or {p.name for p in folder.glob('[0-9][0-9]-response.json')}!={f'{i:02d}-response.json' for i in range(1,turns+1)}):raise ValueError('Exact fresh completed model transcript required')
        roles[role]=value
    expected_folders={role+'-01' for role in roles}|({'controller-01','author-01'} if imported is not None else set())
    if {p.name for p in (attempt/'roles').iterdir()}!=expected_folders:raise ValueError('Unexpected imported/reused/extra model stage')
    from earnings_population_campaign_context import _training_context
    summary=_training_context(study,packet,scope)['training_comparator']
    evidence+=_physical(reader,runtime,task,summary,roles)+completed._budget(reader,runtime,owner,result)+[r['result'] for r in _cleanup(attempt)]
    config=reader.read(runtime['review']); clock=reader.pair(attempt/'clock.json')
    if (config.get('verdict')!='PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY' or config.get('blocking_findings')!=[] or config.get('source_commit')!=reader.commit
            or str(config.get('reviewer','')).lower() in {'','root','/root'} or config.get('reviewed_configuration_sha256')!=digest({k:v for k,v in runtime.items() if k!='review'})
            or clock!=reader.read(owner['clock']) or clock.get('source_commit')!=reader.commit or clock.get('cutoff_utc')!=runtime['cutoff_utc'] or clock.get('deadline_utc')!=runtime['deadline_utc']):raise ValueError('Original distinct runtime review/sealed clock differs')
    reader.extra.add(Path(resident['kernel']['qa']['path']));reader.scan(runtime);reader.scan(study);reader.scan(result);reader.scan(outputs)
    python=completed._literal(reader,runtime['sources']['tools/earnings_population_run.py'],'PYTHON')
    evidence+=completed._native(reader,native,runtime_bound,runtime,expected,resident,python,training_scope=scope)
    return dict(schema=SCHEMA,accepted=accepted,proposal=deepcopy(binding),base_origin=base,task=task,candidate=deepcopy(child),parent=deepcopy(parent),
        decision=deepcopy(chosen),evidence=[binding,runtime_bound,claim_bound,owner_bound,runtime['review'],study['training_proposal_task'],*evidence,*base['evidence']],
        runtime=runtime,runtime_binding=runtime_bound,review=review,
        **({} if imported is None else dict(proposal_prefix_reuse=deepcopy(runtime['proposal_prefix_reuse']),
            stage_attribution=dict(new_model_Controller_called=False,new_model_Author_called=False,
                new_model_Review_called='review' in roles,source_attempt=deepcopy(imported['failed_attempt']),
                review_assessment='fresh_model_review' if 'review' in roles else 'authored_cases_failed_no_model_review'))))


# Separate failed-prefix admission. The successful four-stage loader above is
# intentionally unchanged: failed37 never becomes a completed proposal/origin.
FAILED37_ID = 'edgar-population-20261016-37'
FAILED37_COMPANY = 'CIK0000003545'
FAILED37_MODE = 'training25_failed37_CA_fresh_Review_v1'
FAILED37_SCHEMA = 'earnings_training25_verified_failed37_prefix_v1'
FAILED37_AUTHORITY = dict(path=str(tasks.ARTIFACTS/'edgar-population-20261016'/'TRAIN25-DIRECT-REVIEW200K-REUSE37-AUTHORITY.json'),
    sha256='aef9fa092ceeb4afe4b1ee22f288df5b9d660f8419fdd84f2b866ae8885aa959')
FAILED37 = dict(path=str(tasks.ARTIFACTS/'edgar-population-20261016'/'attempts'/FAILED37_ID/'training-proposal-failure.json'),
    sha256='1ae9ad87e77a8daf2649839441a14da88cff74c47f7a14306dbbd7ec0cb62a7d')
# Exact closed37 public producer anchors; a coherent rewrite of mutable siblings
# must not become a different scientific proposal under the same failure.
FAILED37_ANCHORS = {
    'loop/round-0001-input.done.json':'f3f764665fbe993e662d87c5f6d1ea24e36667f9bce3fe540462d9414b621bbc',
    'loop/round-0001-controller.done.json':'ea27273a77ed3487caefe6306b249e363bdd47970d180f838c7083c16228b502',
    'loop/round-0001-implement.done.json':'c8cdfbfc30bf96748f84bdaa5e8a5434685f1ba7a5c53d0fde8a96bb965c133d',
    'roles/controller-01/effective-input.json':'987144e723f75b27055580b6b71c9f0d8dc022f497ca1a7433aad98de39942f5',
    'roles/author-01/effective-input.json':'19105941ae3901f2de4f621de3d4990e8e76bfb576437bb0e87d2678927b8f8a',
    'roles/review-01/effective-input.json':'0d23fa41a08fbaad656c95fb8e3a435be3b90be69e1e5ddf7c97c9208c9d4221',
    'roles/controller-01/result.json':'ea26d347e2f813b363cbd2e494c20561207e3fcef55dffaf52fc1610802aaf9e',
    'roles/author-01/result.json':'2b3d2a9d4b7aea34fe0405f88e215ddd425631e7cdd623e127a75bc94315850f',
    'roles/review-01/result.json':'26cd2c2e681b85864f43a014f2cff018025ea429dcba3cb5ecb0e9f9926bd5d8',
}
FAILED37_NATIVE_ANCHORS = {
    'review-01-cases.json':'d4be711766d04fae4fb961d4652785bbff9677b49ea97982cffc008b57a11856',
    'review-01-forecast-probe.json':'d253c3576f404f349164118383d76ef4c2d1377146d255e5585f28abcfc1e465',
    'review-01-parent-forecast-comparison.json':'c3ce93171a64a8dc6ffb2367f23ec9ddc5096e8bae5a6b539dbaffd437186978',
    'review-01-controller-probe.json':'f2e33f68dc2acc15351b5c2fc06caa86350d4a358c3af0c0c178c4889a2dd380',
    'review-01-parent-controller-comparison.json':'a5d1e8f7a2202ff95913f0a3914c4830ecd6dfbe175abe68fb23785c0d20e921',
}


def failed37_policy(consumer_attempt_id, *, company_id):
    """Exact receiving metadata, not runtime admission or a new owner lease."""
    if (type(consumer_attempt_id) is not str
            or re.fullmatch('edgar-population-20261016-[0-9]{2}',consumer_attempt_id) is None
            or int(consumer_attempt_id[-2:]) <= 37 or company_id != FAILED37_COMPANY):
        raise ValueError('Distinct prospective same-Alico consumer for failed37 required')
    return dict(mode=FAILED37_MODE,consumer_attempt_id=consumer_attempt_id,company_id=company_id,
                failed_attempt=deepcopy(FAILED37),authority=deepcopy(FAILED37_AUTHORITY))


def _failed37_counts(reader, attempt, runtime, selected, parent, child):
    """Four real Review responses, attempted fifth count; never rewrite result."""
    roles={}; evidence=[]; counts={'controller':8,'author':8,'review':4}
    for role,n in counts.items():
        folder=attempt/'roles'/(role+'-01'); bound=reader.pin(folder/'result.json'); value=reader.read(bound)
        wall=value.get('wall_seconds'); failed=role=='review'
        if (value.get('status') != ('FAILED_NO_RETRY' if failed else 'COMPLETED_DECISION' if role=='controller' else 'COMPLETED_CANDIDATE')
                or value.get('error_type') != ('BudgetStop' if failed else None) or value.get('retry_allowed') is not False
                or value.get('turns') != (5 if failed else 8) or value.get('tool_calls') != (4 if failed else 7)
                or value.get('final_numbered_response') != f'{n:02d}-response.json'
                or type(wall) not in (int,float) or not math.isfinite(wall) or not 0<=wall<=runtime['limits'][role]['wall_seconds']
                or {p.name for p in folder.glob('[0-9][0-9]-request.json')} != {f'{i:02d}-request.json' for i in range(1,n+1)}
                or {p.name for p in folder.glob('[0-9][0-9]-response.json')} != {f'{i:02d}-response.json' for i in range(1,n+1)}
                or not failed and reader.read(reader.pin(folder/'response.json')) != reader.read(reader.pin(folder/f'{n:02d}-response.json'))):
            raise ValueError('Exact completed C8/A8 and failed Review4-of5 transcripts required')
        roles[role]=value; evidence.append(bound)
    if {p.name for p in (attempt/'roles').iterdir()} != {r+'-01' for r in counts}:
        raise ValueError('Only original C/A/failed Review slots may transfer')
    folder=attempt/'roles/review-01'; packet=reader.read(reader.pin(folder/'effective-input.json'))
    _packet_identity(packet,'review',selected,parent['R'],child)
    if (any((folder/name).exists() for name in ('review.json','05-request.json','05-response.json'))
            or reader.read(reader.pin(folder/'response.json'))!=reader.read(reader.pin(folder/'04-response.json'))):
        raise ValueError('Failed37 has no completed Review verdict or fifth generation')
    paths=sorted(folder.glob('05-context-*-count.json'))
    if [p.name for p in paths] != ['05-context-01-count.json','05-context-04-count.json']:
        raise ValueError('Exact native/public-final failed Review count pair required')
    for path,expected in zip(paths,(32976,33290),strict=True):
        bound=reader.pin(path); counted=reader.read(bound); meta=reader.pin(path.with_name(path.name.replace('-count.json','.json')))
        preparation=reader.read(meta); matches=[]
        for intent_path in folder.glob('http-*.intent.json'):
            intent=reader.read(reader.pin(intent_path))
            if intent.get('endpoint') != '/v1/responses/input_tokens':continue
            prefix=intent_path.name.removesuffix('.intent.json')
            side=reader.pin(folder/(prefix+'.response.json'))
            if reader.read(side)==counted:matches.append((reader.pin(intent_path),intent,side,reader.pin(folder/(prefix+'.raw.bin'))))
        if len(matches)!=1:raise ValueError('Original failed count physical response required')
        intent_bound,intent,side,raw=matches[0]; payload=intent['payload']
        if (runtime['limits']['review']['max_input_tokens']!=32000 or counted.get('input_tokens')!=expected
                or preparation.get('schema')!='earnings_context_preparation_v1' or preparation.get('generation_not_sent') is not True
                or preparation.get('max_input_tokens')!=32000
                or preparation.get('effective_request_sha256')!=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
                or payload.get('model')!=runtime['rates']['api_model'] or strict_json(payload['input'][0]['content'])!=packet
                or reader.read(raw)!={k:v for k,v in counted.items() if k!='_request_id'}):
            raise ValueError('Exact failed37 count/payload/ceiling proof differs')
        evidence += [bound,meta,intent_bound,side,raw]
    return roles,counts,evidence


def load_failed37_prefix(binding, *, consumer_attempt_id, root, ledger, repo):
    """Authenticate original37 C/A only; no successful Review/owner is invented.

    The caller separately owes source-bound new-consumer opt-in, current original
    preflight/owner/clock/budget admission and a genuinely new independent Review.
    """
    policy=failed37_policy(consumer_attempt_id,company_id=FAILED37_COMPANY)
    root,ledger,repo=map(Path,(root,ledger,repo)); attempt=root/'attempts'/FAILED37_ID
    if (binding!=FAILED37 or root!=completed.bootstrap.OWNED or ledger!=completed.bootstrap.LEDGER
            or repo!=completed.bootstrap.REPO or any(p.resolve()!=p for p in (root,ledger,repo,attempt))):
        raise ValueError('Exact canonical owned failed37 and authority required')
    reader=history._Reader(root,ledger,repo,FAILED37_ID)
    registry=ledger.parent/'.capacity-runtime-claims'; key=hashlib.sha256(FAILED37_ID.encode()).hexdigest()
    claim_bound,owner_bound=[reader.pin(registry/(key+suffix)) for suffix in ('.json','.result.json')]
    reader.extra.update(Path(b['path']) for b in (claim_bound,owner_bound,FAILED37_AUTHORITY,tasks.FULL_PLAN,tasks.SCORER))
    authority=reader.read(FAILED37_AUTHORITY); reuse=authority.get('reuse_scope',{})
    if (authority.get('schema')!='earnings_training25_direct_review200k_reuse37_authority_v1'
            or authority.get('direct_human_answer')!='make it 200k?' or reuse.get('failed_attempt')!=FAILED37_ID
            or reuse.get('failure_sha256')!=binding['sha256']):
        raise ValueError('Exact direct narrow37 reuse authority required')
    failure=reader.read(binding); owner,claim=reader.read(owner_bound),reader.read(claim_bound)
    runtime_bound=failure.get('runtime'); runtime=reader.read(runtime_bound)
    if (failure!=dict(schema='earnings_training25_proposal_failure_v1',status='FAILED_NO_RETRY',error_type='LoopHalted',
                    native_closure=None,retry_allowed=False,runtime=runtime_bound)
            or runtime_bound.get('path')!=str(root/'inputs'/FAILED37_ID/'runtime-reviewed.json')
            or owner.get('runtime')!=runtime_bound or owner.get('status')!='FAILED_NO_RETRY'
            or owner.get('error_type')!='LoopHalted' or owner.get('retry_allowed') is not False
            or claim.get('runtime')!=runtime_bound or claim.get('id')!=FAILED37_ID or claim.get('retry_allowed') is not False
            or claim.get('source_commit')!=runtime.get('source_commit') or runtime.get('id')!=FAILED37_ID
            or runtime.get('schema')!='earnings_population_runtime_v1' or runtime.get('root')!=str(attempt)
            or runtime.get('ledger')!=str(ledger) or runtime.get('companies')!=[FAILED37_COMPANY]
            or runtime.get('training_proposal_policy')!=runtime_module.PROPOSAL_POLICY
            or any((attempt/name).exists() for name in ('training-proposal-result.json','population-run-result.json','population-run-failure.json','frozen-pool-01.json'))
            or any((attempt/'roles').glob('forecast-*')) or any(attempt.rglob('score.json')) or any(attempt.rglob('predictions.json'))):
        raise ValueError('Original failed37 owner/claim/unscored proposal differs')
    reader.register_sources(runtime); reader.extra.update(Path(runtime[k]['path']) for k in ('review','budget_amendment','model_budget_amendment'))
    anchors=[dict(path=str(attempt/name),sha256=sha) for name,sha in FAILED37_ANCHORS.items()]
    study=reader.read(runtime['forecast_study']); scope,_=completed._training(reader,runtime,study,preview=True)
    if scope is None:raise ValueError('Original failed37 training admission required')
    from earnings_population_training25 import admit
    admit(scope,FAILED37_COMPANY)  # Before resident, candidate or predecessor artifact bodies.
    for bound in anchors:reader.read(bound)
    task=runtime_module.proposal_task(runtime)
    if task is None or task.get('smoke_company_id')!=FAILED37_COMPANY:raise ValueError('Original whole25 proposal task required')
    base=completed.load(runtime_module.PROPOSAL_ORIGIN,root=root,ledger=ledger,repo=repo)
    if base['previous_result']!=runtime_module.PROPOSAL_ORIGIN:raise ValueError('Authentic completed36 predecessor required')
    completed._register(reader,base,training_scope=scope); _,evidence=completed._training(reader,runtime,study,inherited=base)
    from earnings_population_recovery import _prefix as failed_prefix
    seed,outputs,prefix_evidence=failed_prefix(reader,runtime,attempt,failed_stage='source_review')
    if seed['population']!=base['population'] or reader.read(seed['feedback'])!=base['research_feedback'] or seed['last_scored_feedback']!=base['last_scored_feedback']:
        raise ValueError('Original failed37 scientific predecessor/seed differs')
    state=pool.validate(base['population']); packet=reader.read(outputs['input']['packet'])
    chosen_bound=outputs['controller']['decision']; chosen=reader.read(chosen_bound); child=outputs['implement']['candidate']
    parent=state['versions'].get(chosen.get('parent_pair_sha256'))
    if (packet.get('population')!=state or packet.get('feedback')!=seed['feedback'] or packet.get('company_id')!=FAILED37_COMPANY
            or packet.get('round_index')!=1 or packet.get('parent_feedback_sha256')!=digest(seed['feedback']) or packet.get('campaign')!=study['campaign']
            or chosen.get('feedback_sha256')!=digest(seed['feedback']) or chosen.get('axis')!='R' or parent is None
            or parent['id']!=reuse.get('actual_parent') or parent['id'] not in [state['stable_id'],*state['explorers']]
            or parent['id'] in task['archive_only_version_ids'] or child.get('id')!=reuse.get('candidate_id')
            or child.get('R',{}).get('sha256')!=reuse.get('R_sha256') or child.get('H',{}).get('sha256')!=reuse.get('H_sha256')
            or reader.read(reader.pin(attempt/'roles/controller-01/decision.json'))!=dict(original=reader.pin(attempt/'roles/controller-01/response.json'),decision=chosen)
            or decode_proposal(reader.read(reader.pin(attempt/'roles/controller-01/response.json')),
                reader.read(reader.pin(attempt/'roles/controller-01/effective-input.json')))!=chosen):
        raise ValueError('Original failed37 Controller/parent/fresh candidate differs')
    parent,selected,business,parsed,authored=_authored(reader,attempt,state,chosen,child,runtime)
    if reader.pin(attempt/'roles/author-01/cases.py')['sha256']!=reuse.get('tests_sha256'):
        raise ValueError('Exact authorized37 literal tests required')
    roles,counts,failed_count_evidence=_failed37_counts(reader,attempt,runtime,selected,parent,child)
    native=Path('/private/tmp')/('market-rsi-'+FAILED37_ID); resident=tasks.resident(FAILED37_COMPANY)
    native_anchors=[dict(path=str(native/name),sha256=sha) for name,sha in FAILED37_NATIVE_ANCHORS.items()]
    for bound in native_anchors:reader.read(bound)
    cases_bound=reader.pin(native/'review-01-cases.json'); cases=reader.read(cases_bound)
    if cases.get('candidate_id')!=child['id'] or len(cases.get('results',[]))!=len(parsed['cases']) or len(parsed['cases'])!=7:
        raise ValueError('Seven original failed37 candidate cases required')
    for case,row in zip(parsed['cases'],cases['results'],strict=True):
        if row.get('passed') is not True or digest(researcher.execution_value(row['execution'],business['source_text'],case['input']))!=digest(case['expected']):
            raise ValueError('Original failed37 isolated source/input/case result differs')
    probes=[]
    for stage in ('forecast','controller'):
        bound,matched=[reader.pin(native/name) for name in (f'review-01-{stage}-probe.json',f'review-01-parent-{stage}-comparison.json')]
        probe,comparison=reader.read(bound),reader.read(matched); payload=probe['input']; files=FilingTools(resident['company']).files
        if (probe.get('company_id')!=FAILED37_COMPANY or payload!=comparison['input'] or payload.get('stage')!=stage or payload.get('records')!=[]
                or payload.get('questions')!=files['questions.md'] or payload.get('filing_index')!=files['filing_index.tsv']
                or comparison.get('parent_version_id')!=parent['id']):raise ValueError('Original failed37 matched cold payload differs')
        researcher.verify(probe['execution'],business['source_text'],payload,resident['company'])
        researcher.verify(comparison['execution'],reader.read(parent['R'],binary=True).decode(),payload,resident['company'])
        probes.append(dict(company_id=FAILED37_COMPANY,stage=stage,receipt=bound,matched_parent=matched,diagnostics=deepcopy(probe['diagnostics'])))
    if (native/'review-01-outcome.json').exists():raise ValueError('Failed37 has no independent Review outcome')
    from earnings_population_campaign_context import _training_context
    summary=_training_context(study,packet,scope)['training_comparator']
    evidence+=anchors+native_anchors+prefix_evidence+authored+failed_count_evidence+[cases_bound]+[b for p in probes for b in (p['receipt'],p['matched_parent'])]
    evidence+=_physical(reader,runtime,task,summary,roles,completed_generations=counts)
    evidence+=completed._budget(reader,runtime,owner,dict(budget=owner['budget_summary']))
    clock=reader.pair(attempt/'clock.json'); review=reader.read(runtime['review'])
    if (review.get('verdict')!='PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY' or review.get('blocking_findings')!=[]
            or review.get('source_commit')!=reader.commit or str(review.get('reviewer','')).lower() in {'','root','/root'}
            or review.get('reviewed_configuration_sha256')!=digest({k:v for k,v in runtime.items() if k!='review'})
            or clock!=reader.read(owner['clock']) or clock.get('source_commit')!=reader.commit
            or clock.get('cutoff_utc')!=runtime['cutoff_utc'] or clock.get('deadline_utc')!=runtime['deadline_utc']):
        raise ValueError('Original failed37 distinct configuration/clock review differs')
    expected={name+'-01':dict(role=name,company_id=FAILED37_COMPANY,version=version)
              for name,version in (('controller',state['versions'][state['stable_id']]),('author',parent),('review',child))}
    python=completed._literal(reader,runtime['sources']['tools/earnings_population_run.py'],'PYTHON')
    evidence+=completed._native(reader,native,runtime_bound,runtime,expected,resident,python,training_scope=scope)
    cleanup=_cleanup(attempt); evidence += [r['result'] for r in cleanup]
    reader.extra.add(Path(resident['kernel']['qa']['path']));reader.scan(runtime);reader.scan(study);reader.scan(outputs)
    bundle=dict(schema='earnings_population_author_stage_reuse_v1',mode='review_existing_candidate_v1',candidate=deepcopy(child),
        decision=chosen_bound,scientific_decision=selected,raw_patch_response=reader.pin(attempt/'roles/author-01/response.json'),
        assembly=reader.pin(attempt/'roles/author-01/delta-assembly.json'),tests=reader.pin(attempt/'roles/author-01/cases.py'),source=child['R'],
        parent_source=parent['R'],cases=cases_bound,probes=probes,failed_attempt=deepcopy(binding),
        new_model_Controller_called=False,new_model_Author_called=False)
    return dict(schema=FAILED37_SCHEMA,mode=FAILED37_MODE,policy=policy,consumer_attempt_id=consumer_attempt_id,
        company_id=FAILED37_COMPANY,failed_attempt=deepcopy(binding),authority=deepcopy(FAILED37_AUTHORITY),
        completed_origin=base['previous_result'],base_origin=deepcopy(base),task=deepcopy(task),candidate=deepcopy(child),parent=deepcopy(parent),
        original_decision=chosen_bound,scientific_decision=deepcopy(selected),author_stage_reuse=bundle,
        review_assessment='not_completed',original_completed_generations=counts,
        evidence=[binding,FAILED37_AUTHORITY,runtime_bound,claim_bound,owner_bound,runtime['review'],study['training_proposal_task'],*evidence,*base['evidence']])
