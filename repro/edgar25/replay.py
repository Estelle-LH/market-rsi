"""Read-only saved-result replay. Python stdlib only; never import experiment code."""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys

TARGETS = ['T%03d'%i for i in range(1,6)]


class Unverifiable(ValueError): pass


def require(condition, message):
    if not condition: raise Unverifiable(message)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def loads(raw):
    def pairs(items):
        value={}
        for k,v in items:
            require(k not in value,'Duplicate JSON key: '+k);value[k]=v
        return value
    return json.loads(raw,object_pairs_hook=pairs,
        parse_constant=lambda v:(_ for _ in ()).throw(Unverifiable('Nonfinite JSON: '+v)))


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def production_digest(value):
    return sha(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode())


class Bundle:
    def __init__(self, root, expected):
        self.root=Path(root).resolve();path=self.root/'manifest.json'
        require(not path.is_symlink() and path.is_file(),'Missing regular manifest')
        raw=path.read_bytes();require(sha(raw)==expected,'Manifest trust-anchor mismatch')
        self.manifest=loads(raw)
        require(self.manifest.get('schema')=='edgar25_offline_bundle_v1','Unknown bundle schema')
        require(sha(Path(__file__).read_bytes())==self.manifest['replay_code']['replay.py']['sha256'],'Replay code differs from specified delivery commit')
        self.cache={}
        for token,item in self.manifest['files'].items():
            relative=PurePosixPath(item['relative_path'])
            require(not relative.is_absolute() and '..' not in relative.parts,'Unsafe relative path')
            path=self.root.joinpath(*relative.parts)
            require(path.resolve()==path and path.is_relative_to(self.root) and not path.is_symlink(),'Aliased bundle file')
            require(path.is_file(),'Missing evidence: '+str(relative))
            raw=path.read_bytes()
            require(len(raw)==item['bytes'] and sha(raw)==token,'Evidence hash mismatch: '+str(relative))
        self.verify_git()

    def read(self,bound):
        require(type(bound) is dict and set(bound)=={'path','sha256'},'Exact historical binding required')
        item=self.manifest['files'].get(bound['sha256'])
        require(item is not None and bound['path'] in item['original_paths'],'Unmapped historical evidence: '+bound['path'])
        # NEVER open bound['path']; it remains historical text only.
        raw=self.root.joinpath(*PurePosixPath(item['relative_path']).parts).read_bytes()
        require(sha(raw)==bound['sha256'],'Evidence changed after initial integrity scan')
        return raw

    def json(self,bound):return loads(self.read(bound))

    def object(self,oid):
        obj=self.manifest['git_objects'].get(oid)
        require(obj is not None,'Missing Git object proof: '+oid)
        raw=self.read(obj['binding']);kind=obj['type']
        require(hashlib.sha1((kind+' '+str(len(raw))+'\0').encode()+raw).hexdigest()==oid,'Git object identity mismatch')
        return kind,raw

    def git_file(self,commit,path):
        kind,raw=self.object(commit);require(kind=='commit','Expected Git commit')
        first=raw.split(b'\n',1)[0];require(first.startswith(b'tree '),'Missing Git tree')
        oid=first[5:].decode()
        parts=PurePosixPath(path).parts
        require(parts and not PurePosixPath(path).is_absolute() and '..' not in parts,'Unsafe Git source path')
        for index,name in enumerate(parts):
            kind,raw=self.object(oid);require(kind=='tree','Expected Git tree')
            entries={};offset=0
            while offset<len(raw):
                end=raw.index(b'\0',offset);mode,filename=raw[offset:end].split(b' ',1)
                entries[filename.decode()]=(mode,raw[end+1:end+21].hex());offset=end+21
            require(name in entries,'Missing committed source: '+path)
            mode,oid=entries[name]
            require(mode in ((b'100644',b'100755') if index==len(parts)-1 else (b'40000',)), 'Symlink/submodule not replay source')
        kind,raw=self.object(oid);require(kind=='blob','Expected source blob');return raw

    def verify_git(self):
        for source in self.manifest['source_proofs']:
            require(self.git_file(source['commit'],source['repository_path'])==self.read(source['binding']),
                'Source/manifest not in specified Git commit: '+source['repository_path'])


