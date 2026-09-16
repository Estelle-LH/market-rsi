"""One bounded recursive metadata page at an independently observed HF revision.

Lists file names/hashes/bytes only. No raw object request, pagination following,
model call, source selection or download authority. A paginated result is partial.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from market_rsi import canonical,digest,file_hash,fresh_json,load_json
from public_source_metadata import bounded_get,metadata_url,parse_listing,unique_object,no_constant,MAX_BYTES


def normalized_path(path):
    if (not isinstance(path,str) or not path or len(path)>500 or '\\' in path or '%' in path
            or any(ord(c)<32 for c in path)):
        raise ValueError('normalized relative path required')
    p=PurePosixPath(path)
    if p.is_absolute() or len(p.parts)>8 or any(s in ('','.','..') for s in path.split('/')):
        raise ValueError('relative canonical path required')
    if str(p)!=path:raise ValueError('canonical path required')
    return path


def parse_inventory(body,headers):
    if not isinstance(body,bytes) or len(body)>MAX_BYTES:raise ValueError('bounded metadata body required')
    records=json.loads(body,object_pairs_hook=unique_object,parse_constant=no_constant)
    if not isinstance(records,list) or len(records)>1000:raise ValueError('bounded metadata list required')
    seen=set();objects=[];families={}
    for item in records:
        if not isinstance(item,dict):raise ValueError('object metadata required')
        path=normalized_path(item.get('path'))
        if path in seen:raise ValueError('duplicate metadata path')
        seen.add(path)
        # Reuse the frozen size/Git/LFS validation on one basename; preserve the
        # validated full relative path only in this explicitly recursive schema.
        parsed=parse_listing(canonical([{**item,'path':PurePosixPath(path).name}]).encode(),{})['objects'][0]
        parsed['path']=path;objects.append(parsed)
        if parsed['type']=='file':
            family=path.split('/')[0] if '/' in path else '(root documents)'
            f=families.setdefault(family,{'files':0,'advertised_bytes':0,'sha256_objects':0})
            f['files']+=1;f['advertised_bytes']+=parsed['advertised_bytes']
            f['sha256_objects']+=parsed['advertised_sha256'] is not None
    return {'objects':sorted(objects,key=lambda o:o['path']),'families':families,
        'inventory_complete_by_http_pagination':not bool(headers.get('pagination_link')),
        'pagination_followed':False,'raw_contents_verified':False,'event_time_coverage_verified':False,
        'source_selected':False,'fresh_test_admitted':False,'acquisition_admitted':False}


def run(revision_receipt,request_path,output,getter=bounded_get):
    observed=load_json(revision_receipt);request=load_json(request_path)
    if (observed.get('schema')!='controller_requested_public_revision_metadata_v1'
            or observed.get('passed') is not True
            or observed.get('result_sha256')!=digest({k:v for k,v in observed.items() if k!='result_sha256'})
            or observed['request_sha256']!=file_hash(request_path)
            or observed['body_sha256']!=file_hash(revision_receipt.parent/'response.body.json')):
        raise ValueError('unchanged independent revision receipt and controller request required')
    dataset=observed['dataset'];revision=observed['observed_revision']
    if 'https://huggingface.co/api/datasets/'+dataset not in request['body']['public_metadata_urls']:
        raise ValueError('controller-requested source required')
    url=metadata_url(dataset,revision).replace('recursive=false','recursive=true')
    if output.exists():raise ValueError('fresh metadata inspection ID required')
    output.mkdir(parents=True,exist_ok=False)
    fresh_json(output/'claim.json',{'url':url,'revision_receipt_sha256':file_hash(revision_receipt),
        'request_sha256':file_hash(request_path),'max_body_bytes':MAX_BYTES,'maximum_pages':1,
        'created_at':datetime.now(timezone.utc).isoformat(),'raw_acquisition':False,'automatic_retry':False})
    try:
        body,headers=getter(url)
        if not isinstance(body,bytes) or len(body)>MAX_BYTES:raise ValueError('metadata size bound')
        with (output/'response.body.json').open('xb') as f:f.write(body)
        parsed=parse_inventory(body,headers)
        result={'schema':'public_source_recursive_metadata_review_v1','passed':True,
            'dataset':dataset,'revision':revision,'metadata_url':url,'http':headers,
            'response_body_sha256':hashlib.sha256(body).hexdigest(),
            'claim_sha256':file_hash(output/'claim.json'),'inspector_sha256':file_hash(Path(__file__)),
            'new_raw_download_bytes':0,'provider_calls':0,**parsed}
        result['result_sha256']=digest(result);fresh_json(output/'result.json',result);return result
    except Exception as e:
        fresh_json(output/'failure.json',{'passed':False,'error_type':type(e).__name__,
            'message_sha256':digest(str(e)),'automatic_retry':False,'raw_acquisition':False})
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('revision-receipt','request-path','output'):p.add_argument('--'+n,type=Path,required=True)
    r=run(**{k:v.resolve() for k,v in vars(p.parse_args()).items()})
    print(canonical({k:v for k,v in r.items() if k!='objects'}))
