"""Explicit new-ID PUBLIC proposal import; never a manufactured model stage.

The recovery loader authenticates the original closed owner and physical raw.
This adapter revalidates that decision against the new active pool, names the
feedback rebind, and leaves Author/tests/Review/forecast entirely live.
"""
from copy import deepcopy
from pathlib import Path

from earnings_population_roles import decode_proposal
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine

MODE = 'received_completed_controller_proposal_v1'
SOURCE = 'tools/earnings_population_controller_delivery.py'


def _bundle(origin):
    value = origin.get('controller_stage_import')
    if value is None:
        return None
    if (value.get('schema') != 'earnings_population_controller_proposal_import_v1'
            or value.get('mode') != MODE or value.get('new_model_called') is not False
            or origin.get('author_stage_reuse') is not None):
        raise ValueError('Distinct authenticated public Controller proposal import required')
    return value


def selected(bundle, packet, prompt, *, read=engine.read):
    """Revalidate old public science under current pool; rebind only feedback."""
    if (packet.get('round_index') != 1 or prompt['feedback_sha256'] != packet['parent_feedback_sha256']
            or packet['parent_feedback_sha256'] != digest(packet['feedback'])
            or prompt['active_versions'] != [packet['population']['stable_id'], *packet['population']['explorers']]
            or prompt['explorers'] != packet['population']['explorers']):
        raise ValueError('Exact fresh first-round pool/feedback required for proposal import')
    raw = read(bundle['raw_response'])
    original_prompt = read(bundle['original_prompt'])
    old_hash = bundle['original_feedback_sha256']
    original = decode_proposal(raw, original_prompt)
    if (original_prompt['feedback_sha256'] != old_hash or original != bundle['original_decision_public']
            or original['feedback_sha256'] != old_hash):
        raise ValueError('Original public proposal or original feedback differs')
    current = decode_proposal(raw, dict(prompt, feedback_sha256=old_hash))
    if current != original:
        raise ValueError('Public proposal scientific fields cannot change during import')
    current['feedback_sha256'] = packet['parent_feedback_sha256']
    return current


def route(runtime, campaign_context, prompt, packet, slot):
    if campaign_context is None:
        return None
    study = engine.read(runtime['forecast_study'])
    origin = engine.read(study['campaign_origin'])
    bundle = _bundle(origin)
    if bundle is None or packet['round_index'] != 1:
        return None
    resumed = engine.read(study['campaign_resume'])
    if (resumed.get('controller_import_mode') != MODE or Path(slot).name != 'controller-01'
            or str(slot) not in runtime['slots']['controller']
            or resumed.get('prior_failed_attempt') != bundle['failed_attempt']):
        raise ValueError('Admitted fresh first Controller slot and typed import manifest required')
    chosen = selected(bundle, packet, prompt)
    packet_bound = engine.pin(Path(slot).parent.parent/'packet-01.json')
    if engine.read(packet_bound) != packet:
        raise ValueError('Actual new input packet differs before Controller import')
    Path(slot).mkdir(parents=True, exist_ok=False)
    routed = engine.save(Path(slot)/'population-decision.json', chosen)
    engine.save(Path(slot)/'controller-proposal-import.json', dict(
        schema='earnings_population_trusted_controller_proposal_import_v1', mode=MODE,
        routing_author='trusted_controller_proposal_import', new_model_called=False,
        original_raw=bundle['raw_response'], original_prompt=bundle['original_prompt'],
        source_attempt=bundle['failed_attempt'], original_runtime=bundle['runtime'],
        settlement=bundle['settlement'], original_feedback_sha256=bundle['original_feedback_sha256'],
        new_feedback_sha256=packet['parent_feedback_sha256'], decision=routed, packet=packet_bound,
        source=runtime['sources'][SOURCE],
        decoder_source=runtime['sources']['tools/earnings_population_roles.py'],
        service_source=runtime['sources']['tools/earnings_population_services.py'],
        attribution='Original failed producer public Controller proposal only. Explicit trusted feedback rebind; no new Controller model call. New Author and financial evaluation remain mandatory.'))
    return routed


def verify(reader, attempt, rows, origin, runtime):
    bundle = _bundle(origin)
    if bundle is None:
        return
    packet_bound = rows['input']['packet']; packet = reader.read(packet_bound)
    original_prompt = reader.read(bundle['original_prompt'])
    prompt = deepcopy(original_prompt)
    prompt.update(active_versions=[packet['population']['stable_id'], *packet['population']['explorers']],
                  explorers=packet['population']['explorers'], feedback_sha256=digest(packet['feedback']))
    chosen = selected(bundle, packet, prompt, read=reader.read)
    c = attempt/'roles/controller-01'
    bound = rows['controller'].get('proposal_import')
    if (type(bound) is not dict or bound.get('path') != str(c/'controller-proposal-import.json')
            or rows['controller'].get('artifacts') != [rows['controller']['decision'],bound]):
        raise ValueError('Exact durably sealed Controller proposal-import binding required')
    receipt = reader.read(bound)
    expected = dict(schema='earnings_population_trusted_controller_proposal_import_v1', mode=MODE,
        routing_author='trusted_controller_proposal_import', new_model_called=False,
        original_raw=bundle['raw_response'], original_prompt=bundle['original_prompt'],
        source_attempt=bundle['failed_attempt'], original_runtime=bundle['runtime'], settlement=bundle['settlement'],
        original_feedback_sha256=bundle['original_feedback_sha256'],
        new_feedback_sha256=packet['parent_feedback_sha256'], decision=rows['controller']['decision'], packet=packet_bound,
        source=runtime['sources'][SOURCE], decoder_source=runtime['sources']['tools/earnings_population_roles.py'],
        service_source=runtime['sources']['tools/earnings_population_services.py'],
        attribution='Original failed producer public Controller proposal only. Explicit trusted feedback rebind; no new Controller model call. New Author and financial evaluation remain mandatory.')
    if (receipt != expected or reader.read(rows['controller']['decision']) != chosen
            or any((c/name).exists() for name in ('result.json','response.json','decision.json','controller-stage-reuse.json'))
            or list(c.glob('http-*')) or list(c.glob('[0-9][0-9]-request.json'))):
        raise ValueError('Exact explicit imported Controller/no-new-model receipt differs')
