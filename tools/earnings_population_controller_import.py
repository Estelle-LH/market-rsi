"""Read-only import of original22's completed, but undelivered, public proposal.

The old Controller remains FAILED. No old slot is reopened and no model call,
Author, candidate, acceptance or score is manufactured by this verifier.
"""
from contextlib import closing
from copy import deepcopy
import hashlib
from pathlib import Path
import sqlite3

import earnings_population as pool
import earnings_population_continuation as history
import earnings_population_campaign_resume as resume
import earnings_population_tasks as tasks
from earnings_native_failure import _cleanup, _owned_requests
from earnings_night_budget import history_snapshot
from market_rsi import digest

MODE = 'received_completed_controller_proposal_v1'
IDENT = 'edgar-population-20261016-22'
SOURCE = '3d5b59b34c872b672417097d956704833babeef7'
RUNTIME_SHA = '5549479547bcde0274e1fb923fee1b1884ad0db381fde2f34d5cc38de2839ce7'
FAILURE_SHA = '9f781795ffb9d54442e3625d98876fb978db4045a8a5bcd7cb24195933c0a5f5'
AUDIT_SHA = '281f2f5fdbbb78289d6c0e4513a6113816b2eaf75cbc6f602ee9feb29f6c46a4'


def _prefix(reader, runtime, study, attempt):
    """Original input seal followed by a failed Controller claim, nothing later."""
    path=attempt/'loop'
    with history._journal_lock(path):
        manifest=reader.pair(path/'manifest.json'); seed=manifest['seed']
        if (manifest.get('schema')!='feedback_linked_loop_v1' or manifest.get('seed_sha256')!=digest(seed)
                or manifest.get('max_rounds')!=len(runtime['companies'])
                or seed['companies']!=runtime['companies']
                or seed['population']!=reader.read(runtime['initial_population'])
                or manifest['driver_source_sha256']!=runtime['sources'][history.DRIVER]['sha256']
                or set(manifest['handler_identity'])!=set(history.STAGES)):
            raise ValueError('Original Controller failure seed/driver differs')
        for stage,identity in manifest['handler_identity'].items():
            expected=dict(stage=stage,adapter=runtime['sources']['tools/earnings_population_loop.py'],
                admission={'function':'execute.<locals>.admit','module':runtime['sources']['tools/earnings_population_run.py']},
                services={r:{'function':'Services.'+r,'module':runtime['sources']['tools/earnings_population_services.py']}
                          for r in ('controller','author','review','forecast')},
                campaign_policy=runtime['sources']['tools/earnings_population_campaign.py'],campaign=study['campaign'])
            if identity!=expected:raise ValueError('Original Controller failure handler differs')
        outputs={};files=set();evidence=[reader.pin(path/'manifest.json')]
        for stage in ('input','controller'):
            stem=path/f'round-0001-{stage}';claim=stem.with_suffix('.claim.json')
            current=dict(round_index=1,seed=seed,previous_result=seed,previous_feedback_sha256=digest(seed),outputs=outputs)
            if reader.read(reader.pin(claim))!=dict(round_index=1,stage=stage,context_sha256=digest(current),
                    manifest_sha256=evidence[0]['sha256'],previous_feedback_sha256=digest(seed)):
                raise ValueError('Original Controller failure claim differs')
            files.add(claim.name);evidence.append(reader.pin(claim))
            if stage=='controller':
                failed=stem.with_suffix('.failed.json')
                if reader.read(reader.pin(failed))!=dict(claim_sha256=reader.pin(claim)['sha256'],
                        exception_type='RuntimeError',retry_allowed=False):
                    raise ValueError('Original Controller failed-stage seal differs')
                files.add(failed.name);evidence.append(reader.pin(failed));break
            done=stem.with_suffix('.done.json');row=reader.pair(done)
            if (set(row)!={'claim_sha256','output','output_sha256'}
                    or row['claim_sha256']!=reader.pin(claim)['sha256'] or row['output_sha256']!=digest(row['output'])):
                raise ValueError('Original input done seal differs')
            reader.scan(row['output']);outputs[stage]=row['output']
            files.update((done.name,done.with_suffix('.binding.json').name));evidence.append(reader.pin(done))
        if {p.name for p in path.glob('round-*')}!=files:
            raise ValueError('Only input-complete/Controller-failed prefix may import')
    return seed,outputs['input'],evidence


