# Source excerpt. Imports and other methods are omitted.

def scientific_question():
    """Read the predeclared public question; a draft cannot invent a new child."""
    originals = entry.strict_json(entry.checked(ORIGINAL_FRONTIER))
    if (originals.get('generation') != 9 or originals.get('growth_depth') != 0
            or len(originals['expansions']) != 1
            or len(originals['expansions'][0]['children']) != 16):
        raise ValueError('Original Root0 frontier width or generation changed')
    question = originals['expansions'][0]['children'][ORDINAL - 1]
    if question['hypothesis_id'] != HYPOTHESIS or question['change_axis'] != 'H':
        raise ValueError('Original ordinal 12 must be the distinct H-only question')
    return question


def context(origin, supplied_plan=None):
    """Replay the complete finite public composition named by the committed plan."""
    from earnings_population_docker_profile import _bytes
    from earnings_population_frozen222_evaluation import _read
    from supervisor_harness import capacity_feedback_engine as engine

    if not is_origin(origin) or entry.REPO != WORKSPACE:
        raise ValueError('Exact independent Q12 public origin required')
    sources = {CONFIG: dict(path=str(WORKSPACE / CONFIG), sha256=CONFIG_SHA),
        PLAN: engine.pin(WORKSPACE / PLAN)}
    plan = entry.strict_json(entry.checked(sources[PLAN]))
    value = dict(clean_learning_round=ROUND, sources=sources)
    _, saved, _ = source_origin(value, plan['origin'])
    if (not typed_equal(origin, saved)
            or supplied_plan is not None and not typed_equal(supplied_plan, plan)):
        raise ValueError('Q12 public context must match the Source-selected origin')
    claim_bound = _binding(plan, 'frontier_expansion', ROOT / CLAIM_NAME)
    claim = entry.strict_json(_bytes(claim_bound, ROOT / CLAIM_NAME))
    feedback_bound = _binding(plan, 'public_feedback', ROOT / FEEDBACK_NAME)
    material = entry.strict_json(_bytes(plan['public_material'], ROOT / MATERIAL_NAME, maximum=2_100_000))
    feedback = entry.strict_json(_bytes(feedback_bound, ROOT / FEEDBACK_NAME, maximum=2_100_000))
    population_bound = _binding(plan, 'carried_population', ROOT / POPULATION_NAME)
    population = entry.strict_json(_bytes(population_bound, ROOT / POPULATION_NAME, maximum=2_100_000))
    if (origin.get('carried_population') != population_bound
            or not typed_equal(population, carried_population())
            or not typed_equal(origin['parent'], population['versions'][claim['parent_id']])):
        raise ValueError('Exact registered population and working Root0 must remain in Q12')
    if (origin.get('frontier_expansion') != claim_bound or origin.get('public_feedback') != feedback_bound
            or not typed_equal(claim, frontier_claim())
            or not typed_equal(feedback, public_feedback(material, frontier_expansion=claim_bound))):
        raise ValueError('Exact Q12 public Source construction and frontier claim required')
    authority = feedback['public_composition']['authority']
    _read(authority)
    if origin.get('layered_feedback_delivery') != dict(authority=authority, summaries=NEGATIVE_SUMMARIES):
        raise ValueError('Q12 must use the original qualified summary and public delivery authority')
    return dict(origin=origin, plan=plan, claim=claim, frontier=_read(ORIGINAL_FRONTIER),
        contract=scientific_question(), feedback=feedback, policy={'origin': plan['origin']},
        public_memory_authority=authority, summaries=material['mandatory_negative_evidence_summaries'],
        baseline=feedback['scored_round0_baseline'], champion_feedback=feedback['selection_incumbent'],
        bindings=[sources[CONFIG], sources[PLAN], plan['direct_window_authority'], plan['origin'], claim_bound, feedback_bound,
            plan['public_material'], population_bound, ORIGINAL_FRONTIER, NEGATIVE_REPORT, NEGATIVE_SUMMARIES, authority])


def check_child(candidate, parent):
    child_h = candidate.get('H')
    if (candidate.get('parent') != parent['id'] or candidate.get('axis') != 'H'
            or candidate.get('R') != parent['R']
            or type(child_h) is not dict or set(child_h) != {'path', 'sha256'}
            or type(child_h['path']) is not str or type(child_h['sha256']) is not str
            or re.fullmatch('[0-9a-f]{64}', child_h['sha256']) is None
            or child_h['sha256'] == parent['H']['sha256']):
        raise ValueError('Question 12 may change H only, with the exact original R unchanged')
