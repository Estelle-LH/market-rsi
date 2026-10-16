"""Small evidence-linked research pool; retention is not Native adoption.

Pure state transitions. Trusted callers independently verify original scores,
candidate review and execution before supplying them. File hashes are integrity
checks, not proof of model authorship, scientific merit or permission to run.
"""
from copy import deepcopy
import math
from pathlib import Path
import re

from earnings_entry import checked
from market_rsi import digest
from supervisor_harness.feedback_linked_loop import _artifacts


def _sha(value):
    if type(value) is not str or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('Exact identity hash required')
    return value


def _bindings(values):
    if type(values) is not list or not values:
        raise ValueError('Nonempty retained evidence bindings required')
    for item in values:
        if type(item) is not dict or set(item) != {'path', 'sha256'}:
            raise ValueError('Exact evidence binding required')
        if (type(item['path']) is not str or not Path(item['path']).is_absolute()
                or str(Path(item['path']).resolve()) != item['path']):
            raise ValueError('Canonical absolute evidence path required')
        _sha(item['sha256'])
        checked(item)
    return values


def version(R, H, *, parent=None, axis='baseline', method='baseline', author='human', evidence=None):
    _bindings([R, H])
    if (axis not in {'baseline', 'R', 'H'} or (axis == 'baseline') != (parent is None)
            or any(type(v) is not str or not v.strip() or len(v) > 1000 for v in (method, author))):
        raise ValueError('Named source-bound single-axis version required')
    if parent is not None:
        _sha(parent)
    rows = [] if evidence is None else deepcopy(evidence)
    if rows:
        _bindings(rows)
    return dict(id=digest({a: b['sha256'] for a, b in [('R', R), ('H', H)]}),
                R=deepcopy(R), H=deepcopy(H), parent=parent, axis=axis,
                method=method, author=author, evidence=rows)


def _event(state, kind, body):
    event = dict(index=len(state['history']), kind=kind, body=deepcopy(body),
                 previous=None if not state['history'] else state['history'][-1]['sha256'])
    state['history'].append(dict(event, sha256=digest(event)))
    return state


def initialize(stable, protected, *, exposed_companies=None):
    if type(protected) is not dict or set(protected) != {'K', 'M', 'C'}:
        raise ValueError('Protected K/M/C identities required')
    for value in protected.values():
        _sha(value)
    if version(**{k: stable[k] for k in ('R', 'H', 'parent', 'axis', 'method', 'author', 'evidence')}) != stable:
        raise ValueError('Exact stable source identity required')
    state = dict(schema='earnings_population_v1', protected=deepcopy(protected),
                 anchor_id=stable['id'], stable_id=stable['id'], explorers=[],
                 versions={stable['id']: deepcopy(stable)}, observations=[], history=[],
                 exposed_companies=list(exposed_companies or []))
    _event(state, 'initialize', dict(stable=stable, protected=protected,
                                  exposed_companies=state['exposed_companies']))
    return validate(state)


def validate(state):
    _artifacts(state)
    if (type(state) is not dict or set(state) != {'schema', 'protected', 'anchor_id', 'stable_id',
            'explorers', 'versions', 'observations', 'history', 'exposed_companies'}
            or state['schema'] != 'earnings_population_v1' or not state['history']
            or set(state['protected']) != {'K', 'M', 'C'}):
        raise ValueError('Exact bounded population state required')
    for token in state['protected'].values():
        _sha(token)
    first = state['history'][0]
    if (first['kind'] != 'initialize' or first['body']['protected'] != state['protected']
            or first['body']['stable']['id'] != state['anchor_id']):
        raise ValueError('Protected identity or anchor drift')
    active = [state['stable_id'], *state['explorers']]
    if (len(state['explorers']) > 2 or len(active) != len(set(active))
            or any(key not in state['versions'] for key in [state['anchor_id'], *active])
            or len(state['exposed_companies']) != len(set(state['exposed_companies']))):
        raise ValueError('One stable plus at most two unique explorers required')
    for key, item in state['versions'].items():
        if (version(**{k: item[k] for k in ('R', 'H', 'parent', 'axis', 'method', 'author', 'evidence')}) != item
                or item['id'] != key or item['parent'] is not None and item['parent'] not in state['versions']):
            raise ValueError('Version source/parent drift')
    previous = None
    for index, item in enumerate(state['history']):
        if (item['index'] != index or item['previous'] != previous
                or digest({k: v for k, v in item.items() if k != 'sha256'}) != item['sha256']):
            raise ValueError('Retained history changed')
        previous = item['sha256']
    # Bind current results and selection to the journal, not just its hashes.
    replay = dict(versions={state['anchor_id']: first['body']['stable']},
                  stable_id=state['anchor_id'], explorers=[], observations=[],
                  exposed_companies=list(first['body']['exposed_companies']))
    for event in state['history'][1:]:
        kind, body = event['kind'], event['body']
        if kind == 'retain_exploration':
            replay['versions'][body['version']['id']] = body['version']
            replay['explorers'].append(body['version']['id'])
        elif kind == 'retire_exploration':
            replay['explorers'].remove(body['id'])
        elif kind == 'observe':
            replay['observations'].append(body)
            replay['exposed_companies'].append(body['company_id'])
        elif kind == 'explicit_selection':
            if body['before'] != replay['stable_id']:
                raise ValueError('Selection parent differs from preceding journal')
            replay['stable_id'] = body['after']
            replay['explorers'].remove(body['after'])
        else:
            raise ValueError('Unknown population transition')
    if any(digest(state[k]) != digest(v) for k, v in replay.items()):
        raise ValueError('Current population differs from retained journal replay')
    return state


