"""Read-only completed-window inheritance; historical code is checked in Git."""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import re
import subprocess

import earnings_entry as e
import earnings_population as pool
import earnings_population_tasks as tasks
from earnings_population_runtime import EXTRA_BASELINE, EXTRA_CAP
from market_rsi import digest
from supervisor_harness.feedback_linked_loop import STAGES

OWNED = tasks.ARTIFACTS / 'edgar-population-20261016'
LEDGER = e.PILOT / 'api-budget.sqlite3'
REPO = Path(__file__).resolve().parents[1]
DRIVER = 'research/market_rsi/supervisor_harness/feedback_linked_loop.py'
ID = re.compile(r'edgar-population-20261016-[0-9]{2}')


@lru_cache(maxsize=2048)
def _git(repo, commit, name):
    return subprocess.run(['git', 'show', commit + ':' + name], cwd=repo,
                          check=True, capture_output=True).stdout


class _Reader:
    def __init__(self, root, ledger, repo, ident):
        self.root, self.ledger, self.repo, self.ident = root, ledger, repo, ident
        self.ids, self.extra, self.sources, self.commit, self.cache = {ident}, set(), {}, None, {}

    def read(self, bound, *, binary=False):
        if (type(bound) is not dict or set(bound) != {'path', 'sha256'}
                or type(bound['path']) is not str or type(bound['sha256']) is not str
                or not re.fullmatch(r'[0-9a-f]{64}', bound['sha256'])):
            raise ValueError('Exact original binding required')
        path = Path(bound['path'])
        if not path.is_absolute() or str(path) != bound['path'] or path.resolve() != path:
            raise ValueError('Canonical non-symlink historical path required')
        if path.is_relative_to(self.repo):
            if (self.commit is None or (str(path), bound['sha256']) not in self.sources
                    and bound != tasks.RUNTIME):
                raise ValueError('Unregistered historical production source')
            name = str(path.relative_to(self.repo))
            if name not in self.cache:
                self.cache[name] = _git(self.repo, self.commit, name)
            raw = self.cache[name]
        else:
            allowed = [self.root / kind / ident for ident in self.ids for kind in ('inputs', 'attempts')]
            allowed += [Path('/private/tmp') / ('market-rsi-' + ident) for ident in self.ids]
            allowed += [tasks.ARTIFACTS / 'edgar-research-objective-20261014',
                Path('/Users/estelle/Library/Application Support/MarketRSI/co-evo-earnings/episodes/edgar-research-20261015-09')]
            if path not in self.extra and not any(path.is_relative_to(p) for p in allowed):
                raise ValueError('Historical artifact outside exact owned roots')
            if not path.is_file():
                raise ValueError('Missing original historical artifact')
            raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != bound['sha256']:
            raise ValueError('Historical artifact/source hash differs')
        return raw if binary else e.strict_json(raw)

    def pin(self, path):
        # Caller supplies only internally derived canonical owned paths.
        if not path.is_absolute() or path.resolve() != path or not path.is_file():
            raise ValueError('Canonical existing historical evidence required before read')
        return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def scan(self, value):
        if type(value) is dict:
            if set(value) == {'path', 'sha256'}:
                self.read(value, binary=True)
            else:
                for item in value.values(): self.scan(item)
        elif type(value) is list:
            for item in value: self.scan(item)

    def pair(self, path):
        binding = self.read(self.pin(path.with_suffix('.binding.json')))
        if binding.get('path') != str(path):
            raise ValueError('Historical durable seal path differs')
        return self.read(binding)


@contextmanager
def _journal_lock(path):
    descriptor = os.open(path / '.loop.lock', os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as stream:
        fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)
        yield


