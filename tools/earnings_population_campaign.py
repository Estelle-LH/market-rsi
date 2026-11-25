"""Opt-in fixed-development-panel policy for the existing seven-stage owner.

This helper supplies no execution, admission, budget or scientific authority.
Runtime admission independently validates the actual frozen task contract.
Rejected/no-change decisions have no invented forecast score. Repeated panel
measurements are development records, never fresh-company observations.
"""
from copy import deepcopy
from pathlib import Path
import re

from earnings_entry import checked, strict_json
from earnings_population import _bindings, _sha, validate, validate_result
from market_rsi import digest
from supervisor_harness.feedback_linked_loop import _artifacts


PANEL = ['CIK0000017313']
VALIDATION_COMPANY = 'CIK0000021076'
SCOPE = ('Repeated fixed development panel; exposed data, not holdout or a '
         'new-company learning curve. Original scorer; no automatic promotion.')
FIELDS = {'schema', 'source_plan', 'panel', 'baseline_version_id', 'max_decisions',
          'initial_population_sha256', 'initial_feedback', 'last_scored_feedback',
          'contract', 'validation_company_id'}
PARENT_COMPARISON = 'chosen_parent_and_fixed_control'


def expected_arms(manifest, parent_id, candidate_id):
    """Keep the frozen control and separately measure a different actual parent."""
    result = [manifest['baseline_version_id']]
    if manifest.get('comparison_policy') == PARENT_COMPARISON and parent_id not in result:
        result.append(parent_id)
    return result + [candidate_id]


def _read(binding, *, recursive=True):
    _bindings([binding])
    value = strict_json(checked(binding))
    if type(value) is not dict:
        raise ValueError('Campaign binding must contain a JSON object')
    if recursive:
        _artifacts(value)
    return value


def _training_input(binding, name, *, directory=None):
    """Check the exact current-input namespace before reading its metadata."""
    from earnings_population_training25 import ROOT
    if (type(binding) is not dict or set(binding) != {'path','sha256'}
            or type(binding.get('path')) is not str
            or type(binding.get('sha256')) is not str
            or re.fullmatch('[0-9a-f]{64}',binding['sha256']) is None):
        raise ValueError('Exact training metadata binding required before read')
    path = Path(binding['path'])
    parent = path.parent if directory is None else directory
    if (parent.parent != ROOT/'inputs'
            or re.fullmatch('edgar-population-20261016-[0-9]{2}',parent.name) is None
            or path != parent/name or not path.is_absolute() or str(path) != binding['path']
            or path.resolve() != path or path.is_symlink() or not path.is_file()
            or path.stat().st_nlink != 1 or path.stat().st_size > 16_000_000):
        raise ValueError('Canonical owned training metadata required before read')
    return path.parent


