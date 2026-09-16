"""Continue the first valid source plan with new, independently bound clock evidence.

External preparation only: no change to DSH1.4.1, source admission or paid dispatch.
All historical findings/archive remain present. Reviewer supplies no market policy.
"""
import argparse
from pathlib import Path
from market_rsi import digest,file_hash,load_json,fresh_json
from data_scientist_harness.store import Store,create
from data_scientist_harness.source_study import current
from data_scientist_harness.io_preflight import require_budget_resident
from paid_budget import PaidBudget
from audit_data_scientist_session import audit
from prepare_temporal_feedback import unalias,checked_result
from prepare_source_study_revision_workspace import merge_findings
from finding_aliases import alias_findings
from controller_dependency_preflight import inspect

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'artifacts/temporal-executable-controller-20260913-01'
MANIFEST='e316be7fabfa1b7fa7e9802c5ee01a5081be64ebb59d978818d9636e46eb3b99'
PROPOSAL='ccd61b133a4ebe2391a3ea58e1981f75dbb229723a8ae5c7333cb20ab95cd75d'
AUDIT=ROOT/'artifacts/temporal-executable-controller-audit-20260913-01/audit.json'
AUDIT_SHA='faeb99960046d64ae645d205af404c4f054e8d76fccddb1e95fd67a38405bd30'
BUDGET=ROOT/'artifacts/kalshi-research-glm53-20260907-01/budget'
AUTH='d5bcc2d00a3b574485252693c4ba07b3a4a3ab9e083ac3bbbc1d8b30e556a8f9'
RELEASE=ROOT/'artifacts/releases/dsh-v1.4.1/release.json'
REVIEWS=(
    ('single-object-source-review-20260913-01','aadf77c63017acd1cfd137516588b81214bc50e29a3528b3e641c35aec994e36'),
    ('message-clock-origin-review-20260913-01','ba7ada697233dc73aaab1c073e6a6a3fabbbed7161429390bd4850394ce2d083'))


def feedback(reviews,proposal):
    return {'id':'real-clock-origin-and-sample-kernel-feedback',
        'origin':'human_directed_independent_review_not_controller_decision',
        'parent_manifest_sha256':MANIFEST,'parent_proposal':proposal,
        'bound_reviews':reviews,
        'new_evidence':'The SAME selected Sep08T12 current file was content-bound in two distinct diagnostics. '
            'All120 adjacent source-clock regressions occur between REST snapshot and WS price_change kinds '
            '(112 WS->REST,8 REST->WS). No within-kind regressions were observed in this file. '
            'Source timestamps before the wrapper UTC day occur only in272 REST observations. '
            'This does not attest the original collector clock, absence of outages, full-day continuity or forecasting validity. '
            'Do not interpret90.27% unchanged adjacent mids as horizon-label inactivity or independent sample size.',
        'public_research_by_execution_reviewer':[
            {'url':'https://docs.polymarket.com/api-reference/market-data/get-order-book',
             'read':'timestamp field describes snapshot time, not our collector receipt time'},
            {'url':'https://docs.polymarket.com/api-reference/wss/market',
             'read':'book,price_change,last_trade_price and best_bid_ask examples; no proof of historical collector t'},
            {'url':'https://github.com/Polymarket/py-clob-client/blob/main/py_clob_client/utilities.py',
             'read':'parse_raw_orderbook_summary preserves response timestamp; current code is not historical deployment evidence'}],
        'reference_kernel_not_activated':{
            'file':'audit_tools/causal_event_samples.py','sha256':file_hash(Path(__file__).with_name('causal_event_samples.py')),
            'tests_file_sha256':file_hash(Path(__file__).with_name('test_causal_event_samples.py')),
            'tested':'19 synthetic tests; future mutation/prefix invariance, ties, invalid last anchor/endpoint, '
                'zero vs missing, label maturity, mixed clocks/entities, regressions, gaps, day edges, probe parity',
            'input':'Explicit runner-canonical single-entity monotone segment; exact arrival key, clock domain, '
                'clock field and allowed kinds are required. No default source choice or silent filtering/sorting.',
            'feature_policy_fields':['lookback_ms','lookup_tolerance_ms','minimum_observations','max_gap_ms','same_utc_day'],
            'feature_semantics':'For each decision record, last prior anchor <=decision-lookback selected BEFORE validity. '
                'Count records in inclusive[decision-lookback,decision] using only prefix through decision key. '
                'Gap bound includes anchor through decision. Feature=current value minus anchor. '
                'These are prototype semantics, NOT automatically adopted interpretation of your earlier prose.',
            'label_semantics':'Endpoint is future label-only. Last observation <=target chosen BEFORE validity for backward-asof. '
                'A strictly later observation closes target group; maturity key/time is retained for future train-cutoff purge. '
                'Fresh valid equal endpoint gives0; no endpoint/closure gives unavailable. '
                'after_timestamp_group uses first strictly newer record as actual decision and label start. '
                'same_utc_day, if selected, includes closure. Separate X and y; future data cannot enter X.',
            'not_implemented':['raw-source adapter','full source admission','train-cutoff selection and cache integration',
                'multi-file continuity','real market samples or fitting'],
            'source_admitted':False,'fits':0},
        'current_task':'Read and acknowledge ALL findings, preserving old definitions/results. '
            'Decide explicitly which message kinds/clock domains belong in the study; the reviewer has NOT chosen WS-only or wrapper time. '
            'Clarify the exact feature window observation count, coverage and gaps, endpoint closure and train-cutoff rules. '
            'You may retain or revise your prior plan, with reasons and research receipts. '
            'Use the actual temporal probe where applicable, then register the FIRST valid revised source proposal. '
            'Archive ONE smallest executable next operation. State precisely which claim is possible with current-copy recorded events '
            'and which needs unavailable original capture evidence. Never mark missing QA as passed or require final20sessions for software tests. '
            'No generic repeat122file scan, repeatAug21T00, inaccessible234.236 host attempt, or request to repeat the just-completed diagnostics. '
            'This source-only workspace still cannot fit. Defer with the concrete operation, not a promise that training already ran.',
        'capability_format':'The old record0009 verification_needed JSON has a wrong outputs-list delimiter and incorrectly '
            'restricts future labels to past keys. It was not activated; do not claim it was fully executed. '
            'New verification_needed must be one syntactically valid JSON object encoded as STRING with operation_kind, exact_objects '
            '(host,path,advertised_bytes), purpose, outputs, deterministic_rules, max_input_bytes,max_decoded_bytes,wall_seconds,memory_bytes, '
            'stop_conditions,excluded_work. A kernel-only operation may use exact_objects=[] and synthetic inputs. '
            'Source paths must come from prior frozen opened inventory. Past-only restriction applies to prediction inputs, not future labels. '
            'Every request remains inactive until independent implementation/test/review.',
        'no_new_authority':'No raw quotes/IDs/keys/Test supplied; no new data/date/purchase/production write; original budget only.'}


