# Source excerpt. Imports and other methods are omitted.

def research_task(value):
    if followup_round(value.get('clean_learning_round')):
        origin=round2_origin(value)
        from earnings_population_root_reentry import is_root,context
        if is_root(origin):
            root=context(origin)
            return (f"Continue the SAME experiment at global logical{origin['logical_round']}/root-child{origin['root_child_ordinal']} from original unscored R0/H0 "
                f"{origin['parent']['id']}. Its score is NULL, not the saved plain Round0 mean3.00. "
                'Read complete latest25 public outcomes, separate saved baseline3.00 and prediction champion3.18, '
                'current enforced memory, all12 negative lessons and later technical failure lessons. Carry evidence '
                'and reusable lessons, not descendant code by default. Test the declared distinct R/H hypothesis '
                'through original Controller/Author/Review with minimal final-assembled-file checks. Freeze one '
                'accepted R/H over all25 before the next scientific candidate. A lower full25 score is still valid '
                'feedback; a technical failure leaves the hypothesis untested. Only strict full25 improvement over '
                'saved baseline AND champion adopts; ties/worse keep the champion. No baseline/completed-company '
                'rerun, new population, history/memory/budget reset, resource or retry increase, answer hardcoding, '
                'heldout access or field/test/tool-count-as-learning claim. Training reuse is Discovery, not '
                'generalization. One root and16 planned slots are a disclosed search-origin exception, not a '
                'standard3-parent layer,16 funded children or promised first-round gain. Declared test: '
                +json.dumps(root['contract'],sort_keys=True))
        specific=''
        if frontier_round(origin['logical_round']):
            from earnings_population_coevolution import declared_test
            specific=' Declared prospective frontier test (support/refutation are criteria, not assumed results): '+json.dumps(declared_test(origin),sort_keys=True)
        return (f"Continue logical Round{origin['logical_round']} from the actual selected R/H code parent "
            f"{origin['parent']['id']} (complete25 mean{origin['prior_mean']}). Read ALL latest25 public feedback "
            "and the separate actual-parent and prediction-incumbent feedback plus observed activation/coverage diagnostics. "
            "Rejected candidate modifications are lessons, NOT the code parent. Choose one testable transferable R or H "
            "change using available literature/tools; preserve useful parent behavior. Do not force a parser fix, "
            "particular strategy, both axes, adoption or promised gain. Freeze the resulting R/H once for all25; "
            "strictly greater complete25 company-equal mean adopts, tie/worse retains parent. No baseline/parent rerun, "
            "answer hardcoding, changed model/resources/budget/data/scorer/cutoff or heldout access. "
            "Feedback reuse is Discovery, not generalization; human rolling8 is not autonomous H improvement."
            + (f" For continuous rounds, adoption must ALSO beat the separately saved best incumbent mean{origin['incumbent_mean']}; "
               "The selected code parent is not necessarily the prediction incumbent. A provisional frontier seat is not prediction adoption; "
               "new children are prospective, never backfilled historical branches. Group completion/count never stops useful research."
               if continuous_round(value['clean_learning_round']) else '')+specific)
    return ROUND2_TASK if second_round(value) else TASK