def load(binding, initial, companies, max_rounds):
    """Validate opt-in structure/seed; admission owns real source/task authority."""
    # Dispatch needs only the exact top-level JSON, never recursive artifacts.
    # Known current-input entries can be namespace-checked before even that read.
    from earnings_population_training25 import ROOT, PLAN as training_plan
    from earnings_entry import REPO
    if (type(binding) is dict and type(binding.get('path')) is str
            and Path(binding['path']).is_relative_to(ROOT/'inputs')):
        _training_input(binding,'campaign.json')
    metadata = _read(binding,recursive=False)
    plan = metadata.get('source_plan')
    if ('training_state_link' in metadata or 'training_policy' in metadata
            or type(plan) is dict and plan.get('path') == str(REPO/training_plan)):
        return _training(binding,metadata,initial,companies,max_rounds)
    # The absent-policy branch retains its original validation/artifact checks.
    validate(initial)
    value = _read(binding)
    extra = set(value) & {'comparison_policy', 'initial_feedback_contract_sha256', 'last_scored_contract_sha256'}
    if (set(value) != FIELDS | extra or value.get('schema') != 'earnings_population_campaign_v1'
            or extra and value.get('comparison_policy') != PARENT_COMPARISON
            or value['panel'] != PANEL or type(value['max_decisions']) is not int
            or not 1 <= value['max_decisions'] <= 2
            or type(max_rounds) is not int or max_rounds != value['max_decisions']
            or companies != PANEL * max_rounds
            or value['validation_company_id'] != VALIDATION_COMPANY
            or type(value['baseline_version_id']) is not str
            or value['baseline_version_id'] not in initial['versions']
            or value['initial_population_sha256'] != digest(initial)
            or type(value['contract']) is not dict or not value['contract']):
        raise ValueError('Exact bounded fixed-panel campaign/initial identity required')
    plan = _read(value['source_plan'])
    if plan.get('schema') != 'supervisor_bottleneck_plan_v1':
        raise ValueError('Bound campaign source plan required')
    initial_feedback = _read(value['initial_feedback'])
    last_scored = _read(value['last_scored_feedback'])
    scored_contract = value.get('last_scored_contract_sha256')
    if 'last_scored_contract_sha256' in value:
        _sha(scored_contract)
        if last_scored.get('schema') != 'earnings_population_campaign_feedback_v1':
            raise ValueError('Historical contract requires an actual scored campaign ancestor')
    if (initial_feedback.get('schema') not in {
            'earnings_population_rejection_feedback_v1',
            'earnings_population_campaign_feedback_v1'}
            or initial_feedback.get('company_id') != PANEL[0]):
        raise ValueError('Exact typed prior campaign/rejection feedback required')
    if initial_feedback['schema'] == 'earnings_population_rejection_feedback_v1':
        if (initial_feedback.get('kind') != 'review_rejected'
                or initial_feedback.get('score_state') != 'unscored'
                or initial_feedback.get('last_scored_feedback') != value['last_scored_feedback']
                or 'results' in initial_feedback or 'points' in initial_feedback):
            raise ValueError('Prior rejection is unscored and separate from prior score')
    else:
        historical_contract = value.get('initial_feedback_contract_sha256')
        if 'initial_feedback_contract_sha256' in value:
            _sha(historical_contract)
        _validate_feedback(initial_feedback, value, contract_sha256=historical_contract)
        if initial_feedback['score_state'] == 'scored':
            valid_last = last_scored == initial_feedback
        else:
            valid_last = value['last_scored_feedback'] == initial_feedback['last_scored_feedback']
        if not valid_last:
            raise ValueError('Initial campaign must retain its latest actual scored feedback')
    if (last_scored.get('schema') not in {'earnings_population_feedback_v1',
                                        'earnings_population_campaign_feedback_v1'}
            or last_scored.get('company_id') != PANEL[0]
            or type(last_scored.get('results')) is not list or not last_scored['results']
            or value['baseline_version_id'] not in
                [row.get('version_id') for row in last_scored['results']]):
        raise ValueError('Separate real scored development feedback required')
    if (last_scored['schema'] == 'earnings_population_campaign_feedback_v1'
            and (last_scored.get('kind') != 'scored_dev'
                 or last_scored.get('score_state') != 'scored'
                 or last_scored.get('campaign_contract_sha256') !=
                    (digest(value['contract']) if scored_contract is None else scored_contract))):
        raise ValueError('Last scored campaign feedback must be scored/matched')
    if last_scored['schema'] == 'earnings_population_campaign_feedback_v1':
        _validate_feedback(last_scored, value, contract_sha256=scored_contract)
    for row in last_scored['results']:
        validate_result(row)
    return value


def _validate_feedback(value, manifest, *, contract_sha256=None, company_id=None):
    expected = {'schema', 'kind', 'score_state', 'company_id', 'round_index', 'decision',
        'chosen_parent_id', 'baseline_version_id', 'candidate', 'exploration_review',
        'results', 'previous_feedback', 'campaign_contract_sha256', 'last_scored_feedback', 'scope'}
    if (set(value) != expected or value['schema'] != 'earnings_population_campaign_feedback_v1'
            or value['kind'] not in {'scored_dev', 'review_rejected', 'no_change'}
            or value['score_state'] != ('scored' if value['kind'] == 'scored_dev' else 'unscored')
            or value['company_id'] != (PANEL[0] if company_id is None else company_id)
            or value['baseline_version_id'] != manifest['baseline_version_id']
            or value['campaign_contract_sha256'] != (digest(manifest['contract']) if contract_sha256 is None else contract_sha256)
            or type(value['results']) is not list
            or type(value['exploration_review']) is not dict
            or set(value['exploration_review']) != {'accepted_for_exploration', 'evidence'}
            or type(value['exploration_review']['accepted_for_exploration']) is not bool
            or value['exploration_review']['accepted_for_exploration'] != (value['kind'] == 'scored_dev')
            or (value['candidate'] is None) != (value['kind'] == 'no_change')):
        raise ValueError('Typed campaign feedback/contract state required')
    _bindings([value[k] for k in ('decision', 'previous_feedback', 'last_scored_feedback')])
    if value['kind'] == 'scored_dev':
        if (type(value['candidate']) is not dict
                or value['candidate'].get('parent') != value['chosen_parent_id']
                or [row.get('version_id') for row in value['results']] !=
                    expected_arms(manifest, value['chosen_parent_id'], value['candidate'].get('id'))):
            raise ValueError('Scored development feedback requires exact baseline/child results')
        for row in value['results']:
            validate_result(row)
    elif value['results']:
        raise ValueError('Unscored development feedback cannot contain scores')


