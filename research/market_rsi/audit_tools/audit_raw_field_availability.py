"""Audit raw fields omitted by the current cache, with no label access or fitting."""
import argparse
from collections import Counter
from pathlib import Path
import sys

import numpy as np
import pyarrow.parquet as pq

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_rsi import canonical, digest, file_hash, fresh_json, load_json


def flag_counts(values):
    values=np.asarray(values)
    finite=np.isfinite(values)
    return {'zero':int((finite & (values==0)).sum()),'one':int((finite & (values==1)).sum()),
        'missing':int(np.isnan(values).sum()),'invalid':int((~np.isnan(values) & (~finite | ((values!=0) & (values!=1)))).sum())}


def run(ingest, materialized, output):
    result=load_json(materialized/'result.json')
    if result['result_sha256']!=digest({k:v for k,v in result.items() if k!='result_sha256'}):
        raise ValueError('materialized source receipt changed')
    if output.exists():raise ValueError('fresh field audit output required')
    raw=ingest/'raw';days=result['controller_requested_utc_dates'];schemas={}
    for stream in ['polymarket_ticks_ms','binance_trades','binance_ticks_ms','market_meta']:
        groups={}
        for path in sorted((raw/'unified'/stream).rglob('*.parquet')):
            schema=pq.read_schema(path);fields=[{'name':f.name,'type':str(f.type)} for f in schema]
            key=digest(fields)
            group=groups.setdefault(key,{'fields':fields,'files':[]})
            group['files'].append(str(path.relative_to(raw)))
        schemas[stream]=list(groups.values())
    reports=[]
    for receipt in result['all_source_receipts']:
        if '/binance_trades/' not in receipt['path']:continue
        path=raw/receipt['path']
        if file_hash(path)!=receipt['source_sha256']:raise ValueError('raw source hash changed')
        counter=Counter();per_day={};rows=0
        for batch in pq.ParquetFile(path).iter_batches(batch_size=65536,
                columns=['received_at','is_buyer_maker','price','quantity','quote_volume']):
            values={n:batch.column(n).to_numpy(zero_copy_only=False) for n in batch.schema.names}
            received=values['received_at'];rows+=len(received)
            if not np.all(np.isfinite(received)) or np.any(received<0):raise ValueError('invalid recorded clock')
            dates=received.astype('datetime64[ms]').astype('datetime64[D]').astype(str)
            for day in days:
                mask=dates==day
                if not mask.any():continue
                count=flag_counts(values['is_buyer_maker'][mask]);count['rows']=int(mask.sum())
                quantity=values['quantity'][mask];price=values['price'][mask];volume=values['quote_volume'][mask]
                count['invalid_price_or_quantity']=int((~np.isfinite(price) | (price<=0) | ~np.isfinite(quantity) | (quantity<0)).sum())
                count['quote_volume_disagrees_with_price_times_quantity']=int((~np.isclose(volume,price*quantity,rtol=1e-10,atol=1e-8)).sum())
                counter.update(count);per_day.setdefault(day,Counter()).update(count)
        if rows!=receipt['full_source_rows_scanned'] or file_hash(path)!=receipt['source_sha256']:
            raise ValueError('raw row count or hash changed during audit')
        reports.append({'path':receipt['path'],'source_sha256':receipt['source_sha256'],
            'full_file_rows_scanned':rows,'opened_train_only_counts':dict(counter),
            'by_opened_train_utc_date':{k:dict(v) for k,v in per_day.items()},'raw_unchanged':True})
    total=Counter()
    for report in reports:total.update(report['opened_train_only_counts'])
    value={'schema':'raw_field_availability_audit_v1','complete':True,
        'materialization_result_sha256':result['result_sha256'],'schema_inventory':schemas,
        'already_open_train_utc_dates':days,'trade_field_audits':reports,'trade_counts':dict(total),
        'proven_findings':[
            'Every acquired binance_trades file has is_buyer_maker, quantity and quote_volume columns.',
            'Current historical_source_contract projection carries only trade_price/trade_quantity, omitting maker flag and quote_volume.',
            'Current cache also omits market_meta up_token_id/down_token_id and polymarket side_label.',
            'Acquired schemas contain no full bid/ask depth ladder or identified Polymarket trade tape.'],
        'semantic_limit':'Column presence and 0/1 validity do not prove deployed collector mapping. Verify publisher mapping before defining signed flow; maintain recorded-arrival clock caveat.',
        'binance_primary_reference':'https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams',
        'new_target_values_read':False,'new_dev_test_opened':False,'features_constructed':False,
        'new_downloads':0,'model_calls':0,'fits':0,'raw_deleted_or_modified':False}
    value['result_sha256']=digest(value);output.mkdir(parents=True,exist_ok=False)
    fresh_json(output/'audit.json',value);return value


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['ingest','materialized','output']:p.add_argument('--'+name,type=Path,required=True)
    print(canonical(run(**vars(p.parse_args()))))
