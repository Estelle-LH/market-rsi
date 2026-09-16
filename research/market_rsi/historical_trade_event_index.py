"""Immutable raw-trade index for a requested all-recorded-event capability.

Only the controller's six already-open receipt dates and exact previously
verified files enter. No aggregation window, direction formula, feature, model,
target or new date is selected here. Raw files remain the source of truth.
"""
import argparse
import fcntl
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from historical_direction_fields import direction_contract
from historical_source_contract import CLOCK_ASSUMPTION
from market_rsi import canonical,digest,file_hash,fresh_json,load_json
from materialize_selected_grid_objective import write_archive

MAX_ROWS=8_000_000
MAX_UNCOMPRESSED_BYTES=550_000_000
RAW_COLUMNS=['received_at','trade_time','trade_id','price','quantity','quote_volume','is_buyer_maker']
RENAME={'received_at':'received_ms','trade_time':'event_ms','trade_id':'aggregate_trade_id',
        'price':'price','quantity':'quantity','quote_volume':'reported_quote_volume',
        'is_buyer_maker':'reported_maker'}
QUALITY_BITS={'invalid_price_or_quantity':1,'invalid_maker':2,'invalid_quote_amount':4,
              'arrival_precedes_source_event':8,'invalid_aggregate_trade_id':16}