def scope(manifest):
    if 'training_state_link' in manifest:
        from earnings_population_training25 import SCOPE as training_scope
        return training_scope
    return SCOPE


def _training(binding, value, initial, companies, max_rounds):
    """Structural joins only; trusted admission independently replays origin."""
    from earnings_population_training25 import (POLICY, admit, entry_plan, load_scope,
        validate_link, feedback_contracts, _read as training_read)
    extra = {'training_state_link','comparison_policy','initial_feedback_contract_sha256'}
    if 'last_scored_contract_sha256' in value:extra.add('last_scored_contract_sha256')
    if (set(value) != FIELDS | extra or value.get('schema') != 'earnings_population_campaign_v1'
            or type(max_rounds) is not int or max_rounds != 1
            or type(value.get('max_decisions')) is not int or value['max_decisions'] != 1
            or value.get('comparison_policy') != PARENT_COMPARISON):
        raise ValueError('Exact opted-in training campaign fields required')
    for key in ('baseline_version_id','initial_population_sha256','initial_feedback_contract_sha256'):
        _sha(value[key])
    if 'last_scored_contract_sha256' in value:_sha(value['last_scored_contract_sha256'])
    directory = _training_input(binding,'campaign.json')
    _training_input(value['training_state_link'],'training-state-link.json',directory=directory)
    _training_input(value['initial_feedback'],'rejection-feedback.json',directory=directory)
    link = _read(value['training_state_link'],recursive=False)
    fields = {'schema','policy','split','comparator','previous_population','population_sha256',
              'previous_feedback','last_scored_feedback','panel','completed_origin'}
    if (set(link) != fields or link.get('schema') != 'earnings_training25_state_link_v1'
            or type(link.get('policy')) is not str or link['policy'] != POLICY):
        raise ValueError('Exact forward training link metadata required')
    _sha(link['population_sha256'])
    for key in ('split','comparator','previous_population','previous_feedback','last_scored_feedback','completed_origin'):
        bound = link[key]
        if (type(bound) is not dict or set(bound) != {'path','sha256'}
                or type(bound.get('path')) is not str or type(bound.get('sha256')) is not str
                or re.fullmatch('[0-9a-f]{64}',bound['sha256']) is None):
            raise ValueError('Exact original link bindings required before recursion')
    boundary = load_scope(link['split'])
    if (type(companies) is not list or type(value['panel']) is not list or type(link['panel']) is not list
            or len(companies) != 1 or value['panel'] != companies or link['panel'] != companies
            or type(value['contract']) is not dict):
        raise ValueError('Exactly one training company in panel/link/contract required')
    for company in [*companies,value['validation_company_id'],value['contract'].get('company_id')]:
        admit(boundary,company)  # BEFORE any manifest or initial-state recursion.
    if value['validation_company_id'] != companies[0] or value['contract'].get('company_id') != companies[0]:
        raise ValueError('Training contract company differs from admitted panel')
    from earnings_entry import REPO
    entry_plan(value['source_plan'], REPO)
    if initial != training_read(link['previous_population']):
        raise ValueError('Training initial state differs from exact bound prior metadata')
    link = validate_link(link)  # A3 admits observed company IDs before pool recursion.
    validate(initial)
    if (link.get('completed_origin') is None or value['panel'] != link['panel']
            or companies != link['panel'] or len(companies) != 1
            or type(max_rounds) is not int or max_rounds != 1
            or type(value['max_decisions']) is not int or value['max_decisions'] != 1
            or value['validation_company_id'] != companies[0]
            or value['initial_population_sha256'] != digest(initial)
            or link['population_sha256'] != digest(initial)
            or value['comparison_policy'] != PARENT_COMPARISON
            or type(value['contract']) is not dict or value['contract'].get('company_id') != companies[0]
            or value['baseline_version_id'] not in initial['versions']):
        raise ValueError('Exact one-company frozen training task/state required')
    latest = training_read(link['previous_feedback']); scored = training_read(link['last_scored_feedback'])
    if (_read(value['initial_feedback'],recursive=False) != latest
            or value['last_scored_feedback'] != link['last_scored_feedback']
            or latest.get('baseline_version_id') != value['baseline_version_id']):
        raise ValueError('Training latest/last-score/control must preserve original identities')
    contracts = feedback_contracts(dict(research_feedback=latest,last_scored_feedback=link['last_scored_feedback']), boundary)
    if {k:value[k] for k in contracts} != contracts or ('last_scored_contract_sha256' in value) != ('last_scored_contract_sha256' in contracts):
        raise ValueError('Original training feedback contracts differ')
    _validate_feedback(latest,value,contract_sha256=contracts['initial_feedback_contract_sha256'],company_id=latest['company_id'])
    if scored.get('schema') == 'earnings_population_campaign_feedback_v1':
        _validate_feedback(scored,value,contract_sha256=contracts['last_scored_contract_sha256'],company_id=scored['company_id'])
    if (not scored.get('results') or value['baseline_version_id'] not in [row.get('version_id') for row in scored['results']]):
        raise ValueError('Separate real scored training ancestor/control required')
    for row in scored['results']:validate_result(row)
    # Nested current-task bindings must match the admitted resident, not merely
    # a self-declared company tag, before the final manifest artifact walk.
    from earnings_population_tasks import resident
    from earnings_population_campaign_admission import scientific_contract
    from earnings_open_resources import review_input_policy
    selected = review_input_policy(value['contract'])
    review_fields = {} if selected is None else {'review_input_policy': selected}
    if value['contract'] != scientific_contract(resident(companies[0]),training_scope=boundary,**review_fields):
        raise ValueError('Training contract differs from independently admitted resident')
    _artifacts(value)
    return value


