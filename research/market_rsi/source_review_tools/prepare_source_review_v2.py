"""Freeze NEW v2 metadata before calling the improved source-review interface."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'audit_tools')]
import controller_source_review as core
import controller_source_review_v2 as review
from controller_activity_log import read_activity_events,verify_activity_log
from market_rsi import canonical,digest,file_hash,fresh_json,load_json
from paid_budget import PaidBudget


def prepare(output,purpose):
    if output.exists():raise ValueError('fresh v2 preparation ID required')
    old=ROOT/'artifacts/historical-source-review-controller-20260910-01'
    prep=load_json(old/'preparation.json');decision=load_json(old/'workspace'/core.DECISION)
    if not (old/'dispatch-claim.json').is_file() or load_json(old/'session/assessment.json')['valid'] is not True:
        raise ValueError('completed prior source review required')
    for name,sha in prep['source_hashes'].items():
        if file_hash(ROOT/name)!=sha or file_hash(old/'source-snapshot'/name)!=sha:raise ValueError('frozen old source changed')
    for path,sha in prep['inputs'].items():
        if file_hash(Path(path))!=sha:raise ValueError('old frozen input changed')
    _,visible=core.validate_workspace(old/'workspace',prep['workspace_sha256'])
    followup_path=ROOT/'artifacts/historical-source-metadata-followup-20260910-01/followup.json'
    followup=review.validate_followup(load_json(followup_path))
    for path,sha in followup['inputs'].items():
        if file_hash(Path(path))!=sha:raise ValueError('requested evidence changed')
    if (followup['prior_decision_sha256']!=file_hash(old/'workspace'/core.DECISION)
            or followup['request_id']!=decision['artifact_id']):raise ValueError('followup not bound to prior decision')
    budget_path=ROOT/'artifacts/kalshi-research-glm53-20260907-01/budget'
    b=PaidBudget(budget_path).snapshot();context=visible['context.json']
    if (b['experiment_id']!=context['experiment_id'] or b['cap_usd']!=context['budget_cap_usd']
            or file_hash(budget_path/'authorization.json')!=context['budget_authorization_sha256']):
        raise ValueError('original budget changed')
    if any(v['state']=='dispatched' and '-turn-' in k for k,v in b['jobs'].items()):
        raise ValueError('another or unresolved model turn exists')
    visible=copy.deepcopy(visible)
    visible['evidence.json']['source_metadata_followup']=followup
    visible['readiness.json'].update({'source_review_interface_version':2,
        'budget_snapshot_not_spend':{k:v for k,v in b.items() if k!='jobs'},
        'full_nested_schema_and_pinned_documentation_available':True,
        'v2_full_codex_canary_required_before_paid_dispatch':True})
    visible['archive.json']['prior_source_review']={'decision':decision,
        'failed_plan_claims':[load_json(p) for p in sorted((old/'workspace/plans').glob('*/claim.json'))],
        'request_followup_sha256':file_hash(followup_path),
        'interface_failure_correction':followup['interface_failure_correction']}
    inv=followup['joseph_inventory']
    for s in visible['source-review-catalog.json']['sources']:
        if s['id']==inv['dataset']:
            s['observed_revision']=inv['revision'];s['recursive_metadata_result_sha256']=inv['result_sha256']
            s['actual_event_coverage_verified']=False
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    sources=list(ROOT.glob('*.py'))
    for folder in ('validation_tools','source_review_tools'):
        sources += [p for p in (ROOT/folder).glob('*.py') if not p.name.startswith('test_')]
    sources += [ROOT/'audit_tools/public_source_metadata.py']
    hashes={}
    for source in sorted(sources):
        name=str(source.relative_to(ROOT));hashes[name]=file_hash(source)
        dest=output/'source-snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
        if file_hash(dest)!=hashes[name]:raise ValueError('snapshot copy changed')
    sha=core.make_workspace(output/'workspace',visible,output.name,purpose)
    review.validate_workspace(output/'workspace',sha)
    paths=[old/'preparation.json',old/'dispatch-claim.json',old/'session/assessment.json',
           old/'workspace'/core.DECISION,followup_path,budget_path/'authorization.json']
    inputs={**prep['inputs'],**followup['inputs'],**{str(p):file_hash(p) for p in paths}}
    result={'schema':'historical_source_review_v2_preparation_v1','purpose':purpose,
        'source_review_interface_version':2,'old_source_files_preserved':len(prep['source_hashes']),
        'source_hashes':hashes,'workspace_sha256':sha,'context_sha256':context['context_sha256'],
        'followup_sha256':file_hash(followup_path),'inputs':inputs,'new_model_calls':0,
        'new_raw_download_bytes':0,'execution_admitted':False,'paid_dispatch_ready':False}
    for name,expected in hashes.items():
        if file_hash(ROOT/name)!=expected:raise ValueError('source changed during preparation')
    fresh_json(output/'preparation.json',result);return result


def canary(prepared):
    prep=load_json(prepared/'preparation.json');ws=prepared/'workspace'
    if prep['purpose']!='transport_canary' or (prepared/'transport-canary-claim.json').exists():
        raise ValueError('fresh v2 canary required')
    for name,sha in prep['source_hashes'].items():
        if file_hash(ROOT/name)!=sha or file_hash(prepared/'source-snapshot'/name)!=sha:
            raise ValueError('canary source changed')
    review.validate_workspace(ws,prep['workspace_sha256'])
    fresh_json(prepared/'transport-canary-claim.json',{'preparation_sha256':file_hash(prepared/'preparation.json'),
        'scope':'real v2 STDIO, existing metadata only, no model/source decision/network'})
    requests=[{'jsonrpc':'2.0','id':1,'method':'initialize'},{'jsonrpc':'2.0','id':2,'method':'tools/list'}]
    calls=[('inspect_source_context',{}),('inspect_source_readiness',{}),('inspect_source_archive',{}),
           ('search_source_notes',{'query':'DATA_DICTIONARY.md'}),
           ('search_source_notes',{'query':'2026-05-16'})]
    for i,(name,args) in enumerate(calls,3):requests.append({'jsonrpc':'2.0','id':i,'method':'tools/call',
        'params':{'name':name,'arguments':args}})
    try:
        p=subprocess.run([sys.executable,str(prepared/'source-snapshot/source_review_tools/controller_source_review_v2.py'),
            '--workspace',str(ws),'--manifest-sha256',prep['workspace_sha256']],
            input=''.join(canonical(r)+'\n' for r in requests),capture_output=True,text=True,timeout=30)
        if p.returncode:raise ValueError('v2 STDIO failed: '+p.stderr[-1500:])
        replies=[json.loads(x) for x in p.stdout.splitlines()]
        if (len(replies)!=7 or replies[1]['result']['tools']!=review.TOOLS
                or any(r.get('error') or r['result'].get('isError') for r in replies)):
            raise ValueError('v2 tool schema/call failed')
        doc=json.loads(replies[5]['result']['content'][0]['text'])
        files=json.loads(replies[6]['result']['content'][0]['text'])
        if not doc['documents'] or not files['metadata_file_matches']:raise ValueError('pinned evidence not served')
        if (ws/core.DECISION).exists() or any(list((ws/k).iterdir()) for k in ('plans','metadata-requests','public-metadata')):
            raise ValueError('read-only canary unexpectedly acted')
        if len(read_activity_events(ws/core.LOG))!=5:raise ValueError('unexpected canary tools')
        review.validate_workspace(ws,prep['workspace_sha256'])
        result={'schema':'historical_source_review_v2_stdio_canary_v1','passed':True,
            'actual_stdio_child':True,'transport_calls':7,'actual_tools':5,'full_plan_schema_served':True,
            'pinned_document_and_file_metadata_served':True,'source_files_verified':len(prep['source_hashes']),
            'preparation_sha256':file_hash(prepared/'preparation.json'),'followup_sha256':prep['followup_sha256'],
            'context_sha256':prep['context_sha256'],'activity':verify_activity_log(ws/core.LOG),
            'new_model_calls':0,'new_public_metadata_calls':0,'new_raw_download_bytes':0,
            'model_authorship_proven':False,'paid_dispatch_ready':False}
        result['result_sha256']=digest(result);fresh_json(prepared/'transport-canary.json',result);return result
    except Exception as e:
        fresh_json(prepared/'transport-canary-failure.json',{'error_type':type(e).__name__,
            'message_sha256':digest(str(e)),'automatic_retry':False});raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='operation',required=True)
    a=sub.add_parser('prepare');a.add_argument('--output',type=Path,required=True)
    a.add_argument('--purpose',choices=['source_review','transport_canary'],required=True)
    c=sub.add_parser('canary');c.add_argument('--prepared',type=Path,required=True)
    a=p.parse_args();r=prepare(a.output.resolve(),a.purpose) if a.operation=='prepare' else canary(a.prepared.resolve())
    print(canonical({k:v for k,v in r.items() if k not in ('source_hashes','inputs')}))
