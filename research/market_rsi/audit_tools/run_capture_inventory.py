"""Save a bounded, read-only remote metadata inventory without raw market rows."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_rsi import digest,file_hash,fresh_json

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if args.output.exists(): raise ValueError('fresh metadata receipt required')
script=Path(__file__).with_name('capture_inventory_metadata.py')
response=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@173.255.231.4',
    'timeout 20s python3 -'],input=script.read_bytes(),capture_output=True,timeout=35)
if response.returncode or len(response.stdout)>14_000_000:
    raise RuntimeError('metadata SSH read failed or exceeded bound; no automatic retry')
value=json.loads(response.stdout)
value.update(reader_sha256=file_hash(script),transport_sha256=file_hash(__file__))
value['result_sha256']=digest(value)
args.output.parent.mkdir(parents=True,exist_ok=True)
fresh_json(args.output,value)
summary=[]
for day in value['days']:
    manifest=day['metadata'].get('manifest.json',{}).get('content',{})
    qa=day['metadata'].get('qa_'+day['directory_date']+'.json',{}).get('content',{})
    summary.append({'date':day['directory_date'],'complete_day_claim':manifest.get('complete_day'),
        'qa_counts':qa.get('counts'), 'topofbook_bytes':sum(f['bytes'] for f in day['files'] if f['name'].startswith('topofbook'))})
print(json.dumps({'summary':summary,'source_admitted':False,'market_rows_read':0,'result_sha256':value['result_sha256']}))
