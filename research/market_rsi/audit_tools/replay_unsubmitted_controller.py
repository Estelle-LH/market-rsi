"""Replay saved bytes through the terminal guard: ZERO live provider/budget calls."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from codex_glm_provider import ControllerSession
from codex_glm_responses_adapter import AdapterProtocolError
from historical_grid_learning_controller import ALLOWED_TOOLS
from historical_learning_recovery import inspection_failure_evidence
from market_rsi import canonical,digest,file_hash,fresh_json,load_json


class ReplayBudget:
    def __init__(self):self.events=[]
    def reserve(self,*args):self.events.append(('reserve',args))
    def dispatch(self,*args):self.events.append(('dispatch',args))
    def settle_metered(self,*args):self.events.append(('settle_metered',args))


class ReplayBackend:
    def __init__(self,request,response):self.request=request;self.response=response;self.calls=0
    def encode(self,turn):
        if turn['messages']!=self.request['glm_messages'] or turn['tools']!=self.request['glm_tools']:
            raise ValueError('actual recorded request conversion changed')
        return self.request
    def sample(self,tokens,max_output_tokens,timeout_seconds):
        if tokens!=self.request['token_ids'] or max_output_tokens!=self.request['max_output_tokens']:
            raise ValueError('replay admission differs from original request')
        self.calls+=1;r=self.response;receipt=r['receipt']
        return {'text':r['text'],'output_tokens':r['tokens'],
            'cached_input_tokens':receipt['cache_hit_prompt_tokens'],
            'finish_reason':receipt['finish_reason'],'provider':{'mode':'LOCAL_SAVED_BYTES_NOT_PROVIDER'}}


def run(session,parent,output):
    evidence=inspection_failure_evidence(session,parent)
    if output.exists():raise ValueError('fresh unpaid replay output required')
    output.mkdir(parents=True,exist_ok=False)
    turn=sorted((session/'session').glob('turn-*'))[-1]
    r=load_json(turn/'request.json');response=load_json(turn/'response.json')
    backend=ReplayBackend(r,response);budget=ReplayBudget()
    s=ControllerSession(session_id=output.name,output=output/'local-replay',
        backend=backend,budget=budget,budget_bucket='LOCAL_REPLAY_ONLY',
        submit_tool='submit_grid_learning_decision',allowed_tools=ALLOWED_TOOLS)
    req=r['responses_request'];s.turns=len(list((session/'session').glob('turn-*')))-1
    previous=load_json(turn.parent/f'turn-{s.turns:03d}'/'assessment.json') if s.turns else {}
    s.tokens.input_tokens=previous.get('cumulative_input_tokens',0)
    s.tokens.output_tokens=previous.get('cumulative_output_tokens',0)
    for item in req['input']:
        if item.get('type')=='function_call':
            name=item['name']
            if item.get('namespace') is not None:name=f"{item['namespace']}__{name}"
            s.emitted_calls.append({'call_id':item['call_id'],'name':name,'arguments':item['arguments']})
    s.tool_calls=len(s.emitted_calls)
    try:s.handle(req)
    except AdapterProtocolError as e:
        if 'unsubmitted narrative' not in str(e):raise
    else:raise ValueError('unsubmitted narrative incorrectly accepted')
    failure=load_json(output/'local-replay/request-failure.json')
    if backend.calls!=1 or not s.failed or failure['stage']!='terminal_submission_protocol':
        raise ValueError('terminal guard did not fail exactly once')
    result={'passed':True,'schema':'historical_unsubmitted_controller_replay_v1',
        'evidence':evidence,'original_request_sha256':file_hash(turn/'request.json'),
        'original_response_sha256':file_hash(turn/'response.json'),
        'new_provider_calls':0,'actual_budget_writes':0,'new_fits':0,
        'synthetic_budget_events':[n for n,_ in budget.events],
        'original_narrative_replayed_once':True,'automatic_resampling':0,
        'original_artifacts_changed':False,'terminal_submission_not_fabricated':True,
        'local_failure_stage':failure['stage'],'provider_source_sha256':file_hash(Path(__file__).parents[1]/'codex_glm_provider.py')}
    result['result_sha256']=digest(result);fresh_json(output/'audit.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('session','parent','output'):p.add_argument('--'+n,type=Path,required=True)
    r=run(**vars(p.parse_args()))
    print(canonical({k:r[k] for k in ['passed','result_sha256','new_provider_calls','actual_budget_writes','new_fits']}))
