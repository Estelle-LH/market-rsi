"""Opt-in wiring of open programs to the existing shared owner and engine."""
import hashlib
from pathlib import Path

from earnings_assembly_readiness import validate_setup
from earnings_capacity_runtime import preflight_runtime, open_capacity_runtime
from earnings_capacity_checks import MechanicalProbes
from earnings_completed_replay import seal_completed_replay
from earnings_entry import CapacityForecast
from earnings_open_admission import admit, read, slots, ROOT
from earnings_open_broker import ResearchBroker
from earnings_open_capacity import ProgramCapacity
from earnings_open_code import DockerRunner
from earnings_open_literature import LiteratureBroker
from earnings_open_roles import OpenController, OpenAuthor
from earnings_open_source_review import ProgramSourceReview
from earnings_open_task import OpenTask
from earnings_pending_evolution import PendingEvolution
from earnings_live_capacity import provider_client
import earnings_native_namespace as namespace
from market_rsi import digest
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
from supervisor_harness import capacity_feedback_engine as engine


def constructors():
    return {name:engine.source_of(method) for name,method in {
        'controller':OpenController.propose,'author':OpenAuthor.author,'review':ProgramSourceReview.review,
        'forecast':CapacityForecast.forecast,'pending':PendingEvolution.handle}.items()}


def followthrough_factories(*, enabled, broker, study, kernel, clock, transport):
    """Exact one-role followthrough; unused roles are constructed closed.

    No new provider, budget, code execution or scientific selection is added.
    The task-specific caller admits the original decision and candidate review.
    """
    if enabled not in {'author','forecast'}:
        raise ValueError('One declared Author or Forecast stage required')
    def disabled(context, *, budget, client_factory):
        def refuse(*args, **kwargs):
            raise ValueError('Role not authorized in this followthrough stage')
        return refuse
    def author(context, *, budget, client_factory):
        return OpenAuthor(context,budget=budget,client_factory=client_factory,broker=broker,
            socket_timeout_seconds=900).author
    def forecast(context, *, budget, client_factory):
        return CapacityForecast(context,budget=budget,client_factory=client_factory,
            study_binding=study,evaluation_kernel=kernel,clock_binding=clock,
            transport_policy_binding=transport).forecast
    return {name:(author if name=='author' else forecast) if name==enabled else disabled
        for name in ('controller','author','review','forecast')}


