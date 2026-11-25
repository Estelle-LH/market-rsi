# Source excerpt. Imports and other methods are omitted.

def declared_test(origin):
    """Small literal projection into C/A/Review, not just an unread path/hash."""
    claim=expansion(origin)
    frontier=saved(claim['frontier'])
    group=next(g for g in frontier['expansions'] if g['parent_id']==claim['parent_id'])
    hypothesis=next(c for c in group['children'] if c['hypothesis_id']==claim['hypothesis_id'])
    return dict(generation=claim['generation'],logical_round=claim['logical_round'],
        actual_parent_id=claim['parent_id'],frontier_expansion=origin['frontier_expansion'],**hypothesis)
