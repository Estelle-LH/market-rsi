"""Check the additive adapter on exact prior physical rows; no new labels/fits."""
import argparse
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import sys

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from historical_direction_fields import (DOWN, MAKER, MAPPING_ASSUMPTION, QUOTE_VOLUME,
    UP, direction_contract, project_reported_orientation, project_reported_trade, require_reported_direction)
from historical_source_contract import CLOCK_ASSUMPTION, physical_reference
from market_rsi import canonical, digest, file_hash, fresh_json, load_json


def physical_rows(path, ordinals, columns):
    """Read only referenced ordinals, preserving the file's row-group order."""
    pf=pq.ParquetFile(path); wanted=np.array(sorted(set(ordinals)),dtype=np.int64)
    if not len(wanted) or wanted[0]<0 or wanted[-1]>=pf.metadata.num_rows:
        raise ValueError('nonempty in-range physical ordinals required')
    found={};start=0
    for group in range(pf.num_row_groups):
        end=start+pf.metadata.row_group(group).num_rows
        chosen=wanted[(wanted>=start)&(wanted<end)]
        if len(chosen):
            offset=start
            for batch in pf.iter_batches(batch_size=16384,row_groups=[group],columns=columns):
                take=chosen[(chosen>=offset)&(chosen<offset+batch.num_rows)]
                if len(take):
                    rows=batch.take(pa.array(take-offset)).to_pylist()
                    found.update(zip(map(int,take),rows,strict=True))
                offset+=batch.num_rows
            if offset!=end:raise ValueError('physical row-group size changed')
        start=end
    if set(found)!=set(map(int,wanted)):raise ValueError('physical reference retrieval incomplete')
    return found


