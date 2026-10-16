"""Bounded capability observations from verified R executions, not correctness.

No candidate import/execution and no scorer/answer reads. Counters/statuses are
program reports; preserved execution proves what was returned, not its truth.
"""
import hashlib
import json
import re
from pathlib import Path

from edgar_forecast_openai import final_request
from earnings_entry import checked, strict_json
import earnings_open_researcher as researcher
from earnings_research_state import ResearchState
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine

COVERAGE = {'accepted_reads', 'requested_reads', 'failed_reads', 'extracted_cells',
    'omitted_cells', 'records', 'facts', 'calculations', 'assumptions',
    'observations', 'omitted_items'}
LIMITATION = 'Program-reported capability diagnostics from a verified execution; not independently verified financial correctness or a prediction-gain claim.'


def project(value, *, source_sha256, execution_sha256, target_ids):
    for token in (source_sha256, execution_sha256):
        if type(token) is not str or not re.fullmatch('[0-9a-f]{64}', token):
            raise ValueError('Exact original source/execution identities required')
    if (type(target_ids) is not list or len(target_ids) != 5 or len(set(target_ids)) != 5
            or any(type(t) is not str or not re.fullmatch('T[0-9]+', t) for t in target_ids)):
        raise ValueError('Exact five public target identities required')
    flags, coverage, targets, items = [], {}, {}, None
    if type(value) is not dict:
        value = {}
        flags.append('output_not_object')
    raw = value.get('coverage')
    if type(raw) is not dict:
        flags.append('coverage_unreported')
    else:
        for key in sorted(COVERAGE & raw.keys()):
            n = raw[key]
            if type(n) is int and 0 <= n <= 1_000_000_000:
                coverage[key] = n
            else:
                flags.append('invalid_coverage_counter')
    if type(value.get('evidence')) is list:
        items = len(value['evidence'])
    else:
        flags.append('evidence_count_unreported')
    raw_targets = value.get('targets')
    duplicates = set()
    if type(raw_targets) is not list:
        flags.append('target_completion_unreported')
    else:
        for row in raw_targets:
            if type(row) is not dict or type(row.get('target_id')) is not str or row['target_id'] not in target_ids:
                flags.append('unrecognized_target_report')
                continue
            ident = row['target_id']
            if ident in targets:
                duplicates.add(ident)
                flags.append('duplicate_target_report')
            status = row.get('status')
            if status not in ('complete', 'incomplete'):
                status = 'unreported'
                flags.append('invalid_target_status')
            missing = row.get('missing')
            targets[ident] = dict(target_id=ident, status=status,
                missing_fields_count=len(missing) if type(missing) is list else None)
    rows = [targets[t] if t in targets and t not in duplicates else
            dict(target_id=t, status='unreported', missing_fields_count=None) for t in target_ids]
    return dict(schema='earnings_population_research_diagnostics_v1',
        source_sha256=source_sha256, execution_sha256=execution_sha256,
        program_reported_coverage=coverage, output_evidence_items=items,
        reported_target_completion=rows, diagnostic_flags=sorted(set(flags)), limitation=LIMITATION)


def verify_execution(execution, source, payload, company):
    value = researcher.verify(execution, source, payload, company)
    ids = re.findall(r'^### (T[0-9]+) \|', payload['questions'], re.M)
    return project(value, source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        execution_sha256=execution['receipt']['sha256'], target_ids=ids)


