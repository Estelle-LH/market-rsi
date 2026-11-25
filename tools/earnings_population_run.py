"""Prepare or execute the explicitly reviewed two-company population pilot.

Preparation is provider-free and writes immutable inputs, never a review. Run
requires the separately supplied exact review and unchanged shared owner.
"""
import argparse
from copy import deepcopy
from contextlib import closing
from datetime import datetime, timezone
import fcntl
from pathlib import Path
import re
import sqlite3
import subprocess

import earnings_entry as e
import earnings_population_window as window
from earnings_capacity_runtime import open_capacity_runtime
from earnings_night_budget import history_snapshot
from earnings_population import initialize, version, validate_result
from earnings_population_loop import run as loop
from earnings_population_runtime import (ROOT, PLAN, CONTINUATION_PLAN, CAMPAIGN_PLAN, RESUME_PLAN, CONTINUATION_AUTHORIZATION,
    EXTRA_BASELINE, EXTRA_CAP, RECOVERY_PLAN, preflight, source_paths, panel_selection)
from earnings_population_services import Services
from earnings_population_tasks import FULL_PLAN, SCORER, RUNTIME, resident, select_companies
from earnings_open_resources import ROLE_EFFORTS, role_limits, population_role_limits
from earnings_http import RawOpenAIHTTP, save_bytes
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine

OLD = e.PILOT.parent.parent/'edgar-research-objective-20261014'
ADOPTED = Path('/__LOCAL_RESEARCH_HOME__/Library/Application Support/MarketRSI/co-evo-earnings/episodes/edgar-research-20261015-09')
MANIFEST = ADOPTED/'versions/7639473675b41296abbd1a20e529d357bc544f726134ed52c6118dbc1c3e2482.json'
PYTHON = {'path': '/__LOCAL_RESEARCH_HOME__/Library/Application Support/MarketRSI/runtimes/ds-py312-20260912-01/bin/python',
          'sha256': '80ee2dd97bc26259d4e30853336f72ad38aa4aa0531bb196cc444d899422689d'}


def _feedback_contract_fields(origin, contract):
    """Preserve distinct contracts after the existing immutable origin replay."""
    from earnings_population_campaign_admission import last_scored_contract_sha256
    fields = {'initial_feedback_contract_sha256': origin['research_feedback']['campaign_contract_sha256']}
    scored = last_scored_contract_sha256(origin, contract)
    if scored is not None: fields['last_scored_contract_sha256'] = scored
    return fields


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


