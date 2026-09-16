"""Audit completed validation-design evidence without opening market data."""
import argparse
from collections import Counter
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'validation_tools')]
from controller_design import ALLOWED_TOOLS, DECISION, LOG, assess_activity
from controller_activity_log import read_activity_events
from codex_glm_responses_adapter import parse_glm_completion
from codex_glm_provider import CHAT_TEMPLATE_SHA256, HF_MODEL, TOKENIZER_REVISION
from glm_canary import MODEL, RATES
from market_rsi import canonical, digest, file_hash, fresh_json, load_json
from paid_budget import PaidBudget, money


def require(value, reason):
    if not value:
        raise ValueError(reason)


def response_calls(text):
    parsed = parse_glm_completion(text, ALLOWED_TOOLS)
    if parsed['kind'] == 'function_call':
        return [{'name': parsed['name'], 'arguments': parsed['arguments']}]
    require(parsed['kind'] == 'function_calls', 'submitted tool calls required')
    return parsed['calls']


def verify_turn(request, response, job):
    receipt = response['receipt']
    n, o, c = receipt['prompt_tokens'], receipt['output_tokens'], receipt['cache_hit_prompt_tokens']
    require(all(type(v) is int and v >= 0 for v in (n, o, c)) and c <= n, 'token counts')
    require(n == len(request['token_ids']) == request['input_tokens'] and o == len(response['tokens']),
            'saved token lengths differ')
    require(receipt['model'] == MODEL and receipt['rates'] == RATES
            and receipt['provider'] == 'tinker' and receipt['terminal'] is True, 'provider identity/rates')
    require(request['tokenizer_repo'] == HF_MODEL and request['tokenizer_revision'] == TOKENIZER_REVISION
            and request['chat_template_sha256'] == CHAT_TEMPLATE_SHA256, 'tokenizer identity')
    # Independent decimal arithmetic, not the provider's cost helper.
    charge = ((n-c)*Decimal('4.86') + c*Decimal('0.972') + o*Decimal('12.15')) / Decimal(1000000)
    require(job['state'] == 'metered_terminal' and job['bucket'] == 'learning'
            and money(job['metered_usd']) == charge == money(receipt['metered_cost_usd']), 'metered cost')
    require(job['input_sha256'] == digest(request['token_ids'])
            and job['receipt_sha256'] == digest(receipt), 'ledger receipt binding')
    return charge


