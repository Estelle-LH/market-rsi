"""Resolve a controller-requested public HF dataset revision from metadata only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from market_rsi import canonical,digest,file_hash,fresh_json,load_json
from public_source_metadata import bounded_get,metadata_url,unique_object,no_constant,MAX_BYTES


def parse_info(body,dataset):
    if not isinstance(body,bytes) or len(body)>MAX_BYTES:raise ValueError('bounded metadata only')
    v=json.loads(body,object_pairs_hook=unique_object,parse_constant=no_constant)
    if not isinstance(v,dict) or v.get('id')!=dataset:raise ValueError('exact requested dataset required')
    if not isinstance(v.get('sha'),str) or not re.fullmatch('[0-9a-f]{40}',v['sha']):
        raise ValueError('observed full revision required')
    return {'dataset':dataset,'observed_revision':v['sha'],
        'last_modified_metadata':v.get('lastModified'),'private':v.get('private'),
        'siblings_metadata_count':len(v['siblings']) if isinstance(v.get('siblings'),list) else None,
        'recursive_inventory_verified':False,'file_sizes_verified':False,'raw_contents_read':False,
        'source_selected':False,'acquisition_admitted':False,'new_fresh_test':False}


def run(dataset,request_path,output,getter=bounded_get):
    metadata_url(dataset,'0'*40)  # reuse exact owner/dataset syntax validation
    url='https://huggingface.co/api/datasets/'+dataset
    request=load_json(request_path)
    if request.get('acquisition_admitted') is not False or url not in request['body']['public_metadata_urls']:
        raise ValueError('exact controller-requested public metadata URL required')
    if output.exists():raise ValueError('fresh permanent inspection ID required')
    output.mkdir(parents=True,exist_ok=False)
    fresh_json(output/'claim.json',{'url':url,'request_sha256':file_hash(request_path),
        'requested_at':datetime.now(timezone.utc).isoformat(),'max_body_bytes':MAX_BYTES,
        'raw_acquisition':False,'automatic_retry':False})
    try:
        body,headers=getter(url)
        if not isinstance(body,bytes) or len(body)>MAX_BYTES:raise ValueError('metadata size bound')
        with (output/'response.body.json').open('xb') as f:f.write(body)
        parsed=parse_info(body,dataset)
        result={'schema':'controller_requested_public_revision_metadata_v1','passed':True,
            'url':url,'http':headers,'body_sha256':hashlib.sha256(body).hexdigest(),
            'request_sha256':file_hash(request_path),'claim_sha256':file_hash(output/'claim.json'),
            'inspector_sha256':file_hash(Path(__file__)),'provider_calls':0,'raw_download_bytes':0,**parsed}
        result['result_sha256']=digest(result);fresh_json(output/'result.json',result);return result
    except Exception as e:
        fresh_json(output/'failure.json',{'passed':False,'error_type':type(e).__name__,
            'message_sha256':digest(str(e)),'automatic_retry':False,'raw_acquisition':False})
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',required=True)
    p.add_argument('--request-path',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(canonical(run(a.dataset,a.request_path.resolve(),a.output.resolve())))
