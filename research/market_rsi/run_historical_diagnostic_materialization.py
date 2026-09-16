#!/usr/bin/env python3
"""Apply the tested grid to all controller-selected open-Train dates, no fitting.

Requires the separately preserved first proposal, terminal-bug audit and a passing
local real-byte canary. This is diagnostic source processing, NOT retroactive
acceptance of the original controller session or admission to a formal experiment.
"""
import argparse
from collections import Counter
from pathlib import Path
import time

import pyarrow.parquet as pq

from bounded_historical_ingest import verify_file
from bounded_compressed_rows import CompressedRows
from historical_ingest_controller import _signed
from historical_materializer import GridMaterializer
from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json
from run_historical_materializer_canary import inputs, MAX_OUTPUT_BYTES


MAX_LOGICAL_OUTPUT_BYTES=1500000000


def require_canary(canary, proposal):
    result=load_json(canary/'result.json');_signed(result,'result_sha256')
    claim=load_json(canary/'claim.json')
    if (result.get('mechanical_canary_pass') is not True or result.get('training_admitted') is not False
            or result['proposal_sha256']!=proposal['proposal_sha256']
            or claim['proposal_sha256']!=proposal['proposal_sha256']
            or file_hash(canary/'diagnostic-states.jsonl')!=result['rows_sha256']):
        raise ValueError('intact matching diagnostic materializer canary required')
    for name in ['historical_materializer.py','historical_source_contract.py']:
        if file_hash(Path(__file__).with_name(name))!=claim['source_hashes'][name]:
            raise ValueError('tested causal core changed; requires new canary')
    return result


