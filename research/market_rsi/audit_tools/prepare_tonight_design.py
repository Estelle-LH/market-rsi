"""Give the released controller current facts for tonight's first design decision.

No price/label loading, hand-selected target, source admission, model sample or
new acquisition authority. The controller must decide the research proposal.
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_rsi import digest,file_hash,fresh_json,load_json
from paid_budget import PaidBudget
from data_scientist_harness.store import create
from controller_dependency_preflight import inspect

ROOT=Path(__file__).resolve().parents[1]


def verify_dependency_receipt(previous,current):
    unsigned={k:v for k,v in previous.items() if k!='result_sha256'}
    if previous.get('result_sha256')!=digest(unsigned) or digest(unsigned)!=digest(current):
        raise ValueError('offline SDK environment changed')


def prepare(output, evidence_root, release, dependency_receipt):
    output=output.resolve(); evidence_root=evidence_root.resolve()
    if output.exists(): raise ValueError('new permanent workspace ID required')
    release=release.resolve(); dependency_receipt=dependency_receipt.resolve()
    previous=load_json(dependency_receipt)
    current=inspect(release,ROOT/'artifacts/tokenizer-cache')
    verify_dependency_receipt(previous,current)
    inv_path=evidence_root/'capture-inventory.json'; inv=load_json(inv_path)
    if inv['result_sha256']!=digest({k:v for k,v in inv.items() if k!='result_sha256'}):
        raise ValueError('capture metadata receipt changed')
    coverage_path=ROOT/'artifacts/vantage-indexed-metadata-20260910-02/conclusion.json'
    coverage=load_json(coverage_path)
    budget_path=ROOT/'artifacts/kalshi-research-glm53-20260907-01/budget'
    budget=PaidBudget(budget_path).snapshot()
    if any(v['state']=='dispatched' and '-turn-' in k for k,v in budget['jobs'].items()):
        raise ValueError('another active or unresolved model turn')
    days=[]
    for d in inv['days']:
        m=d['metadata'].get('manifest.json',{}).get('content',{})
        q=d['metadata'].get('qa_'+d['directory_date']+'.json',{}).get('content',{})
        days.append({'directory_date':d['directory_date'],'complete_day_publisher_claim':m.get('complete_day'),
            'qa_counts':q.get('counts'), 'publisher_findings':q.get('findings'),
            'file_sizes':d['files']})
    old=ROOT/'artifacts/data-science-source-controller-20260910-01/workspace'
    context=load_json(old/'context.json')
    failed_path=ROOT/'artifacts/tonight-data-scientist-design-20260910-02/session/assessment.json'
    failed=load_json(failed_path)
    if failed.get('valid') is not False or failed.get('process_reaped') is not True:
        raise ValueError('prior failed session not confirmed stopped')
    malformed_path=ROOT/'artifacts/tonight-data-scientist-design-20260910-03/session/assessment.json'
    malformed=load_json(malformed_path)
    if malformed.get('valid') is not False or malformed.get('process_reaped') is not True:
        raise ValueError('malformed-output session not confirmed stopped')
    unsubmitted_path=ROOT/'artifacts/tonight-data-scientist-design-20260910-04/session/assessment.json'
    unsubmitted=load_json(unsubmitted_path)
    if unsubmitted.get('valid') is not False or unsubmitted.get('process_reaped') is not True:
        raise ValueError('prior source-design session not confirmed stopped')
    header_path=ROOT/'artifacts/capture-schema-probe-20260911-01/report.json'
    headers=load_json(header_path)
    if headers.get('result_sha256')!=digest({k:v for k,v in headers.items() if k!='result_sha256'}):
        raise ValueError('schema evidence changed')
    semantic_path=ROOT/'artifacts/capture-semantics-review-20260911-01/report.json'
    audit_path=ROOT/'artifacts/capture-quote-audit-20260911-01/report.json'
    audit=load_json(audit_path)
    if audit.get('status')!='failed' or audit.get('exit_code')!=124 or audit.get('source_admitted') is not False:
        raise ValueError('expected immutable capped-audit failure evidence')
    split_path=ROOT/'artifacts/polymarket-rsi-round1-20260907-07/evidence/split_receipt.json'
    findings=[
        {'id':'latest-audit-terminal','report':audit,'report_sha256':file_hash(audit_path),
         'facts':'The source diagnostic has ENDED at its unchanged 1200s cap; exact local/remote '
            'processes were confirmed reaped. Seven dates completed internally, with 25,487,620 '
            'Polymarket quote rows counted; Sep09 incomplete. Detailed per-day QA aggregates were '
            'NOT preserved by the old end-only return. These counts are NOT a QA pass or independent '
            'sample count. A post-exit reader repair now flushes day aggregates and saves receipts '
            'when SSH returns or times out (8 synthetic tests pass); not rerun, not crash-durable '
            'local checkpointing, no new source admission. Choose a concrete next work order using '
            'this failure; do not wait for a nonexistent running audit or pretend the lost stats exist.'},
        {'id':'prior-source-research-unsubmitted','assessment_sha256':file_hash(unsubmitted_path),
         'accepted_research_record':load_json(unsubmitted_path.parent.parent/'records/0011.json'),
         'accepted_capability_request':load_json(unsubmitted_path.parent.parent/'records/0012.json'),
         'facts':'Session04 searched three metadata queries and read one DeepLOB abstract page. '
            'It archived a source-audit proposal but repeatedly supplied plan IDs for defer trial_id, '
            'then emitted unsubmitted narrative. No valid final decision or fit occurred. v1.2.3 '
            'documents that defer requires trial_id to be the empty string. Prior work is context, '
            'not an approved plan or source admission; retain or revise it on the new evidence yourself.'},
        {'id':'new-capture-schema-and-semantics','header_report_sha256':file_hash(header_path),
         'header_files_read':len(headers['files']),
         'schemas':[list(v) for v in sorted({tuple(f['columns']) for f in headers['files'] if 'columns' in f})],
         'semantic_report':load_json(semantic_path),'semantic_report_sha256':file_hash(semantic_path),
         'facts':'Headers are now inspected, not assumed. Source inspection is not historical provenance proof. '
            'The CSV is change-only, drops one-sided book states and rounds fields; no source admission yet. '
            'See latest-audit-terminal for the ended diagnostic and retained limits; propose the next '
            'concrete study with clearly conditional gates.'},
        {'id':'corrected-prior-data-exposure','source_sha256':file_hash(split_path),
         'old_experiment_date_blocks':load_json(split_path)['chronological_blocks'],
         'protected_interval_pending_exact_map':['2026-08-26','2026-09-06'],
         'unprotected_dates_in_your_prior_request':['2026-08-21','2026-08-22','2026-08-23','2026-08-24',
             '2026-08-25','2026-09-07','2026-09-08','2026-09-09'],
         'facts':'Previous exposure lower-bound list omitted old D10 experiments. Conservatively protect '
            'the old Aug27..Sep05 range plus one day each side until exact mapping; do not inspect hidden '
            'values or count reused periods as fresh. This is an exposure restriction, not future-movement '
            'selection. You must choose whether an honest small diagnostic remains feasible or another '
            'source/work order is required; the runner has NOT lowered your scientific requirements.'},
        {'id':'prior-malformed-output','assessment_sha256':file_hash(malformed_path),
         'facts':'v1.2.1 session03 successfully inspected and acknowledged findings, then emitted nonexistent '
            'tool names record_research-obj-1 and record_research-obj-2. Neither ran. No source plan or '
            'literature reading resulted. v1.2.2 now returns at most two explicit runner protocol-error '
            'feedback receipts; a third malformed completion stops. Calls, token budget and costs still count. '
            'Use exact tool names and actual returned record IDs. This repair does not supply a scientific answer.'},
        {'id':'prior-interface-failure','assessment_sha256':file_hash(failed_path),
         'facts':'The previous v1.2.0 design session was stopped for repeated tool-argument errors. '
            'Its schema failed to declare responses item fields id, handling, next_evidence. '
            'v1.2.1 declares them; inspect_harness provides required_finding_ids and the item schema. '
            'No valid source decision, fitted candidate, or new Dev/Test resulted. This is a documented '
            'interface repair, not a resample to obtain a preferred scientific answer. All earlier calls and costs remain.'},
        {'id':'tonight-assignment','request':
            'Design the smallest scientifically honest Polymarket prediction research cycle executable tonight. '
            'Choose the source path, Train-only data checks, objective-discovery study, temporal split, simple baseline '
            'and first controlled comparison yourself using evidence and actual literature. Do not imitate an assistant-selected '
            'target or model. This source-only session can research and propose, not train or admit data. '
            'Record a concrete plan (source, universe, sampling, target candidates, split logic, baseline, one changed layer, '
            'required evidence, stop rules and first executable work order) in your final decision reason. '
            'Use the extensible capability request if a needed operator is not available. Separate an executable '
            'opened-Train diagnostic from independent validation; never label a short or reused period as fresh final Test.',
         'user_wants_experiment_running_tonight':True,'source_admission_granted':False},
        {'id':'vantage-actual-coverage','observed':coverage,
         'evidence':{'path':str(coverage_path),'sha256':file_hash(coverage_path)},
         'instruction':'Already acquired and backed up, NOT missing acquisition. Six observed dates/617 event minutes '
            'fail the earlier 20-complete-session requirement. Do not restate it as adequate or automatically redownload.'},
        {'id':'pending-primary-and-transfer','pending_primary':{
            'dataset':'oraclemangle/polymarket-canary-tape','revision':'0f09fdb48f703d672a648c562e3f6398f45eb168',
            'filename':'polymarket-canary-tape-20260513-20260705.db.zst','compressed_bytes':5986672592,
            'decoded_bytes_from_header':61556076544,'content_not_inspected':True},
         'combined_transfer_limit_bytes':15000000000,'combined_recorded_transfer_bytes':11338004681,
         'combined_remaining_bytes':3661995319,'linode_free_bytes_observed':24241463296,
         'instruction':'No authority for extra transfers, storage purchase, deletion or benchmark reopening. '
            'Primary archive remains pending, not silently dropped. Consider other feasible sources without presuming '
            'this one failed. Proposing a change is not approving it.'},
        {'id':'existing-linode-capture-metadata','inventory':days,
         'evidence':{'path':str(inv_path),'sha256':file_hash(inv_path)},
         'instruction':'This is a newly inspected metadata-only option, not a forced source choice. '
            'D10 files may mix Kalshi and Polymarket, so venue isolation needs a real schema audit. '
            'Completeness flags and existing QA are publisher claims. This original metadata inventory '
            'did not read raw rows or labels; the later capped audit did read rows, as separately reported. '
            'Empty/header-only days, partial dates, crossed-book warnings and metadata clock repairs need separate decisions. '
            'No whole-day exclusion based on future price movement.'},
        {'id':'old-opened-research','known_opened_dates_lower_bound':context['known_opened_dates_lower_bound'],
         'old_result_scope':'Earlier OpenMarket study used April4-6 for fit and April16-18 for repeated diagnostics. '
            't7 improvement was only 0.159% MSE vs persistence on three reused days. Not final validation, not profitability.',
         'instruction':'Historical model findings are past context. Do not reuse their QA as proof for a new source. '
            'Do not select a source merely because it might make t7 score higher. Date exposure list is incomplete '
            'until source-specific exposure audit; neither new folder names nor metadata-only reads create a passed split.'},
        {'id':'funds-and-tools','budget_snapshot_not_spend':{k:v for k,v in budget.items() if k!='jobs'},
         'harness_release':load_json(release)['publication'],'offline_dependency_receipt_sha256':file_hash(dependency_receipt),
         'instruction':'Use the published harness. Existing final $50 and repair $20 buckets remain protected. '
            'No need to wait for more model money. Exact feature policies belong to the later pre-result plan. '
            'Research decisions, live reading, failures and next steps must be archived; no hidden reasoning requested.'}]
    quality_root=ROOT/'artifacts/data-science-review-20260910-02'
    quality={'spec_path':str(quality_root/'spec.json'),'spec_sha256':file_hash(quality_root/'spec.json'),
        'review_path':str(quality_root/'reviewed-checks.json'),'review_sha256':file_hash(quality_root/'reviewed-checks.json')}
    sha=create(output,quality=quality,findings=findings,allowed_dates=[],purpose='source_research',
        network=True,release_path=release)
    extra={'schema':'tonight_design_preparation_v1','workspace_sha256':sha,
        'reader_script_sha256':file_hash(Path(__file__)),
        'sdk_receipt':{'path':str(dependency_receipt),'sha256':file_hash(dependency_receipt)},
        'budget_authorization_sha256':file_hash(budget_path/'authorization.json'),
        'source_research_only':True,'model_calls':0,'fits':0,'new_market_rows_read':0}
    fresh_json(output/'preparation.json',extra)
    return extra


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--evidence-root',type=Path,required=True)
    p.add_argument('--release',type=Path,required=True)
    p.add_argument('--dependency-receipt',type=Path,required=True)
    a=p.parse_args();print(prepare(a.output,a.evidence_root,a.release,a.dependency_receipt))