def selection(manager, role, args, kwargs):
    """Independent current role selection; never call a legacy campaign loader."""
    from earnings_population_runtime import _local
    task, scope = read_task(manager.value)
    slot = Path(args[-1])
    if kwargs or str(slot) not in manager.value['slots'][role]: raise ValueError('Exact clean role slot required')
    if task['mode']=='repair_review':
        fixed=repair_metadata(task['repair'],manager.value['id'])
        if role!='review' or args!=(fixed['candidate'],repair_state(task,fixed),str(slot)):
            raise ValueError('Repair permits exactly one original Review, no C/A/forecast')
        version=fixed['candidate'];company=task['company_id'];packet_binding=None
    elif task['mode'] == 'evaluate':
        if role != 'forecast' or len(args) != 3: raise ValueError('Candidate-only frozen evaluation')
        version = load_frozen(task['frozen_candidate'])['candidate']
        company=task['company_ids'][manager.value['slots']['forecast'].index(str(slot))]
        if args[:2] != (version,company): raise ValueError('Frozen candidate/company substitution')
        packet_binding = None
    else:
        packet_binding = engine.pin(manager.root/'packet-01.json'); packet = _local(packet_binding)
        if (packet['company_id'] != task['company_id'] or packet.get('round_index') != 1
                or packet['feedback'] != task['feedback'] or packet['population'] != task['scaffold']):
            raise ValueError('Clean proposal packet feedback/state differs')
        origin=round2_origin(manager.value) if second_round(manager.value) else None
        parent=selected_parent(packet['population'],origin)
        if role == 'controller':
            if len(args) != 2 or args[0] != packet: raise ValueError('Controller packet substitution')
            version = parent
        elif role == 'author':
            from earnings_population_technical_retry import for_runtime, verify_controller_route
            technical = for_runtime(manager.value)
            feedback_sha = (digest(task['feedback']) if technical is None else
                verify_controller_route(manager.binding,manager.value['slots']['controller'][0],
                    packet=packet,chosen=args[0])['scientific_feedback_sha256'])
            if len(args) != 3 or args[1] != packet['population'] or args[0]['feedback_sha256'] != feedback_sha:
                raise ValueError('Author feedback/state substitution')
            version = packet['population']['versions'][args[0]['parent_pair_sha256']]
            # Services.author prepares the original registered Native record.
            # selected_parent already authenticates the exact descriptor and
            # any historical incumbent anchor projection without rewriting it.
            if version['id']!=parent['id'] or any(version[a]!=parent[a] for a in ('R','H')):
                raise ValueError('Author replaced the selected actual parent')
        elif role == 'review':
            if len(args) != 3 or args[1] != packet['population'] or args[0]['parent'] != parent['id']:
                raise ValueError('Review child/scaffold substitution')
            version = args[0]
        else: raise ValueError('Proposal cannot forecast scaffold or candidate')
    if version['id'] != digest({a:version[a]['sha256'] for a in ('R','H')}): raise ValueError('Source identity differs')
    company=task['company_id'] if task['mode'] in ('proposal','repair_review') else company
    resident = tasks.resident(training.admit(scope,company))
    saved = _local(manager.value['forecast_study'])
    bindings = [manager.binding,manager.value['forecast_study'],manager.value['initial_population'],
        manager.value['population_plan'],manager.value['review'],saved['clean_slate_task'],task['feedback'],
        SPLIT,ROUND0,manager.value['model_budget_amendment'],tasks.FULL_PLAN,tasks.METADATA,tasks.MANIFEST,
        tasks.RUNTIME,tasks.SCORER,resident['kernel']['qa'],version['R'],version['H']]
    if 'research_memory' in task:
        bindings += [task['research_memory'],*task['research_memory_predecessor'].values()]
    from earnings_population_docker_profile import metadata as docker_profile_metadata
    profile=docker_profile_metadata(manager.value,task)
    if profile is not None:bindings += profile['bindings']
    if packet_binding is not None: bindings.append(packet_binding)
    from earnings_population_technical_retry import for_runtime, verify_controller_route
    technical = for_runtime(manager.value)
    if technical is not None:
        # Keep the new finite authority and original science proofs in the
        # existing current HTTP guard, not only a one-time setup check.
        bindings += technical['evidence']
        if role in ('author','review'):
            bindings += verify_controller_route(manager.binding,
                manager.value['slots']['controller'][0])['evidence']
    if task['frozen_candidate'] is not None: bindings += frozen_inputs(task['frozen_candidate'])
    if second_round(manager.value):
        origin=round2_origin(manager.value)
        from earnings_population_root_reentry import is_root,context
        root_context=context(origin) if is_root(origin) else None
        bindings += [task['round2_origin'],origin['public_feedback'],origin['prior_comparison'],origin['prior_stable']]
        bindings += root_context['bindings'] if root_context else [origin['prior_descriptor']]
        if followup_round(manager.value.get('clean_learning_round')):
            bindings += [origin[k] for k in (('direct_authority',) if root_context else ('parent_feedback','parent_comparison','direct_authority'))]
        if manager.value.get('clean_learning_round')==5:bindings.append(STABLE03A_YIELD_AUTHORITY)
        if manager.value.get('clean_learning_round')==6:
            bindings += [STABLE03A_ROUND6_YIELD_AUTHORITY,origin['group_progress'],origin['previous_complete_checkpoint']]
        if manager.value.get('clean_learning_round')==7:
            bindings += [STABLE03A_ROUND7_YIELD_AUTHORITY,origin['group_progress'],origin['previous_complete_checkpoint']]
        if continuous_round(manager.value.get('clean_learning_round')):
            from earnings_population_coevolution import yield_authority
            bindings += [yield_authority(manager.value),origin['previous_complete_checkpoint'],
                *[origin[k] for k in ('incumbent_descriptor','incumbent_comparison','incumbent_feedback','group_start_stable','carried_population')]]
            if frontier_round(manager.value['clean_learning_round']):
                from earnings_population_coevolution import expansion
                claim=expansion(origin)
                bindings += [origin['frontier_expansion'],claim['frontier']]
                frontier=engine.read(claim['frontier'])
                if root_context:
                    bindings += root_context['bindings']
                    if role in ('author','review'):
                        from earnings_population_layered import within_slot_context
                        within=within_slot_context(manager.value,task,origin)
                        if within is not None:bindings.append(within['current_Controller_decision'])
                elif frontier.get('schema') in ('edgar25_depth_frontier_v4','edgar25_depth_frontier_v5'):
                    from earnings_population_layered import AUTHORITY as layered_authority,POLICY as layered_policy
                    bindings += [layered_authority,layered_policy,frontier['preceding_outcomes'],origin['additional_budget_amendment']]
                    if frontier.get('schema')=='edgar25_depth_frontier_v5':
                        from earnings_population_layered import TRANSITION_POLICY,slot_resolution
                        bindings += [TRANSITION_POLICY,engine.read(TRANSITION_POLICY)['direct_instruction']]
                        plan=e.strict_json(e.checked(manager.value['sources'][
                            'configs/earnings_coevolution/training25_continuation_authority.json']))
                        bindings += slot_resolution(frontier,claim,frontier_binding=claim['frontier'],plan=plan)['evidence']
                        if role in ('author','review'):
                            from earnings_population_layered import within_slot_context
                            within=within_slot_context(manager.value,task,origin)
                            if within is not None:bindings.append(within['current_Controller_decision'])
        delivery=layered_feedback(origin,engine.read(task['feedback']),task=task)
        if delivery is not None:bindings += delivery['bindings']
    if task['mode']=='repair_review':
        if manager.value['id'] in SOURCE_TRIVIA_IDS:
            if manager.value['id']==TRIVIA154_ID:
                from earnings_population_source_trivia154 import bindings as trivia_bindings
            elif manager.value['id']==TRIVIA144_ID:
                from earnings_population_source_trivia144 import bindings as trivia_bindings
            else:
                from earnings_population_source_trivia import bindings as trivia_bindings
            bindings += [task['repair'],repair_authority(manager.value['id']),*trivia_bindings(fixed)]
        else:
            bindings += [task['repair'],repair_authority(manager.value['id']),*[fixed[k] for k in ('closure','original_git','original_review','source','tests','validation')],fixed['original_candidate']['R'],fixed['original_candidate']['H']]
        if case_contract_review(manager.value['id']) and manager.value['id'] not in SOURCE_TRIVIA_IDS:
            bindings += [fixed[k] for k in ('original_inputs_git','original_implement','scientific_decision','original_tests','original_case_results','original_feedback','exact_saved_replay')]
        if manager.value['id']==CASE146_ID:
            from earnings_population_case_expectation146 import EXTRA_KEYS
            bindings += [fixed[k] for k in EXTRA_KEYS]
        if manager.value['id']==FIXTURE_REVIEW_ID:
            bindings += [fixed[k] for k in ('full_diagnostic','financial_audit','distinct_financial_review','integration_contract')]
        if manager.value['id']==ACQUISITION_REVIEW_ID:
            bindings += [fixed[k] for k in ('distinct_financial_review','integration_contract')]
        if manager.value['id']==RATE_SCALE_REVIEW_ID:bindings += [fixed['original_implement'],fixed['scientific_decision']]
        if manager.value['id']==ANCHOR_REVIEW_ID:bindings += [fixed['prior_inputs_git'],fixed['scientific_decision']]
        if manager.value['id']==CONCISE_REVIEW_ID:
            concise=concise_review_metadata(task['repair'],fixed)
            bindings += [CONCISE_REVIEW_AUTHORITY,concise['failed_closure'],concise['failed_private_git']]
    bindings += [dict(path=str(Path(resident['company']['visible_root'])/r['path']),sha256=r['sha256'])
        for r in resident['company']['allowed_files']]
    return dict(role=role,slot=str(slot),version=deepcopy(version),company=company,
        resident=resident,bindings=bindings,registered=False,extra_contexts={})