def predictions(response):
    require(response.get('status')=='completed' and response.get('error') is None,'Incomplete/refused final response')
    require(not any(r.get('type') in ('function_call','refusal') for r in response['output']),'Tool-bearing final response')
    text=''.join(c['text'] for r in response['output'] if r.get('type')=='message'
        for c in r.get('content',[]) if c.get('type')=='output_text')
    value=loads(text);rows=value.get('predictions')
    require(set(value)=={'predictions'} and type(rows) is list and len(rows)==5,'Five saved predictions required')
    require([r.get('target_id') for r in rows]==TARGETS,'Wrong/duplicate/reordered targets')
    for r in rows:
        require(set(r)=={'target_id','predicted_value'} and type(r['predicted_value']) is str,'Single numeric string required')
        try:number=Decimal(r['predicted_value'])
        except Exception as error:raise Unverifiable('Invalid numeric prediction') from error
        require(number.is_finite(),'Nonfinite prediction')
    return value


def awards(rows):
    require(type(rows) is list and [r.get('target_id') for r in rows]==TARGETS,'Exactly5 unique public target awards')
    require(all(type(r.get('points_awarded')) in (int,float) and r['points_awarded'] in (0,.5,1) for r in rows),'Invalid fractional award')
    return sum(r['points_awarded'] for r in rows)


def fees(bundle,round_manifest):
    snapshot=bundle.json(bundle.manifest['ledger_snapshot']);rows=snapshot['rows']
    require([r[0] for r in rows]==list(range(1,len(rows)+1)),'Noncontiguous historical ledger prefix')
    require(sha(json.dumps(rows,separators=(',',':')).encode())==snapshot['prefix_sha256'],'Ledger prefix identity mismatch')
    ledger={r[1]:r for r in rows};require(len(ledger)==len(rows),'Duplicate ledger request')
    seen=set();total=0;count=0;fallback=[]
    for run in round_manifest['physical_runs']:
        config=bundle.json(run['config']);rates=bundle.json(config['runtime'])['models'][config['model']]
        unit=lambda rate:int(Decimal(rate)*1000)
        ceiling=max(unit(rates[k]) for k in ('input','cached','write') if rates[k] is not None)
        run_cost=0
        for generation in run['generations']:
            request=bundle.json(generation['request']);response=bundle.json(generation['response'])
            identifier=request['request_id'];require(identifier not in seen,'Duplicate generation UUID')
            seen.add(identifier);require(identifier in ledger,'Missing fee row for saved generation')
            row=ledger[identifier];usage=response['usage'];inp=usage['input_tokens'];out=usage['output_tokens'];cached=usage['input_tokens_details']['cached_tokens']
            require(all(type(v) is int and v>=0 for v in (inp,out,cached)) and cached<=inp,'Invalid saved usage')
            charge=(inp-cached)*ceiling+cached*unit(rates['cached'])+out*unit(rates['output'])
            require(row[2]==request['payload']['model']==response['model']==config['model'],'Fee/model attribution mismatch')
            require(row[3]==request['reserved_nano_usd'] and row[4]==charge and row[5]=='settled','Saved cost/reservation/usage mismatch')
            require(charge<=row[3] and usage['total_tokens']==inp+out,'Charge exceeds reservation')
            run_cost+=charge;count+=1
        terminal=bundle.json(run['terminal']);saved=terminal['budget']
        require(abs(Decimal(str(saved['night_charged_upper_bound_usd']))*Decimal(10**9)-run_cost)<1,'Window cost differs from saved terminal')
        for bound in run['finalizations']:
            item=bundle.json(bound)
            require(item.get('generation_not_sent') is True and item.get('history_preserved') is True,'Invalid finalization/fallback evidence')
            fallback.append(dict(run_id=run['id'],receipt=bound,reason=item['reason']))
        total+=run_cost
    require(count==round_manifest['expected_generations'] and total==round_manifest['expected_cost_nano_usd'],'Round fee/count mismatch')
    return dict(generations=count,charged_nano_usd=total,early_finalization_receipts=fallback)


