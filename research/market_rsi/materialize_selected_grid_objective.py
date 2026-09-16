"""Materialize only the completed controller's exact selected quote objectives.

This is an open-Train LABEL artifact, not a feature table or training admission.
No dates, horizons, sampling rules, weights or new scientific parameters are
chosen by this worker. Missing/quiet rows retain their original slots.
"""
import argparse
import fcntl
import math
import os
from pathlib import Path

import numpy as np

from audit_historical_objective_numerics import scalar_target
from historical_grid_objective_controller import Broker, assess_activity, read_panel
from historical_grid_objectives import profile, targets
from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json


def completed_choice(controller):
    controller = controller.resolve()
    assessment = load_json(controller / 'session/assessment.json')
    expected = {'valid': True, 'process_reaped': True, 'exit_code': 0,
                'controller_stage': 'grid_objective',
                'codex_harness_runtime_unchanged': True,
                'final_message_origin': 'codex_harness_terminal_handshake'}
    if any(assessment.get(k) != v for k, v in expected.items()):
        raise ValueError('completed valid grid-objective controller and terminal handshake required')
    workspace = controller / 'workspace'
    activity = assess_activity(workspace)
    if activity['action'] != 'select':
        raise ValueError('controller deferred; no selected objective to materialize')
    preparation = load_json(controller / 'preparation.json')
    dispatch = load_json(controller / 'dispatch-claim.json')
    if dispatch['preparation_sha256'] != file_hash(controller / 'preparation.json'):
        raise ValueError('controller dispatch/preparation binding changed')
    if (file_hash(workspace / 'workspace.json') != preparation['workspace_sha256']
            or file_hash(controller / 'prompt.txt') != preparation['prompt_sha256']):
        raise ValueError('controller frozen input or prompt changed')
    sources = preparation['source_hashes']
    required = {'historical_grid_objectives.py', 'historical_grid_objective_controller.py',
                'run_codex_glm_controller.py'}
    if not required <= set(sources):
        raise ValueError('controller source manifest is incomplete')
    source_root = Path(__file__).resolve().parent
    for name, sha in sources.items():
        if Path(name).name != name or not name.endswith('.py'):
            raise ValueError('bounded source snapshot filename required')
        if (file_hash(controller / 'source-snapshot' / name) != sha
                or file_hash(source_root / name) != sha):
            raise ValueError('frozen controller source changed; explicit adaptation required')
    choice = load_json(workspace / 'frozen-grid-objective-proposal.json')
    panel, ids, panel_result = read_panel(workspace)
    broker = Broker(workspace)
    queries = {name: broker._query(name) for name in choice['queries']}
    for query in queries.values():
        if query['engine_sha256'] != sources['historical_grid_objectives.py']:
            raise ValueError('selected query engine differs from the frozen engine')
    return choice, panel, ids, panel_result, queries, activity, sources


def prior_day_label_mask(decision_ms, label_available_ms, available, fit_at_ms):
    """Mechanical availability gate; caller must STILL specify its Train split.

    UTC dates here are the panel's declared epoch-derived research clock. A fit
    during day D cannot use any label or observation from D. Repeated calls do
    not turn already-opened dates into fresh evaluation.
    """
    if type(fit_at_ms) is not int or fit_at_ms < 0:
        raise ValueError('explicit nonnegative integer fit clock required')
    if (any(not isinstance(v, np.ndarray) or v.ndim != 1
            for v in [decision_ms, label_available_ms, available])
            or len(decision_ms) != len(label_available_ms) or len(decision_ms) != len(available)
            or available.dtype != np.dtype(bool)
            or not np.issubdtype(decision_ms.dtype, np.signedinteger)
            or not np.issubdtype(label_available_ms.dtype, np.signedinteger)
            or np.any(decision_ms < 0) or np.any(label_available_ms <= decision_ms)):
        raise ValueError('aligned future-only integer label clocks and boolean availability required')
    cutoff = fit_at_ms // 86400000 * 86400000
    return available & (decision_ms < cutoff) & (label_available_ms < cutoff)


def write_archive(path, arrays):
    """No pickle/object arrays and no overwrite; interrupted files stay forensic."""
    if any(v.dtype.hasobject for v in arrays.values()):
        raise ValueError('object arrays cannot enter the label artifact')
    partial = path.with_suffix('.partial.npz')
    with partial.open('xb') as handle:
        np.savez_compressed(handle, **arrays)
        handle.flush()
        os.fsync(handle.fileno())
    # This worker owns an exclusive fresh directory. link is still fail-if-exists.
    os.link(partial, path)
    partial.unlink()