def _settled(reader,runtime,owner,settlement,proof,request):
    from earnings_population_budget import validate_cap,CAP
    from earnings_population_reconcile import RECEIVED_MODE,RECEIVED_POLICY
    result=settlement['operator_return'];closed=result['after'];rows=_owned_requests(runtime)
    if (settlement.get('id')!=IDENT or settlement.get('original_owner_result_preserved')is not True
            or result.get('mode')!=RECEIVED_MODE or result.get('policy')!=RECEIVED_POLICY
            or result.get('actual_charge_known')is not False or result.get('refund_nano_usd')!=0
            or result.get('retry_allowed')is not False or result.get('request_id')!=request['request_id']
            or result.get('before')!=proof['ledger_before']
            or result.get('conservative_charge_nano_usd')!=request['reserved_nano_usd']
            or round(owner['budget_summary']['unresolved_reserved_usd']*1e9)!=request['reserved_nano_usd']
            or len(rows)!=8 or len({r['request_id']for r in rows})!=8
            or closed['max_rowid']!=runtime['baseline']['max_rowid']+8):
        raise ValueError('Exact separate completed-raw ceiling settlement required')
    with closing(sqlite3.connect(reader.ledger.as_uri()+'?mode=ro',uri=True))as db:
        db.execute('BEGIN')
        reconciled=db.execute('SELECT evidence_sha256,prior_status,prior_charge,ceiling,policy FROM reconciliations WHERE request_id=?',
            (request['request_id'],)).fetchall()
        if (validate_cap(db,amendment=runtime['budget_amendment'])!=CAP
                or history_snapshot(db,runtime['baseline']['max_rowid'])!=runtime['baseline']
                or history_snapshot(db,closed['max_rowid'])!=closed
                or {r[0]for r in db.execute('SELECT id FROM requests WHERE rowid>? AND rowid<=?',
                    (runtime['baseline']['max_rowid'],closed['max_rowid']))}!={r['request_id']for r in rows}
                or reconciled!=[(result['evidence']['sha256'],'uncertain',0,request['reserved_nano_usd'],RECEIVED_POLICY)]
                or closed['charged_nano_usd']!=runtime['baseline']['charged_nano_usd']+sum(r['charged_nano_usd']for r in rows)):
            raise ValueError('Original owned settled prefix/reconciliation differs')
    return rows


