# Source excerpt. Imports and other methods are omitted.

def declared_test(origin):
    """Small literal projection into C/A/Review, not just an unread path/hash."""
    claim=expansion(origin)
    frontier=saved(claim['frontier'])
    from earnings_population_layered import slot_resolution
    plan=None if 'substitution' not in claim else e.strict_json((e.REPO/PLAN).read_bytes())
    resolved=slot_resolution(frontier,claim,frontier_binding=claim['frontier'],plan=plan)
    hypothesis=resolved['contract']
    return dict(generation=claim['generation'],logical_round=claim['logical_round'],
        actual_parent_id=claim['parent_id'],
        **(dict(slot_hypothesis_id=resolved['slot_hypothesis_id'])
           if frontier.get('schema')=='edgar25_depth_frontier_v5' else {}),
        frontier_expansion=origin['frontier_expansion'],**hypothesis)
