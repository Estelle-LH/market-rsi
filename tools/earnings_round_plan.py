"""One finite offline round plan; no authority, transport or budget defaults."""
from pathlib import Path


def round_count(envelope, *, legacy_ceiling=3):
    if type(envelope) is dict and envelope.get('schema') == 'earnings_open_episode_v1':
        from earnings_open_admission import admit
        admit(envelope)
        return envelope['max_rounds']
    if type(envelope) is dict and envelope.get('schema') == 'earnings_capacity_episode_v3':
        from earnings_live_capacity import admit
        admit(envelope)
        return envelope['max_rounds']
    if (type(envelope) is not dict
            or envelope.get('schema') not in {'earnings_capacity_episode_v1', 'earnings_capacity_episode_v2'}
            or envelope.get('mode') != 'offline_replay'
            or not {'grant', 'window'} <= set(envelope)
            or envelope.get('grant') is not None or envelope.get('window') is not None
            or type(envelope.get('max_rounds')) is not int or envelope['max_rounds'] < 1
            or (envelope['schema'] == 'earnings_capacity_episode_v1'
                and envelope['max_rounds'] > legacy_ceiling)):
        raise ValueError('Explicit finite offline episode required; legacy limits remain unchanged')
    return envelope['max_rounds']


def _flat_path(raw, root):
    if type(raw) is not str:
        raise ValueError('Canonical flat declared role slot required')
    path = Path(raw)
    if not path.is_absolute() or str(path) != raw or path.resolve() != path or path.parent != root / 'roles':
        raise ValueError('Canonical flat declared role slot required')
    return raw


def declared_slots(envelope, matched_plan):
    rounds = round_count(envelope)
    raw_root = envelope.get('root')
    if type(raw_root) is not str:
        raise ValueError('Canonical episode root required')
    root = Path(raw_root)
    if not root.is_absolute() or str(root) != raw_root or root.resolve() != root or root.parent == root:
        raise ValueError('Canonical episode root required')
    rows = envelope.get('slots')
    if (type(rows) is not list or len(rows) != rounds
            or any(type(row) is not dict or set(row) != {'controller', 'author', 'review', 'forecast'} for row in rows)):
        raise ValueError('Exact N declared episode rows required')
    if (type(matched_plan) is not dict or set(matched_plan) != {'schema', 'episode', 'rounds'}
            or matched_plan['schema'] != 'earnings_matched_plan_v1'
            or type(matched_plan['rounds']) is not list or len(matched_plan['rounds']) != rounds):
        raise ValueError('Exact N matched rows required')
    declared = [_flat_path(raw, root) for row in rows for raw in row.values()]
    if len(set(declared)) != len(declared):
        raise ValueError('Episode role slots must be unique')
    slots = {role: [row[role] for row in rows] for role in ('controller', 'author', 'review')}
    slots['forecast'] = []
    for index, row in enumerate(matched_plan['rounds']):
        if (type(row) is not dict or set(row) != {'parent', 'candidate', 'downstream'}
                or row['downstream'] != rows[index]['forecast']):
            raise ValueError('Exact ordered parent/candidate/downstream slots required')
        slots['forecast'].extend(_flat_path(row[key], root) for key in ('parent', 'candidate', 'downstream'))
    all_slots = [raw for values in slots.values() for raw in values]
    if len(set(all_slots)) != len(all_slots):
        raise ValueError('All prospective role slots must be unique')
    return slots


def _read(binding):
    from earnings_loop_policy import _read as read_binding
    return read_binding(binding)


def validate_runtime_plan(runtime):
    """Validate immutable episode/plan bindings without opening an owner."""
    if type(runtime) is not dict or runtime.get('schema') != 'earnings_capacity_runtime_v3':
        raise ValueError('Plan-bound runtime v3 required')
    episode = _read(runtime.get('episode'))
    plan = _read(runtime.get('matched_plan'))
    from earnings_loop_policy import CAPACITY_FIELDS
    if (type(episode) is not dict or set(episode) != CAPACITY_FIELDS
            or episode.get('schema') not in {'earnings_capacity_episode_v2', 'earnings_capacity_episode_v3'}
            or type(plan) is not dict
            or plan.get('episode') != runtime['episode']
            or runtime.get('forecast_study') != episode.get('study')
            or any(runtime.get(key) != episode.get(key) for key in ('id', 'root', 'source_commit'))
            or runtime.get('slots') != declared_slots(episode, plan)):
        raise ValueError('Runtime must equal its exact episode and derived finite plan')
    return episode


def validate_context(context, role):
    """Borrow only this role's resources from the checked plan-bound owner."""
    from earnings_capacity_runtime import preflight_runtime
    if (type(context) is not dict or role not in {'controller', 'author', 'review', 'forecast'}
            or context.get('schema') != f'earnings_capacity_{role}_transport_v2'):
        raise ValueError('Plan-bound role context required')
    runtime = preflight_runtime(context.get('runtime'))
    if (runtime['schema'] != 'earnings_capacity_runtime_v3'
            or any(context.get(key) != runtime[key] for key in ('root', 'source_commit', 'rates', 'cutoff_utc'))
            or context.get('limits') != runtime['limits'][role]
            or context.get('slots') != runtime['slots'][role]):
        raise ValueError('Borrowed context differs from its exact runtime role')
    return runtime
