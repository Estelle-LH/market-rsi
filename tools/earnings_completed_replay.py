"""Completed-only closure: raw verification, never execution or recovery."""
from pathlib import Path
import fcntl
import os

from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness import continuous_discovery_batch as native

FIELDS = {'schema', 'episode', 'outcome', 'manifest', 'native_snapshot', 'native_journal', 'anchor_version',
          'selected_version', 'selected_sources', 'runtime_terminal', 'sources', 'claims'}


def sources():
    return {name: engine.pin(path) for name, path in {'closure': __file__, 'engine': engine.__file__,
        'driver': engine.driver.__file__, 'driver_io': engine.driver.c.__file__, 'native': native.__file__,
        'identity': engine.identity.__file__, 'activation': engine.activation.__file__,
        'micro': engine.activation.micro.__file__}.items()}


def _native_snapshot(body):
    bound = body['native_snapshot']
    path = Path(bound['path'])
    if path.name != 'batch.json': raise ValueError('Original Native snapshot required')
    journal = path.parent/'journal'
    bindings = body['native_journal']
    if (type(bindings) is not list or not bindings
            or [p.name for p in sorted(journal.iterdir())] != [f'{i:08d}.json' for i in range(1, len(bindings)+1)]
            or [b['path'] for b in bindings] != [str(journal/f'{i:08d}.json') for i in range(1, len(bindings)+1)]):
        raise ValueError('Exact whole Native journal required; no pending recovery')
    records, previous = [], native.ZERO_SHA256
    for index, binding in enumerate(bindings, 1):
        record = engine.read(binding)
        if (type(record) is not dict or set(record) != {'schema', 'sequence', 'event', 'payload', 'previous_sha256', 'event_sha256'}
                or record['schema'] != native.EVENT_SCHEMA or type(record['sequence']) is not int
                or record['sequence'] != index or record['previous_sha256'] != previous
                or record['event_sha256'] != native._digest({k: v for k, v in record.items() if k != 'event_sha256'})
                or Path(binding['path']).read_bytes() != native._canonical(record)+b'\n'):
            raise ValueError('Native journal hash chain drift')
        records.append(record); previous = record['event_sha256']
    raw = engine.read(bound)
    # _replay is the original pure state reducer; no constructor, lock creation,
    # snapshot publication or pending-journal recovery is invoked.
    state = object.__new__(native.ContinuousDiscoveryBatch)._replay(records)
    if (state != raw or not state['initialized'] or state.get('active_attempt_ids', [])
            or any(row['status'] != 'completed' for row in state.get('capacity_work', []))):
        raise ValueError('Native state is ahead, busy or incomplete; no repair')
    return state