def run(ingest, materialized, provenance, output):
    material=load_json(materialized/'result.json'); claim=load_json(materialized/'claim.json')
    evidence=load_json(provenance/'provenance.json')
    for value in (material,evidence):
        if value['result_sha256']!=digest({k:v for k,v in value.items() if k!='result_sha256'}):
            raise ValueError('signed source evidence changed')
    if evidence['direction_contract']!=direction_contract():raise ValueError('semantic evidence changed')
    for source in evidence['files']:
        if file_hash(Path(source['local_path']))!=source['sha256']:raise ValueError('pinned publisher source changed')
    path=materialized/'diagnostic-states.jsonl.gz'
    if file_hash(path)!=material['rows_sha256']:raise ValueError('prior observations changed')
    output.mkdir(parents=True,exist_ok=False)
    code={str(p.resolve()):file_hash(p) for p in (Path(__file__),
        Path(__file__).parents[1]/'historical_direction_fields.py',
        Path(__file__).parents[1]/'historical_source_contract.py')}
    fresh_json(output/'claim.json',{'code_hashes':code,'material_result_sha256':material['result_sha256'],
        'provenance_sha256':file_hash(provenance/'provenance.json'),
        'sampling':'first 32 existing panel rows per already-open date, regardless of price or target',
        'model_calls':0,'new_label_reads':0,'raw_mutation':False})
    counts=Counter();sample=[];n=0
    with gzip.open(path,'rt') as stream:
        for line in stream:
            row=json.loads(line);n+=1; day=row['utc_date']
            if row['target'] is not None or day not in material['controller_requested_utc_dates']:
                raise ValueError('only prior unlabelled opened-Train observations allowed')
            if counts[day]<32:sample.append(row);counts[day]+=1
    if n!=material['row_count']:raise ValueError('original population changed')
    wanted=defaultdict(dict); receipts={r['path']:r['source_sha256'] for r in material['all_source_receipts']}
    for row in sample:
        for stream in ('binance_trades','polymarket_ticks_ms'):
            for ref in row['observations'][stream]['sources']:
                item={'path':ref['relative_path'],'lfs_sha256':ref['sha256']}
                if (receipts.get(item['path'])!=item['lfs_sha256']
                        or physical_reference(item,ref['raw_row_ordinal'])!=ref):
                    raise ValueError('physical reference not bound to original materialization')
                wanted[item['path']][ref['raw_row_ordinal']]=ref
    if sum(map(len,wanted.values()))>10000:raise ValueError('bounded physical-row canary required')
    raw=ingest/'raw';selected={};hashes={}
    columns={'binance_trades':['trade_id','trade_time','received_at','price','quantity','quote_volume','is_buyer_maker'],
        'polymarket_ticks_ms':['id','source_ts_ms','ingest_ts_ms','market_slug','asset_id','side_label',
                               'event_type','best_bid','best_ask','price','size']}
    for relative, refs in wanted.items():
        p=raw/relative; expected=receipts[relative]
        if file_hash(p)!=expected:raise ValueError('raw source changed before canary')
        selected[relative]=physical_rows(p,refs,columns[Path(relative).parts[1]])
        hashes[str(p.resolve())]=expected
    meta=claim['metadata'];meta_path=raw/meta['path']
    if file_hash(meta_path)!=meta['lfs_sha256']:raise ValueError('metadata source changed')
    hashes[str(meta_path.resolve())]=meta['lfs_sha256']
    rows=pq.ParquetFile(meta_path).read(columns=['market_slug','up_token_id','down_token_id','first_seen_ms']).to_pylist()
    metadata={r['market_slug']:(i,r) for i,r in enumerate(rows)}
    if len(metadata)!=len(rows):raise ValueError('ambiguous duplicate market metadata')
    results=[];status=Counter(); negatives=Counter()
    for row in sample:
        for stream in ('binance_trades','polymarket_ticks_ms'):
            for ref in row['observations'][stream]['sources']:
                relative=ref['relative_path']; ordinal=ref['raw_row_ordinal']; rawrow=selected[relative][ordinal]
                item={'path':relative,'lfs_sha256':ref['sha256']}
                if stream=='binance_trades':
                    record=project_reported_trade(rawrow,item,ordinal);fields=(MAKER,QUOTE_VOLUME);kwargs={}
                else:
                    mi,mr=metadata[rawrow['market_slug']]
                    record=project_reported_orientation(rawrow,item,ordinal,mr,meta,mi)
                    fields=(UP,DOWN);kwargs={'mapping_assumption':MAPPING_ASSUMPTION}
                if record['source']!=ref:raise ValueError('source identity changed in projection')
                observations={}
                for field in fields:
                    try:
                        value=require_reported_direction(record,field,row['decision_ms'],max_age_ms=300000,
                            clock_assumption=CLOCK_ASSUMPTION,**kwargs)
                        status[field+':present']+=1;observations[field]={'value':value}
                    except ValueError as exc:
                        status[field+':blocked']+=1;observations[field]={'value':None,'reason':str(exc)}
                    # A known valid observation must be rejected before its receipt.
                    if observations[field]['value'] is not None:
                        try:
                            require_reported_direction(record,field,record['recorded_available_ms']-1,max_age_ms=300000,
                                clock_assumption=CLOCK_ASSUMPTION,**kwargs)
                        except ValueError:negatives['premature_read_blocked']+=1
                        else:raise ValueError('premature raw feature exposed')
                results.append({'panel_row_id':row['row_id'],'decision_ms':row['decision_ms'],'stream':stream,
                    'source':ref,'field_observations':observations})
    if hashes!={p:file_hash(Path(p)) for p in hashes} or file_hash(path)!=material['rows_sha256']:
        raise ValueError('source or prior panel changed during canary')
    if code!={p:file_hash(Path(p)) for p in code}:raise ValueError('canary source changed while running')
    if not status[MAKER+':present']:raise ValueError('zero readable real reported-maker records')
    fresh_json(output/'observations.json',results)
    report={'schema':'historical_direction_real_byte_canary_v1','mechanical_canary_pass':True,
        'source_contract':direction_contract(),'claim_sha256':file_hash(output/'claim.json'),
        'original_population_rows':n,'sampled_panel_rows':len(sample),'sampled_rows_by_open_date':dict(counts),
        'distinct_physical_rows_read':sum(map(len,wanted.values())),
        'source_files_verified_unchanged':hashes,'field_access_counts':dict(status),
        'negative_checks':dict(negatives),'observations_sha256':file_hash(output/'observations.json'),
        'new_historical_data_bytes':0,'new_labels_read':0,'new_model_calls':0,'new_fits':0,
        'frozen_cache_modified':False,'training_admitted':False,'representative_population_sample':False}
    report['result_sha256']=digest(report);fresh_json(output/'result.json',report)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('ingest','materialized','provenance','output'):p.add_argument('--'+name,type=Path,required=True)
    print(canonical(run(**vars(p.parse_args()))))
