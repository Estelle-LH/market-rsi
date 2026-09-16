"""Reconcile local receipt hashes and summarize full-day QA, never admit a source."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_rsi import digest,file_hash,fresh_json,load_json
from capture_quote_audit import SAFE_DATES,PROTECTED


def audit(root):
    root=root.resolve();report=load_json(root/'report.json');claim=load_json(root/'claim.json')
    if report['result_sha256']!=digest({k:v for k,v in report.items() if k!='result_sha256'}):
        raise ValueError('batch report hash changed')
    if report['claim_sha256']!=file_hash(root/'claim.json'):raise ValueError('claim changed')
    dates=claim['dates']
    if not dates or len(set(dates))!=len(dates) or any(d not in SAFE_DATES for d in dates):raise ValueError('invalid scope')
    if claim['protected_interval']!=list(PROTECTED):raise ValueError('protected interval changed')
    records=report['records']
    if sorted(r['date'] for r in records)!=sorted(dates):raise ValueError('missing or repeated day receipt')
    days=[];total_rows=total_cross=total_pairs=total_equal=0
    for record in records:
        path=root/('day-'+record['date']+'.json')
        if path.is_symlink() or Path(record['path'])!=path or file_hash(path)!=record['sha256']:
            raise ValueError('day path/hash mismatch')
        day=load_json(path)
        if day['date']!=record['date'] or day['status']!=record['status']:raise ValueError('day status mismatch')
        entry={'date':day['date'],'status':day['status'],'receipt_sha256':file_hash(path)}
        if day['status']=='complete_day':
            r=day['result']
            if day['result_sha256']!=digest(r) or day['source_reader_sha256']!=claim['reader_sha256']:
                raise ValueError('result/reader hash mismatch')
            if (r['date']!=day['date'] or r['source_admitted'] is not False
                or r['raw_rows_exported']!=0 or r['labels_built']!=0):
                raise ValueError('day scope expanded')
            rows=r['counts'].get('polymarket_rows',0);cross=r['counts'].get('crossed_book',0)
            pairs=r['valid_adjacent_mid_pairs'];equal=r['equal_adjacent_mid_pairs']
            if not 0<=cross<=rows or not 0<=equal<=pairs:raise ValueError('inconsistent counters')
            total_rows+=rows;total_cross+=cross;total_pairs+=pairs;total_equal+=equal
            entry.update(polymarket_quote_rows=rows,crossed_quote_rows=cross,
                crossed_fraction=cross/rows if rows else None,
                minutes_with_any_observation=r['utc_minutes_with_observations'],
                market_outcome_pairs=r['market_outcome_pairs'],
                equal_adjacent_mid_fraction=equal/pairs if pairs else None,
                source_file_sha256=r['file_sha256'],counts=r['counts'])
        days.append(entry)
    result={'schema':'capture_batch_audit_v1','batch_report_sha256':file_hash(root/'report.json'),
        'receipt_integrity_passed':True,'all_requested_days_complete':all(d['status']=='complete_day' for d in days),
        'days':days,'totals':{'polymarket_quote_rows':total_rows,'crossed_quote_rows':total_cross,
            'crossed_fraction':total_cross/total_rows if total_rows else None,
            'valid_adjacent_mid_pairs':total_pairs,'equal_adjacent_mid_pairs':total_equal,
            'equal_adjacent_mid_fraction':total_equal/total_pairs if total_pairs else None},
        'source_admitted':False,'predictive_improvement_proven':False,'fits':0,'new_test_opened':False,
        'unknown':['historical source/receive clock semantics','Gamma identity as of collection',
            'trade size units','quote validity between rows','independent sample size','quiet versus outage'],
        'limitations':['Completed scan is not QA PASS.',
            'Statistics include invalid/crossed rows; no exclusion or training mask was applied.',
            'Observation minutes are not proof of continuous capture; flat adjacent pairs may cross gaps.',
            'Synthetic ETL behavior does not establish the historical causes/frequency of errors.']}
    result['result_sha256']=digest(result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('fresh output required')
    value=audit(a.batch);a.output.parent.mkdir(parents=True,exist_ok=True);fresh_json(a.output,value)
    print({k:v for k,v in value.items() if k!='days'})
