"""Source-bound host effect review; no adoption, inference or claim of learning."""
from pathlib import Path
import re

from market_rsi import digest
from earnings_shadow_measurement import compare, FAMILIES, validate_criterion
from supervisor_harness import capacity_feedback_engine as engine

SCOPES = {
    'success_replay': 'Cold verification of retained successful originals, not new inference',
    'failure_feedback': 'Enumerated local tool denial and safe failure projection only',
    'restart': 'Cold local native/profile/state restoration, not provider restart',
    'historical_replay': 'Retained native journal and public-record prefix only',
    'protected_boundaries': 'Fixed identities and literal profile write scope, not OS containment',
    'rollback': 'Conditional pure child-to-parent rollback, not production rollback',
    'anchor_compatibility': 'Retained anchor files and mechanical interfaces, not accuracy',
    'bounded_trial': 'Original resources and two completed parent-owned trial claims',
}
FACTS = {
    'success_replay': {'originals_recomputed', 'tested_consumption'},
    'failure_feedback': {'tool_denied', 'feedback_safe'},
    'restart': {'cold_identity_equal', 'cold_state_equal'},
    'historical_replay': {'journal_equal', 'prior_records_preserved'},
    'protected_boundaries': {'fixed_context', 'single_axis', 'actual_write_scope'},
    'rollback': {'conditional_projection', 'parent_restored', 'real_state_unchanged'},
    'anchor_compatibility': {'anchor_files_verified', 'interfaces_compatible'},
    'bounded_trial': {'original_resources', 'completed_claims', 'declared_slots'},
}


def effect_criterion(effect, component):
    """Parse the original prospective effect, never retrofit a broad hypothesis."""
    if type(effect) is not str:
        raise ValueError('Exact prospective operational effect required')
    parts = effect.split('|')
    if len(parts) == 7 and parts[0] == 'earnings-shadow-v2':
        thresholds = {str(n / 2).removesuffix('.0') for n in range(1, 11)}
        if (type(component) is not str or parts[1] != component or component not in FAMILIES
                or parts[2:4] != ['score_out_of_5', 'higher'] or parts[4] not in thresholds
                or parts[5:] != ['score_nonregression', 'matched_trial_only']):
            raise ValueError('Exact original-score prediction effect required')
        return validate_criterion({'schema':'earnings_shadow_criterion_v2','component':component,
            'metric':parts[2],'direction':parts[3],'min_delta':float(parts[4])})
    if (len(parts) != 7 or parts[0] != 'earnings-shadow-v1'
            or parts[1] != component or component not in FAMILIES
            or parts[2] not in FAMILIES[component] or parts[3] not in {'lower', 'higher'}
            or not re.fullmatch(r'[1-9][0-9]{0,8}', parts[4])
            or parts[5:] != ['score_nonregression', 'matched_trial_only']):
        raise ValueError('Unsupported effect semantics; no inferred equivalence')
    return {'schema': 'earnings_shadow_criterion_v1', 'component': component,
            'metric': parts[2], 'direction': parts[3], 'min_delta': int(parts[4])}


