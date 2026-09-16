"""Read-only failed source-session handoff; never execute or resume old code."""
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
from market_rsi import digest, file_hash, load_json
from archived_source_session import hashed, enclosed


def verify(root, audit_path, budget, pins):
    root=Path(root).resolve()
    c=load_json(hashed(root/'workspace.json',pins['manifest']))
    if (c['schema']!='data_scientist_workspace_v1' or c['purpose']!='source_research'
            or c['inputs_present'] is not False or c['allowed_train_dates']!=[]
            or c['formal_evaluation_allowed'] is not False or c['paid_execution_tools'] is not False
            or c['session_id']!=root.name): raise ValueError('source-only history required')
    release=c['release']
    if (release['release_sha256']!=pins['release']
            or digest({k:v for k,v in release.items() if k!='release_sha256'})!=pins['release']
            or release['harness_version']!=c['harness_version'] or release['runtime']!=c['runtime']
            or release['harness_change_origin']!=c['harness_change_origin']
            or c['harness_change_origin']!='human_directed_engineering'
            or release['publication']['origin']!='https://github.com/Estelle-LH/RSIBench-Data.git'):
        raise ValueError('historical release differs')
    sources={}
    for name,sha in c['files'].items():
        p=hashed(enclosed(root,name),sha)
        if p.is_relative_to(root/'code'):sources[str(p.relative_to(root/'code'))]=sha
        elif p not in (root/'findings.json',root/'archive-input.json'):
            raise ValueError('unexpected historical input')
    if sources!=release['source_hashes']:raise ValueError('historical source set differs')
    a=load_json(audit_path)
    if (a['result_sha256']!=pins['audit'] or digest({k:v for k,v in a.items() if k!='result_sha256'})!=pins['audit']
            or a['manifest_sha256']!=pins['manifest'] or a['workspace']!=str(root)
            or not a['integrity_and_cost_check_passed'] or a['controller_valid'] is not False
            or a['process_reaped'] is not True or a['fits_completed']!=0 or a['decision_sha256'] is not None):
        raise ValueError('exact terminal failed audit required')
    assessment=load_json(hashed(root/'session/assessment.json',a['assessment_sha256']))
    if (assessment['valid'] is not False or not assessment['process_reaped'] or assessment['exit_code']==0
            or assessment['source_hashes']!=sources or assessment['manifest_sha256']!=pins['manifest']
            or assessment['harness_release']!=a['harness_release']
            or assessment['harness_release']['release_sha256']!=pins['release']):
        raise ValueError('failed assessment differs')
    if any((root/p).exists() for p in ('submitted-decision.json','source-study-proposal.json','trials')):
        raise ValueError('unexpected scientific output in failed history')
    records=[];previous=None
    for n,line in enumerate((root/'activity.jsonl').read_text().splitlines(),1):
        e=json.loads(line);p=root/'records'/f'{n:04d}.json'
        if (e['previous']!=previous or e['sequence']!=n or e['record']['path']!=str(p)
                or digest({k:v for k,v in e.items() if k!='record_sha256'})!=e['record_sha256']):
            raise ValueError('historical event chain differs')
        r=load_json(hashed(p,e['record']['sha256']))
        if r['tool']!=e['tool'] or r['harness_release']!=a['harness_release']:
            raise ValueError('historical tool identity differs')
        records.append(r);previous=e['record_sha256']
    counts=Counter((r['tool'],r['status']) for r in records)
    if (a['tools']!=[{'tool':t,'status':s,'count':n} for (t,s),n in sorted(counts.items())]
            or any(r['tool'] in ('train_candidate','submit_research_decision') for r in records)):
        raise ValueError('historical scientific actions differ')
    jobs={k:v for k,v in budget['jobs'].items() if k.startswith(root.name+'-turn-')}
    if set(jobs)!={t['job_id'] for t in a['turns']}:raise ValueError('historical job set differs')
    metered=Decimal(0);uncertain=Decimal(0)
    for t in a['turns']:
        job=jobs[t['job_id']]; p=root/'session'/('turn-'+t['job_id'].rsplit('-turn-',1)[1])/'response.json'
        if job['state']!=t['state']:raise ValueError('historical accounting state differs')
        if t['state']=='metered_terminal':
            reply=load_json(hashed(p,t['response_sha256'])); amount=Decimal(reply['receipt']['metered_cost_usd'])
            if amount!=Decimal(job['metered_usd']) or amount!=Decimal(t['metered_usd']):raise ValueError('meter differs')
            metered+=amount
        elif t['state']=='uncertain_terminal':
            if p.exists() or t['response_sha256'] is not None:raise ValueError('new receipt needs reconciliation first')
            if Decimal(job['uncertain_upper_usd'])!=Decimal(t['uncertain_upper_usd']):raise ValueError('uncertain bound differs')
            uncertain+=Decimal(t['uncertain_upper_usd'])
        else:raise ValueError('unresolved historical paid job')
    if metered!=Decimal(a['session_metered_usd']) or uncertain!=Decimal(a['session_uncertain_upper_usd']):
        raise ValueError('historical totals differ')
    archives=load_json(root/'archive-input.json')['prior_rounds']
    for archive in archives:
        ref=archive['origin'];body=load_json(hashed(Path(ref['path']),ref['sha256']))
        if body!=archive['history_not_current_evidence']:raise ValueError('inherited archive differs')
    return {'config':c,'records':records,'archives':[v['origin'] for v in archives],
        'receipt':{'schema':'failed_source_history_verified_v1','pins':pins,'parent':str(root),
            'frozen_files_verified':len(c['files']),'tool_records_verified':len(records),
            'provider_turns_verified':len(jobs),'metered_usd':str(metered),'uncertain_upper_usd':str(uncertain),
            'old_workspace_modified':False,'old_code_executed':False,'failure_reclassified_as_success':False}}
