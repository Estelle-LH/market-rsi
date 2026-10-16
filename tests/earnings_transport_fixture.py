"""Fake HTTP only; exercise real capture/accounting, never the real API ledger."""
from copy import deepcopy
from pathlib import Path
import tempfile

import edgar_forecast_openai as forecast
from supervisor_harness import capacity_feedback_engine as engine

SCORER = Path('/Users/estelle/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/earnings-overnight-20261012/exact-benchmark/scripts/edgar_forecast_bench.py')


def make_kernel(root):
    return {'scorer': engine.pin(SCORER), 'qa': engine.save(root / 'protected-invented-qa.json',
        {'targets': [{'target_id': f'T{i:03d}', 'ground_truth_numeric': 100,
            'ground_truth_surface': '100', 'unit_hint': 'count',
            'scoring': {'mode': 'absolute', 'full_tolerance': 0, 'half_tolerance': 0}}
            for i in range(1, 6)]})}


def run_forecast(owner, worker, output, reply):
    output = Path(output)
    if not output.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise ValueError('Synthetic ledger may only live under an owned temporary test root')
    model = owner.rate['api_model']
    class FakeHTTP:
        def post(self, endpoint, request):
            if endpoint == '/v1/responses/input_tokens': return {'input_tokens': 1}
            if endpoint != '/v1/responses': raise ValueError('Unexpected synthetic endpoint')
            response = deepcopy(reply(deepcopy(request)))
            response.update(model=model, service_tier='default',
                usage={'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2,
                       'input_tokens_details': {'cached_tokens': 0}})
            return response
    # Synthetic unit rates; unchanged original budget/capture code executes.
    rates = dict(owner.rate, input='1', output='1', cached='1', write=None)
    config = dict(owner.config, max_input_tokens=100, max_output_tokens=128)
    budget = forecast.PilotBudget(output / 'synthetic-api-budget.sqlite3')
    try:
        return forecast.forecast(FakeHTTP(), rates, config, owner.company,
                                 budget, output, capacity_worker=worker)
    finally:
        budget.close()


def score_payload(kernel, output):
    from edgar_forecast_audit import load_scorer
    scorer, _ = load_scorer(Path(kernel['scorer']['path']))
    return scorer(predictions_payload=engine.read(engine.pin(Path(output)/'predictions.json')),
                  benchmark_qa_payload=engine.read(kernel['qa']))