def review(capacity, comparison_binding, *, registration_binding, probe, output_root):
    """Consume trusted host probe observations; Root separately owns adoption.

    The registration and callback are host-controlled, not model input. Source
    pins and retained facts are not cryptographic attestation of execution.
    Missing/negative checks reject; malformed or changed originals fail closed.
    """
    before = capacity.batch.snapshot()
    micro, pending = before['micro_evolution'], before['micro_evolution']['pending']
    if pending is None or before['active_attempt_ids']:
        raise ValueError('Fresh idle pending candidate required')
    parent = capacity._selected(before)['manifest']
    child = capacity._version(pending['pair'])['manifest']
    bound = {'proposal_sha256': pending['record_sha256'],
        'before_identity_sha256': digest(parent), 'after_identity_sha256': digest(child),
        'tested_pair_sha256': digest(pending['pair']), 'anchor_pair_sha256': digest(micro['anchor_pair'])}
    registration = engine.read(registration_binding)
    if (type(registration) is not dict or set(registration) != {
            'schema', 'reviewer_id', 'proposer_id', 'review_source', 'probe_source', 'scopes'}
            or registration['schema'] != 'earnings_effect_review_registration_v1'
            or registration['reviewer_id'] != micro['reviewer_id']
            or registration['proposer_id'] != pending['proposer_id']
            or registration['reviewer_id'] == registration['proposer_id']
            or registration['review_source'] != engine.source_of(review)
            or not callable(probe) or registration['probe_source'] != engine.source_of(probe)
            or registration['scopes'] != SCOPES):
        raise ValueError('Exact independent host review/probe registration required')
    measured = engine.read(comparison_binding)
    recomputed = compare(measured['originals']['parent'], measured['originals']['child'],
                         declaration=measured['declaration'])
    if any(measured.get(k) != value for k, value in recomputed.items()):
        raise ValueError('Retained comparison differs from recomputed originals')
    consumption = measured['originals']['child']['consumed']
    claim = engine.read(measured['trial_claim'])
    if (consumption['pending_proposal_sha256'] != pending['record_sha256']
            or consumption['active_pair_sha256'] != digest(micro['active_pair'])
            or consumption['tested_pair_sha256'] != bound['tested_pair_sha256']
            or any(claim.get(k) != bound[k] for k in ('before_identity_sha256', 'after_identity_sha256', 'tested_pair_sha256'))
            or digest(engine.read(claim['criterion'])) != digest(measured['declaration'])):
        raise ValueError('Matched trial is not this exact pending candidate')
    root = Path(output_root)
    episode_root = Path(claim['episode']['root'])
    if (not root.is_absolute() or root.resolve() != root
            or not root.is_relative_to(episode_root/'effects') or root.exists()):
        raise ValueError('New canonical episode effect-review root required')
    root.mkdir(parents=True, exist_ok=False)
    engine.save(root/'registration.json', registration)
    reason, passed, evidence = 'UNKNOWN_EFFECT_SEMANTICS', {}, {}
    try:
        criterion = effect_criterion(pending['behavior_change'], pending['component'])
    except ValueError:
        criterion = None
    if criterion is not None and digest(criterion) != digest(measured['declaration']):
        raise ValueError('Predeclared criterion differs from original effect')
    if criterion is not None:
        proof_binding = probe(capacity, comparison_binding, root/'probes')
        proof = engine.read(proof_binding)
        engine.driver._artifacts(proof)
        if (type(proof) is not dict or set(proof) != {
                'schema', 'binding', 'scopes', 'observations', 'sources', 'native_state_sha256'}
                or proof['schema'] != 'earnings_mechanical_checks_v1' or proof['binding'] != bound
                or proof['scopes'] != SCOPES or proof['native_state_sha256'] != before['state_sha256']
                or proof['sources'].get('producer') != engine.source_of(probe)
                or not set(proof['observations']).issubset(FACTS)):
            raise ValueError('Mechanical checks lack exact candidate/source/state binding')
        for name, observation in proof['observations'].items():
            if (type(observation) is not dict or set(observation) != {'facts', 'artifacts'}
                    or type(observation['facts']) is not dict or set(observation['facts']) != FACTS[name]
                    or any(type(value) is not bool for value in observation['facts'].values())
                    or type(observation['artifacts']) is not list or not observation['artifacts']):
                raise ValueError('Exact observed mechanical facts and originals required')
            engine.driver._artifacts(observation)
            passed[name] = all(observation['facts'].values())
        reason = 'MECHANICAL_CHECKS_INCOMPLETE_OR_FAILED'
        if set(passed) == set(FACTS) and all(passed.values()):
            success = ('MATCHED_PREDICTION_BENEFIT' if criterion['schema'] == 'earnings_shadow_criterion_v2'
                       else 'MATCHED_OPERATIONAL_BENEFIT')
            reason = success if measured['benefit_observed'] else 'NO_MATCHED_BENEFIT'
        checks = engine.save(root/'checks.json', {'binding': bound, 'checks': passed,
            'scopes': SCOPES, 'comparison': comparison_binding, 'observations': proof_binding})
        evidence[checks['sha256']] = checks['path']
    accepted = reason in {'MATCHED_OPERATIONAL_BENEFIT', 'MATCHED_PREDICTION_BENEFIT'}
    benefit = None
    if accepted:
        benefit = engine.save(root/'benefit.json', dict(bound,
            matched_outputs_sha256=checks['sha256'], effect=pending['behavior_change'],
            benefit_observed=measured['benefit_observed']))
        evidence[benefit['sha256']] = benefit['path']
    if capacity.batch.snapshot() != before:
        raise ValueError('Effect reviewer must not mutate native owner or selection')
    return engine.save(root/'review.json', {'review': {
        'reviewer_id': micro['reviewer_id'], 'proposal_sha256': pending['record_sha256'],
        'decision': 'accept' if accepted else 'reject', 'reason': reason,
        'tested_pair_sha256': bound['tested_pair_sha256'], 'anchor_pair_sha256': bound['anchor_pair_sha256'],
        'checks': {name: {'passed': value, 'evidence_sha256': checks['sha256']} for name, value in passed.items()},
        'benefit_observed': accepted, 'benefit_evidence_sha256': None if benefit is None else benefit['sha256'],
        'actual_write_paths': pending['write_paths']}, 'evidence': evidence})
