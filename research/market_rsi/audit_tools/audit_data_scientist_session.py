"""Read-only session integrity/accounting report, not a scientific success gate."""
import argparse
from collections import Counter
from decimal import Decimal
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_rsi import digest,file_hash,fresh_json,load_json
from paid_budget import PaidBudget
from data_scientist_harness.store import Store


def audit(root,budget_path):
    root=root.resolve(); manifest=file_hash(root/'workspace.json')
    store=Store(root,manifest);store.verify()
    assessment=load_json(root/'session/assessment.json')
    if assessment.get('manifest_sha256')!=manifest:
        raise ValueError('assessment workspace mismatch')
    budget=PaidBudget(budget_path).snapshot()
    jobs={k:v for k,v in budget['jobs'].items() if k.startswith(root.name+'-turn-')}
    total=Decimal('0');uncertain=Decimal('0');turns=[]
    for job_id,job in sorted(jobs.items()):
        turn=root/'session'/('turn-'+job_id.rsplit('-turn-',1)[1])
        response=turn/'response.json'
        if response.exists():
            receipt=load_json(response)['receipt']; amount=Decimal(receipt['metered_cost_usd'])
            if job['state']!='metered_terminal' or Decimal(job['metered_usd'])!=amount:
                raise ValueError('response and append-only budget disagree')
            total+=amount
        elif job['state']=='uncertain_terminal':
            uncertain+=Decimal(job['uncertain_upper_usd'])
        else:
            raise ValueError('terminal session contains unresolved or missing metering evidence')
        turns.append({'job_id':job_id,'state':job['state'],
            'response_sha256':file_hash(response) if response.exists() else None,
            'metered_usd':job['metered_usd'],'uncertain_upper_usd':job['uncertain_upper_usd'],
            'runner_protocol_feedback':(turn/'protocol-feedback.json').exists()})
    records=store.records();counts=Counter((r['tool'],r['status']) for r in records)
    decision=root/'submitted-decision.json'
    result={'schema':'data_scientist_session_audit_v1','workspace':str(root),'manifest_sha256':manifest,
        'assessment_sha256':file_hash(root/'session/assessment.json'),
        'evidence_mode':assessment['evidence_mode'],
        'cost_scope':'synthetic counters; no provider charge' if assessment['evidence_mode']=='synthetic_transport_fixture'
                     else 'returned token quantities at frozen prices; not provider invoice',
        'integrity_and_cost_check_passed':True,'controller_valid':assessment['valid'],
        'process_reaped':assessment['process_reaped'],'harness_release':assessment['harness_release'],
        'session_metered_usd':str(total),'session_uncertain_upper_usd':str(uncertain),
        'provider_invoice_reconciled':False,'turns':turns,
        'tools':[{'tool':t,'status':s,'count':n} for (t,s),n in sorted(counts.items())],
        'fits_completed':counts['train_candidate','ok'],
        'runner_control_receipts':counts['report_protocol_error','ok'],
        'decision_sha256':file_hash(decision) if decision.exists() else None,
        'decision':load_json(decision) if decision.exists() else None,
        'new_dev_test_admitted':False,'predictive_improvement_proven':False,
        'budget_snapshot':{k:v for k,v in budget.items() if k!='jobs'}}
    result['result_sha256']=digest(result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','budget','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('fresh audit output required')
    result=audit(a.workspace,a.budget);a.output.parent.mkdir(parents=True,exist_ok=True)
    fresh_json(a.output,result)
    print({k:v for k,v in result.items() if k not in {'decision','turns','budget_snapshot'}})