def materialize(controller, output):
    identifier(output.name)
    if controller.resolve() == output.resolve() or controller.resolve() in output.resolve().parents:
        raise ValueError('output must not modify the completed controller directory')
    choice, panel, ids, panel_result, queries, activity, sources = completed_choice(controller)
    workspace = controller / 'workspace'
    paths = [controller / 'session/assessment.json', controller / 'preparation.json',
             controller / 'dispatch-claim.json', workspace / 'workspace.json',
             workspace / 'objective-activity.jsonl', workspace / 'frozen-grid-objective-proposal.json',
             workspace / 'submitted-grid-objective-decision.json', workspace / 'unlabelled-grid.npz']
    paths += [p for name in queries for p in [workspace / 'queries' / name / 'query.json',
                                              workspace / 'queries' / name / 'result.json']]
    before = {str(p.resolve()): file_hash(p) for p in paths}
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    claim = {'schema': 'selected_grid_objective_materialization_claim_v1',
             'controller_id': controller.name, 'proposal_sha256': choice['proposal_sha256'],
             'panel_sha256': panel_result['panel_sha256'], 'input_hashes': before,
             'controller_sources_verified': len(sources), 'controller_activity': activity,
             'worker_sha256': file_hash(__file__),
             'scalar_auditor_sha256': file_hash(Path(__file__).with_name('audit_historical_objective_numerics.py')),
             'engine_sha256': sources['historical_grid_objectives.py'],
             'primary_query_id': choice['primary_query_id'], 'primary_metric': choice['primary_metric'],
             'queries': choice['queries'], 'new_scientific_choices': False,
             'fresh_holdout': False, 'training_admitted': False, 'new_model_calls': 0}
    fresh_json(output / 'claim.json', claim)
    try:
        lookup = {(int(e), int(t)): i for i, (e, t) in enumerate(zip(panel.entity, panel.time_ms))}
        indices = set(np.linspace(0, len(ids) - 1, min(64, len(ids)), dtype=int).tolist())
        for phase in set(panel.phase):
            indices.add(int(np.flatnonzero(panel.phase == phase)[0]))
        reports = {}
        for name, query in queries.items():
            identifier(name)
            spec = query['profile']['spec']
            values = targets(panel, spec)
            observed = profile(panel, spec)
            if digest(observed) != digest(query['profile']):
                raise ValueError('selected profile does not reproduce exactly')
            for index in sorted(indices):
                scalar = scalar_target(panel, spec, index, lookup)
                vector = values['delta_probability'][index]
                if scalar is None:
                    if not np.isnan(vector):
                        raise ValueError('independent scalar missing-label disagreement')
                elif not math.isclose(scalar, float(vector), rel_tol=1e-12, abs_tol=1e-14):
                    raise ValueError('independent scalar target disagreement')
            arrays = {'row_id': ids, 'decision_ms': panel.time_ms,
                      'delta_probability': values['delta_probability'],
                      'delta_probability_bps': values['delta_probability_bps'],
                      'label_available_ms': values['label_available_ms'],
                      'available': values['available'],
                      'future_observation_count': values['future_observation_count'],
                      'reason': values['reason'].astype('U40')}
            path = output / (name + '.npz')
            write_archive(path, arrays)
            with np.load(path, allow_pickle=False) as saved:
                if set(saved.files) != set(arrays):
                    raise ValueError('label archive schema changed')
                for key, original in arrays.items():
                    np.testing.assert_array_equal(saved[key], original)
            reports[name] = {'spec': spec, 'profile_sha256': digest(observed),
                             'archive_sha256': file_hash(path), 'archive_bytes': path.stat().st_size,
                             'rows': len(ids), 'covered_rows': int(values['available'].sum()),
                             'independent_scalar_checks': len(indices),
                             'all_rows_and_order_retained': True, 'profile_exactly_reproduced': True}
        if before != {str(p.resolve()): file_hash(p) for p in paths}:
            raise ValueError('controller evidence changed while materializing')
        completed_choice(controller)  # Recheck inputs, source, activity and reused-query provenance.
        result = {'schema': 'selected_open_train_grid_labels_v1', 'complete': True,
                  'claim_sha256': file_hash(output / 'claim.json'),
                  'proposal_sha256': choice['proposal_sha256'], 'panel_sha256': panel_result['panel_sha256'],
                  'primary_query_id': choice['primary_query_id'], 'primary_metric': choice['primary_metric'],
                  'queries': reports, 'labels_only_not_features': True,
                  'training_admitted': False, 'fresh_holdout': False, 'model_evaluated': False,
                  'download_started': False, 'new_model_calls': 0,
                  'split_gate_required': 'explicit Train membership AND observation/label clocks strictly before fit UTC day'}
        result['result_sha256'] = digest(result)
        fresh_json(output / 'result.json', result)
        return result
    except Exception as exc:
        fresh_json(output / 'failure.json', {'error_type': type(exc).__name__, 'error': str(exc),
                                           'complete': False, 'training_admitted': False})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controller', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with (Path(__file__).parent / 'artifacts/historical-ingest-controller.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        value = materialize(**vars(args))
    print(canonical(value))
