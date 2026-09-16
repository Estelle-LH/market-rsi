"""Separate descriptive clock attribution from admission or policy decisions."""
import argparse
from pathlib import Path
from market_rsi import digest,file_hash,fresh_json,load_json


def review(report,prior):
    for r in (report,prior):
        if r['result_sha256']!=digest({k:v for k,v in r.items() if k!='result_sha256'}):raise ValueError('receipt changed')
        if not r['complete'] or not r['ssh_reaped'] or r['exit_code'] or r['source_admitted']:raise ValueError('incomplete diagnostic')
    for key in ('compressed_sha256','decoded_sha256','decoded_records'):
        if report['transport'][key]!=prior['transport'][key]:raise ValueError('source copy changed between different diagnostics')
    p=report['profile'];kinds=p['quote_event_counts_by_kind']
    quote_events=sum(v.get('quote_events',0) for v in kinds.values())
    adjacent=sum(v.get('adjacent_source_regressions',0) for v in kinds.values())
    highwater=sum(v.get('below_source_highwater',0) for v in kinds.values())
    old=prior['profile']['source_clock_totals']
    if (quote_events!=old['counts']['quote_rows'] or adjacent!=old['adjacent_gap_histogram'].get('regression',0)
        or highwater!=old['counts'].get('below_prior_highwater_rows',0)
        or sum(p['source_regression_transition_counts'].values())!=adjacent):raise ValueError('denominators do not reconcile')
    cross=sum(v for k,v in p['source_regression_transition_counts'].items() if len(set(k.split(' -> ')))==2)
    return {'schema':'message_clock_origin_findings_v1','quote_events':quote_events,
        'adjacent_regressions':adjacent,'below_highwater_rows':highwater,
        'between_kind_regressions':cross,'all_observed_regressions_between_kinds':adjacent>0 and cross==adjacent,
        'transitions':p['source_regression_transition_counts'],'within_kind_regressions':p['within_kind_source_regressions'],
        'source_before_wrapper_day_by_kind':{k:v.get('source_before_wrapper_day',0) for k,v in kinds.items()},
        'min_source_ms_by_kind':p['min_source_ms_by_kind'],'max_source_ms_by_kind':p['max_source_ms_by_kind'],
        'wrapper_adjacent_difference_counts':p['wrapper_adjacent_difference_counts'],
        'clock_semantics_attested':False,'source_admitted':False,'policy_changed':False,'rows_deleted':0,'fits':0,'provider_calls':0,
        'interpretation':'Aggregate regressions must be attributed by message kind before calling live updates disordered. '
            'Within-kind ordering in one file is not proof of original receipt time, full-day completeness or deployable forecasting. '
            'The controller still chooses the source/clock; the runner must not simply drop REST or substitute wrapper time.',
        'report_result_sha256':report['result_sha256'],'prior_report_result_sha256':prior['result_sha256']}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('report','prior','output'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();r=review(load_json(a.report),load_json(a.prior));r['review_source_sha256']=file_hash(__file__)
    r['result_sha256']=digest(r);a.output.parent.mkdir(parents=True,exist_ok=True);fresh_json(a.output,r);print(r)
