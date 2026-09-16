"""Eight-round paired archive-memory replication with twenty sealed Final hours."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import pickle
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'audit_tools')]

from market_rsi import canonical, digest, file_hash, fresh_json, load_json
from paid_budget import PaidBudget, money
from glm_canary import MODEL, cost
from controller_harness_contract import (
    MAX_CUMULATIVE_INPUT_TOKENS,
    MAX_CUMULATIVE_OUTPUT_TOKENS,
)
from memory_pilot.learning import BASE, evaluate, read_cache
from memory_replication.broker import Broker, run_worker
from memory_replication.controller import TinkerGLMBackend, harness, run_session
from data_scientist_harness.release import git, source_files
from scripts.validate_experiment_spec import validate as validate_spec


TAG = 'pm-memory-replication-v0.1.1'
BUDGET = ROOT/'artifacts/kalshi-research-glm53-20260907-01/budget'
AUTH = 'd5bcc2d00a3b574485252693c4ba07b3a4a3ab9e083ac3bbbc1d8b30e556a8f9'
UPPER = cost(MAX_CUMULATIVE_INPUT_TOKENS, MAX_CUMULATIVE_OUTPUT_TOKENS)
INITIAL = ROOT/'artifacts/memory-train-data-20260913-01'
SPEC_PATH = ROOT/'MEMORY_REPLICATION_SPEC_2026-09-14.json'


def source_paths():
    paths = set(source_files(ROOT))
    paths |= set((ROOT/'memory_pilot').glob('*.py'))
    paths |= set((ROOT/'memory_replication').glob('*.py'))
    paths |= {
        ROOT/'audit_tools/run_typed_raw_profile.py',
        ROOT/'scripts/validate_experiment_spec.py',
        ROOT/'MEMORY_REPLICATION_2026-09-14.md',
        SPEC_PATH,
    }
    return sorted(paths)


def hashes():
    return {str(path.relative_to(ROOT)): file_hash(path) for path in source_paths()}


def publication():
    files = hashes()
    repo = ROOT.parents[1]
    ref = 'refs/tags/' + TAG
    commit = git(repo, 'rev-parse', ref+'^{commit}').decode().strip()
    if git(repo, 'remote', 'get-url', 'origin').decode().strip() != 'https://github.com/Estelle-LH/RSIBench-Data.git':
        raise ValueError('wrong origin')
    names = ['research/market_rsi/'+path for path in files]
    if git(repo, 'status', '--porcelain', '--untracked-files=all', '--', *names).strip():
        raise ValueError('dirty frozen replication source')
    for path, sha256 in files.items():
        if hashlib.sha256(git(repo, 'show', commit+':research/market_rsi/'+path)).hexdigest() != sha256:
            raise ValueError('replication source not committed')
    if git(repo, 'cat-file', '-t', ref).decode().strip() != 'tag':
        raise ValueError('annotated tag required')
    tag_object = git(repo, 'rev-parse', ref).decode().strip()
    actual = {value.split()[1]: value.split()[0]
              for value in git(repo, 'ls-remote', 'origin', ref, ref+'^{}').decode().splitlines()}
    if actual != {ref: tag_object, ref+'^{}': commit}:
        raise ValueError('replication tag is not published at authorized origin')
    return dict(commit=commit, tag=TAG, tag_object=tag_object, source_hashes=files)


def cache_record(path, session):
    header = load_json(path/'header.json')
    record = dict(date=session, path=str(path), header_sha256=file_hash(path/'header.json'),
                  cache_sha256=header['sha256'])
    read_cache(record)
    return record


def workspace(path, train, baseline, archive, round_number, arm, rounds, *, fixture=False):
    path.mkdir(parents=True, exist_ok=False)
    (path/'records').mkdir()
    (path/'trials').mkdir()
    qa = []
    for record in train:
        header = load_json(Path(record['path'])/'header.json')
        quality = header.get('quality', {})
        qa.append(dict(session=record['date'], rows=header['shape'][0],
            counts=quality.get('counts', {}), feature_min=header.get('feature_minimum'),
            feature_max=header.get('feature_maximum'),
            target_rms_price_bps=quality.get('target_rms_price_bps'),
            source_hash=record['cache_sha256']))
    config = dict(fixture=fixture, source_hashes=hashes(), train=train, baseline=baseline,
        archive=archive, public_context=dict(round=round_number, planned_rounds=rounds,
            arm=arm, train_qa=qa, train_sessions=[record['date'] for record in train],
            chronological_fit_sessions=[record['date'] for record in train[:-1]],
            opened_train_check_session=train[-1]['date'],
            current_dev='runner-sealed until both submissions; unavailable through tools',
            final_test='opaque, closed', maximum_session_usd_not_spend=str(UPPER),
            maximum_planned_arm_usd_not_spend=str(rounds*UPPER),
            primary_final_selection=f'Round {rounds} submitted specification, refit on that rounds whole Train before Dev, then unchanged Final test',
            common_findings='Earlier source diagnostics found concentration and wide spreads in a small preliminary sample. '
                'Quote midpoint predictability is not executable profit. Do not delete rows or change the target based on future spreads. '
                'Only causal eligible pairs are used; millions of overlapping rows are dependent.',
            supplied_research='Reuse scikit-learn 1.6 common-pitfalls sections 10.1-10.2: fit preprocessing only on earlier Train. '
                'Rolling-origin evaluation moves forward once per round. Reflexion motivates archive feedback without weight updates, not profitability.',
            prior_pilot_import='No prior pilot plan, archive, checkpoint, score or post-hoc ablation is included.',
            model=MODEL, component_change='features OR trainer/normalizer per proposal; fixed target, weights, rows, seed, no clipping',
            operator_limit='Four tabular learners are an executable starting library. Unsupported capabilities may be proposed in notes but not installed mid-comparison.'))
    fresh_json(path/'config.json', config)
    return file_hash(path/'config.json')


def arm_cost(snapshot, prefix):
    jobs = {key: value for key, value in snapshot['jobs'].items()
            if key.startswith(prefix+'-turn-')}
    metered = sum((money(value.get('metered_usd') or 0) for value in jobs.values()), money(0))
    uncertain = sum((money(value.get('uncertain_upper_usd') or 0) for value in jobs.values()), money(0))
    outstanding = sum((money(value['upper_usd']) for value in jobs.values()
                       if value['state'] in ('reserved', 'dispatched')), money(0))
    return dict(metered_usd=str(metered), uncertain_upper_usd=str(uncertain),
                outstanding_usd=str(outstanding), turns=len(jobs))


def source_path(session):
    datetime.strptime(session, '%Y-%m-%dT%H')
    return '/opt/d10/raw/data/polymarket/polymarket-' + session.replace('-', '') + '.jsonl.zst'


def midnight_ms(session):
    day = datetime.strptime(session[:10], '%Y-%m-%d').replace(tzinfo=timezone.utc)
    return int(day.timestamp()*1000)


def heldout_gate(root, session, role, commitments, spec):
    root = Path(root)
    dev = [row['session'] for row in spec['dev']]
    final = [row['session'] for row in spec['final']]
    if role not in ('dev', 'final') or len(commitments) != 2 or len({item['path'] for item in commitments}) != 2:
        raise ValueError('two distinct submissions required before data access')
    for item in commitments:
        if file_hash(item['path']) != item['sha256']:
            raise ValueError('submission changed before held-out access')
    if role == 'dev':
        if session not in dev:
            raise ValueError('Dev session not predeclared')
        freeze = load_json(root/f'round-{dev.index(session)+1}'/'paired-freeze.json')
    else:
        if session not in final:
            raise ValueError('Final session not predeclared')
        for number in range(1, spec['rounds']+1):
            if not load_json(root/f'round-{number}'/'promotion-to-train.json')['consumed']:
                raise ValueError('all paired rounds required before Final access')
        freeze = load_json(root/'final-model-freeze.json')
    if freeze['commitments'] != commitments or set(freeze['models']) != {'archive', 'fresh', 'baseline'}:
        raise ValueError('paired model/submission freeze missing')


def later_data(root, row, role, commitments, spec):
    from memory_pilot.run_materialize import modules
    from run_typed_raw_profile import exchange

    session = row['session']
    heldout_gate(root, session, role, commitments, spec)
    for item in commitments:
        if file_hash(item['path']) != item['sha256']:
            raise ValueError('submission changed before held-out access')
    output = Path(root)/'data'/session
    output.mkdir(parents=True, exist_ok=False)
    contract = load_json(INITIAL/'2026-08-26/report.json')['spec']['contract']
    if digest(contract) != spec['fixed_contract']['target_contract_sha256']:
        raise ValueError('target contract differs from pre-score lock')
    remote_path = '/opt/d10/derived/'+Path(root).name+'/'+session
    operation = dict(date=session, path=source_path(session), output=remote_path,
        compressed_bytes=row['compressed_bytes'], contract=contract,
        day_start_ms=midnight_ms(session), role=role, commitments=commitments)
    fresh_json(output/'exposure-claim.json', operation)
    code = 'import types,sys\n'
    for name in ('quote_source', 'data_scientist_harness'):
        code += 'm=types.ModuleType('+repr(name)+');m.__path__=[];sys.modules[m.__name__]=m\n'
    for name, path in modules():
        code += 'm=types.ModuleType('+repr(name)+');m.__file__='+repr(path)+';sys.modules[m.__name__]=m\n'
        code += 'exec('+repr((ROOT/path).read_text())+',m.__dict__)\n'
    code += 'SPEC='+repr(operation)+'\n'+(ROOT/'memory_pilot/heldout_worker.py').read_text()
    report = exchange(code.encode(), output)
    fresh_json(output/'report.json', report)
    if not report['complete']:
        raise ValueError('held-out source failed; no replacement or score retry')
    transfer = subprocess.run(['scp', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
        'root@173.255.231.4:'+remote_path+'/rows.f64', str(output/'rows.f64')],
        capture_output=True, timeout=180)
    fresh_json(output/'transfer.json', dict(exit_code=transfer.returncode,
        process_reaped=True, derived_cache_only=True))
    if transfer.returncode or file_hash(output/'rows.f64') != report['header']['sha256']:
        raise ValueError('held-out cache transfer failed')
    fresh_json(output/'header.json', report['header'])
    return cache_record(output, session)


def mean(values):
    return sum(values)/len(values) if values else None


def final_summary(final_scores):
    arms = ('archive', 'fresh', 'baseline')
    equal_session_mse = {arm: mean([scores[arm]['candidate_mse'] for scores in final_scores])
                         for arm in arms}
    row_weighted_mse = {arm: sum(scores[arm]['candidate_mse']*scores[arm]['n'] for scores in final_scores)
                        / sum(scores[arm]['n'] for scores in final_scores) for arm in arms}
    per_session = []
    market_deltas = []
    for scores in final_scores:
        session = scores['archive']['date']
        per_session.append(dict(session=session,
            archive_mse=scores['archive']['candidate_mse'],
            fresh_mse=scores['fresh']['candidate_mse'],
            baseline_mse=scores['baseline']['candidate_mse'],
            archive_minus_fresh=scores['archive']['candidate_mse']-scores['fresh']['candidate_mse'],
            archive_minus_baseline=scores['archive']['candidate_mse']-scores['baseline']['candidate_mse']))
        fresh_markets = {row['market_index']: row for row in scores['fresh']['market_scores']}
        for row in scores['archive']['market_scores']:
            other = fresh_markets[row['market_index']]
            market_deltas.append(other['candidate_sse']-row['candidate_sse'])
    positive = [value for value in market_deltas if value > 0]
    return dict(equal_session_mse=equal_session_mse, row_weighted_mse=row_weighted_mse,
        per_session=per_session,
        archive_better_than_fresh_session_fraction=sum(row['archive_minus_fresh'] < 0 for row in per_session)/len(per_session),
        archive_better_than_baseline_session_fraction=sum(row['archive_minus_baseline'] < 0 for row in per_session)/len(per_session),
        archive_better_than_fresh_market_fraction=sum(value > 0 for value in market_deltas)/len(market_deltas),
        archive_positive_gain_top_market_share=max(positive)/sum(positive) if positive else None,
        archive_minus_fresh_session_mean=mean([row['archive_minus_fresh'] for row in per_session]),
        session_mean_pearson_ic={arm: mean([scores[arm]['pearson_ic'] for scores in final_scores
            if scores[arm]['pearson_ic'] is not None]) for arm in arms},
        session_mean_rank_ic={arm: mean([scores[arm]['rank_ic'] for scores in final_scores
            if scores[arm]['rank_ic'] is not None]) for arm in arms},
        session_mean_calibration_slope={arm: mean([scores[arm]['calibration_slope'] for scores in final_scores
            if scores[arm]['calibration_slope'] is not None]) for arm in arms},
        final_sessions=len(final_scores), distinct_utc_dates=len({row['session'][:10] for row in per_session}),
        no_iid_confidence_claim=True)


def study(root, canary_path, env_file, tokenizer_cache):
    root = Path(root)
    with (ROOT/'artifacts/historical-ingest-controller.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if root.exists():
            raise ValueError('permanent study ID already used; no duplicate/retry')
        spec = validate_spec(load_json(SPEC_PATH))
        if root.name != spec['experiment_id']:
            raise ValueError('output directory must match permanent experiment ID')
        pub = publication()
        canary = load_json(canary_path)
        if (not canary['passed'] or canary['source_hashes'] != pub['source_hashes']
                or canary['actual_tinker_calls'] != 0
                or canary['codex_sha256'] != file_hash(harness.CODEX)
                or canary['python_sha256'] != file_hash(sys.executable)):
            raise ValueError('same-source/runtime actual Codex canary required')
        for package, version in {'numpy':'1.26.4', 'scipy':'1.14.0',
                                 'scikit-learn':'1.6.1', 'tinker':'0.25.0'}.items():
            if importlib.metadata.version(package) != version:
                raise ValueError('pinned runtime differs: '+package)
        if file_hash(BUDGET/'authorization.json') != AUTH:
            raise ValueError('original authorization changed')
        budget = PaidBudget(BUDGET)
        before = budget.snapshot()
        if money(before['cap_usd']) != money(200) or any(
                value['state'] == 'dispatched' and '-turn-' in key
                for key, value in before['jobs'].items()):
            raise ValueError('budget or active provider dispatch gate')
        if min(money(before['available_usd']),
               money(before['buckets']['learning']['available_usd'])) < 2*UPPER:
            raise ValueError('first paired atomic round does not fit remaining budget')
        initial = load_json(INITIAL/'complete.json')
        expected_initial = [row['session'][:10] for row in spec['initial_train']]
        if not initial['complete'] or [row['date'] for row in initial['files']] != expected_initial:
            raise ValueError('all initial Train files required')
        train = [cache_record(INITIAL/day, session_row['session'])
                 for day, session_row in zip(expected_initial, spec['initial_train'])]
        root.mkdir(parents=True)
        (root/'data').mkdir()
        fresh_json(root/'pre-score-lock.json', dict(spec=spec, spec_sha256=file_hash(SPEC_PATH),
            canonical_spec_sha256=digest(spec), target_contract_sha256=spec['fixed_contract']['target_contract_sha256'],
            source_hashes=pub['source_hashes'], final_opened=False))
        fresh_json(root/'claim.json', dict(publication=pub,
            canary_sha256=file_hash(canary_path), nonce=secrets.token_hex(16), pid=os.getpid(),
            original_authorization_sha256=AUTH, budget_before=before, initial=train,
            dev=spec['dev'], final_commitment=digest(spec['final']), final_sessions=len(spec['final']),
            session_cap_usd=str(UPPER), arm_cap_usd=str(spec['rounds']*UPPER),
            maximum_theoretical_study_usd_not_authorized_as_spend=str(2*spec['rounds']*UPPER),
            actual_admission='each next archive+fresh pair must fit the remaining original learning bucket',
            final_selection=f'Round {spec["rounds"]} submitted; no hindsight best selection',
            study_kind=spec['claim_limits']['evidence_class'], old_run_artifacts_imported=False))
        from dotenv import dotenv_values
        backend = TinkerGLMBackend(dotenv_values(env_file).get('TINKER_API_KEY'), tokenizer_cache)
        histories = {'archive': [], 'fresh': []}
        costs = {'archive': [], 'fresh': []}
        last_models = {}
        last_commitments = []
        try:
            for round_number, row in enumerate(spec['dev'], 1):
                if hashes() != pub['source_hashes']:
                    raise ValueError('study source mutated')
                now = budget.snapshot()
                if min(money(now['available_usd']),
                       money(now['buckets']['learning']['available_usd'])) < 2*UPPER:
                    raise ValueError('next paired round exceeds remaining original budget')
                round_dir = root/f'round-{round_number}'
                round_dir.mkdir()
                baseline = run_worker(dict(plan=BASE, train=train[:-1], check=train[-1:]),
                                      round_dir/'common-baseline-check')
                if not baseline['success']:
                    raise ValueError('common baseline infrastructure failed')
                sessions = {}
                commitments = []
                order = ('archive', 'fresh') if round_number % 2 else ('fresh', 'archive')
                for arm in order:
                    prior = sum((money(item['metered_usd']) + money(item['uncertain_upper_usd'])
                                 + money(item['outstanding_usd']) for item in costs[arm]), money(0))
                    now = budget.snapshot()
                    if (prior+UPPER > spec['rounds']*UPPER
                            or min(money(now['available_usd']),
                                   money(now['buckets']['learning']['available_usd'])) < UPPER):
                        raise ValueError('atomic session exceeds arm or remaining original budget')
                    session = root/(root.name+'-'+arm+f'-r{round_number:02d}')
                    manifest = workspace(session, train, baseline,
                        histories[arm] if arm == 'archive' else [], round_number, arm,
                        spec['rounds'])
                    fresh_json(session/'dispatch-claim.json', dict(manifest_sha256=manifest,
                        publication=pub, canary_sha256=file_hash(canary_path),
                        session_upper_not_spend=str(UPPER), nonce=secrets.token_hex(16)))
                    print(canonical(dict(stage='controller_started', round=round_number,
                                         arm=arm, path=str(session))), flush=True)
                    run_session(session, backend, budget)
                    costs[arm].append(arm_cost(budget.snapshot(), session.name))
                    fresh_json(session/'cost.json', costs[arm][-1])
                    submission = load_json(session/'submission.json')
                    sessions[arm] = session
                    commitments.append(dict(path=str(session/'submission.json'),
                                            sha256=file_hash(session/'submission.json')))
                    print(canonical(dict(stage='controller_complete', round=round_number,
                        arm=arm, trial=submission['trial_id'], cost=costs[arm][-1])), flush=True)
                for arm, session in sessions.items():
                    chosen = load_json(session/'submission.json')['plan']
                    fitted = run_worker(dict(plan=chosen, train=train, check=[]),
                                        round_dir/(arm+'-refit'))
                    if not fitted['success']:
                        raise ValueError('selected refit failed; do not replace model')
                    last_models[arm] = round_dir/(arm+'-refit')
                common = run_worker(dict(plan=BASE, train=train, check=[]),
                                    round_dir/'common-baseline-refit')
                if not common['success']:
                    raise ValueError('baseline refit failed')
                last_models['baseline'] = round_dir/'common-baseline-refit'
                fresh_json(round_dir/'paired-freeze.json', dict(commitments=commitments,
                    models={arm:file_hash(path/'model.pkl') for arm, path in last_models.items()}))
                dev = later_data(root, row, 'dev', commitments, spec)
                scores = {}
                for arm, directory in last_models.items():
                    result = load_json(directory/'result.json')
                    if file_hash(directory/'model.pkl') != result['checkpoint_sha256']:
                        raise ValueError('owned model changed')
                    with (directory/'model.pkl').open('rb') as stream:
                        model = pickle.load(stream)
                    scores[arm] = evaluate(model, dev,
                                           round_dir/(arm+'-dev-predictions.npy'))
                fresh_json(round_dir/'dev-scores.json', scores)
                for arm, session in sessions.items():
                    histories[arm].append(dict(round=round_number,
                        records=Broker(session, file_hash(session/'config.json')).records(),
                        submission=load_json(session/'submission.json'),
                        own_dev={key:value for key,value in scores[arm].items()
                                 if key != 'market_scores'},
                        common_baseline_dev={key:value for key,value in scores['baseline'].items()
                                             if key != 'market_scores'},
                        cost=costs[arm][-1]))
                fresh_json(round_dir/'promotion-to-train.json', dict(dev=dev,
                    paired_submission_commitments=commitments, consumed=True))
                train.append(dev)
                last_commitments = commitments
                print(canonical(dict(stage='round_complete', round=round_number,
                    dev_session=row['session'],
                    mse={arm:score['candidate_mse'] for arm,score in scores.items()})), flush=True)

            fresh_json(root/'final-model-freeze.json', dict(commitments=last_commitments,
                models={arm:file_hash(path/'model.pkl') for arm,path in last_models.items()},
                source_hashes=pub['source_hashes'],
                selection=f'Round {spec["rounds"]} submissions; no further model dispatch',
                final_manifest_commitment=digest(spec['final'])))
            final_scores = []
            for row in spec['final']:
                record = later_data(root, row, 'final', last_commitments, spec)
                scores = {}
                for arm, directory in last_models.items():
                    if file_hash(directory/'model.pkl') != load_json(directory/'result.json')['checkpoint_sha256']:
                        raise ValueError('Final model changed')
                    with (directory/'model.pkl').open('rb') as stream:
                        model = pickle.load(stream)
                    scores[arm] = evaluate(model, record,
                        root/(arm+'-final-'+row['session']+'.npy'))
                fresh_json(root/('final-'+row['session']+'.json'), scores)
                final_scores.append(scores)
                print(canonical(dict(stage='final_session_complete',
                    session=row['session'], completed=len(final_scores),
                    total=len(spec['final']))), flush=True)
            metrics = final_summary(final_scores)
            after = budget.snapshot()
            report = dict(complete=True, rounds=spec['rounds'],
                final_sessions=[row['session'] for row in spec['final']], metrics=metrics,
                costs=costs, budget_after={key:value for key,value in after.items() if key != 'jobs'},
                publication=pub, evidence_class=spec['claim_limits']['evidence_class'],
                formal_promotion=False, pnl_measured=False,
                source_unchanged=hashes() == pub['source_hashes'])
            fresh_json(root/'complete.json', report)
            print(canonical(report), flush=True)
        except BaseException as error:
            fresh_json(root/'failure.json', dict(type=type(error).__name__,
                message=str(error)[:800], budget_after=budget.snapshot(),
                no_automatic_retry=True, partial_outcomes_preserved=True))
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--canary', type=Path, required=True)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--tokenizer-cache', type=Path, required=True)
    args = parser.parse_args()
    study(args.output.resolve(), args.canary.resolve(), args.env_file.resolve(),
          args.tokenizer_cache.resolve())
