"""Prepare or execute the explicitly reviewed two-company population pilot.

Preparation is provider-free and writes immutable inputs, never a review. Run
requires the separately supplied exact review and unchanged shared owner.
"""
import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import fcntl
from pathlib import Path
import re
import sqlite3
import subprocess

import earnings_entry as e
from earnings_capacity_runtime import open_capacity_runtime
from earnings_night_budget import history_snapshot
from earnings_population import initialize, version
from earnings_population_loop import run as loop
from earnings_population_runtime import (ROOT, PLAN, CONTINUATION_PLAN, CONTINUATION_AUTHORIZATION,
    EXTRA_BASELINE, EXTRA_CAP, preflight, source_paths)
from earnings_population_services import Services
from earnings_population_tasks import FULL_PLAN, SCORER, RUNTIME, resident, select_companies
from earnings_open_resources import ROLE_EFFORTS, role_limits
from earnings_http import RawOpenAIHTTP, save_bytes
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine

OLD = e.PILOT.parent.parent/'edgar-research-objective-20261014'
ADOPTED = Path('/Users/estelle/Library/Application Support/MarketRSI/co-evo-earnings/episodes/edgar-research-20261015-09')
MANIFEST = ADOPTED/'versions/7639473675b41296abbd1a20e529d357bc544f726134ed52c6118dbc1c3e2482.json'
PYTHON = {'path': '/Users/estelle/Library/Application Support/MarketRSI/runtimes/ds-py312-20260912-01/bin/python',
          'sha256': '80ee2dd97bc26259d4e30853336f72ad38aa4aa0531bb196cc444d899422689d'}


def idle_snapshot():
    """Read-only accounting and momentary nonblocking shared-lock observation."""
    ledger = e.PILOT/'api-budget.sqlite3'
    with closing(sqlite3.connect(ledger.as_uri()+'?mode=ro', uri=True)) as db:
        db.execute('BEGIN')
        if db.execute("SELECT COUNT(*) FROM requests WHERE status NOT IN ('settled','settled_upper_bound')").fetchone()[0]:
            raise RuntimeError('Pending shared fees; no new allocation or model call')
        baseline = history_snapshot(db)
    lock = ledger.parent/'.capacity-runtime.lock'
    # Do not create/modify a foreign lock; shared ownership is acquired again
    # atomically by the original owner immediately before any paid role.
    with lock.open('rb') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(stream, fcntl.LOCK_UN)
    return baseline


