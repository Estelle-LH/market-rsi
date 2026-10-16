"""Serial parent-owned shadow work; originals measured before any adoption."""
from pathlib import Path
import inspect

from earnings_capacity_adapter import EarningsCapacity
from earnings_capacity_worker import CapacityWorker
from earnings_shadow_measurement import compare, validate_criterion
import earnings_capacity_worker as worker_source
import earnings_shadow_measurement as measurement_source
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


def run_matched(task, envelope, capacity, parent_state, *, pending_proposal_sha256,
                forecast, parent_slot, child_slot, comparison_root, criterion_binding):
    """Return a retained comparison binding; uncertainty stays native-claimed.

    Native capacity-work ownership is always the active parent. The checked
    worker/originals separately identify the tested pending child. This function
    never opens a ledger, changes a version or grants actual model authority.
    """
    actual_live = envelope.get('mode') == 'real_provider'
    if actual_live and (not callable(getattr(task,'admit_live',None)) or task.admit_live(envelope) is not True):
        raise ValueError('Explicit source-bound live task required for matched trial')
    if (not isinstance(capacity, EarningsCapacity) or not callable(forecast)
            or envelope.get('mode') not in {'offline_replay','real_provider'}
            or task.state_api.task_id != envelope['id'] or task.company['cik'] != envelope['cik']
            or task.kernel != envelope['evaluation_kernel']):
        raise ValueError('Explicit native offline task and borrowed forecast required')
    snapshot = capacity.batch.snapshot()
    micro, root = snapshot['micro_evolution'], Path(envelope['root'])
    pending = micro['pending']
    if pending is None or pending['record_sha256'] != engine.identity.sha(pending_proposal_sha256):
        raise ValueError('Exact still-pending shadow proposal required')
    active, tested = digest(micro['active_pair']), digest(pending['pair'])
    before = capacity._selected(snapshot)['manifest']
    after = capacity._version(pending['pair'])['manifest']
    axis = engine.identity.change_axis(before, after)
    if axis not in {'R', 'H'} or pending['parent_pair_sha256'] != active or active == tested:
        raise ValueError('One pending capacity child of the current active parent required')
    criterion = engine.read(criterion_binding)
    if type(criterion) is not dict or criterion.get('component') != pending['component']:
        raise ValueError('Criterion does not match the declared pending component')
    # Same semantics as measurement/review, before either physical trial arm.
    validate_criterion(criterion)
    slots = [Path(parent_slot), Path(child_slot)]
    location = Path(comparison_root)
    context = getattr(getattr(forecast, '__self__', None), 'context', {})
    if (type(context) is not dict or context.get('root') != str(root)
            or any(str(slot) not in context.get('slots', []) for slot in slots)):
        raise ValueError('Both shadow slots must be declared by the borrowed forecast service')
    if (not root.is_absolute() or root.resolve() != root or len(set(slots)) != 2
            or any(not slot.is_absolute() or slot.resolve() != slot or slot.parent != root / 'roles'
                   or slot.exists() for slot in slots)
            or not location.is_absolute() or location.resolve() != location
            or not location.is_relative_to(root / 'shadow') or location.exists()):
        raise ValueError('New distinct canonical shadow/role slots required')
    if snapshot['active_attempt_ids'] or snapshot['max_attempts'] - len(snapshot.get('capacity_work', [])) < 2:
        raise ValueError('Native must be idle with two prospective work items remaining')
    task.load_state(parent_state)
    worker_type = getattr(task, 'worker_type', CapacityWorker)
    if not isinstance(worker_type, type) or not issubclass(worker_type, CapacityWorker):
        raise ValueError('Explicit supported task worker type required')
    claim = {'schema': 'earnings_shadow_trial_claim_v1', 'episode': envelope,
        'study': envelope['study'], 'kernel': task.kernel, 'initial_state': parent_state,
        'active_pair_sha256': active, 'tested_pair_sha256': tested,
        'pending_proposal_sha256': pending_proposal_sha256,
        'before_identity_sha256': digest(before), 'after_identity_sha256': digest(after),
        'criterion': criterion_binding, 'slots': [str(slot) for slot in slots],
        'forecast_source': engine.source_of(forecast),
        'sources': {name: engine.pin(path) for name, path in {
            'coordinator': __file__, 'worker': inspect.getsourcefile(worker_type),
            'task': inspect.getsourcefile(type(task)), 'measurement': measurement_source.__file__}.items()}}
    engine.driver._artifacts(claim)
    location.mkdir(parents=True, exist_ok=False)
    claimed = engine.save(location/'claim.json', claim)
    outputs, work_ids = {}, []
    try:
        for arm, slot in zip(('parent', 'child'), slots):
            if (engine.read(claimed) != claim or engine.read(criterion_binding) != criterion
                    or capacity.batch.snapshot()['micro_evolution']['pending'] != pending
                    or digest(capacity.batch.snapshot()['micro_evolution']['active_pair']) != active):
                raise ValueError('Shadow commitments drifted before arm')
            engine.driver._artifacts(claim)
            work_id = 'shadow-' + digest({'claim': claimed, 'arm': arm})
            work_ids.append(work_id)
            snap = capacity.batch.snapshot()
            capacity.batch.record_capacity_work('claim', work_id=work_id, pair_sha256=active,
                evidence_sha256=digest({'claim': claimed, 'tested_pair_sha256': active if arm == 'parent' else tested}),
                expected_state_sha256=snap['state_sha256'])
            factory = getattr(task, 'make_worker', None)
            options = {'shadow_proposal_sha256':None if arm == 'parent' else pending_proposal_sha256}
            worker = (factory(envelope['id'], capacity, active, location/(arm+'-memory'), parent_state, **options)
                if callable(factory) else CapacityWorker(task.company, envelope['id'], capacity, active,
                    location/(arm+'-memory'), parent_state, **options))
            if type(worker) is not worker_type:
                raise ValueError('Actual trial worker differs from declared implementation')
            engine.save(location/(arm+'-worker.json'), {'source':engine.pin(inspect.getsourcefile(type(worker))),
                'factory':None if not callable(factory) else engine.source_of(factory),
                'active_pair_sha256':active,'tested_pair_sha256':worker.tested_pair})
            raw = forecast(worker, str(slot))
            verified = task.shadow_execution(raw, worker, slot, active_pair_sha256=active,
                tested_pair_sha256=active if arm == 'parent' else tested,
                pending_proposal_sha256=pending_proposal_sha256, initial_state=parent_state)
            outputs[arm] = verified
            bound = engine.save(location/(arm+'.json'), verified)
            snap = capacity.batch.snapshot()
            capacity.batch.record_capacity_work('complete', work_id=work_id, pair_sha256=active,
                evidence_sha256=bound['sha256'], expected_state_sha256=snap['state_sha256'])
        if (capacity.batch.snapshot()['micro_evolution'] != micro
                or engine.read(criterion_binding) != criterion or engine.read(claimed) != claim):
            raise ValueError('Trial changed native selection/proposal/history or criterion')
        engine.driver._artifacts(claim)
        measured = compare(outputs['parent'], outputs['child'], declaration=criterion)
        comparison = engine.save(location/'comparison.json', dict(measured, trial_claim=claimed, work_ids=work_ids))
        engine.save(location/'terminal.json', {'status': 'MEASURED', 'comparison': comparison, 'retry_allowed': False})
        return comparison
    except BaseException as error:
        failure = location/'failed.json'
        if not failure.exists():
            engine.save(failure, {'status': 'FAILED_NO_RETRY', 'error_type': type(error).__name__,
                'retry_allowed': False, 'trial_claim': claimed, 'completed_outputs': outputs, 'work_ids': work_ids})
        raise