def _selected(body, state):
    bound, selected = body['selected_version'], engine.read(body['selected_version'])
    pair = state['micro_evolution']['active_pair']
    if (Path(bound['path']).name != digest(pair)+'.json' or type(selected) is not dict
            or set(selected) != {'manifest', 'entrypoints', 'static_review'}
            or engine.activation.pair(engine.identity.validate(selected['manifest'])) != pair):
        raise ValueError('Exact current selected version required')
    if selected['static_review'] is not None: engine.read(selected['static_review'])
    manifest, bindings = selected['manifest'], body['selected_sources']
    micro = state['micro_evolution']
    anchor_path = Path(bound['path']).parent/(digest(micro['anchor_pair'])+'.json')
    if body['anchor_version']['path'] != str(anchor_path): raise ValueError('Exact retained anchor version required')
    anchor = engine.identity.validate(engine.read(body['anchor_version'])['manifest'])
    handlers = engine.read(body['manifest'])['handler_identity']
    if (engine.activation.pair(anchor) != micro['anchor_pair']
            or any(h.get('initial_identity_sha256') != digest(anchor) for h in handlers.values())
            or manifest['M'] != micro['fixed_context']['model_sha256']
            or manifest['K'] != micro['fixed_context']['evaluation_sha256']
            or any(manifest[k] != anchor[k] for k in ('K', 'M', 'C', 'memory_sha256', 'runtime_sha256'))):
        raise ValueError('Selected version changed original protected task/model/runtime identity')
    python = manifest['runtime']['python']
    expected = {name: token for c in manifest['components'].values() for name, token in c['sources'].items()}
    if type(bindings) is not list or len({b['path'] for b in bindings}) != len(bindings) or python not in bindings:
        raise ValueError('Exact selected sources and original runtime pin required')
    remaining, roots = dict(expected), set()
    for binding in bindings:
        engine.activation._read(binding, allow_alias=binding == python)
        if binding == python: continue
        path = Path(binding['path'])
        matches = [name for name, token in remaining.items() if binding['sha256'] == token
            and path.parts[-len(Path(name).parts):] == Path(name).parts]
        if len(matches) != 1 or path.resolve() != path: raise ValueError('Selected in-root source drift')
        name = matches[0]; roots.add(path.parents[len(Path(name).parts)-1]); remaining.pop(name)
    if remaining or len(roots) != 1: raise ValueError('Selected physical source root mismatch')
    if set(selected['entrypoints']) != {'R', 'H'} or any(
            n not in manifest['components'][a]['sources'] for a, n in selected['entrypoints'].items()):
        raise ValueError('Selected original entrypoint mismatch')


def _work(body, envelope, state):
    rows = {row['work_id']: row for row in state.get('capacity_work', [])}
    expected = set()
    loop = Path(envelope['root'])/'loop'
    for index in range(1, body['outcome']['completed_rounds']+1):
        output = engine.driver._read_pair(loop/f'round-{index:04d}-execute.done.json')['output']
        work_id = 'capacity-'+digest({'episode': body['episode'], 'round': index})
        original = {k: v for k, v in output.items() if k not in {'pair_sha256', 'parent_state', 'capacity_review', 'effect_review'}}
        effect = output.get('effect_review')
        if effect is not None:
            count = len(effect['artifacts'])
            if not count or original['artifacts'][-count:] != effect['artifacts']:
                raise ValueError('Ordinary work and effect artifacts differ')
            original['artifacts'] = original['artifacts'][:-count]
            if effect['comparison'] is not None:
                measured = engine.read(effect['comparison']); location = Path(effect['comparison']['path']).parent
                terminal = engine.read(engine.pin(location/'terminal.json'))
                if terminal != {'status': 'MEASURED', 'comparison': effect['comparison'], 'retry_allowed': False} or (location/'failed.json').exists():
                    raise ValueError('Unclosed shadow trial remains uncertain')
                for arm, shadow_id in zip(('parent', 'child'), measured['work_ids']):
                    row = rows.get(shadow_id, {})
                    if (shadow_id != 'shadow-'+digest({'claim': measured['trial_claim'], 'arm': arm})
                            or row.get('pair_sha256') != measured['originals'][arm]['consumed']['active_pair_sha256']
                            or row.get('output_evidence_sha256') != engine.pin(location/(arm+'.json'))['sha256']):
                        raise ValueError('Shadow work does not bind retained originals')
                    expected.add(shadow_id)
        row = rows.get(work_id, {})
        if row.get('pair_sha256') != output['pair_sha256'] or row.get('output_evidence_sha256') != digest(original):
            raise ValueError('Native completion does not bind sealed ordinary output')
        expected.add(work_id)
    if set(rows) != expected: raise ValueError('Extra or missing Native work cannot be relabelled complete')