def prepare(output):
    output=Path(output).resolve()
    if output.exists():raise ValueError('fresh continuation ID required')
    require_budget_resident(BUDGET)
    if file_hash(BUDGET/'authorization.json')!=AUTH:raise ValueError('original authorization changed')
    budget=PaidBudget(BUDGET).snapshot()
    if any(v['state']=='dispatched' and '-turn-' in k for k,v in budget['jobs'].items()):
        raise ValueError('active or unresolved model dispatch')
    parent=Store(PARENT,MANIFEST);parent.require_release()
    frozen=checked_result(AUDIT,AUDIT_SHA);now=audit(PARENT,BUDGET)
    for k in frozen:
        if k not in {'result_sha256','budget_snapshot'} and frozen[k]!=now[k]:raise ValueError('parent evidence changed: '+k)
    if (not now['controller_valid'] or not now['process_reaped'] or now['fits_completed']!=0
            or current(parent)!={'path':str(PARENT/'source-study-proposal.json'),'sha256':PROPOSAL}):
        raise ValueError('first valid completed source plan required')
    reviews=[]
    for name,sha in REVIEWS:
        path=ROOT/'artifacts'/name/'findings.json'
        reviews.append({'ref':{'path':str(path),'sha256':file_hash(path)},'findings':checked_result(path,sha)})
    originals=unalias(load_json(PARENT/'findings.json'))
    additions=[feedback(reviews,load_json(PARENT/'source-study-proposal.json')['proposal']),
        {'id':'budget-before-feedback-revision','budget':{k:v for k,v in budget.items() if k!='jobs'},
         'limits':'Original200; final50/repair20 protected; reserves/uncertain holds are NOT metered spend.'}]
    findings=alias_findings(merge_findings(originals,additions,MANIFEST))
    dependency=inspect(RELEASE,ROOT/'artifacts/tokenizer-cache')
    # A round archive references older history but does not embed archive-input.
    # Carry every history entry visible to the parent, not just its latest round.
    archives=[r['origin'] for r in load_json(PARENT/'archive-input.json')['prior_rounds']]
    archives.append({'path':str(PARENT/'round-archive.json'),'sha256':file_hash(PARENT/'round-archive.json')})
    manifest=create(output,quality=parent.config['quality'],findings=findings,allowed_dates=[],purpose='source_research',
        prior_archives=archives,
        network=True,release_path=RELEASE,planning_context=parent.config['planning_context'])
    fresh_json(output/'dependency-preflight.json',dependency)
    result={'schema':'clock_feedback_preparation_v1','manifest_sha256':manifest,'parent_manifest_sha256':MANIFEST,
        'parent_audit_result_sha256':AUDIT_SHA,'findings':len(findings),'prior_findings_preserved':len(originals),
        'inherited_archives_preserved':len(archives)-1,'archives_including_parent':archives,
        'same_harness':True,'harness_release_sha256':load_json(RELEASE)['release_sha256'],
        'source_hashes':{n:file_hash(Path(__file__).with_name(n)) for n in ('prepare_clock_feedback.py',
            'causal_event_samples.py','test_causal_event_samples.py','review_message_clock_origin.py')},
        'provider_calls':0,'fits':0,'source_admitted':False,'new_dev_test_admitted':False}
    result['result_sha256']=digest(result);fresh_json(output/'preparation.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    r=prepare(p.parse_args().output);print({k:r[k] for k in ('manifest_sha256','result_sha256','findings','provider_calls')})
