"""Controller-selected causal phase/state annotations without changing any row.

The source-slug15m window is a descriptive clock convention, NOT settlement or
tradability proof. This sidecar preserves every original row, including missing,
stale, conflicting and quiet observations. It defines no target or row weight.
"""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import re

from bounded_compressed_rows import CompressedRows
from historical_data_use_controller import assess_activity
from historical_ingest_controller import _signed
from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json


NON_SAMPLING_FIELDS={'feature_ideas','rationale','limitations'}
SPEC={
    'schema':'historical_causal_phase_state_annotations_v1',
    'nominal_clock':'source_slug_epoch_plus900s_descriptive_only_not_verified_settlement',
    'phase_encoding':['before_nominal_window','within_nominal_window','after_nominal_window'],
    'phase_formula':'before if decision_ms<start; within if start<=decision_ms<start+900000; after otherwise',
    'state_flags':'derived from the current materialized observation reason, not future outcomes',
    'density':'recorded PM events since previous declared grid tick; includes book and price_change events',
    'age':'decision minus recorded availability, only when that timestamp is present; otherwise null',
    'row_weight_added':False,'target_added':False,'rows_deleted':False,
    'future_information_used':False,'settlement_verified':False,
    'deferred_feature_ideas':{
        'trailing_windows':'controller must supply window lengths and exact formula before implementation',
        'signed_book_delta_direction':'requires further selected source fields and exact definition',
        'signed_trade_flow':'current materialization carries latest trade values, not a signed flow aggregate',
        'full_day_update_count':'not available intraday; only a causal prefix may become a feature'},
}


def require_same_sampling(old, new):
    before={k:v for k,v in old['plan'].items() if k not in NON_SAMPLING_FIELDS}
    after={k:v for k,v in new['plan'].items() if k not in NON_SAMPLING_FIELDS}
    if before!=after:raise ValueError('sampling parameters changed; cannot reuse this materialization')


def annotate(row):
    match=re.fullmatch(r'btc-updown-15m-(\d{10})',row['market_slug'])
    if not match:raise ValueError('no supported source-slug clock; never invent a phase')
    when=row['decision_ms'];start=int(match.group(1))*1000;offset=when-start
    phase=('before_nominal_window' if offset<0 else 'within_nominal_window' if offset<900000 else 'after_nominal_window')
    states={}
    for stream,obs in row['observations'].items():
        reason=obs['reason'];available=obs.get('available_ms')
        if available is not None and available>when:raise ValueError('future observation cannot supply state annotations')
        states[stream]={'value_present':bool(obs['values']),
            'stale':reason=='observation exceeds declared staleness',
            'ambiguous_same_receipt':reason.startswith('conflicting_same_receipt_timestamp'),
            'missing':reason=='no_visible_observation',
            'invalid_source':reason=='flagged source observation cannot supply a feature',
            'recorded_arrival_age_ms':when-available if available is not None else None}
    count=row['pm_events_since_previous_grid_tick']
    if type(count) is not int or count<0:raise ValueError('causal event count required')
    return {'row_id':row['row_id'],'decision_ms':when,'nominal_phase':phase,
        'nominal_offset_seconds':offset/1000,'nominal_window_is_verified_settlement':False,
        'observation_states':states,'pm_recorded_events_since_previous_grid_tick':count,
        'quiet_since_previous_grid_tick':count==0,'row_weight':None,'target':None}


