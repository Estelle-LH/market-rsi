# Source excerpt. Imports and other methods are omitted.

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
