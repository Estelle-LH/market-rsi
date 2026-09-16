"""Audit v2 model authorship, exact tools, immutable evidence and actual charges."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'source_review_tools'),str(ROOT/'validation_tools')]
import controller_source_review_v2 as review
from audit_validation_design_result import require,verify_turn
from audit_source_review_result import response_calls,match_calls
from controller_activity_log import read_activity_events
from market_rsi import canonical,digest,file_hash,fresh_json,load_json
from paid_budget import PaidBudget


def require_completed(a):
    require(a.get('schema')=='historical_source_review_v2_controller_assessment_v1'
        and a.get('controller_stage')=='source_review_v2' and a.get('valid') is True
        and a.get('process_reaped') is True and a.get('failed') is False
        and a.get('evidence_mode')=='paid_controller' and a.get('model_authorship_proven') is True,
        'completed real v2 controller required')


def run(session,output,budget):
    require(not output.exists(),'fresh audit ID required')
    a=load_json(session/'session/assessment.json');require_completed(a)
    prep=load_json(session/'preparation.json');claim=load_json(session/'dispatch-claim.json')
    require(prep['purpose']=='source_review' and claim['controller_stage']=='source_review_v2','exact paid v2 stage')
    require(claim['preparation_sha256']==file_hash(session/'preparation.json'),'preparation changed')
    for n,h in prep['source_hashes'].items():
        require(file_hash(ROOT/n)==h==file_hash(session/'source-snapshot'/n),'frozen source changed')
    for p,h in prep['inputs'].items():require(file_hash(Path(p))==h,'frozen evidence changed')
    ws=session/'workspace';_,visible=review.validate_workspace(ws,prep['workspace_sha256'])
    activity=review.assess_activity(ws,prep['workspace_sha256']);events=read_activity_events(ws/review.LOG)
    b=PaidBudget(budget).snapshot()
    require(file_hash(budget/'authorization.json')==claim['budget_authorization_sha256'],'budget authority changed')
    jobs={k:v for k,v in b['jobs'].items() if k.startswith(session.name+'-turn-')}
    turns=sorted((session/'session').glob('turn-*'))
    require(len(turns)==len(jobs)==a['turns'],'exact terminal turn count')
    calls=[];charges=[];inputs={};tokens={'prompt':0,'cached_prompt':0,'output':0}
    for i,d in enumerate(turns,1):
        req=load_json(d/'request.json');resp=load_json(d/'response.json');tid=session.name+f'-turn-{i:03d}'
        require(req['turn_id']==tid,'turn sequence');charges.append(verify_turn(req,resp,jobs[tid]))
        rec=resp['receipt'];tokens['prompt']+=rec['prompt_tokens'];tokens['cached_prompt']+=rec['cache_hit_prompt_tokens']
        tokens['output']+=rec['output_tokens'];calls.extend(response_calls(resp['text']))
        for name in ('request.json','response.json','assessment.json'):inputs[str(d/name)]=file_hash(d/name)
    match_calls(calls,events,a['tool_calls'])
    ack=load_json(session/'session/terminal-handshake.json')
    require(ack['provider_called'] is False and ack['paid_turn_added'] is False,'extra terminal paid call')
    decision=load_json(ws/review.DECISION);proposal=None
    if decision['action']=='propose':
        p=ws/'plans'/decision['artifact_id']/'result.json';proposal=load_json(p)
        receipts=review.Broker(ws,prep['workspace_sha256'])._receipts(visible,events)
        v=review.core.validate_plan(proposal['body'],visible,receipts)
        require(all(proposal[k]==x for k,x in v.items()),'proposal revalidation mismatch')
        inputs[str(p)]=file_hash(p)
    elif decision['action']=='request_metadata':
        p=ws/'metadata-requests'/decision['artifact_id']/'result.json';proposal=load_json(p)
        review.core.validate_request(proposal['body']);inputs[str(p)]=file_hash(p)
    r={'schema':'historical_source_review_v2_result_audit_v1','passed':True,'session_id':session.name,
        'assessment_sha256':file_hash(session/'session/assessment.json'),'decision_sha256':file_hash(ws/review.DECISION),
        'source_files_verified':len(prep['source_hashes']),'activity':activity,'decision':decision,'proposal':proposal,
        'turns':len(turns),'tool_calls':len(calls),'session_metered_usd':str(sum(charges)),'tokens':tokens,
        'budget_snapshot':{k:v for k,v in b.items() if k!='jobs'},'inputs':inputs,
        'claim_boundaries':['Metadata proposal is not acquisition permission or verified raw compatibility.',
            'Directory dates do not prove clean sessions; no fresh-test population admitted.',
            'Changing source is a separate data stage, not a result for unchanged t7.'],
        'new_provider_calls':0,'new_raw_data_read':False,'new_downloads':0,'new_fits':0,
        'fresh_validation_result':False,'auditor_sha256':file_hash(Path(__file__)),
        'accounting_verifier_sha256':file_hash(Path(__file__).with_name('audit_validation_design_result.py'))}
    r['result_sha256']=digest(r);output.mkdir(parents=True,exist_ok=False);fresh_json(output/'audit.json',r);return r


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('session','output','budget'):p.add_argument('--'+n,type=Path,required=True)
    r=run(**{k:v.resolve() for k,v in vars(p.parse_args()).items()})
    print(canonical({k:v for k,v in r.items() if k not in ('inputs','budget_snapshot','proposal','decision')}))