def retain(state, child, *, reason, evidence):
    validate(state)
    _bindings(evidence)
    if type(reason) is not str or not reason.strip():
        raise ValueError('Distinct follow-up reason required')
    if len(state['explorers']) >= 2 or child['id'] in state['versions']:
        raise ValueError('Explorer pool full or version already archived')
    parent = state['versions'].get(child['parent'])
    if parent is None or child['axis'] not in {'R', 'H'}:
        raise ValueError('Existing research parent required')
    changed = [a for a in ('R', 'H') if child[a]['sha256'] != parent[a]['sha256']]
    if changed != [child['axis']]:
        raise ValueError('Exactly the declared R/H component may change')
    result = deepcopy(state)
    result['versions'][child['id']] = deepcopy(child)
    result['explorers'].append(child['id'])
    _event(result, 'retain_exploration', dict(version=child, reason=reason, evidence=evidence))
    return validate(result)


def retire(state, branch_id, *, reason, evidence):
    validate(state)
    _bindings(evidence)
    if branch_id not in state['explorers'] or type(reason) is not str or not reason.strip():
        raise ValueError('Only an exploratory branch can retire with a reason')
    result = deepcopy(state)
    result['explorers'].remove(branch_id)
    _event(result, 'retire_exploration', dict(id=branch_id, reason=reason, evidence=evidence))
    return validate(result)


def validate_result(row):
    if (type(row) is not dict or set(row) != {'version_id', 'points', 'evidence'}
            or type(row['points']) not in (int, float) or not math.isfinite(row['points'])
            or not 0 <= row['points'] <= 5 or row['points'] * 2 != int(row['points'] * 2)):
        raise ValueError('Original complete five-target half-point score required')
    _sha(row['version_id'])
    _bindings(row['evidence'])
    return row


def observe(state, company_id, results, *, feedback):
    validate(state)
    _bindings([feedback])
    active = {state['stable_id'], *state['explorers']}
    if (type(company_id) is not str or not company_id or company_id in state['exposed_companies']
            or type(results) is not list or len(results) != len(active)
            or {row.get('version_id') for row in results} != active):
        raise ValueError('Fresh company and one matched result per active version required')
    for row in results:
        validate_result(row)
    result = deepcopy(state)
    observation = dict(company_id=company_id, stable_id=state['stable_id'],
                       results=deepcopy(results), feedback=deepcopy(feedback))
    result['observations'].append(observation)
    result['exposed_companies'].append(company_id)
    _event(result, 'observe', observation)
    return validate(result)


def promote(state, branch_id, *, evidence, minimum_companies=2):
    """Explicit host selection; never a score-triggered Native activation."""
    validate(state)
    _bindings(evidence)
    if (branch_id not in state['explorers'] or type(minimum_companies) is not int
            or minimum_companies < 2):
        raise ValueError('Exploratory version and multiple-company evidence required')
    deltas = []
    for item in state['observations']:
        values = {row['version_id']: row['points'] for row in item['results']}
        if item['stable_id'] == state['stable_id'] and branch_id in values:
            deltas.append(values[branch_id] - values[state['stable_id']])
    if len(deltas) < minimum_companies or min(deltas) < 0 or sum(deltas) / len(deltas) < 0.5:
        raise ValueError('Repeated matched nonregressing half-point benefit not demonstrated')
    result = deepcopy(state)
    old = result['stable_id']
    result['stable_id'] = branch_id
    result['explorers'].remove(branch_id)
    _event(result, 'explicit_selection', dict(before=old, after=branch_id, evidence=evidence,
                                           matched_deltas=deltas))
    return validate(result)