def run(materialized, original_controller, controller, source_audit, output):
    identifier(output.name)
    result=load_json(materialized/'result.json');_signed(result,'result_sha256')
    old=load_json(original_controller/'workspace/frozen-data-use-proposal.json');_signed(old,'proposal_sha256')
    new=load_json(controller/'workspace/frozen-data-use-proposal.json');_signed(new,'proposal_sha256')
    assessment=load_json(controller/'session/assessment.json')
    if assessment.get('valid') is not True or assess_activity(controller/'workspace')['valid'] is not True:
        raise ValueError('new first-valid controller decision and unpaid terminal handshake required')
    audit=load_json(source_audit/'audit.json');_signed(audit,'audit_sha256')
    if (audit.get('audit_pass') is not True or audit['materialization_result_sha256']!=file_hash(materialized/'result.json')
            or result['proposal_sha256']!=old['proposal_sha256']):raise ValueError('intact audited original data lineage required')
    require_same_sampling(old,new)
    source=materialized/'diagnostic-states.jsonl.gz'
    if file_hash(source)!=result['rows_sha256']:raise ValueError('original materialization changed')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    spec={**SPEC,'spec_sha256':digest(SPEC)}
    fresh_json(output/'annotation-spec.json',spec)
    claim={'schema':'historical_annotation_claim_v1','controller_proposal_sha256':new['proposal_sha256'],
        'original_proposal_sha256':old['proposal_sha256'],'source_rows_sha256':result['rows_sha256'],
        'source_materialization':str(materialized.absolute()),'source_audit_sha256':file_hash(source_audit/'audit.json'),
        'controller_assessment_sha256':file_hash(controller/'session/assessment.json'),
        'annotation_spec_sha256':spec['spec_sha256'],'code_sha256':file_hash(__file__),
        'source_sampling_parameters_unchanged':True,'observations_reused_unchanged':True,
        'new_model_or_download_calls':0,'training_admitted':False,'no_scope_filter':True}
    fresh_json(output/'claim.json',claim)
    seen=set();counts=Counter();state_counts=Counter();canaries={};last_per_entity={}
    target=output/'annotations.jsonl.gz'
    with gzip.open(source,'rt') as src,CompressedRows(target,max_logical_bytes=750000000,max_stored_bytes=100000000) as out:
        for line in src:
            row=json.loads(line);row_before=digest(row);value=annotate(row)
            if digest(row)!=row_before:raise ValueError('annotation mutated a source row')
            if value['row_id'] in seen:raise ValueError('duplicate sidecar row identity')
            seen.add(value['row_id']);counts[value['nominal_phase']]+=1
            for name,states in value['observation_states'].items():
                for flag in ['value_present','stale','ambiguous_same_receipt','missing','invalid_source']:
                    state_counts[name+':'+flag]+=int(states[flag])
            if value['nominal_phase'] not in canaries:
                # First physical grid row in each phase, not a price-movement selection.
                canaries[value['nominal_phase']]={'source_row_sha256':row_before,'annotation':value}
            out.write_row(value)
        logical_bytes=out.logical
    if len(seen)!=result['row_count'] or dict(counts)!=audit['nominal_scope_counts']:
        raise ValueError('annotation row/phase conservation failed')
    if file_hash(source)!=result['rows_sha256'] or file_hash(__file__)!=claim['code_sha256']:
        raise ValueError('source changed during annotation')
    # Fresh real-row canary plus full conservation pass; old data and proposal remain unchanged.
    fresh_json(output/'canary.json',{'passed':True,'selector':'first_grid_row_per_source_clock_phase',
        'examples':canaries,'all_source_rows_retained':True,'same_sampling_verified':True,'no_model_calls':True})
    final={'schema':'historical_phase_annotations_result_v1','complete':True,'row_count':len(seen),
        'phase_counts':dict(counts),'observation_state_counts':dict(state_counts),
        'annotation_rows_sha256':file_hash(target),'logical_bytes':logical_bytes,'stored_bytes':target.stat().st_size,
        'proposal_sha256':new['proposal_sha256'],'original_observations_sha256':result['rows_sha256'],
        'controller_proposal_materializer_verified':True,'canary_sha256':file_hash(output/'canary.json'),
        'new_model_calls':0,'new_download_bytes':0,'training_admitted':False,'objective_selected':False,
        'deferred_feature_ideas':SPEC['deferred_feature_ideas'],
        'reporting_corrections':[
            'PM stale observations are53872/259780 total grid rows (20.74%), not26% of all observations.',
            'Choosing a diagnostic nominal-window scope would not itself certify settlement; retaining broad scope was the controller choice.']}
    final['result_sha256']=digest(final);fresh_json(output/'result.json',final)
    return final


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['materialized','original-controller','controller','source-audit','output']:
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();r=run(a.materialized,a.original_controller,a.controller,a.source_audit,a.output)
    print(canonical({k:r[k] for k in ['complete','row_count','phase_counts','stored_bytes','result_sha256']}))
