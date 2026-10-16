"""Close one known failed external work item; never run or retry its runtime.

Only a durable failed owner, settled owned requests and intact cleanup receipts
can release occupancy. Missing proof leaves the Native claim in place.
"""
from pathlib import Path
import re
import sqlite3

import earnings_entry as e
from earnings_http import save_bytes
from supervisor_harness import capacity_feedback_engine as engine


def _path(value):
    path=Path(value)
    if not path.is_absolute() or path.resolve()!=path:
        raise ValueError('Canonical original failure evidence path required')
    return path


def _owned_requests(runtime):
    records=[];seen=set();root=_path(runtime['root'])
    for slots in runtime['slots'].values():
        for raw in slots:
            slot=_path(raw)
            if slot.parent!=root/'roles':raise ValueError('Owned role slot required')
            for path in sorted(slot.glob('[0-9][0-9]-request.json')):
                bound=engine.pin(path);value=engine.read(bound);identifier=value.get('request_id')
                if (type(identifier) is not str or not identifier or identifier in seen
                        or type(value.get('reserved_nano_usd')) is not int
                        or value['reserved_nano_usd']<1
                        or value.get('payload',{}).get('model')!=runtime['rates']['api_model']):
                    raise ValueError('Exact distinct owned reservation receipts required')
                seen.add(identifier);records.append((bound,value))
    result=[]
    with sqlite3.connect(_path(runtime['ledger']).as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        if db.execute('SELECT * FROM config').fetchall()!=[(1,200_000_000_000,100_000_000_000,0)]:
            raise ValueError('Original unblocked ledger/caps required')
        for bound,value in records:
            row=db.execute('SELECT model,reserved,charged,status FROM requests WHERE id=?',
                (value['request_id'],)).fetchone()
            if (row is None or row[0]!=runtime['rates']['api_model']
                    or row[1]!=value['reserved_nano_usd']
                    or row[3] not in {'settled','settled_upper_bound'}
                    or type(row[2]) is not int or not 0<=row[2]<=row[1]
                    or (row[3]=='settled_upper_bound' and row[2]!=row[1])):
                raise ValueError('Every original owned request must be fully settled')
            result.append({'request':bound,'request_id':value['request_id'],
                'reserved_nano_usd':row[1],'charged_nano_usd':row[2],'status':row[3]})
    return result


def _cleanup(root):
    result=[];code=root/'code'
    if code.exists() and (not code.is_dir() or code.resolve()!=code):
        raise ValueError('Original code receipt directory required')
    for call in sorted(code.glob('call-*')):
        if (not call.is_dir() or call.resolve()!=call
                or re.fullmatch(r'call-[0-9a-f]{32}',call.name) is None):
            raise ValueError('Exact original code call directory required')
        bound=engine.pin(call/'result.json');value=engine.read(bound)
        bindings={name:engine.pin(call/name) for name in ('input.json','stdout.bin','stderr.bin')}
        original=engine.read(bindings['input.json'])
        if (value.get('status') not in {'COMPLETED','FAILED_NO_RETRY'}
                or value.get('cleanup_verified') is not True
                or value.get('host_candidate_execution') is not False
                or value.get('source_integrity_verified') is not True
                or value.get('retry_allowed') is not False
                or type(original.get('source')) is not str
                or value.get('source_sha256')!=e.digest(original['source'].encode())
                or any(value.get(key)!=bindings[name]['sha256'] for key,name in (
                    ('input_sha256','input.json'),('stdout_sha256','stdout.bin'),('stderr_sha256','stderr.bin')))):
            raise ValueError('Complete original source/input/output and cleanup proof required')
        result.append({'result':bound,'files':bindings})
    return result


def close_failed_work(batch, *, runtime_binding, work_id, pair_sha256, output_root, error_type):
    """Append fail after owner exit; no clock refresh, ledger write or adoption."""
    runtime=engine.read(runtime_binding);root=_path(runtime['root']);output_root=_path(output_root)
    if (runtime.get('purpose')!='capacity_episode' or type(error_type) is not str or not error_type
            or output_root!=root/'native-failure' or output_root.exists()):
        raise ValueError('Unused exact failed runtime closure directory required')
    identity=e.digest(runtime['id'].encode())
    claims=_path(runtime['ledger']).parent/'.capacity-runtime-claims'
    claim_binding=engine.pin(claims/(identity+'.json'))
    terminal_binding=engine.pin(claims/(identity+'.result.json'))
    claim=engine.read(claim_binding);terminal=engine.read(terminal_binding)
    summary=terminal.get('budget_summary')
    if (claim.get('runtime')!=runtime_binding or claim.get('id')!=runtime['id']
            or claim.get('source_commit')!=runtime['source_commit'] or claim.get('retry_allowed') is not False
            or terminal.get('runtime')!=runtime_binding or terminal.get('status')!='FAILED_NO_RETRY'
            or terminal.get('error_type')!=error_type or terminal.get('retry_allowed') is not False
            or type(summary) is not dict or summary.get('blocked') is not False
            or summary.get('unresolved_reserved_usd')!=0):
        raise ValueError('Exact closed failed owner with settled costs required; unknown crash stays claimed')
    before=batch.snapshot()
    rows=[row for row in before.get('capacity_work',[]) if row['work_id']==work_id]
    if (len(rows)!=1 or rows[0]['status']!='claimed' or rows[0]['pair_sha256']!=pair_sha256
            or work_id not in before['active_attempt_ids']):
        raise ValueError('Exact active claimed work and selected pair required')
    requests=_owned_requests(runtime);cleanup=_cleanup(root)
    prefix=[engine.pin(path) for path in sorted(batch.journal_dir.iterdir()) if path.is_file()]
    original_snapshot=engine.pin(batch.root/'batch.json');raw=e.checked(original_snapshot)
    # Freeze the old operational bytes before normal append-only advancement.
    output_root.mkdir(parents=True,exist_ok=False)
    save_bytes(output_root/'before-native-batch.json',raw)
    frozen=engine.pin(output_root/'before-native-batch.json')
    journal=engine.save(output_root/'before-native-journal.json',prefix)
    evidence=engine.save(output_root/'failure-evidence.json',{
        'schema':'earnings_native_known_failure_v1','runtime':runtime_binding,
        'owner_claim':claim_binding,'owner_terminal':terminal_binding,'error_type':error_type,
        'work_id':work_id,'pair_sha256':pair_sha256,'owned_requests':requests,'cleanup':cleanup,
        'historical_operational_snapshot':original_snapshot,'before_native_snapshot':frozen,
        'before_native_journal':journal,'retry_allowed':False,'candidate_adopted':False})
    batch.record_capacity_work('fail',work_id=work_id,pair_sha256=pair_sha256,
        evidence_sha256=evidence['sha256'],expected_state_sha256=before['state_sha256'])
    after=batch.snapshot()
    for key in ('attempts_claimed','branches','incumbent','micro_evolution'):
        if after[key]!=before[key]:raise ValueError('Failed work changed protected Native research state')
    for binding in prefix:e.checked(binding)
    after_binding=engine.save(output_root/'after-native-batch.json',after)
    return engine.save(output_root/'result.json',{
        'schema':'earnings_native_failure_closure_v1','status':'FAILED_WORK_CLOSED_NO_RETRY',
        'runtime':runtime_binding,'work_id':work_id,'pair_sha256':pair_sha256,
        'owner_terminal':terminal_binding,'before_native_snapshot':frozen,
        'before_native_journal':journal,'failure_evidence':evidence,'after_native_snapshot':after_binding,
        'own_request_count':len(requests),'own_charge_nano_usd':sum(v['charged_nano_usd'] for v in requests),
        'candidate_adopted':False,'retry_allowed':False})
