"""Trusted offline verification of captured originals with the unchanged scorer.

Originals show the source-bound transport path, not independent provider/model
authenticity or OS containment. No network, credentials, payment or rewriting.
"""
from copy import deepcopy
from pathlib import Path
import re

import earnings_entry as entry
from edgar_forecast_audit import load_scorer
from edgar_forecast_openai import final_request, digest
from supervisor_harness import capacity_feedback_engine as engine


def kernel(binding, questions):
    if type(binding) is not dict or set(binding) != {'scorer', 'qa'}:
        raise ValueError('Explicit protected scorer and QA bindings required')
    for value in binding.values():
        if type(value) is not dict or set(value) != {'path', 'sha256'}:
            raise ValueError('Exact protected kernel artifact binding required')
        entry.checked(value)
    scorer, sha = load_scorer(Path(binding['scorer']['path']))
    if sha != binding['scorer']['sha256']: raise ValueError('Scorer changed during loading')
    qa = entry.strict_json(entry.checked(binding['qa']).decode())
    targets = re.findall(r'^### (T\d+) \|', questions, re.M)
    if (len(targets) != 5 or len(set(targets)) != 5
            or [row['target_id'] for row in qa['targets']] != targets):
        raise ValueError('Protected QA does not match the original five questions')
    return scorer, qa, targets


def verify(output, worker, slot, binding):
    scorer, qa, targets = kernel(binding, worker.files['questions.md'])
    root, artifacts = Path(slot), []
    def original(name):
        path = root / name
        bound = engine.pin(path)
        if bound['path'] != str(path): raise ValueError('Physical original outside exact slot')
        artifacts.append(bound)
        return entry.strict_json(entry.checked(bound).decode())
    result = engine.read(output['result'])
    turns = result.get('turns')
    if type(turns) is not int or not 1 <= turns <= 24:
        raise ValueError('Bounded completed turn originals required')
    for suffix in ('request', 'response', 'count'):
        expected = [f'{n:02d}-{suffix}.json' for n in range(1, turns+1)]
        if sorted(p.name for p in root.glob(f'[0-9][0-9]-{suffix}.json')) != expected:
            raise ValueError('Exact consecutive physical turn originals required')
    history = deepcopy(worker.context['messages'])
    model = worker.capacity.baseline['model']['requested_model']
    seen, tools, tool_names = set(), 0, set()
    for turn in range(1, turns+1):
        count = original(f'{turn:02d}-count.json')
        receipt = original(f'{turn:02d}-request.json')
        response = original(f'{turn:02d}-response.json')
        payload = receipt['payload']
        if (type(receipt.get('reserved_nano_usd')) is not int or receipt['reserved_nano_usd'] <= 0
                or type(receipt.get('request_id')) is not str or not receipt['request_id']
                or receipt['request_id'] in seen or payload.get('model') != model
                or response.get('model') != model or response.get('service_tier') != 'default'
                or response.get('status') != 'completed' or response.get('error') is not None):
            raise ValueError('Original request/reservation/model/completion differs')
        seen.add(receipt['request_id'])
        usage = response['usage']
        numbers = [count['input_tokens'], usage['input_tokens'], usage['output_tokens'],
                   usage['total_tokens'], usage['input_tokens_details']['cached_tokens']]
        if (any(type(n) is not int or n < 0 for n in numbers)
                or numbers[1] > numbers[0] or numbers[3] != numbers[1]+numbers[2]
                or numbers[4] > numbers[1]):
            raise ValueError('Original counted/reserved usage differs')
        expected = history
        if payload.get('tool_choice') == 'none':
            expected = final_request(history, {'api_model': model,
                'effort': payload['reasoning']['effort']}, targets)['input']
        elif payload.get('tools') != worker.definitions:
            raise ValueError('Original worker tool definitions differ')
        if payload.get('input') != expected:
            raise ValueError('Physical request lost selected capacity/state or prior outputs')
        items = response['output']
        history.extend(items)
        calls = [row for row in items if row.get('type') == 'function_call']
        if turn == turns:
            predictions = entry.strict_predictions(response, targets)
            if predictions != original('predictions.json'):
                raise ValueError('Saved predictions differ from raw original final response')
        else:
            if not calls or payload.get('tool_choice') == 'none':
                raise ValueError('Intermediate original did not request work')
            for call in calls:
                name = f"{turn:02d}-tool-{digest(call['call_id'].encode())[:12]}.json"
                observed = original(name)
                if (observed.get('type') != 'function_call_output'
                        or observed.get('call_id') != call['call_id'] or type(observed.get('output')) is not str):
                    raise ValueError('Original tool result does not close exact call')
                history.append(observed); tools += 1; tool_names.add(name)
    research_calls=0
    from earnings_open_worker import ProgramWorker
    if type(worker) is ProgramWorker:
        from earnings_open_researcher import verify as verify_researcher, evidence_rows
        verify_researcher(worker.r_execution,worker._source('R'),worker.r_payload,worker.state_api.company)
        research_calls=len(evidence_rows(worker.r_execution))
    if (set(p.name for p in root.glob('[0-9][0-9]-tool-*.json')) != tool_names
            or result.get('tool_calls') != tools+research_calls or worker.calls != tools+research_calls):
        raise ValueError('Actual tool count/originals differ')
    actual = scorer(predictions_payload=predictions, benchmark_qa_payload=qa)
    if (engine.read(output['score']) != actual or result.get('points') != actual['score_out_of_5']
            or result.get('planned_targets') != 5 or result.get('scored_targets') != 5):
        raise ValueError('Original scorer/result mismatch; originals preserved')
    return artifacts + list(binding.values())
