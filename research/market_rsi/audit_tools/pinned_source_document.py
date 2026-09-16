"""Fetch an explicitly requested root documentation file, verify its Git blob.

Not a general download tool: only README.md, DATA_DICTIONARY.md or schema.sql;
<=64KiB, anonymously, no redirects, exact reviewed revision/name/length/blob.
"""
import argparse
import hashlib
from pathlib import Path
import sys
from urllib.parse import urlsplit
from urllib.request import ProxyHandler,Request,build_opener

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from market_rsi import canonical,digest,file_hash,fresh_json,load_json
from public_source_metadata import NoRedirect,metadata_url

MAX_DOC_BYTES=65536
NAMES={'README.md','DATA_DICTIONARY.md','schema.sql'}


def document_url(receipt,request,name):
    if name not in NAMES:raise ValueError('requested root documentation only, never samples or data')
    dataset=receipt['dataset'];revision=receipt['revision'];metadata_url(dataset,revision)
    allowed=[]
    for raw in request['body']['public_metadata_urls']:
        p=urlsplit(raw)
        allowed.append(p.scheme=='https' and p.netloc=='huggingface.co'
            and p.path.startswith('/datasets/'+dataset+'/') and p.path.endswith('/'+name))
    if not any(allowed):raise ValueError('exact controller-requested dataset/document required')
    obj=next((o for o in receipt['objects'] if o['path']==name and o['type']=='file'),None)
    if obj is None or not 0<obj['advertised_bytes']<=MAX_DOC_BYTES:
        raise ValueError('bounded observed root document required')
    return f'https://huggingface.co/datasets/{dataset}/raw/{revision}/{name}',obj


def verify_document(body,obj):
    if not isinstance(body,bytes) or len(body)!=obj['advertised_bytes'] or len(body)>MAX_DOC_BYTES:
        raise ValueError('exact bounded document bytes required')
    body.decode('utf-8',errors='strict')
    git=hashlib.sha1(b'blob '+str(len(body)).encode()+b'\x00'+body).hexdigest()
    if git!=obj['git_oid']:raise ValueError('pinned Git blob mismatch')
    if obj.get('advertised_sha256') and hashlib.sha256(body).hexdigest()!=obj['advertised_sha256']:
        raise ValueError('advertised document SHA256 mismatch')
    return git


def bounded_doc_get(url):
    request=Request(url,headers={'Accept':'text/plain','Accept-Encoding':'identity',
        'User-Agent':'market-rsi-requested-document-audit/1'})
    with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=20) as r:
        if r.status!=200 or r.geturl()!=url:raise ValueError('exact HTTP200 document endpoint required')
        if r.headers.get_content_type() not in ('text/plain','text/markdown'):
            raise ValueError('plain documentation required; no HTML/data viewer')
        if r.headers.get('Content-Encoding','identity')!='identity':raise ValueError('identity encoding required')
        n=r.headers.get('Content-Length')
        if n is not None and (not n.isdecimal() or int(n)>MAX_DOC_BYTES):raise ValueError('document bound')
        body=r.read(MAX_DOC_BYTES+1)
        if len(body)>MAX_DOC_BYTES or (n is not None and int(n)!=len(body)):raise ValueError('length bound')
        return body,{'status':r.status,'content_type':r.headers.get_content_type(),
            'http_document_bytes':len(body),'etag':r.headers.get('ETag')}


def run(directory_receipt,request_path,name,output,getter=bounded_doc_get):
    receipt=load_json(directory_receipt);request=load_json(request_path)
    if (receipt.get('schema')!='public_source_directory_metadata_review_v1' or receipt.get('passed') is not True
            or receipt.get('result_sha256')!=digest({k:v for k,v in receipt.items() if k!='result_sha256'})
            or receipt['response_body_sha256']!=file_hash(directory_receipt.parent/'response.body.json')
            or request.get('acquisition_admitted') is not False):
        raise ValueError('unchanged independent directory receipt and non-acquiring request required')
    url,obj=document_url(receipt,request,name)
    if output.exists():raise ValueError('fresh document inspection ID required')
    output.mkdir(parents=True,exist_ok=False)
    fresh_json(output/'claim.json',{'url':url,'directory_receipt_sha256':file_hash(directory_receipt),
        'request_sha256':file_hash(request_path),'name':name,'max_document_bytes':MAX_DOC_BYTES,
        'automatic_retry':False,'market_data_acquisition':False})
    try:
        body,http=getter(url)
        if not isinstance(body,bytes) or len(body)>MAX_DOC_BYTES:raise ValueError('document body bound')
        with (output/'document.txt').open('xb') as f:f.write(body)
        oid=verify_document(body,obj)
        result={'schema':'controller_requested_pinned_source_document_v1','passed':True,
            'dataset':receipt['dataset'],'revision':receipt['revision'],'name':name,'url':url,'http':http,
            'git_blob_oid':oid,'document_sha256':hashlib.sha256(body).hexdigest(),
            'claim_sha256':file_hash(output/'claim.json'),'inspector_sha256':file_hash(Path(__file__)),
            'documentation_verified_not_raw_data':True,'provider_calls':0,'market_data_download_bytes':0,
            'source_selected':False,'acquisition_admitted':False,'fresh_test_admitted':False}
        result['result_sha256']=digest(result);fresh_json(output/'result.json',result);return result
    except Exception as e:
        fresh_json(output/'failure.json',{'passed':False,'error_type':type(e).__name__,
            'message_sha256':digest(str(e)),'automatic_retry':False,'market_data_acquisition':False})
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('directory-receipt','request-path','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--name',required=True);a=vars(p.parse_args())
    print(canonical(run(**{k:v.resolve() if isinstance(v,Path) else v for k,v in a.items()})))
