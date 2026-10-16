"""Prepare, never dispatch, an opt-in episode using resident data and ledger."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import earnings_open_admission as live
import earnings_open_assembly as assembly
import earnings_capacity_runtime as owner
import earnings_native_namespace as namespace
from earnings_capacity_checks import MechanicalProbes
from earnings_effect_review import review as effect_review,SCOPES
from earnings_research_state import ResearchState
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


def prepare(number, *, carry_forward=False, research_followup=False):
    e=live.e
    if type(carry_forward) is not bool or type(research_followup) is not bool:
        raise ValueError('Explicit source carry-forward and fresh follow-up flags required')
    policy=None
    if research_followup:
        import earnings_open_fresh_grant as fresh
        policy=fresh.policy()
        if not carry_forward:raise ValueError('Fresh follow-up must inherit selected sources')
    if type(number) is not int or not 1<=number<=99:raise ValueError('Fresh bounded attempt number required')
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=e.REPO,check=True,capture_output=True,text=True).stdout.strip()
    if subprocess.run(['git','status','--porcelain'],cwd=e.REPO,check=True,capture_output=True).stdout:
        raise ValueError('Commit source/configs before prospective preparation')
    ident=(f'edgar-research-20261015-{number:02d}' if policy else f'edgar-open-20261014-{number:02d}')
    artifact_root=fresh.ROOT if policy else live.ROOT
    root=artifact_root/'attempts'/ident;home=artifact_root/'inputs'/ident
    paths=namespace.native_paths(root,ident)
    if home.exists() or root.exists() or any(path.exists() for path in paths.values()):
        raise ValueError('Consumed or failed preparations remain closed')
    old=live.read(live.original.original.pin(live.original.original.CANARIES.parent/'config-prospective-02.json'))
    ledger=Path(old['ledger'])
    with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        if (db.execute('SELECT * FROM config').fetchall()!=[(1,200_000_000_000,100_000_000_000,0)]
                or db.execute("SELECT 1 FROM requests WHERE status NOT IN ('settled','settled_upper_bound')").fetchone()):
            raise ValueError('Original idle sole ledger required')
        baseline=live.history_snapshot(db,policy['baseline']['max_rowid'] if policy else live.BASELINE_ROWS)
        charged=db.execute('SELECT COALESCE(SUM(charged),0) FROM requests').fetchone()[0]
    cap=fresh.pilot_cap(policy) if policy else live.PILOT_CAP
    rounds=fresh.requested_rounds(policy) if policy else 2
    if ((policy is not None and baseline!=policy['baseline'])
            or (policy is None and (baseline['charged_nano_usd']!=live.BASELINE_CHARGED or baseline['request_count']!=live.BASELINE_ROWS))
            or charged-baseline['charged_nano_usd']>=cap):
        raise ValueError('Already consumed pilot budget cannot be rebased')
    now=datetime.now(timezone.utc).replace(microsecond=0)
    fmt=lambda value:value.strftime('%Y-%m-%dT%H:%M:%SZ')
    cutoff,deadline=((policy['window'] if policy else live.PILOT_WINDOW)[k] for k in ('cutoff_utc','deadline_utc'))
    if now.timestamp()>=live.utc_epoch(cutoff):
        raise ValueError('Fixed window closed; a new ID cannot extend it')
    grant={'schema':fresh.SCHEMA if policy else 'earnings_open_grant_v1','id':ident,'root':str(root),'source_commit':commit,
        'sources':{name:e.digest((e.REPO/name).read_bytes()) for name in live.sources()},
        'python':live.original.original.pin(Path(sys.executable).absolute()),'data':old['pilot_plan'],
        'runtime':old['runtime'],'scorer':old['scorer'],'qa':old['qa'],'cik':old['cik'],'ledger':old['ledger'],
        'baseline':baseline,'cutoff_utc':cutoff,'deadline_utc':deadline,'additional_cap_nano_usd':cap,
        'human_authorization':fresh.AUTHORIZATION if policy else live.AUTHORIZATION,
        'allowed_egress':fresh.EGRESS if policy else live.EGRESS,'bootstrap_no_model_call':policy is None}
    company,runtime=live.original.task(grant)
    lineage=None
    if carry_forward:
        from earnings_open_continuation import prior
        lineage=prior()
    home.mkdir(parents=True,exist_ok=False)
    def save(name,value):return engine.save(home/name,value)
    source=paths['source_root'];source.mkdir(parents=True,exist_ok=False)
    copies={'predictor.py':e.REPO/'tools/edgar_forecast_openai.py',
        'researcher_v0.py':e.REPO/'configs/earnings_coevolution/program_R0.py',
        'harness_v0.py':e.REPO/'configs/earnings_coevolution/program_H0.py',
        'evaluation_scorer.py':Path(grant['scorer']['path']),'evaluation_qa.json':Path(grant['qa']['path'])}
    if lineage:
        copies.update({name:Path(lineage['sources'][axis]['path'])
            for axis,name in [('R','researcher_v0.py'),('H','harness_v0.py')]})
    for name,path in copies.items():
        shutil.copyfile(path,source/name);(source/name).chmod(0o600)
        if e.digest((source/name).read_bytes())!=e.digest(path.read_bytes()):raise ValueError('Original protected copy drift')
    state=ResearchState(company,ident)
    initial=state.save(home/'initial-state',state.empty())
    snapshot=save('original-runtime-snapshot.json',{'schema':'original_runtime_snapshot_v1','source':grant['runtime'],'config':runtime})
    kernel={'scorer':grant['scorer'],'qa':grant['qa']}
    case={k:company[k] for k in ('cik','cutoff','target_accession','visible_root')}
    case.update(evaluation_kernel=kernel,allowed_manifest_sha256=e.digest(json.dumps(company['allowed_files'],sort_keys=True,separators=(',',':')).encode()))
    model={'requested_model':'gpt-6.1-sol','serving_snapshot':'unknown','serving_snapshot_verified':False}
    granted=save('grant.json',grant)
    lineage_fields={'program_lineage':save('program-lineage.json',lineage)} if lineage else {}
    study=save('study.json',{'schema':'earnings_coevolution_study_v1','data':grant['data'],'scorer':grant['scorer'],
        'runtime_config':runtime,'python':grant['python'],'sole_ledger':grant['ledger'],'cases':[case],'model':model,
        'prior_batch':snapshot,'new_live_grant':granted,'new_episode_deadline':deadline,'exposure':'EXPOSED_DISCOVERY_NOT_UNTOUCHED',**lineage_fields})
    rows=[{r:str(root/'roles'/f'{r}-{i:02d}') for r in ('controller','author','review','forecast')} for i in range(1,rounds+1)]
    envelope={'schema':live.SCHEMA,'mode':'real_provider','id':ident,'root':str(root),'source_commit':commit,
        'sources':grant['sources'],'study':study,'cik':company['cik'],'max_rounds':rounds,
        'role_limits':live.role_limits(),'slots':rows,
        'initial_state':initial,'grant':granted,'window':{k:grant[k] for k in ('cutoff_utc','deadline_utc')},'evaluation_kernel':kernel}
    episode=save('episode.json',envelope)
    matched={'schema':'earnings_matched_plan_v1','episode':episode,'rounds':[{
        'parent':str(root/'roles'/f'parent-{i:02d}'),'candidate':str(root/'roles'/f'candidate-{i:02d}'),
        'downstream':row['forecast']} for i,row in enumerate(rows,1)]}
    limits=live.role_limits()
    limits['forecast']={'max_input_tokens':runtime['max_input_tokens'],
        'max_output_tokens':max(runtime['max_output_tokens'],runtime.get('final_max_output_tokens',0)),
        'wall_seconds':runtime['company_wall_seconds']}
    resources={'schema':'earnings_capacity_runtime_v2','purpose':'capacity_episode','id':ident,'root':str(root),
        'source_commit':commit,'ledger':grant['ledger'],'baseline':baseline,'cutoff_utc':cutoff,'deadline_utc':deadline,
        'additional_cap_nano_usd':cap,'rates':runtime['models']['gpt-6.1-sol'],'limits':limits,
        'slots':live.slots(envelope,matched),'forecast_study':study,'sources':{
            **{name:engine.pin(path) for name,path in owner.CORE.items()},'forecast_entry':engine.pin(e.__file__),
            'forecaster':engine.pin(e.REPO/'tools/edgar_forecast_openai.py'),
            **{'factory_'+role:engine.pin(assembly.__file__) for role in ('controller','author','review','forecast')}}}
    if policy and policy.get('author_configuration'):
        from earnings_open_resources import ROLE_EFFORTS
        resources['role_efforts']=dict(ROLE_EFFORTS)
    resource=save('runtime.json',resources)
    component=lambda names,config:{'sources':{name:e.digest((source/name).read_bytes()) for name in names},'configuration_sha256':digest(config)}
    program_config=lambda axis:{'program':axis+'0'} if lineage is None else {
        'program':'inherited_'+axis,'prior_pair_sha256':lineage['prior_pair_sha256'],
        'inherited_source_sha256':lineage['sources'][axis]['sha256']}
    manifest=engine.identity.manifest(kernel=component(['evaluation_scorer.py','evaluation_qa.json'],kernel),
        predictor=component(['predictor.py'],{'output':'original_five_numeric_predictions'}),
        harness=component(['harness_v0.py'],program_config('H')),researcher=component(['researcher_v0.py'],program_config('R')),
        model=model,memory=initial['sha256'],runtime={'python':grant['python'],'dependencies':{}})
    source_review={'schema':'earnings_source_review_setup_v1','source_root':str(source),
        'proposer_id':'actual-model-author-'+ident,'reviewer_id':'trusted-host-effect-review-'+ident,
        'slots':{row['review']:{'candidate_id':f'{ident}-child-{i:02d}','R':f'researcher_child_{i:02d}.py',
            'H':f'harness_child_{i:02d}.py'} for i,row in enumerate(rows,1)}}
    native={'schema':'earnings_native_setup_v1',**{k:str(paths[k]) for k in ('source_root','registry_root','batch_root')},
        'baseline':manifest,'entrypoints':{'R':'researcher_v0.py','H':'harness_v0.py'},
        'batch_config':{'batch_id':ident,'start_utc':fmt(now),'deadline_utc':deadline,'max_attempts':3*rounds,
            'initial_incumbent':{'candidate_id':'fixed-original-forecast','candidate_sha256':manifest['C'],
                'scorecard_sha256':'0'*64,'review_sha256':'0'*64},'active_pool_capacity':2,'learning_checkpoint_version':1},
        'micro_config':{'pair':engine.activation.pair(manifest),'fixed_context':{'model_sha256':manifest['M'],
            'evaluation_sha256':manifest['K'],'data_scope_sha256':digest({'study':study,'cik':company['cik'],'kernel':kernel}),
            'authority_sha256':digest({k:envelope[k] for k in ('mode','grant','window')}),'resource_policy_sha256':digest(resource)},
            'allowed_write_paths':{kind:[f'{prefix}_v0.py',*[row[axis] for row in source_review['slots'].values()]]
                for axis,kind,prefix in [('R','researcher','researcher'),('H','harness','harness')]},
            'protected_paths':['predictor.py','evaluation_scorer.py','evaluation_qa.json'],'reviewer_id':source_review['reviewer_id']}}
    registration={'schema':'earnings_effect_review_registration_v1','reviewer_id':source_review['reviewer_id'],
        'proposer_id':source_review['proposer_id'],'review_source':engine.source_of(effect_review),
        'probe_source':engine.source_of(MechanicalProbes.run),'scopes':SCOPES}
    transport=save('transport-policy.json',{'schema':('edgar_foreground_role_socket_policy_v1' if policy else 'edgar_foreground_slow_call_policy_v1'),'source_commit':commit,
        'original_runtime_request_timeout_seconds':runtime['request_timeout_seconds'],'effective_socket_timeout_seconds':600,
        'role_and_global_deadlines_unchanged':True,'retry_allowed':False,
        **({'author_socket_timeout_seconds':900} if policy else {}),
        **({'author_reasoning_effort':'high'} if 'role_efforts' in resources else {})})
    assembled=save('assembly.json',{'schema':'earnings_open_assembly_v1','episode':episode,'runtime':resource,
        'native':save('native.json',native),'matched_plan':save('matched-plan.json',matched),
        'effect_registration':save('effect-registration.json',registration),'source_review':save('source-review.json',source_review),
        'constructors':assembly.constructors(),'transport':engine.source_of(assembly.provider_client),
        'transport_policy':transport,'independent_review':None,'claims':{'model_authorship':False,'predictive_gain':False}})
    assembly.validate(episode,assembled,require_review=False)
    return save('prepared.json',{'schema':'earnings_open_prepared_v1','episode':episode,'assembly':assembled,
        'source_commit':commit,'provider_calls':0,'status':'AWAITING_DISTINCT_REVIEW_NO_OWNER'})


def attach_review(prepared_binding,review_binding):
    prepared=live.read(prepared_binding)
    body=live.read(prepared['assembly'])
    body['independent_review']=review_binding
    home=Path(prepared['assembly']['path']).parent
    bound=engine.save(home/'assembly-reviewed.json',body)
    assembly.validate(prepared['episode'],bound)
    return engine.save(home/'prepared-reviewed.json',dict(prepared,assembly=bound,status='SOURCE_REVIEWED_NOT_DISPATCHED'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--number',type=int,required=True)
    parser.add_argument('--carry-forward',action='store_true')
    parser.add_argument('--research-followup',action='store_true')
    args=parser.parse_args()
    print(json.dumps(prepare(args.number,carry_forward=args.carry_forward,research_followup=args.research_followup)))