def replay_round0(bundle,manifest):
    original=bundle.json(manifest['original_manifest']);scope=bundle.json(original['split'])
    training=scope['training'];require(len(training)==25 and len(set(training))==25,'Invalid training split')
    require(not set(training)&set(scope['heldout']),'Split overlap')
    rows=[]
    for row in original['rows']:
        cik=row['cik'];require(cik in training,'Nontraining company')
        saved=bundle.json(row['predictions']);final=predictions(bundle.json(row['final_response']))
        public=bundle.json(row['public_feedback']);result=bundle.json(row['result'])
        points=awards(public['per_target'])
        require(saved==final and public['cik']==cik and result['cik']==cik,'Prediction/company substitution')
        require(result['status']=='COMPLETED_SCORED' and result['scored_targets']==5,'Unscored result cannot count as scored')
        require(points==public['score_out_of_5']==result['points'],'Company score mismatch')
        rows.append(dict(company_id=cik,points=points,targets=[dict(**p,points_awarded=a['points_awarded'])
            for p,a in zip(saved['predictions'],public['per_target'])]))
    require(len({r['company_id'] for r in rows})==len(rows),'Duplicate scored company')
    require([r['company_id'] for r in rows]==training,'Incomplete/reordered Round0 coverage')
    summary=bundle.json(manifest['summary']);total=sum(r['points'] for r in rows)
    require(total==summary['sum_points'] and total/25==summary['company_equal_mean_out_of5'],'Saved25 summary mismatch')
    failed=[]
    for failure in summary['excluded_failed_attempts']:
        result=bundle.json(failure['result']);require(result['status']=='FAILED_NO_RETRY','Failure history rewritten')
        failed.append(dict(company_id=failure['cik'],result=failure['result'],status=result['status']))
    return dict(trajectory='round0',logical_round=0,state=manifest['state'],scored=25,targets=125,
        total_points=total,company_equal_mean=total/25,rows=rows,excluded_failed_attempts=failed,
        fees=fees(bundle,manifest),selection='FIXED_HISTORICAL_COMPARATOR_NOT_EVOLVED_PARENT')


def replay_clean(bundle,manifest,baseline):
    runtime=bundle.json(manifest['runtime']);study=bundle.json(runtime['forecast_study'])
    task=bundle.json(study['clean_slate_task']);feedback=bundle.json(task['feedback'])
    require(task['mode']=='proposal' and task['frozen_candidate'] is None,'Current snapshot is not the declared fresh proposal')
    require([r['company_id'] for r in feedback['rows']]==[r['company_id'] for r in baseline['rows']],'Incomplete next-researcher feedback input')
    for original,saved in zip(baseline['rows'],feedback['rows']):
        require(saved['points']==original['points'] and saved['targets']==original['targets'],'Round0 feedback substitution')
    if manifest['state']=='PROPOSAL_REJECTED_CLOSED_NOT_A_COMPLETED_RESEARCH_ROUND':
        return rejected_proposal(bundle,manifest,runtime,task,feedback)
    require(manifest['candidate'] is None and manifest['scored']==0,'Wrong/nonexistent candidate or fabricated coverage')
    require(manifest['state']=='PROPOSAL_AT_LAUNCH_UNCLOSED_SNAPSHOT','Cannot silently mark an incomplete proposal closed')
    require(manifest['decision']=='INCOMPLETE_NO_SELECTION','Incomplete25 cannot select/adopt')
    return dict(trajectory='clean_slate',logical_round=1,physical_run_ids=manifest['physical_run_ids'],
        state=manifest['state'],candidate=None,scored=0,not_measured=25,company_equal_mean=None,
        selection='INCOMPLETE_NO_SELECTION',next_mutation_allowed=False,
        full_round0_feedback_saved_in_input=True,actual_model_receiving_verified=False,
        fees=None,unverifiable=manifest['unverifiable'],
        qualification='Prepared input is not physical model consumption; ongoing results/fees require a later immutable snapshot.')


