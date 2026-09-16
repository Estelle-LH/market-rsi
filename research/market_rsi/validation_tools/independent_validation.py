"""Metadata-only admission checks for a frozen predictor's independent test.

Caller ownership matters: proposals may come from the controller; context,
proofs and budget are runner-owned. Never route controller arguments into those
trusted inputs. These checks do not open data, reserve money or execute a model.
Hash-bound proof files must be independently reviewed by the runner adapter.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_rsi import digest, identifier
from paid_budget import money


MINIMUM_FINAL_DAYS = 20
PROPOSAL_KEYS = {'proposal_id', 'context_sha256', 'source_contract_sha256',
                 'utc_dates', 'embargo_ms', 'minimum_coverage_fraction',
                 'minimum_market_groups_per_day', 'interval', 'reason'}
PROOF_KINDS = {'source_compatibility', 'exposure_history', 'whole_market_split',
               'coverage', 'causal_timestamps', 'full_population', 'cost_bound'}
SHA = re.compile(r'[0-9a-f]{64}')


def sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError('SHA-256 commitment required')
    return value


def dates(values):
    if not isinstance(values, list) or not values:
        raise ValueError('nonempty ordered UTC dates required')
    if any(not isinstance(v, str) or date.fromisoformat(v).isoformat() != v for v in values):
        raise ValueError('ISO UTC dates required')
    if values != sorted(set(values)):
        raise ValueError('UTC dates must be unique and sorted')
    return values


def positive_int(value, label, *, allow_zero=False):
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise ValueError(label + ' requires a bounded nonnegative/positive integer')
    return value


def fraction(value, label, *, allow_one=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(label + ' must be a finite fraction')
    number = Decimal(str(value))
    if not number.is_finite() or number <= 0 or (number > 1 if allow_one else number >= 1):
        raise ValueError(label + ' must be a finite fraction')
    return number


def verify_context(context):
    if context.get('schema') != 'historical_independent_validation_context_v1':
        raise ValueError('frozen runner context required')
    body = {k: v for k, v in context.items() if k != 'context_sha256'}
    if sha(context.get('context_sha256')) != digest(body):
        raise ValueError('frozen context commitment changed')
    for name in ('model_sha256', 'selected_plan_sha256', 'objective_sha256',
                 'source_contract_sha256', 'budget_authorization_sha256'):
        sha(context.get(name))
    money(context['budget_cap_usd'])
    positive_int(context['minimum_final_utc_days'], 'minimum final days')
    if (context['minimum_final_utc_days'] < MINIMUM_FINAL_DAYS
            or context['allow_refit'] is not False
            or context['allow_target_or_feature_change'] is not False
            or context['claim_scope'] != 'prediction_only_not_pnl_or_rsi'):
        raise ValueError('frozen predictor or validation boundary changed')
    dates(context['known_opened_dates_lower_bound'])
    return context


def validate_proposal(proposal, context):
    """Valid syntax/frozen-policy references are NOT permission to open labels."""
    verify_context(context)
    if not isinstance(proposal, dict) or set(proposal) != PROPOSAL_KEYS:
        raise ValueError('exact validation proposal fields required; no model/target edits')
    identifier(proposal['proposal_id'])
    if (proposal['context_sha256'] != context['context_sha256']
            or proposal['source_contract_sha256'] != context['source_contract_sha256']):
        raise ValueError('proposal changes frozen context/source; separate data-stage study required')
    selected = dates(proposal['utc_dates'])
    if len(selected) < context['minimum_final_utc_days']:
        raise ValueError('at least 20 distinct untouched final UTC sessions required')
    if selected[0] <= max(context['known_opened_dates_lower_bound']):
        raise ValueError('final dates must follow all known opened dates')
    positive_int(proposal['embargo_ms'], 'embargo', allow_zero=True)
    fraction(proposal['minimum_coverage_fraction'], 'coverage')
    positive_int(proposal['minimum_market_groups_per_day'], 'market groups')
    interval = proposal['interval']
    if not isinstance(interval, dict) or set(interval) != {'unit', 'block_days', 'replicates', 'confidence'}:
        raise ValueError('complete date-block interval specification required')
    if interval['unit'] != 'utc_date':
        raise ValueError('row-independent intervals are not admissible')
    positive_int(interval['block_days'], 'block length')
    positive_int(interval['replicates'], 'replicates')
    if interval['block_days'] >= len(selected) or interval['replicates'] > 100000:
        raise ValueError('interval has no independent blocks or exceeds runner resource bound')
    fraction(interval['confidence'], 'confidence', allow_one=False)
    if not isinstance(proposal['reason'], str) or not proposal['reason'].strip():
        raise ValueError('controller rationale required')
    return {'proposal_sha256': digest(proposal), 'proposal_valid': True,
            'execution_admitted': False, 'dates_are_not_yet_admitted': True}


def check_runner_evidence(proposal, context, runner, budget):
    """Consume trusted metadata proof summaries; never controller self-attestation.

    This pure checker returns readiness, not a dispatch token. A later wrapper
    must reverify proof bytes, claim the cohort once, reserve the runner-derived
    upper bound and revalidate immediately before any actual label access.
    """
    checked = validate_proposal(proposal, context)
    blockers = []
    if runner.get('schema') != 'historical_validation_runner_evidence_v1':
        raise ValueError('runner evidence schema required')
    for key, expected in [('proposal_sha256', checked['proposal_sha256']),
                          ('context_sha256', context['context_sha256'])]:
        if runner.get(key) != expected:
            raise ValueError('runner proof bound to another proposal/context')
    for key in ('model_sha256', 'selected_plan_sha256', 'objective_sha256', 'source_contract_sha256'):
        if runner.get(key) != context[key]:
            raise ValueError('runner execution would change frozen ' + key)
    proofs = runner.get('reviewed_proof_hashes', {})
    if set(proofs) != PROOF_KINDS:
        blockers.append('independent_proof_set_incomplete')
    else:
        for value in proofs.values():
            sha(value)
    required_true = ('source_compatible', 'exposure_audit_complete', 'whole_market_isolation',
                     'causal_timestamps_verified', 'quiet_rows_retained', 'same_evaluation_population',
                     'policy_frozen_before_new_label_access', 'cohort_never_scored')
    for key in required_true:
        if runner.get(key) is not True:
            blockers.append(key + '_not_verified')
    for key in ('source_values_imputed', 'future_value_filter', 'new_labels_exposed_to_controller',
                'refit_requested'):
        if runner.get(key) is not False:
            blockers.append(key + '_not_false')
    sessions = runner.get('sessions', [])
    if not isinstance(sessions, list):
        raise ValueError('runner session list required')
    if [s.get('utc_date') for s in sessions] != proposal['utc_dates']:
        blockers.append('session_dates_not_exactly_frozen_population')
    previous_label = positive_int(runner.get('latest_learning_label_available_ms'), 'last learning label')
    opened_groups = runner.get('opened_market_groups')
    if not isinstance(opened_groups, list) or len(opened_groups) != len(set(opened_groups)):
        raise ValueError('runner-owned unique opened market groups required')
    for s in sessions:
        stamp = s.get('utc_date')
        dates([stamp])
        prefix = stamp + ':'
        if s.get('exposure_state') != 'verified_untouched':
            blockers.append(prefix + 'exposure_unknown_or_opened')
        if s.get('closed') is not True:
            blockers.append(prefix + 'session_not_closed')
        observed = s.get('coverage_fraction')
        if (isinstance(observed, bool) or not isinstance(observed, (int, float))
                or not Decimal(str(observed)).is_finite()
                or not 0 <= observed <= 1):
            raise ValueError('invalid observed session coverage')
        if observed < proposal['minimum_coverage_fraction']:
            blockers.append(prefix + 'insufficient_coverage')
        groups = s.get('market_groups')
        if not isinstance(groups, list) or len(groups) != len(set(groups)):
            raise ValueError('unique whole-market group IDs required')
        if len(groups) < proposal['minimum_market_groups_per_day']:
            blockers.append(prefix + 'insufficient_market_groups')
        if set(groups) & set(opened_groups):
            blockers.append(prefix + 'market_group_already_opened')
        first = positive_int(s.get('first_feature_available_ms'), 'first feature')
        day_start = int(datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc).timestamp() * 1000)
        if not day_start <= first < day_start + 86400000:
            raise ValueError('session date and feature clock disagree')
        if first <= previous_label + proposal['embargo_ms']:
            blockers.append(prefix + 'learning_label_embargo_overlap')
    if budget.get('experiment_id') != context['experiment_id']:
        raise ValueError('another experiment budget cannot fund validation')
    if (money(budget.get('cap_usd')) != money(context['budget_cap_usd'])
            or runner.get('budget_authorization_sha256') != context['budget_authorization_sha256']):
        raise ValueError('budget authorization or cap changed; no budget reset')
    total_available = money(budget.get('available_usd'))
    bucket_available = money(budget['buckets']['final']['available_usd'])
    upper = money(runner.get('runner_cost_upper_usd'))
    if upper > min(total_available, bucket_available):
        blockers.append('runner_upper_exceeds_available_final_budget')
    download = positive_int(runner.get('new_download_bytes_upper'), 'download upper', allow_zero=True)
    headroom = positive_int(runner.get('authorized_download_headroom_bytes'), 'download headroom', allow_zero=True)
    if download > headroom:
        blockers.append('new_download_not_authorized')
    if money(runner.get('vendor_purchase_usd')) != 0:
        blockers.append('separate_vendor_purchase_authority_required')
    return {**checked, 'metadata_gate_passed': not blockers, 'blockers': blockers,
            'execution_admitted': False, 'dispatch_token_created': False,
            'session_count': len(sessions), 'scientific_power_proven': False,
            'runner_cost_upper_usd': str(upper),
            'next_required': 'hash-reverified one-shot runner claim and budget reservation; no label access here'}