def kind(child, review):
    if child is None:
        return 'no_change'
    return 'scored_dev' if review['accepted_for_exploration'] else 'review_rejected'


def arms(manifest, state, child, review):
    """Fresh matched baseline/child only; baseline may be an archived parent."""
    if kind(child, review) != 'scored_dev':
        return []
    baseline = manifest['baseline_version_id']
    if baseline not in state['versions'] or child['id'] not in state['explorers']:
        raise ValueError('Frozen campaign baseline and accepted child required')
    result = expected_arms(manifest, child['parent'], child['id'])
    if any(ident not in state['versions'] for ident in result):
        raise ValueError('Actual parent/control/child must exist in the frozen source pool')
    return result


def feedback(manifest, previous, chosen, child, review, measured,
             round_index, decision_binding):
    """Project only actual measurements; keep the last scored pointer separate."""
    outcome = kind(child, review)
    results = measured['results']
    if outcome == 'scored_dev':
        if (child['parent'] != chosen['parent_pair_sha256'] or
                [row['version_id'] for row in results] !=
                expected_arms(manifest, chosen['parent_pair_sha256'], child['id'])):
            raise ValueError('Campaign score requires exact frozen baseline and child')
        for row in results:
            validate_result(row)
    elif results:
        raise ValueError('Rejected or unchanged campaign decision is unscored')
    return dict(schema='earnings_population_campaign_feedback_v1', kind=outcome,
        score_state='scored' if outcome == 'scored_dev' else 'unscored',
        company_id=measured['company_id'], round_index=round_index,
        decision=deepcopy(decision_binding), chosen_parent_id=chosen['parent_pair_sha256'],
        baseline_version_id=manifest['baseline_version_id'], candidate=deepcopy(child),
        exploration_review=deepcopy(review), results=deepcopy(results),
        previous_feedback=deepcopy(previous['feedback']),
        campaign_contract_sha256=digest(manifest['contract']),
        last_scored_feedback=deepcopy(previous['last_scored_feedback']), scope=scope(manifest))
