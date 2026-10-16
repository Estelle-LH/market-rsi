"""Prepare an isolated Native exploration context; no model call or adoption.

The resident loader and live owner retain original-data and spending authority.
This initialization is not historical Native promotion of an exploratory pool
version. Model-written programs are parsed as metadata, never executed here.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile

from earnings_entry import checked
from earnings_open_capacity import ProgramCapacity
from earnings_open_program import program
from earnings_population import version as describe
from earnings_research_state import ResearchState
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch


def prepare_case(root, resident, version, *, source_commit, authority_binding,
                 python_binding, start_utc, deadline_utc):
    """Create fresh source/state and actual Native guards, without dispatch.

    Caller must supply an original ``earnings_population_tasks.resident`` result
    and separately reviewed authority. Hash verification here never grants API
    permission or proves the source commit matches the owner's current checkout.
    Failed/consumed roots remain closed; callers preserve and diagnose failures.
    """
    root = Path(root)
    if (not root.is_absolute() or root.resolve() != root or root.exists()
            or type(source_commit) is not str or not re.fullmatch(r'[0-9a-f]{40}', source_commit)
            or type(resident) is not dict
            or set(resident) != {'company', 'runtime', 'kernel', 'data_binding', 'case'}):
        raise ValueError('Fresh canonical root, exact resident task and commit required')
    temporary_roots = (Path(tempfile.gettempdir()).resolve(), Path('/private/tmp'))
    temporary = any(location in root.parents for location in temporary_roots)
    # Keep the Native worktree/cloud/root policy intact; this constructor writes
    # nothing and rejects forbidden ancestry before this helper creates files.
    batch = ContinuousDiscoveryBatch(root/'batch', allow_temporary=temporary)
    if not temporary:
        raise ValueError('Population case contexts require owned temporary roots')
    names = ('R', 'H', 'parent', 'axis', 'method', 'author', 'evidence')
    if describe(**{name: version[name] for name in names}) != version:
        raise ValueError('Exact pool version source/parent metadata required')
    checked(authority_binding)
    engine.activation._read(python_binding, allow_alias=True)
    checked(resident['data_binding'])
    company, kernel = deepcopy(resident['company']), deepcopy(resident['kernel'])
    runtime = deepcopy(resident['runtime'])
    expected_case = {key: company[key] for key in ('cik', 'cutoff', 'target_accession', 'visible_root')}
    expected_case.update(evaluation_kernel=kernel, allowed_manifest_sha256=hashlib.sha256(
        json.dumps(company['allowed_files'], sort_keys=True, separators=(',', ':')).encode()).hexdigest())
    if (resident['case'] != expected_case or set(kernel) != {'scorer', 'qa'}
            or runtime.get('models', {}).get('gpt-6.1-sol', {}).get('api_model') != 'gpt-6.1-sol'):
        raise ValueError('Original case/kernel and fixed model runtime required')
    start = datetime.fromisoformat(start_utc.replace('Z', '+00:00'))
    deadline = datetime.fromisoformat(deadline_utc.replace('Z', '+00:00'))
    if start.tzinfo != timezone.utc or deadline.tzinfo != timezone.utc or start >= deadline:
        raise ValueError('Fixed ordered UTC case window required')
    originals = {'researcher_v0.py': checked(version['R']), 'harness_v0.py': checked(version['H']),
        'evaluation_scorer.py': checked(kernel['scorer']), 'evaluation_qa.json': checked(kernel['qa']),
        'predictor.py': checked(engine.pin(Path(__file__).resolve().parent/'edgar_forecast_openai.py'))}
    program(originals['researcher_v0.py'], 'R')
    program(originals['harness_v0.py'], 'H')
    task_id = 'population-case-'+digest([str(root), company['cik'], version['id']])[:24]
    state_api = ResearchState(company, task_id)  # Original public cutoff/file admission.
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    source = root/'source'
    source.mkdir(mode=0o700)
    for name, raw in originals.items():
        path = source/name
        with path.open('xb') as stream:
            stream.write(raw)
        path.chmod(0o600)
        if path.read_bytes() != raw:
            raise ValueError('Exact protected/source copy differs')
    initial = state_api.save(root/'initial-state', state_api.empty())
    component = lambda names, configuration: {
        'sources': {name: engine.pin(source/name)['sha256'] for name in names},
        'configuration_sha256': digest(configuration)}
    manifest = engine.identity.manifest(
        kernel=component(['evaluation_scorer.py', 'evaluation_qa.json'],
                         {'kernel': kernel, 'case': expected_case, 'data': resident['data_binding']}),
        predictor=component(['predictor.py'], {'output': 'original_five_numeric_predictions'}),
        harness=component(['harness_v0.py'], {'population_component': 'H'}),
        researcher=component(['researcher_v0.py'], {'population_component': 'R'}),
        memory=initial['sha256'], model={'requested_model': 'gpt-6.1-sol',
            'serving_snapshot': 'unknown', 'serving_snapshot_verified': False},
        runtime={'python': deepcopy(python_binding), 'dependencies': {}})
    context = engine.save(root/'context.json', {'schema': 'earnings_population_native_case_v1',
        'source_commit': source_commit, 'pool_version': deepcopy(version), 'company': company,
        'runtime': runtime, 'data': resident['data_binding'], 'kernel': kernel,
        'case': expected_case, 'authority': authority_binding, 'python': python_binding,
        'initial_state': initial, 'manifest': manifest,
        'window': {'start_utc': start_utc, 'deadline_utc': deadline_utc},
        'scope': 'Isolated exploration initialization, not population or historical Native adoption',
        'model_code_executed': False, 'provider_calls': 0, 'promotion_claimed': False})
    batch.initialize(batch_id=task_id, start_utc=start_utc, deadline_utc=deadline_utc,
        max_attempts=1, active_pool_capacity=2, learning_checkpoint_version=1,
        initial_incumbent={'candidate_id': 'isolated-exploration-context',
            'candidate_sha256': manifest['C'], 'scorecard_sha256': '0'*64, 'review_sha256': '0'*64})
    micro = {'pair': engine.activation.pair(manifest), 'fixed_context': {
        'model_sha256': manifest['M'], 'evaluation_sha256': manifest['K'],
        'data_scope_sha256': digest({'company': expected_case, 'data': resident['data_binding']}),
        'authority_sha256': digest(authority_binding), 'resource_policy_sha256': digest(runtime)},
        'allowed_write_paths': {'researcher': ['researcher_v0.py'], 'harness': ['harness_v0.py']},
        'protected_paths': ['predictor.py', 'evaluation_scorer.py', 'evaluation_qa.json'],
        'reviewer_id': 'population-independent-reviewer'}
    batch.record_micro_evolution('initialize', micro, expected_state_sha256=batch.snapshot()['state_sha256'])
    capacity = ProgramCapacity(batch, source_root=source, registry_root=root/'versions',
        baseline=manifest, entrypoints={'R': 'researcher_v0.py', 'H': 'harness_v0.py'})
    return {'capacity': capacity, 'pair_sha256': digest(micro['pair']), 'company': company,
            'kernel': kernel, 'manifest': manifest, 'source_root': source,
            'initial_state': initial, 'state_api': state_api, 'context': context, 'task_id': task_id}
