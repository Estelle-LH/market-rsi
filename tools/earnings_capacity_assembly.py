"""Explicit offline assembly of the existing capacity engine and one owner."""
from pathlib import Path
import hashlib

from earnings_capacity_adapter import EarningsCapacity
from earnings_capacity_task import EarningsTask
from earnings_controller import CapacityController, CapacityAuthor
from earnings_entry import CapacityForecast
from earnings_capacity_runtime import preflight_runtime, open_capacity_runtime
from earnings_pending_evolution import PendingEvolution
from earnings_source_review import SourceReview
from earnings_assembly_readiness import validate_setup
import earnings_native_namespace as namespace
from market_rsi import digest
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
from supervisor_harness import capacity_feedback_engine as engine


def constructor_sources():
    return {name: engine.source_of(method) for name, method in {
        'controller': CapacityController.propose, 'author': CapacityAuthor.author,
        'review': SourceReview.review, 'forecast': CapacityForecast.forecast,
        'pending': PendingEvolution.handle}.items()}


def validate_assembly(episode_binding, assembly_binding, *, client_factory, task=None):
    """No factory/owner/native constructor; normal Task admission is preserved."""
    if not callable(client_factory):
        raise ValueError('Explicit trusted offline transport required; no paid fallback')
    envelope, assembly = engine.read(episode_binding), engine.read(assembly_binding)
    from earnings_live_capacity import live, admit
    actual_live = live(envelope)
    if actual_live:
        admit(envelope)
    fields = {'schema', 'mode', 'episode', 'runtime', 'native', 'matched_plan',
              'effect_registration', 'source_review', 'constructors', 'transport', 'claims'}
    if (type(assembly) is not dict or set(assembly) != fields | ({'transport_policy'} if actual_live else set())
            or assembly['schema'] != ('earnings_capacity_assembly_v2' if actual_live else 'earnings_capacity_assembly_v1')
            or assembly['mode'] != ('real_provider' if actual_live else 'offline_replay') or assembly['mode'] != envelope.get('mode')
            or assembly['episode'] != episode_binding or assembly['constructors'] != constructor_sources()
            or assembly['transport'] != engine.source_of(client_factory)
            or assembly['claims'] != {'model_authorship': False, 'predictive_gain': False}):
        raise ValueError('Exact source-bound offline assembly required')
    engine.driver._artifacts(assembly)
    runtime = preflight_runtime(assembly['runtime'])
    if ((envelope.get('schema'), runtime['schema']) not in {
                ('earnings_capacity_episode_v1', 'earnings_capacity_runtime_v2'),
                ('earnings_capacity_episode_v2', 'earnings_capacity_runtime_v3'),
                ('earnings_capacity_episode_v3', 'earnings_capacity_runtime_v3')}
            or runtime['purpose'] != 'capacity_episode'
            or any(runtime[k] != envelope[k] for k in ('id', 'root', 'source_commit'))
            or runtime['forecast_study'] != envelope['study']
            or any(runtime['sources']['factory_'+name] != engine.pin(__file__)
                   for name in ('controller','author','review','forecast'))):
        raise ValueError('Episode and actual common runtime/factory bindings differ')
    if actual_live:
        grant = engine.read(envelope['grant'])
        if (any(runtime[key] != grant[key] for key in ('ledger','baseline','cutoff_utc','deadline_utc','additional_cap_nano_usd'))
                or runtime['rates'] != engine.read(grant['runtime'])['models']['gpt-6.1-sol']):
            raise ValueError('Actual live owner differs from approved finite resource grant')
        expected_policy = {'schema':'edgar_foreground_slow_call_policy_v1','source_commit':grant['source_commit'],
            'original_runtime_request_timeout_seconds':engine.read(grant['runtime'])['request_timeout_seconds'],
            'effective_socket_timeout_seconds':600,'role_and_global_deadlines_unchanged':True,'retry_allowed':False}
        actual_policy = engine.read(assembly['transport_policy'])
        if actual_policy != expected_policy or any(type(actual_policy[k]) != type(v) for k,v in expected_policy.items()):
            raise ValueError('Explicit original-byte foreground600 policy required before owner')
    if runtime['schema'] == 'earnings_capacity_runtime_v3' and (
            runtime['episode'] != episode_binding or runtime['matched_plan'] != assembly['matched_plan']):
        raise ValueError('Runtime must bind the actual assembly episode and matched plan')
    for name in ('controller', 'author', 'review'):
        if (runtime['slots'][name] != [row[name] for row in envelope['slots']]
                or any(runtime['limits'][name][key] > envelope['role_limits'][name][key]
                       for key in runtime['limits'][name])):
            raise ValueError('Original finite episode role slots/limits required')
    native, review = engine.read(assembly['native']), engine.read(assembly['source_review'])
    validate_setup(episode_binding, envelope, assembly, runtime, native, review)
    claims = Path(runtime['ledger']).parent/'.capacity-runtime-claims'
    token = hashlib.sha256(runtime['id'].encode()).hexdigest()
    # Only inspect the exact prospective claim metadata, never the ledger DB.
    if any((claims/(token+suffix)).exists() for suffix in ('.json', '.result.json')):
        raise ValueError('Consumed runtime ID stays closed; use completed-only replay')
    task = EarningsTask() if task is None else task
    task.preflight(envelope)
    return envelope, assembly, native, review, task


