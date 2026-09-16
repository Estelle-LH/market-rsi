"""Bounded CSV-header-only inspection; no price rows returned or source admitted.

Controller-independent plumbing check over the already inventoried dates. This
does not select dates/universe/targets, inspect labels, or change remote files.
"""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


def header(path):
    before=path.stat()
    with (gzip.open(path,'rb') if path.name.endswith('.gz') else path.open('rb')) as stream:
        raw=stream.readline(65537)
    after=path.stat()
    if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
        raise ValueError('file changed during header probe')
    if not raw or len(raw)>65536 or not raw.endswith(b'\n'):
        raise ValueError('empty, unterminated or oversized CSV header')
    columns=next(csv.reader([raw.decode('utf-8-sig').rstrip('\r\n')]))
    if not columns or len(columns)>256 or len(set(columns))!=len(columns):
        raise ValueError('ambiguous CSV columns')
    return {'name':path.name,'file_bytes':before.st_size,'mtime_ns':before.st_mtime_ns,
        'header_sha256':hashlib.sha256(raw).hexdigest(),'columns':columns,
        'full_file_sha256':None,'csv_data_rows_parsed':0,'gzip_full_integrity_checked':False}


def probe(root,dates):
    if not dates or len(dates)>100 or len(set(dates))!=len(dates) or any(
            not isinstance(d,str) or not re.fullmatch(r'2026-\d{2}-\d{2}',d) for d in dates):
        raise ValueError('bounded exact inventoried dates required')
    result=[]
    for day in dates:
        directory=root/day
        if directory.is_symlink() or not directory.is_dir():raise ValueError('inventoried day unavailable')
        for path in sorted(directory.iterdir()):
            if not (path.is_file() and not path.is_symlink() and
                    path.name.startswith(('topofbook_','depth_','trades_','markets_')) and
                    path.name.endswith(('.csv','.csv.gz'))):continue
            try:value={'status':'header_read',**header(path)}
            except (ValueError,UnicodeError,OSError,EOFError,csv.Error) as error:
                value={'status':'failed','name':path.name,'error_type':type(error).__name__,'error':str(error)[:300]}
            result.append({'directory_date':day,**value})
            if len(result)>500:raise ValueError('file count bound')
    return {'schema':'capture_csv_header_probe_v1','files':result,'dates':dates,
        'csv_data_rows_parsed':0,'source_admitted':False,'labels_built':0,
        'limitations':['Header presence is not row/clock/unit correctness.',
            'Decompressor can buffer bytes beyond header; no data rows were parsed or returned.',
            'Full gzip integrity/source hash/completeness have not been checked.']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--remote-dates');p.add_argument('--inventory',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.remote_dates:
        print(json.dumps(probe(Path('/opt/d10/research'),json.loads(a.remote_dates)),sort_keys=True));return
    if not a.inventory or not a.output or a.output.exists():raise ValueError('inventory and fresh output required')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from market_rsi import digest,file_hash,fresh_json,load_json
    inv=load_json(a.inventory)
    if inv.get('result_sha256')!=digest({k:v for k,v in inv.items() if k!='result_sha256'}):
        raise ValueError('inventory receipt changed')
    dates=[d['directory_date'] for d in inv['days']]
    # This argument contains only validated ISO dates, never data or shell code.
    if any(not re.fullmatch(r'2026-\d{2}-\d{2}',d) for d in dates):raise ValueError('invalid date')
    import shlex
    cmd='timeout 30s python3 - --remote-dates '+shlex.quote(json.dumps(dates))
    response=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@173.255.231.4',cmd],
        input=Path(__file__).read_bytes(),capture_output=True,timeout=45)
    if response.returncode or len(response.stdout)>1_000_000:raise RuntimeError('bounded schema probe failed; no automatic retry')
    value=json.loads(response.stdout)
    value.update(inventory_sha256=file_hash(a.inventory),reader_sha256=file_hash(__file__),
        transport_response_bytes=len(response.stdout),remote_host='173.255.231.4')
    value['result_sha256']=digest(value);a.output.parent.mkdir(parents=True,exist_ok=True);fresh_json(a.output,value)
    print({'file_count':len(value['files']),'failed_headers':sum(f['status']=='failed' for f in value['files']),
        'schemas':[list(t) for t in sorted({tuple(f['columns']) for f in value['files'] if 'columns' in f})],
        'csv_data_rows_parsed':0,'source_admitted':False,'result_sha256':value['result_sha256']})


if __name__=='__main__':main()
