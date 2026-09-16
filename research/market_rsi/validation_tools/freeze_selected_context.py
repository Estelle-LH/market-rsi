"""Freeze the already-selected predictor's metadata, not a validation decision.

No controller choices are generated here. No price/label arrays are decoded,
model unpickled, money reserved, source downloaded or evaluator dispatched.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_rsi import canonical, digest, file_hash, fresh_json, load_json
from paid_budget import PaidBudget
from independent_validation import verify_context


def verify_selected_bindings(decision, trial, reconstruction, saved_plan,
                             model_file_sha256, plan_file_sha256):
    if (decision.get('action') != 'select' or decision.get('trial_id') != trial.get('trial_id')
            or reconstruction.get('selected_trial_id') != trial.get('trial_id')):
        raise ValueError('exact completed SELECT required; no DEFER continuation')
    for field in ('passed', 'all_original_prediction_arrays_identical', 'reload_predictions_identical'):
        if reconstruction.get(field) is not True:
            raise ValueError('reconstructed model equivalence not verified')
    if (saved_plan != trial['plan'] or digest(saved_plan) != reconstruction['selected_plan_sha256']
            or plan_file_sha256 != reconstruction['selected_plan_file_sha256']):
        raise ValueError('selected plan differs from frozen reconstruction')
    if model_file_sha256 != reconstruction['model_sha256']:
        raise ValueError('selected model bytes changed')


def create(root, session, reconstruction, exposure, inventory, budget_path, output):
    if output.exists():
        raise ValueError('fresh validation-context artifact required')
    bindings = {}

    def read(path):
        if path.is_symlink() or not path.is_file():
            raise ValueError('regular trusted metadata evidence required')
        before = file_hash(path)
        value = load_json(path)
        if file_hash(path) != before:
            raise ValueError('metadata changed during read')
        bindings[str(path.resolve())] = before
        return value

    def bind(path):
        if path.is_symlink() or not path.is_file():
            raise ValueError('regular frozen artifact required')
        value = file_hash(path)
        bindings[str(path.resolve())] = value
        return value

    preparation = read(session / 'preparation.json')
    for name, expected in preparation['source_hashes'].items():
        if bind(root / name) != expected or bind(session / 'source-snapshot' / name) != expected:
            raise ValueError('selected scientific source changed')
    assessment = read(session / 'session/assessment.json')
    if assessment.get('valid') is not True or assessment.get('process_reaped') is not True:
        raise ValueError('controller must be valid and terminal before validation preparation')
    ws = session / 'workspace'
    workspace_manifest = read(ws / 'workspace.json')
    if preparation['workspace_sha256'] != bindings[str((ws / 'workspace.json').resolve())]:
        raise ValueError('selected workspace manifest changed')
    decision = read(ws / 'submitted-grid-learning-decision.json')
    selected = read(ws / 'frozen-grid-learning-plan.json')
    # A trusted runner selection, never an arbitrary controller-supplied path.
    from market_rsi import identifier
    identifier(decision['trial_id'])
    trial = read(ws / 'trials' / decision['trial_id'] / 'result.json')
    if selected != trial:
        raise ValueError('selected plan differs from original trial result')
    rebuilt = read(reconstruction / 'result.json')
    reconstruction_claim = read(reconstruction / 'claim.json')
    if (rebuilt['result_sha256'] != digest({k: v for k, v in rebuilt.items() if k != 'result_sha256'})
            or rebuilt['source_session_id'] != session.name
            or rebuilt['claim_sha256'] != bind(reconstruction / 'claim.json')):
        raise ValueError('reconstruction receipt binding changed')
    if reconstruction_claim['source_preparation_sha256'] != bindings[str((session / 'preparation.json').resolve())]:
        raise ValueError('reconstruction scientific source differs')
    for path, expected in reconstruction_claim['input_hashes'].items():
        if bind(Path(path)) != expected:
            raise ValueError('original reconstruction input changed')
    saved_plan = read(reconstruction / 'selected-plan.json')
    model_sha = bind(reconstruction / 'estimator.pkl')
    verify_selected_bindings(decision, trial, rebuilt, saved_plan, model_sha,
                             bindings[str((reconstruction / 'selected-plan.json').resolve())])
    source_ws = root / 'artifacts/historical-data-use-controller-20260909-02/workspace'
    source = read(source_ws / 'source-contract.json')
    source_manifest = read(source_ws / 'workspace.json')
    if (source_manifest['files']['source-contract.json'] != bindings[str((source_ws / 'source-contract.json').resolve())]
            or source['contract_sha256'] != digest({k: v for k, v in source.items() if k != 'contract_sha256'})):
        raise ValueError('source contract changed')
    data_use = read(ws / 'data-use-proposal.json')
    if data_use['contract_sha256'] != source['contract_sha256']:
        raise ValueError('selected plan used another source contract')
    objective = read(ws / 'objective-proposal.json')
    for name in ('data-use-proposal.json', 'objective-proposal.json'):
        if workspace_manifest['files'][name] != bindings[str((ws / name).resolve())]:
            raise ValueError('selected data/objective workspace input changed')
    primary = {'primary_query_id': objective['primary_query_id'],
               'primary_metric': objective['primary_metric'],
               'spec': objective['queries'][objective['primary_query_id']]['spec']}
    audit = read(exposure)
    cover = read(inventory)
    for obj in (audit, cover):
        if obj['result_sha256'] != digest({k: v for k, v in obj.items() if k != 'result_sha256'}):
            raise ValueError('metadata audit changed')
        for path, expected in obj['input_hashes'].items():
            if bind(Path(path)) != expected:
                raise ValueError('underlying audit evidence changed')
    if audit['selected_trial_id'] != decision['trial_id'] or cover['selected_trial_id'] != decision['trial_id']:
        raise ValueError('metadata audit belongs to another selected model')
    budget = PaidBudget(budget_path).snapshot()
    snapshot = {k: v for k, v in budget.items() if k != 'jobs'}
    context = {'schema': 'historical_independent_validation_context_v1',
               'experiment_id': budget['experiment_id'], 'source_session_id': session.name,
               'budget_cap_usd': budget['cap_usd'],
               'budget_authorization_sha256': bind(budget_path / 'authorization.json'),
               'selected_trial_id': decision['trial_id'], 'model_sha256': model_sha,
               'model_artifact_is_reconstructed': True, 'selected_plan_sha256': digest(saved_plan),
               'objective_sha256': digest(primary), 'objective_contract': primary,
               'source_contract_sha256': source['contract_sha256'],
               'baseline': 'zero_probability_delta_persistence',
               'score_aggregation': saved_plan['score_aggregation'],
               'runtime_packages': rebuilt['packages'], 'minimum_final_utc_days': 20,
               'known_opened_dates_lower_bound': audit['known_open_dates_lower_bound'],
               'allow_refit': False, 'allow_target_or_feature_change': False,
               'claim_scope': 'prediction_only_not_pnl_or_rsi',
               'input_bindings_sha256': digest(bindings)}
    context['context_sha256'] = digest(context)
    verify_context(context)
    status = {'schema': 'historical_validation_preparation_status_v1',
              'created_utc': datetime.now(timezone.utc).isoformat(),
              'context_sha256': context['context_sha256'], 'controller_plan_exists': False,
              'controller_dispatch_ready': False, 'new_validation_dates_selected': [],
              'fresh_holdout_dates_admitted': [], 'execution_admitted': False,
              'remaining_gates': ['controller design tool adapter and real transport canary',
                  'complete source/exposure/whole-market review',
                  'at least twenty untouched compatible closed sessions',
                  'hash-reverified permanent cohort claim and provider budget reservation',
                  'separate download or vendor authority if acquisition is needed'],
              'exposure_audit_complete': audit['exposure_audit_complete'],
              'optimistic_existing_future_date_upper_bound': cover[
                  'potential_later_dates_excluding_known_opened_upper_bound'],
              'new_prices_or_labels_decoded': False, 'new_fits': 0, 'new_provider_calls': 0,
              'new_downloads': 0, 'model_deserialized': False,
              'budget_snapshot_not_a_reservation': snapshot,
              'source_hashes': {name: file_hash(Path(__file__).parent / name)
                  for name in ('independent_validation.py', 'freeze_selected_context.py')}}
    for path, expected in bindings.items():
        if file_hash(Path(path)) != expected:
            raise ValueError('input changed before metadata context publication')
    output.mkdir(parents=True, exist_ok=False)
    fresh_json(output / 'context.json', context)
    fresh_json(output / 'input-bindings.json', bindings)
    fresh_json(output / 'readiness.json', status)
    return {'context': context, 'readiness': status}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('root', 'session', 'reconstruction', 'exposure', 'inventory', 'budget-path', 'output'):
        parser.add_argument('--' + field, type=Path, required=True)
    print(canonical(create(**{k: v.resolve() for k, v in vars(parser.parse_args()).items()})))