def _physical(reader,runtime,attempt,prompt,rows,proof):
    from edgar_forecast_openai import unit
    slot=attempt/'roles/controller-01';limits=runtime['limits']['controller'];rates=runtime['rates']
    expected={slot/f'{i:02d}-request.json'for i in range(1,9)}
    if {Path(r['request']['path'])for r in rows}!=expected:
        raise ValueError('Exactly eight original Controller reservations required')
    evidence=[];intents=[(p,reader.read(reader.pin(p)))for p in slot.glob('http-*.intent.json')]
    if len([x for _,x in intents if x.get('endpoint')=='/v1/responses'])!=8:
        raise ValueError('Exactly eight original physical Controller generations required')
    for own in rows:
        bound=own['request'];path=Path(bound['path']);number=path.name[:2];request=reader.read(bound)
        count=reader.pin(slot/f'{number}-count.json');tokens=reader.read(count)['input_tokens'];payload=request['payload']
        matched=[(p,x)for p,x in intents if x.get('endpoint')=='/v1/responses' and x.get('complete_reservation')==request]
        if (type(tokens)is not int or not 0<=tokens<=limits['max_input_tokens'] or len(matched)!=1
                or request['reserved_nano_usd']!=tokens*max(unit(rates[k])for k in ('input','cached','write'))+
                    limits['max_output_tokens']*unit(rates['output'])
                or payload.get('model')!=rates['api_model'] or payload.get('reasoning')!={'effort':runtime['role_efforts']['controller']}
                or history.e.strict_json(payload['input'][0]['content'])!=prompt):
            raise ValueError('Original counted Controller prompt/model/reservation differs')
        p,intent=matched[0]
        if (intent.get('request_receipt_sha256')!=bound['sha256'] or intent.get('budget_request_id')!=request['request_id']
                or intent.get('retry_allowed')is not False or intent.get('payload')!=dict(payload,
                    max_output_tokens=limits['max_output_tokens'],service_tier='default',store=False)):
            raise ValueError('Original physical Controller payload differs')
        evidence += [bound,count,reader.pin(p)]
        if number=='08':
            if bound!=proof['request']or own['status']!='settled_upper_bound'or own['charged_nano_usd']!=request['reserved_nano_usd']:
                raise ValueError('Final undelivered raw must retain its conservative ceiling')
            continue
        response=reader.pin(slot/f'{number}-response.json');value=reader.read(response)
        sidecar=reader.pin(p.with_name(p.name.replace('.intent.json','.response.json')))
        raw=reader.pin(p.with_name(p.name.replace('.intent.json','.raw.bin')))
        usage=value['usage'];inp,out,cached=usage['input_tokens'],usage['output_tokens'],usage['input_tokens_details']['cached_tokens']
        if (reader.read(sidecar)!=value or reader.read(raw)!={k:v for k,v in value.items()if k!='_request_id'}
                or value.get('status')!='completed'or value.get('model')!=rates['api_model']or value.get('service_tier')!='default'
                or any(type(v)is not int or v<0 for v in (inp,out,cached))or not cached<=inp<=tokens
                or out>limits['max_output_tokens']or usage['total_tokens']!=inp+out or own['status']!='settled'
                or own['charged_nano_usd']!=(inp-cached)*max(unit(rates[k])for k in ('input','cached','write'))+
                    cached*unit(rates['cached'])+out*unit(rates['output'])):
            raise ValueError('Original delivered Controller response/charge differs')
        evidence += [response,sidecar,raw]
    return evidence


def _attach(inherited,bundle,*,audit):
    if (inherited.get('author_stage_reuse') is not None
            or bundle.get('schema')!='earnings_population_controller_proposal_import_v1'
            or bundle.get('mode')!=MODE or bundle.get('new_model_called')is not False):
        raise ValueError('Explicit Controller-only proposal import required')
    result=deepcopy(inherited);result['controller_stage_import']=deepcopy(bundle)
    result['recovery_context']['controller_delivery_diagnosis']=dict(schema='earnings_population_controller_delivery_diagnosis_v1',
        mode=MODE,failed_attempt=deepcopy(bundle['failed_attempt']),audit=deepcopy(audit),stage='controller',error_type='BudgetStop',
        completed_role_generations=7,received_final_raw=deepcopy(bundle['raw_response']),original_owner_status='FAILED_NO_RETRY',
        qualification='Original completed public proposal was received but not delivered. Explicit new-window import is not a new Controller call, old-slot success, Author code, quality verdict or score.')
    return result


