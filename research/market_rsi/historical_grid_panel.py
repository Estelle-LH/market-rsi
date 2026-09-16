"""Stream the audited, unchanged open-Train grid into compact objective inputs.

No target, horizon, row weights, Dev, fit or model call is selected here. The
panel retains every grid row and uses NaN for unavailable quotes. Raw sources
and the full observation/annotation records remain authoritative and unchanged.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path

import numpy as np

from historical_grid_objectives import GridPanel
from historical_ingest_controller import _signed
from historical_phase_annotations import annotate, require_same_sampling
from historical_source_contract import CLOCK_ASSUMPTION
from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json


def bounded_rows(path, max_bytes):
    total=0
    with gzip.open(path,'rb') as source:
        while True:
            line=source.readline(1048577)
            if not line:break
            total+=len(line)
            if len(line)>1048576 or total>max_bytes:
                raise ValueError('bounded uncompressed observation stream exceeded')
            yield json.loads(line)


def panel_from_rows(rows, annotations, plan, expected_count):
    """Identity-aligned streaming projection; no implicit row selection or fill."""
    if type(expected_count) is not int or not 0<expected_count<=500000:
        raise ValueError('bounded complete row count required')
    if (plan['clock_assumption']!=CLOCK_ASSUMPTION or plan['primary_observation']!='pm_reported_bbo'
            or plan['market_time_scope']!='observed_arrival_interval'):
        raise ValueError('only the explicit recorded-arrival observation contract is supported')
    codes={};seen=set();dates=Counter();phases=Counter();reasons=Counter()
    entity=np.zeros(expected_count,dtype=np.int64)
    when=np.zeros(expected_count,dtype=np.int64)
    midpoint=np.full(expected_count,np.nan);age=np.full(expected_count,np.nan)
    day=np.empty(expected_count,dtype='U10');phase=np.empty(expected_count,dtype='U21')
    row_ids=np.empty(expected_count,dtype='U64')
    count=0
    for i,(row,annotation) in enumerate(zip(rows,annotations,strict=True)):
        if i>=expected_count:raise ValueError('actual rows exceed committed count; never truncate')
        timestamp=row['decision_ms']
        if type(timestamp) is not int:raise ValueError('integer source grid time required')
        expected_id=digest({k:row[k] for k in ['market_slug','asset_id','decision_ms']})
        if row['row_id']!=expected_id or row['row_id'] in seen:
            raise ValueError('source row identity mismatch or duplicate')
        if annotation!=annotate(row):raise ValueError('annotation is not aligned with exact current observation')
        if row.get('target') is not None or row.get('training_admitted') is not False:
            raise ValueError('unlabelled diagnostic source required')
        actual_day=datetime.fromtimestamp(timestamp/1000,timezone.utc).date().isoformat()
        if actual_day!=row['utc_date'] or actual_day not in plan['open_train_utc_dates']:
            raise ValueError('row is outside the controller-selected open Train dates')
        pair=(row['market_slug'],row['asset_id'])
        if any(not isinstance(value,str) or not value for value in pair):
            raise ValueError('complete market/token entity identity required')
        code=codes.setdefault(pair,len(codes));obs=row['observations']['polymarket_ticks_ms']
        values=obs['values'];reason=obs['reason']
        if values:
            if reason!='recorded_source_only_not_execution_proof':
                raise ValueError('invalid or stale source cannot supply a finite quote')
            bid,ask,mid=[values[k] for k in ['reported_bid','reported_ask','midpoint_from_reported_bbo']]
            if (any(type(v) not in (int,float) or not math.isfinite(v) for v in [bid,ask,mid])
                    or not 0<=bid<=ask<=1 or not math.isclose(mid,(bid+ask)/2,rel_tol=0,abs_tol=1e-12)):
                raise ValueError('quote midpoint must derive from co-reported valid bid and ask')
            arrival=obs.get('available_ms');event_age=obs.get('max_source_age_ms')
            if type(arrival) is not int or type(event_age) is not int or arrival>timestamp or event_age<0:
                raise ValueError('finite quote needs causal arrival and event ages')
            # Both clocks matter; a recent receipt must not refresh an old event.
            maximum_age=max(timestamp-arrival,event_age)
            if maximum_age>plan['max_age_ms']:raise ValueError('source quote exceeds controller staleness limit')
            midpoint[i]=mid;age[i]=maximum_age
        elif reason=='recorded_source_only_not_execution_proof':
            raise ValueError('available observation cannot omit quote values')
        entity[i]=code;when[i]=timestamp;day[i]=actual_day;phase[i]=annotation['nominal_phase'];row_ids[i]=row['row_id']
        seen.add(row['row_id']);dates[actual_day]+=1;phases[annotation['nominal_phase']]+=1;reasons[reason]+=1
        count=i+1
    if count!=expected_count:raise ValueError('incomplete grid/sidecar; no partial panel')
    panel=GridPanel(entity,when,midpoint,age,day,phase,plan['cadence_ms'],plan['max_age_ms'])
    panel.validate()
    return panel,row_ids,{'rows':count,'entities':len(codes),'by_open_train_date':dict(dates),
        'by_nominal_phase':dict(phases),'quote_reasons':dict(reasons),
        'finite_midpoint_rows':int(np.isfinite(midpoint).sum()),
        'entity_mapping':[{'entity_code':code,'market_slug':pair[0],'asset_id':pair[1]} for pair,code in codes.items()]}


def load_audited_panel(materialized, annotations, source_audit, controller, original_controller):
    paths={'materialization':materialized/'result.json','annotations':annotations/'result.json',
        'audit':source_audit/'audit.json','proposal':controller/'workspace/frozen-data-use-proposal.json',
        'old_proposal':original_controller/'workspace/frozen-data-use-proposal.json',
        'assessment':controller/'session/assessment.json','annotation_claim':annotations/'claim.json',
        'observations':materialized/'diagnostic-states.jsonl.gz','sidecar':annotations/'annotations.jsonl.gz'}
    before={key:file_hash(path) for key,path in paths.items()}
    values={key:load_json(path) for key,path in paths.items() if key not in ['observations','sidecar']}
    for key,field in [('materialization','result_sha256'),('annotations','result_sha256'),
                      ('audit','audit_sha256'),('proposal','proposal_sha256'),('old_proposal','proposal_sha256')]:
        _signed(values[key],field)
    result,side,audit=values['materialization'],values['annotations'],values['audit']
    proposal,old,claim=values['proposal'],values['old_proposal'],values['annotation_claim']
    if (result.get('full_six_day_dataset_built') is not True or result.get('source_scan_complete') is not True
            or side.get('complete') is not True or audit.get('audit_pass') is not True
            or values['assessment'].get('valid') is not True):raise ValueError('complete audited source and valid controller required')
    require_same_sampling(old,proposal)
    if (result['rows_sha256']!=before['observations'] or side['annotation_rows_sha256']!=before['sidecar']
            or side['original_observations_sha256']!=before['observations']
            or audit['materialization_result_sha256']!=before['materialization']
            or result['proposal_sha256']!=old['proposal_sha256']
            or side['proposal_sha256']!=proposal['proposal_sha256']
            or claim['controller_assessment_sha256']!=before['assessment']
            or claim['source_audit_sha256']!=before['audit']
            or claim['source_rows_sha256']!=before['observations']
            or claim['controller_proposal_sha256']!=proposal['proposal_sha256']
            or claim['original_proposal_sha256']!=old['proposal_sha256']
            or result['row_count']!=side['row_count']):raise ValueError('source and controller lineage hash mismatch')
    panel,ids,summary=panel_from_rows(bounded_rows(paths['observations'],1500000000),
        bounded_rows(paths['sidecar'],750000000),proposal['plan'],result['row_count'])
    if (summary['by_nominal_phase']!=side['phase_counts'] or summary['by_nominal_phase']!=audit['nominal_scope_counts']
            or summary['by_open_train_date']!=result['grid_rows_by_date']
            or summary['finite_midpoint_rows']!=result['nonempty_observation_counts']['polymarket_ticks_ms']):
        raise ValueError('full population conservation failed')
    if before!={key:file_hash(path) for key,path in paths.items()}:
        raise ValueError('input changed during panel construction')
    return panel,ids,summary,before


def run(materialized,annotations,source_audit,controller,original_controller,output):
    identifier(output.name);output.mkdir(parents=True,exist_ok=False,mode=0o700)
    modules=[Path(__file__),Path(__file__).with_name('historical_grid_objectives.py')]
    source_hashes={path.name:file_hash(path) for path in modules}
    fresh_json(output/'claim.json',{'schema':'historical_grid_panel_claim_v1','code_hashes':source_hashes,
        'inputs':{k:str(v.absolute()) for k,v in dict(materialized=materialized,annotations=annotations,
            source_audit=source_audit,controller=controller,original_controller=original_controller).items()},
        'target_selected':False,'new_paid_or_download_calls':0})
    panel,ids,summary,inputs=load_audited_panel(materialized,annotations,source_audit,controller,original_controller)
    target=output/'unlabelled-grid.npz'
    with target.open('xb') as handle:
        np.savez_compressed(handle,entity=panel.entity,time_ms=panel.time_ms,midpoint=panel.midpoint,
            quote_age_ms=panel.quote_age_ms,date=panel.date,phase=panel.phase,row_id=ids,
            cadence_ms=np.array(panel.cadence_ms),max_age_ms=np.array(panel.max_age_ms))
    if source_hashes!={path.name:file_hash(path) for path in modules}:
        raise ValueError('loader source changed while running')
    final={'schema':'historical_unlabelled_grid_panel_v1','complete':True,'summary':summary,
        'input_hashes':inputs,'panel_sha256':file_hash(target),'stored_bytes':target.stat().st_size,
        'code_hashes':source_hashes,'all_grid_rows_retained':True,'training_admitted':False,
        'target_selected':False,'target_computed':False,'fresh_holdout':False,
        'quote_execution_verified':False,'new_paid_or_download_calls':0}
    final['result_sha256']=digest(final);fresh_json(output/'result.json',final)
    return {k:final[k] for k in ['complete','stored_bytes','result_sha256','target_computed']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['materialized','annotations','source-audit','controller','original-controller','output']:
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();print(canonical(run(**vars(args))))
