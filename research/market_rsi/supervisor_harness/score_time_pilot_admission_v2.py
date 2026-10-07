"""Supervisor correction: configure existing native evolution before admission."""
from datetime import datetime, timezone
from pathlib import Path
import fcntl
import json
import subprocess
import shutil
from experiments import nfl_ingame_score_time_pilot_entry_v2 as entry
from supervisor_harness import opened_train_discovery_worker as w
from supervisor_harness import coevo_pilot_transaction as transaction
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch, _digest
from data_scientist_harness.co_evolution_loop import micro_pair_hash

REPO = Path('/Users/estelle/Developer/market-rsi')
ROOT = transaction.ROOT.parent / entry.BATCH
PREFIX = 'research/market_rsi/'


def load(path):
    return json.loads(Path(path).read_text())


def configure(batch, config):
    state = batch.snapshot()
    return batch.record_micro_evolution('initialize', config,
        expected_state_sha256=state['state_sha256'])


def prepare():
    assert w.sha(ROOT / 'authorization.json') == entry.AUTH_SHA
    assert load(transaction.ROOT / 'ledger.json')['status'] == 'closed_at_attempt_cap'
    grant = load(ROOT / 'authorization.json')
    old = transaction.ROOT / 'candidate01r2'
    native = ROOT / 'native'
    native.mkdir(exist_ok=False)
    shutil.copyfile(ROOT / 'authorization.json', native / 'authorization.json')
    assert w.sha(native / 'authorization.json') == entry.AUTH_SHA
    binding = load(old / 'binding.json')
    for module in (entry,):
        path = Path(module.__file__).resolve()
        binding['dependency_source_hashes'][str(path)] = w.sha(path)
    w.save(native / 'binding.json', binding)
    memory = native / 'activation_memory.json'
    w.save(memory, load(old / 'activation_memory.json'))
    baseline = load(old / 'batch.json')
    archive_root = transaction.ROOT.parent / 'market-rsi-authorized-discovery-20261006-01'
    batch = ContinuousDiscoveryBatch(native)
    batch.initialize(batch_id=entry.BATCH, start_utc=grant['start_utc'],
        deadline_utc=grant['deadline_utc'], max_attempts=1,
        initial_incumbent={k: baseline['incumbent'][k] for k in
            ('candidate_id', 'candidate_sha256', 'scorecard_sha256', 'review_sha256')},
        active_pool_capacity=3,
        initial_archived_parents=load(archive_root / 'archive_imports.json')['archived_parents'],
        learning_checkpoint_version=1)
    old_request = load(old / 'prepared_request.json')
    config = {'pair': {'harness_sha256': _digest(binding['dependency_source_hashes']),
        'researcher_sha256': _digest({'memory': w.sha(memory), 'R_source':
            w.sha(REPO / PREFIX / 'supervisor_harness/hypothesis_differentiation_ledger_v1.py')})},
        'fixed_context': {'model_sha256': old_request['python_sha256'],
            'data_scope_sha256': _digest({'resident_train': str(w.TRAIN), 'population': 195, 'checks': 87}),
            'evaluation_sha256': binding['adapter_contract_sha256'],
            'authority_sha256': entry.AUTH_SHA, 'resource_policy_sha256': _digest(grant['limits'])},
        'allowed_write_paths': {'harness': [PREFIX + entry.MODULE.replace('.', '/') + '.py'],
            'researcher': [PREFIX + 'supervisor_harness/hypothesis_differentiation_ledger_v1.py']},
        'protected_paths': ['protected_Dev', 'protected_Final', 'minimal_prediction_loop/proper_scoring.py'],
        'reviewer_id': 'independent-score-time-trial-reviewer'}
    state = configure(batch, config)
    files = {**old_request['files']}
    for name in (entry.MODULE.replace('.', '/') + '.py',
                 'supervisor_harness/score_time_pilot_admission_v2.py',
                 'supervisor_harness/test_score_time_pilot_admission_v2.py'):
        files[PREFIX + name] = w.sha(REPO / PREFIX / name)
    request = {**old_request, 'attempt_id': 'score-time-fresh-03', 'module': entry.MODULE,
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'files': files, 'memory': str(memory), 'memory_sha256': w.sha(memory),
        'runtime_pair_sha256': micro_pair_hash(state['micro_evolution'])}
    w.validate(request, REPO)
    for name, sha in files.items():
        assert transaction.c.hashlib.sha256(subprocess.check_output(
            ['git', 'show', request['source_commit'] + ':' + name], cwd=REPO)).hexdigest() == sha
    selection = load(old / 'selection.json')
    selection.update(attempt_id=request['attempt_id'])
    selection['resource_hint']['max_cost_usd'] = 0.0
    w.save(native / 'prepared_request.json', request)
    w.save(native / 'selection.json', selection)
    w.save(native / 'evolution_configuration.json', config)
    w.save(ROOT / 'ledger.json', {'batch_id': entry.BATCH, 'status': 'open',
        'max_attempts': 1, 'fits_cap': 4, 'attempts': [], 'authorization_sha256': entry.AUTH_SHA})
    print(json.dumps({'request_sha256': w.sha(native / 'prepared_request.json'),
        'configured_evolution': True, 'fits': 0, 'claims': 0, 'selected': False}))


def freeze_ready_request():
    native = ROOT / 'native'
    request = load(native / 'prepared_request.json')
    request['source_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    request['files'] = {name: w.sha(REPO / name) for name in request['files']}
    w.validate(request, REPO)
    w.save(native / 'ready_request.json', request)


def execute(review_path):
    native = ROOT / 'native'
    request = load(native / 'ready_request.json')
    review = load(review_path)
    assert review['passed'] is True and review['authorization_sha256'] == entry.AUTH_SHA
    assert review['request_sha256'] == w.sha(native / 'ready_request.json')
    with (ROOT / '.trial.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ledger = load(ROOT / 'ledger.json')
        assert ledger['status'] == 'open' and not ledger['attempts']
        assert datetime.now(timezone.utc) < datetime.fromisoformat('2026-10-06T18:26:12+00:00')
        row = {'attempt_id': request['attempt_id'], 'fits_reserved': 4, 'actual_fits': 0,
               'status': 'reserved', 'source_commit': request['source_commit'],
               'source_review_sha256': w.sha(review_path)}
        ledger['attempts'].append(row)
        transaction._ledger(ROOT / 'ledger.json', ledger)
        try:
            batch = ContinuousDiscoveryBatch(native)
            batch.select_controller_pool([load(native / 'selection.json')])
            receipt = w.execute(batch, request, REPO)
            row.update(status=receipt['outcome'], receipt_sha256=w.sha(
                native / 'worker' / (request['attempt_id'] + '.receipt.json')))
            progress = Path(receipt['output']) / 'fit_progress.json'
            if progress.exists():
                fit = load(progress)
                row.update(actual_fits=fit['fit_calls_entered'], valid_fits_completed=fit['fit_calls_completed'])
            ledger['status'] = 'closed_at_attempt_cap'
            print(json.dumps(receipt))
        except BaseException as error:
            row.update(status='uncertain', error=str(error), no_retry=True)
            raise
        finally:
            transaction._ledger(ROOT / 'ledger.json', ledger)