def load(binding,*,root,ledger,repo,plan):
    """Exact audited22 only; no general failed-window or paid retry authority."""
    from earnings_population_budget import AUTHORIZATION,amendment_binding
    from earnings_population_completed import _literal,_native
    from earnings_population_reconcile import inspect_received_raw_evidence
    from earnings_population_recovery import _capacity_origin
    from earnings_population_roles import decode_proposal
    root,ledger,repo=map(Path,(root,ledger,repo));attempt=root/'attempts'/IDENT
    if (root!=resume.OWNED or ledger!=resume.LEDGER or repo!=resume.REPO
            or any(p.resolve()!=p for p in (root,ledger,repo))
            or binding!=dict(path=str(attempt/'population-run-failure.json'),sha256=FAILURE_SHA)
            or plan.get('id')!='earnings-population-review-recovery-20261016'
            or plan.get('human_authorization')!=AUTHORIZATION or plan.get('recovery_mode')!=MODE
            or plan.get('failed_attempt')!=binding):
        raise ValueError('Exact original22 received Controller proposal authority required before read')
    audit_bound=plan['closed_failure_audit'];settled_bound=plan['operator_settlement']
    if (audit_bound!=dict(path=str(root/'CUMULATIVE400-LIVE22-CLOSURE-AUDIT.json'),sha256=AUDIT_SHA)
            or Path(settled_bound['path']).parent!=root):
        raise ValueError('Exact owned original pending audit and separate settlement required')
    reader=history._Reader(root,ledger,repo,IDENT);stamp=hashlib.sha256(IDENT.encode()).hexdigest()
    claims=ledger.parent/'.capacity-runtime-claims'
    owner_bound,claim_bound=(reader.pin(claims/(stamp+s))for s in ('.result.json','.json'))
    reader.extra.update(Path(b['path'])for b in (audit_bound,settled_bound,owner_bound,claim_bound))
    owner,claim,audit,settlement=[reader.read(b)for b in (owner_bound,claim_bound,audit_bound,settled_bound)]
    runtime_bound=owner['runtime'];runtime=reader.read(runtime_bound)
    if (runtime_bound!=dict(path=str(root/'inputs'/IDENT/'runtime-reviewed.json'),sha256=RUNTIME_SHA)
            or runtime.get('source_commit')!=SOURCE or runtime.get('schema')!='earnings_population_runtime_v1'
            or runtime.get('id')!=IDENT or runtime.get('root')!=str(attempt) or runtime.get('ledger')!=str(ledger)
            or runtime.get('companies')!=[resume.COMPANY] or runtime.get('budget_amendment')!=amendment_binding()
            or owner.get('status')!='FAILED_NO_RETRY'or owner.get('error_type')!='LoopHalted'or owner.get('retry_allowed')is not False
            or claim.get('runtime')!=runtime_bound or claim.get('id')!=IDENT or claim.get('source_commit')!=SOURCE
            or claim.get('retry_allowed')is not False or reader.read(binding)!=dict(status='FAILED_NO_RETRY',error_type='LoopHalted',native_closure=None,retry_allowed=False)
            or (attempt/'population-run-result.json').exists()or {p.name for p in (attempt/'roles').iterdir()}!={'controller-01'}
            or (attempt/'roles/controller-01/decision.json').exists()
            or _cleanup(attempt)or any(attempt.rglob('score.json'))):
        raise ValueError('Original closed Controller-only owner/runtime/source differs')
    reader.register_sources(runtime)
    reader.extra.update(Path(runtime[k]['path'])for k in ('review','budget_amendment'))
    study=reader.read(runtime['forecast_study']);inherited=_capacity_origin(reader,runtime,study,root=root,ledger=ledger,repo=repo)
    resident=tasks.resident(resume.COMPANY)
    reader.extra.update(Path(b['path'])for b in (tasks.FULL_PLAN,tasks.SCORER,resident['kernel']['qa']))
    if (study.get('data')!=tasks.FULL_PLAN or study.get('scorer')!=tasks.SCORER or study.get('runtime_config')!=resident['runtime']
            or study.get('cases')!=[resident['case']]or runtime['rates']!=resident['runtime']['models']['gpt-6.1-sol']):
        raise ValueError('Unchanged original scientific dataset/scorer/model required')
    reader.scan(runtime);reader.scan(study)
    review=reader.read(runtime['review']);clock=reader.pair(attempt/'clock.json')
    if (review.get('verdict')!='PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY'or review.get('blocking_findings')!=[]
            or review.get('source_commit')!=SOURCE or review.get('reviewed_configuration_sha256')!=digest({k:v for k,v in runtime.items()if k!='review'})
            or clock!=reader.read(owner['clock'])or clock.get('source_commit')!=SOURCE
            or clock.get('cutoff_utc')!=runtime['cutoff_utc']or clock.get('deadline_utc')!=runtime['deadline_utc']):
        raise ValueError('Original reviewed Controller source/time binding differs')
    proof,original,request=inspect_received_raw_evidence(settlement['operator_return']['evidence'])
    if original!=runtime:raise ValueError('Separate raw settlement references another runtime')
    for bound in (settlement['operator_return']['evidence'],*[
            proof[k]for k in ('raw_response','input_count','role_identity','role_result','last_numbered_response','http_intent','http_failure','request')]):
        reader.extra.add(Path(bound['path']));reader.read(bound)
    seed,inputs,evidence=_prefix(reader,runtime,study,attempt);state=pool.validate(inherited['population'])
    packet=reader.read(inputs['packet']);control=attempt/'roles/controller-01';prompt_bound=reader.pin(control/'effective-input.json');prompt=reader.read(prompt_bound)
    if (seed['population']!=state or reader.read(seed['feedback'])!=inherited['research_feedback']
            or seed['last_scored_feedback']!=inherited['last_scored_feedback']
            or packet['population']!=state or packet['feedback']!=seed['feedback']
            or packet['parent_feedback_sha256']!=digest(seed['feedback'])
            or prompt.get('feedback_binding')!=seed['feedback']or prompt.get('feedback_sha256')!=digest(seed['feedback'])
            or prompt.get('active_versions')!=[state['stable_id'],*state['explorers']]or prompt.get('explorers')!=state['explorers']
            or prompt.get('stable_id')!=state['stable_id']or prompt.get('company_id')!=resume.COMPANY):
        raise ValueError('Original unchanged pool/feedback and public Controller prompt differ')
    rows=_settled(reader,runtime,owner,settlement,proof,request);evidence+=_physical(reader,runtime,attempt,prompt,rows,proof)
    final=reader.read(proof['raw_response']);chosen=decode_proposal(final,prompt)
    if (audit.get('schema')!='earnings_population_live22_closure_audit_v1'or audit.get('attempt_id')!=IDENT
            or audit.get('status')!='SEALED_FAILED_CONTROLLER_DEADLINE_ONE_RECEIVED_RAW_UNSETTLED'
            or audit['checkpoints'][-1]['owner_terminal']!=dict(binding=owner_bound,value=owner)
            or audit['checkpoints'][-1]['accounting']['snapshot']!=proof['ledger_before']
            or audit['checkpoints'][-1]['root_results']['population-run-failure.json']['binding']!=binding):
        raise ValueError('Original pending Controller closure audit differs')
    native=Path('/private/tmp')/('market-rsi-'+IDENT)
    evidence+=_native(reader,native,runtime_bound,runtime,{'controller-01':dict(role='controller',round_index=1,
        company_id=resume.COMPANY,version=state['versions'][state['stable_id']])},resident,
        _literal(reader,runtime['sources']['tools/earnings_population_run.py'],'PYTHON'))
    bundle=dict(schema='earnings_population_controller_proposal_import_v1',mode=MODE,failed_attempt=deepcopy(binding),
        runtime=runtime_bound,raw_response=proof['raw_response'],original_prompt=prompt_bound,original_decision_public=chosen,
        original_feedback_sha256=prompt['feedback_sha256'],settlement=settled_bound,new_model_called=False)
    result=_attach(inherited,bundle,audit=audit_bound)
    result['evidence'] += [binding,audit_bound,settled_bound,owner_bound,claim_bound,runtime_bound,prompt_bound,*evidence,
        settlement['operator_return']['evidence'],*[proof[k]for k in ('raw_response','input_count','role_identity','role_result','last_numbered_response','http_intent','http_failure')]]
    return result
