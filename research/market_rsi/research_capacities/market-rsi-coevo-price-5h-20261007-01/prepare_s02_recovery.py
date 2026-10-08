"""Reuse only certainly completed B4 output; original window/calls remain charged."""
import argparse
import fcntl
import json
import os
from pathlib import Path
from supervisor_harness import run_price_discovery as entry
from supervisor_harness import price_candidate_author as author
from supervisor_harness import price_account_roles as roles

r, t = entry.r, entry.r.t
ROOT = t.ROOT.parent / 'market-rsi-coevo-price-5h-20261007-01-s02'
DIGEST = '34271f24b9f81f654f88ae0efa2c8bc46100408719c05a418e161e8cbbfa2e7e'
IDENT = 'author-r0002-' + DIGEST[:12]


def prepare(review_binding):
    review = t.c._read(review_binding)
    if (review.get('passed') is not True or review.get('no_new_model_call') is not True
            or review.get('entry_source_sha256') != r.w.sha(entry.__file__)
            or review.get('author_source_sha256') != r.w.sha(author.__file__)
            or review.get('original_decision_sha256') != DIGEST
            or review.get('ops_source_sha256') != r.w.sha(__file__)):
        raise ValueError('Exact independent source-only engineering review required')
    with (ROOT / '.entry.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (ROOT / 'launch-admission-v3.json').exists():
            raise FileExistsError('Preserve prepared continuation; no reprepare')
        old = t._file(ROOT / 'launch.json')
        grant = t.c._read(old['authorization'])
        if grant['deadline_utc'] != '2026-10-08T00:38:09Z' or grant['selection_cutoff_utc'] != '2026-10-08T00:33:09Z':
            raise ValueError('Never reset or extend original s02 window')
        ledger = t._file(ROOT / 'ledger.json')
        if ledger['status'] != 'open' or len(ledger['attempts']) != 1 or len(ledger['controller_decisions']) != 2:
            raise ValueError('Exact unfinished prefix and already-charged originals required')
        role = ROOT / 'role_calls/author' / IDENT
        failure, completion = r.pin(ROOT / IDENT / 'failure.json'), r.pin(role / 'completion.json')
        if review['original_failure_sha256'] != failure['sha256'] or review['original_completion_sha256'] != completion['sha256']:
            raise ValueError('Original failure/completion binding drift')
        for process in [*(ROOT / 'decisions').glob('*/process.json'), *(ROOT / 'role_calls').glob('*/*/process.json')]:
            try: os.kill(t._file(process)['pid'], 0)
            except ProcessLookupError: pass
            else: raise RuntimeError('Original process still present; do not continue')
        original = roles._recover(role, t._file(role / 'claim.json'), t._file(role / 'schema.json'))
        for key in ('candidate_source', 'test_source'):
            author.validate_source(original['response'][key], is_test=key == 'test_source')
        def save(name, value):
            path = ROOT / (name + '.json'); r.w.save(path, value); return r.pin(path)
        recovery = save('completed-round2-author-recovery', {
            'schema': 'price_completed_author_admission_recovery_v1', 'round_index': 2,
            'original_decision_sha256': DIGEST, 'original_author_id': IDENT, 'fresh_local_id': IDENT + '-admission-v3',
            'original_failure': failure, 'original_input': r.pin(role / 'input.json'),
            'original_response': r.pin(role / 'response.json'), 'original_completion': completion, 'review': review_binding})
        prefix = save('completed-round2-prefix-recovery', {
            'schema': 'price_certain_completed_capacity_round2_prefix_recovery_v1',
            'authorization': old['authorization'], 'original_manifest': r.pin(ROOT / 'price-loop/manifest.json'),
            'original_failed_stage': r.pin(ROOT / 'price-loop/round-0002-implement.failed.json'),
            'original_author_recovery': recovery, 'review': review_binding})
        new = {**old, 'recovery': prefix, 'service_sources': dict(old['service_sources']), 'source_files': dict(old['source_files'])}
        for name, module in (('entry', entry), ('author', author)):
            new['service_sources'][name] = r.pin(module.__file__)
            relative = str(Path(module.__file__).relative_to(Path(old['repo'])))
            if relative in new['source_files']: new['source_files'][relative] = r.w.sha(module.__file__)
        launch = save('launch-admission-v3', new)
        # Full original native/completion/context/selection validation, no model or fit.
        _, service, _ = entry.build(launch)
        if service.capacity.validate()['manifest']['H'] != 'e2a5ce346cc130ab03cda2bb4f9862b2602d75a612f011bac81a425b9736a049':
            raise ValueError('Actual accepted H1 selection changed')
        return {'launch': launch, 'initial_feedback': r.pin(ROOT / 'initial-feedback.json'),
            'original_deadline_utc': grant['deadline_utc'], 'model_calls': 0, 'fits': 0,
            'same_original_response_reused': True, 'original_ledger_unchanged': ledger == t._file(ROOT / 'ledger.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--review', type=Path, required=True)
    print(json.dumps(prepare(r.pin(parser.parse_args().review)), sort_keys=True))
