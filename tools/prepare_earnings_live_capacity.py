"""Prepare one bounded real R/H configuration; never load a key or infer."""
import argparse
from datetime import datetime,timedelta,timezone
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import earnings_live_capacity as live
import earnings_capacity_assembly as assembly
import earnings_capacity_runtime as owner
import earnings_round_plan as rounds
import earnings_native_namespace as namespace
from earnings_capacity_checks import MechanicalProbes
from earnings_effect_review import review as effect_review,SCOPES
from earnings_research_state import ResearchState
from earnings_capacity_adapter import profile
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


def prepare(number):
    e=live.e
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=e.REPO,check=True,capture_output=True,text=True).stdout.strip()
    if subprocess.run(['git','status','--porcelain'],cwd=e.REPO,check=True,capture_output=True).stdout:
        raise ValueError('Commit every source/config change before prospective preparation')
    ident=f'edgar-real-rh-20261014-{number:02d}'
    root=live.ROOT/ident
    home=live.ROOT.parent/'inputs'/ident
    paths=namespace.native_paths(root,ident)
    if home.exists() or root.exists() or any(path.exists() for path in paths.values()):
        raise ValueError('Existing/failed preparation and consumed run IDs stay closed')
    def save(name,value): return engine.save(home/name,value)
    old=live.read(live.original.pin(live.original.CANARIES.parent/'config-prospective-02.json'))
    ledger=Path(old['ledger'])
    with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        if (db.execute('SELECT * FROM config').fetchall()!=[(1,200_000_000_000,100_000_000_000,0)]
                or db.execute("SELECT 1 FROM requests WHERE status NOT IN ('settled','settled_upper_bound')").fetchone()):
            raise ValueError('Existing idle accounting required before preparing fresh bound')
        baseline=live.history_snapshot(db)
    now=datetime.now(timezone.utc).replace(microsecond=0)
    fmt=lambda value:value.strftime('%Y-%m-%dT%H:%M:%SZ')
    cutoff,deadline=fmt(now+timedelta(minutes=90)),fmt(now+timedelta(minutes=91))
    grant={'schema':'earnings_real_rh_grant_v1','id':ident,'root':str(root),'source_commit':commit,
        'sources':{name:e.digest((e.REPO/name).read_bytes()) for name in live.sources()},
        'python':live.original.pin(Path(sys.executable).absolute()),'data':old['pilot_plan'],
        'runtime':old['runtime'],'scorer':old['scorer'],'qa':old['qa'],'cik':old['cik'],
        'ledger':old['ledger'],'baseline':baseline,'cutoff_utc':cutoff,'deadline_utc':deadline,
        'additional_cap_nano_usd':10_000_000_000,'human_authorization':live.AUTHORIZATION,
        'allowed_egress':live.EGRESS,'bootstrap_no_model_call':True}
    company,runtime=live.task(grant)
    home.mkdir(parents=True,exist_ok=False)
    source=paths['source_root'];source.mkdir(parents=True,exist_ok=False)
    copies={'predictor.py':e.REPO/'tools/edgar_forecast_openai.py',
        'researcher_v0.py':e.REPO/'configs/earnings_coevolution/researcher_v0.py',
        'harness_v0.py':e.REPO/'configs/earnings_coevolution/harness_v0.py',
        'evaluation_scorer.py':Path(grant['scorer']['path']),'evaluation_qa.json':Path(grant['qa']['path'])}
    for name,path in copies.items():
        shutil.copyfile(path,source/name)
        (source/name).chmod(0o600)
        if e.digest((source/name).read_bytes())!=e.digest(path.read_bytes()): raise ValueError('Protected copy differs')
    if (profile((source/'researcher_v0.py').read_bytes(),'R')!={'axis':'R','research_instructions':'','reuse_facts':True}
            or profile((source/'harness_v0.py').read_bytes(),'H')!={'axis':'H','read_chunk_limit':20000,'search_hit_limit':50}):
        raise ValueError('Original R0/H0 required')
    initial=ResearchState(company,ident).save(home/'initial-state',ResearchState(company,ident).empty())
    snapshot=save('original-runtime-snapshot.json',{'schema':'original_runtime_snapshot_v1','source':grant['runtime'],'config':runtime})
    kernel={'scorer':grant['scorer'],'qa':grant['qa']}
    case={key:company[key] for key in ('cik','cutoff','target_accession','visible_root')}
    import json
    case.update(evaluation_kernel=kernel,allowed_manifest_sha256=e.digest(json.dumps(company['allowed_files'],sort_keys=True,separators=(',',':')).encode()))
    model={'requested_model':'gpt-6.1-sol','serving_snapshot':'unknown','serving_snapshot_verified':False}
    study=save('study.json',{'schema':'earnings_coevolution_study_v1','data':grant['data'],
        'scorer':grant['scorer'],'runtime_config':runtime,'python':grant['python'],'sole_ledger':grant['ledger'],
        'cases':[case],'model':model,'prior_batch':snapshot,'new_live_grant':save('grant.json',grant),
        'new_episode_deadline':deadline,'exposure':'EXPOSED_DISCOVERY_NOT_UNTOUCHED'})
    slots=[{role:str(root/'roles'/f'{role}-{index:02d}') for role in ('controller','author','review','forecast')} for index in range(1,4)]
    envelope={'schema':live.SCHEMA,'mode':'real_provider','id':ident,'root':str(root),
        'source_commit':commit,'sources':grant['sources'],'study':study,'cik':company['cik'],'max_rounds':3,
        'role_limits':{role:live.policy.LIMITS for role in ('controller','author','review')},'slots':slots,
        'initial_state':initial,'grant':study and live.read(study)['new_live_grant'],
        'window':{key:grant[key] for key in ('cutoff_utc','deadline_utc')},'evaluation_kernel':kernel}
    episode=save('episode.json',envelope)
    plan={'schema':'earnings_matched_plan_v1','episode':episode,'rounds':[
        {'parent':str(root/'roles'/f'parent-{index:02d}'),'candidate':str(root/'roles'/f'candidate-{index:02d}'),
         'downstream':row['forecast']} for index,row in enumerate(slots,1)]}
    matched=save('matched-plan.json',plan)
    limits={role:live.policy.LIMITS for role in ('controller','author','review')}
    limits['forecast']={'max_input_tokens':runtime['max_input_tokens'],
        'max_output_tokens':max(runtime['max_output_tokens'],runtime.get('final_max_output_tokens',0)),
        'wall_seconds':runtime['company_wall_seconds']}
    resources={'schema':'earnings_capacity_runtime_v3','purpose':'capacity_episode','id':ident,'root':str(root),
        'source_commit':commit,'ledger':grant['ledger'],'baseline':baseline,'cutoff_utc':cutoff,'deadline_utc':deadline,
        'additional_cap_nano_usd':grant['additional_cap_nano_usd'],'rates':runtime['models']['gpt-6.1-sol'],
        'limits':limits,'slots':rounds.declared_slots(envelope,plan),'forecast_study':study,'episode':episode,'matched_plan':matched,
        'sources':{**{name:engine.pin(path) for name,path in owner.CORE.items()},'forecast_entry':engine.pin(e.__file__),
            'forecaster':engine.pin(e.REPO/'tools/edgar_forecast_openai.py'),'round_plan':engine.pin(rounds.__file__),
            **{'factory_'+role:engine.pin(assembly.__file__) for role in ('controller','author','review','forecast')}}}
    resource=save('runtime.json',resources)
    component=lambda names,config:{'sources':{name:e.digest((source/name).read_bytes()) for name in names},'configuration_sha256':digest(config)}
    manifest=engine.identity.manifest(kernel=component(['evaluation_scorer.py','evaluation_qa.json'],kernel),
        predictor=component(['predictor.py'],{'output':'original_five_numeric_predictions'}),
        harness=component(['harness_v0.py'],{'profile':'H0'}),researcher=component(['researcher_v0.py'],{'profile':'R0'}),
        model=model,memory=initial['sha256'],runtime={'python':grant['python'],'dependencies':{}})
    source_review={'schema':'earnings_source_review_setup_v1','source_root':str(source),
        'proposer_id':'actual-model-author-'+ident,'reviewer_id':'trusted-host-effect-review-'+ident,
        'slots':{row['review']:{'candidate_id':f'{ident}-child-{index:02d}',
            'R':f'researcher_child_{index:02d}.py','H':f'harness_child_{index:02d}.py'} for index,row in enumerate(slots,1)}}
    native={'schema':'earnings_native_setup_v1',**{key:str(paths[key]) for key in ('source_root','registry_root','batch_root')},
        'baseline':manifest,'entrypoints':{'R':'researcher_v0.py','H':'harness_v0.py'},
        'batch_config':{'batch_id':ident,'start_utc':fmt(now),'deadline_utc':deadline,'max_attempts':9,
            'initial_incumbent':{'candidate_id':'fixed-original-forecast','candidate_sha256':manifest['C'],
                'scorecard_sha256':'0'*64,'review_sha256':'0'*64},'active_pool_capacity':2,'learning_checkpoint_version':1},
        'micro_config':{'pair':engine.activation.pair(manifest),'fixed_context':{
            'model_sha256':manifest['M'],'evaluation_sha256':manifest['K'],
            'data_scope_sha256':digest({'study':study,'cik':company['cik'],'kernel':kernel}),
            'authority_sha256':digest({key:envelope[key] for key in ('mode','grant','window')}),'resource_policy_sha256':digest(resource)},
            'allowed_write_paths':{kind:[f'{prefix}_v0.py',*[row[axis] for row in source_review['slots'].values()]]
                for axis,kind,prefix in [('R','researcher','researcher'),('H','harness','harness')]},
            'protected_paths':['predictor.py','evaluation_scorer.py','evaluation_qa.json'],
            'reviewer_id':source_review['reviewer_id']}}
    registration={'schema':'earnings_effect_review_registration_v1','reviewer_id':source_review['reviewer_id'],
        'proposer_id':source_review['proposer_id'],'review_source':engine.source_of(effect_review),
        'probe_source':engine.source_of(MechanicalProbes.run),'scopes':SCOPES}
    transport=save('transport-policy.json',{'schema':'edgar_foreground_slow_call_policy_v1','source_commit':commit,
        'original_runtime_request_timeout_seconds':runtime['request_timeout_seconds'],'effective_socket_timeout_seconds':600,
        'role_and_global_deadlines_unchanged':True,'retry_allowed':False})
    assembled=save('assembly.json',{'schema':'earnings_capacity_assembly_v2','mode':'real_provider','episode':episode,
        'runtime':resource,'native':save('native.json',native),'matched_plan':matched,
        'effect_registration':save('effect-registration.json',registration),'source_review':save('source-review.json',source_review),
        'constructors':assembly.constructor_sources(),'transport':engine.source_of(live.provider_client),
        'transport_policy':transport,'claims':{'model_authorship':False,'predictive_gain':False}})
    assembly.validate_assembly(episode,assembled,client_factory=live.provider_client)
    return save('prepared.json',{'schema':'earnings_real_rh_prepared_v1','episode':episode,'assembly':assembled,
        'source_commit':commit,'provider_calls':0,'claim_boundary':'Prepared only; no owner or batch initialized'})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--number',type=int,required=True,choices=range(1,100))
    import json
    print(json.dumps(prepare(parser.parse_args().number)))