def contains_feedback(payload,feedback):
    def visit(value):
        if isinstance(value,dict):return value==feedback or any(visit(v) for v in value.values())
        if isinstance(value,list):return any(visit(v) for v in value)
        if isinstance(value,str):
            start=value.find('{')
            if start>=0:
                try:return visit(json.JSONDecoder().raw_decode(value[start:])[0])
                except (ValueError,RecursionError):return False
        return False
    return any(visit(row.get('content')) for row in payload.get('input',[]) if row.get('role')=='user')


def rejected_proposal(bundle,manifest,runtime,task,feedback):
    result=bundle.json(manifest['result']);owner=bundle.json(manifest['owner']);audit=bundle.json(manifest['closure'])
    require(result['status']=='PROPOSAL_NOT_ACCEPTED' and result['retry_allowed'] is False,'Rejected result rewritten')
    require(owner['status']=='COMPLETED_COMPONENT_CONTEXT' and owner['error_type'] is None and owner['runtime']==manifest['runtime'], 'Missing actual original owner closure')
    require(audit['original_exec_true_exit']==0 and audit['original_exec_session']==21317,'Original exit unknown/mismatched')
    child=bundle.json(manifest['implement'])['output']['candidate'];verdict=bundle.json(manifest['source_review'])['output']
    require(child==manifest['candidate'] and child['id']==production_digest({a:child[a]['sha256'] for a in ('R','H')}),'Wrong candidate identity')
    for axis in ('R','H'):bundle.read(child[axis])
    require(child['parent']==task['scaffold']['stable_id'] and verdict['accepted_for_exploration'] is False,'Parent/review substitution')
    require(manifest['scored']==0 and manifest['frozen_candidate'] is None and manifest['decision']=='INCOMPLETE_NO_SELECTION','Rejected proposal cannot be frozen/scored/adopted')
    snapshot=bundle.json(bundle.manifest['ledger_snapshot']);ledger={r[1]:r for r in snapshot['rows']}
    seen=set();total=0;receiving={};per_role={};rates=runtime['rates']
    unit=lambda rate:int(Decimal(str(rate))*1000)
    ceiling=max(unit(rates[k]) for k in ('input','cached','write') if rates[k] is not None)
    for role in manifest['roles']:
        values=[(b,bundle.json(b)) for b in role['physical_bindings'] if b['path'].endswith('.intent.json')]
        role_total=0;reads=0
        for generation in role['generations']:
            request=bundle.json(generation['request']);response=bundle.json(generation['response']);uuid=request['request_id']
            require(uuid not in seen and uuid in ledger,'Duplicate/missing clean request UUID');seen.add(uuid)
            actual=[(b,v) for b,v in values if v.get('endpoint')=='/v1/responses' and v.get('budget_request_id')==uuid]
            require(len(actual)==1,'Unique physical generation intent required');bound,intent=actual[0]
            maximum=intent['payload']['max_output_tokens']
            require(intent['complete_reservation']==request and intent['payload']==dict(request['payload'],max_output_tokens=maximum,service_tier='default',store=False)
                and intent['request_receipt_sha256']==generation['request']['sha256'] and intent['retry_allowed'] is False,'Saved/actual HTTP request substitution')
            prefix=bound['path'].removesuffix('.intent.json')
            matches=[b for b in role['physical_bindings'] if b['path']==prefix+'.response.json']
            require(len(matches)==1 and bundle.read(matches[0])==bundle.read(generation['response']),'Physical/numbered response mismatch')
            raw=[b for b in role['physical_bindings'] if b['path']==prefix+'.raw.bin']
            require(len(raw)==1 and len(bundle.read(raw[0]))>0,'Missing opaque physical response')
            counts=[v for b,v in values if v.get('endpoint')=='/v1/responses/input_tokens' and v['payload']['input']==request['payload']['input']]
            require(bool(counts),'Missing physical input-token request')
            if role['role'] in ('controller','author'):
                require(contains_feedback(intent['payload'],feedback),'Complete125 feedback not actually sent');reads+=1
            row=ledger[uuid];usage=response['usage'];inp=usage['input_tokens'];out=usage['output_tokens'];cached=usage['input_tokens_details']['cached_tokens']
            require(all(type(v) is int and v>=0 for v in (inp,out,cached)) and cached<=inp and usage['total_tokens']==inp+out,'Invalid saved clean usage')
            charge=(inp-cached)*ceiling+cached*unit(rates['cached'])+out*unit(rates['output'])
            require(row[2]==request['payload']['model']==response['model']==rates['api_model'] and row[3]==request['reserved_nano_usd']
                and row[4]==charge and row[5]=='settled' and charge<=row[3],'Clean fee/usage/reservation mismatch')
            role_total+=charge
        total+=role_total;per_role[role['role']]=dict(generations=len(role['generations']),charged_nano_usd=role_total)
        receiving[role['role']]=reads
    require(len(seen)==manifest['expected_generations'] and total==manifest['expected_cost_nano_usd'],'Clean fee/count mismatch')
    require(owner['budget_summary']==result['budget'] and abs(Decimal(str(result['budget']['night_charged_upper_bound_usd']))*Decimal(10**9)-total)<1,'Clean terminal fee mismatch')
    return dict(trajectory='clean_slate',logical_round=1,physical_run_ids=manifest['physical_run_ids'],state=manifest['state'],
        candidate=child,scored=0,not_measured=25,company_equal_mean=None,selection='INCOMPLETE_NO_SELECTION',next_mutation_allowed=False,
        full_round0_feedback_saved_in_input=True,actual_model_receiving_verified=True,physical_full_feedback_generations=receiving,
        fees=dict(generations=len(seen),charged_nano_usd=total,per_role=per_role),source_review_accepted=False,
        original_exec_true_exit=0,unverifiable=manifest['unverifiable'])