def prepare(identifier, *, continue_from=None, company_count=2, repair_parent=None, campaign_rejection=False,
            campaign_from=None, cumulative400=False, recover_from=None, window_minutes=90, public_predictions=False,
            training_cik=None, training_split=None, training_comparator=None, model_budget_amendment=None,
            training_stage_attachment=None, frozen_panel=None, panel_arms=None, panel_window_budget_authority=None,
            new_panel_proposal=False, review_input_policy=None, proposal_prefix_failure=None):
    if not re.fullmatch(r'edgar-population-20261016-[0-9]{2}', identifier):
        raise ValueError('Exact new population ID required')
    output = ROOT/'inputs'/identifier
    attempt = ROOT/'attempts'/identifier
    if output.exists() or attempt.exists():
        raise FileExistsError('Old inputs/attempt remain closed; no retry')
    training = any(v is not None for v in (training_cik,training_split,training_comparator,model_budget_amendment,
                                          training_stage_attachment))
    scope = None; stage_spec = None; carried_stages = None
    frozen = None; panel_fields = {}; panel_window = None
    if type(new_panel_proposal) is not bool:
        raise ValueError('Explicit boolean new-panel proposal selection required')
    review_fields = {} if review_input_policy is None else {'review_input_policy': review_input_policy}
    limits = population_role_limits(review_fields)
    if review_fields and not new_panel_proposal:
        raise ValueError('Review200k requires an explicit prospective training proposal')
    prefix_receipt = None
    if proposal_prefix_failure is not None:
        from earnings_population_proposal_completed import FAILED37, failed37_policy
        from earnings_open_resources import REVIEW200_POLICY
        if (not new_panel_proposal or review_input_policy != REVIEW200_POLICY
                or proposal_prefix_failure != FAILED37):
            raise ValueError('Only explicit Review200k may resume the exact failed37 research prefix')
        failed37_policy(identifier,company_id=training_cik)  # Before history, outputs or accounting.
    if new_panel_proposal:
        from earnings_population_runtime import PROPOSAL_AUTHORITY, PROPOSAL_ORIGIN, _local
        if (not training or frozen_panel is not None or panel_arms is not None
                or panel_window_budget_authority is not None or training_stage_attachment is not None
                or campaign_from != PROPOSAL_ORIGIN['path']):
            raise ValueError('Fresh whole25 proposal uses completed36 ancestry, never old stages or a frozen candidate')
        _local(PROPOSAL_AUTHORITY)  # Exact direct authority before outputs or accounting.
    panel_cap = 5_000_000_000
    if panel_window_budget_authority is not None:
        from earnings_population_panel_budget import AUTHORITY, PANEL_CAP, _read
        if (frozen_panel is None or not training or training_stage_attachment is not None
                or panel_window_budget_authority != AUTHORITY):
            raise ValueError('Only the exact prospective authority may opt a frozen panel into50')
        _read(AUTHORITY,Path(AUTHORITY['path']))  # Before outputs, ledger or inherited artifacts.
        panel_cap = PANEL_CAP
    if frozen_panel is None and panel_arms is not None:
        raise ValueError('Explicit frozen-panel descriptor required for an arm slice')
    if training:
        import earnings_population_training25 as training25
        if (type(company_count) is not int or company_count != 1 or not cumulative400
                or campaign_from is None or continue_from is not None or recover_from is not None
                or campaign_rejection or repair_parent is not None or type(window_minutes) is not int or window_minutes != 90
                or training_comparator is None or model_budget_amendment is None):
            raise ValueError('Training requires one explicit company/completed origin/400/model grant and90minutes')
        scope = training25.load_scope(training_split)
        training25.admit(scope,training_cik)  # BEFORE resident/content or immutable output creation.
        training25.load_comparator(scope,training_comparator)
    if frozen_panel is not None:
        from earnings_population_frozen_panel import ARMS
        if (not training or training_stage_attachment is not None
                or type(panel_arms) not in (list,type(None))):
            raise ValueError('Frozen panel requires ordinary completed training lineage, not stage reuse')
        panel_arms = list(ARMS) if panel_arms is None else panel_arms
        if not panel_arms or panel_arms != [arm for arm in ARMS if arm in panel_arms]:
            raise ValueError('Exact ordered finite frozen-panel arms required')
    if (type(company_count) is not int or not 1 <= company_count <= 2
            or type(campaign_rejection) is not bool or type(public_predictions) is not bool
            or public_predictions and (not cumulative400 or campaign_from is None and recover_from is None)
            or campaign_rejection and (continue_from is not None or repair_parent is not None)
            or repair_parent is not None and continue_from is None
            or type(cumulative400) is not bool or cumulative400 and campaign_from is None and recover_from is None
            or campaign_from is not None and (continue_from is not None or repair_parent is not None or campaign_rejection or recover_from is not None)
            or recover_from is not None and (continue_from is not None or repair_parent is not None or campaign_rejection)):
        raise ValueError('One/two preselected companies; repair requires exact prior continuation')
    window_authority = dict(window_minutes=window_minutes, companies=[None] * company_count)
    if cumulative400:
        from earnings_population_budget import amendment_binding
        window_authority['budget_amendment'] = amendment_binding()
    window.minutes(window_authority)
    baseline = idle_snapshot()
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=e.REPO, check=True,
                            capture_output=True, text=True).stdout.strip()
    paths = source_paths(model_budget=True,training=True) if training else source_paths()
    sources = {name: engine.pin(path) for name, path in paths.items()}
    for bound in sources.values():
        relative = str(Path(bound['path']).relative_to(e.REPO))
        raw = subprocess.run(['git', 'show', commit+':'+relative], cwd=e.REPO,
                             check=True, capture_output=True).stdout
        if raw != e.checked(bound):
            raise ValueError('Uncommitted bound production source; do not prepare')
    if training:
        training25.entry_plan(sources[training25.PLAN],e.REPO)
        stage_spec = training25.stage_attachment_policy(sources[training25.PLAN],repo=e.REPO,
            attempt_id=identifier,company_id=training_cik,attachment_binding=training_stage_attachment)
        if stage_spec is not None and training_stage_attachment != stage_spec['input']:
            raise ValueError('Targeted successful stages require explicit exact producer input')
        if frozen_panel is not None:
            from earnings_population_frozen_panel import POLICY, load_descriptor
            frozen = load_descriptor(frozen_panel,policy=POLICY,root=ROOT,
                ledger=e.PILOT/'api-budget.sqlite3',repo=e.REPO)
            descriptor = frozen['descriptor']
            if (descriptor['split'] != training_split or descriptor['round0']['manifest'] != training_comparator
                    or descriptor['origin']['completed_result']['path'] != str(campaign_from)):
                raise ValueError('Frozen descriptor and explicit training origin/split/Round0 differ')
    selected = engine.read(engine.pin(MANIFEST))
    if selected['manifest']['components']['R']['sources'] != {'researcher_child_01.py':
            'c3296f1b75cc10a6e67f746b0137f99f2f6765740b19f59b716acd29fa3907be'}:
        raise ValueError('Previously actually adopted stable R changed')
    engine.activation._read(PYTHON, allow_alias=True)
    inherited = None
    origin = None
    if campaign_rejection:
        import earnings_population_rejection as rejection
        origin = rejection.load_closed_review_rejection(
            {'path': str(ROOT/'attempts'/rejection.IDENT/'population-run-failure.json'),
             'sha256': rejection.FAILURE_SHA}, root=ROOT, ledger=e.PILOT/'api-budget.sqlite3', repo=e.REPO)
    if campaign_from is not None:
        from earnings_population_completed import load
        previous_path = Path(campaign_from)
        if (not previous_path.is_absolute() or previous_path.resolve() != previous_path
                or previous_path.name != 'population-run-result.json'
                or previous_path.parent.parent != ROOT/'attempts'):
            raise ValueError('Canonical owned completed campaign path required before read')
        if frozen is not None:
            if engine.pin(previous_path) != frozen['descriptor']['origin']['completed_result']:
                raise ValueError('Frozen panel requires its exact authenticated completed origin')
            origin = frozen['base_origin']
        elif training and stage_spec is not None:
            from earnings_population_recovery import load_training_stage_attachment
            carried = load_training_stage_attachment(training_stage_attachment,
                completed_result=engine.pin(previous_path),training_scope=scope,company_id=training_cik,
                attempt_id=identifier,root=ROOT,ledger=e.PILOT/'api-budget.sqlite3',repo=e.REPO,
                plan_binding=sources[training25.PLAN])
            origin, carried_stages = carried['base_origin'], carried['stage_attachment']
        else:
            origin = load(engine.pin(previous_path), root=ROOT, ledger=e.PILOT/'api-budget.sqlite3', repo=e.REPO)
    if recover_from is not None:
        from earnings_population_recovery import load, latest_failed_attempt
        failed_path = Path(recover_from)
        if (not failed_path.is_absolute() or failed_path.resolve() != failed_path
                or failed_path.name != 'population-run-failure.json'
                or failed_path.parent.parent != ROOT/'attempts'):
            raise ValueError('Canonical owned closed failure required before read')
        origin = load(engine.pin(failed_path), root=ROOT, ledger=e.PILOT/'api-budget.sqlite3',
                      repo=e.REPO, plan_binding=sources[RECOVERY_PLAN])
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
    if origin is not None and origin.get('author_stage_reuse') is not None and company_count != 1:
        raise ValueError('Successful Author review reuse permits one fresh decision only')
    if new_panel_proposal and (origin is None or origin.get('previous_result') != PROPOSAL_ORIGIN
            or origin.get('author_stage_reuse') is not None):
        raise ValueError('New whole25 Author requires authentic completed36 without stage reuse')
    if proposal_prefix_failure is not None:
        from earnings_population_proposal_completed import load_failed37_prefix
        prefix_receipt = load_failed37_prefix(proposal_prefix_failure,consumer_attempt_id=identifier,
            root=ROOT,ledger=e.PILOT/'api-budget.sqlite3',repo=e.REPO)
        if prefix_receipt['base_origin'] != origin:
            raise ValueError('Imported research must retain its authentic unchanged completed36 origin')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    continuation = None
    if origin is not None:
        state = origin['population']
    elif inherited is None:
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
    if training:
        companies = [training_cik]
    elif origin is None:
        companies = select_companies(state['exposed_companies'], company_count)
    else:
        from earnings_population_campaign import PANEL
        companies = PANEL * company_count
    tasks = [resident(cik) for cik in companies]
    runtime = tasks[0]['runtime']
    prior = engine.save(output/'original-runtime-snapshot.json',
        {'schema': 'original_runtime_snapshot_v1', 'source': RUNTIME, 'config': runtime})
    campaign_fields = {}
    if origin is not None:
        from earnings_population_campaign import VALIDATION_COMPANY, PARENT_COMPARISON
        from earnings_population_campaign_admission import scientific_contract
        from earnings_population_rejection import PARENT
        origin_binding = engine.save(output/'campaign-origin.json', origin)
        feedback = engine.save(output/'rejection-feedback.json', origin['research_feedback'])
        training_link = None
        if training:
            closed = engine.read(origin['previous_result'])['result']['result']
            training_link = engine.save(output/'training-state-link.json',training25.link_state(
                training25.POLICY,training_split,training_comparator,closed['artifacts'][0],origin['feedback'],
                panel=companies,completed_origin=origin['previous_result']))
        contract = (scientific_contract(tasks[0],training_scope=scope, **review_fields)
                    if training else scientific_contract(tasks[0]))
        manifest = engine.save(output/'campaign.json', dict(
            schema='earnings_population_campaign_v1', source_plan=sources[training25.PLAN] if training else sources[CAMPAIGN_PLAN],
            panel=companies if training else PANEL, baseline_version_id=PARENT, max_decisions=company_count,
            initial_population_sha256=digest(state), initial_feedback=feedback,
            last_scored_feedback=origin['last_scored_feedback'], contract=contract,
            validation_company_id=companies[0] if training else VALIDATION_COMPANY,
            **(training25.feedback_contracts(origin,scope) if training else _feedback_contract_fields(origin, contract)
               if recover_from is not None or campaign_from is not None else {}),
            **({'comparison_policy': PARENT_COMPARISON} if campaign_from is not None or recover_from is not None else {}),
            **({'training_state_link':training_link} if training else {})))
        campaign_fields = dict(campaign=manifest, campaign_origin=origin_binding)
        if training:campaign_fields['training_state_link'] = training_link
        if campaign_from is not None or recover_from is not None:
            parent = origin['reference_candidate']['parent']
            completed = recover_from is None and Path(origin['previous_result']['path']).parent.name != 'edgar-population-20261016-03'
            reuse = origin.get('author_stage_reuse') is not None
            controller_import = origin.get('controller_stage_import')
            capacity = origin.get('recovery_context',{}).get('mode') in {
                'author_assembly_capacity_feedback_v1','author_implementation_base_capacity_feedback_v1'}
            if capacity and (reuse or parent not in state['explorers']
                    or parent != origin['recovery_context']['failed_parent']['version_id']
                    or state['versions'][parent]['R'] != origin['recovery_context']['failed_parent']['source']):
                raise ValueError('Exact verified failed-parent/reference ancestry required')
            if not completed and not reuse and not capacity and (parent not in state['explorers'] or parent != PARENT):
                raise ValueError('Actual inherited repair parent must be the matched active baseline')
            plan_name = RECOVERY_PLAN if recover_from is not None else RESUME_PLAN
            if completed:
                from earnings_population_budget import PLAN as BUDGET_PLAN
                plan_name = BUDGET_PLAN
            if training:plan_name = training25.PLAN
            plan = engine.read(sources[plan_name])
            repair = None if recover_from is not None or completed else dict(schema='earnings_population_human_repair_v1',
                parent_version_id=parent, human_authorization=plan['human_authorization'])
            resumed = engine.save(output/'campaign-resume.json', dict(
                schema='earnings_population_campaign_resume_v1', previous_result=origin['previous_result'],
                plan=sources[plan_name], repair=repair,
                **({'prior_failed_attempt': latest_failed_attempt(origin)} if recover_from is not None else {}),
                **({'reuse_mode': origin['author_stage_reuse']['mode']} if reuse else {}),
                **({'controller_import_mode': controller_import['mode']} if controller_import is not None else {})))
            campaign_fields['campaign_resume'] = resumed
    stage_binding = (None if carried_stages is None else
                     engine.save(output/'training-stage-attachment.json',carried_stages))
    if frozen is not None:
        panel_window = dict(schema='earnings_training25_frozen_panel_window_v1',policy=POLICY,
            descriptor=deepcopy(frozen_panel),company_id=training_cik,arms=deepcopy(panel_arms),
            versions=[descriptor['members'][arm]['id'] for arm in panel_arms],
            slots=[str(attempt/'roles'/f'forecast-01-{ARMS.index(arm):02d}') for arm in panel_arms])
        panel_fields = dict(frozen_panel_policy=POLICY,frozen_panel=deepcopy(frozen_panel),
            frozen_panel_window=engine.save(output/'frozen-panel-window.json',panel_window))
        if panel_window_budget_authority is not None:
            panel_fields['panel_window_budget_authority'] = deepcopy(panel_window_budget_authority)
    proposal_fields = {}
    if new_panel_proposal:
        from earnings_population_runtime import _proposal_expected
        proposal_fields['training_proposal_task'] = engine.save(output/'training-proposal-task.json',
            _proposal_expected(scope,training_cik))
    if prefix_receipt is not None:
        proposal_fields['proposal_prefix_reuse'] = engine.save(output/'proposal-prefix-reuse.json',prefix_receipt)
    study = engine.save(output/'study.json', {'schema': 'earnings_coevolution_study_v1',
        'model': selected['manifest']['model'], 'data': FULL_PLAN, 'scorer': SCORER,
        'sole_ledger': str(e.PILOT/'api-budget.sqlite3'), 'runtime_config': runtime,
        'cases': [task['case'] for task in tasks], 'prior_batch': prior,
        **campaign_fields,
        **panel_fields,
        **proposal_fields,
        **({} if stage_binding is None else {'training_stage_attachment':stage_binding}),
        **({'continuation': continuation} if continuation is not None else {})})
    now = datetime.now(timezone.utc).replace(microsecond=0)
    value = dict(schema='earnings_population_runtime_v1', purpose='capacity_episode', id=identifier,
        source_commit=commit, root=str(attempt), ledger=str(e.PILOT/'api-budget.sqlite3'),
        baseline=baseline, window_minutes=window_minutes, additional_cap_nano_usd=panel_cap,
        rates=runtime['models']['gpt-6.1-sol'], role_efforts=ROLE_EFFORTS,
        limits=dict(limits, forecast={'max_input_tokens': runtime['max_input_tokens'],
            'max_output_tokens': runtime['max_output_tokens'], 'wall_seconds': runtime['company_wall_seconds']}),
        slots={role: [str(attempt/'roles'/f'{role}-{i:02d}') for i in (1, 2)]
               for role in ('controller', 'author', 'review')}, sources=sources,
        forecast_study=study, population_plan=sources[PLAN], initial_population=initial,
        companies=companies, original_extra_baseline=EXTRA_BASELINE,
        original_extra_cap_nano_usd=EXTRA_CAP, review=None, **review_fields)
    if cumulative400:
        value['budget_amendment'] = window_authority['budget_amendment']
        if campaign_fields.get('campaign_resume') is not None:
            from earnings_population_live_guard import POLICY
            value['validation_policy'] = POLICY
    if training:
        value.update(training_policy=training25.POLICY,model_budget_amendment=deepcopy(model_budget_amendment))
    value.update(panel_fields)
    if new_panel_proposal:
        from earnings_population_runtime import PROPOSAL_POLICY
        value['training_proposal_policy'] = PROPOSAL_POLICY
    if prefix_receipt is not None:
        value['proposal_prefix_reuse'] = proposal_fields['proposal_prefix_reuse']
    if public_predictions:
        from earnings_population_public_predictions import POLICY, runtime_policy
        value['public_feedback_policy'] = POLICY
        runtime_policy(value, engine.read(study))
    value.update(window.bounds(now, value))
    value['slots']['forecast'] = [str(attempt/'roles'/f'forecast-{i:02d}-{arm:02d}')
                                  for i in (1, 2) for arm in range(3)]
    if panel_window is not None:value['slots']['forecast'] = panel_window['slots']
    bound = engine.save(output/'runtime-unreviewed.json', value)
    preflight(bound, require_review=False)
    return bound


