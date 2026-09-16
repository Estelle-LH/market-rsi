#!/usr/bin/env python3
"""Real-byte, local-only canary of the preserved GLM data-use proposal.

Select the first clock-overlapping file per controller-selected stream and read
at most100000 clock-eligible rows per stream. This deterministic ENGINEERING
slice is not the six-day research dataset, training admission or a scored trial.
"""
import argparse
from collections import Counter
from pathlib import Path
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from bounded_historical_ingest import verify_file
from historical_data_use_controller import assess_activity, validate_proposal
from historical_ingest_controller import _signed
from historical_materializer import GridMaterializer, clock_array, day_windows, window_mask
from historical_source_contract import CANDLE_MS, contract, project, require_causal_feature
from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json


CANARY_ROWS_PER_STREAM=100000
MAX_OUTPUT_BYTES=250000000


def inputs(ingest, controller, repair, clocks, *, all_overlaps=False):
    plan=load_json(ingest/'frozen-plan.json');_signed(plan,'plan_sha256')
    completed=load_json(ingest/'completion.json')
    if not completed['raw_acquisition_complete'] or completed['source_plan_sha256']!=plan['plan_sha256']:
        raise ValueError('complete immutable acquisition required')
    audit=load_json(repair/'audit.json');_signed(audit,'audit_sha256')
    if (audit.get('original_run')!=controller.name or audit.get('eligible_for_local_materializer_canary') is not True
            or audit.get('training_admitted') is not False):raise ValueError('specific diagnostic continuation audit required')
    for name,sha in audit['original_artifact_sha256'].items():
        if file_hash(controller/name)!=sha:raise ValueError('original controller artifact changed')
    if assess_activity(controller/'workspace')['valid'] is not True:raise ValueError('controller activity is not intact')
    proposal=load_json(controller/'workspace/frozen-data-use-proposal.json');_signed(proposal,'proposal_sha256')
    validate_proposal(proposal['plan'],controller/'workspace')
    if proposal['proposal_sha256']!=audit['proposal_sha256'] or proposal['contract_sha256']!=contract()['contract_sha256']:
        raise ValueError('proposal or source contract changed')
    feedback=load_json(controller/'workspace/quality.json')
    if feedback['source_plan_sha256']!=plan['plan_sha256']:raise ValueError('wrong acquisition lineage')
    clock_result=load_json(clocks/'result.json')
    if clock_result['source_plan_sha256']!=plan['plan_sha256'] or clock_result['failures']:
        raise ValueError('matching complete clock audit required')
    selected=[]
    streams=['polymarket_ticks_ms',*proposal['plan']['context_streams']]
    windows=day_windows(proposal['plan'],padded=True)
    for stream in streams:
        candidates=[]
        for item in plan['audit']['selected_files']:
            if item['path'].split('/')[1]!=stream:continue
            report_path=clocks/'files'/(item['path'].replace('/','__')+'.json')
            report=load_json(report_path)
            if report['sha256']!=item['lfs_sha256']:raise ValueError('clock audit source identity mismatch')
            fields=report['clock_fields']
            if stream in CANDLE_MS:
                lo=max(fields['created_at']['min_ms'],fields['candle_end']['min_ms']+1)
                hi=max(fields['created_at']['max_ms'],fields['candle_end']['max_ms']+1)
            else:
                field='ingest_ts_ms' if stream=='polymarket_ticks_ms' else 'received_at'
                lo,hi=fields[field]['min_ms'],fields[field]['max_ms']
            if any(hi>=a and lo<b for a,b in windows):
                candidates.append({'item':item,'clock_report_sha256':file_hash(report_path),
                                   'min_possible_available_ms':lo,'max_possible_available_ms':hi})
        if not candidates:raise ValueError('no source file intersects chosen controller dates for '+stream)
        ordered=sorted(candidates,key=lambda v:v['item']['path'])
        selected.extend(ordered if all_overlaps else ordered[:1])
    meta=next(i for i in plan['audit']['selected_files'] if i['path'].split('/')[1]=='market_meta')
    return plan,proposal,selected,meta


