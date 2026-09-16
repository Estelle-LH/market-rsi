"""Independent output conservation, causal-boundary and source-scope audit.

Descriptive cadence changes are NOT a selected prediction target. The source's
15m slug window is a diagnostic hypothesis, not verified exchange settlement.
No rows are filtered or rewritten by this audit.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path
import re

from historical_ingest_controller import _signed
from historical_source_contract import physical_reference
from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json


def nominal_scope(slug, when):
    match=re.fullmatch(r'btc-updown-15m-(\d{10})',slug)
    if not match:return 'unknown_nominal_window'
    start=int(match.group(1))*1000
    return 'before_nominal_window' if when<start else 'within_nominal_window' if when<start+900000 else 'after_nominal_window'


def compare_prefix(old, compressed):
    compared=0
    with old.open('rb') as source,gzip.open(compressed,'rb') as new:
        while chunk:=source.read(1048576):
            if new.read(len(chunk))!=chunk:raise ValueError('storage-only continuation changed row content')
            compared+=len(chunk)
    return compared


def audit(materialized, controller, prior, output):
    identifier(output.name)
    result=load_json(materialized/'result.json');_signed(result,'result_sha256')
    proposal=load_json(controller/'workspace/frozen-data-use-proposal.json');_signed(proposal,'proposal_sha256')
    claim=load_json(materialized/'claim.json')
    if result['proposal_sha256']!=proposal['proposal_sha256'] or result['training_admitted'] is not False:
        raise ValueError('matching unadmitted controller proposal required')
    path=materialized/'diagnostic-states.jsonl.gz'
    if file_hash(path)!=result['rows_sha256']:raise ValueError('compressed output hash mismatch')
    adaptation=load_json(materialized/'storage-adaptation.json')
    old=prior/'diagnostic-states.jsonl'
    if file_hash(old)!=adaptation['prior_partial_sha256']:raise ValueError('original partial output changed')
    prefix=compare_prefix(old,path)
    planned=proposal['plan'];dates=Counter();valid=Counter();reasons=Counter();scopes=Counter();scope_valid=Counter()
    changes=defaultdict(Counter);previous={};row_ids=set();references=set();seen=logical=0
    manifest={x['item']['path']:x['item'] for x in claim['selected_files']}
    with gzip.open(path,'rb') as f:
        for line in f:
            logical+=len(line);row=json.loads(line);seen+=1
            if seen>planned['max_materialized_rows']:raise ValueError('row cap exceeded')
            if row.get('training_admitted') is not False or row.get('target') is not None:
                raise ValueError('source materialization has unexpected target/admission')
            when=row['decision_ms'];day=datetime.fromtimestamp(when/1000,timezone.utc).date().isoformat()
            if row['utc_date']!=day or day not in planned['open_train_utc_dates'] or when%planned['cadence_ms']:
                raise ValueError('grid clock/date differs from controller selection')
            expected_id=digest({k:row[k] for k in ['market_slug','asset_id','decision_ms']})
            if row['row_id']!=expected_id or expected_id in row_ids:raise ValueError('row identity/uniqueness failed')
            row_ids.add(expected_id);dates[day]+=1
            scope=nominal_scope(row['market_slug'],when);scopes[scope]+=1
            if set(row['observations'])!={'polymarket_ticks_ms',*planned['context_streams']}:
                raise ValueError('selected observation set changed')
            for stream,obs in row['observations'].items():
                reasons[stream+':'+obs['reason']]+=1
                for ref in obs['sources']:
                    if ref['physical_row_id'] in references:continue
                    item=manifest.get(ref['relative_path'])
                    if item is None or ref!=physical_reference(item,ref['raw_row_ordinal']):
                        raise ValueError('source physical provenance invalid')
                    references.add(ref['physical_row_id'])
                if obs['values']:
                    valid[stream]+=1
                    if (obs['available_ms']>when or when-obs['available_ms']>planned['max_age_ms']
                            or not 0<=obs['max_source_age_ms']<=planned['max_age_ms']):
                        raise ValueError('future/stale observation escaped source boundary')
                    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in obs['values'].values()):
                        raise ValueError('nonfinite available feature')
            pm=row['observations']['polymarket_ticks_ms']['values']
            midpoint=None
            if pm:
                if not 0<=pm['reported_bid']<=pm['reported_ask']<=1:raise ValueError('invalid materialized BBO')
                midpoint=(pm['reported_bid']+pm['reported_ask'])/2
                if midpoint!=pm['midpoint_from_reported_bbo']:raise ValueError('wrong midpoint alias')
                scope_valid[scope]+=1
            key=(row['market_slug'],row['asset_id']);old_state=previous.get(key)
            if old_state and old_state[0]+planned['cadence_ms']==when and midpoint is not None and old_state[1] is not None:
                group=scope if old_state[2]==scope else 'crosses_nominal_boundary'
                changes[group]['consecutive_available_pairs']+=1
                changes[group]['exactly_unchanged_pairs']+=int(midpoint==old_state[1])
                changes[group]['changed_pairs']+=int(midpoint!=old_state[1])
            previous[key]=(when,midpoint,scope)
    if (seen!=result['row_count'] or dict(dates)!=result['grid_rows_by_date']
            or dict(valid)!=result['nonempty_observation_counts']
            or dict(reasons)!=result['observation_reason_counts'] or logical!=result['logical_output_bytes']):
        raise ValueError('full output counter conservation failed')
    if file_hash(path)!=result['rows_sha256']:raise ValueError('output changed during audit')
    report={'schema':'historical_materialization_output_audit_v1','audit_pass':True,
        'materialization_result_sha256':file_hash(materialized/'result.json'),
        'rows_sha256':result['rows_sha256'],'proposal_sha256':proposal['proposal_sha256'],
        'row_count':seen,'unique_row_ids':len(row_ids),'verified_physical_references':len(references),
        'grid_rows_by_date':dict(dates),'nonempty_observation_counts':dict(valid),
        'original_plain_partial_exact_prefix_bytes':prefix,'logical_bytes':logical,
        'stored_bytes':path.stat().st_size,'nominal_scope_counts':dict(scopes),
        'nonempty_pm_by_nominal_scope':dict(scope_valid),
        'descriptive_adjacent_grid_midpoint_changes':{k:dict(v) for k,v in changes.items()},
        'nominal_window_is_not_verified_settlement':True,'future_label_filter':False,
        'training_admitted':False,'objective_selected':False,'new_paid_calls':0,'raw_rows_deleted':False}
    report['audit_sha256']=digest(report)
    output.mkdir(parents=True,exist_ok=False,mode=0o700);fresh_json(output/'audit.json',report)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['materialized','controller','prior','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();r=audit(a.materialized,a.controller,a.prior,a.output)
    print(canonical({k:r[k] for k in ['audit_pass','row_count','stored_bytes','nominal_scope_counts',
        'nonempty_pm_by_nominal_scope','descriptive_adjacent_grid_midpoint_changes','audit_sha256']}))
