"""Fresh DSH1.5.0 continuation; preserve1.4.1 history, do not dispatch or admit data."""
import argparse
from pathlib import Path
from market_rsi import digest,file_hash,load_json,fresh_json
from data_scientist_harness.store import create
from data_scientist_harness.io_preflight import require_budget_resident
from data_scientist_harness.sample_contract import SCHEMA
from paid_budget import PaidBudget
from archived_source_session import ArchivedSourceSession
from prepare_temporal_feedback import unalias,checked_result
from prepare_source_study_revision_workspace import merge_findings
from finding_aliases import alias_findings
from controller_dependency_preflight import inspect

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'artifacts/clock-feedback-controller-20260913-01'
AUDIT=ROOT/'artifacts/clock-feedback-controller-audit-20260913-01/audit.json'
PINS={'manifest':'72f9bbdfed56b606f0ee71a87505693dcf1d3b4aa2e228e1b7d901243461dbae',
    'proposal':'d54e550e13c5a483fec4450ae5ad4f91ef91e0b1c11832f4968b0222210f1500',
    'release':'00b7b4b6ec11aa37b88886378580b83c01483b5b6f531a526701e110d78fbcd5',
    'audit':'0a9248f13c6d160f2b1e5cf7ada762db205303c6fabda197492de285dade7e22',
    'archive':'3c93c2fb2bd8a98d23747a26bae90d03396b38421e3be2cc1fde837f46202f52'}
REVIEW=ROOT/'artifacts/clock-feedback-review-20260913-01/review.json'
REVIEW_SHA='b2f37e491ac4949db48a9f3a35e895f0964a762312193ee7fb1a6cb812a839f8'
RELEASE=ROOT/'artifacts/releases/dsh-v1.5.0/release.json'
BUDGET=ROOT/'artifacts/kalshi-research-glm53-20260907-01/budget'
AUTH='d5bcc2d00a3b574485252693c4ba07b3a4a3ab9e083ac3bbbc1d8b30e556a8f9'


def prepare(output):
    output=Path(output).resolve()
    if output.exists():raise ValueError('fresh sample-contract workspace required')
    require_budget_resident(BUDGET)
    if file_hash(BUDGET/'authorization.json')!=AUTH:raise ValueError('original authorization changed')
    budget=PaidBudget(BUDGET).snapshot()
    if any(v['state']=='dispatched' and '-turn-' in k for k,v in budget['jobs'].items()):
        raise ValueError('active or unresolved model dispatch')
    old=ArchivedSourceSession(PARENT,AUDIT,budget,PINS)
    review=checked_result(REVIEW,REVIEW_SHA)
    additions=[{'id':'typed-sample-interface-and-review','origin':'human_harness_engineering_not_model_improvement',
        'historical_verification':old.receipt,'independent_review':review,
        'old_request':old.records('request_capability')[0]['arguments'],
        'instruction':'DSH1.5.0 now exposes probe_sample_contract, a real bounded kernel, not another prose reminder. '
            'Read and acknowledge all findings. Preserve your old first proposal and failed admission unchanged. '
            'Research as needed using actual tools. Choose explicit sample rules; run BOTH temporal and sample probes '
            'and cite their exact matching successful records in the FIRST valid new source-study registration. '
            'The new typed sample fields alone are executable. Do not restate conflicting rules in prose or capability requests. '
            'Keep the final plan concise; link old evidence instead of repeating every old paragraph. '
            'You retain freedom to choose quote kinds/field extraction/clock/window/count/coverage/label policy; '
            'the runner has NOT filled any market parameters. Clearly explain changes from your rev5. '
            'For undefined ws_shot_gap either select a precise supported grid/count policy or explicitly request an unsupported method; '
            'do not silently claim the old ambiguous rule was implemented. '
            'Book direct fields do not fallback to bids/asks; choose book_levels explicitly if that is intended, or direct_bbo/exclude. '
            'Train and Check use observed label maturity, never a date alone. No baseline waiver exists. '
            'Request only ONE concrete next operation bound to the typed sample contract hash, then defer. '
            'No generic repeated data scan, original234.236host retry or invented external provenance. '
            'Source QA/input cache remain absent, and this session has no raw rows or fit permission.',
        'mechanics':'window_edges both=[decision-lookback,decision], right=(decision-lookback,decision]; '
            'minimum_observations counts selected all_records or valid_quotes ONLY in that interval. '
            'anchor query is decision-lookback; last recorded observation <=query before validity; max_gap covers anchor through decision. '
            'Extra coverage slots are decision,decision-slot_ms,...>=decision-lookback, at most1024. '
            'A slot counts only if LAST observed quote <=slot is valid and no older than tolerance; no earlier-valid skip. '
            'Coverage fraction uses integer covered*1000>=total*minimum_coverage_per_mille. '
            'anchor_and_gap_only explicitly disables additional slots with three zeros, not the feature gap checks. '
            'label_max_gap_ms=0 explicitly disables only the extra decision-to-endpoint gap test. '
            'Tail closure always needs a strictly later observation; its clock must be <cutoff for both Train and Check. '
            'day_boundary purge also applies to the closing observation. '
            'Source-clock regression rejects the canonical segment; changing to window-level purge needs a separate capability, not hidden fallback.',
        'history_access':'All parent findings and every archive visible to the parent are preserved. '
            'inspect_harness returns archive index; read_archive retrieves exact frozen text pages and logs ranges. '
            'Unread history is not discarded or claimed read. Current findings remain complete.',
        'source_admitted':False,'model_performance_claim':False},
        {'id':'budget-before-feedback-revision','budget':{k:v for k,v in budget.items() if k!='jobs'},
            'limits':'Original200; final50/repair20 protected. All historical uncertain costs/holds preserved, not called metered spend.'}]
    originals=unalias(load_json(PARENT/'findings.json'))
    findings=alias_findings(merge_findings(originals,additions,PINS['manifest']))
    archives=[r['origin'] for r in load_json(PARENT/'archive-input.json')['prior_rounds']]+[old.receipt['archive']]
    dependency=inspect(RELEASE,ROOT/'artifacts/tokenizer-cache')
    manifest=create(output,quality=old.config['quality'],findings=findings,allowed_dates=[],purpose='source_research',
        prior_archives=archives,network=True,release_path=RELEASE,planning_context=old.config['planning_context'])
    fresh_json(output/'dependency-preflight.json',dependency)
    v={'schema':'sample_contract_preparation_v1','manifest_sha256':manifest,'historical_verification':old.receipt,
        'same_harness':False,'release_sha256':load_json(RELEASE)['release_sha256'],'findings':len(findings),
        'prior_findings_preserved':len(originals),'archives_preserved':archives,'sample_schema_sha256':digest(SCHEMA),
        'provider_calls':0,'fits':0,'source_admitted':False,'new_dev_test_admitted':False,
        'preparation_sources':{n:file_hash(Path(__file__).with_name(n)) for n in ('prepare_sample_contract_workspace.py',
            'archived_source_session.py','prepare_temporal_feedback.py','finding_aliases.py','prepare_source_study_revision_workspace.py')}}
    v['result_sha256']=digest(v);fresh_json(output/'preparation.json',v);return v


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    r=prepare(p.parse_args().output);print({k:r[k] for k in ('manifest_sha256','result_sha256','findings','provider_calls')})
