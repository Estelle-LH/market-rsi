"""Retained local connection fixture / cold process restore. Never calls an API.

Uses the same native journal and engine as the task tests. Roles and model/runtime
identities are invented fixtures, so this is wiring proof, not learning evidence.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO/'tools'), str(REPO/'tests'), str(REPO/'research/market_rsi')]

import test_capacity_feedback_engine as fixture
from test_earnings_capacity_adapter import EarningsCapacityTests, BASE
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch

engine = fixture.engine


def verify(owner, outcome):
    root = Path(owner.envelope['root'])
    previous = engine.driver._read_pair(root/'loop/round-0001-reconcile.done.json')['output']
    current = engine.driver._read_pair(root/'loop/round-0002-execute.done.json')['output']
    packet = engine.read(engine.pin(root/'packet-02.json'))
    first = engine.read(engine.pin(Path(owner.envelope['slots'][0]['forecast'])/'consumption.json'))
    second = engine.read(engine.pin(Path(owner.envelope['slots'][1]['forecast'])/'consumption.json'))
    checks = {'feedback_body': packet['feedback'] == previous['feedback'],
        'feedback_digest': packet['feedback_sha256'] == fixture.digest(previous),
        'parent_state': second['parent_state'] == previous['state'] == current['parent_state'],
        'R_used': first['messages'][1]['content'] == 'Verify signs with calculate',
        'H_used': second['tool_bounds']['read_chunk_limit'] == 1000,
        'both_rounds': outcome['status'] == 'completed' and outcome['completed_rounds'] == 2,
        'native_history': len(owner.native.batch.snapshot()['micro_evolution']['history']) == 2}
    if not all(checks.values()): raise ValueError('Observed handoff verification failed')
    return checks


def create(root, kind):
    root.mkdir(parents=True, exist_ok=False)
    counter = [0]
    class RetainedTemporary:
        def __init__(self, *args, **kwargs):
            counter[0] += 1
            self.name = str(root / f'fixture-{counter[0]:02d}')
            Path(self.name).mkdir()
        def cleanup(self): pass  # Every invented source/receipt is deliberately retained.
    owner = fixture.CommonEngineTests('test_sum_task_has_actual_scores_versions_state_and_completed_restore')
    with patch('tempfile.TemporaryDirectory', RetainedTemporary): owner.setUp()
    owner.setup_task(kind)
    outcome = owner.invoke_engine()
    checks = verify(owner, outcome)
    context = {'task': kind, 'owner_root': str(owner.root), 'envelope': owner.bound,
        'native': {'root': str(owner.native.root), 'batch': str(owner.native.root/'batch'),
            'before': owner.native.before, 'args': owner.native.args, 'entry': owner.native.entry,
            'config': owner.native.config, 'files': owner.native.files}, 'outcome': outcome}
    bound = engine.save(root/'restore-context.json', context)
    engine.save(root/'restore-context.binding.json', bound)
    report = {'mode': 'RETAINED_OFFLINE_FIXTURE', 'task': kind, 'checks': checks,
        'completed_rounds': 2, 'service_calls': {'controller': len(owner.packets),
            'author': len(owner.authored), 'review': len(owner.reviewed), 'execute': len(owner.task.calls)},
        'model_calls': 0, 'learning_claim': False, 'context': bound}
    engine.save(root/'connection-report.json', report)
    return report


def restore(root):
    bound = engine.read(engine.pin(root/'restore-context.binding.json'))
    saved = engine.read(bound)
    owner = fixture.CommonEngineTests('test_sum_task_has_actual_scores_versions_state_and_completed_restore')
    owner.root, owner.bound = Path(saved['owner_root']), saved['envelope']
    owner.envelope = engine.read(owner.bound)
    owner.axes, owner.packets, owner.authored, owner.reviewed = ['R','H'], [], [], []
    native = EarningsCapacityTests('test_earnings_reject_keeps_parent_and_history')
    for key in ('before', 'args', 'entry', 'config', 'files'): setattr(native, key, saved['native'][key])
    native.root, native.count = Path(saved['native']['root']), 0
    native.batch = ContinuousDiscoveryBatch(saved['native']['batch'], allow_temporary=True,
        test_clock=lambda: BASE, allow_test_clock=True)
    owner.native = native
    owner.task = fixture.LocalTask(owner, saved['task'], restore=True)
    before = native.batch.snapshot()['state_sha256']
    outcome = owner.invoke_engine()
    checks = verify(owner, outcome)
    calls = {'controller': len(owner.packets), 'author': len(owner.authored),
             'review': len(owner.reviewed), 'execute': len(owner.task.calls)}
    if any(calls.values()) or outcome != saved['outcome'] or native.batch.snapshot()['state_sha256'] != before:
        raise ValueError('Completed restore executed a role or changed retained outcome/history')
    return {'mode': 'COLD_PROCESS_RESTORE', 'task': saved['task'], 'checks': checks,
            'service_calls': calls, 'model_calls': 0, 'learning_claim': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--task', choices=('sum','count'), default='sum')
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    root = args.root.absolute()
    if root.resolve() != root or not root.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise ValueError('Fresh owned canonical OS-temporary fixture directory required')
    result = restore(root) if args.restore else create(root, args.task)
    print(json.dumps(result, sort_keys=True))

if __name__ == '__main__': main()