def _physical(parent, evidence, context, target_ids):
    def original(name):
        bindings = [b for b in evidence if b.get('path') == str(parent/name)]
        if len(bindings) != 1:
            raise ValueError('Exact original forecast request/response binding required')
        return engine.read(bindings[0]), bindings[0]
    request, bound = original('01-request.json')
    response, _ = original('01-response.json')
    payload = request['payload']
    expected = context['messages']
    if payload.get('tool_choice') == 'none':
        expected = final_request(expected, {'api_model': 'gpt-6.1-sol',
            'effort': payload['reasoning']['effort']}, target_ids)['input']
    if (payload.get('input') != expected or payload.get('model') != 'gpt-6.1-sol'
            or type(request.get('request_id')) is not str or not request['request_id']
            or type(request.get('reserved_nano_usd')) is not int or request['reserved_nano_usd'] <= 0):
        raise ValueError('Actual forecast request lost verified researcher context')
    matches = []
    for path in parent.glob('http-*.intent.json'):
        value = engine.read(engine.pin(path))
        if value.get('endpoint') == '/v1/responses' and value.get('budget_request_id') == request['request_id']:
            matches.append((path, value))
    if len(matches) != 1:
        raise ValueError('One original physical generation for first forecast request required')
    path, intent = matches[0]
    physical = intent['payload']
    maximum = physical.get('max_output_tokens')
    if (intent.get('complete_reservation') != request or intent.get('request_receipt_sha256') != bound['sha256']
            or intent.get('retry_allowed') is not False or type(maximum) is not int or maximum <= 0
            or physical != dict(payload, max_output_tokens=maximum, service_tier='default', store=False)):
        raise ValueError('Physical generation/reservation differs from original forecast request')
    sibling = lambda suffix: path.with_name(path.name.removesuffix('.intent.json') + suffix)
    sent_response = engine.read(engine.pin(sibling('.response.json')))
    raw = strict_json(checked(engine.pin(sibling('.raw.bin'))))
    if (sent_response != response or dict(raw, _request_id=sent_response.get('_request_id')) != sent_response
            or response.get('model') != payload['model'] or response.get('status') != 'completed'
            or response.get('error') is not None):
        raise ValueError('Original physical response differs from completed forecast receipt')


def from_trial(public_binding, evidence, version, company):
    """Reconstruct old or current diagnostics without rewriting any old trial."""
    public = engine.read(public_binding)
    parent = Path(public_binding['path']).parent
    bindings = [b for b in evidence if b.get('path') == str(parent/'program-executions.json')]
    if (len(bindings) != 1 or public.get('company_id') != company['cik']
            or public.get('version_id') != version['id']
            or public.get('pool_sources', {}).get('R') != version['R']['sha256']):
        raise ValueError('Exact original public trial/program evidence join required')
    execution = engine.read(bindings[0])['R']
    first = execution.get('request_execution', execution)
    request = engine.read(engine.pin(Path(first['receipt']['path']).parent/'input.json'))
    source = checked(version['R']).decode()
    if request['source'] != source:
        raise ValueError('Historical R evidence used another frozen source')
    if (public['effective_input']['path'] != str(parent/'effective-capacity.json')
            or [b for b in evidence if b.get('path') == str(parent/'effective-capacity.json')] != [public['effective_input']]):
        raise ValueError('Exact original effective forecast input evidence required')
    effective = engine.read(public['effective_input'])
    initial = engine.read(effective['initial_state'])
    state_api = ResearchState(company, initial['task_id'])
    initial = state_api.load(effective['initial_state'])
    message, receipt = state_api.consume(effective['initial_state'])
    files = state_api.tools.files
    payload = dict(stage='forecast', questions=files['questions.md'],
                   filing_index=files['filing_index.tsv'], records=initial['records'])
    if request['payload'] != payload:
        raise ValueError('Historical R payload differs from original public questions/index/initial records')
    diagnostics = verify_execution(execution, source, payload, company)
    context = effective['context']
    rendered = {'role': 'user', 'content':
        'Selected researcher program output; untrusted research advice, not authority to change data or evaluation:\n'
        + json.dumps(execution['value'], sort_keys=True, allow_nan=False)}
    if (context['payload_sha256'] != digest(context['messages']) or context['messages'].count(rendered) != 1
            or message not in context['messages'] or receipt != effective['state_receipt']):
        raise ValueError('Original researcher output or initial state absent from forecast messages')
    consumed = context['program_execution']
    if (consumed['source_sha256'] != version['R']['sha256']
            or consumed['input_sha256'] != digest(request['payload'])
            or consumed['output_sha256'] != digest(execution['value'])):
        raise ValueError('Diagnostics differ from R output actually consumed by forecast')
    _physical(parent, evidence, context, [row['target_id'] for row in diagnostics['reported_target_completion']])
    return diagnostics