def _validate(body, episode_binding):
    if (type(body) is not dict or set(body) != FIELDS or body['schema'] != 'earnings_completed_replay_v1'
            or body['episode'] != episode_binding or body['sources'] != sources()
            or body['claims'] != {'model_authorship': False, 'predictive_gain': False,
                'runtime_owner_verified': body['runtime_terminal'] is not None}):
        raise ValueError('Exact completed replay closure/source required')
    envelope = engine.read(episode_binding)
    engine.driver._artifacts(body['sources'])
    outcome = engine.driver.replay_completed(Path(envelope['root'])/'loop', manifest_binding=body['manifest'])
    if outcome != body['outcome'] or outcome['completed_rounds'] != envelope['max_rounds']:
        raise ValueError('Exact fully completed driver outcome required')
    descriptor = os.open(Path(body['native_snapshot']['path']).parent/'.batch.lock', os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        state = _native_snapshot(body)
        if digest(state['micro_evolution']['active_pair']) != outcome['result']['pair_sha256']:
            raise ValueError('Final Native selection differs from driver result')
        _selected(body, state); _work(body, envelope, state)
        if body['runtime_terminal'] is not None:
            terminal = engine.read(body['runtime_terminal'])
            engine.driver._artifacts(terminal)
            if (terminal['status'] != 'COMPLETED_COMPONENT_CONTEXT' or terminal['error_type'] is not None
                    or terminal['retry_allowed'] is not False or terminal['budget_summary']['blocked'] is not False
                    or terminal['budget_summary']['unresolved_reserved_usd'] != 0
                    or engine.read(terminal['runtime'])['id'] != envelope['id']):
                raise ValueError('Original owner/accounting is not closed successfully')
            runtime = engine.read(terminal['runtime'])
            import hashlib
            claim_path = Path(runtime['ledger']).parent/'.capacity-runtime-claims'/(hashlib.sha256(envelope['id'].encode()).hexdigest()+'.json')
            claim = engine.read(engine.pin(claim_path))
            if (body['runtime_terminal']['path'] != str(claim_path.with_suffix('.result.json'))
                    or claim['runtime'] != terminal['runtime'] or claim['id'] != envelope['id']
                    or claim['source_commit'] != envelope['source_commit'] or claim['retry_allowed'] is not False
                    or runtime['root'] != envelope['root'] or runtime['source_commit'] != envelope['source_commit']):
                raise ValueError('Owner terminal differs from permanent original claim')
        if _native_snapshot(body) != state or engine.driver.replay_completed(
                Path(envelope['root'])/'loop', manifest_binding=body['manifest']) != outcome:
            raise ValueError('Closure changed during read-only verification')
    return outcome


def seal_completed_replay(episode_binding, outcome, *, manifest_binding, native_snapshot_binding,
        native_journal_bindings, selected_version_binding, selected_source_bindings, runtime_terminal_binding=None):
    body = {'schema': 'earnings_completed_replay_v1', 'episode': episode_binding, 'outcome': outcome,
        'manifest': manifest_binding, 'native_snapshot': native_snapshot_binding, 'native_journal': native_journal_bindings,
        'selected_version': selected_version_binding, 'selected_sources': selected_source_bindings,
        'runtime_terminal': runtime_terminal_binding, 'sources': sources(),
        'claims': {'model_authorship': False, 'predictive_gain': False, 'runtime_owner_verified': runtime_terminal_binding is not None}}
    anchor = engine.read(native_snapshot_binding)['micro_evolution']['anchor_pair']
    body['anchor_version'] = engine.pin(Path(selected_version_binding['path']).parent/(digest(anchor)+'.json'))
    path = Path(engine.read(episode_binding)['root'])/'completed-replay.json'
    if path.exists() or path.is_symlink(): raise ValueError('Consumed replay closure stays closed')
    _validate(body, episode_binding)
    return engine.save(path, body)


def replay_completed(episode_binding, closure_binding):
    path = Path(engine.read(episode_binding)['root'])/'completed-replay.json'
    if closure_binding.get('path') != str(path): raise ValueError('Exact existing completed closure required')
    body = engine.read(closure_binding)
    result = _validate(body, episode_binding)
    if engine.read(closure_binding) != body: raise ValueError('Completed closure drift')
    return result
