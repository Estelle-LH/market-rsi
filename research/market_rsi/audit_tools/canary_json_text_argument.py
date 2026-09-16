"""Actual Codex JSON-text tool roundtrip; scripted replies, zero Tinker/raw data."""
import argparse
from pathlib import Path
from data_scientist_harness import fixtures
from data_scientist_harness.canary import ScriptedBackend, call
from data_scientist_harness.store import create, Store
from data_scientist_harness.run_controller import run_session
from market_rsi import load_json, digest, file_hash, fresh_json
from paid_budget import PaidBudget


def run(root):
    bootstrap = root.parent / (root.name + '-bootstrap')
    fixtures.workspace(bootstrap, failed=True)
    quality = load_json(bootstrap / 'workspace.json')['quality']
    findings = [{'id':'fixture-only', 'reason':'Synthetic serialization test, no source admission'}]
    manifest = create(root, quality=quality, findings=findings, allowed_dates=[], purpose='canary', network=True)
    value = '{"operation_kind":"fixture_only","max_input_bytes":13,"execute":false}'
    backend = ScriptedBackend(findings, root)
    backend.responses = [call('inspect_harness', {}),
        call('read_public_source', {'url':'https://pandas.pydata.org/docs/reference/api/pandas.merge_asof.html','offset':0}),
        call('record_research', {'layer':'data_quality', 'question':'Synthetic text serialization check',
            'read_records':['0002'], 'applicability':'Existing asof reference; no method change',
            'limitations':'Does not validate market data', 'alternatives':'Schema-blind parsing fails for JSON text',
            'proposed_test':'Text remains text through actual Codex and broker'}),
        call('acknowledge_current_findings', {'finding_sha256':digest(findings), 'responses':[
            {'id':'fixture-only','handling':'No fitting','next_evidence':'Real source QA'}]}),
        call('request_capability', {'name':'fixture_text',
            'problem':'Serialization canary only', 'research_record':'0003',
            'evidence_refs':[{'record_id':'0002','json_pointer':'/result/read_level',
                'observed_value_json':'"delivered_text_range_not_proof_of_understanding"',
                'claim':'A bounded source text range was delivered.',
                'inference_limit':'It does not validate market data or understanding.'}],
            'proposed_interface':'Preserve a bounded JSON-looking string as text.',
            'verification_needed':value,
            'unsupported_assumptions':['No executable market capability is assumed.']}),
        call('submit_research_decision', {'action':'defer','trial_id':'',
            'reason':'fixture_text is archived only; fixture complete and no data admitted.'})]
    budget = PaidBudget.create(root/'fixture-budget', {'experiment_id':'fixture-'+root.name,
        'cap_usd':'10','target_usd':'10','buckets_usd':{'learning':'10'},'authority':'Synthetic counters; no provider'})
    assessment = run_session(root, manifest, backend, budget, 'synthetic_transport_fixture')
    records = Store(root, manifest).records()
    if not (assessment['valid'] and assessment['process_reaped'] and len(records)==6
            and all(r['status']=='ok' for r in records)
            and records[4]['arguments']['verification_needed']==value
            and records[4]['result']['proposal']['verification_needed']==value
            and records[4]['result']['activated'] is False and not (root/'trials').exists()):
        raise ValueError('JSON-text actual tool roundtrip failed')
    result = {'schema':'json_text_codex_canary_v1','passed':True,'actual_codex_cli':True,
        'scripted_model':True,'model_authorship_proven':False,'tool_calls':6,'provider_calls':0,
        'fits':0,'raw_market_rows_read':0,'capability_activated':False,'json_text_preserved':True,
        'manifest_sha256':manifest,'assessment_sha256':file_hash(root/'session/assessment.json'),
        'canary_source_sha256':file_hash(__file__)}
    result['result_sha256']=digest(result)
    fresh_json(root/'canary.json',result)
    print(result)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output.resolve())