def validate(episode_binding,assembly_binding,*,require_review=True):
    envelope,assembly=read(episode_binding),read(assembly_binding)
    company,state=admit(envelope)
    fields={'schema','episode','runtime','native','matched_plan','effect_registration','source_review',
        'constructors','transport','transport_policy','independent_review','claims'}
    if (type(assembly) is not dict or set(assembly)!=fields or assembly['schema']!='earnings_open_assembly_v1'
            or assembly['episode']!=episode_binding or assembly['constructors']!=constructors()
            or assembly['transport']!=engine.source_of(provider_client)
            or assembly['claims']!={'model_authorship':False,'predictive_gain':False}):
        raise ValueError('Exact opt-in open-program assembly required')
    runtime=preflight_runtime(assembly['runtime']);grant=read(envelope['grant'])
    matched=read(assembly['matched_plan'])
    if (runtime['schema']!='earnings_capacity_runtime_v2' or runtime['purpose']!='capacity_episode'
            or any(runtime[k]!=envelope[k] for k in ('id','root','source_commit'))
            or any(runtime[k]!=grant[k] for k in ('ledger','baseline','cutoff_utc','deadline_utc','additional_cap_nano_usd'))
            or runtime['forecast_study']!=envelope['study'] or matched['episode']!=episode_binding
            or runtime['slots']!=slots(envelope,matched)
            or any(runtime['sources']['factory_'+name]!=engine.pin(__file__) for name in ('controller','author','review','forecast'))
            or any(runtime['limits'][role]!=envelope['role_limits'][role] for role in ('controller','author','review'))):
        raise ValueError('Original owner must bind the exact open plan and terminal Controller')
    if any(Path(p).exists() for values in runtime['slots'].values() for p in values):
        raise ValueError('Consumed ordinary, shadow or terminal role slot stays closed')
    policy=read(assembly['transport_policy'])
    followup=grant.get('schema')=='earnings_research_followup_grant_v1'
    if (policy!={'schema':('edgar_foreground_role_socket_policy_v1' if followup else 'edgar_foreground_slow_call_policy_v1'),'source_commit':grant['source_commit'],
            'original_runtime_request_timeout_seconds':read(grant['runtime'])['request_timeout_seconds'],
            'effective_socket_timeout_seconds':600,'role_and_global_deadlines_unchanged':True,'retry_allowed':False,
            **({'author_socket_timeout_seconds':900} if followup else {}),
            **({'author_reasoning_effort':'high'} if 'role_efforts' in runtime else {})}
            or type(policy['effective_socket_timeout_seconds']) is not int
            or type(policy['original_runtime_request_timeout_seconds']) is not int
            or type(policy['role_and_global_deadlines_unchanged']) is not bool
            or type(policy['retry_allowed']) is not bool
            or followup and type(policy['author_socket_timeout_seconds']) is not int):
        raise ValueError('Exact retained foreground transport policy required')
    native,source_review=read(assembly['native']),read(assembly['source_review'])
    validate_setup(episode_binding,envelope,assembly,runtime,native,source_review,program_route=True)
    study=read(envelope['study'])
    if 'program_lineage' in study:
        from earnings_open_continuation import verify
        lineage=verify(study['program_lineage'])
        baseline=engine.identity.validate(native['baseline'])
        if any(baseline['components'][axis]['sources'].get(native['entrypoints'][axis])!=
                lineage['sources'][axis]['sha256'] for axis in ('R','H')):
            raise ValueError('Prepared baseline did not inherit the exact adopted programs')
        old=read(lineage['selected_version'])['manifest']
        if any(baseline[k]!=old[k] for k in ('K','C','M','runtime')):
            raise ValueError('Source carry-forward changed protected predictor/kernel/model/runtime')
    claim=Path(grant['ledger']).parent/'.capacity-runtime-claims'/hashlib.sha256(grant['id'].encode()).hexdigest()
    if any(Path(str(claim)+suffix).exists() for suffix in ('.json','.result.json')):
        raise ValueError('Consumed runtime ID remains closed')
    if require_review:
        review=read(assembly['independent_review'])
        if (review.get('verdict')!='PASS_FOR_BOUNDED_OPEN_RESEARCH' or review.get('blocking_findings')!=[]
                or review.get('reviewed_sources')!=grant['sources'] or review.get('reviewer') in {None,'Root'}
                or review.get('reviewed_configuration_sha256')!=digest({k:v for k,v in assembly.items() if k!='independent_review'})
                or review.get('episode')!=episode_binding):
            raise ValueError('Distinct exact-source prospective review required before owner')
    engine.driver._artifacts(assembly)
    return envelope,assembly,native,source_review