def freeze(result_binding, output):
    verified = closed_evidence(result_binding,proposal=True); value = verified['runtime']
    descriptor = dict(schema='earnings_training25_clean_frozen_candidate_v1',policy=POLICY,
        authority=value['sources'][PLAN],split=SPLIT,round0=ROUND0,
        training=training.load_scope(SPLIT)['training'],candidate=verified['candidate'],
        proposal=result_binding,source_commit=value['source_commit'],
        forecast_sources={k:value['sources'][k] for k in ('forecaster','tools/earnings_entry.py',
            'tools/earnings_open_worker.py','tools/earnings_population_execution.py')},
        forecast_limits=value['limits']['forecast'],rates=value['rates'])
    if second_round(value):descriptor.update(learning_round=value['clean_learning_round'],parent_basis=verified['task']['round2_origin'])
    if Path(output).parent != training.ROOT: raise ValueError('Own immutable descriptor path required')
    return engine.save(Path(output),descriptor)


def compare(descriptor_binding, window_results, *, preserved_partial=None):
    descriptor = load_frozen(descriptor_binding); rows = []
    if preserved_partial is not None:
        if not backpressure_rebind(descriptor_binding):raise ValueError('Finite partial70 receiver only')
        rows=preserved70_rows(descriptor,preserved_partial)
    for binding in window_results:
        verified = closed_evidence(binding,proposal=False)
        task = verified['task']; runtime = verified['runtime']
        if task['frozen_candidate'] != descriptor_binding: raise ValueError('Another frozen candidate')
        for index,item in enumerate(verified['result']['result']['results']):
            company=task['company_ids'][index]
            row=_comparison_row(descriptor,runtime,company,index,item['result'],binding)
            if backpressure_rebind(descriptor_binding):
                row.update(runtime=verified['result']['runtime'],source_commit=runtime['source_commit'],execution_descriptor=descriptor_binding,
                    slot=runtime['slots']['forecast'][index],preserved_partial=False)
            rows.append(row)
    ids = [r['company_id'] for r in rows]
    if len(ids) != len(set(ids)) or not set(ids) <= set(descriptor['training']):
        raise ValueError('Duplicate or nontraining scored company')
    complete = len(rows) == 25
    mean = sum(r['points'] for r in rows)/25 if complete else None
    parent_mean=engine.read(descriptor['parent_basis'])['prior_mean'] if parent_round(descriptor.get('learning_round')) else 3.0
    threshold=parent_mean
    if continuous_round(descriptor.get('learning_round')):
        from earnings_population_coevolution import selection_threshold
        threshold=selection_threshold(engine.read(descriptor['parent_basis']))
    result=dict(schema='earnings_training25_clean_comparison_v1',descriptor=descriptor_binding,
        rows=rows,scored=len(rows),not_measured=25-len(rows),round0_mean=3.0,candidate_mean=mean,
        decision=('ADOPT_CANDIDATE' if mean>threshold else ('RETAIN_ADOPTED_PARENT' if parent_round(descriptor.get('learning_round')) else 'RETAIN_ROUND0')) if complete else 'INCOMPLETE_NO_SELECTION',
        next_mutation_allowed=complete,scope='Discovery, historical Round0 comparison; not generalization or causal-method proof.')
    if parent_round(descriptor.get('learning_round')):
        origin=engine.read(descriptor['parent_basis'])
        result.update(logical_round=descriptor['learning_round'],parent_mean=origin['prior_mean'],parent_version_id=origin['parent']['id'],
            next_mutation_allowed=False,scope=('Discovery versus saved full25 adopted parent; scheduler changed by human, no causal attribution or generalization. '
                + ('Direct next-group03a authority; complete25 feedback before next mutation, no extra budget.' if descriptor['learning_round'] in (5,6,7) else
                    'No automatic mutation; only directly authorized bounded followups3/4.' if descriptor['learning_round'] in (3,4) else 'No further round authorized.')))
        if continuous_round(descriptor['learning_round']):
            result.update(next_mutation_allowed=complete,
                selection_threshold=threshold,selection_incumbent_descriptor=origin['incumbent_descriptor'],
                selection_incumbent_mean=origin['incumbent_mean'],
                scope='Discovery versus saved parent/Round0; complete feedback and meaningful-next/original-budget admission, not a count stop. No causal/generalization claim.')
            from earnings_population_root_reentry import is_root,context
            if is_root(origin):
                context(origin)
                result.update(root_child_ordinal=origin['root_child_ordinal'],parent_scored=False,parent_mean=None,
                    delta_actual_parent=None,delta_round0=None if mean is None else mean-3.0,
                    delta_prediction_incumbent=None if mean is None else mean-origin['incumbent_mean'],
                    selected_version_id=(descriptor['candidate']['id'] if complete and mean>threshold else
                        engine.read(origin['incumbent_descriptor'])['candidate']['id']),
                    decision=('ADOPT_CANDIDATE' if mean>threshold else 'RETAIN_PREDICTION_INCUMBENT') if complete else 'INCOMPLETE_NO_SELECTION',
                    scope='Same-experiment root return: actual R0/H0 parent is unscoredNULL, no parent score imputation. '
                        'Separate saved plain baseline and prediction champion; strict full25 beats both to adopt. '
                        'Historical comparators, not matched reruns; Discovery, not causal/generalization proof.')
    return result
