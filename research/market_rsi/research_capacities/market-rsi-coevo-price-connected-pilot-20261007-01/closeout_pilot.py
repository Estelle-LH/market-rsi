"""Exact failed original's terminal accounting; no model launch or retry."""
from collections import Counter
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess

from supervisor_harness import coevo_pilot_transaction as t
from supervisor_harness import price_account_roles as roles
from supervisor_harness import price_loop_services as s

REPO = Path('/Users/estelle/Developer/market-rsi')
BATCH = 'market-rsi-coevo-price-connected-pilot-20261007-01'
ROOT = t.ROOT.parent / BATCH


def pin(path):
    return {'path': str(path), 'sha256': t.c.sha(path)}


def close():
    if (ROOT / 'closeout.json').exists():
        raise FileExistsError('Terminal receipt already exists; do not replay writes')
    with (ROOT / '.entry.lock').open('a+') as entry_lock, (ROOT / '.pilot.lock').open('a+') as pilot_lock:
        for lock in (entry_lock, pilot_lock):
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        launch = t._file(ROOT / 'launch.json')
        grant = t.c._read(launch['authorization'])
        ledger = t._file(ROOT / 'ledger.json')
        failed = ROOT / 'price-loop/round-0001-controller.failed.json'
        if (grant['batch_id'] != BATCH or ledger['batch_id'] != BATCH
                or ledger['status'] != 'open' or ledger['attempts']
                or len(ledger['controller_decisions']) != 1
                or ledger['controller_decisions'][0]['status'] != 'reserved'
                or t._file(failed) != {'claim_sha256': t.c.sha(ROOT / 'price-loop/round-0001-controller.claim.json'),
                                    'exception_type': 'TimeoutExpired', 'retry_allowed': False}):
            raise ValueError('Exact failed no-retry Controller original required')
        key = ledger['controller_decisions'][0]['feedback_sha256']
        decision = ROOT / 'decisions' / key
        if (decision / 'completion.json').exists() or (decision / 'response.json').exists():
            raise ValueError('Unexpected Controller completion; do not label failed')
        review_dirs = list((ROOT / 'role_calls/input_review').iterdir())
        if len(review_dirs) != 1:
            raise ValueError('Expected exactly one input review original')
        review = review_dirs[0]
        roles._recover(review, t._file(review / 'claim.json'), t._file(review / 'schema.json'))
        for directory in (decision, review):
            pid = t._file(directory / 'process.json')['pid']
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pass
            else:
                raise RuntimeError('Original process still exists; preserve without accounting retry')
        originals = list((ROOT / 'role_calls').glob('*/*/claim.json'))
        if len(originals) != 1:
            raise ValueError('Unexpected extra original role claim')
        old_pins = {
            t.ROOT.parent / 'market-rsi-coevo-price-connected-pilot-20261006-01/ledger.json':
                '4fd6b6ca762bc9cdf4728c4c7183d06284d1c2f4748ef7e760f7d7aab29478af',
            t.ROOT.parent / 'market-rsi-price-auto-loop-20261006-01/ledger.json':
                '67b0bcb4c3197aacfc518ecce09958febe1dca90181bb025d28ba6f1c54cc543'}
        if any(t.c.sha(path) != token for path, token in old_pins.items()):
            raise ValueError('Closed historical ledger drift')
        wire = [json.loads(line) for line in (decision / 'native-events.jsonl').read_text().splitlines()]
        messages = [row['message'] for row in wire if row['direction'] == 'response']
        methods = Counter(m['method'] for m in messages if 'method' in m)
        if methods['turn/completed'] or any('id' in m and 'method' in m for m in messages):
            raise ValueError('Unexpected completion/tool RPC requires separate reconciliation')
        evidence_paths = [failed, ROOT / 'price-loop/round-0001-controller.claim.json',
            ROOT / 'price-loop/round-0001-controller.timing.json',
            ROOT / 'price-loop/round-0001-input.done.json', ROOT / 'account-runtime-preflight.json']
        evidence_paths += [directory / name for directory, names in (
            (decision, ('claim.json', 'failure.json', 'process.json', 'native-events.jsonl', 'events.jsonl',
                        'input.json', 'schema.json', 'runtime-policy.json')),
            (review, ('claim.json', 'completion.json', 'response.json', 'timing.json', 'native-events.jsonl')))
            for name in names]
        now = datetime.now(timezone.utc)
        value = {'schema': 'market_rsi_connected_pilot_closeout_v1', 'batch_id': BATCH,
            'complete': False, 'status': 'NOT_COMPLETE', 'closed_at_utc': now.isoformat(),
            'authorization': launch['authorization'], 'configuration': launch['configuration'],
            'launch': pin(ROOT / 'launch.json'), 'initial_feedback': pin(ROOT / 'initial-feedback.json'),
            'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
            'first_blocking_stage': 'round1.controller:120s TimeoutExpired, no terminal response/usage',
            'account_originals_started': 2, 'account_originals_completed': 1,
            'controller_decisions': {'started': 1, 'completed': 0, 'uncertain_originals': 1},
            'input_review_calls': 1, 'author_calls': 0, 'source_review_calls': 0, 'result_review_calls': 0,
            'candidate_attempts': 0, 'fits_reserved': 0, 'fits_entered': 0, 'fits_completed': 0,
            'predictions_generated': 0, 'new_scorecard': None,
            'input_review_wall_seconds': t._file(review / 'timing.json')['wall_seconds'],
            'controller_wall_seconds': t._file(decision / 'failure.json')['wall_seconds'],
            'window_wall_seconds': (now - t.c._time(grant['start_utc'])).total_seconds(),
            'known_input_review_usage': t._file(review / 'timing.json')['usage'],
            'controller_token_usage': 'unknown:missing final usage', 'subscription_usd': 'unknown',
            'paid_provider_calls': 0, 'model_requested': t.c.MODEL, 'serving_snapshot': 'unknown',
            'native_controller_methods': dict(methods), 'tool_rpc_requests': 0,
            'controller_agent_message_items': sum(m.get('params', {}).get('item', {}).get('type') == 'agentMessage'
                for m in messages), 'controller_turn_start_count': sum(row['message'].get('method') == 'turn/start' for row in wire),
            'original_processes_gone': True, 'automatic_retry': False, 'quota_refund': False,
            'old_caps_preserved': {str(path): token for path, token in old_pins.items()},
            'incumbent': ledger['incumbent'], 'pool_unchanged': True,
            'human_per_round_scientific_interventions': 0,
            'autonomous_capacity_proposals_completed': 0, 'autonomous_capacity_gain': False,
            'downstream_effect_demonstrated': False,
            'helper_source_review': pin(REPO / 'research/market_rsi/supervisor_harness/AGENT_LOG_REVIEW_TIMEOUT_REVIEW_2026-10-07.md'),
            'baseline_hook_receipts': [pin(ROOT / f'capacity-hooks-r0001/{axis}/receipt.json') for axis in ('H', 'R')],
            'evidence': [pin(path) for path in evidence_paths]}
        s.loop._read_pair(ROOT / 'price-loop/round-0001-input.done.json')
        t.c.save(ROOT / 'ledger-before-terminal.json', ledger)
        value['original_ledger'] = pin(ROOT / 'ledger-before-terminal.json')
        t.c.save(ROOT / 'closeout.json', value)
        ledger.update(status='closed_failed_no_retry', closed_at_utc=now.isoformat(), closeout=pin(ROOT / 'closeout.json'))
        t._ledger(ROOT / 'ledger.json', ledger)
        return {'closeout': pin(ROOT / 'closeout.json'), 'ledger': pin(ROOT / 'ledger.json'),
                'complete': False, 'account_originals_started': 2, 'fits': 0,
                'window_wall_seconds': value['window_wall_seconds']}


if __name__ == '__main__':
    print(json.dumps(close(), sort_keys=True))
