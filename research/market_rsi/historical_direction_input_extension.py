"""Add reported direction columns to a frozen panel without rewriting old inputs.

No label, model, target-selection or network API is called. Only physical rows
already referenced by the completed opened-Train materialization are accessed.
This makes source observations available, not a selected flow signal/model.
"""
import argparse
from collections import Counter, defaultdict
import fcntl
import gzip
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from audit_tools.canary_direction_fields import physical_rows
from historical_direction_fields import (DOWN, MAKER, MAPPING_ASSUMPTION, QUOTE_VOLUME,
    UP, direction_contract, project_reported_orientation, project_reported_trade,
    require_reported_direction)
from historical_grid_learning import bounded_npz
from historical_ingest_controller import _signed
from historical_input_compatibility import ADDED_FIELDS, ARRAY_KEYS, verify_addition
from historical_phase_annotations import require_same_sampling
from historical_source_contract import CLOCK_ASSUMPTION, physical_reference
from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json
from materialize_selected_grid_objective import write_archive


MAX_REFERENCES = 600000
MAX_OUTPUT_BYTES = 150000000
TRADE_COLUMNS = ['trade_id','trade_time','received_at','price','quantity','quote_volume','is_buyer_maker']
PM_COLUMNS = ['id','source_ts_ms','ingest_ts_ms','market_slug','asset_id','side_label',
              'event_type','best_bid','best_ask','price','size']


def original_rows(path, x, dates):
    """Verify the exact population/order/times, even for rows without any quote."""
    n=0
    with gzip.open(path,'rt') as stream:
        for n,line in enumerate(stream,1):
            if n>len(x['row_id']):raise ValueError('extra panel row; no truncation')
            row=json.loads(line);i=n-1
            if (row['row_id']!=x['row_id'][i] or row['decision_ms']!=x['decision_ms'][i]
                    or row['utc_date']!=x['date'][i] or row['utc_date'] not in dates
                    or row.get('target') is not None or row.get('training_admitted') is not False
                    or digest({k:row[k] for k in ('market_slug','asset_id','decision_ms')})!=row['row_id']):
                raise ValueError('exact previously opened unlabelled row required')
            yield row
    if n!=len(x['row_id']):raise ValueError('incomplete original population')


def agree_field(records, field, decision_ms, max_age_ms):
    """Require all tied original latest records to supply the same field value."""
    if not records:return np.nan,'no_original_source_reference'
    if len({r['recorded_available_ms'] for r in records})!=1:
        raise ValueError('original latest references have unequal receipt clocks')
    try:
        values=[require_reported_direction(r,field,decision_ms,max_age_ms=max_age_ms,
            clock_assumption=CLOCK_ASSUMPTION,
            mapping_assumption=MAPPING_ASSUMPTION if field in (UP,DOWN) else None) for r in records]
    except ValueError as exc:
        return np.nan,str(exc)
    if len(set(values))!=1:return np.nan,'conflicting_same_receipt_direction_values'
    return float(values[0]),'present'


def sampling_ancestry(material, original_proposal, current_proposal):
    """An annotation-only controller revision may reuse the original sampling."""
    _signed(original_proposal,'proposal_sha256');_signed(current_proposal,'proposal_sha256')
    if material['proposal_sha256']!=original_proposal['proposal_sha256']:
        raise ValueError('original materialization proposal is not the claimed ancestor')
    require_same_sampling(original_proposal,current_proposal)
    return {'materialization_proposal_sha256':original_proposal['proposal_sha256'],
            'current_proposal_sha256':current_proposal['proposal_sha256'],
            'same_sampling_verified':True}


