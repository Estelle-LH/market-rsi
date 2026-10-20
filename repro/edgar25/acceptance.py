"""Fresh-directory acceptance, using only a Git code archive and evidence tar."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time


def run(repo,commit,archive,package_sha,manifest_sha):
    package=Path(archive).read_bytes()
    assert hashlib.sha256(package).hexdigest()==package_sha
    fresh=Path(tempfile.mkdtemp(prefix='edgar25-offline-accept-')).resolve()
    code=fresh/'checkout';code.mkdir()
    archived=subprocess.run(['git','archive',commit],cwd=repo,check=True,capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archived)) as tar:tar.extractall(code,filter='data')
    with tarfile.open(fileobj=io.BytesIO(package),mode='r:gz') as tar:tar.extractall(fresh,filter='data')
    evidence=fresh/'evidence';script=code/'repro/edgar25/replay.py'
    env={'PATH':'/usr/bin:/bin','LANG':'en_US.UTF-8','PYTHONDONTWRITEBYTECODE':'1'}
    def replay(expected):
        start=time.monotonic()
        child=subprocess.run([sys.executable,'-I','-B',str(script),'--bundle',str(evidence),
            '--manifest-sha256',expected],cwd=fresh,env=env,capture_output=True,text=True,timeout=120)
        return dict(exit=child.returncode,seconds=time.monotonic()-start,
            output=json.loads(child.stdout) if child.stdout else None,stderr=child.stderr[-3000:])
    good=replay(manifest_sha)
    (fresh/'replay-report.json').write_text(json.dumps(good,sort_keys=True,indent=2)+'\n')
    if good['exit']!=0:
        print(json.dumps(dict(fresh_directory=str(fresh),positive=good),sort_keys=True));return 1
    manifest_path=evidence/'manifest.json';raw=manifest_path.read_bytes();manifest=json.loads(raw)
    token,item=next((k,v) for k,v in manifest['files'].items() if v['bytes']>20)
    asset=evidence/item['relative_path'];original=asset.read_bytes()
    negative={}
    asset.rename(asset.with_suffix('.test-missing'))
    try:negative['missing_file']=replay(manifest_sha)
    finally:asset.with_suffix('.test-missing').rename(asset)
    asset.write_bytes(original+b'!')
    try:negative['tampered_hash']=replay(manifest_sha)
    finally:asset.write_bytes(original)
    negative['wrong_trust_anchor']=replay('0'*64)
    # A consistent replacement manifest is still not allowed to substitute a
    # candidate for the actual immutable implementation-stage result.
    bound=manifest['rounds'][1];entry=manifest['files'][bound['sha256']]
    clean=json.loads((evidence/entry['relative_path']).read_bytes())
    clean['candidate']['id']='0'*64
    changed=(json.dumps(clean,sort_keys=True,indent=2)+'\n').encode();changed_sha=hashlib.sha256(changed).hexdigest()
    (evidence/'objects'/changed_sha).write_bytes(changed)
    manifest['files'][changed_sha]=dict(relative_path='objects/'+changed_sha,bytes=len(changed),original_paths=[bound['path']])
    manifest['rounds'][1]=dict(path=bound['path'],sha256=changed_sha)
    changed_manifest=(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode();manifest_path.write_bytes(changed_manifest)
    try:negative['wrong_candidate']=replay(hashlib.sha256(changed_manifest).hexdigest())
    finally:manifest_path.write_bytes(raw)
    unit=subprocess.run([sys.executable,'-I','-B','-c',
        'import sys,unittest;sys.path.insert(0,'+repr(str(script.parent))+');import test_replay;'
        'result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(test_replay));sys.exit(not result.wasSuccessful())'],
        cwd=fresh,env=env,capture_output=True,text=True,timeout=120)
    assert all(r['exit']==2 and r['output']['status']=='UNVERIFIABLE' for r in negative.values())
    assert unit.returncode==0
    report=dict(schema='edgar25_clean_environment_acceptance_v1',fresh_directory=str(fresh),
        code_commit=commit,package_sha256=package_sha,manifest_sha256=manifest_sha,
        positive_exit=good['exit'],positive_seconds=good['seconds'],
        replay_report=str(fresh/'replay-report.json'),rounds=[{k:r.get(k) for k in
            ('trajectory','state','scored','targets','total_points','company_equal_mean','selection','fees','physical_full_feedback_generations')} for r in good['output']['rounds']],
        negatives=negative,unit_tests=dict(exit=unit.returncode,output=unit.stderr),
        environment='Fresh physical extraction; sanitized env without API variables; Python-I/-B; runtime audit denies sockets/subprocesses/writes/reads outside fresh code/evidence/stdlib.',
        network_calls=0,model_calls=0,original_ledger_writes=0)
    (fresh/'acceptance-report.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps(report,sort_keys=True));return 0


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('repo','commit','archive','package-sha','manifest-sha'):p.add_argument('--'+name,required=True)
    a=p.parse_args();sys.exit(run(a.repo,a.commit,a.archive,a.package_sha,a.manifest_sha))
