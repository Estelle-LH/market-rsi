"""Bounded company-by-company research using the existing once-only driver.

Services are trusted source-bound adapters, never commands returned by a model.
They own original-data admission, shared budget/lock, model transport, isolated
execution and original scoring. This module supplies none of that authority.
"""
from copy import deepcopy
from pathlib import Path

from earnings_entry import checked, strict_json
from earnings_population import validate, retain, retire, observe, validate_result
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness import feedback_linked_loop as driver


def run(root, initial, companies, services, *, admit, max_rounds, identity=None, campaign=None,
        initial_feedback=None, initial_task=None):
    validate(initial)
    if initial_task is not None:
        from earnings_population_memory_delta import typed_equal
        if (type(initial_task) is not dict or initial_feedback is None
                or not typed_equal(initial_task.get('feedback'),initial_feedback)):
            raise ValueError('Original task must bind this exact initial feedback')
    frontier_seed=False
    if initial_feedback is not None:
        from earnings_population_coevolution import feedback_expansion
        frontier_seed=feedback_expansion(engine.read(initial_feedback),initial,task=initial_task)
    policy = None
    if campaign is not None:
        import earnings_population_campaign as campaign_policy
        policy = campaign_policy.load(campaign, initial, companies, max_rounds)
    if (type(companies) is not list or any(type(c) is not str or not c for c in companies)
            or policy is None and (len(set(companies)) != len(companies)
                or not frontier_seed and set(companies) & set(initial['exposed_companies']))
            or type(max_rounds) is not int or not 1 <= max_rounds <= len(companies) <= 50
            or set(services) != {'controller', 'author', 'review', 'forecast'}
            or any(not callable(call) for call in services.values()) or not callable(admit)):
        raise ValueError('Unique preselected companies and explicit bounded trusted services required')
    root = Path(root)
    if not root.is_absolute() or root.resolve() != root:
        raise ValueError('Canonical population run root required')
    feedback = {'schema': 'earnings_population_seed_v1', 'scope': 'No new prediction or improvement claimed'}
    if initial_feedback is not None:
        full = engine.read(initial_feedback)
        if (campaign is not None or not frontier_seed and (initial['observations'] or len(initial['versions']) != 1)
                or full.get('schema') != 'earnings_training25_public_summary_v1'
                or len(full.get('rows',[])) != 25 or any(len(r.get('targets',[])) != 5 for r in full['rows'])):
            raise ValueError('Explicit fresh full25 feedback seed required')
        feedback = deepcopy(initial_feedback)
    if policy is not None:
        feedback = deepcopy(policy['initial_feedback'])
    elif initial['observations'] and not frontier_seed:
        last = initial['observations'][-1]
        prior = engine.read(last['feedback'])
        if (prior.get('schema') != 'earnings_population_feedback_v1'
                or prior.get('company_id') != last['company_id']
                or prior.get('results') != last['results']
                or prior.get('stable_id') != last['stable_id']):
            raise ValueError('Inherited pool must consume its exact last observed feedback')
        feedback = deepcopy(last['feedback'])
    seed = dict(population=deepcopy(initial), feedback=feedback, companies=deepcopy(companies))
    if policy is not None:
        seed.update(campaign=deepcopy(campaign), latest_feedback=deepcopy(feedback),
                    last_scored_feedback=deepcopy(policy['last_scored_feedback']))

    def slot(ctx, role, suffix=''):
        return str(root/'roles'/f'{role}-{ctx["round_index"]:02d}{suffix}')

    def packet(ctx):
        previous = ctx['previous_result']
        state = validate(previous['population'])
        company = companies[ctx['round_index'] - 1]
        if policy is None and not frontier_seed and company in state['exposed_companies']:
            raise ValueError('Company was already exposed to this evolution trajectory')
        value = dict(schema='earnings_population_packet_v1', round_index=ctx['round_index'],
            company_id=company, population=deepcopy(state), feedback=deepcopy(previous['feedback']),
            previous_feedback_sha256=ctx['previous_feedback_sha256'],
            parent_feedback_sha256=digest(previous['feedback']),
            scope=('Reused training interface case; complete frontier feedback retained; Discovery, not untouched evidence'
                if frontier_seed else 'New to this evolution path, not globally untouched or future-event evidence'))
        if policy is not None:
            value.update(campaign=deepcopy(campaign), scope=campaign_policy.scope(policy),
                         last_scored_feedback=deepcopy(previous['last_scored_feedback']))
        binding = engine.save(root/f'packet-{ctx["round_index"]:02d}.json', value)
        return dict(packet=binding, artifacts=[binding])

    def control(ctx):
        prompt = engine.read(ctx['outputs']['input']['packet'])
        bound = services['controller'](deepcopy(prompt), slot(ctx, 'controller'))
        chosen = strict_json(checked(bound))
        state = prompt['population']
        expected_feedback=prompt['parent_feedback_sha256']
        routed=Path(slot(ctx,'controller'))/'controller-stage-reuse.json'
        if routed.exists():
            route=engine.read(engine.pin(routed))
            from earnings_population_technical_retry import POLICY, verify_controller_route
            if route.get('schema')==POLICY:
                expected_feedback=verify_controller_route(route['runtime'],routed.parent,
                    packet=prompt,chosen=chosen)['scientific_feedback_sha256']
        if (chosen.get('axis') not in {'R', 'H', 'continue'}
                or chosen.get('feedback_sha256') != expected_feedback
                or chosen.get('parent_pair_sha256') not in [state['stable_id'], *state['explorers']]
                or type(chosen.get('hypothesis')) is not str or not chosen['hypothesis'].strip()):
            raise ValueError('Controller decision must bind actual preceding feedback and active parent')
        retiring = chosen.get('retire_branch_id')
        if retiring is not None and retiring not in state['explorers']:
            raise ValueError('Only an explicit existing exploration branch may retire')
        output = dict(decision=bound, packet_sha256=ctx['outputs']['input']['packet']['sha256'],
                      artifacts=[bound])
        imported = Path(slot(ctx, 'controller'))/'controller-proposal-import.json'
        if imported.exists():
            # Attribute the trusted import at the same durable once-only stage
            # boundary as its routed decision, not by later ad-hoc pinning.
            output['proposal_import'] = engine.pin(imported)
            output['artifacts'].append(output['proposal_import'])
        reused = Path(slot(ctx, 'controller'))/'controller-stage-reuse.json'
        if reused.exists():
            output['stage_reuse'] = engine.pin(reused)
            output['artifacts'].append(output['stage_reuse'])
        return output

    def implement(ctx):
        chosen = engine.read(ctx['outputs']['controller']['decision'])
        if chosen['axis'] == 'continue':
            return dict(candidate=None)
        prompt = engine.read(ctx['outputs']['input']['packet'])
        if len(prompt['population']['explorers']) >= 2 and chosen.get('retire_branch_id') is None:
            raise ValueError('Explorer pool full: preserve it, no silent eviction or extra Author')
        child = services['author'](deepcopy(chosen), deepcopy(prompt['population']), slot(ctx, 'author'))
        if (type(child) is not dict or child.get('parent') != chosen['parent_pair_sha256']
                or child.get('axis') != chosen['axis']):
            raise ValueError('Author candidate must implement the actual chosen parent/axis')
        output = dict(candidate=child)
        reused = Path(slot(ctx, 'author'))/'author-stage-reuse.json'
        if reused.exists():
            output.update(stage_reuse=engine.pin(reused), artifacts=[engine.pin(reused)])
        return output

    def review(ctx):
        child = ctx['outputs']['implement']['candidate']
        if child is None:
            return dict(accepted_for_exploration=False, evidence=[])
        state = engine.read(ctx['outputs']['input']['packet'])['population']
        result = services['review'](deepcopy(child), deepcopy(state), slot(ctx, 'review'))
        if (type(result) is not dict or set(result) != {'accepted_for_exploration', 'evidence'}
                or type(result['accepted_for_exploration']) is not bool
                or type(result['evidence']) is not list or not result['evidence']):
            raise ValueError('Independent candidate review/evidence required')
        driver._artifacts(result)
        return result

    def execute(ctx):
        prompt = engine.read(ctx['outputs']['input']['packet'])
        state = deepcopy(prompt['population'])
        child, reviewed = ctx['outputs']['implement']['candidate'], ctx['outputs']['source_review']
        chosen = engine.read(ctx['outputs']['controller']['decision'])
        retiring = chosen.get('retire_branch_id')
        if retiring is not None and ((policy is None and child is None)
                                    or child is not None and reviewed['accepted_for_exploration']):
            # Replace atomically only after the new candidate passes review;
            # rejection preserves the old exploration branch and all history.
            state = retire(state, retiring, reason=chosen['hypothesis'],
                           evidence=[ctx['outputs']['controller']['decision']])
        if child is not None and reviewed['accepted_for_exploration']:
            state = retain(state, child, reason=chosen['hypothesis'], evidence=reviewed['evidence'])
        frozen = engine.save(root/f'frozen-pool-{ctx["round_index"]:02d}.json', state)
        results = []
        branches = ([state['stable_id'], *state['explorers']] if policy is None else
                    campaign_policy.arms(policy, state, child, reviewed))
        for arm, branch in enumerate(branches):
            # The exact frozen pool is rechecked before every serial forecast.
            if engine.read(frozen) != state:
                raise ValueError('Candidate selection changed after freeze')
            validate(state)
            result = services['forecast'](deepcopy(state['versions'][branch]), prompt['company_id'],
                                          slot(ctx, 'forecast', f'-{arm:02d}'))
            if type(result) is not dict or result.get('version_id') != branch:
                raise ValueError('Forecast result did not use its frozen version')
            validate_result(result)
            driver._artifacts(result)
            results.append(result)
        return dict(frozen=frozen, results=results, company_id=prompt['company_id'], artifacts=[frozen])

    def result_review(ctx):
        measured = ctx['outputs']['execute']
        frozen = engine.read(measured['frozen'])
        if policy is not None:
            decision_binding = ctx['outputs']['controller']['decision']
            value = campaign_policy.feedback(policy, ctx['previous_result'],
                engine.read(decision_binding), ctx['outputs']['implement']['candidate'],
                ctx['outputs']['source_review'], measured, ctx['round_index'], decision_binding)
            feedback = engine.save(root/f'feedback-{ctx["round_index"]:02d}.json', value)
            last_scored = (feedback if value['score_state'] == 'scored' else
                           ctx['previous_result']['last_scored_feedback'])
            decision_record = engine.save(root/f'decision-{ctx["round_index"]:02d}.json', dict(
                schema='earnings_population_campaign_decision_v1', campaign=deepcopy(campaign),
                round_index=ctx['round_index'], feedback=feedback, frozen=measured['frozen'],
                population_sha256=digest(frozen), score_state=value['score_state'], kind=value['kind'],
                parent_id=value['chosen_parent_id'], baseline_version_id=value['baseline_version_id'],
                candidate_id=None if value['candidate'] is None else value['candidate']['id']))
            return dict(population=frozen, feedback=feedback, latest_feedback=feedback,
                        last_scored_feedback=last_scored, decision_record=decision_record,
                        artifacts=[feedback, decision_record])
        # Original scores are projected by the trusted forecast service; never
        # give the Controller the scorer's hidden numeric answers.
        value = dict(schema='earnings_population_feedback_v1', company_id=measured['company_id'],
            round_index=ctx['round_index'], preceding_feedback_sha256=ctx['previous_feedback_sha256'],
            decision=ctx['outputs']['controller']['decision'], results=deepcopy(measured['results']),
            exploration_review=dict(candidate_id=None if ctx['outputs']['implement']['candidate'] is None
                                    else ctx['outputs']['implement']['candidate']['id'],
                                    **deepcopy(ctx['outputs']['source_review'])),
            stable_id=frozen['stable_id'], scope='Discovery scores, not confirmed improvement')
        feedback = engine.save(root/f'feedback-{ctx["round_index"]:02d}.json', value)
        updated = observe(frozen, measured['company_id'], measured['results'], feedback=feedback)
        return dict(population=updated, feedback=feedback, artifacts=[feedback])

    def reconcile(ctx):
        result = ctx['outputs']['result_review']
        validate(result['population'])
        saved = engine.save(root/f'population-{ctx["round_index"]:02d}.json', result['population'])
        reconciled = dict(population=deepcopy(result['population']), feedback=result['feedback'],
                    company_id=ctx['outputs']['execute']['company_id'], artifacts=[saved, result['feedback']])
        if policy is not None:
            reconciled.update(latest_feedback=result['latest_feedback'],
                              last_scored_feedback=result['last_scored_feedback'],
                              decision_record=result['decision_record'])
            reconciled['artifacts'].append(result['decision_record'])
        return reconciled

    handlers = dict(input=packet, controller=control, implement=implement, source_review=review,
                    execute=execute, result_review=result_review, reconcile=reconcile)
    def source_identity():
        from earnings_population_live_guard import service_identity
        common = dict(adapter=engine.pin(__file__), services={name: service_identity(call)
                      for name, call in services.items()}, admission=engine.source_of(admit))
        if policy is not None:
            common.update(campaign_policy=engine.pin(campaign_policy.__file__), campaign=deepcopy(campaign))
        return {stage: dict(common, stage=stage) for stage in driver.STAGES}
    return driver.run(root/'loop', handlers, seed=seed, admit=admit, max_rounds=max_rounds,
                      handler_identity=source_identity if identity is None else identity)
