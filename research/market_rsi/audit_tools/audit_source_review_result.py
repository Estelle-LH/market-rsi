"""Independent receipt/accounting audit of a completed source-review decision.

No market rows, public requests, model calls, downloads, fitting or evaluation.
"""
import argparse
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'source_review_tools'), str(ROOT/'validation_tools')]
import controller_source_review as review
from audit_validation_design_result import require, verify_turn
from codex_glm_responses_adapter import parse_glm_completion
from controller_activity_log import read_activity_events
from market_rsi import canonical, digest, file_hash, fresh_json, load_json
from paid_budget import PaidBudget


def response_calls(text):
    parsed = parse_glm_completion(text, review.ALLOWED_TOOLS)
    if parsed['kind'] == 'function_call':
        return [{'name': parsed['name'], 'arguments': parsed['arguments']}]
    require(parsed['kind'] == 'function_calls', 'submitted tool calls required')
    return parsed['calls']


def match_calls(calls, events, expected_count):
    model = Counter(canonical({'name':c['name'].removeprefix('mcp__controller_tools__'),
                              'arguments':c['arguments']}) for c in calls)
    actual = Counter(canonical({'name':e['tool'],'arguments':e['arguments']}) for e in events)
    require(model == actual and len(calls) == expected_count, 'model-to-tool transcript mismatch')


def run(session, output, budget):
    require(not output.exists(), 'fresh audit ID required')
    a=load_json(session/'session/assessment.json')
    require(a['valid'] is True and a['process_reaped'] is True and a['failed'] is False
        and a['evidence_mode']=='paid_controller' and a['model_authorship_proven'] is True,
        'completed real source-review controller required')
    prep=load_json(session/'preparation.json'); claim=load_json(session/'dispatch-claim.json')
    require(prep['purpose']=='source_review' and claim['controller_stage']=='source_review',
            'fixture or other stage cannot be research')
    require(claim['preparation_sha256']==file_hash(session/'preparation.json'),'preparation binding')
    for name,sha in prep['source_hashes'].items():
        require(file_hash(session/'source-snapshot'/name)==sha==file_hash(ROOT/name),'frozen source changed')
    for path,sha in prep['inputs'].items():require(file_hash(Path(path))==sha,'input evidence changed')
    ws=session/'workspace'; _,visible=review.validate_workspace(ws,prep['workspace_sha256'])
    activity=review.assess_activity(ws,prep['workspace_sha256'])
    state=PaidBudget(budget).snapshot()
    require(file_hash(budget/'authorization.json')==claim['budget_authorization_sha256'],'budget authority')
    jobs={k:v for k,v in state['jobs'].items() if k.startswith(session.name+'-turn-')}
    turns=sorted((session/'session').glob('turn-*'))
    require(len(turns)==len(jobs)==a['turns'],'exact terminal turn count')
    calls=[]; charges=[]; inputs={}; tokens={'prompt':0,'cached_prompt':0,'output':0}
    for i,directory in enumerate(turns,1):
        turn_id=session.name+f'-turn-{i:03d}'
        request=load_json(directory/'request.json'); response=load_json(directory/'response.json')
        require(request['turn_id']==turn_id,'turn sequence')
        charges.append(verify_turn(request,response,jobs[turn_id]))
        receipt=response['receipt']
        tokens['prompt']+=receipt['prompt_tokens']; tokens['output']+=receipt['output_tokens']
        tokens['cached_prompt']+=receipt['cache_hit_prompt_tokens']
        calls.extend(response_calls(response['text']))
        for name in ('request.json','response.json','assessment.json'):
            inputs[str(directory/name)]=file_hash(directory/name)
    events=read_activity_events(ws/review.LOG);match_calls(calls,events,a['tool_calls'])
    handshake=load_json(session/'session/terminal-handshake.json')
    require(handshake['provider_called'] is False and handshake['paid_turn_added'] is False,
            'terminal acknowledgment added provider charge')
    decision=load_json(ws/review.DECISION); proposal=None
    receipts=review.Broker(ws,prep['workspace_sha256'])._receipts(visible,events)
    if decision['action']=='propose':
        p=ws/'plans'/decision['artifact_id']/'result.json'; proposal=load_json(p)
        verified=review.validate_plan(proposal['body'],visible,receipts)
        require(all(proposal[k]==v for k,v in verified.items()),'proposal result differs from fresh validation')
        inputs[str(p)]=file_hash(p)
    elif decision['action']=='request_metadata':
        p=ws/'metadata-requests'/decision['artifact_id']/'result.json'; proposal=load_json(p)
        review.validate_request(proposal['body']);inputs[str(p)]=file_hash(p)
    result={'schema':'historical_source_review_result_audit_v1','passed':True,'session_id':session.name,
        'assessment_sha256':file_hash(session/'session/assessment.json'),
        'decision_sha256':file_hash(ws/review.DECISION),'source_files_verified':len(prep['source_hashes']),
        'activity':activity,'decision':decision,'proposal':proposal,'turns':len(turns),'tool_calls':len(calls),
        'session_metered_usd':str(sum(charges)),'tokens':tokens,
        'budget_snapshot':{k:v for k,v in state.items() if k!='jobs'},
        'public_metadata_calls':sum(e['tool']=='inspect_public_source_directory' for e in events),
        'public_metadata_successes':sum(e['tool']=='inspect_public_source_directory' and e['status']=='ok' for e in events),
        'claim_boundaries':['Publisher metadata and controller prose do not prove raw compatibility or complete dates.',
            'Any source or feature substitution is a new declared data stage, not an untouched t7 validation.',
            'Advertised object payload is not total wire transfer or download authority.',
            'Original raw-download allowance has no remaining headroom; no new acquisition admitted.'],
        'inputs':inputs,'new_provider_calls':0,'new_raw_data_read':False,'new_fits':0,'new_downloads':0,
        'fresh_validation_result':False,'auditor_sha256':file_hash(Path(__file__)),
        'accounting_verifier_sha256':file_hash(Path(__file__).with_name('audit_validation_design_result.py'))}
    result['result_sha256']=digest(result);output.mkdir(parents=True,exist_ok=False)
    fresh_json(output/'audit.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('session','output','budget'):p.add_argument('--'+name,type=Path,required=True)
    r=run(**{k:v.resolve() for k,v in vars(p.parse_args()).items()})
    print(canonical({k:v for k,v in r.items() if k not in ('inputs','budget_snapshot','proposal','decision')}))
