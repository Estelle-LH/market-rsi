"""Prepare a hash-bound answer to GLM's public-metadata request, not a source decision."""
import argparse
from datetime import date,timedelta
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from market_rsi import canonical,digest,file_hash,fresh_json,load_json
from pinned_source_document import verify_document
from public_recursive_metadata import parse_inventory


def checked(path):
    v=load_json(path)
    if v.get('passed') is not True or v.get('result_sha256')!=digest({k:x for k,x in v.items() if k!='result_sha256'}):
        raise ValueError('unchanged completed evidence required')
    return v


def inventory_summary(objects,start='2026-05-16',end='2026-06-30'):
    first,last=date.fromisoformat(start),date.fromisoformat(end)
    expected={(first+timedelta(days=i)).isoformat() for i in range((last-first).days+1)}
    out={}
    for family in ('orderbook','orderbook_1min'):
        files=[o for o in objects if o['type']=='file' and o['path'].startswith(family+'/')]
        dates={}
        for obj in files:
            match=re.fullmatch(family+r'/date=(\d{4}-\d{2}-\d{2})/data_0\.parquet',obj['path'])
            if not match or match[1] in dates:raise ValueError('unexpected or duplicate date partition path')
            date.fromisoformat(match[1]);dates[match[1]]=obj
        requested=sorted(expected & set(dates))
        out[family]={'advertised_files':len(files),'advertised_bytes':sum(o['advertised_bytes'] for o in files),
            'file_date_range':[min(dates),max(dates)] if dates else None,
            'requested_calendar':[start,end],'requested_window_files':len(requested),
            'requested_window_advertised_bytes':sum(dates[d]['advertised_bytes'] for d in requested),
            'absent_filename_partitions_in_requested_window':sorted(expected-set(dates)),
            'minimum_file_bytes':min((o['advertised_bytes'] for o in files),default=None),
            'maximum_file_bytes':max((o['advertised_bytes'] for o in files),default=None),
            'event_dates_or_complete_sessions_verified':False,'subset_selected':False}
    return out


def assemble(output):
    if output.exists():raise ValueError('fresh followup evidence ID required')
    art=ROOT/'artifacts';old=art/'historical-source-review-controller-20260910-01'
    audit_path=art/'historical-source-review-result-audit-20260910-01/audit.json';audit=checked(audit_path)
    prep_path=old/'preparation.json';prep=load_json(prep_path)
    for name,sha in prep['source_hashes'].items():
        if file_hash(ROOT/name)!=sha or file_hash(old/'source-snapshot'/name)!=sha:raise ValueError('old source changed')
    decision_path=old/'workspace/submitted-source-review-decision.json';decision=load_json(decision_path)
    if decision['action']!='request_metadata' or file_hash(decision_path)!=audit['decision_sha256']:
        raise ValueError('exact audited metadata request required')
    req_path=old/'workspace/metadata-requests'/decision['artifact_id']/'result.json';request=load_json(req_path)
    if digest(request)!=decision['artifact_sha256']:raise ValueError('requested artifact changed')
    paths=[audit_path,prep_path,decision_path,req_path];docs=[]
    for folder in ('historical-canary-schema-document-20260910-01',
                   'historical-canary-dictionary-document-20260910-01','historical-joseph-readme-document-20260910-01'):
        p=art/folder/'result.json';receipt=checked(p);document=p.parent/'document.txt'
        if file_hash(document)!=receipt['document_sha256']:raise ValueError('pinned document bytes changed')
        body=document.read_bytes()
        verify_document(body,{'advertised_bytes':receipt['http']['http_document_bytes'],
            'git_oid':receipt['git_blob_oid'],'advertised_sha256':receipt['document_sha256']})
        docs.append({'receipt':receipt,'text':body.decode('utf-8')});paths += [p,document]
    p=art/'historical-joseph-recursive-metadata-20260910-01/result.json';inventory=checked(p)
    raw=p.parent/'response.body.json'
    if file_hash(raw)!=inventory['response_body_sha256']:raise ValueError('inventory bytes changed')
    actual=parse_inventory(raw.read_bytes(),inventory['http'])
    if any(inventory[k]!=v for k,v in actual.items()):raise ValueError('inventory parse mismatch')
    revision_path=art/'historical-joseph-revision-metadata-20260910-01/result.json';revision=checked(revision_path)
    revision_body=revision_path.parent/'response.body.json'
    if (file_hash(revision_body)!=revision['body_sha256'] or revision['observed_revision']!=inventory['revision']):
        raise ValueError('independent source revision mismatch')
    advertised={x['rfilename'] for x in load_json(revision_body)['siblings']}
    listed={x['path'] for x in inventory['objects'] if x['type']=='file'}
    if advertised!=listed or not actual['inventory_complete_by_http_pagination']:
        raise ValueError('complete directory and independent sibling metadata disagree')
    paths += [p,raw,revision_path,revision_body]
    result={'schema':'controller_source_metadata_followup_v1','passed':True,
        'prior_session_id':old.name,'request_id':decision['artifact_id'],'request_body':request['body'],
        'prior_decision_sha256':file_hash(decision_path),'old_source_files_preserved':len(prep['source_hashes']),
        'pinned_documentation':docs,'joseph_inventory':inventory,
        'filename_only_summary':inventory_summary(inventory['objects']),
        'independent_sibling_listing_matches':True,
        'interface_failure_correction':{'known_source_was_not_missing':True,
            'invalid_source_id_was_dataset_plus_revision':True,'object_keys_and_list_types_also_wrong':True,
            'full_nested_schema_required_next_stage':True,'failed_plan_not_promoted_to_selection':True},
        'unanswered_without_raw_qa':['actual event/time coverage per day','as-of UP/DOWN semantic equivalence',
            'observed co-reported BBO and payload completeness','cross-stream same-time ordering',
            'quiet periods versus unrecorded outages'],
        'sample_files_opened':False,'new_raw_download_bytes':0,'provider_calls':0,
        'source_selected':False,'acquisition_admitted':False,'fresh_test_admitted':False,
        'documentation_is_not_training_rows_or_complete_session_proof':True,
        'inputs':{str(p):file_hash(p) for p in paths},'assembler_sha256':file_hash(Path(__file__))}
    result['result_sha256']=digest(result);output.mkdir(parents=True,exist_ok=False)
    fresh_json(output/'followup.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    r=assemble(p.parse_args().output.resolve())
    print(canonical({k:v for k,v in r.items() if k not in
        ('pinned_documentation','joseph_inventory','request_body','inputs')}))
