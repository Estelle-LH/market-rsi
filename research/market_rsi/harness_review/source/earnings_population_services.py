# Source excerpt. Imports and other methods are omitted.

class Services:
    def author(self, chosen, state, slot):
        scope = self._training_scope()
        task = self._proposal_task(scope=scope)
        if task is not None:
            self._proposal_context(task)
            if chosen['parent_pair_sha256'] in task['archive_only_version_ids']:
                raise ValueError('Archive-only version cannot be the new Author parent')
        self.role_versions = {ident: state['versions'][ident] for ident in [state['stable_id'], *state['explorers']]}
        parent = state['versions'][chosen['parent_pair_sha256']]
        selected = scientific(chosen)
        campaign = getattr(self, 'campaign_context', None)
        reuse = self.reused_author()
        base = (None if campaign is None or reuse is not None else implementation_base(selected, parent,
            campaign['feedback_binding'], campaign['prior_candidate']))
        case = self.case(parent, slot)
        if hasattr(self, 'prior_feedback'):
            references = {axis: {'sha256': parent[axis]['sha256'],
                'read_tool': 'read_population_program', 'arguments': {
                    'version_id': parent['id'], 'axis': axis, 'offset': 0, 'characters': 4000}}
                for axis in ('R', 'H')}
            if campaign is not None:
                references = program_references({axis: checked(parent[axis]).decode() for axis in ('R', 'H')})
            context = {
                'schema': 'earnings_population_author_context_v1', 'parent_version_id': parent['id'],
                'parent_programs': references, 'feedback': deepcopy(self.prior_feedback),
                'feedback_sha256': chosen['feedback_sha256'],
                'task': 'Implement the Controller decision. Diagnose the verified prior program failure using its exact source and read_prior_file for original prior-company tables. Reported counts are not independent correctness. Preserve scorer/data/model/budget; no forced adoption or gain.'}
            if campaign is not None:
                context.update(feedback_binding=campaign['feedback_binding'],
                    campaign=campaign['campaign'], prior_candidate=campaign['prior_candidate'],
                    original_R_evidence_abi=campaign['original_R_evidence_abi'],
                    failure_evidence_context=deepcopy(campaign.get('failure_evidence_context')),
                    evidence_abi_guidance=campaign['research_context']['verification'])
                if base is not None:
                    context.update(implementation_base=deepcopy(base), implementation_base_decision=deepcopy(selected))
                delivery = campaign['research_context']['observations'].get('prior_delivery_failure')
                if delivery is not None:
                    context['prior_delivery_failure'] = deepcopy(delivery)
                if campaign.get('repair_assignment') is not None:
                    context['task'] += (' This human-assigned repair must be narrow and justified by the real failed excerpts. '
                        'Preserve working parent behavior; inspect real date/unit/value context. Avoid a wholesale parser rewrite, '
                        'hardcoded target answers, manufactured source metadata or an unavailable extra R evidence phase. '
                        'Report the specific changed functions and test the actual acquisition path, not only constructed complete excerpts.')
                if scope is not None:
                    if campaign.get('training_scope') != scope or campaign.get('repair_assignment') is not None:
                        raise ValueError('Author training context differs from actual admitted scope')
                    context.update(**{key: deepcopy(campaign[key]) for key in
                        ('training_comparator', 'training_state')})
                    context['task'] = ('Implement the actual Controller hypothesis to improve transferable financial '
                        'research across training25. Literature, algorithms and tools remain available under the '
                        'existing one-axis/source/feedback limits. Preserve useful actual-parent behavior, '
                        'use old failures as evidence rather than a mandatory parser repair, and test available '
                        'period/unit/source evidence. No answer hardcoding, forced adoption or promised score gain.')
                if task is not None:
                    context.update(proposal_task=deepcopy(task),task=campaign['research_context']['human_task'])
            if 'clean_slate_policy' in getattr(self,'runtime',{}):
                from earnings_population_clean_slate import read_task, research_task, second_round, POLICY
                clean_task, _ = read_task(self.runtime)
                context.update(task=research_task(self.runtime),training_comparator=engine.read(clean_task['feedback']),
                    feedback_binding=clean_task['feedback'],clean_slate_policy=POLICY,
                    scaffold_semantics=('Selected actual complete25 code parent R/H, not necessarily prediction incumbent; full pool/genealogy and distinct feedback sources retained in the round origin.'
                        if second_round(self.runtime) else 'Unscored empty code adapter only; actual comparator is saved plain Round0.'))
            self.author_context = engine.save(self.native_root/(Path(slot).name+'-context.json'), context)
        if reuse is not None:
            expected = engine.read(reuse['decision'])
            expected['feedback_sha256'] = chosen['feedback_sha256']
            if chosen != expected or Path(slot).name != 'author-01' or parent['id'] != reuse['candidate']['parent']:
                raise ValueError('Reuse cannot silently change science/parent or re-author')
            selected = reuse['scientific_decision']
            base_option = ({} if reuse.get('implementation_base') is None
                           else {'implementation_base': reuse['implementation_base']})
            authored = assemble(parent[chosen['axis']], selected, engine.read(reuse['raw_patch_response']), **base_option)
            parsed = candidate(authored, program(checked(parent[chosen['axis']]), chosen['axis']), selected)
            child = deepcopy(reuse['candidate'])
            if (checked(child[chosen['axis']]) != authored['source_text'].encode()
                    or checked(reuse['tests']) != authored['test_text'].encode()
                    or child['H'] != parent['H']):
                raise ValueError('Exact reused assembled source/tests/unchanged H required')
            Path(slot).mkdir(parents=True, exist_ok=False)
            receipt = engine.save(Path(slot)/'author-stage-reuse.json', dict(
                schema='earnings_population_Author_stage_reuse_v1', mode=reuse['mode'],
                new_model_called=False, source_attempt=reuse['failed_attempt'], candidate_id=child['id'],
                original_decision=reuse['decision'], scientific_decision_sha256=digest(selected),
                raw_patch_response=reuse['raw_patch_response'], assembly=reuse['assembly'],
                source=reuse['source'], tests=reuse['tests'],
                **{k: deepcopy(reuse[k]) for k in ('implementation_base','original_controller_import') if k in reuse},
                attribution=('Original10 model Delta/tests; no new model call or source authorship.'
                    if Path(reuse['failed_attempt']['path']).parent.name == 'edgar-population-20261016-10' else
                    Path(reuse['failed_attempt']['path']).parent.name+
                    ' original model Delta/tests; no new model call or source authorship.')))
            self.authored[child['id']] = dict(parsed=parsed, decision=selected, source=authored['source_text'],
                originals=[receipt,reuse['raw_patch_response'],reuse['assembly'],reuse['source'],reuse['tests']],
                review_index_inputs=dict(parent_binding=reuse['parent_source'], chosen=selected,
                    original_binding=reuse['raw_patch_response'], source_binding=reuse['source'],
                    version_id=child['id'], assembly_binding=reuse['assembly']),
                reused_stage=receipt)
            return child
        role = self.role('author', DeltaAuthor, case, slot)
        before = program(checked(parent[chosen['axis']]), chosen['axis'])
        base_option = {} if base is None else {'implementation_base': base}
        original = role.author(selected, before, slot, parent_binding=parent[chosen['axis']], **base_option)
        raw = engine.read(original)
        authored = assemble(parent[chosen['axis']], selected, raw, **base_option)
        parsed = candidate(authored, before, selected)
        projection = engine.save(Path(slot)/'scientific-decision-projection.json', {
            'population_decision': chosen, 'scientific_decision': selected,
            'scientific_decision_sha256': digest(selected),
            'scope': 'Explicitly removed retirement field only; no parent or feedback rewrite'})
        for name, value in [('candidate.py', authored['source_text']), ('cases.py', authored['test_text'])]:
            save_bytes(Path(slot)/name, value.encode())
        source_binding, test_binding = (engine.pin(Path(slot)/name) for name in ('candidate.py', 'cases.py'))
        assembly = engine.save(Path(slot)/'delta-assembly.json', {
            'schema': 'earnings_population_delta_assembly_v1' if base is None else 'earnings_population_delta_assembly_v2', 'axis': chosen['axis'],
            'parent_version_id': parent['id'], 'parent_source': deepcopy(parent[chosen['axis']]),
            'raw_patch_response': original, 'scientific_decision': projection,
            'scientific_decision_sha256': digest(selected), 'assembled_business_sha256': digest(authored),
            'assembly_source': engine.source_of(assemble), 'source': source_binding, 'tests': test_binding,
            'model_authorship': ('Delta edits and test_text only; unchanged parent code is mechanically inherited.' if base is None else
                                'Delta edits and test_text only; unchanged rejected implementation-base code is mechanically inherited, not newly authored or adopted.'),
            'host_candidate_execution': False,
            **({} if base is None else dict(implementation_base=deepcopy(base),
                comparison_parent_source=deepcopy(parent[chosen['axis']]),
                comparison_parent_version_id=parent['id'],
                genetic_scope='Delta edits/tests are newly authored; unchanged rejected implementation-base bytes are inherited. Child parent remains active comparison parent; a paired trial measures accumulated repairs, not just latest edits.'))})
        sources = {axis: parent[axis] for axis in ('R', 'H')}
        sources[chosen['axis']] = source_binding
        child = describe(**sources, parent=parent['id'], axis=chosen['axis'],
            method=chosen['hypothesis'], author='model:DeltaAuthor', evidence=[original, projection, assembly])
        if child['id'] == parent['id']:
            raise ValueError('No source change; no false candidate or automatic retry')
        if task is not None and child['id'] in state['versions']:
            raise ValueError('New Author proposal must not substitute any archived existing version')
        self.authored[child['id']] = dict(parsed=parsed, decision=selected,
            source=authored['source_text'], originals=[original, projection, assembly, source_binding, test_binding],
            review_index_inputs=dict(parent_binding=parent[chosen['axis']], chosen=selected,
                original_binding=original, source_binding=source_binding, version_id=child['id'], assembly_binding=assembly))
        return child

    def review(self, child, state, slot):
        task = self._proposal_task()
        prefix=None
        if 'proposal_prefix_reuse' in getattr(self,'runtime',{}):
            from earnings_population_runtime import _proposal_prefix_metadata
            prefix=_proposal_prefix_metadata(self.runtime,engine.read(self.runtime['forecast_study']),
                company_id=self.runtime['companies'][0])
        if task is not None and (child.get('parent') in task['archive_only_version_ids']
                or child['id'] in state['versions']):
            raise ValueError('Review requires the fresh proposal and actual permitted implementation parent')
        authored = self.authored[child['id']]
        if task is not None and authored.get('reused_stage') is not None and prefix is None:
            raise ValueError('Fresh proposal Review cannot reuse an old Author receipt')
        parent = None
        if getattr(self, 'campaign_context', None) is not None:
            parent_id = child.get('parent')
            parent = state['versions'].get(parent_id)
            other = 'H' if child['axis'] == 'R' else 'R'
            if (parent_id not in [state['stable_id'], *state['explorers']] or parent is None
                    or parent.get('id') != parent_id or child[other] != parent[other]
                    or parent_id != digest({axis: parent[axis]['sha256'] for axis in ('R', 'H')})):
                raise ValueError('Review comparison requires exact selected active parent/other axis')
            for axis in ('R', 'H'):
                checked(parent[axis])
        self.role_versions = {child['id']: child, **({} if parent is None else {parent['id']: parent})}
        frontier_test=None
        if 'clean_slate_policy' in getattr(self,'runtime',{}) and self.runtime.get('clean_learning_round',0)>=9:
            from earnings_population_clean_slate import round2_origin
            from earnings_population_coevolution import declared_test, selected_parent
            origin=round2_origin(self.runtime);frontier_parent=selected_parent(state,origin)
            if child['parent']!=frontier_parent['id']:raise ValueError('Review replaced the declared frontier parent')
            self.role_versions[frontier_parent['id']]=frontier_parent
            frontier_test=declared_test(origin)
        case = self.case(child, slot)
        reuse = self.reused_author() if hasattr(self, 'runtime') else None
        if reuse is not None:
            study = engine.read(self.runtime['forecast_study'])
            reviewed = self._reuse_origin(study).get('review_stage_reuse')
            if reviewed is not None:
                from earnings_population_forecast_failure import reuse_receipt
                receipt = reuse_receipt(reviewed, reuse, child, slot)
                if Path(slot).exists() and any(Path(slot).iterdir()):
                    raise ValueError('Accepted Review reuse requires a fresh empty role slot')
                Path(slot).mkdir(parents=True, exist_ok=True)
                marker = engine.save(Path(slot)/'review-stage-reuse.json', receipt)
                return dict(accepted_for_exploration=True, evidence=[marker, *deepcopy(reviewed['evidence'])])
        results = run_cases(self.runner, authored['source'], authored['parsed']['cases'])
        evidence = engine.save(self.native_root/(Path(slot).name+'-cases.json'), {
            'candidate_id': child['id'], 'results': results,
            'scope': ('Human-authorized acquisition expectation repair plus original model examples in Docker; not financial proof'
                if authored.get('human_interface_repair') is not None else
                'Actual model-authored test cases in Docker, not independent financial proof')})
        if not all(row['passed'] for row in results):
            return self.review_outcome(child, slot, False, 'MODEL_CASES_FAILED; inspect preserved case evidence',
                                       [evidence, *authored['originals']])
        probes = []
        if child['axis'] == 'R':
            for stage in ('forecast', 'controller'):
                payload = dict(stage=stage, questions=case['state_api'].tools.files['questions.md'],
                    filing_index=case['state_api'].tools.files['filing_index.tsv'], records=[])
                if stage == 'controller':
                    payload.update(feedback={'scope': 'Cold admission probe; no new score'},
                                   research_objective=('Improve original financial forecasting on this company' if task is None
                                       else task['primary_task']+' Current-company integration smoke only, not whole25 validation.'))
                run = researcher.run(self.runner, authored['source'], payload, case['state_api'].tools)
                value = researcher.verify(run, authored['source'], payload, case['company'])
                diagnostics = project(value, source_sha256=child['R']['sha256'],
                    execution_sha256=run['receipt']['sha256'],
                    target_ids=re.findall(r'^### (T[0-9]+) \|', payload['questions'], re.M))
                probe = {
                    'input': payload, 'execution': run, 'diagnostics': diagnostics,
                    'scope': 'Real public-data empty-state interface probe, not financial correctness'}
                if getattr(self, 'campaign_context', None) is not None or authored.get('human_interface_repair') is not None:
                    probe['company_id'] = case['company']['cik']
                    probe['verified_public_R_output'] = review_probe_output(value)
                probes.append(engine.save(self.native_root/(Path(slot).name+'-'+stage+'-probe.json'), probe))
            feedback = getattr(self, 'prior_feedback', {})
            if 'company_id' in feedback and feedback['company_id'] != case['company']['cik']:
                scope = self._training_scope()
                if scope is not None:
                    from earnings_population_training25 import admit
                    admit(scope, feedback['company_id'])
                prior = resident(feedback['company_id'])['company']
                tools = FilingTools(prior)
                payload = dict(stage='forecast', questions=tools.files['questions.md'],
                    filing_index=tools.files['filing_index.tsv'], records=[])
                run = researcher.run(self.runner, authored['source'], payload, tools)
                value = researcher.verify(run, authored['source'], payload, prior)
                diagnostics = project(value, source_sha256=child['R']['sha256'],
                    execution_sha256=run['receipt']['sha256'],
                    target_ids=re.findall(r'^### (T[0-9]+) \|', payload['questions'], re.M))
                probes.append(engine.save(self.native_root/(Path(slot).name+'-prior-probe.json'), {
                    'company_id': prior['cik'], 'input': payload, 'execution': run,
                    'diagnostics': diagnostics, 'scope': 'Original previous-company repair test; no scorer or hidden labels'}))
        navigation = {}
        if authored.get('human_interface_repair') is not None:
            navigation['human_authorized_minimal_interface_repair']=deepcopy(authored['human_interface_repair'])
        parent_probes = []
        if parent is not None:
            matched, parent_probes = (self.matched_parent_probes(parent, child, case, probes, slot)
                                     if child['axis'] == 'R' else ([], []))
            navigation.update(matched_active_parent_empty_state_probes=matched,
                active_parent_comparison=dict(parent_version_id=parent['id'],
                    parent_programs={axis: deepcopy(parent[axis]) for axis in ('R', 'H')},
                    child_version_id=child['id'], changed_axis=child['axis'],
                    status='matched_R_probes_completed' if matched else 'not_run_H_candidate',
                    scope='R advice/execution comparison only, not H behavior or financial truth; original independent Review and forecast admission remain unchanged.'))
        role = self.role('review', PopulationReviewer, case, slot)
        if authored.get('review_index_inputs') is not None:
            from earnings_population_delta_author import review_index
            navigation['candidate_change_index'] = review_index(**authored['review_index_inputs'])
        if authored.get('reused_stage') is not None:
            navigation['successful_Author_stage_reuse'] = engine.read(authored['reused_stage'])
            if prefix is not None:
                navigation['prior_Review_delivery_failure']=dict(failed_attempt=prefix['failed_attempt'],
                    authority=prefix['authority'],stage='source_review',error_type='BudgetStop',
                    observed_input_tokens=[32976,33290],prior_input_limit=32000,
                    review_assessment=prefix['review_assessment'],
                    completed_Review_generations=prefix['original_completed_generations']['review'],score_state='unscored',
                    scope='Closed37 delivery failure, no scientific verdict or prediction. Original code/tests imported; assess current source and matched probes independently.')
            else:
                recovery = self.campaign_context['research_context']['observations']['prior_delivery_failure']
                navigation['prior_Review_delivery_failure'] = {key: deepcopy(recovery[key]) for key in (
                    'failed_attempt','audit','stage','error_type','observed_input_tokens','prior_input_limit',
                    'review_assessment','completed_Review_generations','score_state','scope')}
                navigation['known_public_tradeoff'] = 'Prior public cold audit reported improved T005 evidence but T002 acquisition regression. Inspect the actual current probes and source; this is not acceptance or a financial-correctness certificate.'
        review_prompt = dict(candidate_id=child['id'], decision=authored['decision'], **navigation,
            company_id=case['company']['cik'], tests={'passed': len(results), 'failed': 0},
            **({'human_repair_acceptance': 'Before a forecast trial, the real empty-state original-data tests must demonstrate usable source-backed period/unit/value evidence for the claimed repair. Inspect the exact saved probe output, not only synthetic cases or program-reported counts. Reject unresolved real extraction failure; no score gain is required before the trial.'}
                if getattr(self, 'campaign_context', None) is not None
                    and self.campaign_context.get('repair_assignment') is not None else {}),
            **({'campaign_research_context': dict(
                feedback_binding=self.campaign_context['feedback_binding'],
                original_R_evidence_abi=self.campaign_context['original_R_evidence_abi'],
                cold_probe_company_id=case['company']['cik'],
                prior_feedback_company_id=self.prior_feedback['company_id'],
                scope='R cold probes below already use the labeled development company. If it equals the feedback company, an extra duplicate prior-company probe is unnecessary; H candidates do not create R cold probes.')}
                if getattr(self, 'campaign_context', None) is not None else {}),
            original_public_empty_state_probes=[{'stage': stage, 'completed': True, 'receipt': bound,
                                                **({'company_id': case['company']['cik']}
                                                   if getattr(self, 'campaign_context', None) is not None else {}),
                                                **({'verified_public_R_output': engine.read(bound)['verified_public_R_output']}
                                                   if 'verified_public_R_output' in engine.read(bound) else {}),
                                                'diagnostics': engine.read(bound)['diagnostics']}
                for stage, bound in zip(('forecast', 'controller'), probes)],
            original_questions=case['state_api'].tools.files['questions.md'],
            prior_company_repair_probe=None if len(probes) < 3 else {
                'receipt': probes[2], 'company_id': engine.read(probes[2])['company_id'],
                'diagnostics': engine.read(probes[2])['diagnostics'],
                'original_questions': engine.read(probes[2])['input']['questions'],
                'previous_feedback': getattr(self, 'prior_feedback', {})},
            repair_objective=None if getattr(self, 'repair_company', None) is None else {
                'task': 'Assess whether this implementation addresses the actual previous-company parsing failure. Completed execution and passing Author examples alone do not demonstrate repair. A parser still producing zero extracted cells and all targets incomplete has not demonstrated the requested extraction benefit; inspect exact source/public tables when needed.',
                'previous_feedback': self.prior_feedback},
            current_programs=role.broker.references())
        if task is not None:
            review_prompt.update(proposal_task=deepcopy(task),research_objective=task['primary_task'],
                evaluation_scope='Current-company cases/cold probes are integration and safety smoke only; accepted Review is not full25 suitability, predictive gain or adoption. The same fresh code must be frozen for all25 before another mutation.')
        if frontier_test is not None:
            review_prompt.update(declared_frontier_test=frontier_test,
                frontier_parent_programs={axis:deepcopy(frontier_parent[axis]) for axis in ('R','H')},
                frontier_scope='Verify this actual-parent hypothesis against source/test/public evidence. Criteria are not assumed gain. No additional paid role, probe phase or resources; same candidate must complete25 before selection.')
        from earnings_population_review_context import share_probe_prefixes
        original = role.review(share_probe_prefixes(review_prompt), slot)
        reviewed = engine.read(engine.pin(Path(slot)/'review.json'))
        if reviewed['original'] != original:
            raise ValueError('Exploration review differs from original response')
        return self.review_outcome(child, slot, reviewed['review']['accepted_for_exploration'],
            reviewed['review']['rationale'], [original, evidence, *probes, *parent_probes, *authored['originals']])

    def review_outcome(self, child, slot, accepted, rationale, evidence):
        public = engine.save(self.native_root/(Path(slot).name+'-outcome.json'), {
            'schema': 'earnings_population_exploration_review_v1', 'candidate_id': child['id'],
            'accepted_for_exploration': accepted, 'rationale': rationale})
        return dict(accepted_for_exploration=accepted, evidence=[public, *evidence])
