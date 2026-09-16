"""Complete audit pipeline on three temporary synthetic quotes, no market read."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
from market_rsi import digest,file_hash,fresh_json
from quote_source.test_reconstruct import delta,T
from run_single_object_audit import remote_program


def run(output):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    raw=b''.join((json.dumps(delta(t=T+i))+'\n').encode() for i in range(3))
    encoded=subprocess.run(['zstd','-q','-c'],input=raw,stdout=subprocess.PIPE,check=True).stdout
    scope={'object':{'source_root':'/__SYNTHETIC_DIRECTORY__','relative_path':'fixture.zst','advertised_bytes':len(encoded)},
        'max_input_bytes':len(encoded),'max_decoded_bytes':1024*1024,'wall_seconds':30,
        'memory_bytes':1024**3,'synthetic_only':True}
    program=remote_program(scope).decode()
    wrapper=('import tempfile,pathlib,base64,sys,json\n'
        'with tempfile.TemporaryDirectory(prefix="market-rsi-synthetic-audit-") as tmp:\n'
        ' p=pathlib.Path(tmp)/"fixture.zst";p.write_bytes(base64.b64decode('+repr(base64.b64encode(encoded).decode())+'))\n'
        ' sys.argv=["synthetic-audit","--remote"]\n'
        ' exec('+repr(program)+'.replace("/__SYNTHETIC_DIRECTORY__",tmp),{"__name__":"__main__"})\n'
        'print(json.dumps({"stage":"canary_cleanup","temporary_directory_removed":not pathlib.Path(tmp).exists(),"raw_market_files_opened":0}))\n')
    claim={'schema':'single_object_audit_canary_claim_v1','program_sha256':hashlib.sha256(wrapper.encode()).hexdigest(),
        'runner_sha256':file_hash(__file__),'synthetic_compressed_sha256':hashlib.sha256(encoded).hexdigest(),
        'synthetic_decoded_sha256':hashlib.sha256(raw).hexdigest(),'raw_market_files_opened':0,'provider_calls':0}
    fresh_json(output/'claim.json',claim)
    done=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@173.255.231.4',
        'timeout --signal=TERM --kill-after=5s 35s python3 -u -'],input=wrapper.encode(),
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=45)
    if done.returncode or len(done.stdout)>65536:raise ValueError('synthetic complete pipeline failed')
    packets=[json.loads(line) for line in done.stdout.splitlines()]
    terminals=[p['report'] for p in packets if p.get('stage')=='terminal']
    if len(terminals)!=1:raise ValueError('missing synthetic terminal')
    r=terminals[0];t=r['transport']
    if (not r['complete'] or t['compressed_sha256']!=claim['synthetic_compressed_sha256']
        or t['decoded_sha256']!=claim['synthetic_decoded_sha256'] or t['decoded_records']!=3
        or not t['decoder_reaped'] or not t['feeder_reaped'] or not packets[-1]['temporary_directory_removed']
        or r['profile']['source_clock_totals']['counts']['quote_rows']!=3
        or r['profile']['population']['totals']['counts']['equal_mid_pairs']!=2
        or r['source_admitted'] or r['labels_computed']):raise ValueError('synthetic audit invariant differs')
    result={'schema':'single_object_audit_linux_canary_v1','passed':True,'claim':claim,'report':r,
        'temporary_directory_removed':True,'ssh_reaped':True,'exit_code':done.returncode,
        'raw_market_files_opened':0,'provider_calls':0}
    result['result_sha256']=digest(result);fresh_json(output/'canary.json',result)
    print({'passed':True,'result_sha256':result['result_sha256'],'synthetic_rows':3,'raw_market_files_opened':0})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