def prepare(identifier, *, continue_from=None, company_count=2, repair_parent=None):
    if not re.fullmatch(r'edgar-population-20261016-[0-9]{2}', identifier):
        raise ValueError('Exact new population ID required')
    output = ROOT/'inputs'/identifier
    attempt = ROOT/'attempts'/identifier
    if output.exists() or attempt.exists():
        raise FileExistsError('Old inputs/attempt remain closed; no retry')
    if type(company_count) is not int or not 1 <= company_count <= 2 or repair_parent is not None and continue_from is None:
        raise ValueError('One/two preselected companies; repair requires exact prior continuation')
    baseline = idle_snapshot()
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=e.REPO, check=True,
                            capture_output=True, text=True).stdout.strip()
    sources = {name: engine.pin(path) for name, path in source_paths().items()}
    for bound in sources.values():
        relative = str(Path(bound['path']).relative_to(e.REPO))
        raw = subprocess.run(['git', 'show', commit+':'+relative], cwd=e.REPO,
                             check=True, capture_output=True).stdout
        if raw != e.checked(bound):
            raise ValueError('Uncommitted bound production source; do not prepare')
    selected = engine.read(engine.pin(MANIFEST))
    if selected['manifest']['components']['R']['sources'] != {'researcher_child_01.py':
            'c3296f1b75cc10a6e67f746b0137f99f2f6765740b19f59b716acd29fa3907be'}:
        raise ValueError('Previously actually adopted stable R changed')
    engine.activation._read(PYTHON, allow_alias=True)
    inherited = None
    if continue_from is not None:
        from earnings_population_continuation import load
        previous_path = Path(continue_from)
        if (not previous_path.is_absolute() or previous_path.resolve() != previous_path
                or previous_path.name != 'population-run-result.json'
                or previous_path.parent.parent != ROOT/'attempts'
                or not re.fullmatch(r'edgar-population-20261016-[0-9]{2}', previous_path.parent.name)):
            raise ValueError('Exact canonical owned completed result path required before read')
        previous = engine.pin(previous_path)
        inherited = load(previous, root=ROOT, ledger=e.PILOT/'api-budget.sqlite3', repo=e.REPO)
        if repair_parent is not None and repair_parent not in inherited['population']['explorers']:
            raise ValueError('Repair parent must be an actual inherited active explorer')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    continuation = None
    if inherited is None:
        stable = {}
        for axis, name in selected['entrypoints'].items():
            old = {'path': str(ADOPTED/'source'/name),
                   'sha256': selected['manifest']['components'][axis]['sources'][name]}
            save_bytes(output/(axis+'.py'), e.checked(old))
            stable[axis] = engine.pin(output/(axis+'.py'))
        audit = engine.pin(OLD/'ACTUAL09-FINAL-REVIEW.json')
        state = initialize(version(**stable, method='Previously adopted R09/H; operational anchor, not proven strongest',
            author='historical model R / historical H', evidence=[engine.pin(MANIFEST), audit]),
            {'K': digest({'data': FULL_PLAN, 'scorer': SCORER}),
             'M': selected['manifest']['M'], 'C': engine.pin(e.REPO/'tools/edgar_forecast_openai.py')['sha256']},
            exposed_companies=['CIK0000003545'])
    else:
        state = inherited['population']
        continuation = engine.save(output/'continuation.json', dict(
            schema='earnings_population_continuation_v1', previous_result=previous,
            population_sha256=digest(state), feedback=inherited['feedback'], evidence=inherited['evidence'],
            plan=sources[CONTINUATION_PLAN], repair=None if repair_parent is None else dict(
                schema='earnings_population_human_repair_v1', parent_version_id=repair_parent,
                human_authorization=CONTINUATION_AUTHORIZATION)))
    initial = engine.save(output/'initial-population.json', state)
    companies = select_companies(state['exposed_companies'], company_count)
    tasks = [resident(cik) for cik in companies]
    runtime = tasks[0]['runtime']
    prior = engine.save(output/'original-runtime-snapshot.json',
        {'schema': 'original_runtime_snapshot_v1', 'source': RUNTIME, 'config': runtime})
    study = engine.save(output/'study.json', {'schema': 'earnings_coevolution_study_v1',
        'model': selected['manifest']['model'], 'data': FULL_PLAN, 'scorer': SCORER,
        'sole_ledger': str(e.PILOT/'api-budget.sqlite3'), 'runtime_config': runtime,
        'cases': [task['case'] for task in tasks], 'prior_batch': prior,
        **({'continuation': continuation} if continuation is not None else {})})
    now = datetime.now(timezone.utc).replace(microsecond=0)
    utc = lambda t: t.strftime('%Y-%m-%dT%H:%M:%SZ')
    value = dict(schema='earnings_population_runtime_v1', purpose='capacity_episode', id=identifier,
        source_commit=commit, root=str(attempt), ledger=str(e.PILOT/'api-budget.sqlite3'),
        baseline=baseline, cutoff_utc=utc(now+timedelta(minutes=90)),
        deadline_utc=utc(now+timedelta(minutes=90, seconds=60)), additional_cap_nano_usd=5_000_000_000,
        rates=runtime['models']['gpt-6.1-sol'], role_efforts=ROLE_EFFORTS,
        limits=dict(role_limits(), forecast={'max_input_tokens': runtime['max_input_tokens'],
            'max_output_tokens': runtime['max_output_tokens'], 'wall_seconds': runtime['company_wall_seconds']}),
        slots={role: [str(attempt/'roles'/f'{role}-{i:02d}') for i in (1, 2)]
               for role in ('controller', 'author', 'review')}, sources=sources,
        forecast_study=study, population_plan=sources[PLAN], initial_population=initial,
        companies=companies, original_extra_baseline=EXTRA_BASELINE,
        original_extra_cap_nano_usd=EXTRA_CAP, review=None)
    value['slots']['forecast'] = [str(attempt/'roles'/f'forecast-{i:02d}-{arm:02d}')
                                  for i in (1, 2) for arm in range(3)]
    bound = engine.save(output/'runtime-unreviewed.json', value)
    preflight(bound, require_review=False)
    return bound


