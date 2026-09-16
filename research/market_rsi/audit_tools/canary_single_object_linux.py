"""Free Linode transport canary: only temporary synthetic text, no market access."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from market_rsi import digest,file_hash,fresh_json


def run(output):
    output=Path(output).resolve()
    if output.exists():raise ValueError('fresh canary output required')
    source=Path(__file__).with_name('single_object_stream.py')
    tests=Path(__file__).with_name('test_single_object_stream.py')
    program=("import sys,types,unittest,json,resource,signal,tempfile,subprocess,pathlib\n"
        "resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))\nsignal.alarm(30)\n"
        "m=types.ModuleType('single_object_stream');sys.modules[m.__name__]=m\nexec("+repr(source.read_text())+",m.__dict__)\n"
        "t=types.ModuleType('transport_tests');exec("+repr(tests.read_text())+",t.__dict__)\n"
        "r=unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromModule(t))\n"
        "with tempfile.TemporaryDirectory(prefix='market-rsi-synthetic-stream-') as tmp:\n"
        " p=pathlib.Path(tmp)/'fixture.zst';raw=b'{}\\n';encoded=subprocess.run(['zstd','-q','-c'],input=raw,stdout=subprocess.PIPE,check=True).stdout;p.write_bytes(encoded)\n"
        " checked=m.stream_object(p,advertised_bytes=len(encoded),max_input_bytes=len(encoded),max_decoded_bytes=1024,wall_seconds=10,consume=lambda *_:None,decoder_memory_bytes=256*1024**2)\n"
        " temporary_path=str(p)\n"
        "print(json.dumps({'passed':r.wasSuccessful() and r.testsRun==6 and not r.skipped and checked['complete'], 'tests':r.testsRun, 'skipped':len(r.skipped), 'limited_decoder':checked,'temporary_file_removed':not pathlib.Path(temporary_path).exists(),'raw_market_files_opened':0,'provider_calls':0}))\n"
        "sys.exit(0 if r.wasSuccessful() and checked['complete'] else 1)\n")
    output.mkdir(parents=True)
    claim={'schema':'single_object_linux_canary_claim_v1','host':'173.255.231.4',
        'program_sha256':hashlib.sha256(program.encode()).hexdigest(),
        'source_sha256':file_hash(source),'tests_sha256':file_hash(tests),'runner_sha256':file_hash(__file__),
        'wall_seconds':40,'raw_market_files_opened':0,'provider_calls':0,'synthetic_only':True}
    fresh_json(output/'claim.json',claim)
    done=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@173.255.231.4',
        'timeout --signal=TERM --kill-after=5s 35s python3 -u -'],input=program.encode(),
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
    if len(done.stdout)>65536 or len(done.stderr)>65536:raise ValueError('canary output bound')
    if done.returncode:raise RuntimeError('synthetic Linux canary failed; no market operation started')
    r=json.loads(done.stdout)
    if not r['passed'] or not r['temporary_file_removed']:raise ValueError('canary or cleanup failed')
    r.update(schema='single_object_linux_canary_v1',claim=claim,ssh_reaped=True,exit_code=done.returncode,
        market_rows_synthetic=True,source_admitted=False)
    r['result_sha256']=digest(r);fresh_json(output/'canary.json',r);print(r)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output)
