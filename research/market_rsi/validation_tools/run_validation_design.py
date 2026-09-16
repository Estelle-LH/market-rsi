"""New validation-design stage composed from the existing Codex/GLM harness.

The old scientific source stays untouched. Only the exact MCP script argument
is replaced in the legacy command template. No evaluation or acquisition tool
is available in this stage. Preflight precedes credential loading and backend
construction; each actual GLM turn uses the original append-only paid ledger.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_codex_glm_controller as harness
from codex_glm_model_catalog import model_catalog
from codex_glm_provider import ControllerSession, TinkerGLMBackend
from controller_harness_contract import MAX_CUMULATIVE_INPUT_TOKENS, MAX_CUMULATIVE_OUTPUT_TOKENS
from glm_canary import MODEL, cost
from market_rsi import canonical, digest, file_hash, fresh_json, load_json
from paid_budget import PaidBudget, money
from controller_design import ALLOWED_TOOLS, BASE_INSTRUCTIONS, DECISION, assess_activity, validate_workspace


def command_for_validation(*, broker_script, **kwargs):
    """Reuse isolation/runtime flags, changing exactly one MCP route value."""
    command = harness.codex_command(**kwargs, tool_mode='canary', controller_stage='grid_learning')
    prefix = 'mcp_servers.controller_tools.args='
    positions = [i for i, value in enumerate(command) if value.startswith(prefix)]
    if len(positions) != 1:
        raise ValueError('exactly one existing MCP route required')
    index = positions[0]
    previous = json.loads(command[index][len(prefix):])
    expected = [str(Path(harness.__file__).with_name('historical_grid_learning_controller.py')),
                '--workspace', str(kwargs['workspace'])]
    if previous != expected:
        raise ValueError('legacy MCP template changed; do not silently route')
    command[index] = prefix + json.dumps([str(broker_script), '--workspace', str(kwargs['workspace'])])
    return command


def preflight(prepared, budget_path, canary_path, codex_canary_path):
    preparation = load_json(prepared / 'preparation.json')
    if preparation.get('purpose') != 'controller_design':
        raise ValueError('a canary workspace cannot become a paid controller lineage')
    if (prepared / 'dispatch-claim.json').exists() or (prepared / 'session').exists():
        raise ValueError('permanent session already claimed; no reuse')
    ws = prepared / 'workspace'
    if file_hash(ws / 'workspace.json') != preparation['workspace_sha256']:
        raise ValueError('workspace preparation changed')
    manifest = validate_workspace(ws)
    if manifest['session_id'] != prepared.name:
        raise ValueError('session ID differs from permanent workspace')
    if (ws / DECISION).exists():
        raise ValueError('workspace already has a decision')
    sources = preparation['source_hashes']
    for name, expected in sources.items():
        if (file_hash(prepared / 'source-snapshot' / name) != expected
                or file_hash(Path(__file__).resolve().parents[1] / name) != expected):
            raise ValueError('frozen stage source changed')
    required = 'validation_tools/run_validation_design.py'
    if sources.get(required) != file_hash(Path(__file__)):
        raise ValueError('running validation dispatcher not in exact source freeze')
    canary = load_json(canary_path)
    old_preparation = load_json(canary_path.parent / 'preparation.json')
    if (canary.get('passed') is not True or canary.get('real_stdio_child') is not True
            or canary.get('new_controller_calls') != 0
            or canary['context_sha256'] != preparation['context_sha256']
            or canary['source_preparation_sha256'] != file_hash(canary_path.parent / 'preparation.json')
            or old_preparation['source_hashes'] != sources
            or canary['result_sha256'] != digest({k: v for k, v in canary.items() if k != 'result_sha256'})):
        raise ValueError('exact same-source unpaid transport canary required')
    full_canary = load_json(codex_canary_path)
    full_preparation = load_json(codex_canary_path.parent / 'preparation.json')
    if (full_canary.get('schema') != 'historical_validation_codex_fixture_canary_v1'
            or full_canary.get('passed') is not True
            or full_canary.get('actual_codex_cli') is not True
            or full_canary.get('actual_tinker_calls') != 0
            or full_canary.get('source_hashes') != sources
            or full_canary.get('context_sha256') != preparation['context_sha256']
            or full_preparation.get('source_hashes') != sources
            or full_preparation.get('purpose') != 'transport_canary'
            or full_canary.get('source_preparation_sha256') != file_hash(codex_canary_path.parent / 'preparation.json')
            or full_canary.get('assessment_sha256') != file_hash(codex_canary_path.parent / 'session/assessment.json')
            or full_canary.get('fixture_claim_sha256') != file_hash(codex_canary_path.parent / 'fixture-only-claim.json')
            or full_canary.get('codex_cli_sha256') != file_hash(harness.CODEX)
            or full_canary.get('python_sha256') != file_hash(Path(sys.executable))
            or full_canary.get('result_sha256') != digest({k: v for k, v in full_canary.items() if k != 'result_sha256'})):
        raise ValueError('exact same-source/runtime real Codex fixture canary required')
    assessment = load_json(codex_canary_path.parent / 'session/assessment.json')
    if (assessment.get('valid') is not True or assessment.get('evidence_mode') != 'synthetic_transport_fixture'
            or assessment.get('model_authorship_proven') is not False
            or assessment.get('process_reaped') is not True or assessment.get('turns') != 2
            or assessment.get('tool_calls') != 4):
        raise ValueError('real Codex fixture assessment does not prove the intended transport')
    context = load_json(ws / 'context.json')
    budget = PaidBudget(budget_path)
    snapshot = budget.snapshot()
    if (snapshot['experiment_id'] != context['experiment_id']
            or money(snapshot['cap_usd']) != money(context['budget_cap_usd'])
            or file_hash(budget_path / 'authorization.json') != context['budget_authorization_sha256']):
        raise ValueError('existing budget authorization changed')
    if any(job['state'] == 'dispatched' and '-turn-' in job_id for job_id, job in snapshot['jobs'].items()):
        raise ValueError('another or unresolved controller turn exists')
    upper = cost(MAX_CUMULATIVE_INPUT_TOKENS, MAX_CUMULATIVE_OUTPUT_TOKENS)
    if min(money(snapshot['available_usd']), money(snapshot['buckets']['learning']['available_usd'])) < upper:
        raise ValueError('whole controller upper does not fit remaining learning allocation')
    return {'controller_stage': 'validation_design', 'model': MODEL,
            'session_id': prepared.name, 'context_sha256': context['context_sha256'],
            'source_preparation_sha256': file_hash(prepared / 'preparation.json'),
            'same_source_canary_sha256': file_hash(canary_path),
            'codex_fixture_canary_sha256': file_hash(codex_canary_path),
            'budget_authorization_sha256': context['budget_authorization_sha256'],
            'budget_bucket': 'learning', 'controller_worst_case_usd': str(upper),
            'budget_snapshot_not_spend': {k: v for k, v in snapshot.items() if k != 'jobs'},
            'new_test_admitted': False, 'new_download_admitted': False}


def run_session(*, prepared, backend, budget, prompt, evidence_mode):
    """Shared transport. Tests use explicit fixture mode and a separate fake ledger."""
    if evidence_mode not in ('paid_controller', 'synthetic_transport_fixture'):
        raise ValueError('explicit execution evidence mode required')
    if evidence_mode == 'paid_controller' and type(backend) is not TinkerGLMBackend:
        raise ValueError('paid authorship requires exact pinned Tinker backend')
    ws = prepared / 'workspace'; output = prepared / 'session'
    manifest = validate_workspace(ws)
    if evidence_mode == 'synthetic_transport_fixture':
        if manifest['purpose'] != 'transport_canary' or not budget.snapshot()['experiment_id'].startswith('fixture-'):
            raise ValueError('synthetic transport requires an isolated fixture workspace and fixture ledger')
    elif manifest['purpose'] != 'controller_design' or not (prepared / 'dispatch-claim.json').is_file():
        raise ValueError('paid controller requires prior permanent preflight claim')
    session = ControllerSession(session_id=prepared.name, output=output, backend=backend,
        budget=budget, budget_bucket='learning', submit_tool='submit_validation_decision',
        allowed_tools=ALLOWED_TOOLS)
    catalog = output / 'model-catalog.json'; instructions = output / 'model-instructions.md'
    fresh_json(catalog, model_catalog(BASE_INSTRUCTIONS))
    # Generated runtime artifact, not a scientific source edit.
    with instructions.open('x', encoding='utf-8') as stream:
        stream.write(BASE_INSTRUCTIONS)
    bearer = secrets.token_urlsafe(32)
    server = harness.ThreadingHTTPServer(('127.0.0.1', 0),
        harness.make_handler(session, bearer, model_catalog(BASE_INSTRUCTIONS)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    transport = None
    try:
        answer = output / 'last-message.txt'
        command = command_for_validation(workspace=ws, answer=answer,
            base_url=f'http://127.0.0.1:{server.server_address[1]}/v1', catalog=catalog,
            instructions=instructions, broker_script=prepared / 'source-snapshot/validation_tools/controller_design.py')
        fresh_json(output / 'command.json', {'args': command, 'controller_stage': 'validation_design'})
        runtime = harness.codex_harness_identity(catalog=catalog, instructions=instructions, command=command)
        fresh_json(output / 'harness-runtime.json', runtime)
        environment = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'HOME': os.environ.get('HOME', ''), 'TMPDIR': os.environ.get('TMPDIR', '/tmp'),
            'CODEX_GLM_LOOPBACK_KEY': bearer}
        transport = harness.run_process(command, prompt, environment, output)
        same_runtime = harness.codex_harness_identity(catalog=catalog, instructions=instructions, command=command) == runtime
        unresolved = harness.reconcile_unresolved_session_dispatches(
            session_id=prepared.name, budget=budget, output=output, transport=transport)
        try:
            activity = assess_activity(ws)
        except Exception as exc:
            activity = {'valid': False, 'error_type': type(exc).__name__}
        handshake_path = output / 'terminal-handshake.json'
        handshake = load_json(handshake_path) if handshake_path.is_file() else None
        final = answer.read_text() if answer.is_file() else ''
        valid = (transport['exit_code'] == 0 and transport['process_reaped'] and not session.failed
                 and same_runtime and activity['valid'] is True
                 and final.strip() == 'Controller decision submitted; session complete.'
                 and isinstance(handshake, dict) and handshake.get('provider_called') is False
                 and handshake.get('paid_turn_added') is False and (ws / DECISION).is_file())
        result = {**transport, 'schema': 'historical_validation_controller_assessment_v1',
                  'controller_stage': 'validation_design', 'evidence_mode': evidence_mode,
                  'model': MODEL, 'valid': bool(valid), 'turns': session.turns,
                  'tool_calls': session.tool_calls, 'activity': activity, 'failed': session.failed,
                  'unresolved_accounting': unresolved, 'harness_runtime_unchanged': same_runtime,
                  'terminal_handshake': handshake,
                  'model_authorship_proven': bool(valid and evidence_mode == 'paid_controller' and session.turns > 0),
                  'provider_budget': budget.snapshot(), 'new_test_admitted': False,
                  'new_download_admitted': False, 'new_model_fit': False}
        fresh_json(output / 'assessment.json', result)
        if not valid:
            raise RuntimeError('validation controller failed; preserve this permanent attempt')
        return result
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def main(args):
    prepared = args.prepared.resolve()
    lock_path = prepared.parent / 'historical-ingest-controller.lock'
    with lock_path.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        checked = preflight(prepared, args.budget.resolve(), args.canary.resolve(), args.codex_canary.resolve())
        fresh_json(prepared / 'dispatch-claim.json', {**checked, 'claimed_unix_ns': time.time_ns(),
                   'pid': os.getpid(), 'shared_lock_held': True, 'automatic_retry': False})
        # Only after all local gates and the permanent claim may credentials load.
        from dotenv import dotenv_values
        try:
            backend = TinkerGLMBackend(dotenv_values(args.env_file).get('TINKER_API_KEY'), args.tokenizer_cache)
        except Exception as exc:
            fresh_json(prepared / 'backend-initialization-failure.json', {'error_type': type(exc).__name__,
                'message_sha256': digest(str(exc)), 'automatic_retry': False, 'provider_sample_started': False})
            raise
        prompt = ('Continue from the already-selected frozen diagnostic. Inspect your validation context, '
                  'readiness and prior archive. Decide the next defensible independent-validation plan '
                  'or a concrete missing-data request and defer. Submit the first valid decision and exit. '
                  'No evaluator, acquisition permission, new labels or price rows are available in this stage.')
        result = run_session(prepared=prepared, backend=backend, budget=PaidBudget(args.budget),
                             prompt=prompt, evidence_mode='paid_controller')
        print(canonical({k: v for k, v in result.items() if k != 'provider_budget'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('prepared', 'budget', 'canary', 'codex-canary', 'env-file', 'tokenizer-cache'):
        parser.add_argument('--' + name, type=Path, required=True)
    main(parser.parse_args())
