"""Explicit local exporter; never imports/runs experiment code or writes ledger.

Only Round0 training artifacts, explicit current clean proposal inputs, selected
Git objects and a read-only historical fee prefix enter the private package.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tarfile


def encoded(value):return (json.dumps(value,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()


class Export:
    def __init__(self,root,repo):
        self.root=Path(root).resolve();self.repo=Path(repo).resolve()
        self.root.mkdir(mode=0o700,parents=False,exist_ok=False)
        (self.root/'objects').mkdir(mode=0o700)
        self.files={};self.objects={};self.proofs=[];self.proof_keys=set()

    def raw(self,raw,origin):
        # Original receipts are never redacted/re-written. Refuse the whole
        # export if credential-shaped material unexpectedly occurs.
        if (re.search(rb'(?<![A-Za-z0-9_-])sk-(?:proj|svcacct)-[A-Za-z0-9_-]{24,}',raw)
                or (b'-----BEGIN '+b'PRIVATE KEY-----') in raw
                or re.search(rb'Authorization["\x27]?\s*[:=]\s*["\x27]?(?:Bearer|Basic)\s+[A-Za-z0-9_-]{20,}',raw)):
            raise ValueError('Credential-shaped bytes; export refused: '+origin)
        token=sha(raw);item=self.files.get(token)
        if item is None:
            relative='objects/'+token
            fd=os.open(self.root/relative,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(raw)
            item=dict(relative_path=relative,bytes=len(raw),original_paths=[]);self.files[token]=item
        if origin not in item['original_paths']:item['original_paths'].append(origin)
        return dict(path=origin,sha256=token)

    def file(self,path,expected=None):
        path=Path(path)
        if path.resolve()!=path or path.is_symlink() or not path.is_file() or path.stat().st_nlink!=1:
            raise ValueError('Canonical original file required: '+str(path))
        raw=path.read_bytes()
        if expected is not None and sha(raw)!=expected:raise ValueError('Original hash drift: '+str(path))
        return self.raw(raw,str(path))

    def bound(self,binding):return self.file(binding['path'],binding['sha256'])
    def value(self,binding):return json.loads(self._bytes(binding))
    def _bytes(self,binding):
        item=self.files[binding['sha256']];return (self.root/item['relative_path']).read_bytes()

    def git(self,*args):
        return subprocess.run(['git',*args],cwd=self.repo,check=True,capture_output=True).stdout

    def object(self,oid):
        if oid in self.objects:return self.objects[oid]['type'],self._bytes(self.objects[oid]['binding'])
        kind=self.git('cat-file','-t',oid).decode().strip()
        raw=self.git('cat-file',kind,oid)
        if hashlib.sha1((kind+' '+str(len(raw))+'\0').encode()+raw).hexdigest()!=oid:
            raise ValueError('Git object identity mismatch')
        self.objects[oid]=dict(type=kind,binding=self.raw(raw,'git-object:'+oid))
        return kind,raw

    def proof(self,commit,path,binding):
        key=(commit,path)
        if key in self.proof_keys:return
        kind,raw=self.object(commit)
        if kind!='commit':raise ValueError('Expected Git commit')
        oid=raw.split(b'\n',1)[0][5:].decode()
        for name in path.split('/'):
            kind,raw=self.object(oid);entries={};offset=0
            if kind!='tree':raise ValueError('Expected Git tree')
            while offset<len(raw):
                end=raw.index(b'\0',offset);_,filename=raw[offset:end].split(b' ',1)
                entries[filename.decode()]=raw[end+1:end+21].hex();offset=end+21
            oid=entries[name]
        kind,raw=self.object(oid)
        if kind!='blob' or raw!=self._bytes(binding):raise ValueError('Committed source differs: '+path)
        self.proofs.append(dict(commit=commit,repository_path=path,binding=binding));self.proof_keys.add(key)

    def historical_source(self,commit,name,bound):
        raw=self.git('show',commit+':'+name)
        if sha(raw)!=bound['sha256']:raise ValueError('Historic Source hash mismatch: '+name)
        copied=self.raw(raw,bound['path']);self.proof(commit,name,copied)


def build(artifacts,repo,output,clean_id,code_commit):
    A=Path(artifacts).resolve();D=Path(repo).resolve();out=Path(output).resolve()
    original_manifest=A/'TRAIN25-PLAIN-COMPARATOR-MANIFEST.json'
    if not A.is_dir() or not D.is_dir():raise ValueError('Explicit original artifacts/repo required')
    ex=Export(out,D)
    bind=lambda name:ex.file(A/name)
    r0=bind('TRAIN25-PLAIN-COMPARATOR-MANIFEST.json');manifest=ex.value(r0)
    if r0['sha256']!='7a43ee9cac7204ef664d134c2e5effac14e2422aa9cedc207f66fcfe55ef07a3':raise ValueError('Wrong original Round0 manifest')
    split=ex.bound(manifest['split']);scope=ex.value(split)
    training=scope['training']
    if len(training)!=25 or len(set(training))!=25 or set(training)&set(scope['heldout']):raise ValueError('Wrong split')
    summary=bind('TRAIN25-BASELINE-COMPLETE.json');saved_summary=ex.value(summary)
    root_closure=bind('TRAIN25-BASELINE-ROOT-CLOSURE.json');closure=ex.value(root_closure)
    round0_git=ex.value(bind('TRAIN25-BASELINE-COMPLETE-GIT.json'))['commit']
    ex.proof(round0_git,'manifest.json',r0);ex.proof(round0_git,'summary.json',summary)
    runs=[];omitted=[]
    for row in manifest['rows']:
        if row['cik'] not in training:raise ValueError('Nontraining row before content access')
        for key,binding in row.items():
            if key=='cik':continue
            if key=='score':
                omitted.append(dict(binding=binding,reason='Protected raw score/answer detail excluded; replay public fractional awards only.'))
            else:ex.bound(binding)
    for window in saved_summary['windows']:
        config_bound=ex.bound(window['config']);config=ex.value(config_bound)
        if any(c not in training for c in config['companies']):raise ValueError('Nontraining physical run')
        for key in ('identity','terminal'):ex.bound(window[key])
        identity=ex.value(window['identity'])
        for key in ('review','checkpoint'):ex.bound(identity[key])
        ex.bound(config['driver']);ex.bound(config['runtime'])
        for name,binding in config['source_bindings'].items():ex.historical_source(config['source_commit'],name,binding)
        root=Path(config['output'])
        if root.parent!=A/'training-baseline':raise ValueError('Only original owned baseline tree')
        generations=[];finalizations=[]
        allowed=re.compile(r'(?:[0-9]{2}-(?:request|response|count|research-request|research-count|finalization)\.json|http-[A-Za-z0-9_-]+\.(?:intent|response|error)\.json|http-[A-Za-z0-9_-]+\.raw\.bin|identity\.json|result\.json|predictions\.json|public-feedback\.json|budget-summary\.json|terminal\.json)')
        for path in sorted(root.rglob('*')):
            if path.is_file() and allowed.fullmatch(path.name):
                ex.file(path)  # Original bytes, including opaque raw responses; never reasoning-decode.
                if re.fullmatch(r'[0-9]{2}-request\.json',path.name):
                    generations.append(dict(request=ex.file(path),response=ex.file(path.with_name(path.name.replace('-request','-response')))))
                if re.fullmatch(r'[0-9]{2}-finalization\.json',path.name):finalizations.append(ex.file(path))
        runs.append(dict(id=config['identifier'],config=config_bound,identity=window['identity'],terminal=window['terminal'],generations=generations,finalizations=finalizations))
    for failure in saved_summary['excluded_failed_attempts']:ex.bound(failure['result'])
    # Explicit upper prefix, never a live SQLite copy or any database mutation.
    runtime_path=A/'inputs'/clean_id/'runtime-reviewed.json'
    runtime_bound=ex.file(runtime_path);runtime=ex.value(runtime_bound)
    closure_bound=bind('TRAIN25-CLEAN50-REJECTED-CLOSURE.json')
    clean_closure=ex.value(closure_bound)
    if (clean_closure['status']!='PROPOSAL_NOT_ACCEPTED' or clean_closure['original_exec_true_exit']!=0
            or clean_closure['runtime']!=runtime_bound or clean_closure['current_pending_count']!=0):
        raise ValueError('Exact closed rejected proposal required')
    prefix=clean_closure['current_ledger']['max_rowid']
    ledger=Path(runtime['ledger'])
    with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        rows=db.execute('SELECT rowid,id,model,reserved,charged,status FROM requests WHERE rowid<=? ORDER BY rowid',(prefix,)).fetchall()
    ledger_snapshot=ex.raw(encoded(dict(schema='edgar25_readonly_ledger_prefix_v1',max_rowid=prefix,rows=rows,
        prefix_sha256=sha(json.dumps(rows,separators=(',',':')).encode()),qualification='Historical selected financial columns, not a writable ledger or invoice audit.')),'generated:ledger-prefix')
    if ex.value(ledger_snapshot)['prefix_sha256']!=clean_closure['current_ledger']['rows_sha256']:raise ValueError('Original ledger prefix changed')
    earlier=[r for r in rows if r[0]<=runtime['baseline']['max_rowid']]
    if sha(json.dumps(earlier,separators=(',',':')).encode())!=runtime['baseline']['rows_sha256']:raise ValueError('Preproposal ledger prefix changed')
    root0=dict(schema='edgar25_round_manifest_v1',trajectory='round0',logical_round=0,
        state='SCORED25_ORIGINAL_CLOSURE_RECEIPTS_PRESERVED',original_manifest=r0,summary=summary,
        physical_runs=runs,expected_generations=closure['accounting']['new_settled_generations'],
        expected_cost_nano_usd=closure['accounting']['stage_spent_nano_usd'],
        evaluated_parent=None,candidate=None,next_feedback='Complete125 public pairs in clean proposal task; actual model use is separate physical evidence.')
    r0_manifest=ex.raw(encoded(root0),'generated:round0-manifest')
    for key in ('forecast_study','initial_population','population_plan','review','budget_amendment','model_budget_amendment'):ex.bound(runtime[key])
    study=ex.value(runtime['forecast_study']);ex.bound(study['prior_batch']);task=ex.value(ex.bound(study['clean_slate_task']))
    ex.bound(task['feedback'])
    for name,binding in runtime['sources'].items():
        relative=str(Path(binding['path']).relative_to(D))
        ex.historical_source(runtime['source_commit'],relative,binding)
    launch=bind('TRAIN25-CLEAN50-LAUNCH-RECEIPT.json');approval=bind('TRAIN25-DIRECT-OPENAI-PAYLOAD-APPROVAL.json')
    for name in ('TRAIN25-CLEAN50-LAUNCH-BLOCKED.json','TRAIN25-CLEAN50-INPUT-GIT.json','TRAIN25-CLEAN50-APPROVAL-BLOCKED-GIT.json'):bind(name)
    # Closed originals only, no snapshots of an active request and no follow of
    # protected QA/score links. Physical raw responses remain opaque bytes.
    attempt=Path(runtime['root'])
    for path in sorted(attempt.rglob('*')):
        if path.is_file():
            if path.name in ('score.json','evaluation_qa.json'):
                omitted.append(dict(binding=dict(path=str(path),sha256=sha(path.read_bytes())),reason='Protected answer/scorer material excluded.'))
            else:ex.file(path)
    for key in ('owner','claim','review','source_review_stage','audit_script'):ex.bound(clean_closure[key])
    owner=ex.value(clean_closure['owner']);ex.bound(owner['clock'])
    for key in ('native_evidence','financial_evidence'):
        for bound in clean_closure[key]:ex.bound(bound)
    candidate=clean_closure['candidate']
    for axis in ('R','H'):ex.bound(candidate[axis])
    rejected_git=bind('TRAIN25-CLEAN50-REJECTED-CLOSED-GIT.json')
    rejected_commit=ex.value(rejected_git)['commit']
    ex.proof(rejected_commit,'original/'+str(Path(candidate['R']['path']).relative_to(A)),candidate['R'])
    roles=[]
    for role in ('controller','author','review'):
        slot=attempt/'roles'/(role+'-01')
        generations=[dict(request=ex.file(p),response=ex.file(p.with_name(p.name.replace('-request','-response'))))
            for p in sorted(slot.glob('[0-9][0-9]-request.json'))]
        roles.append(dict(role=role,generations=generations,physical_bindings=clean_closure['actual_physical_roles'][role]['bindings']))
    clean=dict(schema='edgar25_round_manifest_v1',trajectory='clean_slate',logical_round=1,
        state='PROPOSAL_REJECTED_CLOSED_NOT_A_COMPLETED_RESEARCH_ROUND',as_of_utc=clean_closure['created_utc'],physical_run_ids=[clean_id],
        runtime=runtime_bound,launch=launch,approval=approval,candidate=candidate,scored=0,
        actual_parent='Unscored empty R0/H0 ABI scaffold, not R09/control/Round0 model or a stage best.',
        frozen_candidate=None,decision='INCOMPLETE_NO_SELECTION',
        closure=closure_bound,rejected_git=rejected_git,result=clean_closure['result'],owner=clean_closure['owner'],roles=roles,
        implement=ex.file(attempt/'loop/round-0001-implement.done.json'),source_review=clean_closure['source_review_stage'],
        expected_generations=clean_closure['owned_generations'],expected_cost_nano_usd=clean_closure['owned_charged_nano_usd'],
        unverifiable=['No candidate forecast or25-company comparison exists. Review rejected evidence-acquisition integration before freezing.',
            'Original EXIT0 is the supervising operator receipt of exec21317, not an independently signed OS attestation.',
            'Native closure was metadata-audited at the source; offline replay verifies preserved bytes, not Docker or protected scorer execution.'])
    clean_manifest=ex.raw(encoded(clean),'generated:clean-slate-round1-manifest')
    archive_receipt=bind('TRAIN25-PANEL47-INCOMPLETE-EVIDENCE-GIT.json')
    code={}
    for name in ('replay.py','build_bundle.py','README.txt'):
        path=D/'repro/edgar25'/name;bound=ex.file(path);code[name]=bound
        ex.proof(code_commit,'repro/edgar25/'+name,bound)
    manifest=dict(schema='edgar25_offline_bundle_v1',created_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        access='PRIVATE_AUTHORIZED_TRAINING_EVIDENCE_ONLY; contains original request/response data. Owner approval required for transfer; no credential/heldout body content.',
        files=ex.files,git_objects=ex.objects,source_proofs=ex.proofs,rounds=[r0_manifest,clean_manifest],
        replay_code_commit=code_commit,replay_code=code,ledger_snapshot=ledger_snapshot,
        legacy_archive=dict(receipt=archive_receipt,status='ARCHIVE_ONLY_OLD47_EXIT_UNKNOWN_NOT_NEW_PANEL_DATA',
            bodies_packaged=False,remaining_gap='Legacy full histories are not yet packaged/replayed.'),
        restricted_omissions=omitted,limitations=['Replay reported public awards, not recompute protected scorer/ground truth.',
            'No heldout bodies, QA/reference answer files, credentials, provider keys or writable ledger.',
            'Raw HTTP responses preserved as opaque bytes; hidden reasoning is not interpreted.',
            'Git/Merkle/hash integrity does not certify truthful original measurement or provider invoice.',
            'Clean proposal was genuinely rejected before forecasting;0/25 candidate coverage is not a completed research round.'])
    raw=encoded(manifest)
    fd=os.open(out/'manifest.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw)
    package=out.with_suffix('.tar.gz')
    if package.exists():raise FileExistsError('Never overwrite a versioned package')
    with tarfile.open(package,'x:gz',compresslevel=1) as tar:tar.add(out,arcname='evidence',recursive=True)
    package.chmod(0o600)
    return dict(bundle_directory=str(out),manifest_sha256=sha(raw),package=str(package),package_sha256=sha(package.read_bytes()),
        files=len(ex.files),uncompressed_bytes=sum(r['bytes'] for r in ex.files.values()),package_bytes=package.stat().st_size,
        replay_code_commit=code_commit,original_ledger_writes=0,model_calls=0)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',required=True);parser.add_argument('--repo',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--clean-id',default='edgar-population-20261016-50')
    parser.add_argument('--code-commit',required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.artifacts,args.repo,args.output,args.clean_id,args.code_commit),sort_keys=True,indent=2))