def _replay(path, reader, runtime):
    manifest = reader.pair(path / 'manifest.json')
    if (set(manifest) != {'schema', 'seed', 'seed_sha256', 'handler_identity', 'driver_source_sha256', 'max_rounds'}
            or manifest['schema'] != 'feedback_linked_loop_v1'
            or manifest['seed_sha256'] != digest(manifest['seed'])
            or type(manifest['max_rounds']) is not int or not 1 <= manifest['max_rounds'] <= 2
            or manifest['max_rounds'] != len(runtime['companies'])
            or manifest['driver_source_sha256'] != runtime['sources'][DRIVER]['sha256']
            or set(manifest['handler_identity']) != set(STAGES)):
        raise ValueError('Historical journal manifest/driver/round identity differs')
    reader.scan(manifest)
    if manifest['seed']['companies'] != runtime['companies'] or manifest['seed']['population'] != reader.read(runtime['initial_population']):
        raise ValueError('Historical journal seed differs from original runtime')
    for stage, identity in manifest['handler_identity'].items():
        if (identity.get('stage') != stage
                or identity.get('adapter') != runtime['sources']['tools/earnings_population_loop.py']
                or identity.get('admission') != {'function': 'execute.<locals>.admit',
                    'module': runtime['sources']['tools/earnings_population_run.py']}
                or identity.get('services') != {role: {'function': 'Services.' + role,
                    'module': runtime['sources']['tools/earnings_population_services.py']}
                    for role in ('controller', 'author', 'review', 'forecast')}):
            raise ValueError('Historical handler identity differs')
    previous, expected_files = manifest['seed'], set()
    for index in range(1, manifest['max_rounds'] + 1):
        outputs = {}
        for stage in STAGES:
            current = dict(round_index=index, seed=manifest['seed'], previous_result=previous,
                           previous_feedback_sha256=digest(previous), outputs=outputs)
            prefix = path / f'round-{index:04d}-{stage}'
            claim, done = prefix.with_suffix('.claim.json'), prefix.with_suffix('.done.json')
            expected_files.update([claim.name, done.name, done.with_suffix('.binding.json').name])
            expected = dict(round_index=index, stage=stage, context_sha256=digest(current),
                manifest_sha256=reader.pin(path / 'manifest.json')['sha256'], previous_feedback_sha256=digest(previous))
            if reader.read(reader.pin(claim)) != expected:
                raise ValueError('Historical claim/context/feedback differs')
            result = reader.pair(done)
            if (set(result) != {'claim_sha256', 'output', 'output_sha256'}
                    or type(result['output']) is not dict
                    or result['claim_sha256'] != reader.pin(claim)['sha256']
                    or result['output_sha256'] != digest(result['output'])):
                raise ValueError('Historical completed output differs')
            reader.scan(result['output'])
            outputs[stage] = result['output']
        previous = outputs['reconcile']
    if {p.name for p in path.glob('round-*')} != expected_files or reader.pair(path / 'manifest.json') != manifest:
        raise ValueError('Historical failed/orphaned/changed journal record')
    return dict(status='completed', completed_rounds=manifest['max_rounds'], result=previous), manifest['seed']


