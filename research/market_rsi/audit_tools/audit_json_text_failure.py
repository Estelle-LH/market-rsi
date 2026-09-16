"""Reparse immutable tool outputs for a transport diagnosis; never execute them."""
import argparse
from pathlib import Path
from codex_glm_responses_adapter import parse_glm_completion
from data_scientist_harness.broker import ALLOWED_TOOLS, validate_shape
from market_rsi import load_json, file_hash, digest, fresh_json


def audit(root):
    root = Path(root).resolve()
    evidence=[]
    for turn in (7, 8, 9):
        parent=root/'session'/f'turn-{turn:03d}'
        request=load_json(parent/'request.json')
        schemas={t['function']['name']:t['function']['parameters'] for t in request['glm_tools']}
        raw=load_json(parent/'response.json')['text']
        parsed=parse_glm_completion(raw,ALLOWED_TOOLS,tool_schemas=schemas)
        calls=parsed['calls'] if parsed['kind']=='function_calls' else [parsed]
        found=[c for c in calls if c['name']=='mcp__controller_tools__request_capability']
        if len(found)!=1:raise ValueError('exact failed capability call required')
        call=found[0];validate_shape(call['arguments'],schemas[call['name']])
        record=root/'records'/f'{turn+2:04d}.json'
        before=load_json(record)
        if not (before['status']=='error' and before['result']['error']=='arguments.verification_needed: expected string'
                and isinstance(before['arguments']['verification_needed'],dict)):
            raise ValueError('not the diagnosed historical failure')
        text=call['arguments']['verification_needed']
        import json
        if json.loads(text)!=before['arguments']['verification_needed']:
            raise ValueError('historical parsed object differs from emitted JSON text')
        evidence.append({'turn':turn,'request_sha256':file_hash(parent/'request.json'),
            'response_sha256':file_hash(parent/'response.json'),'original_error_record_sha256':file_hash(record),
            'original_type':'object','schema_required_type':'string','reparsed_type':'string',
            'new_shape_passed':True,'original_text_semantics_preserved':True,'action_reexecuted':False})
    value={'schema':'json_text_transport_audit_v1','workspace':str(root),
        'manifest_sha256':file_hash(root/'workspace.json'),'evidence':evidence,
        'adapter_sha256':file_hash(Path(__file__).resolve().parents[1]/'codex_glm_responses_adapter.py'),
        'raw_responses_mutated':False,'action_reexecuted':False,'controller_retry':False,
        'source_admitted':False,'fits':0,'provider_calls':0,
        'limitation':'Schema-correct reparsing is not scientific approval or a completed historical controller session.'}
    value['result_sha256']=digest(value)
    return value


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=audit(a.workspace);a.output.parent.mkdir(parents=True,exist_ok=True)
    fresh_json(a.output,result);print(result)
