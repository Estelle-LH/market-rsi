"""Bounded five-hour ops; reuse the reviewed two-round price entry unchanged."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

from supervisor_harness import run_price_discovery as entry
from supervisor_harness import price_account_roles as roles
from supervisor_harness import research_capacity_identity as identity
from supervisor_harness import research_capacity_activation as activation
from supervisor_harness import price_capacity_source as guard

r, t = entry.r, entry.r.t
REPO = Path('/Users/estelle/Developer/market-rsi')
WINDOW = 'market-rsi-coevo-price-5h-20261007-01'
START = '2026-10-07T23:11:45Z'
DEADLINE = '2026-10-08T04:11:45Z'
GLOBAL_CUTOFF = '2026-10-08T03:56:45Z'
SEGMENTS = [WINDOW + '-s' + str(i).zfill(2) for i in range(1, 6)]
APPROVAL_ROOT = t.ROOT.parent / WINDOW
OLD_OPS = REPO / 'research/market_rsi/research_capacities/market-rsi-coevo-price-connected-pilot-20261007-02/prepare_pilot.py'
TOTAL_CAPS = {'controller': 10, 'author': 10, 'independent_review': 30, 'attempts': 10, 'fits': 40}


def committed(name):
    token = r.w.sha(REPO / name)
    import hashlib
    if hashlib.sha256(subprocess.check_output(['git', 'show', 'HEAD:' + name], cwd=REPO)).hexdigest() != token:
        raise ValueError('Current source not committed: ' + name)
    return token


def load(segment):
    if type(segment) is not int or not 1 <= segment <= 5:
        raise ValueError('Exactly five finite segment slots; no extra retry slot')
    batch = SEGMENTS[segment - 1]; root = t.ROOT.parent / batch
    if root.exists(): raise FileExistsError('Segment already exists; do not reopen')
    committed(str(OLD_OPS.relative_to(REPO)))
    spec = importlib.util.spec_from_file_location('previous_source_checker_only', OLD_OPS)
    checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
    # check() is read-only. Point its fresh-root existence check at this new
    # namespace; do NOT call the old prepare() or change its source/artifacts.
    checker.ROOT = root
    launch, seed, data, sources = checker.check()
    selected = None
    if segment > 1:
        prior = t.ROOT.parent / SEGMENTS[segment - 2]
        ledger = t._file(prior / 'ledger.json')
        if ledger['status'] == 'closed_at_attempt_cap':
            previous_launch = prior / 'launch-admission-v3.json'
            if not previous_launch.exists(): previous_launch = prior / 'launch.json'
            previous_config, previous_service, _ = entry.build(r.pin(previous_launch))
            directory = previous_service.recovery_directory
            manifest = entry.s.loop._read_pair(prior / directory / 'manifest.json')
            if manifest['max_rounds'] != 2: raise ValueError('Original two-round scope drift')
            seed = entry.s.loop._read_pair(prior / directory / 'round-0002-reconcile.done.json')['output']
            entry.s.loop._artifacts(seed)
            if previous_service.identity() != manifest['handler_identity']:
                raise ValueError('Prior completed source/handler drift')
            selected = previous_service.capacity.validate()
            data = {key: t.c._read(binding) for key, binding in seed.items()}
        elif segment == 2 and ledger['status'] == 'closed_failed_no_retry':
            # Exact known s01 pre-source rejection, not replay/resampling of its
            # calls. A new original Controller must consume the failure evidence.
            closeout = t.c._read(ledger['closeout'])
            if (closeout.get('schema') != 'market_rsi_exact_pre_source_failure_closeout_v1'
                    or closeout['batch_id'] != SEGMENTS[0] or closeout['retry_allowed'] is not False
                    or closeout['quota_refund'] is not False or closeout['original_processes_gone'] is not True
                    or closeout['candidate_attempts'] != 0 or closeout['fits_reserved'] != 0
                    or closeout['account_originals_started'] != 3 or closeout['account_originals_completed'] != 3
                    or closeout['performance_evidence'] is not False or closeout['capacity_gain'] is not False
                    or ledger['attempts'] or len(ledger['controller_decisions']) != 1
                    or ledger['controller_decisions'][0]['status'] != 'completed'
                    or closeout['original_controller_decision_sha256'] != ledger['controller_decisions'][0]['decision_sha256']):
                raise ValueError('Not the exact certain charged s01 pre-source failure')
            for binding in closeout['evidence'] + [closeout['failure'], closeout['original_ledger']]:
                t.c._read(binding)
            seed = t.c._read(closeout['initial_feedback'])
            entry.s.loop._artifacts(seed)
            data = {key: t.c._read(binding) for key, binding in seed.items()}
            selected = closeout['selected_capacity']
            identity.validate(selected['manifest'])
            finding = {'closeout': ledger['closeout'], 'execution_outcome': 'pre_source_admission_failed',
                'proposal': closeout['proposal'],
                'reason': closeout['reason'], 'original_controller_decision_sha256': closeout['original_controller_decision_sha256'],
                'performance_evidence': False, 'capacity_gain': False, 'originals_consumed': 3,
                'attempts_entered': 0, 'fits_entered': 0, 'same_ID_retry': False,
                'next': 'Fresh original decision in next finite slot. Do not replay unchanged rejected source/test. '
                    'Use failure to simplify or change the next proposed capacity; no scientific conclusion from failure.'}
            for key in ('feedback', 'memory', 'history'):
                data[key] = {**data[key], 'last_operational_failure': finding}
            data['_known_failure_continuation'] = True
        else:
            raise ValueError('Prior segment must be certainly complete or exact reviewed s01 failure; no uncertain continuation')
        for component in selected['manifest']['components'].values():
            for name, token in component['sources'].items():
                if committed(name) != token: raise ValueError('Inherited selected source drift')
                sources[name] = token
    for name in (str(OLD_OPS.relative_to(REPO)), str(Path(__file__).resolve().relative_to(REPO))):
        sources[name] = committed(name)
    return batch, root, launch, seed, data, sources, selected


def prepare(segment, approval):
    batch, root, launch, seed, data, sources, selected = load(segment)
    if approval != APPROVAL_ROOT / 'explicit-account-consent.json':
        raise ValueError('Exact whole-window explicit consent record required')
    consent = t._file(approval)
    if (consent.get('window_id') != WINDOW or consent.get('explicit_payload_destination_approved') is not True
            or consent.get('hard_deadline_utc') != DEADLINE or consent.get('total_caps') != TOTAL_CAPS):
        raise ValueError('Explicit private payload/destination/window approval missing or drifted')
    now = datetime.now(timezone.utc).replace(microsecond=0)
    deadline = min(now + timedelta(minutes=45), t.c._time(DEADLINE))
    cutoff = min(deadline - timedelta(minutes=5), t.c._time(GLOBAL_CUTOFF))
    if now >= cutoff: raise ValueError('Whole-window cutoff exhausted; never extend')
    times = {key: value.strftime('%Y-%m-%dT%H:%M:%SZ') for key, value in
        [('start_utc', now), ('selection_cutoff_utc', cutoff), ('deadline_utc', deadline)]}
    grant = deepcopy(t.c._read(launch['authorization']))
    limits = {**t.LIMITS, 'live_candidate_processes': 1}
    grant.update(batch_id=batch, limits=limits, **times)
    grant['account_transfer'].update(max_input_bytes=262144, max_call_seconds=300)
    grant['account_roles'].update(capacity_changes_approved=True, max_input_bytes=262144, max_call_seconds=300,
        call_seconds={role: 300 for role in roles.ROLES})
    grant['approval_evidence'] = {'whole_window': r.pin(approval), 'window_id': WINDOW,
        'human_reply': consent['human_reply'], 'explicit_payload_destination_approved': True,
        'hard_deadline_utc': DEADLINE, 'total_caps': TOTAL_CAPS, 'fixed_segment_ids': SEGMENTS,
        'segment_index': segment, 'old_authority_reused': False}
    root.mkdir()
    def save(name, value):
        path = root / (name + '.json'); r.w.save(path, value); return r.pin(path)
    if data.pop('_known_failure_continuation', False):
        seed = {**seed, **{key: save('inherited-' + key, data[key]) for key in ('feedback', 'memory', 'history')}}
    authority = save('authorization', grant)
    configuration = save('configuration', {'schema': 'supervisor_reviewed_pilot_configuration_v1',
        'batch_id': batch, 'root': str(root), 'limits': limits, **times})
    base = deepcopy(launch['base_spec']); cfg = base['identity_configuration']
    baseline = t.c._read(launch['capacity_configuration']) if 'capacity_configuration' in launch else None
    if baseline is None:
        old_capacity = t.ROOT.parent / 'market-rsi-coevo-price-connected-pilot-20261007-02/capacity-configuration.json'
        baseline = t._file(old_capacity)
    before = deepcopy(selected['manifest'] if selected else baseline['baseline'])
    entries = deepcopy(selected['entrypoints'] if selected else baseline['entrypoints'])
    before = identity.manifest(kernel=before['components']['K'], predictor=before['components']['C'],
        harness=before['components']['H'], researcher=before['components']['R'], memory=seed['memory']['sha256'],
        runtime=before['runtime'], model=before['model'])
    cfg['pair'] = activation.pair(before)
    cfg['fixed_context'].update(authority_sha256=authority['sha256'], model_sha256=before['M'],
        resource_policy_sha256=configuration['sha256'])
    prefix = 'research/market_rsi/research_capacities/' + batch + '/'
    cfg['allowed_write_paths'] = {axis: [prefix + axis + '/capacity.py', prefix + axis + '/test_capacity.py']
        for axis in ('researcher', 'harness')}
    cfg['reviewer_id'] = 'connected-price-native-independent-review'
    cases = deepcopy(baseline['replay_cases'])
    if segment > 1:
        # Actual prior feedback, with old frozen replay cases retained separately.
        cases['success'] = {key: deepcopy(data[key]) for key in ('feedback', 'memory', 'history', 'pool')}
        cases['restart'] = deepcopy(cases['success'])
    capacity = save('capacity-configuration', {'schema': 'price_capacity_loop_configuration_v1',
        'baseline': before, 'entrypoints': entries, 'replay_cases': cases, 'hook_seconds': 5})
    source = deepcopy(data['source_context'])
    source.update(source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        authority='Explicit whole-window account payload consent, bounded fresh segment, no old ID reopened',
        loop_contract='First choose a small R or research-side H improvement from verified evidence; '
        'state a falsifiable named benefit and matched test. Second use actual trial/review feedback and selected '
        'hook outputs to choose a price predictor on the fixed300s task. No forced algorithm or metric gain. '
        'Preserve useful negative findings and separate code/adoption from useful downstream effects. '
        'Actual inherited versions and feedback persist; a negative result does not erase a branch. '
        'All scientific method choices are Controller-owned; Supervisor ops are not autonomous evolution.',
        baseline_capacity_sources={axis.lower(): {'path': name, 'source': (REPO / name).read_text()}
            for axis, name in entries.items()}, window_approval=r.pin(approval))
    seed = {**seed, 'source_context': save('source-context', source)}
    initial = save('initial-feedback', seed)
    save('ledger', {'schema': 'market_rsi_coevo_pilot_ledger_v1', 'batch_id': batch,
        'authorization_sha256': authority['sha256'], 'status': 'open', 'controller_decisions': [], 'attempts': [],
        'incumbent': data['pool']['incumbent'], 'research_pool_sha256': seed['pool']['sha256']})
    services = {name: r.pin(REPO / 'research/market_rsi/supervisor_harness' / module) for name, module in {
        'entry': 'run_price_discovery.py', 'roles': 'price_account_roles.py', 'author': 'price_candidate_author.py',
        'reviewer': 'price_independent_review.py', 'capacity_author': 'price_capacity_services.py',
        'capacity_loop': 'price_capacity_loop.py'}.items()}
    config = save('launch', {'schema': 'price_discovery_launch_v2', 'repo': str(REPO), 'root': str(root),
        'authorization': authority, 'configuration': configuration, 'role_authorization': authority,
        'base_spec': base, 'source_files': sources, 'service_sources': services,
        'capacity_configuration': capacity, 'max_rounds': 2})
    _, service, _ = entry.build(config)
    packet = service.prepare_packet({'round_index': 1, 'seed': seed, 'previous_result': seed,
        'previous_feedback_sha256': t.c._digest(seed), 'outputs': {}})
    size = len(roles._prompt(packet, controller=True).encode())
    if size > 262144: raise ValueError('Rendered input exceeds original consent bytes')
    return {'launch': config, 'initial_feedback': initial, 'input_bytes': size, **times,
        'account_calls': 0, 'fits': 0, 'source_count': len(sources), 'inherited_capacity': selected is not None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--segment', type=int, default=1)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--approval', type=Path)
    args = parser.parse_args()
    if args.prepare: result = prepare(args.segment, args.approval)
    else:
        batch, root, _, _, _, sources, _ = load(args.segment)
        result = {'checks_passed': True, 'batch_id': batch, 'source_count': len(sources), 'account_calls': 0, 'fits': 0}
    print(json.dumps(result, sort_keys=True))