def replay(root,expected):
    bundle=Bundle(root,expected);rounds=[bundle.json(b) for b in bundle.manifest['rounds']]
    require([r['trajectory'] for r in rounds]==['round0','clean_slate'],'Historical trajectories must remain separate')
    baseline=replay_round0(bundle,rounds[0]);clean=replay_clean(bundle,rounds[1],baseline)
    return dict(schema='edgar25_offline_replay_report_v1',manifest_sha256=expected,
        files_verified=len(bundle.manifest['files']),source_proofs_verified=len(bundle.manifest['source_proofs']),
        rounds=[baseline,clean],legacy_archive=bundle.manifest['legacy_archive'],
        limitations=bundle.manifest['limitations'],network_calls=0,model_calls=0,ledger_writes=0,
        scope='Replay saved public results/fees; no prediction, protected scorer execution or invoice certification.')


def offline_guard(root):
    roots=[Path(root).resolve(),Path(__file__).resolve().parent,Path(sys.base_prefix).resolve(),Path(sys.prefix).resolve()]
    def audit(event,args):
        if event.startswith('socket.') or event in {'subprocess.Popen','os.system','os.posix_spawn','ctypes.dlopen'}:
            raise Unverifiable('Offline replay forbids network/process/native loading')
        if event=='open':
            path,mode,flags=args
            require(not (isinstance(mode,str) and any(c in mode for c in 'wax+'))
                and not flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND),'Replay forbids writes')
            if isinstance(path,(str,bytes)):
                resolved=Path(os.fsdecode(path)).resolve()
                require(any(resolved==r or resolved.is_relative_to(r) for r in roots),'Read outside bundle/code/stdlib refused')
    sys.addaudithook(audit)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',required=True)
    parser.add_argument('--manifest-sha256',required=True,help='Trusted hash from the separately delivered Git release manifest')
    args=parser.parse_args()
    try:
        offline_guard(args.bundle)
        print(json.dumps(replay(args.bundle,args.manifest_sha256),sort_keys=True,ensure_ascii=False,indent=2))
    except (OSError,ValueError,KeyError,TypeError,ArithmeticError) as error:
        print(json.dumps(dict(status='UNVERIFIABLE',error_type=type(error).__name__,error=str(error)),ensure_ascii=False))
        sys.exit(2)
