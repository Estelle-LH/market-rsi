"""Real Codex/Responses/MCP loop, with scripted replies and NO paid provider.

Requires a fresh transport_canary preparation. Its decision is synthetic
transport evidence only, never a controller research decision. Fixture token
counters live in an isolated fixture ledger and are not provider usage.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_rsi import canonical, digest, file_hash, fresh_json, load_json
from paid_budget import PaidBudget
import run_validation_design as runner


class ScriptedBackend:
    def __init__(self):
        self.sample_calls = 0
        self.responses = [
            '<think>Transport fixture: inspect the three metadata tools.</think>'
            '<tool_call>mcp__controller_tools__inspect_validation_context</tool_call>'
            '<tool_call>mcp__controller_tools__inspect_validation_readiness</tool_call>'
            '<tool_call>mcp__controller_tools__inspect_validation_archive</tool_call>',
            '<think>Transport fixture: close the tool loop without a research decision.</think>'
            '<tool_call>mcp__controller_tools__submit_validation_decision'
            '<arg_key>action</arg_key><arg_value>defer</arg_value>'
            '<arg_key>artifact_id</arg_key><arg_value></arg_value>'
            '<arg_key>reason</arg_key><arg_value>Synthetic transport fixture only; '
            'not a model-authored research decision and no evaluation authorized.</arg_value></tool_call>',
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
    preparation = load_json(prepared / 'preparation.json')
    if preparation['purpose'] != 'transport_canary':
        raise ValueError('only a fresh explicit transport_canary may run scripted replies')
    if (prepared / 'session').exists() or (prepared / 'fixture-budget').exists():
        raise ValueError('permanent fixture already used; preserve and use a fresh ID')
    sources = preparation['source_hashes']
    for name, expected in sources.items():
        if (file_hash(prepared / 'source-snapshot' / name) != expected
                or file_hash(Path(__file__).resolve().parents[1] / name) != expected):
            raise ValueError('fixture source snapshot changed')
    for module in (Path(__file__), Path(runner.__file__)):
        if sources.get('validation_tools/' + module.name) != file_hash(module):
            raise ValueError('actual canary/dispatcher differs from source snapshot')
    budget = PaidBudget.create(prepared / 'fixture-budget', {
        'experiment_id': 'fixture-' + prepared.name, 'cap_usd': '10', 'target_usd': '10',
        'buckets_usd': {'learning': '10'},
        'authority': 'Synthetic token counters only; no provider or acquisition authorization.'})
    fresh_json(prepared / 'fixture-only-claim.json', {
        'evidence_mode': 'synthetic_transport_fixture', 'actual_tinker_calls': 0,
        'real_budget_access': False, 'credentials_loaded': False,
        'decision_is_model_authored': False, 'source_hashes': sources})
    backend = ScriptedBackend()
    try:
        assessment = runner.run_session(prepared=prepared, backend=backend, budget=budget,
            prompt='Synthetic transport fixture: execute the scripted tools and terminal handshake.',
            evidence_mode='synthetic_transport_fixture')
    except Exception as exc:
        fresh_json(prepared / 'fixture-failure.json', {'error_type': type(exc).__name__,
            'message_sha256': digest(str(exc)), 'actual_tinker_calls': 0,
            'automatic_retry': False, 'permanent_artifacts_preserved': True})
        raise
    if (backend.sample_calls != 2 or assessment['turns'] != 2 or assessment['tool_calls'] != 4
            or assessment['model_authorship_proven'] is not False):
        raise ValueError('fixture transport did not complete the exact two-sample/four-tool sequence')
    if any(file_hash(prepared / 'source-snapshot' / n) != h for n, h in sources.items()):
        raise ValueError('fixture source changed during execution')
    result = {'schema': 'historical_validation_codex_fixture_canary_v1', 'passed': True,
        'actual_codex_cli': True, 'actual_tinker_calls': 0, 'credentials_loaded': False,
        'source_hashes': sources, 'context_sha256': preparation['context_sha256'],
        'source_preparation_sha256': file_hash(prepared / 'preparation.json'),
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
    print(canonical({k: v for k, v in result.items() if k != 'source_hashes'}))