def run(ingest, controller, repair, clocks, output):
    identifier(output.name)
    if output.exists():raise ValueError('canary run ID already claimed')
    plan,proposal,selected,meta=inputs(ingest,controller,repair,clocks)
    meta_path=ingest/'raw'/meta['path'];verify_file(meta_path,meta)
    metadata=pq.ParquetFile(meta_path).read(columns=['market_slug','up_token_id','down_token_id']).to_pylist()
    grid=GridMaterializer(proposal['plan'],metadata)
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    source_paths=[Path(__file__),Path(__file__).with_name('historical_materializer.py'),
                  Path(__file__).with_name('historical_source_contract.py')]
    claim={'schema':'historical_materializer_canary_claim_v1','started_unix_ns':time.time_ns(),
           'source_plan_sha256':plan['plan_sha256'],'proposal_sha256':proposal['proposal_sha256'],
           'repair_audit_sha256':file_hash(repair/'audit.json'),'selected_files':selected,'metadata':meta,
           'source_hashes':{p.name:file_hash(p) for p in source_paths},
           'slice_rule':'first_lexicographic_clock_overlapping_file_per_stream_first100000_clock_eligible_rows',
           'max_rows_per_stream':CANARY_ROWS_PER_STREAM,'max_output_bytes':MAX_OUTPUT_BYTES,
           'full_six_day_dataset_built':False,'no_paid_calls':True,'new_download_bytes':0,'training_admitted':False}
    fresh_json(output/'claim.json',claim)
    receipts=[];future_reads_blocked=0
    for selection in selected:
        item=selection['item'];stream=item['path'].split('/')[1];path=ingest/'raw'/item['path']
        verify_file(path,item);pf=pq.ParquetFile(path);seen=selected_count=0;probe=None
        for batch in pf.iter_batches(batch_size=100000):
            table=pa.Table.from_batches([batch]);arrivals=clock_array(table,stream)
            keep=np.flatnonzero(window_mask(arrivals,grid.padded_windows))[:CANARY_ROWS_PER_STREAM-selected_count]
            if len(keep):
                accepted=table.take(pa.array(keep))
                if probe is None:probe=(accepted.slice(0,1).to_pylist()[0],int(seen+keep[0]))
                grid.consume(accepted,item,raw_ordinals=seen+keep)
                selected_count+=len(keep)
            seen+=table.num_rows
            if selected_count>=CANARY_ROWS_PER_STREAM:break
        verify_file(path,item)
        if not selected_count:raise ValueError('selected canary file contains no clock-eligible rows')
        projected=project(probe[0],item,probe[1],metadata=grid.metadata)
        try:
            require_causal_feature(projected,'not_an_alias',projected['recorded_available_ms']-1,
                max_age_ms=proposal['plan']['max_age_ms'],clock_assumption=proposal['plan']['clock_assumption'])
        except ValueError as exc:
            if 'not yet available' not in str(exc):raise
            future_reads_blocked+=1
        else:raise ValueError('future observation was exposed')
        receipt={'path':item['path'],'source_sha256':item['lfs_sha256'],'rows_in_source_file':pf.metadata.num_rows,
                 'raw_rows_scanned':seen,'clock_eligible_rows_used':selected_count,
                 'all_file_rows_consumed':seen==pf.metadata.num_rows and selected_count<CANARY_ROWS_PER_STREAM}
        receipts.append(receipt);fresh_json(output/(stream+'-receipt.json'),receipt)
        print(canonical({'stage':'canary_source_consumed','stream':stream,'rows':selected_count,
                         'state_nodes':len(grid.nodes)}),flush=True)
    reasons=Counter();nonempty=Counter();row_count=byte_count=0;last=None
    row_path=output/'diagnostic-states.jsonl'
    with row_path.open('x',encoding='utf-8') as out:
        for row in grid.rows():
            for stream,observation in row['observations'].items():
                reasons[stream+':'+observation['reason']]+=1
                if observation['values']:
                    nonempty[stream]+=1
                    if observation['available_ms']>row['decision_ms']:raise ValueError('future-state invariant failed')
            payload=canonical(row)+'\n';size=len(payload.encode())
            if byte_count+size>MAX_OUTPUT_BYTES:raise ValueError('output byte cap; partial remains, no completion')
            out.write(payload);byte_count+=size;row_count+=1
    if not row_count:raise ValueError('no grid rows; preserve diagnostic failure')
    if any(file_hash(p)!=claim['source_hashes'][p.name] for p in source_paths):raise ValueError('source changed while canary running')
    verify_file(meta_path,meta)
    result={**grid.summary(),'schema':'historical_materializer_canary_v1','mechanical_canary_pass':True,
            'row_count':row_count,'output_bytes':byte_count,'rows_sha256':file_hash(row_path),
            'source_receipts':receipts,'observation_reason_counts':dict(reasons),
            'nonempty_observation_counts':dict(nonempty),'premature_reads_blocked':future_reads_blocked,
            'full_six_day_dataset_built':False,'fit_started':False,'formal_evaluation':False,
            'no_paid_calls':True,'new_download_bytes':0,'proposal_sha256':proposal['proposal_sha256'],
            'limitations':['engineering_slice_not_representative','retrospective_observed_interval_not_tradable_universe',
                           'rolling_feature_windows_not_selected','not_training_admitted','source_clock_is_publisher_proxy']}
    result['result_sha256']=digest(result);fresh_json(output/'result.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['ingest','controller','repair','clocks','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    try:
        result=run(a.ingest,a.controller,a.repair,a.clocks,a.output)
        print(canonical({k:result[k] for k in ['mechanical_canary_pass','row_count','nonempty_observation_counts','result_sha256']}))
    except Exception as exc:
        if a.output.is_dir() and (a.output/'claim.json').exists() and not (a.output/'failure.json').exists():
            fresh_json(a.output/'failure.json',{'error_type':type(exc).__name__,'error':str(exc),
                       'training_admitted':False,'no_paid_calls':True})
        raise