def run(ingest, controller, repair, clocks, canary, output, *, prior_storage_failure=None):
    identifier(output.name)
    if output.exists():raise ValueError('permanent materialization run ID already claimed')
    plan,proposal,selected,meta=inputs(ingest,controller,repair,clocks,all_overlaps=True)
    require_canary(canary,proposal)
    meta_path=ingest/'raw'/meta['path'];verify_file(meta_path,meta)
    metadata=pq.ParquetFile(meta_path).read(columns=['market_slug','up_token_id','down_token_id']).to_pylist()
    grid=GridMaterializer(proposal['plan'],metadata)
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    sources=[Path(__file__).with_name(n) for n in ['historical_materializer.py','historical_source_contract.py','bounded_compressed_rows.py',
        'run_historical_materializer_canary.py','run_historical_diagnostic_materialization.py']]
    claim={'schema':'historical_diagnostic_materialization_claim_v1','started_unix_ns':time.time_ns(),
        'source_plan_sha256':plan['plan_sha256'],'proposal_sha256':proposal['proposal_sha256'],
        'repair_audit_sha256':file_hash(repair/'audit.json'),'canary_result_sha256':file_hash(canary/'result.json'),
        'selected_files':selected,'metadata':meta,'source_hashes':{p.name:file_hash(p) for p in sources},
        'source_policy':'all_selected_stream_files_with_recorded_time_bounds_overlapping_controller_dates_plus_causal_warmup',
        'retrospective_observed_intervals':True,'batch_rows':100000,'max_stored_output_bytes':MAX_OUTPUT_BYTES,
        'max_logical_output_bytes':MAX_LOGICAL_OUTPUT_BYTES,'output_format':'gzip_canonical_jsonl_lossless',
        'original_controller_session_valid':False,'local_diagnostic_continuation_only':True,
        'no_paid_calls':True,'new_download_bytes':0,'training_admitted':False}
    fresh_json(output/'claim.json',claim)
    if prior_storage_failure is not None:
        prior=load_json(prior_storage_failure/'claim.json')
        failure=load_json(prior_storage_failure/'failure.json')
        if (failure.get('error')!='output byte cap; preserve partial, no completion'
                or (prior_storage_failure/'result.json').exists()
                or prior['proposal_sha256']!=proposal['proposal_sha256']
                or prior['selected_files']!=selected
                or prior['source_hashes']['historical_materializer.py']!=claim['source_hashes']['historical_materializer.py']
                or prior['source_hashes']['historical_source_contract.py']!=claim['source_hashes']['historical_source_contract.py']):
            raise ValueError('storage-only continuation must preserve the exact proposal, sources and causal core')
        fresh_json(output/'storage-adaptation.json',{'prior_run':prior_storage_failure.name,
            'prior_claim_sha256':file_hash(prior_storage_failure/'claim.json'),
            'prior_failure_sha256':file_hash(prior_storage_failure/'failure.json'),
            'prior_partial_sha256':file_hash(prior_storage_failure/'diagnostic-states.jsonl'),
            'change':'lossless_gzip_only_same_rows_and_core','prior_session_restarted':False,
            'new_model_or_download':False,'prior_artifacts_unchanged':True,
            'max_stored_bytes_unchanged':MAX_OUTPUT_BYTES,'new_max_logical_bytes':MAX_LOGICAL_OUTPUT_BYTES})
    (output/'receipts').mkdir()
    receipts=[]
    for i,selection in enumerate(selected):
        item=selection['item'];path=ingest/'raw'/item['path'];verify_file(path,item)
        pf=pq.ParquetFile(path);seen=0
        before=dict(grid.counts)
        for batch in pf.iter_batches(batch_size=100000):
            grid.consume(batch,item,seen);seen+=batch.num_rows
        if seen!=pf.metadata.num_rows:raise ValueError('full-source scan row conservation failed')
        verify_file(path,item)
        receipt={'path':item['path'],'source_sha256':item['lfs_sha256'],'full_source_rows_scanned':seen,
            'counter_deltas':{k:v-before.get(k,0) for k,v in grid.counts.items() if v!=before.get(k,0)}}
        receipts.append(receipt)
        fresh_json(output/'receipts'/(item['path'].replace('/','__')+'.json'),receipt)
        print(canonical({'stage':'source_materialized','files':i+1,'total_files':len(selected),
                         'full_source_rows_scanned':seen,'retained_state_nodes':len(grid.nodes)}),flush=True)
    counts=Counter();reasons=Counter();nonnull=Counter();rows=byte_count=0
    by_date={};first=last=None
    row_path=output/'diagnostic-states.jsonl.gz'
    with CompressedRows(row_path,max_logical_bytes=MAX_LOGICAL_OUTPUT_BYTES,max_stored_bytes=MAX_OUTPUT_BYTES) as out:
        for row in grid.rows():
            day=row['utc_date'];counts[day]+=1
            for stream,obs in row['observations'].items():
                reasons[stream+':'+obs['reason']]+=1
                if obs['values']:
                    if obs['available_ms']>row['decision_ms']:raise ValueError('future observation invariant failed')
                    nonnull[stream]+=1
                    by_date.setdefault(day,Counter())[stream]+=1
            out.write_row(row);rows+=1
        byte_count=out.logical
    if not rows:raise ValueError('zero grid rows; preserve diagnostic failure')
    if any(file_hash(p)!=claim['source_hashes'][p.name] for p in sources):raise ValueError('loaded source changed while running')
    verify_file(meta_path,meta)
    result={**grid.summary(),'schema':'historical_diagnostic_materialization_v1','source_scan_complete':True,
        'proposal_sha256':proposal['proposal_sha256'],'row_count':rows,'logical_output_bytes':byte_count,
        'stored_output_bytes':row_path.stat().st_size,'output_format':'gzip_canonical_jsonl_lossless',
        'rows_sha256':file_hash(row_path),'all_source_receipts':receipts,
        'controller_requested_utc_dates':proposal['plan']['open_train_utc_dates'],
        'grid_rows_by_date':dict(counts),'nonempty_observation_counts':dict(nonnull),
        'nonempty_observations_by_date':{k:dict(v) for k,v in by_date.items()},
        'observation_reason_counts':dict(reasons),'fit_started':False,'formal_evaluation':False,
        'new_download_bytes':0,'no_paid_calls':True,'raw_bytes_unchanged':True,
        'full_six_day_dataset_built':len(counts)==len(proposal['plan']['open_train_utc_dates']),
        'limitations':['diagnostic_only_not_formal_experiment','no_target_or_rolling_feature_windows_selected',
            'coverage_biased_six_day_open_train_sample','missing_states_preserved_not_imputed',
            'retrospective_observed_interval_universe_not_exchange_executability','original_terminal_failure_not_erased']}
    result['result_sha256']=digest(result);fresh_json(output/'result.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['ingest','controller','repair','clocks','canary','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--prior-storage-failure',type=Path)
    a=p.parse_args()
    try:
        r=run(a.ingest,a.controller,a.repair,a.clocks,a.canary,a.output,prior_storage_failure=a.prior_storage_failure)
        print(canonical({k:r[k] for k in ['source_scan_complete','row_count','grid_rows_by_date','nonempty_observation_counts','result_sha256']}))
    except Exception as exc:
        if a.output.is_dir() and (a.output/'claim.json').exists() and not (a.output/'failure.json').exists():
            fresh_json(a.output/'failure.json',{'error_type':type(exc).__name__,'error':str(exc),'training_admitted':False})
        raise
