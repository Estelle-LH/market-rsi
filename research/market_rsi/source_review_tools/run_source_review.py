"""Source-review stage using the existing frozen Codex/GLM transport and budget.

Only the MCP route/manifest and stage tools/instructions change. This dispatcher
does not acquire market data or turn a source proposal into spending authority.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'validation_tools')]
import run_codex_glm_controller as harness
from codex_glm_model_catalog import model_catalog
from codex_glm_provider import ControllerSession, TinkerGLMBackend
from controller_harness_contract import MAX_CUMULATIVE_INPUT_TOKENS, MAX_CUMULATIVE_OUTPUT_TOKENS
from glm_canary import MODEL, cost
from market_rsi import canonical, digest, file_hash, fresh_json, load_json
from paid_budget import PaidBudget, money
import controller_source_review as review
from run_validation_design import command_for_validation


def command_for_source_review(*, manifest_sha256, broker_script, **kwargs):
    # Reuse its verified change of only the existing MCP route, then add the
    # runner-owned immutable workspace commitment required by this broker.
    command = command_for_validation(broker_script=broker_script, **kwargs)
    prefix = 'mcp_servers.controller_tools.args='
    positions = [i for i,v in enumerate(command) if v.startswith(prefix)]
    if len(positions) != 1: raise ValueError('exactly one source-review MCP route required')
    i = positions[0]; previous = json.loads(command[i][len(prefix):])
    if previous != [str(broker_script), '--workspace', str(kwargs['workspace'])]:
        raise ValueError('source-review command template changed')
    if len(manifest_sha256) != 64 or any(c not in '0123456789abcdef' for c in manifest_sha256):
        raise ValueError('exact runner manifest hash required')
    command[i] = prefix + json.dumps(previous + ['--manifest-sha256', manifest_sha256])
    return command


def verify_preparation(prepared):
    prep = load_json(prepared / 'preparation.json')
    if prep.get('schema') != 'historical_source_review_preparation_v1':
        raise ValueError('source-review preparation required')
    manifest, visible = review.validate_workspace(prepared / 'workspace', prep['workspace_sha256'])
    if manifest['session_id'] != prepared.name or manifest['purpose'] != prep['purpose']:
        raise ValueError('permanent session ID/purpose mismatch')
    for name, expected in prep['source_hashes'].items():
        if file_hash(ROOT / name) != expected or file_hash(prepared / 'source-snapshot' / name) != expected:
            raise ValueError('frozen source-review stage changed')
    if prep['source_hashes'].get('source_review_tools/run_source_review.py') != file_hash(Path(__file__)):
        raise ValueError('running dispatcher not in source freeze')
    for path, expected in prep['inputs'].items():
        if file_hash(Path(path)) != expected: raise ValueError('review input evidence changed')
    return prep, manifest, visible


def verify_canaries(prep, canary_path, codex_canary_path):
    sources = prep['source_hashes']; context = prep['context_sha256']
    canary = load_json(canary_path); cp = load_json(canary_path.parent / 'preparation.json')
    if (canary.get('schema') != 'historical_source_review_stdio_canary_v1'
            or canary.get('passed') is not True or canary.get('actual_stdio_child') is not True
            or canary.get('new_model_calls') != 0 or canary.get('new_public_metadata_calls') != 0
            or canary.get('context_sha256') != context or cp['source_hashes'] != sources
            or cp['purpose'] != 'transport_canary'
            or canary['preparation_sha256'] != file_hash(canary_path.parent / 'preparation.json')
            or canary['result_sha256'] != digest({k:v for k,v in canary.items() if k != 'result_sha256'})):
        raise ValueError('same-source metadata-only STDIO canary required')
    full = load_json(codex_canary_path); fp = load_json(codex_canary_path.parent / 'preparation.json')
    if (full.get('schema') != 'historical_source_review_codex_fixture_canary_v1'
            or full.get('passed') is not True or full.get('actual_codex_cli') is not True
            or full.get('actual_tinker_calls') != 0 or full.get('source_hashes') != sources
            or full.get('context_sha256') != context or fp['source_hashes'] != sources
            or fp['purpose'] != 'transport_canary'
            or full['preparation_sha256'] != file_hash(codex_canary_path.parent / 'preparation.json')
            or full['assessment_sha256'] != file_hash(codex_canary_path.parent / 'session/assessment.json')
            or full['fixture_claim_sha256'] != file_hash(codex_canary_path.parent / 'fixture-only-claim.json')
            or full['codex_cli_sha256'] != file_hash(harness.CODEX)
            or full['python_sha256'] != file_hash(Path(sys.executable))
            or full['result_sha256'] != digest({k:v for k,v in full.items() if k != 'result_sha256'})):
        raise ValueError('same-source/runtime actual Codex fixture required')
    a = load_json(codex_canary_path.parent / 'session/assessment.json')
    if (a.get('valid') is not True or a.get('evidence_mode') != 'synthetic_transport_fixture'
            or a.get('model_authorship_proven') is not False or a.get('process_reaped') is not True
            or a.get('turns') != 2 or a.get('tool_calls') != 4):
        raise ValueError('fixture must prove two samples, four tools and exact cleanup')


def preflight(prepared, budget_path, canary_path, codex_canary_path):
    if (prepared / 'dispatch-claim.json').exists() or (prepared / 'session').exists():
        raise ValueError('permanent session already claimed; no reuse')
    prep, manifest, visible = verify_preparation(prepared)
    if manifest['purpose'] != 'source_review': raise ValueError('canary cannot become a paid lineage')
    ws = prepared / 'workspace'
    if ((ws / review.DECISION).exists() or (ws / review.LOG).exists()
            or any(list((ws / kind).iterdir()) for kind in ('plans', 'metadata-requests', 'public-metadata'))):
        raise ValueError('paid workspace must be unconsumed')
    verify_canaries(prep, canary_path, codex_canary_path)
    context = visible['context.json']; b = PaidBudget(budget_path).snapshot()
    if (b['experiment_id'] != context['experiment_id'] or money(b['cap_usd']) != money(context['budget_cap_usd'])
            or file_hash(budget_path / 'authorization.json') != context['budget_authorization_sha256']):
        raise ValueError('original budget authorization changed')
    if any(v['state'] == 'dispatched' and '-turn-' in k for k,v in b['jobs'].items()):
        raise ValueError('another or unresolved model turn exists')
    upper = cost(MAX_CUMULATIVE_INPUT_TOKENS, MAX_CUMULATIVE_OUTPUT_TOKENS)
    if min(money(b['available_usd']), money(b['buckets']['learning']['available_usd'])) < upper:
        raise ValueError('whole controller upper exceeds available learning budget')
    return {'controller_stage': 'source_review', 'model': MODEL, 'session_id': prepared.name,
        'context_sha256': context['context_sha256'], 'preparation_sha256': file_hash(prepared / 'preparation.json'),
        'stdio_canary_sha256': file_hash(canary_path), 'codex_canary_sha256': file_hash(codex_canary_path),
        'budget_authorization_sha256': context['budget_authorization_sha256'], 'budget_bucket': 'learning',
        'controller_worst_case_usd_not_spend': str(upper),
        'budget_snapshot_not_spend': {k:v for k,v in b.items() if k != 'jobs'},
        'new_raw_download_admitted': False, 'new_test_admitted': False}


def run_session(*, prepared, backend, budget, prompt, evidence_mode):
    if evidence_mode not in ('paid_controller', 'synthetic_transport_fixture'):
        raise ValueError('explicit evidence mode required')
    if evidence_mode == 'paid_controller' and type(backend) is not TinkerGLMBackend:
        raise ValueError('paid authorship requires exact pinned Tinker backend')
    prep, manifest, _ = verify_preparation(prepared)
    if evidence_mode == 'synthetic_transport_fixture':
        if manifest['purpose'] != 'transport_canary' or not budget.snapshot()['experiment_id'].startswith('fixture-'):
            raise ValueError('fixture requires separate canary workspace and fixture ledger')
    elif manifest['purpose'] != 'source_review' or not (prepared / 'dispatch-claim.json').is_file():
        raise ValueError('paid source review requires permanent preflight claim')
    ws = prepared / 'workspace'; output = prepared / 'session'
    session = ControllerSession(session_id=prepared.name, output=output, backend=backend, budget=budget,
        budget_bucket='learning', submit_tool='submit_source_review_decision', allowed_tools=review.ALLOWED_TOOLS)
    catalog = output / 'model-catalog.json'; instructions = output / 'model-instructions.md'
    fresh_json(catalog, model_catalog(review.INSTRUCTIONS))
    with instructions.open('x', encoding='utf-8') as stream: stream.write(review.INSTRUCTIONS)
    bearer = secrets.token_urlsafe(32)
    server = harness.ThreadingHTTPServer(('127.0.0.1', 0),
        harness.make_handler(session, bearer, model_catalog(review.INSTRUCTIONS)))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        answer = output / 'last-message.txt'
        command = command_for_source_review(workspace=ws, answer=answer,
            base_url=f'http://127.0.0.1:{server.server_address[1]}/v1', catalog=catalog,
            instructions=instructions, manifest_sha256=prep['workspace_sha256'],
            broker_script=prepared / 'source-snapshot/source_review_tools/controller_source_review.py')
        fresh_json(output / 'command.json', {'args': command, 'controller_stage': 'source_review'})
        runtime = harness.codex_harness_identity(catalog=catalog, instructions=instructions, command=command)
        fresh_json(output / 'harness-runtime.json', runtime)
        environment = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': os.environ.get('HOME', ''),
            'TMPDIR': os.environ.get('TMPDIR', '/tmp'), 'CODEX_GLM_LOOPBACK_KEY': bearer}
        transport = harness.run_process(command, prompt, environment, output)
        same_runtime = harness.codex_harness_identity(catalog=catalog, instructions=instructions, command=command) == runtime
        unresolved = harness.reconcile_unresolved_session_dispatches(
            session_id=prepared.name, budget=budget, output=output, transport=transport)
        try: activity = review.assess_activity(ws, prep['workspace_sha256'])
        except Exception as error: activity = {'valid': False, 'error_type': type(error).__name__}
        handshake = load_json(output / 'terminal-handshake.json') if (output / 'terminal-handshake.json').is_file() else None
        final = answer.read_text() if answer.is_file() else ''
        valid = (transport['exit_code'] == 0 and transport['process_reaped'] and not session.failed
            and same_runtime and activity['valid'] is True and final.strip() == 'Controller decision submitted; session complete.'
            and isinstance(handshake, dict) and handshake.get('provider_called') is False
            and handshake.get('paid_turn_added') is False and (ws / review.DECISION).is_file())
        result = {**transport, 'schema': 'historical_source_review_controller_assessment_v1',
            'controller_stage': 'source_review', 'evidence_mode': evidence_mode, 'model': MODEL,
            'valid': bool(valid), 'turns': session.turns, 'tool_calls': session.tool_calls, 'activity': activity,
            'failed': session.failed, 'unresolved_accounting': unresolved, 'harness_runtime_unchanged': same_runtime,
            'terminal_handshake': handshake, 'model_authorship_proven': bool(valid and evidence_mode == 'paid_controller'),
            'provider_budget': budget.snapshot(), 'new_test_admitted': False,
            'new_raw_download_admitted': False, 'new_model_fit': False}
        fresh_json(output / 'assessment.json', result)
        if not valid: raise RuntimeError('source-review controller failed; preserve permanent attempt')
        return result
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def main(args):
    prepared = args.prepared.resolve()
    with (prepared.parent / 'historical-ingest-controller.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        checked = preflight(prepared, args.budget.resolve(), args.canary.resolve(), args.codex_canary.resolve())
        fresh_json(prepared / 'dispatch-claim.json', {**checked, 'claimed_unix_ns': time.time_ns(),
            'nonce': secrets.token_hex(16), 'pid': os.getpid(), 'shared_lock_held': True, 'automatic_retry': False})
        from dotenv import dotenv_values
        try: backend = TinkerGLMBackend(dotenv_values(args.env_file).get('TINKER_API_KEY'), args.tokenizer_cache)
        except Exception as error:
            fresh_json(prepared / 'backend-initialization-failure.json', {'error_type': type(error).__name__,
                'message_sha256': digest(str(error)), 'automatic_retry': False, 'provider_sample_started': False})
            raise
        prompt = ('Review the updated source evidence and all prior open research. The old requested source '
            'has no executable later-date inventory. Use the new metadata-only tools to choose a defensible '
            'source/field study with exact advertised required files, or request missing public metadata. '
            'Do not choose from financial outcomes, modify t7, or equate a proposal with download permission. '
            'Submit the first valid source-review decision and exit. Current raw-download headroom is zero.')
        result = run_session(prepared=prepared, backend=backend, budget=PaidBudget(args.budget),
                             prompt=prompt, evidence_mode='paid_controller')
        print(canonical({k:v for k,v in result.items() if k != 'provider_budget'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('prepared', 'budget', 'canary', 'codex-canary', 'env-file', 'tokenizer-cache'):
        parser.add_argument('--' + name, type=Path, required=True)
    main(parser.parse_args())
