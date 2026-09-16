"""Metadata-only upper bound on future validation dates, not holdout admission."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_rsi import canonical,digest,file_hash,fresh_json,load_json


def summarize(calendar,opened,check_dates):
    dates=[r['utc_date'] for r in calendar]
    if not dates or len(set(dates))!=len(dates):raise ValueError('unique metadata dates required')
    known=sorted(set(opened));last_check=max(check_dates)
    later=[dict(r,known_previously_opened=r['utc_date'] in known) for r in calendar if r['utc_date']>last_check]
    optimistic=[r for r in later if not r['known_previously_opened']]
    return {'metadata_date_count':len(dates),'known_opened_dates_lower_bound':known,
        'latest_selected_check_date':last_check,'dates_after_selected_check':later,
        'potential_later_dates_excluding_known_opened_upper_bound':len(optimistic),
        'later_than_all_known_opened_dates':[r for r in calendar if r['utc_date']>max(known)],
        'twenty_future_untouched_sessions_proven':False,
        'twenty_future_dates_even_arithmetically_possible':len(optimistic)>=20,
        'fresh_holdout_dates_admitted':[],'exposure_audit_complete':False,
        'limits':'This is only a date-count upper bound from retained coverage metadata. Absence from '
            'the known-opened list is NOT proof of no exposure. An event in a minute is not '
            'continuous executable coverage. No date, quality threshold or validation population '
            'is selected here. All unseen prices/labels remain unopened.'}


def run(session,coverage,prior_data_workspace,output):
    if output.exists():raise ValueError('fresh inventory audit required')
    m=load_json(prior_data_workspace/'workspace.json')
    for name in ('constraints.json','coverage-calendar.json'):
        if m['files'][name]!=file_hash(prior_data_workspace/name):raise ValueError('old metadata workspace changed')
    cov=load_json(coverage)
    if load_json(prior_data_workspace/'coverage-calendar.json')['dates']!=cov['actual_utc_receipt_day_event_bins']:
        raise ValueError('coverage calendar differs from frozen evidence')
    workspace=session/'workspace';decision=load_json(workspace/'submitted-grid-learning-decision.json')
    if decision['action']!='select':raise ValueError('completed candidate selection required')
    selected=load_json(workspace/'frozen-grid-learning-plan.json')
    plan=load_json(workspace/'data-use-proposal.json')['plan']
    known=set(load_json(prior_data_workspace/'constraints.json')['known_opened_dates_not_fresh_holdout'])
    known.update(plan['open_train_utc_dates'])
    result=summarize(cov['actual_utc_receipt_day_event_bins'],known,selected['plan']['check_utc_dates'])
    result.update({'schema':'historical_validation_metadata_inventory_v1','session_id':session.name,
        'selected_trial_id':decision['trial_id'],'metadata_only':True,'raw_prices_or_labels_read':False,
        'new_downloads':0,'new_provider_calls':0,'new_fits':0,'controller_selected_next_dates':False,
        'input_hashes':{str(p.resolve()):file_hash(p) for p in [coverage,prior_data_workspace/'workspace.json',
            prior_data_workspace/'constraints.json',prior_data_workspace/'coverage-calendar.json',
            workspace/'frozen-grid-learning-plan.json',workspace/'data-use-proposal.json',
            workspace/'submitted-grid-learning-decision.json']},'auditor_sha256':file_hash(Path(__file__))})
    result['result_sha256']=digest(result);output.mkdir(parents=True,exist_ok=False)
    fresh_json(output/'audit.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('session','coverage','prior-data-workspace','output'):p.add_argument('--'+name,type=Path,required=True)
    print(canonical(run(**{k:v.resolve() for k,v in vars(p.parse_args()).items()})))