def run(session, output, budget):
    require(not output.exists(), 'fresh audit ID required')
    a = load_json(session / 'session/assessment.json')
    require(a['valid'] is True and a['process_reaped'] is True and a['failed'] is False
            and a['evidence_mode'] == 'paid_controller' and a['model_authorship_proven'] is True,
            'completed real controller required')
    prep = load_json(session / 'preparation.json'); claim = load_json(session / 'dispatch-claim.json')
    require(claim['source_preparation_sha256'] == file_hash(session / 'preparation.json'), 'preparation binding')
    for name, sha in prep['source_hashes'].items():
        require(file_hash(session / 'source-snapshot' / name) == sha == file_hash(ROOT / name),
                'frozen source changed')
    require(prep['purpose'] == 'controller_design', 'fixture cannot be research')
    ws = session / 'workspace'; activity = assess_activity(ws)
    state = PaidBudget(budget).snapshot()
    require(file_hash(budget / 'authorization.json') == claim['budget_authorization_sha256'], 'budget authority')
    jobs = {k:v for k,v in state['jobs'].items() if k.startswith(session.name + '-turn-')}
    turns = sorted((session / 'session').glob('turn-*'))
    require(len(turns) == len(jobs) == a['turns'], 'exact terminal turn count')
    calls = []; charges = []; inputs = {}; prompt_tokens = output_tokens = cached_tokens = 0
    for index, directory in enumerate(turns, 1):
        turn_id = session.name + f'-turn-{index:03d}'
        request = load_json(directory / 'request.json'); response = load_json(directory / 'response.json')
        require(request['turn_id'] == turn_id, 'turn sequence')
        charges.append(verify_turn(request, response, jobs[turn_id]))
        receipt = response['receipt']; prompt_tokens += receipt['prompt_tokens']
        output_tokens += receipt['output_tokens']; cached_tokens += receipt['cache_hit_prompt_tokens']
        calls.extend(response_calls(response['text']))
        for name in ('request.json', 'response.json', 'assessment.json'):
            inputs[str(directory / name)] = file_hash(directory / name)
    events = read_activity_events(ws / LOG)
    # Tools can execute in parallel within a reply: compare exact multisets,
    # while the broker separately proves the unique terminal event is last.
    expected = Counter(canonical({'name': c['name'].removeprefix('mcp__controller_tools__'),
                                   'arguments': c['arguments']}) for c in calls)
    actual = Counter(canonical({'name': e['tool'], 'arguments': e['arguments']}) for e in events)
    require(expected == actual and len(calls) == a['tool_calls'], 'model-to-tool transcript mismatch')
    handshake = load_json(session / 'session/terminal-handshake.json')
    require(handshake['provider_called'] is False and handshake['paid_turn_added'] is False,
            'terminal acknowledgment added a provider call')
    decision = load_json(ws / DECISION)
    requests = [load_json(p / 'result.json') for p in sorted((ws / 'data-requests').iterdir())
                if (p / 'result.json').is_file()]
    inventory = load_json(ws / 'inventory.json')
    readiness = []
    for request in requests:
        body = request['body']
        later = inventory['later_than_all_known_opened_dates']
        dates_in_window = [d['utc_date'] for d in later
                           if body['earliest_utc_date'] <= d['utc_date'] <= body['latest_utc_date']]
        readiness.append({'request_id': request['artifact_id'],
            'requested_window': [body['earliest_utc_date'], body['latest_utc_date']],
            'retained_metadata_dates_in_requested_window': dates_in_window,
            'requested_download_upper_bytes_not_authorized': body['max_new_download_bytes'],
            'acquisition_executable': False,
            'remote_pinned_revision_has_requested_dates': 'not_verified',
            'coverage_threshold_is_controller_requirement_not_verified_coverage': True})
    result = {'schema': 'historical_validation_design_result_audit_v1', 'passed': True,
        'session_id': session.name, 'assessment_sha256': file_hash(session / 'session/assessment.json'),
        'decision_sha256': file_hash(ws / DECISION), 'source_files_verified': len(prep['source_hashes']),
        'activity': activity, 'action': decision['action'], 'request_readiness': readiness,
        'turns': len(turns), 'tool_calls': len(calls), 'session_metered_usd': str(sum(charges)),
        'tokens': {'prompt': prompt_tokens, 'cached_prompt': cached_tokens, 'output': output_tokens},
        'budget_snapshot': {k:v for k,v in state.items() if k != 'jobs'},
        'controller_claim_corrections': [
            'Five potential dates are after the selected April18 check window, NOT after all known exposure. '
            'Only May15 (3 event-minutes) is after the last known-opened May14 date.',
            'The new Codex/MCP interface was canary-verified before this call; the old readiness snapshot '
            'still lists adapter/canary as pending. It is not a current transport blocker.',
            'A 100GB requested ceiling is neither authority nor a proven required transfer amount. '
            'Existing download allowance remains blocked. No requested dates are retained or admitted.',
            'Presence of requested May/June data in the same pinned remote dataset revision is unverified. '
            'Do not buy or increase allowance until metadata availability and source compatibility are established.'
        ], 'inputs': inputs, 'new_provider_calls': 0, 'new_market_data_read': False,
        'new_fits': 0, 'new_downloads': 0, 'fresh_validation_result': False,
        'auditor_sha256': file_hash(Path(__file__))}
    result['result_sha256'] = digest(result)
    output.mkdir(parents=True, exist_ok=False); fresh_json(output / 'audit.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('session', 'output', 'budget'):
        parser.add_argument('--' + name, type=Path, required=True)
    result = run(**{k:v.resolve() for k,v in vars(parser.parse_args()).items()})
    print(canonical({k:v for k,v in result.items() if k not in {'inputs', 'budget_snapshot'}}))
