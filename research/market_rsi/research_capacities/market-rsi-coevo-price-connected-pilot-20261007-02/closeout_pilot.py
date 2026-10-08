"""Exact completed-but-rejected Controller accounting; never resample or admit it."""
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path

from supervisor_harness import coevo_pilot_transaction as t
from supervisor_harness import price_account_roles as roles

ROOT = t.ROOT.parent / 'market-rsi-coevo-price-connected-pilot-20261007-02'


def pin(path):
    return {'path': str(path), 'sha256': t.c.sha(path)}


def close():
    if (ROOT / 'closeout.json').exists():
        raise FileExistsError('Exact closeout already exists; no repeated writes')
    with (ROOT / '.entry.lock').open('a+') as entry_lock, (ROOT / '.pilot.lock').open('a+') as pilot_lock:
        for lock in (entry_lock, pilot_lock):
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ledger = t._file(ROOT / 'ledger.json')
        launch = t._file(ROOT / 'launch.json'); grant = t.c._read(launch['authorization'])
        if (ledger['status'] != 'open' or ledger['batch_id'] != ROOT.name
                or grant['batch_id'] != ROOT.name or ledger['attempts']
                or len(ledger['controller_decisions']) != 1
                or ledger['controller_decisions'][0]['status'] != 'reserved'):
            raise ValueError('Exact zero-attempt, one charged original required')
        decision = ROOT / 'decisions' / ledger['controller_decisions'][0]['feedback_sha256']
        failed = ROOT / 'price-loop/round-0001-controller.failed.json'
        if t._file(failed) != {'claim_sha256': t.c.sha(ROOT / 'price-loop/round-0001-controller.claim.json'),
                             'exception_type': 'ValueError', 'retry_allowed': False}:
            raise ValueError('Exact preserved no-retry failure required')
        packet, response = [t._file(decision / name) for name in ('input.json', 'response.json')]
        claim = t._file(decision / 'claim.json')
        if (claim['authorization'] != launch['authorization']
                or claim['configuration_sha256'] != launch['configuration']['sha256']
                or t.c._read(claim['input_binding']) != packet
                or claim['input_sha256'] != t.c._digest(packet)
                or ledger['controller_decisions'][0]['input_sha256'] != t.c._digest(packet)
                or claim.get('controller_transport') != roles.transport_contract()
                or claim['transaction_source_sha256'] != t.c.sha(Path(t.__file__))):
            raise ValueError('Exact original authority/input/process contract required')
        try:
            # Reuse every native hash/process/source/policy check preceding
            # semantic validation. Never translate or admit the bad response.
            t._recover(decision, packet, claim, roles.transport_contract())
        except ValueError as error:
            if str(error) != 'capacity parent/scope/component/evidence/resource drift':
                raise
        else:
            raise ValueError('Do not reject or rewrite a valid original')
        events = list(map(t.c._json, (decision / 'events.jsonl').read_text().splitlines()))
        finals = [t.c._json(e['item']['text']) for e in events if e.get('type') == 'item.completed'
                  and e.get('item', {}).get('type') == 'agent_message']
        if sum(e.get('type') == 'turn.completed' for e in events) != 1 or finals != [response]:
            raise ValueError('Exactly one actual terminal and unchanged final response required')
        review_dirs = list((ROOT / 'role_calls/input_review').iterdir())
        if len(review_dirs) != 1 or len(list((ROOT / 'role_calls').glob('*/*/claim.json'))) != 1:
            raise ValueError('Exactly one input review original required')
        review = review_dirs[0]
        roles._recover(review, t._file(review / 'claim.json'), t._file(review / 'schema.json'))
        for directory in (decision, review):
            try:
                os.kill(t._file(directory / 'process.json')['pid'], 0)
            except ProcessLookupError:
                pass
            else:
                raise RuntimeError('Exact original process still exists; do not reconcile')
        old = {
            'market-rsi-coevo-price-connected-pilot-20261007-01': 'dc63bcea7ff6225387d5461b4e81f21a686fb0082ac3fe31e3ae39329eb1ec51',
            'market-rsi-coevo-price-connected-pilot-20261006-01': '4fd6b6ca762bc9cdf4728c4c7183d06284d1c2f4748ef7e760f7d7aab29478af',
            'market-rsi-price-auto-loop-20261006-01': '67b0bcb4c3197aacfc518ecce09958febe1dca90181bb025d28ba6f1c54cc543'}
        if any(t.c.sha(ROOT.parent / name / 'ledger.json') != token for name, token in old.items()):
            raise ValueError('Closed old ledger drift')
        usage = None
        for row in map(json.loads, (decision / 'native-events.jsonl').read_text().splitlines()):
            m = row['message']
            if m.get('method') == 'thread/tokenUsage/updated':
                usage = m['params']['tokenUsage']['total']
        now = datetime.now(timezone.utc)
        evidence = [ROOT / name for name in ('launch.json', 'initial-feedback.json', 'explicit-account-consent.json',
            'account-runtime-preflight.json', 'price-loop/round-0001-input.done.json',
            'price-loop/round-0001-controller.claim.json', 'price-loop/round-0001-controller.failed.json',
            'price-loop/round-0001-controller.timing.json')]
        evidence += [decision / name for name in ('claim.json', 'input.json', 'response.json', 'completion.json',
            'failure.json', 'native-events.jsonl', 'events.jsonl', 'process.json', 'runtime-policy.json')]
        t.c.save(ROOT / 'ledger-before-terminal.json', ledger)
        value = {'schema': 'market_rsi_connected_pilot_closeout_v1', 'batch_id': ROOT.name,
            'complete': False, 'status': 'NOT_COMPLETE', 'closed_at_utc': now.isoformat(),
            'first_blocking_stage': 'round1.Controller completed response semantic admission',
            'observed_rejection': 'capacity parent/scope/component/evidence/resource drift',
            'supervisor_diagnosis': 'Required pair digest/component labels/citation eligibility not exposed; '
                'Root checked the exact rendered original input. This is not a source-only reviewer finding.',
            'authorization': launch['authorization'], 'configuration': launch['configuration'],
            'original_deadline_utc': grant['deadline_utc'], 'clock_extended': False,
            'account_originals_started': 2, 'account_originals_completed': 2,
            'controller_decisions': {'started': 1, 'native_completed': 1, 'accepted': 0, 'rejected': 1},
            'input_review_calls': 1, 'author_calls': 0, 'source_review_calls': 0, 'result_review_calls': 0,
            'candidate_attempts': 0, 'fits_reserved': 0, 'fits_entered': 0, 'fits_completed': 0,
            'predictions_generated': 0, 'new_scorecard': None,
            'proposal': {'change_id': response['capacity']['change_id'], 'axis': response['action'],
                         'status': 'unaccepted original; not implemented/tested/adopted'},
            'input_review_wall_seconds': t._file(review / 'timing.json')['wall_seconds'],
            'controller_wall_seconds': t._file(decision / 'failure.json')['wall_seconds'],
            'window_wall_seconds': (now - t.c._time(grant['start_utc'])).total_seconds(),
            'input_review_usage': t._file(review / 'timing.json')['usage'], 'controller_usage': usage,
            'subscription_usd': 'unknown', 'paid_provider_calls': 0, 'model_requested': t.c.MODEL,
            'serving_snapshot': 'unknown', 'original_processes_gone': True, 'automatic_retry': False,
            'quota_refund': False, 'raw_response_changed': False, 'old_caps_preserved': old,
            'incumbent': ledger['incumbent'], 'research_pool_unchanged': True,
            'autonomous_capacity_gain': False, 'downstream_effect_demonstrated': False,
            'original_ledger': pin(ROOT / 'ledger-before-terminal.json'), 'evidence': list(map(pin, evidence))}
        t.c.save(ROOT / 'closeout.json', value)
        ledger['controller_decisions'][0].update(status='completed_rejected',
            response_sha256=t.c.sha(decision / 'response.json'), completion_sha256=t.c.sha(decision / 'completion.json'),
            rejection_sha256=t.c.sha(decision / 'failure.json'))
        ledger.update(status='closed_failed_no_retry', closed_at_utc=now.isoformat(), closeout=pin(ROOT / 'closeout.json'))
        t._ledger(ROOT / 'ledger.json', ledger)
        return {'closeout': pin(ROOT / 'closeout.json'), 'ledger': pin(ROOT / 'ledger.json'),
                'complete': False, 'account_originals': 2, 'fits': 0, 'window_wall_seconds': value['window_wall_seconds']}


if __name__ == '__main__':
    print(json.dumps(close(), sort_keys=True))
