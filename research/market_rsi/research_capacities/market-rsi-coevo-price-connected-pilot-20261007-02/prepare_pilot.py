"""Fresh approved ops binding; unchanged scientific pipeline and seed evidence."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import argparse
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
BATCH = 'market-rsi-coevo-price-connected-pilot-20261007-02'
ROOT = t.ROOT.parent / BATCH
OLD = t.ROOT.parent / 'market-rsi-price-auto-loop-20261006-01'
PREFIX = 'research/market_rsi/research_capacities/' + BATCH + '/'
BASELINE_PREFIX = 'research/market_rsi/research_capacities/market-rsi-coevo-price-connected-pilot-20261007-01/'


def check():
    if ROOT.exists():
        raise FileExistsError('Fresh pilot root already exists; do not overwrite/reopen')
    launch = json.loads((OLD / 'launch.json').read_text())
    seed = entry.s.loop._read_pair(OLD / 'price-loop-admission-v3/round-0002-reconcile.done.json')['output']
    data = {key: t.c._read(binding) for key, binding in seed.items()}
    if t._file(OLD / 'ledger.json')['status'] != 'closed_at_attempt_cap':
        raise ValueError('Old batch must stay closed')
    sources = {name: r.w.sha(REPO / name) for name in launch['source_files']}
    extra = ['price_capacity_services', 'price_capacity_loop', 'price_capacity_trial',
             'price_capacity_replay', 'price_capacity_source',
             'research_capacity_identity', 'research_capacity_activation']
    sources.update({f'research/market_rsi/supervisor_harness/{name}.py':
        r.w.sha(REPO / f'research/market_rsi/supervisor_harness/{name}.py') for name in extra})
    for axis in ('h', 'r'):
        name = BASELINE_PREFIX + f'baseline_{axis}.py'
        guard.validate_source((REPO / name).read_text())
        sources[name] = r.w.sha(REPO / name)
    for name, token in sources.items():
        import hashlib
        if hashlib.sha256(subprocess.check_output(['git', 'show', 'HEAD:' + name], cwd=REPO)).hexdigest() != token:
            raise ValueError('Versioned source drift: ' + name)
    for binding in (launch['base_spec']['plan_binding'], launch['base_spec']['ordinary_reference_binding']):
        t.c._read(binding)
    return launch, seed, data, sources


def prepare():
    launch, seed, data, sources = check()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    times = {key: (now + timedelta(minutes=minutes)).strftime('%Y-%m-%dT%H:%M:%SZ')
        for key, minutes in [('start_utc', 0), ('selection_cutoff_utc', 40), ('deadline_utc', 45)]}
    limits = {**t.LIMITS, 'live_candidate_processes': 1}
    grant = deepcopy(t.c._read(launch['authorization']))
    grant.update(batch_id=BATCH, limits=limits, **times)
    grant['account_transfer'].update(max_input_bytes=262144, max_call_seconds=300)
    grant['account_roles'].update(capacity_changes_approved=True, max_input_bytes=262144,
        max_call_seconds=300, call_seconds={'author': 300, 'input_review': 300,
                                           'source_review': 300, 'result_review': 300})
    roles.controller_call_seconds(grant)
    roles.call_limits(grant['account_roles'])
    grant['approval_evidence'] = {
        'human_reply': 'try again co-evo closing loop',
        'reply_context': 'Direct human reply to pending fresh20261007-02 scope after repaired chain status',
        'batch_id': BATCH, 'scope': '2 original Controller,2 author,6 independent review;2 attempts/8fits;'
        'signed-in Codex gpt-6.1-sol compact private aggregates/memory/history/source <=256KiB perinput;'
        'prospective reviewed research-side R/H modification and downstream use; no rawtransfer/retries/paid/'
        'acquisition/DevFinal/release/push/promotion; all account roles<=300s,clipped to batchdeadline;'
        'existing journal synchronization;45min after preparation',
        'structured_question_reply_received': False, 'old_authority_reused': False}
    ROOT.mkdir()
    def save(name, value):
        path = ROOT / (name + '.json')
        r.w.save(path, value)
        return r.pin(path)
    authority = save('authorization', grant)
    configuration = save('configuration', {'schema': 'supervisor_reviewed_pilot_configuration_v1',
        'batch_id': BATCH, 'root': str(ROOT), 'limits': limits, **times})
    base = deepcopy(launch['base_spec'])
    def component(names, configuration):
        return {'sources': {name: sources[name] for name in names},
                'configuration_sha256': t.c._digest(configuration)}
    before = identity.manifest(
        kernel=component(['research/market_rsi/experiments/nfl_ingame_price_data.py',
                          'research/market_rsi/experiments/nfl_ingame_price_score.py'], base['plan_binding']),
        predictor=component(['research/market_rsi/experiments/nfl_ingame_price_change_train_diagnostic.py'],
                            {'task': entry.s.h.TASK, 'incumbent': data['pool']['incumbent']['candidate_id']}),
        harness=component([BASELINE_PREFIX + 'baseline_h.py'], {'behavior': 'direct supplied process evidence'}),
        researcher=component([BASELINE_PREFIX + 'baseline_r.py'], {'behavior': 'direct supplied latest evidence'}),
        memory=seed['memory']['sha256'], runtime={'python': base['python_binding']['binary'], 'dependencies': {}},
        model={'requested_model': t.c.MODEL, 'serving_snapshot': 'unknown', 'serving_snapshot_verified': False})
    cfg = base['identity_configuration']
    cfg['pair'] = activation.pair(before)
    cfg['fixed_context'].update(authority_sha256=authority['sha256'], model_sha256=before['M'],
                                resource_policy_sha256=configuration['sha256'])
    cfg['allowed_write_paths'] = {axis: [PREFIX + axis + '/capacity.py', PREFIX + axis + '/test_capacity.py']
                                  for axis in ('researcher', 'harness')}
    cfg['reviewer_id'] = 'connected-price-native-independent-review'
    compact = {'history': {'last_experiment': data['history']['last_experiment'],
                          'earlier_experiment': data['history']['prior']['last_experiment']},
               'memory': {'stopped_exact_recipes': data['memory']['stopped_exact_recipes']},
               'feedback': {'decision': data['feedback']['decision'],
                            'comparison': data['feedback'].get('comparison')},
               'pool': {'incumbent': data['pool']['incumbent']['candidate_id']}}
    cases = {name: {**deepcopy(compact), 'replay_case': name,
                   'interpretation': 'Supplied historical diagnostic context, not future or OOS evidence'}
             for name in ('success', 'failure', 'restart', 'historical_replay')}
    cases['failure']['history']['known_operational_failure'] = {
        'source': r.pin(OLD / 'price-loop/round-0001-implement.failed.json'),
        'observation': 'Known author numeric admission failure before source/training; subsequently repaired',
        'scientific_refutation': False}
    capacity = save('capacity-configuration', {'schema': 'price_capacity_loop_configuration_v1',
        'baseline': before, 'entrypoints': {'H': BASELINE_PREFIX + 'baseline_h.py', 'R': BASELINE_PREFIX + 'baseline_r.py'},
        'replay_cases': cases, 'hook_seconds': 5})
    source = deepcopy(data['source_context'])
    source.update(source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        authority='Fresh direct human whole-batch approval, exact current authorization binding',
        loop_contract='This is a prospective capacity-to-prediction pilot, not two preselected models. '
        'First choose one small R or research-side H improvement from the existing verified negative evidence, '
        'predeclare a falsifiable matched test/benefit and later use. Independently reviewed pure apply(context) '
        'may analyze supplied JSON feedback/memory/history/pool; no access to files or extra data/tools. '
        'Second decision must consume the actual first trial/review feedback and selected hook output, '
        'then choose and execute a prediction candidate on the unchanged 300s task. Do not claim a gain '
        'from source change/adoption alone. A rejection/negative result is valid evidence. No forced algorithm. '
        'All method choices are Controller-owned; Supervisor baseline projections are bootstrap only, '
        'not a competent matched research-process benchmark. Do not repeat identical failed recipes.',
        baseline_capacity_sources={axis: {'path': BASELINE_PREFIX + f'baseline_{axis}.py',
            'source': (REPO / (BASELINE_PREFIX + f'baseline_{axis}.py')).read_text()} for axis in ('h', 'r')})
    seed = {**seed, 'source_context': save('source-context', source)}
    initial = save('initial-feedback', seed)
    save('ledger', {'schema': 'market_rsi_coevo_pilot_ledger_v1', 'batch_id': BATCH,
        'authorization_sha256': authority['sha256'], 'status': 'open', 'controller_decisions': [], 'attempts': [],
        'incumbent': t._file(OLD / 'ledger.json')['incumbent'], 'research_pool_sha256': seed['pool']['sha256']})
    services = {name: r.pin(REPO / 'research/market_rsi/supervisor_harness' / module) for name, module in {
        'entry': 'run_price_discovery.py', 'roles': 'price_account_roles.py', 'author': 'price_candidate_author.py',
        'reviewer': 'price_independent_review.py', 'capacity_author': 'price_capacity_services.py',
        'capacity_loop': 'price_capacity_loop.py'}.items()}
    config = save('launch', {'schema': 'price_discovery_launch_v2', 'repo': str(REPO), 'root': str(ROOT),
        'authorization': authority, 'configuration': configuration, 'role_authorization': authority,
        'base_spec': base, 'source_files': sources, 'service_sources': services,
        'capacity_configuration': capacity, 'max_rounds': 2})
    _, service, _ = entry.build(config)
    packet = service.prepare_packet({'round_index': 1, 'seed': seed, 'previous_result': seed,
        'previous_feedback_sha256': t.c._digest(seed), 'outputs': {}})
    size = len(roles._prompt(packet, controller=True).encode())
    if size > 262144:
        raise ValueError('Frozen fully rendered input exceeds authorized bytes')
    return {'launch': config, 'initial_feedback': initial, 'input_bytes': size, **times,
            'account_calls': 0, 'fits': 0, 'source_count': len(sources)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        print(json.dumps(prepare(), sort_keys=True))
    else:
        _, _, _, sources = check()
        print(json.dumps({'checks_passed': True, 'source_count': len(sources), 'account_calls': 0, 'fits': 0}))
