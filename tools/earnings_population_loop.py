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


def run(root, initial, companies, services, *, admit, max_rounds, identity=None):
    validate(initial)
    if (type(companies) is not list or any(type(c) is not str or not c for c in companies)
            or len(set(companies)) != len(companies)
            or set(companies) & set(initial['exposed_companies'])
            or type(max_rounds) is not int or not 1 <= max_rounds <= len(companies) <= 50
            or set(services) != {'controller', 'author', 'review', 'forecast'}
            or any(not callable(call) for call in services.values()) or not callable(admit)):
        raise ValueError('Unique preselected companies and explicit bounded trusted services required')
    root = Path(root)
    if not root.is_absolute() or root.resolve() != root:
        raise ValueError('Canonical population run root required')
    feedback = {'schema': 'earnings_population_seed_v1', 'scope': 'No new prediction or improvement claimed'}
    if initial['observations']:
        last = initial['observations'][-1]
        prior = engine.read(last['feedback'])
        if (prior.get('schema') != 'earnings_population_feedback_v1'
                or prior.get('company_id') != last['company_id']
                or prior.get('results') != last['results']
                or prior.get('stable_id') != last['stable_id']):
            raise ValueError('Inherited pool must consume its exact last observed feedback')
        feedback = deepcopy(last['feedback'])
    seed = dict(population=deepcopy(initial), feedback=feedback, companies=deepcopy(companies))

    def slot(ctx, role, suffix=''):
        return str(root/'roles'/f'{role}-{ctx["round_index"]:02d}{suffix}')

    def packet(ctx):
        previous = ctx['previous_result']
        state = validate(previous['population'])
        company = companies[ctx['round_index'] - 1]
        if company in state['exposed_companies']:
            raise ValueError('Company was already exposed to this evolution trajectory')
        value = dict(schema='earnings_population_packet_v1', round_index=ctx['round_index'],
            company_id=company, population=deepcopy(state), feedback=deepcopy(previous['feedback']),
            previous_feedback_sha256=ctx['previous_feedback_sha256'],
            parent_feedback_sha256=digest(previous['feedback']),
            scope='New to this evolution path, not globally untouched or future-event evidence')
        binding = engine.save(root/f'packet-{ctx["round_index"]:02d}.json', value)
        return dict(packet=binding, artifacts=[binding])

    def control(ctx):
        prompt = engine.read(ctx['outputs']['input']['packet'])
        bound = services['controller'](deepcopy(prompt), slot(ctx, 'controller'))
        chosen = strict_json(checked(bound))
        state = prompt['population']
        if (chosen.get('axis') not in {'R', 'H', 'continue'}
                or chosen.get('feedback_sha256') != prompt['parent_feedback_sha256']
                or chosen.get('parent_pair_sha256') not in [state['stable_id'], *state['explorers']]
                or type(chosen.get('hypothesis')) is not str or not chosen['hypothesis'].strip()):
            raise ValueError('Controller decision must bind actual preceding feedback and active parent')
        retiring = chosen.get('retire_branch_id')
        if retiring is not None and retiring not in state['explorers']:
            raise ValueError('Only an explicit existing exploration branch may retire')
        return dict(decision=bound, packet_sha256=ctx['outputs']['input']['packet']['sha256'],
                    artifacts=[bound])

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
        return dict(candidate=child)

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
        if retiring is not None and (child is None or reviewed['accepted_for_exploration']):
            # Replace atomically only after the new candidate passes review;
            # rejection preserves the old exploration branch and all history.
            state = retire(state, retiring, reason=chosen['hypothesis'],
                           evidence=[ctx['outputs']['controller']['decision']])
        if child is not None and reviewed['accepted_for_exploration']:
            state = retain(state, child, reason=chosen['hypothesis'], evidence=reviewed['evidence'])
        frozen = engine.save(root/f'frozen-pool-{ctx["round_index"]:02d}.json', state)
        results = []
        for arm, branch in enumerate([state['stable_id'], *state['explorers']]):
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
        return dict(population=deepcopy(result['population']), feedback=result['feedback'],
                    company_id=ctx['outputs']['execute']['company_id'], artifacts=[saved, result['feedback']])

    handlers = dict(input=packet, controller=control, implement=implement, source_review=review,
                    execute=execute, result_review=result_review, reconcile=reconcile)
    def source_identity():
        common = dict(adapter=engine.pin(__file__), services={name: engine.source_of(call)
                      for name, call in services.items()}, admission=engine.source_of(admit))
        return {stage: dict(common, stage=stage) for stage in driver.STAGES}
    return driver.run(root/'loop', handlers, seed=seed, admit=admit, max_rounds=max_rounds,
                      handler_identity=source_identity if identity is None else identity)