def run(episode_binding,assembly_binding):
    envelope,assembly,setup,review_setup=validate(episode_binding,assembly_binding)
    root=Path(envelope['root'])
    root.mkdir(parents=True,exist_ok=False)
    # Freeze the original clock while the new root is empty. The unchanged
    # owner subsequently loads this exact seal; setup time consumes the window.
    from earnings_clock import capture_or_load
    runtime=read(assembly['runtime'])
    capture_or_load(root,{'source_commit':runtime['source_commit'],
        'new_request_cutoff_utc':runtime['cutoff_utc'],'deadline_utc':runtime['deadline_utc']})
    runner=DockerRunner(root/'code',max_calls=80)
    literature=LiteratureBroker(root/'literature',max_requests=8)
    task=OpenTask();task.preflight(envelope)
    if Path(setup['batch_root']).exists() or Path(setup['registry_root']).exists():
        raise ValueError('Consumed Native setup remains closed')
    batch=ContinuousDiscoveryBatch(setup['batch_root'],allow_temporary=
        namespace.NATIVE_RUNTIME_ROOT!=Path.home()/'Library/Application Support/MarketRSI/co-evo-earnings/episodes')
    batch.initialize(**setup['batch_config'])
    batch.record_micro_evolution('initialize',setup['micro_config'],expected_state_sha256=batch.snapshot()['state_sha256'])
    capacity=ProgramCapacity(batch,source_root=setup['source_root'],registry_root=setup['registry_root'],
        baseline=setup['baseline'],entrypoints=setup['entrypoints'])
    traces={Path(p).name:p for p in runtime['slots']['forecast']}
    study=read(envelope['study'])
    if 'program_lineage' in study:
        from earnings_open_continuation import verify
        traces.update(verify(study['program_lineage'])['trace_slots'])
    research_context_binding=None
    if read(envelope['grant']).get('schema')=='earnings_research_followup_grant_v1':
        from earnings_open_fresh_grant import policy
        research_context_binding=policy().get('continuation',{}).get('research_context')
    broker=ResearchBroker(root/'research-actions',company=task.company,capacity=capacity,
        runner=runner,literature=literature,trace_slots=traces,
        research_context_binding=research_context_binding)
    task.capacity,task.runner,task.broker=capacity,runner,broker
    transport_policy=read(assembly['transport_policy'])
    forecast_transport=assembly['transport_policy']
    if transport_policy['schema']=='edgar_foreground_role_socket_policy_v1':
        # The forecast consumer retains its exact original600-second contract.
        # Only the independently bound Author uses the declared900-second role.
        forecast_transport=engine.save(root/'forecast-transport-policy.json',{
            **{k:v for k,v in transport_policy.items() if k not in {'author_socket_timeout_seconds','author_reasoning_effort'}},
            'schema':'edgar_foreground_slow_call_policy_v1'})
    source_review=ProgramSourceReview(review_setup['source_root'],slots=review_setup['slots'],
        proposer_id=review_setup['proposer_id'],reviewer_id=review_setup['reviewer_id'],runner=runner)
    def controller_factory(context,*,budget,client_factory):
        return OpenController(context,budget=budget,client_factory=client_factory,broker=broker).propose
    def author_factory(context,*,budget,client_factory):
        return OpenAuthor(context,budget=budget,client_factory=client_factory,broker=broker,
            socket_timeout_seconds=transport_policy.get('author_socket_timeout_seconds')).author
    def review_factory(context,*,budget,client_factory):return source_review.review
    def forecast_factory(context,*,budget,client_factory):
        return CapacityForecast(context,budget=budget,client_factory=client_factory,
            study_binding=envelope['study'],evaluation_kernel=envelope['evaluation_kernel'],
            clock_binding=engine.pin(root/'clock.json'),transport_policy_binding=forecast_transport).forecast
    with open_capacity_runtime(assembly['runtime'],client_factory=provider_client,role_factories={
            'controller':controller_factory,'author':author_factory,'review':review_factory,'forecast':forecast_factory}) as owner:
        pending=PendingEvolution(episode_binding,capacity,task,owner['roles']['forecast'],
            plan_binding=assembly['matched_plan'],registration_binding=assembly['effect_registration'])
        roles=owner['roles']
        result=engine.run(episode_binding,capacity,task,services={
            'controller':roles['controller'],'author':roles['author'],'review':roles['review'],
            'execute':roles['forecast']},pending_handler=pending.handle)
        if result['status']!='completed':raise RuntimeError('Open driver did not complete; no further launch')
        previous=result['result'];pair=previous['pair_sha256']
        profiles={axis:capacity.resolve(axis,expected_pair_sha256=pair)['profile'] for axis in ('R','H')}
        prompt=task.packet(envelope,{'previous_result':previous,
            'previous_feedback_sha256':engine.driver.c._digest(previous)},profiles,pair)
        packet=engine.save(root/'terminal-controller-packet.json',prompt)
        terminal=roles['controller'](prompt,runtime['slots']['controller'][-1])
        task.decision(engine.read(terminal),prompt)
        terminal_binding=engine.save(root/'terminal-controller.json',{'packet':packet,'original':terminal,
            'feedback_sha256':prompt['feedback_sha256'],'applied':False,
            'scope':'Actual next Controller input/decision only; no additional evolution authorized'})
    snapshot=engine.pin(batch.root/'batch.json')
    selected=engine.pin(capacity.registry/(digest(batch.snapshot()['micro_evolution']['active_pair'])+'.json'))
    manifest=engine.read(selected)['manifest']
    selected_sources=[engine.pin(capacity.source_root/name) for part in manifest['components'].values() for name in part['sources']]
    selected_sources.append(manifest['runtime']['python'])
    terminal_owner=Path(runtime['ledger']).parent/'.capacity-runtime-claims'/(
        hashlib.sha256(envelope['id'].encode()).hexdigest()+'.result.json')
    closure=seal_completed_replay(episode_binding,result,manifest_binding=engine.pin(root/'loop'/'manifest.json'),
        native_snapshot_binding=snapshot,native_journal_bindings=[engine.pin(p) for p in sorted((batch.root/'journal').iterdir())],
        selected_version_binding=selected,selected_source_bindings=selected_sources,runtime_terminal_binding=engine.pin(terminal_owner))
    return engine.save(root/'open-result.json',{'outcome':result,'completed_driver':closure,
        'next_actual_controller':terminal_binding,'artifacts':[engine.pin(p) for p in sorted(root.rglob('*'))
            if p.is_file() and not p.is_symlink() and p.name not in {'.loop.lock'}],
        'claims':{'predictive_gain':False,'autonomous_actions_require_raw_audit':True}})
