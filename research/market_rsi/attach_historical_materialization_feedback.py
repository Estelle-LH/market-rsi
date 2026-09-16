"""Bind open-Train diagnostic materialization observations to controller QA input."""
import argparse
from pathlib import Path

from historical_ingest_controller import _signed
from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json


def attach(base, materialized, output_audit, controller, output):
    identifier(output.name)
    old=load_json(base);_signed(old,'feedback_sha256')
    result=load_json(materialized/'result.json');_signed(result,'result_sha256')
    audit=load_json(output_audit/'audit.json');_signed(audit,'audit_sha256')
    proposal=load_json(controller/'workspace/frozen-data-use-proposal.json');_signed(proposal,'proposal_sha256')
    claim=load_json(materialized/'claim.json')
    if (audit['audit_pass'] is not True or result['source_scan_complete'] is not True
            or result['proposal_sha256']!=proposal['proposal_sha256']
            or audit['proposal_sha256']!=proposal['proposal_sha256']
            or audit['materialization_result_sha256']!=file_hash(materialized/'result.json')
            or audit['rows_sha256']!=result['rows_sha256']
            or claim['source_plan_sha256']!=old['source_plan_sha256']
            or result['controller_requested_utc_dates']!=proposal['plan']['open_train_utc_dates']):
        raise ValueError('matching complete local diagnostic and output audit required')
    report={k:v for k,v in old.items() if k!='feedback_sha256'}
    report['prior_data_use_review']={
        'first_controller_run':controller.name,'proposal':proposal,
        'original_session_assessment_valid':False,
        'failure':'missing_bytes_in_local_submission_receipt_preserved_separately',
        'decision_resampled':False,'diagnostic_plan_executed':True,
        'new_evidence_since_that_decision':True}
    report['open_train_materialization']={
        'evidence_class':'previously_inspected_open_train_diagnostic_only',
        'opened_utc_dates':result['controller_requested_utc_dates'],
        'row_count':result['row_count'],'rows_by_date':result['grid_rows_by_date'],
        'nonempty_observation_counts':result['nonempty_observation_counts'],
        'observation_reason_counts':result['observation_reason_counts'],
        'nominal_scope_counts':audit['nominal_scope_counts'],
        'nonempty_pm_by_nominal_scope':audit['nonempty_pm_by_nominal_scope'],
        'descriptive_adjacent_grid_midpoint_changes':audit['descriptive_adjacent_grid_midpoint_changes'],
        'nominal_window_rule':'source_slug_epoch_plus900s_not_independently_verified_settlement',
        'materialization_limits':{'max_rows':500000,'max_stored_bytes':250000000,'max_logical_bytes':1500000000},
        'storage_only_repair_verified':True,'original_partial_exact_prefix_bytes':audit['original_plain_partial_exact_prefix_bytes'],
        'forecast_target_selected':False,'dev_or_final_scores_present':False,
        'row_count_is_not_independent_sample_count':True,'training_admitted':False,
        'remaining_questions_for_controller':[
            'Is observed-arrival-interval still justified now that most grid rows precede the named15m event window?',
            'Distinguish pre-event and event-period research populations using information known at decision time; do not filter by future changes.',
            'Should this remain diagnostic-only, use a different supported causal scope, or require an explicit data-contract extension?',
            'Choose any revised data-use parameters yourself; there is no runner-selected sampling or forecast objective.',
            'Full-day update totals must not appear as early-day features; use only causal prefix/trailing information with declared windows.',
            'No evidence here proves profitability, generalization, executable prices or sufficient independent days.'],
        'not_a_retry_for_score':'new source-quality evidence after executing the first proposal; preserve all decisions'}
    report['source_artifact_sha256']={**report['source_artifact_sha256'],
        'data_use_proposal':file_hash(controller/'workspace/frozen-data-use-proposal.json'),
        'diagnostic_materialization':file_hash(materialized/'result.json'),
        'diagnostic_output_audit':file_hash(output_audit/'audit.json')}
    report['feedback_sha256']=digest(report)
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    fresh_json(output/'controller-feedback.json',report)
    fresh_json(output/'source-binding.json',{'base_feedback_sha256':file_hash(base),
        'materialization_result_sha256':file_hash(materialized/'result.json'),
        'output_audit_sha256':file_hash(output_audit/'audit.json'),
        'code_sha256':file_hash(__file__),'controller_dispatched':False,
        'new_downloads_authorized':False,'new_paid_calls':0})
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['base','materialized','output-audit','controller','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();r=attach(a.base,a.materialized,a.output_audit,a.controller,a.output)
    print(canonical({'feedback_sha256':r['feedback_sha256'],'row_count':r['open_train_materialization']['row_count'],
                     'controller_dispatched':False,'new_paid_calls':0}))