def project_batch(values,source_index,ordinal_start,dates):
    """Keep physical ordinals and bad values; select only already-open receipt dates."""
    n=len(values['received_at'])
    if set(values)!=set(RAW_COLUMNS) or any(len(v)!=n for v in values.values()):
        raise ValueError('exact aligned raw columns required')
    for key in ('received_at','trade_time','trade_id','is_buyer_maker'):
        if not np.issubdtype(values[key].dtype,np.signedinteger):
            raise ValueError('raw integer field is null, fractional or unsupported; preserve source and stop')
    arrival,event=values['received_at'],values['trade_time']
    if np.any(arrival<0) or np.any(event<0):raise ValueError('unplaceable raw clock')
    opened=np.array(dates,dtype='datetime64[D]').astype(np.int64)
    mask=np.isin(arrival//86_400_000,opened)
    result={RENAME[k]:v[mask].copy() for k,v in values.items()}
    result['source_index']=np.full(int(mask.sum()),source_index,dtype=np.int16)
    result['row_ordinal']=np.arange(ordinal_start,ordinal_start+n,dtype=np.int64)[mask]
    flags=np.zeros(int(mask.sum()),dtype=np.uint8)
    p,q,v,m=(result[k] for k in ('price','quantity','reported_quote_volume','reported_maker'))
    flags[~np.isfinite(p)|(p<=0)|~np.isfinite(q)|(q<0)]|=1
    flags[(m!=0)&(m!=1)]|=2
    flags[~np.isfinite(v)|(v<0)|~np.isclose(v,p*q,rtol=1e-10,atol=1e-8)]|=4
    flags[result['received_ms']<result['event_ms']]|=8
    flags[result['aggregate_trade_id']<0]|=16
    result['quality_bits']=flags
    return result


def build(ingest,materialized,availability,provenance,controller,output):
    root=Path(__file__).resolve().parent
    with (root/'artifacts/historical-ingest-controller.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        material=load_json(materialized/'result.json')
        available=load_json(availability/'audit.json')
        provenance_value=load_json(provenance/'provenance.json')
        for obj in (material,available,provenance_value):
            if obj['result_sha256']!=digest({k:v for k,v in obj.items() if k!='result_sha256'}):
                raise ValueError('signed source receipt changed')
        if (not provenance_value.get('complete') or provenance_value.get('direction_contract')!=direction_contract()
                or provenance_value.get('raw_field_audit_sha256')!=file_hash(availability/'audit.json')):
            raise ValueError('verified raw-field provenance contract required')
        assessment=load_json(controller/'session/assessment.json')
        decision=load_json(controller/'workspace/submitted-grid-learning-decision.json')
        if (not assessment['valid'] or not assessment['process_reaped'] or decision['action']!='defer'
                or 'window-aggregated' not in decision['reason']):
            raise ValueError('completed controller request for aggregation capability required')
        if available['materialization_result_sha256']!=material['result_sha256']:
            raise ValueError('source-field audit does not bind materialized source selection')
        dates=material['controller_requested_utc_dates']
        if dates!=available['already_open_train_utc_dates']:
            raise ValueError('opened dates differ')
        sources=sorted([r for r in material['all_source_receipts'] if '/binance_trades/' in r['path']],
                       key=lambda r:r['path'])
        audited={r['path']:r for r in available['trade_field_audits']}
        if not sources or len(sources)>100 or set(audited)!={s['path'] for s in sources}:
            raise ValueError('exact previously audited trade files required')
        output.mkdir(parents=True,exist_ok=False)
        claim={'schema':'historical_trade_event_index_claim_v1','dates':dates,'sources':sources,
            'materialization_result_sha256':material['result_sha256'],
            'field_audit_sha256':file_hash(availability/'audit.json'),
            'publisher_provenance_sha256':file_hash(provenance/'provenance.json'),
            'controller_assessment_sha256':file_hash(controller/'session/assessment.json'),
            'controller_decision_sha256':file_hash(controller/'workspace/submitted-grid-learning-decision.json'),
            'clock_assumption':CLOCK_ASSUMPTION,'direction_contract':direction_contract(),
            'max_rows':MAX_ROWS,'max_uncompressed_bytes':MAX_UNCOMPRESSED_BYTES,
            'source_code_sha256':file_hash(Path(__file__)),'aggregation_windows_selected':False,
            'new_dates':False,'new_downloads':False,'labels_read':False,'training_admitted':False}
        fresh_json(output/'claim.json',claim)
        chunks=[];n=0;receipts=[]
        try:
            for index,source in enumerate(sources):
                path=ingest/'raw'/source['path']
                if (file_hash(path)!=source['source_sha256']
                        or audited[source['path']]['source_sha256']!=source['source_sha256']):
                    raise ValueError('raw source changed')
                offset=0;selected=0
                for batch in pq.ParquetFile(path).iter_batches(batch_size=65536,columns=RAW_COLUMNS):
                    values={name:batch.column(name).to_numpy(zero_copy_only=False) for name in RAW_COLUMNS}
                    part=project_batch(values,index,offset,dates);offset+=len(values['received_at'])
                    size=len(part['received_ms']);selected+=size;n+=size
                    if n>MAX_ROWS:raise ValueError('bounded event index row limit')
                    if size:chunks.append(part)
                if (offset!=source['full_source_rows_scanned']
                        or selected!=audited[source['path']]['opened_train_only_counts'].get('rows',0)
                        or file_hash(path)!=source['source_sha256']):
                    raise ValueError('raw count or hash changed during projection')
                receipts.append({'source_index':index,'path':source['path'],
                    'source_sha256':source['source_sha256'],'full_rows_scanned':offset,'selected_rows':selected})
            if not chunks or n!=available['trade_counts']['rows']:
                raise ValueError('exact opened-Train record count mismatch')
            arrays={k:np.concatenate([c[k] for c in chunks]) for k in chunks[0]}
            del chunks
            if sum(v.nbytes for v in arrays.values())>MAX_UNCOMPRESSED_BYTES:
                raise ValueError('bounded event index byte limit')
            order=np.lexsort((arrays['row_ordinal'],arrays['source_index'],arrays['received_ms']))
            arrays={k:v[order] for k,v in arrays.items()}
            # Never merge/drop ties or duplicate IDs. Duplicate ID count remains evidence.
            unique_ids=len(np.unique(arrays['aggregate_trade_id']))
            write_archive(output/'events.npz',arrays)
            for source in sources:
                if file_hash(ingest/'raw'/source['path'])!=source['source_sha256']:
                    raise ValueError('raw source changed before final receipt')
            result={'schema':'historical_trade_event_index_v1','complete':True,'claim_sha256':file_hash(output/'claim.json'),
                'archive_sha256':file_hash(output/'events.npz'),'source_receipts':receipts,
                'rows':n,'uncompressed_bytes':sum(v.nbytes for v in arrays.values()),
                'compressed_bytes':(output/'events.npz').stat().st_size,
                'opened_train_utc_dates':dates,'quality_bits':QUALITY_BITS,
                'quality_counts':{name:int(np.count_nonzero(arrays['quality_bits'] & bit)) for name,bit in QUALITY_BITS.items()},
                'duplicate_aggregate_id_excess':n-unique_ids,'recorded_receipt_tie_excess':n-len(np.unique(arrays['received_ms'])),
                'all_physical_rows_retained':True,'sort_order':'receipt_ms, source_index, physical_row_ordinal; ties all retained',
                'normalizer_fitted':False,'labels_read':False,'features_selected':False,'aggregation_windows_selected':False,
                'new_downloads':0,'provider_calls':0,'fits':0,'training_admitted':False,
                'limits':['Only recorded trades, not proof of complete exchange tape.',
                    'No-trade windows cannot be called verified zero flow without coverage evidence.',
                    'Only six previously opened receipt dates; missing date context must not be filled.',
                    'Maker0 may include publisher default; this cannot be independently recovered.',
                    'Same-millisecond ties are multiple retained aggregate trades, not an inferred exchange order.',
                    'This index is not yet connected to the researcher feature library.']}
            result['result_sha256']=digest(result);fresh_json(output/'result.json',result);return result
        except Exception as error:
            fresh_json(output/'failure.json',{'type':type(error).__name__,'error':str(error),'no_automatic_retry':True})
            raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('ingest','materialized','availability','provenance','controller','output'):
        p.add_argument('--'+name,type=Path,required=True)
    result=build(**{k:v.resolve() for k,v in vars(p.parse_args()).items()})
    print(canonical({k:result[k] for k in ('rows','result_sha256','quality_counts','duplicate_aggregate_id_excess','compressed_bytes')}))