def _load(binding, root, ledger, repo, seen):
    path = Path(binding['path'])
    ident = path.parent.name
    if (not ID.fullmatch(ident) or path != root / 'attempts' / ident / 'population-run-result.json'
            or ident in seen or len(seen) >= 50):
        raise ValueError('Exact noncyclic owned completed result required')
    seen = {*seen, ident}
    reader = _Reader(root, ledger, repo, ident)
    result = reader.read(binding)
    if (result.get('status') != 'COMPLETED_DISCOVERY_PILOT' or result.get('retry_allowed') is not False
            or (path.parent / 'population-run-failure.json').exists()):
        raise ValueError('Failed/incomplete prior run remains closed')
    token = hashlib.sha256(ident.encode()).hexdigest()
    registry = ledger.parent / '.capacity-runtime-claims'
    owner_path, claim_path = registry / (token + '.result.json'), registry / (token + '.json')
    reader.extra.update([owner_path, claim_path, Path(tasks.FULL_PLAN['path']), Path(tasks.SCORER['path'])])
    owner_bound, claim_bound = reader.pin(owner_path), reader.pin(claim_path)
    owner, claim = reader.read(owner_bound), reader.read(claim_bound)
    runtime_bound = owner['runtime']
    runtime = reader.read(runtime_bound)
    if (owner.get('status') != 'COMPLETED_COMPONENT_CONTEXT' or owner.get('error_type') is not None
            or owner.get('retry_allowed') is not False or claim.get('retry_allowed') is not False
            or claim.get('id') != ident or claim.get('runtime') != runtime_bound
            or runtime.get('schema') != 'earnings_population_runtime_v1'
            or runtime.get('id') != ident or runtime.get('root') != str(path.parent)
            or runtime.get('ledger') != str(ledger) or claim.get('source_commit') != runtime.get('source_commit')
            or not re.fullmatch(r'[0-9a-f]{40}', runtime['source_commit'])):
        raise ValueError('Original completed owner/runtime identity differs')
    reader.commit = runtime['source_commit']
    if any(not Path(b['path']).is_relative_to(repo) for b in runtime['sources'].values()):
        raise ValueError('Historical production source outside owned checkout')
    reader.sources = {(b['path'], b['sha256']) for b in runtime['sources'].values()}
    study = reader.read(runtime['forecast_study'])
    inherited, extra_evidence = None, []
    if study.get('continuation') is not None:
        continuation = reader.read(study['continuation'])
        inherited, ancestor_ids, ancestor_qa = _load(continuation['previous_result'], root, ledger, repo, seen)
        reader.ids.update(ancestor_ids)
        reader.extra.update(Path(b['path']) for b in inherited['evidence'])
        # Only exact ancestor kernels already validated against their original
        # resident tasks may travel across windows; never admit a dataset root.
        reader.extra.update(Path(b['path']) for b in ancestor_qa)
        for bound in ancestor_qa: reader.read(bound, binary=True)
        if (continuation.get('schema') != 'earnings_population_continuation_v1'
                or continuation.get('population_sha256') != digest(inherited['population'])
                or continuation.get('feedback') != inherited['feedback']
                or continuation.get('evidence') != inherited['evidence']
                or reader.read(runtime['initial_population']) != inherited['population']):
            raise ValueError('Cross-window population/last feedback differs')
        extra_evidence = [study['continuation'], *inherited['evidence']]
        reader.scan(continuation)
    residents = [tasks.resident(cik) for cik in runtime['companies']]
    qa_bindings = [r['kernel']['qa'] for r in residents]
    reader.extra.update(Path(b['path']) for b in qa_bindings)
    for bound in qa_bindings: reader.read(bound, binary=True)
    original = residents[0]['runtime']
    if (study.get('schema') != 'earnings_coevolution_study_v1' or study.get('data') != tasks.FULL_PLAN
            or study.get('scorer') != tasks.SCORER or study.get('sole_ledger') != str(ledger)
            or study.get('runtime_config') != original or study.get('cases') != [r['case'] for r in residents]
            or study.get('model') != {'requested_model': 'gpt-6.1-sol', 'serving_snapshot': 'unknown', 'serving_snapshot_verified': False}
            or runtime.get('rates') != original['models']['gpt-6.1-sol']
            or runtime.get('original_extra_baseline') != EXTRA_BASELINE
            or runtime.get('original_extra_cap_nano_usd') != EXTRA_CAP):
        raise ValueError('Historical fixed data/scorer/model context differs')
    review = reader.read(runtime['review'])
    if (review.get('verdict') != 'PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY'
            or type(review.get('reviewer')) is not str or not review['reviewer'].strip()
            or review['reviewer'].strip().lower() in {'root', '/root'}
            or review.get('blocking_findings') != [] or review.get('source_commit') != reader.commit
            or review.get('reviewed_configuration_sha256') != digest({k: v for k, v in runtime.items() if k != 'review'})):
        raise ValueError('Original runtime review differs')
    reader.scan(runtime)
    reader.scan(study)
    reader.scan(result)
    budget = owner['budget_summary']
    if (budget != result['budget'] or budget.get('blocked') is not False
            or budget.get('unresolved_reserved_usd') != 0 or budget.get('cap_usd') != 200
            or budget.get('model_cap_usd') != 100 or budget.get('night_cap_usd') != runtime['additional_cap_nano_usd'] / 1e9
            or not 0 <= budget.get('charged_upper_bound_usd', -1) <= 200
            or not 0 <= budget.get('night_charged_upper_bound_usd', -1) <= budget['night_cap_usd']
            or budget.get('prior_history_sha256') != runtime['baseline']['rows_sha256']):
        raise ValueError('Original completed budget/zero-pending summary differs')
    clock = reader.pair(path.parent / 'clock.json')
    if (owner['clock']['path'] != str(path.parent / 'clock.json') or clock != reader.read(owner['clock'])
            or clock.get('source_commit') != reader.commit or clock.get('cutoff_utc') != runtime['cutoff_utc']
            or clock.get('deadline_utc') != runtime['deadline_utc']):
        raise ValueError('Original owner clock seal differs')
    with _journal_lock(path.parent / 'loop'):
        replay, seed = _replay(path.parent / 'loop', reader, runtime)
    if replay != result['result'] or (inherited is not None and seed['feedback'] != inherited['feedback']):
        raise ValueError('Original completed replay or inherited feedback differs')
    final = replay['result']
    population = pool.validate(final['population'])
    count = replay['completed_rounds']
    population_bound = reader.pin(path.parent / f'population-{count:02d}.json')
    if (reader.read(population_bound) != population or population['observations'][-1]['feedback'] != final['feedback']
            or final['feedback']['path'] != str(path.parent / f'feedback-{count:02d}.json')
            or population['protected'] != {'K': digest({'data': tasks.FULL_PLAN, 'scorer': tasks.SCORER}),
                'M': digest(study['model']), 'C': runtime['sources']['forecaster']['sha256']}
            or population['exposed_companies'] != seed['population']['exposed_companies'] + runtime['companies']):
        raise ValueError('Final durable population/feedback/exposure/context differs')
    feedback, observation = reader.read(final['feedback']), population['observations'][-1]
    if (feedback.get('schema') != 'earnings_population_feedback_v1'
            or any(feedback.get(k) != observation[k] for k in ('company_id', 'results', 'stable_id'))
            or feedback.get('round_index') != count):
        raise ValueError('Last feedback content differs from final observed experiment')
    evidence = [binding, runtime_bound, claim_bound, owner_bound, population_bound, final['feedback'],
                reader.pin(path.parent / 'loop/manifest.json'), runtime['review'], *extra_evidence]
    return (dict(population=deepcopy(population), feedback=deepcopy(final['feedback']), evidence=evidence),
            reader.ids, [*(ancestor_qa if inherited is not None else []), *qa_bindings])


def load(result_binding, *, root, ledger, repo):
    root, ledger, repo = map(Path, (root, ledger, repo))
    if root != OWNED or ledger != LEDGER or repo != REPO or any(p.resolve() != p for p in (root, ledger, repo)):
        raise ValueError('Exact own root/sole ledger/source checkout required')
    return _load(result_binding, root, ledger, repo, set())[0]
