"""Read-only assembly validation before Native mutation or runtime claims."""
from pathlib import Path

from earnings_capacity_adapter import profile
from earnings_capacity_checks import MechanicalProbes
from earnings_effect_review import review as effect_review, SCOPES
from earnings_native_namespace import native_paths
from earnings_source_review import SourceReview
from earnings_round_plan import round_count, declared_slots
from market_rsi import digest
from supervisor_harness import continuous_discovery_batch as native_batch
from supervisor_harness import capacity_feedback_engine as engine


def validate_setup(episode_binding, envelope, assembly, runtime, native, review, *, program_route=False):
    rounds = round_count(envelope, legacy_ceiling=2)
    paths = native_paths(envelope['root'], envelope['id'])
    if (type(native) is not dict or set(native) != {'schema', 'source_root', 'registry_root', 'batch_root',
            'baseline', 'entrypoints', 'batch_config', 'micro_config'}
            or native['schema'] != 'earnings_native_setup_v1'
            or any(native[k] != str(paths[k]) for k in ('source_root', 'registry_root', 'batch_root'))
            or type(envelope['max_rounds']) is not int or envelope['max_rounds'] != rounds):
        raise ValueError('Exact external owned Native setup required')
    if any(paths[k].exists() for k in ('batch_root', 'registry_root', 'probe_root')):
        raise ValueError('Consumed or partial Native episode stays closed; cold replay is separate')
    baseline = engine.identity.validate(native['baseline'])
    if (baseline['model'] != engine.read(envelope['study'])['model']
            or baseline['memory_sha256'] != envelope['initial_state']['sha256']
            or baseline['components']['K']['configuration_sha256'] != digest(envelope['evaluation_kernel'])):
        raise ValueError('Original model, initial memory and kernel identity required')
    source = paths['source_root']
    if not source.is_dir() or source.resolve(strict=True) != source:
        raise ValueError('Canonical prepared immutable Native source directory required')
    for component in baseline['components'].values():
        for name, token in component['sources'].items():
            location = source/name
            if location.resolve(strict=True) != location or not location.is_file():
                raise ValueError('Canonical in-root original Native source required')
            engine.activation._read({'path': str(location), 'sha256': token})
    engine.activation._read(baseline['runtime']['python'], allow_alias=True)
    entries = native['entrypoints']
    if type(entries) is not dict or set(entries) != {'R', 'H'}:
        raise ValueError('Exact literal entrypoints required')
    parser = profile
    if program_route:
        from earnings_open_program import program
        if envelope['schema'] != 'earnings_open_episode_v1':
            raise ValueError('Program setup requires exact opt-in admission')
        parser = program
    for axis, name in entries.items():
        if name not in baseline['components'][axis]['sources'] or not name.endswith('.py'):
            raise ValueError('Declared original axis source required')
        parser((source/name).read_bytes(), axis)
    config = native['batch_config']
    if (type(config) is not dict or set(config) != {'batch_id', 'start_utc', 'deadline_utc', 'max_attempts',
            'initial_incumbent', 'active_pool_capacity', 'learning_checkpoint_version'}
            or config['batch_id'] != envelope['id'] or type(config['max_attempts']) is not int
            or config['max_attempts'] != 3*envelope['max_rounds']
            or type(config['active_pool_capacity']) is not int or config['active_pool_capacity'] not in {2, 3}
            or type(config['learning_checkpoint_version']) is not int or config['learning_checkpoint_version'] != 1
            or config['deadline_utc'] != runtime['deadline_utc']):
        raise ValueError('Exact original-window finite Native batch configuration required')
    native_batch._identifier(config['batch_id'], 'batch ID')
    incumbent = native_batch._initial_incumbent(config['initial_incumbent'])
    if incumbent['candidate_sha256'] != baseline['C']:
        raise ValueError('Original predictor incumbent required')
    if (native_batch._utc(config['start_utc'], 'start') >= native_batch._utc(config['deadline_utc'], 'deadline')
            or native_batch._utc(config['start_utc'], 'start') > native_batch._utc(runtime['cutoff_utc'], 'cutoff')):
        raise ValueError('Native window must precede original runtime cutoff')
    micro = engine.activation.micro.initialize_micro_evolution(native['micro_config'])
    protected = set(baseline['components']['K']['sources']) | set(baseline['components']['C']['sources'])
    python = Path(baseline['runtime']['python']['path'])
    if python.is_relative_to(source): protected.add(str(python.relative_to(source)))
    if not protected.issubset(micro['protected_paths']):
        raise ValueError('All original kernel/predictor/runtime source names must stay protected')
    expected_context = {'model_sha256': baseline['M'], 'evaluation_sha256': baseline['K'],
        'data_scope_sha256': digest({'study': envelope['study'], 'cik': envelope['cik'], 'kernel': envelope['evaluation_kernel']}),
        'authority_sha256': digest({'mode': envelope['mode'], 'grant': envelope['grant'], 'window': envelope['window']}),
        'resource_policy_sha256': digest(assembly['runtime'])}
    if micro['active_pair'] != engine.activation.pair(baseline) or micro['fixed_context'] != expected_context:
        raise ValueError('Native fixed context must bind actual task, model and resources')
    if (type(review) is not dict or set(review) != {'schema', 'source_root', 'slots', 'proposer_id', 'reviewer_id'}
            or review['schema'] != 'earnings_source_review_setup_v1' or review['source_root'] != str(source)
            or set(review['slots']) != set(runtime['slots']['review']) or review['reviewer_id'] != micro['reviewer_id']):
        raise ValueError('Exact original source-review slots/actors required')
    SourceReview(source, slots=review['slots'], proposer_id=review['proposer_id'], reviewer_id=review['reviewer_id'])
    for axis, kind in (('R', 'researcher'), ('H', 'harness')):
        names = set(baseline['components'][axis]['sources']) | {row[axis] for row in review['slots'].values()}
        if set(micro['allowed_write_paths'][kind]) != names:
            raise ValueError('Exact original/prospective literal write scope required')
        if any((source/row[axis]).exists() for row in review['slots'].values()):
            raise ValueError('Prospective literal source was already consumed')
    registration = engine.read(assembly['effect_registration'])
    if (type(registration) is not dict or set(registration) != {'schema', 'reviewer_id', 'proposer_id',
            'review_source', 'probe_source', 'scopes'}
            or registration['schema'] != 'earnings_effect_review_registration_v1'
            or any(registration[k] != review[k] for k in ('proposer_id', 'reviewer_id'))
            or registration['review_source'] != engine.source_of(effect_review)
            or registration['probe_source'] != engine.source_of(MechanicalProbes.run) or registration['scopes'] != SCOPES):
        raise ValueError('Full independent measured-effect registration required before claims')
    plan = engine.read(assembly['matched_plan'])
    if (type(plan) is not dict or set(plan) != {'schema', 'episode', 'rounds'}
            or plan['schema'] != 'earnings_matched_plan_v1' or plan['episode'] != episode_binding
            or type(plan['rounds']) is not list or len(plan['rounds']) != envelope['max_rounds']):
        raise ValueError('Exact prospective matched plan required')
    slots = []
    if envelope['schema'] in {'earnings_capacity_episode_v2','earnings_capacity_episode_v3'} and declared_slots(envelope, plan) != runtime['slots']:
        raise ValueError('Every runtime role must match the single declared finite plan')
    for index, row in enumerate(plan['rounds']):
        if (type(row) is not dict or set(row) != {'parent', 'candidate', 'downstream'}
                or row['downstream'] != envelope['slots'][index]['forecast']):
            raise ValueError('Exact ordered parent/candidate/downstream round slots required')
        slots.extend(row[k] for k in ('parent', 'candidate', 'downstream'))
    if (slots != runtime['slots']['forecast'] or len(set(slots)) != len(slots)
            or any(Path(p).parent != Path(envelope['root'])/'roles' or Path(p).resolve() != Path(p) for p in slots)
            or any(Path(p).exists() for p in slots + [p for v in envelope['slots'] for p in v.values()])):
        raise ValueError('Declared fresh canonical flat role slots required before claims')
    return paths