def execute(binding):
    config = preflight(binding)
    idle_snapshot()
    services = Services(binding, native_root=Path('/private/tmp')/('market-rsi-'+config['id']), python_binding=PYTHON)
    services.start_utc = window.start_utc(config)
    root = Path(config['root'])
    study = engine.read(config['forecast_study'])
    panel = 'frozen_panel_policy' in config
    proposal = 'training_proposal_policy' in config
    clean_task = None
    if 'clean_slate_policy' in config:
        from earnings_population_clean_slate import read_task
        clean_task, _ = read_task(config)
        proposal = clean_task['mode'] in ('proposal','repair_review')
    measured = []
    continuation, campaign = study.get('continuation'), study.get('campaign')
    repair = None if continuation is None else engine.read(continuation).get('repair')
    def admit(_):
        if proposal and _.get('round_index') == 1 and _.get('stage') == 'execute':
            return False  # No new claim/action; original Review exit and owner closure still validate.
        preflight(binding)
        services.dependencies['budget'].active()
        if (campaign is None and repair is not None and _.get('round_index') == 1 and _.get('stage') == 'execute'
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
            if clean_task is not None and clean_task['mode']=='repair_review':
                from earnings_population_clean_slate import repair_review
                result=repair_review(services,live,clean_task)
            elif clean_task is not None and not proposal:
                from earnings_population_clean_slate import load_frozen
                candidate = load_frozen(clean_task['frozen_candidate'])['candidate']
                from earnings_population_company_batch import enabled as batch_enabled, run as batch_run
                if batch_enabled(config):
                    measured.extend(batch_run(services,live,candidate))
                else:
                    services.current = clean_task['company_id']
                    row = live['roles']['forecast'](deepcopy(candidate),services.current,config['slots']['forecast'][0])
                    validate_result(row)
                    measured.append(dict(arm='candidate',company_id=services.current,result=deepcopy(row)))
                result = dict(companies=config['companies'],results=measured,
                    descriptor=clean_task['frozen_candidate'])
            elif panel:
                for slot in config['slots']['forecast']:
                    selected = panel_selection(config,slot)
                    services.current = selected['company_id']
                    row = live['roles']['forecast'](deepcopy(selected['version']),selected['company_id'],slot)
                    validate_result(row)
                    if row['version_id'] != selected['version']['id']:
                        raise ValueError('Frozen-panel forecast returned another version')
                    measured.append(dict(arm=selected['arm'],result=deepcopy(row)))
                result = dict(descriptor=config['frozen_panel'],window=config['frozen_panel_window'],
                    company_id=config['companies'][0],results=measured)
            else:
                result = loop(root, engine.read(config['initial_population']), config['companies'],
                              live['roles'], admit=admit, max_rounds=len(config['companies']),
                              **({} if clean_task is None else {'initial_feedback':clean_task['feedback']}),
                              **({} if campaign is None else {'campaign': campaign}))
            stages = []
            accepted = False
            if clean_task is not None and clean_task['mode']=='repair_review':
                stages=[result];record=engine.read(result)
                accepted=record['review']['accepted_for_exploration'] is True
            elif proposal:
                if result != dict(status='stopped',completed_rounds=0,round_index=1,stage='execute'):
                    raise ValueError('Proposal must stop after four original stages before forecast claim')
                from supervisor_harness.feedback_linked_loop import _read_pair
                for stage in ('input','controller','implement','source_review'):
                    path=root/'loop'/('round-0001-'+stage+'.done.json')
                    stages.append(engine.pin(path));_read_pair(path)
                child=_read_pair(Path(stages[2]['path']))['output']['candidate']
                review=_read_pair(Path(stages[3]['path']))['output']
                accepted=child is not None and review['accepted_for_exploration'] is True
            budget_summary = live['budget'].summary()
        if proposal:
            return engine.save(root/'training-proposal-result.json',dict(
                schema='earnings_training25_proposal_result_v1',runtime=binding,
                status='PROPOSAL_REVIEWED_ACCEPTED' if accepted else 'PROPOSAL_NOT_ACCEPTED',
                result=result,proposal_stages=stages,budget=budget_summary,
                improvement_proven=False,retry_allowed=False))
        return engine.save(root/('clean-slate-window-result.json' if clean_task is not None else
            'frozen-panel-window-result.json' if panel else 'population-run-result.json'), dict(
            **(dict(schema='earnings_training25_clean_slate_window_result_v1',runtime=binding) if clean_task is not None else {}),
            **(dict(schema='earnings_training25_frozen_panel_window_result_v1',runtime=binding) if panel else {}),
            status=('COMPLETED_CLEAN_SLATE_CANDIDATE_WINDOW' if clean_task is not None else
                'COMPLETED_FROZEN_PANEL_WINDOW' if panel else 'COMPLETED_DISCOVERY_PILOT'),
            result=result, budget=budget_summary, improvement_proven=False, retry_allowed=False))
    except BaseException as error:
        closure = None
        batch_failure=None
        if 'clean_company_concurrency' in config and (root/'company-batch-execution.json').is_file():
            batch_failure=engine.pin(root/'company-batch-execution.json')
            original_batch=engine.read(batch_failure)
            if original_batch.get('runtime')!=binding:raise ValueError('Another batch failure receipt') from error
            measured=deepcopy(original_batch['completed_results'])
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
        engine.save(root/('training-proposal-failure.json' if proposal else
            'clean-slate-window-failure.json' if clean_task is not None else
            'frozen-panel-window-failure.json' if panel else 'population-run-failure.json'), dict(
            **(dict(schema='earnings_training25_proposal_failure_v1',runtime=binding) if proposal else {}),
            **(dict(schema='earnings_training25_clean_slate_window_failure_v1',runtime=binding,
                clean_slate_task=study['clean_slate_task'],completed_results=measured,
                company_batch=batch_failure,
                successful_cells_preserved_not_rerunnable=True,
                selection_allowed=False,
                receiving_boundary='Successful public scores/checkpoints retained, NOT NOT_MEASURED or zero. Failed batch must stop for original owner/fee/Native/physical closure audit; no automatic next wave or replay of scored cells.') if clean_task is not None and not proposal else {}),
            **(dict(schema='earnings_training25_frozen_panel_window_failure_v1',runtime=binding,
                descriptor=config['frozen_panel'],window=config['frozen_panel_window'],completed_results=measured) if panel else {}),status='FAILED_NO_RETRY',
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
    parser.add_argument('--campaign-from-rejection', action='store_true')
    parser.add_argument('--campaign-from', metavar='CLOSED_CAMPAIGN_RESULT_JSON')
    parser.add_argument('--recover-from', metavar='CLOSED_FIRST_REVIEW_FAILURE_JSON')
    parser.add_argument('--cumulative400', action='store_true')
    parser.add_argument('--window-minutes', type=int, choices=(90, 180), default=None)
    parser.add_argument('--public-predictions', action='store_true')
    parser.add_argument('--training-company', metavar='FROZEN_TRAINING_CIK')
    parser.add_argument('--training-split', metavar='FROZEN_SPLIT_JSON')
    parser.add_argument('--training-comparator', metavar='COMPLETE25_PLAIN_COMPARATOR_JSON')
    parser.add_argument('--model-budget-amendment', metavar='ACTIVATED_NAMED_MODEL_GRANT_JSON')
    parser.add_argument('--training-stage-attachment', metavar='AUTHORIZED_CLOSED_SUCCESSFUL_STAGES_JSON')
    parser.add_argument('--frozen-panel', metavar='AUTHENTICATED_FROZEN_PANEL_JSON')
    parser.add_argument('--panel-arms', nargs='+', choices=('control','parent','candidate'))
    parser.add_argument('--panel-window-budget-authority', metavar='EXACT_DIRECT_PANEL50_AUTHORITY_JSON')
    parser.add_argument('--new-panel-proposal', action='store_true')
    parser.add_argument('--review-input-policy', choices=('review_input_200000_v1',))
    parser.add_argument('--proposal-prefix-failure', metavar='EXACT_FAILED37_JSON')
    parser.add_argument('--clean-slate', action='store_true')
    parser.add_argument('--clean-frozen-candidate', metavar='NEW_CLEAN_FROZEN_DESCRIPTOR_JSON')
    parser.add_argument('--clean-batch-companies',nargs='+',metavar='TRAINING_CIK')
    parser.add_argument('--clean-repair-review',metavar='EXACT_ONCE_REPAIR_RECEIPT_JSON')
    args = parser.parse_args()
    if args.prepare:
        if args.preflight_only:
            parser.error('--preflight-only applies to --runtime')
        if args.clean_slate:
            if (args.training_company is None or args.continue_from or args.campaign_from or args.recover_from
                    or args.repair_parent or args.campaign_from_rejection or args.frozen_panel or args.panel_arms
                    or args.training_stage_attachment or args.proposal_prefix_failure or args.new_panel_proposal
                    or args.window_minutes not in (None,90) or args.panel_window_budget_authority
                    or args.training_split or args.training_comparator or args.model_budget_amendment
                    or args.review_input_policy or args.cumulative400 or args.public_predictions or args.companies != 2):
                parser.error('Clean-slate uses only fresh ID, explicit training company and optional new frozen candidate')
            from earnings_population_clean_slate import prepare as clean_prepare
            print(clean_prepare(args.prepare,company_id=args.training_company,
                frozen_candidate=None if args.clean_frozen_candidate is None else engine.pin(Path(args.clean_frozen_candidate)),
                batch_companies=args.clean_batch_companies,
                repair=None if args.clean_repair_review is None else engine.pin(Path(args.clean_repair_review))))
        elif args.clean_frozen_candidate is not None or args.clean_batch_companies is not None or args.clean_repair_review is not None:
            parser.error('Clean frozen candidate/batch requires --clean-slate')
        else:
            print(prepare(args.prepare, continue_from=args.continue_from,
                      company_count=args.companies, repair_parent=args.repair_parent,
                      campaign_rejection=args.campaign_from_rejection, campaign_from=args.campaign_from,
                      cumulative400=args.cumulative400, recover_from=args.recover_from,
                      window_minutes=90 if args.window_minutes is None else args.window_minutes,
                      public_predictions=args.public_predictions,training_cik=args.training_company,
                      training_split=None if args.training_split is None else engine.pin(Path(args.training_split)),
                      training_comparator=None if args.training_comparator is None else engine.pin(Path(args.training_comparator)),
                      model_budget_amendment=None if args.model_budget_amendment is None else engine.pin(Path(args.model_budget_amendment)),
                      training_stage_attachment=None if args.training_stage_attachment is None else engine.pin(Path(args.training_stage_attachment)),
                      frozen_panel=None if args.frozen_panel is None else engine.pin(Path(args.frozen_panel)),panel_arms=args.panel_arms,
                      panel_window_budget_authority=None if args.panel_window_budget_authority is None else engine.pin(Path(args.panel_window_budget_authority)),
                      new_panel_proposal=args.new_panel_proposal,review_input_policy=args.review_input_policy,
                      proposal_prefix_failure=None if args.proposal_prefix_failure is None else engine.pin(Path(args.proposal_prefix_failure))))
    else:
        if (args.continue_from is not None or args.repair_parent is not None
                or args.companies != 2 or args.campaign_from_rejection or args.campaign_from is not None
                or args.cumulative400 or args.recover_from is not None or args.window_minutes is not None
                or args.public_predictions or args.training_company is not None or args.training_split is not None
                or args.training_comparator is not None or args.model_budget_amendment is not None
                or args.training_stage_attachment is not None or args.frozen_panel is not None or args.panel_arms is not None
                or args.panel_window_budget_authority is not None or args.new_panel_proposal
                or args.review_input_policy is not None or args.proposal_prefix_failure is not None
                or args.clean_slate or args.clean_frozen_candidate is not None or args.clean_batch_companies is not None
                or args.clean_repair_review is not None):
            parser.error('Continuation/company selection applies only to fresh --prepare')
        bound = engine.pin(Path(args.runtime))
        print({'preflight': 'PASS'} if args.preflight_only and preflight(bound) else execute(bound))
