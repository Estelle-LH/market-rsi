"""Account the exact completed, pre-source s01 failure; never retry its calls."""
from datetime import datetime, timezone
import argparse
import fcntl
import json
import os

from supervisor_harness import run_price_discovery as entry
from supervisor_harness import price_account_roles as roles
from supervisor_harness import price_capacity_source as guard

r, t = entry.r, entry.r.t
ROOT = t.ROOT.parent / 'market-rsi-coevo-price-5h-20261007-01-s01'


def close(*, check_only=False):
    if (ROOT / 'closeout.json').exists():
        raise FileExistsError('Preserve existing closeout; no repeat')
    with (ROOT / '.entry.lock').open('a+') as a, (ROOT / '.pilot.lock').open('a+') as b:
        for lock in (a, b):
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ledger = t._file(ROOT / 'ledger.json')
        config, service, _ = entry.build(r.pin(ROOT / 'launch.json'))
        if (ledger['status'] != 'open' or ledger['attempts']
                or len(ledger['controller_decisions']) != 1
                or ledger['controller_decisions'][0]['status'] != 'completed'):
            raise ValueError('Exact completed original and zero attempts required')
        decision_dir = ROOT / 'decisions' / ledger['controller_decisions'][0]['feedback_sha256']
        packet, claim = [t._file(decision_dir / name) for name in ('input.json', 'claim.json')]
        row = ledger['controller_decisions'][0]
        if (ledger['authorization_sha256'] != config['authorization']['sha256']
                or claim['authorization'] != config['authorization']
                or claim['configuration_sha256'] != config['configuration']['sha256']
                or t.c._read(claim['input_binding']) != packet
                or row['input_sha256'] != t.c._digest(packet)
                or row['completion_sha256'] != r.w.sha(decision_dir / 'completion.json')):
            raise ValueError('Exact launch/ledger/original Controller binding required')
        t._review(packet, claim['input_binding'], config['authorization'], claim['review'], service.runtime.repo,
                  configuration_binding=config['configuration'], config=service.runtime.config)
        decision = t._recover(decision_dir, packet, claim, roles.transport_contract())
        digest = t.c._digest(decision)
        if digest != ledger['controller_decisions'][0]['decision_sha256']:
            raise ValueError('Original decision differs from charged ledger')
        author_id = 'capacity-author-r0001-' + digest[:12]
        calls = list((ROOT / 'role_calls').glob('*/*/claim.json'))
        if len(calls) != 2 or {p.parent.parent.name for p in calls} != {'input_review', 'author'}:
            raise ValueError('Exact one input review and one author; no later role')
        usages, evidence = [], []
        for p in calls:
            role_claim = t._file(p)
            if role_claim['authorization'] != config['authorization']:
                raise ValueError('Role original has different batch authority')
            roles._recover(p.parent, t._file(p), t._file(p.parent / 'schema.json'))
            usages.append(t._file(p.parent / 'timing.json'))
            evidence.extend(r.pin(p.parent / name) for name in ('claim.json', 'response.json', 'completion.json', 'timing.json'))
        response = t._file(ROOT / 'role_calls/author' / author_id / 'response.json')
        body = t._file(ROOT / 'role_calls/author' / author_id / 'input.json')['payload']
        if (body['original_controller_decision'] != decision or response['decision_sha256'] != digest
                or response['change_id'] != decision['capacity']['change_id']
                or {response['source_path'], response['test_path']} != set(decision['capacity']['write_paths'])
                or body['parent_identity'] != service.capacity.config['baseline']
                or body['parent_entrypoints'] != service.capacity.config['entrypoints']):
            raise ValueError('Author is not exactly bound to this original and parent')
        manifest = entry.s.loop._read_pair(ROOT / 'price-loop/manifest.json')
        seed = t.c._read(r.pin(ROOT / 'initial-feedback.json'))
        outputs = {stage: entry.s.loop._read_pair(ROOT / ('price-loop/round-0001-' + stage + '.done.json'))['output']
                   for stage in ('input', 'controller')}
        context = {'round_index': 1, 'seed': seed, 'previous_result': seed,
                   'previous_feedback_sha256': t.c._digest(seed), 'outputs': outputs}
        if (manifest['seed'] != seed or manifest['handler_identity'] != service.identity()
                or t._file(ROOT / 'price-loop/round-0001-implement.claim.json') != {
                    'context_sha256': t.c._digest(context), 'manifest_sha256': r.w.sha(ROOT / 'price-loop/manifest.json'),
                    'previous_feedback_sha256': t.c._digest(seed), 'round_index': 1, 'stage': 'implement'}):
            raise ValueError('Exact entry manifest/failed implementation context required')
        if (outputs['controller']['decision'] != decision
                or outputs['input']['input'] != claim['input_binding']
                or outputs['input']['review'] != claim['review']):
            raise ValueError('Reviewed input and original cross-stage binding drift')
        failed = ROOT / 'price-loop/round-0001-implement.failed.json'
        if t._file(failed) != {'claim_sha256': r.w.sha(ROOT / 'price-loop/round-0001-implement.claim.json'),
                              'exception_type': 'ValueError', 'retry_allowed': False}:
            raise ValueError('Exact immutable pre-source admission failure required')
        combined = len((response['capacity_source'] + response['test_source']).encode())
        if combined != 14762 or combined <= 12288:
            raise ValueError('Not this exact observed source/test size failure')
        try:
            guard.validate_source(response['capacity_source'])
        except ValueError as error:
            if str(error) != 'private or unknown capacity attribute':
                raise
        else:
            raise ValueError('Expected additional original static rejection absent')
        for name in decision['capacity']['write_paths']:
            if (service.runtime.repo / name).exists():
                raise ValueError('Source exists: not a certain pre-source failure')
        for p in [decision_dir / 'process.json', *(p.parent / 'process.json' for p in calls)]:
            try:
                os.kill(t._file(p)['pid'], 0)
            except ProcessLookupError:
                pass
            else:
                raise RuntimeError('Original process exists; do not close')
        selected = service.capacity.validate()
        if selected['manifest'] != t._file(ROOT / 'capacity-configuration.json')['baseline']:
            raise ValueError('Selected capacity unexpectedly changed')
        if check_only:
            return {'checks_passed': True, 'write_performed': False, 'calls_retried': 0, 'fits': 0,
                    'combined_bytes': combined, 'exact_originals_completed': 3}
        now = datetime.now(timezone.utc)
        controller_timing = t._file(decision_dir / 'timing.json')
        timings = [controller_timing, *usages]
        r.w.save(ROOT / 'ledger-before-terminal.json', ledger)
        closeout = {'schema': 'market_rsi_exact_pre_source_failure_closeout_v1', 'batch_id': ROOT.name,
            'complete': False, 'status': 'NOT_COMPLETE', 'closed_at_utc': now.isoformat(),
            'first_blocking_stage': 'round1.capacity_author.completed_source_admission',
            'reason': 'Combined source/test 14762 exceeds unchanged12288; source also uses unadmitted dict.pop',
            'original_response_changed': False, 'retry_allowed': False, 'quota_refund': False,
            'authorization': config['authorization'], 'configuration': config['configuration'],
            'original_controller_decision_sha256': digest,
            'proposal': {'change_id': decision['capacity']['change_id'], 'axis': decision['action'],
                         'status': 'proposed; author source rejected before implementation/trial/adoption'},
            'account_originals_started': 3, 'account_originals_completed': 3,
            'calls': {'controller': 1, 'author': 1, 'input_review': 1, 'source_review': 0, 'result_review': 0},
            'candidate_attempts': 0, 'fits_reserved': 0, 'fits_entered': 0, 'predictions_generated': 0,
            'selected_capacity': selected, 'initial_feedback': r.pin(ROOT / 'initial-feedback.json'),
            'unchanged_incumbent': ledger['incumbent'], 'research_pool_sha256': ledger['research_pool_sha256'],
            'performance_evidence': False, 'capacity_gain': False, 'downstream_effect': False,
            'timings': timings, 'known_total_tokens': sum(v['usage']['totalTokens'] for v in timings),
            'subscription_usd': 'unknown', 'paid_provider_usd': 0,
            'window_wall_seconds': (now - t.c._time(service.runtime.fixed_grant['start_utc'])).total_seconds(),
            'original_processes_gone': True, 'failure': r.pin(failed),
            'original_ledger': r.pin(ROOT / 'ledger-before-terminal.json'), 'evidence': evidence}
        r.w.save(ROOT / 'closeout.json', closeout)
        ledger.update(status='closed_failed_no_retry', closed_at_utc=now.isoformat(), closeout=r.pin(ROOT / 'closeout.json'))
        t._ledger(ROOT / 'ledger.json', ledger)
        return {'closeout': r.pin(ROOT / 'closeout.json'), 'ledger': r.pin(ROOT / 'ledger.json'),
                'complete': False, 'originals': 3, 'fits': 0, 'known_tokens': closeout['known_total_tokens']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(json.dumps(close(check_only=parser.parse_args().check), sort_keys=True))