def run(ingest, materialized, original_cache, proposal, original_proposal, provenance, canary, output):
    identifier(output.name)
    original=load_json(original_cache/'result.json');material=load_json(materialized/'result.json')
    source_claim=load_json(materialized/'claim.json');plan=load_json(proposal)
    ancestor=load_json(original_proposal)
    evidence=load_json(provenance/'provenance.json');tested=load_json(canary/'result.json')
    for value in (original,material,evidence,tested):_signed(value,'result_sha256')
    ancestry=sampling_ancestry(material,ancestor,plan)
    cache_claim=load_json(original_cache/'claim.json')
    if (file_hash(original_cache/'claim.json')!=original['claim_sha256']
            or cache_claim['data_use_proposal_sha256']!=plan['proposal_sha256']
            or cache_claim['input_hashes'].get(str(proposal.resolve()))!=file_hash(proposal)
            or cache_claim['input_hashes'].get(str((materialized/'result.json').resolve()))!=file_hash(materialized/'result.json')
            or any(file_hash(Path(p))!=sha for p,sha in cache_claim['input_hashes'].items())):
        raise ValueError('original cache does not bind this materialization and current proposal')
    if (not original['complete'] or original['labels_present'] is not False or original['fresh_holdout'] is not False
            or material['row_count']!=original['rows'] or not material['source_scan_complete']
            or material['controller_requested_utc_dates']!=plan['plan']['open_train_utc_dates']
            or evidence['direction_contract']!=direction_contract()
            or tested['source_contract']!=direction_contract() or not tested['mechanical_canary_pass']):
        raise ValueError('matching completed opened-Train inputs, plan and semantic canary required')
    max_age=plan['plan']['max_age_ms']
    if type(max_age) is not int or max_age<0:raise ValueError('frozen controller age required')
    canary_claim=load_json(canary/'claim.json')
    if (file_hash(canary/'claim.json')!=tested['claim_sha256']
            or canary_claim['material_result_sha256']!=material['result_sha256']
            or canary_claim['provenance_sha256']!=file_hash(provenance/'provenance.json')
            or any(file_hash(Path(p))!=sha for p,sha in canary_claim['code_hashes'].items())):
        raise ValueError('tested adapter source or evidence changed')
    for source in evidence['files']:
        if file_hash(Path(source['local_path']))!=source['sha256']:raise ValueError('publisher source evidence changed')
    source_path=materialized/'diagnostic-states.jsonl.gz';cache_path=original_cache/'current-inputs.npz'
    if file_hash(source_path)!=material['rows_sha256'] or file_hash(cache_path)!=original['archive_sha256']:
        raise ValueError('original source or current-input cache changed')
    x=bounded_npz(cache_path,ARRAY_KEYS)
    if (len(x['row_id'])!=original['rows'] or x['field_names'].tolist()!=original['field_names']
            or not 0<len(x['row_id'])<=500000 or set(x['date'])!=set(plan['plan']['open_train_utc_dates'])):
        raise ValueError('original cache population changed')
    root=Path(__file__).resolve().parent
    source_files=[Path(__file__),root/'historical_direction_fields.py',root/'historical_source_contract.py',
        root/'audit_tools/canary_direction_fields.py',root/'historical_grid_learning.py',
        root/'materialize_selected_grid_objective.py',root/'historical_phase_annotations.py',root/'historical_input_compatibility.py']
    code={str(p.resolve()):file_hash(p) for p in source_files}
    hashes={str(p.resolve()):file_hash(p) for p in [source_path,cache_path,original_cache/'result.json',
        materialized/'result.json',materialized/'claim.json',proposal,original_proposal,
        original_cache/'claim.json',provenance/'provenance.json',canary/'result.json']}
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    fresh_json(output/'claim.json',{'schema':'historical_direction_input_extension_claim_v1',
        'code_hashes':code,'input_hashes':hashes,'max_age_ms_from_controller':max_age,
        'proposal_sha256':plan['proposal_sha256'],'added_fields':list(ADDED_FIELDS),
        'sampling_ancestry':ancestry,
        'new_labels_or_paid_calls':0,'source_scope':'exact old materialization physical references only',
        'mapping_assumption':MAPPING_ASSUMPTION,'source_clock_assumption':CLOCK_ASSUMPTION})
    try:
        wanted=defaultdict(dict);receipts={r['path']:r['source_sha256'] for r in material['all_source_receipts']}
        total_refs=0
        for row in original_rows(source_path,x,plan['plan']['open_train_utc_dates']):
            for stream in ('binance_trades','polymarket_ticks_ms'):
                for ref in row['observations'][stream]['sources']:
                    relative=ref['relative_path'];ordinal=ref['raw_row_ordinal']
                    item={'path':relative,'lfs_sha256':ref['sha256']}
                    if (receipts.get(relative)!=ref['sha256'] or Path(relative).parts[1]!=stream
                            or physical_reference(item,ordinal)!=ref):
                        raise ValueError('unbound physical source reference')
                    if ordinal not in wanted[relative]:total_refs+=1
                    wanted[relative][ordinal]=ref
                    if total_refs>MAX_REFERENCES:raise ValueError('bounded physical input reference cap')
        print(canonical({'stage':'references_bound','rows':len(x['row_id']),'physical_rows':total_refs}),flush=True)
        raw=ingest/'raw';selected={};raw_hashes={}
        meta=source_claim['metadata'];meta_path=raw/meta['path']
        if file_hash(meta_path)!=meta['lfs_sha256']:raise ValueError('raw metadata changed')
        raw_hashes[str(meta_path.resolve())]=meta['lfs_sha256']
        meta_rows=pq.ParquetFile(meta_path).read(columns=['market_slug','up_token_id','down_token_id','first_seen_ms']).to_pylist()
        metadata={r['market_slug']:(i,r) for i,r in enumerate(meta_rows)}
        if len(metadata)!=len(meta_rows):raise ValueError('duplicate publisher mapping')
        for relative,refs in wanted.items():
            path=raw/relative;expected=receipts[relative];stream=Path(relative).parts[1]
            if file_hash(path)!=expected:raise ValueError('raw file changed before physical read')
            raw_hashes[str(path.resolve())]=expected
            rows=physical_rows(path,refs,TRADE_COLUMNS if stream=='binance_trades' else PM_COLUMNS)
            item={'path':relative,'lfs_sha256':expected};projected={}
            for ordinal,row in rows.items():
                if stream=='binance_trades':record=project_reported_trade(row,item,ordinal)
                else:
                    mi,mr=metadata[row['market_slug']]
                    record=project_reported_orientation(row,item,ordinal,mr,meta,mi)
                if record['source']!=refs[ordinal]:raise ValueError('projection changed physical identity')
                projected[ordinal]=record
            selected[relative]=projected
            print(canonical({'stage':'source_projected','path':relative,'physical_rows':len(projected)}),flush=True)
        added=np.full((len(x['row_id']),len(ADDED_FIELDS)),np.nan)
        reason_codes=np.empty(added.shape,dtype=np.int16);reason_dictionary={};counts=Counter()
        for i,row in enumerate(original_rows(source_path,x,plan['plan']['open_train_utc_dates'])):
            for stream,fields in (('binance_trades',(MAKER,QUOTE_VOLUME)),('polymarket_ticks_ms',(UP,DOWN))):
                records=[selected[ref['relative_path']][ref['raw_row_ordinal']] for ref in row['observations'][stream]['sources']]
                for field in fields:
                    column=ADDED_FIELDS.index(stream+'.'+field)
                    value,reason=agree_field(records,field,row['decision_ms'],max_age)
                    if reason not in reason_dictionary:reason_dictionary[reason]=len(reason_dictionary)
                    if len(reason_dictionary)>1000:raise ValueError('bounded distinct source reasons required')
                    added[i,column]=value;reason_codes[i,column]=reason_dictionary[reason]
                    counts[stream+'.'+field+':'+reason]+=1
        extended={k:v for k,v in x.items() if k not in ('field_names','values')}
        extended.update(field_names=np.array(x['field_names'].tolist()+list(ADDED_FIELDS)),values=np.column_stack((x['values'],added)))
        compatibility=verify_addition(x,extended)
        archive_path=output/'current-inputs.npz';write_archive(archive_path,extended)
        reason_path=output/'direction-field-reasons.npz'
        write_archive(reason_path,{'row_id':x['row_id'],'field_names':np.array(ADDED_FIELDS),
            'reason_codes':reason_codes,'reason_dictionary':np.array(list(reason_dictionary))})
        if sum(p.stat().st_size for p in (archive_path,reason_path))>MAX_OUTPUT_BYTES:
            raise ValueError('stored extension byte cap; preserve but do not admit')
        verify_addition(x,bounded_npz(archive_path,ARRAY_KEYS))
        if hashes!={p:file_hash(Path(p)) for p in hashes} or raw_hashes!={p:file_hash(Path(p)) for p in raw_hashes}:
            raise ValueError('original input/source changed during extension')
        if code!={p:file_hash(Path(p)) for p in code}:raise ValueError('extension source changed during execution')
        result={'schema':'historical_direction_input_extension_v1','complete':True,
            'claim_sha256':file_hash(output/'claim.json'),'panel_sha256':original['panel_sha256'],
            'archive_sha256':file_hash(archive_path),'stored_bytes':archive_path.stat().st_size,
            'rows':len(x['row_id']),'field_names':extended['field_names'].tolist(),
            'finite_rows_per_field':{name:int(np.isfinite(extended['values'][:,i]).sum()) for i,name in enumerate(extended['field_names'])},
            'additive_parent':{'archive_sha256':original['archive_sha256'],'result_sha256':original['result_sha256'],
                               'field_names':original['field_names']},
            'compatibility':compatibility,'source_extension':evidence,
            'sampling_ancestry':ancestry,
            'proposal_sha256':plan['proposal_sha256'],'max_age_ms':max_age,
            'distinct_original_physical_rows':total_refs,'raw_source_hashes_verified_unchanged':raw_hashes,
            'field_reason_counts':dict(counts),'reason_archive_sha256':file_hash(reason_path),
            'labels_present':False,'training_admitted':False,'fresh_holdout':False,
            'all_rows_retained_in_original_order':True,'new_model_calls':0,'new_fits':0,'new_download_bytes':0,
            'limitations':['Additional current reported fields only; not all raw source history is exposed.',
                'Latest-record maker/amount are not an aggregated signed-flow series.',
                'Maker0 may be upstream false or publisher missing-field default; deployment unverified.',
                'Token roles use a static publisher mapping and first_seen proxy, not settlement outcomes.',
                'No fresh evaluation data; all dates remain opened Train diagnostics.',
                'No new feature formula, aggregation window, model or scientific method is selected here.']}
        result['result_sha256']=digest(result);fresh_json(output/'result.json',result)
        return result
    except Exception as exc:
        fresh_json(output/'failure.json',{'complete':False,'error_type':type(exc).__name__,'error':str(exc)})
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('ingest','materialized','original-cache','proposal','original-proposal','provenance','canary','output'):
        p.add_argument('--'+name,type=Path,required=True)
    with (Path(__file__).parent/'artifacts/historical-ingest-controller.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        print(canonical(run(**vars(p.parse_args()))))
