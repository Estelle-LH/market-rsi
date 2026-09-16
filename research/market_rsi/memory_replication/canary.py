"""Actual Codex with scripted synthetic outputs; zero paid provider calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'audit_tools')]

from market_rsi import canonical, digest, file_hash, fresh_json
from memory_replication.study import workspace, hashes
from memory_pilot.test_learning import fixture_cache
from memory_pilot.learning import BASE
from memory_replication.controller import run_session, harness
from memory_replication.broker import Broker, run_worker
from data_scientist_harness.canary import call
from glm_canary import MODEL
from paid_budget import PaidBudget


class Scripted:
    def __init__(self, root):
        self.root = root
        self.sample_calls = 0
        plan = dict(BASE, model=dict(algorithm='ridge',
            parameters=dict(alpha=.1, fit_intercept=False)))
        steps = [('inspect_experiment', {}), ('read_archive', {'offset':0}),
            ('record_research', {'note':'Reuse supplied fit-only preprocessing and chronological check evidence. This is a synthetic mechanics fixture, not market research. Compare explicit ridge penalty to OLS.'}),
            ('train_candidate', dict(trial_id='ridge-fixture', parent_trial_id='baseline',
                plan_json=json.dumps(plan), research_record='0002',
                question='Does the actual tool fit and preserve rows?',
                hypothesis='Ridge will fit on earlier synthetic rows.',
                support_criterion='Finite later predictions and correct row count.',
                refute_criterion='Any future fitting or missing prediction.')),
            ('interpret_result', dict(trial_id='ridge-fixture', result_sha256='OUTCOME',
                interpretation='Mechanics only, not financial evidence.',
                next_step='Test real source-specific data after publication.')),
            ('submit_candidate', dict(trial_id='ridge-fixture',
                reason='Synthetic terminal handshake test.'))]
        self.responses = [call(name, arguments) for name, arguments in steps]

    def encode(self, turn):
        return dict(rendered_prompt='Synthetic transport fixture', token_ids=[1,2,3],
            tokenizer_repo='fixture', tokenizer_revision='fixture',
            chat_template_sha256='a'*64)

    def sample(self, token_ids, max_output_tokens, timeout_seconds):
        if not self.responses:
            raise ValueError('unexpected extra model sample')
        self.sample_calls += 1
        text = self.responses.pop(0)
        if 'OUTCOME' in text:
            text = text.replace('OUTCOME', file_hash(self.root/'trials/ridge-fixture/result.json'))
        return dict(text=text, output_tokens=[4,5], cached_input_tokens=1,
            finish_reason='stop', provider=dict(reported_model=MODEL,
                session_id='synthetic', sampling_session_id='synthetic'))


def run(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    data = root/'synthetic-data'
    data.mkdir()
    train = [fixture_cache(data, '2026-01-01'), fixture_cache(data, '2026-01-02')]
    baseline = run_worker(dict(plan=BASE, train=train[:1], check=train[1:]),
                          root/'baseline')
    session = root/(root.name+'-session')
    workspace(session, train, baseline,
        [{'synthetic_archive':'Both original records and failures remain visible.'}],
        1, 'archive', 8, fixture=True)
    budget = PaidBudget.create(root/'fixture-budget', dict(
        experiment_id='fixture-'+root.name, cap_usd='10', target_usd='10',
        buckets_usd={'learning':'10'},
        authority='Synthetic counters only; no credentials or provider calls.'))
    backend = Scripted(session)
    assessment = run_session(session, backend, budget, fixture=True)
    records = Broker(session, file_hash(session/'config.json')).records()
    if backend.sample_calls != 6 or len(records) != 6 or any(record['error'] for record in records):
        raise ValueError('six successful real tools required')
    result = dict(passed=True, actual_codex_cli=True, actual_tinker_calls=0,
        synthetic_market_rows=True, actual_candidate_fits=1, actual_baseline_fits=1,
        model_authorship_proven=False, source_hashes=hashes(),
        codex_sha256=file_hash(harness.CODEX), python_sha256=file_hash(sys.executable),
        assessment_sha256=file_hash(session/'session/assessment.json'),
        samples=6, tools=6, terminal_handshake=assessment['terminal_handshake'],
        process_reaped=assessment['process_reaped'])
    result['sha256'] = digest(result)
    fresh_json(root/'canary.json', result)
    print(canonical({key:value for key,value in result.items() if key != 'source_hashes'}),
          flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