def execute(binding):
    config = preflight(binding)
    idle_snapshot()
    services = Services(binding, native_root=Path('/private/tmp')/('market-rsi-'+config['id']), python_binding=PYTHON)
    services.start_utc = (datetime.fromisoformat(config['cutoff_utc'].replace('Z', '+00:00'))
                          - timedelta(minutes=90)).strftime('%Y-%m-%dT%H:%M:%SZ')
    root = Path(config['root'])
    continuation = engine.read(config['forecast_study']).get('continuation')
    repair = None if continuation is None else engine.read(continuation).get('repair')
    def admit(_):
        preflight(binding)
        services.dependencies['budget'].active()
        if (repair is not None and _.get('round_index') == 1 and _.get('stage') == 'execute'
                and not _['outputs']['source_review']['accepted_for_exploration']):
            raise ValueError('Assigned repair failed independent review; no redundant old-version forecasts')
        return True
    try:
        with open_capacity_runtime(binding, client_factory=lambda: RawOpenAIHTTP(e.credential(), 600),
                                   role_factories=services.factories()) as live:
            services.clock, services.dependencies = live['clock_binding'], live
            services.start_execution()
            services.transport_policy = engine.save(root/'transport-policy.json', {
                'schema': 'edgar_foreground_slow_call_policy_v1', 'source_commit': config['source_commit'],
                'original_runtime_request_timeout_seconds': engine.read(config['forecast_study'])['runtime_config']['request_timeout_seconds'],
                'effective_socket_timeout_seconds': 600, 'role_and_global_deadlines_unchanged': True, 'retry_allowed': False})
            result = loop(root, engine.read(config['initial_population']), config['companies'],
                          live['roles'], admit=admit, max_rounds=len(config['companies']))
            budget_summary = live['budget'].summary()
        return engine.save(root/'population-run-result.json', dict(status='COMPLETED_DISCOVERY_PILOT',
            result=result, budget=budget_summary, improvement_proven=False, retry_allowed=False))
    except BaseException as error:
        closure = None
        if services.pending:
            from earnings_native_failure import close_failed_work
            case, work_id = services.pending[-1]
            try:
                closure = close_failed_work(case['capacity'].batch, runtime_binding=binding,
                    work_id=work_id, pair_sha256=case['pair_sha256'], output_root=root/'native-failure',
                    error_type=type(error).__name__)
            except Exception as closure_error:
                closure = {'status': 'UNRESOLVED_NO_RETRY', 'error_type': type(closure_error).__name__}
        # No pre-clock writes. If the owner itself failed before making a root,
        # preserve that original failure now, rather than masking it on save.
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        engine.save(root/'population-run-failure.json', dict(status='FAILED_NO_RETRY',
            error_type=type(error).__name__, native_closure=closure, retry_allowed=False))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', metavar='NEW_ID')
    group.add_argument('--runtime', metavar='REVIEWED_JSON')
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--continue-from', metavar='CLOSED_RESULT_JSON')
    parser.add_argument('--companies', type=int, choices=(1, 2), default=2)
    parser.add_argument('--repair-parent', metavar='INHERITED_EXPLORER_ID')
    args = parser.parse_args()
    if args.prepare:
        if args.preflight_only:
            parser.error('--preflight-only applies to --runtime')
        print(prepare(args.prepare, continue_from=args.continue_from,
                      company_count=args.companies, repair_parent=args.repair_parent))
    else:
        if args.continue_from is not None or args.repair_parent is not None or args.companies != 2:
            parser.error('Continuation/company selection applies only to fresh --prepare')
        bound = engine.pin(Path(args.runtime))
        print({'preflight': 'PASS'} if args.preflight_only and preflight(bound) else execute(bound))
