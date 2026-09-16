"""Actual Codex/Responses/MCP source-review loop with NO paid model.

Scripted responses prove transport only. Their isolated fixture ledger is not
provider cost, and their terminal decision is not research authored by GLM.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_rsi import canonical, digest, file_hash, fresh_json
from paid_budget import PaidBudget
import run_source_review as runner


class ScriptedBackend:
    def __init__(self):
        self.sample_calls = 0
        self.responses = [
            '<think>Synthetic transport fixture: inspect three metadata tools.</think>'
            '<tool_call>mcp__controller_tools__inspect_source_context</tool_call>'
            '<tool_call>mcp__controller_tools__inspect_source_readiness</tool_call>'
            '<tool_call>mcp__controller_tools__inspect_source_archive</tool_call>',
            '<think>Synthetic transport fixture: close the loop without choosing data.</think>'
            '<tool_call>mcp__controller_tools__submit_source_review_decision'
            '<arg_key>action</arg_key><arg_value>defer</arg_value>'
            '<arg_key>artifact_id</arg_key><arg_value></arg_value>'
            '<arg_key>reason</arg_key><arg_value>Synthetic transport fixture only; '
            'not model-authored research and no acquisition or evaluation authority.</arg_value></tool_call>',
        ]

    def encode(self, turn):
        return {'rendered_prompt': 'synthetic transport fixture; no real tokenizer',
                'token_ids': [1, 2, 3], 'tokenizer_repo': 'fixture',
                'tokenizer_revision': 'fixture', 'chat_template_sha256': 'a' * 64}

    def sample(self, token_ids, max_output_tokens, timeout_seconds):
        if not self.responses:
            raise RuntimeError('unexpected third scripted sample; no fallback or retry')
        self.sample_calls += 1
        return {'text': self.responses.pop(0), 'output_tokens': [4, 5],
                'cached_input_tokens': 1, 'finish_reason': 'stop',
                'provider': {'reported_model': runner.MODEL,
                    'session_id': 'synthetic-fixture', 'sampling_session_id': 'synthetic-fixture'}}


def canary(prepared):
    preparation, manifest, _ = runner.verify_preparation(prepared)
    if manifest['purpose'] != 'transport_canary':
        raise ValueError('only a fresh transport canary may run scripted replies')
    if any((prepared / n).exists() for n in ('session', 'fixture-budget', 'fixture-only-claim.json')):
        raise ValueError('permanent fixture already used; preserve and use a fresh ID')
    sources = preparation['source_hashes']
    for module in (Path(__file__), Path(runner.__file__)):
        if sources.get('source_review_tools/' + module.name) != file_hash(module):
            raise ValueError('actual fixture/dispatcher differs from frozen source')
    fresh_json(prepared / 'fixture-only-claim.json', {
        'evidence_mode': 'synthetic_transport_fixture', 'actual_tinker_calls': 0,
        'real_budget_access': False, 'credentials_loaded': False,
        'decision_is_model_authored': False, 'source_hashes': sources})
    budget = PaidBudget.create(prepared / 'fixture-budget', {
        'experiment_id': 'fixture-' + prepared.name, 'cap_usd': '10', 'target_usd': '10',
        'buckets_usd': {'learning': '10'},
        'authority': 'Synthetic token counters only; no provider or acquisition authorization.'})
    backend = ScriptedBackend()
    try:
        assessment = runner.run_session(prepared=prepared, backend=backend, budget=budget,
            prompt='Synthetic transport fixture: execute the scripted tools and terminal handshake.',
            evidence_mode='synthetic_transport_fixture')
        if (backend.sample_calls != 2 or assessment['turns'] != 2 or assessment['tool_calls'] != 4
                or assessment['model_authorship_proven'] is not False):
            raise ValueError('fixture must complete exactly two samples and four tools')
        runner.verify_preparation(prepared)
    except Exception as exc:
        fresh_json(prepared / 'fixture-failure.json', {'error_type': type(exc).__name__,
            'message_sha256': digest(str(exc)), 'actual_tinker_calls': 0,
            'automatic_retry': False, 'permanent_artifacts_preserved': True})
        raise
    result = {'schema': 'historical_source_review_codex_fixture_canary_v1', 'passed': True,
        'actual_codex_cli': True, 'actual_tinker_calls': 0, 'credentials_loaded': False,
        'source_hashes': sources, 'context_sha256': preparation['context_sha256'],
        'preparation_sha256': file_hash(prepared / 'preparation.json'),
        'codex_cli_sha256': file_hash(runner.harness.CODEX),
        'python_sha256': file_hash(Path(sys.executable)),
        'assessment_sha256': file_hash(prepared / 'session/assessment.json'),
        'fixture_claim_sha256': file_hash(prepared / 'fixture-only-claim.json'),
        'scripted_samples': 2, 'tool_calls': 4, 'local_terminal_ack_without_third_sample': True,
        'model_authorship_proven': False, 'new_market_prices_or_labels_read': False,
        'new_fits': 0, 'new_downloads': 0, 'execution_admitted': False,
        'fixture_ledger_is_not_provider_cost': True}
    result['result_sha256'] = digest(result)
    fresh_json(prepared / 'codex-fixture-canary.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    result = canary(parser.parse_args().prepared.resolve())
    print(canonical({k:v for k,v in result.items() if k != 'source_hashes'}))
