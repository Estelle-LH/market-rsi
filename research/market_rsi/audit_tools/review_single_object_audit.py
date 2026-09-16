"""Reproducible aggregate-only findings; no second source read or QA admission."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
from market_rsi import digest,file_hash,fresh_json,load_json


def findings(report):
    if report.get('result_sha256')!=digest({k:v for k,v in report.items() if k!='result_sha256'}):
        raise ValueError('raw audit result changed')
    if (not report['complete'] or not report['ssh_reaped'] or report['exit_code']!=0
            or any(report[k] for k in ('source_admitted','qa_pass','labels_computed','features_computed','fits','provider_calls','raw_rows_exported','raw_identifiers_exported','new_test_opened','request_fulfilled_in_full'))):
        raise ValueError('not a complete partial raw-only audit')
    t=report['transport'];p=report['profile']['population'];c=p['totals']['counts']
    if (not t['decoder_reaped'] or not t['feeder_reaped'] or not t['source_unchanged_verified']
            or not t['compressed_hash_is_complete'] or t['source_open_passes']!=1
            or t['compressed_bytes_read']!=report['scope']['object']['advertised_bytes']
            or t['decoded_records']!=p['input_counts']['raw_records']):
        raise ValueError('source/cleanup/record count mismatch')
    clock=report['profile']['source_clock_totals'];entities=report['profile']['source_clock_entities']
    if (c.get('equal_mid_pairs',0)+c.get('changed_mid_pairs',0)!=c.get('adjacent_valid_mid_pairs',0)
            or clock['counts']['quote_rows']!=p['input_counts']['quote_observations']
            or sum(clock['adjacent_gap_histogram'].values())!=clock['counts'].get('adjacent_timestamp_pairs',0)
            or sum(e['counts']['quote_rows'] for e in entities)!=clock['counts']['quote_rows']):
        raise ValueError('aggregate denominator mismatch')
    obj=report['scope']['object']
    file_start=int(datetime.fromisoformat(obj['date']+'T'+obj['hour']+':00:00+00:00').timestamp()*1000)
    lows=[e['min_source_ms'] for e in entities if e['min_source_ms'] is not None]
    highs=[e['max_source_ms'] for e in entities if e['max_source_ms'] is not None]
    def utc(ms):return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat() if ms is not None else None
    def ratio(n,d):return n/d if d else None
    return {'schema':'single_object_independent_findings_v1','review_is_not_controller_authored':True,
        'raw_report_result_sha256':report['result_sha256'],
        'current_copy_identity':{'object':obj,'sha256':t['compressed_sha256'],'decoded_sha256':t['decoded_sha256'],
            'raw_records':t['decoded_records'],'decoded_bytes':t['decoded_bytes'],'original_capture_provenance_proven':False},
        'observation_activity':{'quote_observations':p['input_counts']['quote_observations'],
            'adjacent_valid_mid_pairs':c.get('adjacent_valid_mid_pairs',0),
            'equal_mid_pairs':c.get('equal_mid_pairs',0),'changed_mid_pairs':c.get('changed_mid_pairs',0),
            'equal_mid_fraction':ratio(c.get('equal_mid_pairs',0),c.get('adjacent_valid_mid_pairs',0)),
            'breadth':p['breadth'],'independent_training_samples_estimated':False,
            'zero_change_rows_deleted':False,'not_a_horizon_label_activity_measure':True},
        'clock_observations':{'earliest_source_time_utc':utc(min(lows) if lows else None),
            'latest_source_time_utc':utc(max(highs) if highs else None),
            'entities_with_source_time_before_named_hour':sum(e['min_source_ms'] is not None and e['min_source_ms']<file_start for e in entities),
            'entities_with_all_source_times_before_named_hour':sum(e['max_source_ms'] is not None and e['max_source_ms']<file_start for e in entities),
            'adjacent_regressions':clock['adjacent_gap_histogram'].get('regression',0),
            'below_prior_highwater_rows':clock['counts'].get('below_prior_highwater_rows',0),
            'same_ms_adjacent_fraction':ratio(clock['adjacent_gap_histogram'].get('0ms',0),clock['counts'].get('adjacent_timestamp_pairs',0)),
            'timestamp_semantics_or_outage_inferred':False,
            'interpretation':'Source time can precede the named file hour. This alone does not distinguish old state snapshots, delayed events or timestamp semantics. No original-date dataset was opened separately.'},
        'quote_observations':{'bbo_mismatch':c.get('bbo_mismatch',0),'bbo_comparable':c.get('bbo_comparable',0),
            'source_crossed_rows':p['totals']['source_status'].get('crossed',0),
            'interpretation':'Direct BBO and reconstructed depth are different measurements; zero observed direct crossings is not proof of whole-source validity.'},
        'unfinished':['Original capability JSON malformed; contradictory future-label wording remains unexecuted.',
            'No decision-time feature or label materializer was run; no model fit or new score.',
            'Only this current copy gained a content commitment; no full-day, original-capture or other-object attestation.',
            'Clock interpretation and source-specific training checks still require evidence, not row deletion.'],
        'source_admitted':False,'qa_pass':False,'fits':0,'provider_calls':0,'predictive_improvement_proven':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();path=a.run/'report.json';result=findings(load_json(path))
    result.update(report_file_sha256=file_hash(path),review_source_sha256=file_hash(__file__))
    result['result_sha256']=digest(result);a.output.parent.mkdir(parents=True,exist_ok=True);fresh_json(a.output,result)
    print(result)
