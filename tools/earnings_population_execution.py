"""Original Native work/worker/forecast/scorer path for one frozen pool arm."""
from pathlib import Path

from earnings_entry import CapacityForecast
from earnings_open_feedback import project_target_scores
from earnings_open_task import OpenTask
from earnings_open_worker import ProgramWorker
from earnings_population import validate_result
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


def execute(case, version, slot, *, runner, context, budget, client_factory,
            study, clock, transport_policy, before_claim):
    """No retry. A claimed failure is closed only after the owner settles it."""
    capacity, pair = case['capacity'], case['pair_sha256']
    batch = capacity.batch
    work_id = 'capacity-' + digest([str(slot), version['id'], case['company']['cik']])[:32]
    before_claim(case, work_id)
    batch.record_capacity_work('claim', work_id=work_id, pair_sha256=pair,
        evidence_sha256=digest({'context': case['context'], 'slot': str(slot), 'version': version}),
        expected_state_sha256=batch.snapshot()['state_sha256'])
    worker = ProgramWorker(case['company'], case['task_id'], capacity, pair,
        batch.root.parent/'forecast-state', case['initial_state'], runner=runner)
    forecast = CapacityForecast(context, budget=budget, client_factory=client_factory,
        study_binding=study, evaluation_kernel=case['kernel'], clock_binding=clock,
        transport_policy_binding=transport_policy)
    output = forecast.forecast(worker, slot)
    task = OpenTask()
    task.kernel, task.state_api = case['kernel'], worker.state_api
    verified = task.execution(output, worker, slot)
    if verified['consumed']['pair_sha256'] != pair:
        raise ValueError('Actual original worker used a different Native pair')
    # Rejoin the logical pool identity to exact Native source receipts. Pool IDs
    # and Native manifest-pair IDs have different meanings and never substitute.
    for axis in ('R', 'H'):
        resolved = capacity.resolve(axis, expected_pair_sha256=pair)
        if resolved['receipt']['source']['sha256'] != version[axis]['sha256']:
            raise ValueError('Actual Native source differs from frozen pool arm')
    score = engine.read(output['score'])
    public = engine.save(Path(slot)/'population-public-feedback.json', {
        'schema': 'earnings_population_public_trial_v1', 'version_id': version['id'],
        'company_id': case['company']['cik'], 'points': score['score_out_of_5'],
        'target_scores': project_target_scores(score, worker.files['questions.md']),
        'pool_sources': {axis: version[axis]['sha256'] for axis in ('R', 'H')},
        'native_pair_sha256': pair, 'effective_input': engine.pin(Path(slot)/'effective-capacity.json'),
        'scope': 'Discovery trial, not adoption, untouched holdout or a predictive-gain claim'})
    batch.record_capacity_work('complete', work_id=work_id, pair_sha256=pair,
        evidence_sha256=digest(verified), expected_state_sha256=batch.snapshot()['state_sha256'])
    result = {'version_id': version['id'], 'points': score['score_out_of_5'],
              'evidence': [public, *verified['artifacts']]}
    validate_result(result)
    return result