def _native(setup):
    if Path(setup['batch_root']).exists() or Path(setup['registry_root']).exists():
        raise ValueError('Consumed or partial Native setup stays closed')
    batch = ContinuousDiscoveryBatch(setup['batch_root'], allow_temporary=
        namespace.NATIVE_RUNTIME_ROOT != Path.home()/'Library/Application Support/MarketRSI/co-evo-earnings/episodes')
    batch.initialize(**setup['batch_config'])
    state = batch.snapshot()
    batch.record_micro_evolution('initialize', setup['micro_config'], expected_state_sha256=state['state_sha256'])
    return EarningsCapacity(batch, source_root=setup['source_root'], registry_root=setup['registry_root'],
                            baseline=setup['baseline'], entrypoints=setup['entrypoints'])


def run_assembled_capacity(episode_binding, assembly_binding, *, client_factory=None, task=None):
    from earnings_live_capacity import live, provider_client
    actual_live = live(engine.read(episode_binding))
    if actual_live and client_factory is None: client_factory = provider_client
    envelope, assembly, native_setup, source_setup, task = validate_assembly(
        episode_binding, assembly_binding, client_factory=client_factory, task=task)
    source_review = SourceReview(source_setup['source_root'], slots=source_setup['slots'],
        proposer_id=source_setup['proposer_id'], reviewer_id=source_setup['reviewer_id'],
        micro_policy='earnings_micro_v1' if actual_live else None)
    def controller_factory(context, *, budget, client_factory):
        return CapacityController(context, budget=budget, client_factory=client_factory,
            **({'micro_policy':'earnings_micro_v1'} if actual_live else {})).propose
    def author_factory(context, *, budget, client_factory):
        return CapacityAuthor(context, budget=budget, client_factory=client_factory,
            **({'micro_policy':'earnings_micro_v1'} if actual_live else {})).author
    def review_factory(context, *, budget, client_factory):
        return source_review.review
    def forecast_factory(context, *, budget, client_factory):
        return CapacityForecast(context, budget=budget, client_factory=client_factory,
            study_binding=envelope['study'], evaluation_kernel=envelope['evaluation_kernel'],
            clock_binding=engine.pin(Path(envelope['root'])/'clock.json'),
            transport_policy_binding=assembly['transport_policy'] if actual_live else None).forecast
    with open_capacity_runtime(assembly['runtime'], client_factory=client_factory, role_factories={
            'controller': controller_factory, 'author': author_factory, 'review': review_factory,
            'forecast': forecast_factory}) as owner:
        capacity = _native(native_setup)
        roles = owner['roles']
        pending = PendingEvolution(episode_binding, capacity, task, roles['forecast'],
            plan_binding=assembly['matched_plan'], registration_binding=assembly['effect_registration'])
        from earnings_feedback_loop import run_capacity
        result = run_capacity(episode_binding, capacity, roles=roles, task=task, pending_handler=pending.handle)
    from earnings_completed_replay import seal_completed_replay
    snapshot = engine.pin(capacity.batch.root/'batch.json')
    pair = engine.read(snapshot)['micro_evolution']['active_pair']
    selected_binding = engine.pin(capacity.registry/(digest(pair)+'.json'))
    selected = engine.read(selected_binding)['manifest']
    source_bindings = {str(capacity.source_root/name): engine.pin(capacity.source_root/name)
        for component in selected['components'].values() for name in component['sources']}
    python = selected['runtime']['python']
    source_bindings[python['path']] = python
    terminal = Path(engine.read(assembly['runtime'])['ledger']).parent/'.capacity-runtime-claims'/(
        hashlib.sha256(envelope['id'].encode()).hexdigest()+'.result.json')
    seal_completed_replay(episode_binding, result,
        manifest_binding=engine.pin(Path(envelope['root'])/'loop'/'manifest.json'),
        native_snapshot_binding=snapshot,
        native_journal_bindings=[engine.pin(p) for p in sorted((capacity.batch.root/'journal').iterdir())],
        selected_version_binding=selected_binding, selected_source_bindings=list(source_bindings.values()),
        runtime_terminal_binding=engine.pin(terminal))
    return result
