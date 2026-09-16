"""Continue the stopped interface failure under published DSH1.4.1; no dispatch."""
import argparse
from pathlib import Path
from market_rsi import digest,file_hash,load_json,fresh_json
from data_scientist_harness.store import create
from data_scientist_harness.io_preflight import require_budget_resident
from paid_budget import PaidBudget
from archived_failed_source_session import verify
from prepare_temporal_feedback import unalias
from prepare_source_study_revision_workspace import merge_findings
from finding_aliases import alias_findings
from controller_dependency_preflight import inspect

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'artifacts/temporal-feedback-controller-20260913-01'
AUDIT=ROOT/'artifacts/temporal-feedback-controller-audit-20260913-01/audit.json'
PINS={'manifest':'7b07d329fec5a728698881b18e1c0183a87c7c9ba3c37b5004d0499c0b7fceaf',
    'release':'9bae3aa72e7c1e14c6ae24d6457e6cf85615c664d082a51ef4293ed6ecb5bdbb',
    'audit':'6ccfb9a39210aa74165df05e76fb3e50d903853a490959539c84aea2e518cd69'}
BUDGET=ROOT/'artifacts/kalshi-research-glm53-20260907-01/budget'
RELEASE=ROOT/'artifacts/releases/dsh-v1.4.1/release.json'
AUTH='d5bcc2d00a3b574485252693c4ba07b3a4a3ab9e083ac3bbbc1d8b30e556a8f9'


def prepare(output):
    output=Path(output).resolve()
    if output.exists():raise ValueError('fresh continuation workspace required')
    require_budget_resident(BUDGET)
    if file_hash(BUDGET/'authorization.json')!=AUTH:raise ValueError('original authorization changed')
    budget=PaidBudget(BUDGET).snapshot()
    if any(j['state']=='dispatched' and '-turn-' in k for k,j in budget['jobs'].items()):
        raise ValueError('active model dispatch; never duplicate')
    old=verify(PARENT,AUDIT,budget,PINS)
    requests=[r for r in old['records'] if r['tool']=='request_capability' and r['status']=='ok']
    if len(requests)!=1:raise ValueError('exact first recorded capability request required')
    additions=[{'id':'interface-repair-and-executable-handoff','historical_verification':old['receipt'],
        'human_change':'DSH1.4.0 to1.4.1 fixes the JSON-text parser using declared types. It does not change your scientific definitions. '
            'All three raw JSON-text replies now parse without edits; the old failed session stays failed and all costs remain.',
        'previous_successful_capability_request':requests[0]['arguments'],
        'current_task':'Finish the interrupted handoff, not a fresh search for a better score. Read and acknowledge current findings. '
            'Record research from actually-read sources as needed, run your explicit temporal probe, register the FIRST valid source-study proposal, '
            'and archive ONE executable single-object capability request, then defer. No raw data is available to this model. '
            'All earlier source findings remain historical, not new passes. The selected object from your prior request has not been opened. '
            'Do not expand to122files or repeatAug21T00. Keep or explicitly revise your own choices with reasons; reviewer chooses none.',
        'inconsistencies_to_resolve':[
            'Your prior deterministic rule says choose last anchored UNCROSSED observation, which would skip an invalid last endpoint. '
            'The typed probe chooses the last observation first, then marks an invalid endpoint unavailable. Specify one coherent behavior everywhere; '
            'do not claim the current probe tested an alternative. A different policy requires a capability and tests, not silent substitution.',
            'fresh_equal appears under unavailable reasons but a fresh equal valid endpoint should be an observed zero under your declared policy. '
            'Distinguish zero from missing and do not remove zero rows after looking at movement.',
            'Specify whether a clock regression or invalid quote inside a window invalidates the window, whether an initial snapshot anchor is required '
            'even for directly supplied BBO, how a60s lag feature is constructed, and how pending labels are closed at end-of-file. '
            'Some are outside the finite probe; say which checks remain to implement. No source/receipt clock attestation is currently available.',
            'The earlier max2GiB decoded/600s/1GiB RAM values are ceilings, not a guarantee of feasibility. '
            'Request may produce a partial diagnostic and must not be called QA pass or training.'
        ],
        'capability_format':'verification_needed is STRING and now preserves raw JSON text correctly. Put one JSON object in it, no wrapper prose. '
            'Include operation_kind, exact_objects (host,path,advertised_bytes), purpose, outputs, deterministic_rules, '
            'max_input_bytes,max_decoded_bytes,wall_seconds,memory_bytes,stop_conditions,excluded_work. '
            'Request only already-inventoried opened objects; no credentials/new downloads/purchases/production writes. '
            'New capability remains inactive until independently reviewed and tested.',
        'verification':'31 bridge tests,157 DSH tests,6-tool JSON-text actualCodex canary and18-tool standard canary passed; all synthetic/zeroTinker. '
            'These prove interface mechanics, not market-data quality or your model improvement.'},
        {'id':'budget-before-feedback-revision','budget':{k:v for k,v in budget.items() if k!='jobs'},
         'limits':'Original200, final50/repair20 protected. Olduncertain0.99967527 remains charged against cap, not called actual spend.'}]
    originals=unalias(load_json(PARENT/'findings.json'))
    findings=alias_findings(merge_findings(originals,additions,PINS['manifest']))
    dependency=inspect(RELEASE,ROOT/'artifacts/tokenizer-cache')
    manifest=create(output,quality=old['config']['quality'],findings=findings,allowed_dates=[],purpose='source_research',
        prior_archives=old['archives'],network=True,release_path=RELEASE,planning_context=old['config']['planning_context'])
    fresh_json(output/'dependency-preflight.json',dependency)
    value={'schema':'executable_source_preparation_v1','manifest_sha256':manifest,'same_harness':False,
        'harness_release_sha256':load_json(RELEASE)['release_sha256'],'historical_verification':old['receipt'],
        'findings':len(findings),'prior_findings_preserved':len(originals),'provider_calls':0,'fits':0,'source_admitted':False,
        'source_hashes':{p:file_hash(Path(__file__).with_name(p)) for p in ('prepare_executable_source_workspace.py',
            'archived_failed_source_session.py','finding_aliases.py','prepare_temporal_feedback.py','archived_source_session.py')}}
    value['result_sha256']=digest(value);fresh_json(output/'preparation.json',value)
    return value


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    r=prepare(p.parse_args().output);print({k:r[k] for k in ('manifest_sha256','result_sha256','findings','provider_calls')})
