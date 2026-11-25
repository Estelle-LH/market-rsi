"""Explicit Round0-only adapter for the existing owner, roles and scorer.

No old pool/origin, model calls, Native execution or financial implementation
lives here. Empty ABI programs are unscored scaffolding, not a model baseline.
"""
from copy import deepcopy
import ast
from datetime import datetime, timezone
import re
import json
import hashlib
import subprocess
from pathlib import Path

import earnings_entry as e
import earnings_population_training25 as training
import earnings_population_tasks as tasks
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from earnings_population_coevolution import parent_round, followup_round, continuous_round, frontier_round, selected_parent

POLICY = 'round0_clean_slate_v1'
PLAN = 'configs/earnings_coevolution/training25_clean_slate_authority.json'
ROUND2_PLAN = 'configs/earnings_coevolution/training25_clean_round2_authority.json'
FOLLOWUP_PLANS = {n:f'configs/earnings_coevolution/training25_clean_round{n}_authority.json' for n in (3,4,5,6,7)}

def followup_plan(n):
    if not followup_round(n):raise ValueError('Exact followup round required')
    if continuous_round(n):
        from earnings_population_coevolution import PLAN
        return PLAN
    return FOLLOWUP_PLANS[n]
STABLE03A_NEXT_AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-STABLE03A-NEXT-GROUP-DIRECT-AUTHORITY.json'),
    sha256='00425e5d552508b44aeb2d5e229afe1e76df649eb42b2e058bbc8203deadd4ae')
STABLE03A_YIELD_AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-CLEAN77-ROLLING-YIELD-AUTHORITY.json'),
    sha256='07d5826b65caecc50c1bc3d7e10087ece9b64979979220f1d95a06c514cf683b')
STABLE03A_ROUND6_YIELD_AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-CLEAN81-ROLLING-YIELD-AUTHORITY.json'),
    sha256='0d7f1a87bedaeb2786d4a0cca41dd4a312545439ea96507525e4fe42635839bd')
STABLE03A_ROUND7_YIELD_AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-CLEAN85-ROLLING-YIELD-AUTHORITY.json'),
    sha256='ee4143dc94adf063bb7d4f0f4ef8ba093e5274fe45c84a1c735a3d0e6dcaf674')
FINAL_FOLLOWUP_AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-CLEAN73-GROUP-COUNT-CORRECTION-AUTHORITY.json'),
    sha256='ab7c7f36ca1d07089e420c63592dc2650cd5a4bd09676cfb68cf6c3df66a2776')
WINDOW_YIELD_AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-CLEAN74-WINDOW-YIELD-AUTHORITY.json'),
    sha256='d16a558677402f45ac1ccab6e61dc21f7e23bc84c23afe7bc9e13a00b14b1b14')
ROUND2_TASK = ('Continue logical Round2 from the adopted complete25 Round1 R/H and its complete public feedback. '
    'Identify a transferable problem, investigate available literature/tools and propose one testable R or H change. '
    'Preserve useful actual-parent behavior. The parent is the adopted full25 version, not an empty scaffold, R09 or old control. '
    'Current-company tests are interface smoke only; freeze one candidate across all25 before any mutation or adoption. '
    'Compare the full25 company-equal mean to the saved adopted parent3.12; ties or worse retain the parent. '
    'Keep budget/model/effort/input/output/wall/tools/task/cutoff/kernel and heldout boundaries unchanged. '
    'Never hardcode company answers or force adoption. No baseline or parent rerun; no next research round in this authorization.')
_ROUND2_FROZEN = {}
ROUND0 = dict(path=str(training.ROOT/'TRAIN25-PLAIN-COMPARATOR-MANIFEST.json'),
    sha256='7a43ee9cac7204ef664d134c2e5effac14e2422aa9cedc207f66fcfe55ef07a3')
SPLIT = dict(path=str(training.SPLIT), sha256=training.SPLIT_SHA)
REPAIR_AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-CLEAN50-MINIMAL-REPAIR-AUTHORITY.json'),
    sha256='e80420214b045fb7364d022d43a7f73878493b0ec1df7fbf12e6f2b6a709f9d9')
CONCISE_REVIEW_ID = 'edgar-population-20261016-52'
CONCISE_REVIEW_AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-CLEAN52-CONCISE-REVIEW-AUTHORITY.json'),
    sha256='ba35c06dad3f08d1f904176f4561b64907141bcc406ae05bb97f077e75b23ea9')
ANCHOR_REVIEW_ID = 'edgar-population-20261016-53'
ANCHOR_REPAIR_AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-CLEAN53-ANCHOR-DATE-REPAIR-AUTHORITY.json'),
    sha256='a7bac297dc3eadc13b594f0d403ad88ad7bfe9e1138359e75f74f9283930c668')
ANCHOR_REPAIR_DESCRIPTOR = dict(path=str(training.ROOT/'clean52-anchor-date-repair/repair-review-final.json'),
    sha256='b398e0bcd88ec8f216e0859caa710a28385b70157ef6a796f58353b4cfad5af6')
RATE_SCALE_REVIEW_ID = 'edgar-population-20261016-68'
RATE_SCALE_REPAIR_AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-CLEAN68-RATE-SCALE-REPAIR-AUTHORITY.json'),
    sha256='ac0c9324006e6261073123af2097bd7f973da80abf8098196c3cdb83760d3b00')
CASE_EXPECTATION_REVIEW_ID = 'edgar-population-20261016-107'
CASE_EXPECTATION_DESCRIPTOR = dict(path=str(training.ROOT/'TRAIN25-CLEAN107-CASE-EXPECTATION-REPAIR.json'),
    sha256='e96ab9c2772c4535468ad6729a89d0f15b3f3499aa695200c8136bd1014a085a')
FIXTURE_REVIEW_ID = 'edgar-population-20261016-113'
FIXTURE_REVIEW_DESCRIPTOR = dict(path=str(training.ROOT/'TRAIN25-CLEAN113-FIXTURE-CONTRACT-REPAIR.json'),
    sha256='a85a140d18512e639e0d1c8d5fc571625e2b91db5d3be34da8037fb779e6951b')
ACQUISITION_REVIEW_ID = 'edgar-population-20261016-119'
ACQUISITION_REVIEW_DESCRIPTOR = dict(path=str(training.ROOT/'TRAIN25-CLEAN119-FIXTURE-CONTRACT-REPAIR.json'),
    sha256='741ab038d0d35bd8da1211325c89e689ec9c5d83b210ede752b05d0399f6a76a')
from earnings_population_source_trivia import REVIEW_ID as SOURCE_TRIVIA_REVIEW_ID, DESCRIPTOR as SOURCE_TRIVIA_DESCRIPTOR
from earnings_population_source_trivia144 import REVIEW_ID as TRIVIA144_ID, DESCRIPTOR as TRIVIA144_DESCRIPTOR
from earnings_population_source_trivia154 import REVIEW_ID as TRIVIA154_ID, DESCRIPTOR as TRIVIA154_DESCRIPTOR
from earnings_population_case_expectation146 import REVIEW_ID as CASE146_ID, DESCRIPTOR as CASE146_DESCRIPTOR

SOURCE_TRIVIA_IDS = (SOURCE_TRIVIA_REVIEW_ID, TRIVIA144_ID, TRIVIA154_ID)
SLOT_REBIND_AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-CLEAN70-SLOT-REBIND-AUTHORITY.json'),
    sha256='cd956a1985d8314e4cb490d8b27e54a60a26652ca26fe12bc7f236024aa058ee')
BACKPRESSURE_AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-CLEAN71-BACKPRESSURE-AUTHORITY.json'),
    sha256='753bad3b127e9e891e45a2b5f26539807c15541de93daee01cde9fdcca033b85')
TASK = ('Start a new research trajectory from complete plain Round0 public feedback only. '
    'Identify a transferable problem and propose one testable R or H change, using available '
    'literature/tools. Empty R0/H0 are unscored ABI scaffolding, not an evaluated parent, '
    'the plain model baseline or stage best. No old code/results/repair history are supplied. '
    'Current-company tests are interface smoke only. Freeze the resulting R/H pair across '
    'all25 before any next mutation; compare only to saved Round0. Preserve budgets, model, '
    'efforts, resource limits, task/cutoff/scorer and sealed heldout. Never hardcode company '
    'answers, predictions or awards. Do not promise adoption.')


def enabled(value):
    if 'clean_slate_policy' not in value:
        return False
    if value['clean_slate_policy'] != POLICY:
        raise ValueError('Unknown clean-slate policy')
    if 'clean_learning_round' in value:
        n=value['clean_learning_round']
        if (not parent_round(n)
                or followup_round(n) and followup_plan(n) not in value.get('sources',{})):
            raise ValueError('Only explicitly source-bound authorized clean continuation')
    return True


def second_round(value):
    """Legacy helper name: parent-backed clean continuation, not Round0 scaffold."""
    return parent_round(value.get('clean_learning_round'))


def _rate_scale_route(identifier, learning_round, repairing):
    if identifier==RATE_SCALE_REVIEW_ID and (type(learning_round) is not int or learning_round!=3 or repairing is not True):
        raise ValueError('Once68 is strictly logical3 repair Review, never legacy scaffold or C/A')


def _final_followup_route(identifier, learning_round, frozen, repairing):
    from earnings_population_coevolution import route
    route(identifier,learning_round,frozen,repairing)
    if identifier=='edgar-population-20261016-85' and (type(learning_round) is not int
            or learning_round!=7 or frozen or repairing):
        raise ValueError('Once85 is strictly the final03a-group logical7 proposal')
    if learning_round==7 and (repairing or not frozen and identifier!='edgar-population-20261016-85'
            or frozen and (not re.fullmatch(r'edgar-population-20261016-[0-9]{2}',identifier)
                or int(identifier.rsplit('-',1)[1])<=85)):
        raise ValueError('Final03a-group proposal85 once; later fresh IDs only frozen evaluation')
    if identifier=='edgar-population-20261016-81' and (type(learning_round) is not int
            or learning_round!=6 or frozen or repairing):
        raise ValueError('Once81 is strictly the second03a-group logical6 proposal')
    if learning_round==6 and (repairing or not frozen and identifier!='edgar-population-20261016-81'
            or frozen and (not re.fullmatch(r'edgar-population-20261016-[0-9]{2}',identifier)
                or int(identifier.rsplit('-',1)[1])<=81)):
        raise ValueError('Second03a-group proposal81 once; later fresh IDs only frozen evaluation')
    if identifier=='edgar-population-20261016-77' and (type(learning_round) is not int
            or learning_round!=5 or frozen or repairing):
        raise ValueError('Once77 is strictly the new-group logical5 proposal')
    if learning_round==5 and (repairing or not frozen and identifier!='edgar-population-20261016-77'
            or frozen and (not re.fullmatch(r'edgar-population-20261016-[0-9]{2}',identifier)
                or int(identifier.rsplit('-',1)[1])<=77)):
        raise ValueError('New group first proposal77 once; later fresh IDs evaluate frozen candidate only')
    if identifier=='edgar-population-20261016-73' and (type(learning_round) is not int
            or learning_round!=4 or frozen or repairing):
        raise ValueError('Once73 is strictly the final logical4 proposal, never an older route or evaluation')
    if learning_round==4 and (repairing or not frozen and identifier!='edgar-population-20261016-73'):
        raise ValueError('Final group attempt is proposal73 once; later IDs only evaluate its frozen candidate')


def research_task(value):
    if followup_round(value.get('clean_learning_round')):
        origin=round2_origin(value)
        specific=''
        if frontier_round(origin['logical_round']):
            from earnings_population_coevolution import declared_test
            specific=' Declared prospective frontier test (support/refutation are criteria, not assumed results): '+json.dumps(declared_test(origin),sort_keys=True)
        return (f"Continue logical Round{origin['logical_round']} from the actual selected R/H code parent "
            f"{origin['parent']['id']} (complete25 mean{origin['prior_mean']}). Read ALL latest25 public feedback "
            "and the separate actual-parent and prediction-incumbent feedback plus observed activation/coverage diagnostics. "
            "Rejected candidate modifications are lessons, NOT the code parent. Choose one testable transferable R or H "
            "change using available literature/tools; preserve useful parent behavior. Do not force a parser fix, "
            "particular strategy, both axes, adoption or promised gain. Freeze the resulting R/H once for all25; "
            "strictly greater complete25 company-equal mean adopts, tie/worse retains parent. No baseline/parent rerun, "
            "answer hardcoding, changed model/resources/budget/data/scorer/cutoff or heldout access. "
            "Feedback reuse is Discovery, not generalization; human rolling8 is not autonomous H improvement."
            + (f" For continuous rounds, adoption must ALSO beat the separately saved best incumbent mean{origin['incumbent_mean']}; "
               "The selected code parent is not necessarily the prediction incumbent. A provisional frontier seat is not prediction adoption; "
               "new children are prospective, never backfilled historical branches. Group completion/count never stops useful research."
               if continuous_round(value['clean_learning_round']) else '')+specific)
    return ROUND2_TASK if second_round(value) else TASK


def origin_plan(value):
    return ROUND2_PLAN if value.get('clean_learning_round')==2 else followup_plan(value['clean_learning_round'])


def feedback_name(value):
    return f"round{value['clean_learning_round']-1}-public-feedback.json" if second_round(value) else 'round0-public-feedback.json'


def _public_rows(feedback,report,version,training_ids):
    comparison=report['comparison'];rows=feedback.get('rows',[])
    if (feedback.get('schema')!='earnings_training25_public_summary_v1' or feedback.get('version_id')!=version
            or comparison.get('scored')!=25 or comparison.get('not_measured')!=0
            or len(rows)!=25 or [r['company_id'] for r in rows]!=training_ids
            or [r['company_id'] for r in comparison.get('rows',[])]!=training_ids):
        raise ValueError('Complete ordered25 public feedback required')
    for row,saved in zip(rows,comparison['rows']):
        expected=[dict(target_id=t['target_id'],predicted_value=t['candidate_prediction'],points_awarded=t['candidate_award']) for t in saved['targets']]
        if (row['targets']!=expected or row['points']!=saved['points']
                or [t['target_id'] for t in row['targets']]!=training.TARGETS
                or any(type(t['points_awarded']) not in (int,float) or t['points_awarded'] not in (0,.5,1) for t in expected)
                or sum(t['points_awarded'] for t in expected)!=row['points']):
            raise ValueError('Original public prediction/award substitution')
    return sum(r['points'] for r in rows)/25


def _followup_authorized(direct, binding, n):
    if type(n) is not int:return False
    if continuous_round(n):
        from earnings_population_coevolution import authorized
        return authorized(direct,binding,n)
    if n in (5,6,7):
        return (binding==STABLE03A_NEXT_AUTHORITY
            and direct.get('schema')=='edgar25_stable03a_next_group_direct_authority_v1'
            and direct.get('human_reply')=='是' and direct.get('allowed_logical_rounds')==[5,6,7]
            and direct.get('min_new_candidates')==2 and direct.get('max_new_candidates')==3
            and direct.get('group_attempt_ordinal')==1 and direct.get('prior_group_attempts')==0
            and direct.get('first_proposal_id')=='edgar-population-20261016-77'
            and direct.get('starting_parent_id')=='03a87b7b84629aed9dc5fc738b3f2be42e7c49fda8aba346718d8e7359ca67da'
            and direct.get('starting_parent_mean')==3.14 and direct.get('all_candidates_branch_same_parent') is True
            and direct.get('original_stage_budget_nano_usd')==200000000000
            and direct.get('budget')==dict(global_nano_usd=400000000000,named_model_nano_usd=300000000000,
                other_model_nano_usd=100000000000,owner_cap_nano_usd=5000000000,owner_minutes=90,reset=False,
                sole_ledger=str(e.PILOT/'api-budget.sqlite3'),stage_start_nano_usd=187429960800,stage_total_nano_usd=387429960800)
            and direct.get('failed_paid_retry_authorized') is False and direct.get('heldout_access') is False)
    if direct.get('schema')=='edgar25_clean_followup_direct_authority_v1':
        return direct.get('allowed_logical_rounds')==[3,4] and direct.get('max_new_candidates')==2
    if (binding!=FINAL_FOLLOWUP_AUTHORITY or n!=4
            or direct.get('schema')!='edgar25_clean_followup_final_attempt_authority_v1'
            or direct.get('allowed_logical_rounds')!=[4] or direct.get('max_new_candidates')!=3
            or direct.get('prior_group_attempts')!=2 or direct.get('final_attempt_ordinal')!=3
            or direct.get('final_proposal_id')!='edgar-population-20261016-73'
            or direct.get('no_further_candidate_after73') is not True):
        return False
    from earnings_population_runtime import _local
    attempts=direct.get('counted_prior_attempts',[])
    if [a['id'] for a in attempts]!=['edgar-population-20261016-67','edgar-population-20261016-68']:return False
    for attempt in attempts:
        closed=_local(attempt['closure'])
        if closed.get('original_true_exit')!=0 or closed.get('all_owned_settled') is not True:return False
    return True


def current_feedback_diagnostic(origin, logical_round, version_id):
    """Prospective bounded delivery; complete public125 rows live separately.

    Retain every current diagnostic field except the dense per-target period
    audit, which remains immutable at its authenticated evidence binding.
    This changes neither historical artifacts nor any model/resource ceiling.
    """
    from earnings_population_runtime import _local
    facts = _local(origin['supervisor_diagnostic'])
    return dict(schema='edgar25_current_mechanism_delivery_v1',
        logical_round=logical_round, version_id=version_id,
        evidence=deepcopy(origin['supervisor_diagnostic']),
        summary={k:v for k,v in facts.items() if k!='period_rows'},
        separately_preserved_fields=['period_rows'] if 'period_rows' in facts else [])


def validate_current_feedback_metadata(feedback, latest, origin, logical_round):
    """Additional semantic invariant for prospective15+; legacy stays unchanged."""
    if logical_round < 15:return
    from earnings_population_runtime import _local
    previous = logical_round-1
    version_id = _local(latest['frozen'])['candidate']['id']
    if (type(feedback.get('logical_round')) is not int
            or feedback['logical_round']!=previous or latest.get('logical_round')!=previous):
        raise ValueError('Current feedback round label differs from complete latest report')
    facts = _local(origin['supervisor_diagnostic'])
    if facts.get('report')!=origin['prior_comparison'] or facts.get('candidate')!=latest['frozen']:
        raise ValueError('Current diagnostic evidence is not the complete latest candidate/report')
    diagnostic = feedback.get('actual_R_H_diagnostic')
    if diagnostic!=facts and diagnostic!=current_feedback_diagnostic(origin,previous,version_id):
        raise ValueError('Current diagnostic differs from authenticated latest evidence')


def followup_origin(value):
    """Finite direct authority; latest feedback is not the selected code parent."""
    from earnings_population_runtime import _local
    n=value['clean_learning_round'];name=followup_plan(n);bound=value['sources'][name]
    if bound['path']!=str(e.REPO/name):raise ValueError('Own committed followup plan required')
    plan=e.strict_json(e.checked(bound));direct=_local(plan['direct_authority']);origin=_local(plan['origin'])
    old=_local(origin['prior_descriptor']);latest=_local(origin['prior_comparison']);stable=_local(origin['prior_stable'])
    parent_report=_local(origin['parent_comparison']);feedback=_local(origin['public_feedback']);parent_feedback=_local(origin['parent_feedback'])
    parent=origin['parent'];ids=training.load_scope(SPLIT)['training'];comparison=latest['comparison']
    if continuous_round(n):
        from earnings_population_coevolution import validate_plan
        validate_plan(plan,origin)
        validate_current_feedback_metadata(feedback,latest,origin,n)
    if n==6:
        progress=_local(plan['required_complete_progress']);checkpoint=_local(origin['previous_complete_checkpoint'])
        if (plan.get('group_attempt_ordinal')!=2 or origin.get('group_attempt_ordinal')!=2
                or origin.get('group_progress')!=plan['required_complete_progress']
                or progress.get('authority')!=plan['direct_authority'] or progress.get('attempts')!=[77]
                or progress.get('count_used')!=1 or progress.get('count_minimum')!=2 or progress.get('count_cap')!=3
                or progress.get('minimum_additional')!=1 or progress.get('remaining_maximum')!=2
                or progress.get('group_terminal') is not False or progress.get('next_candidate_authorized') is not True
                or progress.get('round5')!=origin['prior_comparison'] or progress.get('stable')!=origin['prior_stable']
                or checkpoint.get('every_blob_readback_verified') is not True or checkpoint.get('report')!=origin['prior_comparison']):
            raise ValueError('Second03a-group candidate requires complete first25 and exact consumed allowance')
    if n==7:
        progress=_local(plan['required_complete_progress']);checkpoint=_local(origin['previous_complete_checkpoint'])
        if (plan.get('group_attempt_ordinal')!=3 or origin.get('group_attempt_ordinal')!=3
                or origin.get('group_progress')!=plan['required_complete_progress']
                or progress.get('authority')!=plan['direct_authority'] or progress.get('attempts')!=[77,81]
                or progress.get('count_used')!=2 or progress.get('count_minimum')!=2 or progress.get('count_cap')!=3
                or progress.get('minimum_additional')!=0 or progress.get('remaining_maximum')!=1
                or progress.get('group_terminal') is not False or progress.get('next_candidate_authorized') is not True
                or progress.get('round6')!=origin['prior_comparison'] or progress.get('stable')!=origin['prior_stable']
                or checkpoint.get('every_blob_readback_verified') is not True or checkpoint.get('report')!=origin['prior_comparison']):
            raise ValueError('Final03a-group candidate requires complete second25 and exact consumed allowance')
    basis=latest.get('parent_basis') or _local(latest['frozen']).get('parent_basis')
    selected=(latest['frozen'] if comparison.get('decision')=='ADOPT_CANDIDATE' else
        comparison.get('selection_incumbent_descriptor',_local(basis)['prior_descriptor']))
    if continuous_round(n):
        incumbent_report=_local(origin['incumbent_comparison']);incumbent_feedback=_local(origin['incumbent_feedback'])
        incumbent=_local(origin['incumbent_descriptor'])['candidate']
        group_start=_local(origin['group_start_stable'])
        incumbent_mean=_public_rows(incumbent_feedback,incumbent_report,incumbent['id'],ids)
        if (selected!=origin['incumbent_descriptor']
                or group_start['selected']!=origin['incumbent_descriptor' if frontier_round(n) else 'prior_descriptor']
                or _local(incumbent_report['frozen'])['candidate']['id']!=incumbent['id']
                or incumbent_mean!=origin['incumbent_mean'] or incumbent_mean<origin['prior_mean']
                or feedback.get('selection_incumbent')!=dict(version_id=incumbent['id'],company_equal_mean=incumbent_mean,
                    manifest=origin['incumbent_comparison'],rows=incumbent_feedback['rows'])):
            raise ValueError('Declared group code parent and best comparable full25 incumbent differ')
    if (plan.get('schema')!='earnings_training25_clean_followup_authority_v1' or plan.get('logical_round')!=n
            or plan.get('max_concurrent_companies')!=8 or plan.get('max_inflight_per_company')!=1
            or plan.get('baseline_rerun') is not False or plan.get('direct_authority')!=origin.get('direct_authority')
            or not _followup_authorized(direct,plan['direct_authority'],n)
            or direct.get('max_concurrent_companies')!=8 or direct.get('single_owner') is not True
            or origin.get('schema')!='earnings_clean_followup_origin_v1' or origin.get('logical_round')!=n
            or origin.get('prior_logical_round')!=n-1 or latest.get('logical_round')!=n-1
            or origin.get('split')!=SPLIT or origin.get('round0')!=ROUND0 or origin.get('training')!=ids
            or stable.get('comparison')!=origin['prior_comparison'] or stable.get('selected')!=selected
            or not continuous_round(n) and selected!=origin['prior_descriptor'] or stable.get('decision')!=comparison.get('decision')
            or comparison.get('decision') not in ('ADOPT_CANDIDATE','RETAIN_ADOPTED_PARENT')
            or origin.get('original_candidate')!=old['candidate'] or parent['id']!=old['candidate']['id']
            or any(parent[a]!=old['candidate'][a] for a in ('R','H'))
            or parent['id']!=digest({a:parent[a]['sha256'] for a in ('R','H')})
            or _local(parent_report['frozen'])['candidate']['id']!=parent['id']
            or feedback.get('manifest')!=origin['prior_comparison'] or parent_feedback.get('manifest')!=origin['parent_comparison']):
        raise ValueError('Exact complete prior comparison/selected parent/followup authority differs')
    latest_id=_local(latest['frozen'])['candidate']['id']
    latest_mean=_public_rows(feedback,latest,latest_id,ids)
    mean=_public_rows(parent_feedback,parent_report,parent['id'],ids)
    selected_mean=latest_mean if comparison['decision']=='ADOPT_CANDIDATE' else comparison.get('parent_mean')
    if (latest_mean!=comparison.get('candidate_mean') or feedback.get('company_equal_mean')!=latest_mean
            or not continuous_round(n) and mean!=selected_mean or mean!=parent_report['comparison'].get('candidate_mean')
            or not continuous_round(n) and comparison['decision']=='RETAIN_ADOPTED_PARENT' and comparison.get('parent_version_id')!=parent['id']
            or mean!=origin['prior_mean'] or feedback.get('actual_parent' if frontier_round(n) else 'adopted_parent')!=dict(version_id=parent['id'],company_equal_mean=mean,
            manifest=origin['parent_comparison'],rows=parent_feedback['rows'])
            or parent['id']!=(plan['group_parent_id'] if continuous_round(n) else direct['starting_parent_id'])
            or mean!=(plan['group_parent_mean'] if continuous_round(n) else direct['starting_parent_mean'])):
        raise ValueError('Actual adopted full25 parent threshold/feedback differs')
    for axis in ('R','H'):e.checked(parent[axis])
    return origin


def round2_origin(value):
    """Current immutable adoption/feedback metadata; never replay old Native gates."""
    from earnings_population_runtime import _local
    if not second_round(value):raise ValueError('Explicit next-round marker required')
    if followup_round(value['clean_learning_round']):return followup_origin(value)
    bound=value['sources'][ROUND2_PLAN]
    if bound['path']!=str(e.REPO/ROUND2_PLAN):raise ValueError('Own committed Round2 authority required')
    plan=e.strict_json(e.checked(bound));direct=_local(plan['direct_authority']);origin=_local(plan['origin'])
    old=_local(origin['prior_descriptor']);comparison=_local(origin['prior_comparison'])['comparison']
    stable=_local(origin['prior_stable']);feedback=_local(origin['public_feedback']);parent=origin['parent']
    if (plan.get('schema')!='earnings_training25_clean_round2_authority_v1' or plan.get('logical_round')!=2
            or direct.get('logical_round')!=2 or direct.get('actual_parent_pair')!=parent['id']
            or plan.get('incumbent_pair')!=parent['id'] or plan.get('incumbent_mean')!=3.12
            or plan.get('max_concurrent_companies')!=4 or plan.get('max_inflight_per_company')!=1
            or plan.get('baseline_rerun') is not False or plan.get('next_round_authorized') is not False
            or origin.get('schema')!='earnings_clean_round2_origin_v1' or origin.get('logical_round')!=2
            or origin.get('split')!=SPLIT or origin.get('round0')!=ROUND0
            or origin.get('training')!=training.load_scope(SPLIT)['training']
            or parent['id']!=old['candidate']['id'] or any(parent[a]!=old['candidate'][a] for a in ('R','H'))
            or parent['id']!=digest({a:parent[a]['sha256'] for a in ('R','H')})
            or stable.get('selected')!=origin['prior_descriptor'] or stable.get('decision')!='ADOPT_CANDIDATE'
            or comparison.get('scored')!=25 or comparison.get('not_measured')!=0
            or comparison.get('decision')!='ADOPT_CANDIDATE' or comparison.get('candidate_mean')!=origin['prior_mean']
            or origin['prior_mean']!=3.12):raise ValueError('Complete adopted Round1 identity differs')
    rows=feedback.get('rows',[])
    if (feedback.get('schema')!='earnings_training25_public_summary_v1'
            or feedback.get('manifest')!=origin['prior_comparison'] or feedback.get('version_id')!=parent['id']
            or [r['company_id'] for r in rows]!=origin['training'] or len(rows)!=25
            or sum(r['points'] for r in rows)!=78):raise ValueError('Complete prior25 public feedback required')
    if (len(comparison.get('rows',[]))!=25
            or [r['company_id'] for r in comparison['rows']]!=origin['training']):
        raise ValueError('Actual prior comparison requires ordered25 rows')
    for row,saved in zip(rows,comparison['rows']):
        expected=[dict(target_id=t['target_id'],predicted_value=t['candidate_prediction'],points_awarded=t['candidate_award']) for t in saved['targets']]
        if (row['company_id']!=saved['company_id'] or row['points']!=saved['points'] or row['targets']!=expected
                or [t['target_id'] for t in row['targets']]!=training.TARGETS
                or any(type(t['points_awarded']) not in (int,float) or t['points_awarded'] not in (0,.5,1) for t in row['targets'])
                or sum(t['points_awarded'] for t in row['targets'])!=row['points']):raise ValueError('Actual prior target feedback differs')
    for axis in ('R','H'):e.checked(parent[axis])
    return origin


def authority(value):
    bound = value['sources'][PLAN]
    if bound['path'] != str(e.REPO/PLAN) or value['population_plan'] != bound:
        raise ValueError('Exact committed clean-slate authority required')
    plan = e.strict_json(e.checked(bound))
    if (plan.get('schema') != 'earnings_training25_clean_slate_authority_v1'
            or plan.get('policy') != POLICY or plan.get('round0_manifest_sha256') != ROUND0['sha256']
            or plan.get('split_sha256') != SPLIT['sha256']
            or plan.get('budget') != dict(sole_ledger=str(e.PILOT/'api-budget.sqlite3'),
                stage_total_nano_usd=387429960800, global_nano_usd=400000000000,
                named_model_nano_usd=300000000000, other_model_nano_usd=100000000000,
                new_window_nano_usd=5000000000, window_minutes=90, serial_proposal=True,
                max_concurrent_companies=4, max_inflight_per_company=1, reset=False)):
        raise ValueError('Clean-slate authority or unchanged financial boundaries differ')
    if second_round(value):round2_origin(value)
    if 'clean_company_concurrency' in value:
        from earnings_population_company_batch import concurrency_limit
        if concurrency_limit(value)>4 and not followup_round(value.get('clean_learning_round')):
            raise ValueError('Rolling8 requires the new direct followup authority, not old rounds')
    return plan


def read_task(value):
    from earnings_population_runtime import _local
    from earnings_population_company_batch import rolling
    study = _local(value['forecast_study'])
    bound = study.get('clean_slate_task')
    expected = training.ROOT/'inputs'/value['id']/'clean-slate-task.json'
    if type(bound) is not dict or bound.get('path') != str(expected):
        raise ValueError('Exact own clean-slate task binding required')
    task = _local(bound)
    _rate_scale_route(value['id'],value.get('clean_learning_round'),task.get('mode')=='repair_review' and 'repair' in task)
    _final_followup_route(value['id'],value.get('clean_learning_round'),task.get('mode')=='evaluate',task.get('mode')=='repair_review')
    fields = {'schema','policy','authority','split','round0','mode','company_id',
              'feedback','scaffold','frozen_candidate','company_ids'}
    if second_round(value):fields.add('round2_origin')
    if (set(task) != fields | ({'repair'} if 'repair' in task else set()) or task['schema'] != 'earnings_training25_clean_slate_task_v1'
            or task['policy'] != POLICY or task['authority'] != value['sources'][PLAN]
            or task['split'] != SPLIT or task['round0'] != ROUND0
            or task['mode'] not in ('proposal','repair_review','evaluate') or value['companies'] != task['company_ids']
            or not 1<=len(task['company_ids'])<=(25 if rolling(value) else 4) or len(set(task['company_ids']))!=len(task['company_ids'])
            or task['company_id']!=task['company_ids'][0]
            or task['mode'] in ('proposal','repair_review') and len(task['company_ids'])!=1
            or ('repair' in task)!=(task['mode']=='repair_review')):
        raise ValueError('Clean-slate task differs from admitted runtime')
    scope = training.load_scope(SPLIT)
    for company in task['company_ids']:training.admit(scope,company)
    from earnings_population_company_batch import enabled as batch_enabled
    if (len(task['company_ids'])>1 or rolling(value))!=batch_enabled(value):raise ValueError('Exact concurrency4 opt-in required')
    if rolling(value) and task['mode']!='evaluate':raise ValueError('Rolling is frozen evaluation only')
    if second_round(value) and task['mode']=='evaluate' and not rolling(value):raise ValueError('Round2 evaluates only with reviewed rolling4')
    if task['feedback']['path'] != str(expected.parent/feedback_name(value)):
        raise ValueError('Canonical Round0 feedback required')
    if second_round(value) and ((task['mode']=='repair_review' and not ((value['id']==RATE_SCALE_REVIEW_ID and value['clean_learning_round']==3)
            or (value['id']==CASE_EXPECTATION_REVIEW_ID and value['clean_learning_round']==11)
            or (value['id']==FIXTURE_REVIEW_ID and value['clean_learning_round']==12)
            or (value['id']==ACQUISITION_REVIEW_ID and value['clean_learning_round']==13)
            or (value['id']==SOURCE_TRIVIA_REVIEW_ID and value['clean_learning_round']==14)
            or (value['id'] in (TRIVIA144_ID,CASE146_ID) and value['clean_learning_round']==16)
            or (value['id']==TRIVIA154_ID and value['clean_learning_round']==17))) or task['round2_origin']!=
            e.strict_json(e.checked(value['sources'][origin_plan(value)]))['origin']):raise ValueError('Exact prospective parent origin required')
    if followup_round(value.get('clean_learning_round')) and task['mode']=='evaluate':
        from earnings_population_company_batch import ROLLING8
        if value.get('clean_company_concurrency')!=ROLLING8:raise ValueError('New followup evaluation requires explicit rolling8')
        if backpressure_rebind(task['frozen_candidate']) and set(task['company_ids'])&set(engine.read(BACKPRESSURE_AUTHORITY)['preserve_completed_companies']):
            raise ValueError('Never rerun a preserved scored70 company')
        from earnings_population_additional_execution import selected
        if selected(task['frozen_candidate']) and (
                'additional_budget_amendment' not in value or value['clean_learning_round']!=15
                or task['company_ids'] not in (['CIK0000946581','CIK0001002638'],['CIK0001002638'])):
            raise ValueError('Additional100 Round15 bridge admits only the two verified never-started suffix companies')
    if task['mode']=='repair_review':repair_metadata(task['repair'],value['id'])
    return task, scope


def round0_feedback():
    """Authenticate originals as opaque bytes; expose public predictions/awards only."""
    scope = training.load_scope(SPLIT)
    manifest = training._read(ROUND0)
    if (set(manifest) != {'schema','split','rows'}
            or manifest['schema'] != 'earnings_plain_training_comparator_manifest_v1'
            or manifest['split'] != SPLIT
            or [row.get('cik') for row in manifest['rows']] != scope['training']):
        raise ValueError('Exact original ordered25 manifest required')
    rows = []
    for row in manifest['rows']:
        training.admit(scope, row['cik'])
        if set(row) != training.ROW_FIELDS:
            raise ValueError('Original baseline row bindings differ')
        for key in training.ROW_FIELDS-{'cik'}:
            training._bytes(row[key])  # Never decode score/QA/hidden reasoning.
        predictions = training._read(row['predictions'])['predictions']
        public = training._read(row['public_feedback'])
        awards = public['per_target']
        if ([v.get('target_id') for v in predictions] != training.TARGETS
                or [v.get('target_id') for v in awards] != training.TARGETS
                or any(type(v.get('points_awarded')) not in (int,float)
                    or v['points_awarded'] not in (0,.5,1) for v in awards)
                or public['cik'] != row['cik']
                or sum(v['points_awarded'] for v in awards) != public['score_out_of_5']):
            raise ValueError('Original five public predictions/awards required')
        values = {v['target_id']:v['predicted_value'] for v in predictions}
        rows.append(dict(company_id=row['cik'],points=public['score_out_of_5'],targets=[dict(
            target_id=v['target_id'],predicted_value=values[v['target_id']],
            points_awarded=v['points_awarded']) for v in awards]))
    if len(rows) != 25 or sum(r['points'] for r in rows) != 75:
        raise ValueError('Original25/125/75 Round0 evidence differs')
    return dict(schema='earnings_training25_public_summary_v1',manifest=deepcopy(ROUND0),
        split=deepcopy(SPLIT),rows=rows,target_order=training.TARGETS,
        attribution='Original plain Round0 public predictions/awards only; no old R/H results or answers.')


def scaffold(sources, origin=None):
    from earnings_population import initialize, version
    if origin is not None and continuous_round(origin.get('logical_round')):
        from earnings_population import validate
        state=deepcopy(validate(engine.read(origin['carried_population'])))
        expected=dict(K=digest({'data':tasks.FULL_PLAN,'scorer':tasks.SCORER}),
            M=digest({'model':'gpt-6.1-sol','serving_snapshot':'unknown'}),C=sources['forecaster']['sha256'])
        if state['protected']!=expected or (not frontier_round(origin['logical_round']) and state['stable_id']!=origin['parent']['id']):
            raise ValueError('Continue the actual retained population/protected identities, never initialize a new experiment')
        if frontier_round(origin['logical_round']):
            from earnings_population_coevolution import expansion
            expansion(origin)
            selected_parent(state,origin)
        return state
    seed = version(sources['configs/earnings_coevolution/program_R0.py'],
        sources['configs/earnings_coevolution/program_H0.py'],
        method='Unscored empty ABI scaffold; NOT plain Round0 or evaluated stage-best',
        author='existing neutral interface code')
    if origin is not None:seed=deepcopy(origin['parent'])
    state = initialize(seed,dict(K=digest({'data':tasks.FULL_PLAN,'scorer':tasks.SCORER}),
        M=digest({'model':'gpt-6.1-sol','serving_snapshot':'unknown'}),C=sources['forecaster']['sha256']))
    return state


def study(value):
    from earnings_population_runtime import _local
    authority(value)
    task, scope = read_task(value)
    saved = _local(value['forecast_study'])
    if task['mode']=='repair_review' and case_contract_review(value['id']):
        case_expectation_originals(repair_metadata(task['repair'],value['id']))
    if task['mode']=='repair_review' and not case_contract_review(value['id']):
        fixed=repair_metadata(task['repair'],value['id'])
        original_git=engine.read(fixed['original_git'])
        expected_git=('fa598c6ea2f3f6a05107d3c16e2653d748f8118f' if value['id']==RATE_SCALE_REVIEW_ID else 'dd000675cb6cef9a53abe1a9c23cf59ddf20d66f' if value['id']==ANCHOR_REVIEW_ID
            else '0af23f3ae465b53819d806e1e7d8e8ae9687c08b')
        if original_git.get('commit')!=expected_git:raise ValueError('Exact original rejected Git seal required')
        bindings=((fixed['closure'],fixed['original_review'],fixed['original_implement'],fixed['scientific_decision'],fixed['original_candidate']['R']) if value['id']==RATE_SCALE_REVIEW_ID else (fixed['closure'],fixed['original_review']) if value['id']==ANCHOR_REVIEW_ID else
            (fixed['closure'],fixed['original_candidate']['R'],fixed['original_review'],fixed['original_candidate']['evidence'][1]))
        for bound in bindings:
            alias='original/'+str(Path(bound['path']).relative_to(training.ROOT))
            raw=subprocess.run(['git','show',original_git['commit']+':'+alias],cwd=e.REPO,check=True,capture_output=True).stdout
            if raw!=e.checked(bound):raise ValueError('Original50 archived evidence differs')
        if value['id']==ANCHOR_REVIEW_ID:
            for commit,bound in ((engine.read(fixed['prior_inputs_git'])['commit'],fixed['original_candidate']['R']),
                    ('0af23f3ae465b53819d806e1e7d8e8ae9687c08b',fixed['scientific_decision'])):
                alias='original/'+str(Path(bound['path']).relative_to(training.ROOT))
                raw=subprocess.run(['git','show',commit+':'+alias],cwd=e.REPO,check=True,capture_output=True).stdout
                if raw!=e.checked(bound):raise ValueError('Original R or scientific decision differs')
        if value['id']==CONCISE_REVIEW_ID:
            concise=concise_review_metadata(task['repair'],fixed)
            for bound in (concise['failed_closure'],engine.read(concise['failed_closure'])['failure']):
                alias='original/'+str(Path(bound['path']).relative_to(training.ROOT))
                raw=subprocess.run(['git','show',concise['failed_commit']+':'+alias],cwd=e.REPO,check=True,capture_output=True).stdout
                if raw!=e.checked(bound):raise ValueError('Original51 archived failure differs')
    if set(saved) != {'schema','model','data','scorer','sole_ledger','runtime_config','cases',
                      'prior_batch','clean_slate_task'}:
        raise ValueError('Clean study must contain no old campaign/reuse/lineage')
    origin=round2_origin(value) if second_round(value) else None
    if (_local(task['feedback']) != (_local(origin['public_feedback']) if origin is not None else round0_feedback())
            or task['scaffold'] != scaffold(value['sources'],origin)
            or _local(value['initial_population']) != task['scaffold']):
        raise ValueError('Round0-only feedback or neutral scaffold changed')
    if task['mode'] in ('proposal','repair_review'):
        if task['frozen_candidate'] is not None:
            raise ValueError('Proposal cannot import old/frozen candidate')
    else:
        frozen = load_frozen(task['frozen_candidate'])
        if (frozen['source_commit'] != value['source_commit']
                or value.get('clean_learning_round',1)!=frozen.get('learning_round',1)
                or second_round(value) and frozen.get('parent_basis')!=task['round2_origin']):
            raise ValueError('Frozen candidate evaluation Source changed')
    resident = tasks.resident(training.admit(scope,task['company_id']))
    original = resident['runtime']
    if (saved['schema'] != 'earnings_coevolution_study_v1'
            or saved['model'] != dict(requested_model='gpt-6.1-sol',serving_snapshot='unknown',serving_snapshot_verified=False)
            or saved['data'] != tasks.FULL_PLAN or saved['scorer'] != tasks.SCORER
            or saved['sole_ledger'] != value['ledger'] or saved['runtime_config'] != original
            or saved['cases'] != [tasks.resident(c)['case'] for c in task['company_ids']]
            or any(tasks.resident(c)['runtime']!=original for c in task['company_ids'])
            or _local(saved['prior_batch']) != dict(schema='original_runtime_snapshot_v1',source=tasks.RUNTIME,config=original)
            or value['rates'] != original['models']['gpt-6.1-sol']):
        raise ValueError('Original data/scorer/task/runtime/model resources changed')
    expected = {role:[str(Path(value['root'])/'roles'/(role+'-01'))] for role in ('controller','author','review')}
    expected['forecast'] = [str(Path(value['root'])/'roles'/f'forecast-01-{i:02d}') for i in range(len(task['company_ids']))]
    if value['slots'] != expected or value.get('additional_cap_nano_usd') != 5000000000:
        raise ValueError('Only one candidate forecast and original5 window permitted')
    return original


def prepare(identifier, *, company_id, frozen_candidate=None, batch_companies=None, repair=None, rolling_refill=False, learning_round=1, rolling_concurrency=4, additional_budget_amendment=None):
    if identifier == CASE146_ID and (type(learning_round) is not int or learning_round != 16
            or frozen_candidate is not None or repair != CASE146_DESCRIPTOR):
        raise ValueError('Once146 requires exact logical16 unchanged-PROGRAM first Review descriptor')
    if identifier == TRIVIA144_ID and (type(learning_round) is not int or learning_round != 16
            or frozen_candidate is not None or repair != TRIVIA144_DESCRIPTOR):
        raise ValueError('Once144 requires exact logical16 source-trivia first Review descriptor')
    if identifier == TRIVIA154_ID and (type(learning_round) is not int or learning_round != 17
            or frozen_candidate is not None or repair != TRIVIA154_DESCRIPTOR):
        raise ValueError('Once154 requires exact logical17 one-comment FIRST Review descriptor')
    if identifier == SOURCE_TRIVIA_REVIEW_ID and (type(learning_round) is not int
            or learning_round != 14 or frozen_candidate is not None or repair != SOURCE_TRIVIA_DESCRIPTOR):
        raise ValueError('Once126 requires exact logical14 source-trivia first Review descriptor')
    _rate_scale_route(identifier,learning_round,repair is not None)
    _final_followup_route(identifier,learning_round,frozen_candidate is not None,repair is not None)
    from earnings_population_company_batch import preparation_policy
    company_policy=preparation_policy(rolling_refill,rolling_concurrency)
    from earnings_population_runtime import ROOT, EXTRA_BASELINE, EXTRA_CAP, source_paths, preflight
    from earnings_population_run import idle_snapshot
    from earnings_population_budget import amendment_binding
    from earnings_population_model_budget import binding as model_binding
    from earnings_open_resources import ROLE_EFFORTS, population_role_limits, REVIEW200_POLICY
    from earnings_population_public_predictions import POLICY as PUBLIC
    from earnings_population_live_guard import POLICY as GUARD
    import earnings_population_window as window
    if not re.fullmatch(r'edgar-population-20261016-[0-9]{2,}',identifier):
        raise ValueError('Exact fresh own ID required')
    output, root = ROOT/'inputs'/identifier, ROOT/'attempts'/identifier
    if output.exists() or root.exists(): raise FileExistsError('Never reopen an ID')
    companies=[company_id] if batch_companies is None else list(batch_companies)
    if repair is not None:
        repair_metadata(repair,identifier)
        if frozen_candidate is not None or companies!=['CIK0000003545']:raise ValueError('Exact once-only repair Review only')
    if type(rolling_refill) is not bool or rolling_refill and (frozen_candidate is None or repair is not None):
        raise ValueError('Rolling requires an explicit frozen evaluation')
    if (not 1<=len(companies)<=(25 if rolling_refill else 4) or len(companies)!=len(set(companies)) or companies[0]!=company_id
            or len(companies)>1 and frozen_candidate is None):raise ValueError('Frozen candidate wave1..4 or explicit rolling queue1..25 required')
    scope = training.load_scope(SPLIT)
    for company in companies:training.admit(scope,company)
    baseline = idle_snapshot()
    source_commit = subprocess.run(['git','rev-parse','HEAD'],cwd=e.REPO,check=True,capture_output=True,text=True).stdout.strip()
    if (type(learning_round) is not int or learning_round < 1
            or learning_round>=2 and repair is not None and not ((learning_round==3 and identifier==RATE_SCALE_REVIEW_ID)
                or (learning_round==11 and identifier==CASE_EXPECTATION_REVIEW_ID)
                or (learning_round==12 and identifier==FIXTURE_REVIEW_ID)
                or (learning_round==13 and identifier==ACQUISITION_REVIEW_ID)
                or (learning_round==14 and identifier==SOURCE_TRIVIA_REVIEW_ID)
                or (learning_round==16 and identifier in (TRIVIA144_ID,CASE146_ID))
                or (learning_round==17 and identifier==TRIVIA154_ID))):
        raise ValueError('Explicit fresh proposal/evaluation Round2 only')
    options={'clean_round2':True} if learning_round==2 else ({'clean_followup':learning_round} if followup_round(learning_round) else {})
    paths = source_paths(model_budget=True,training=True,clean_slate=True,**options)
    sources = {name:engine.pin(Path(path)) for name,path in paths.items()}
    for bound in sources.values():
        name = str(Path(bound['path']).relative_to(e.REPO))
        original = subprocess.run(['git','show',source_commit+':'+name],cwd=e.REPO,check=True,capture_output=True).stdout
        if original != e.checked(bound): raise ValueError('Commit exact production sources before prepare')
    origin=round2_origin(dict(sources=sources,clean_learning_round=learning_round)) if learning_round>=2 else None
    if origin is not None and (origin['forecast_sources']!={k:sources[k] for k in origin['forecast_sources']}):
        raise ValueError('Protected forecaster execution source changed')
    state = scaffold(sources,origin)
    feedback = engine.read(origin['public_feedback']) if origin is not None else round0_feedback()
    if frozen_candidate is not None:
        load_frozen(frozen_candidate)
        if backpressure_rebind(frozen_candidate) and set(companies)&set(engine.read(BACKPRESSURE_AUTHORITY)['preserve_completed_companies']):
            raise ValueError('Never rerun a preserved scored70 company')
    output.mkdir(parents=True,mode=0o700,exist_ok=False)
    task = dict(schema='earnings_training25_clean_slate_task_v1',policy=POLICY,authority=sources[PLAN],
        split=SPLIT,round0=ROUND0,mode='proposal' if frozen_candidate is None else 'evaluate',
        company_id=company_id,company_ids=companies,feedback=engine.save(output/feedback_name(dict(clean_learning_round=learning_round) if origin else {}),feedback),
        scaffold=state,frozen_candidate=frozen_candidate)
    if origin is not None:task['round2_origin']=e.strict_json(e.checked(sources[origin_plan(dict(clean_learning_round=learning_round))]))['origin']
    if repair is not None:task.update(mode='repair_review',repair=repair)
    resident = tasks.resident(company_id); original = resident['runtime']
    prior = engine.save(output/'original-runtime-snapshot.json',dict(schema='original_runtime_snapshot_v1',source=tasks.RUNTIME,config=original))
    saved = engine.save(output/'study.json',dict(schema='earnings_coevolution_study_v1',
        model=dict(requested_model='gpt-6.1-sol',serving_snapshot='unknown',serving_snapshot_verified=False),
        data=tasks.FULL_PLAN,scorer=tasks.SCORER,sole_ledger=str(e.PILOT/'api-budget.sqlite3'),
        runtime_config=original,cases=[tasks.resident(c)['case'] for c in companies],prior_batch=prior,
        clean_slate_task=engine.save(output/'clean-slate-task.json',task)))
    overlay = {'review_input_policy':REVIEW200_POLICY} if frozen_candidate is None else {}
    limits = dict(population_role_limits(overlay),forecast=dict(max_input_tokens=original['max_input_tokens'],
        max_output_tokens=original['max_output_tokens'],wall_seconds=original['company_wall_seconds']))
    value = dict(schema='earnings_population_runtime_v1',purpose='capacity_episode',id=identifier,
        source_commit=source_commit,root=str(root),ledger=str(e.PILOT/'api-budget.sqlite3'),baseline=baseline,
        window_minutes=90,additional_cap_nano_usd=5000000000,rates=original['models']['gpt-6.1-sol'],
        role_efforts=ROLE_EFFORTS,limits=limits,sources=sources,forecast_study=saved,
        initial_population=engine.save(output/'initial-population.json',state),population_plan=sources[PLAN],
        companies=companies,original_extra_baseline=EXTRA_BASELINE,original_extra_cap_nano_usd=EXTRA_CAP,
        review=None,budget_amendment=amendment_binding(),model_budget_amendment=model_binding(),
        training_policy=training.POLICY,validation_policy=GUARD,public_feedback_policy=PUBLIC,
        clean_slate_policy=POLICY,slots={role:[str(root/'roles'/(role+'-01'))] for role in ('controller','author','review')},**overlay)
    value['slots']['forecast'] = [str(root/'roles'/f'forecast-01-{i:02d}') for i in range(len(companies))]
    if additional_budget_amendment is not None:
        value['additional_budget_amendment']=deepcopy(additional_budget_amendment)
    if origin is not None:value['clean_learning_round']=learning_round
    if len(companies)>1 or rolling_refill:
        value['clean_company_concurrency']=company_policy
    value.update(window.bounds(datetime.now(timezone.utc),value))
    binding = engine.save(output/'runtime-unreviewed.json',value)
    preflight(binding,require_review=False)
    return binding


def controller(service, packet, slot):
    from earnings_population_roles import PopulationController
    from earnings_open_broker import program_references
    task, scope = read_task(service.runtime)
    if task['mode'] != 'proposal': raise ValueError('Frozen evaluation cannot mutate')
    service.current = training.admit(scope,packet['company_id'])
    service.campaign_context = None
    state = packet['population']; origin=round2_origin(service.runtime) if second_round(service.runtime) else None
    parent = selected_parent(state,origin)
    service.role_versions = {parent['id']:parent}
    service.prior_feedback = engine.read(task['feedback'])
    if packet['feedback'] != task['feedback']: raise ValueError('Actual packet lost full Round0 feedback')
    case = service.case(parent,slot)
    role = service.role('controller',PopulationController,case,slot)
    prompt = dict(company_id=service.current,questions=case['state_api'].tools.files['questions.md'],
        feedback=service.prior_feedback,feedback_sha256=packet['parent_feedback_sha256'],
        feedback_binding=task['feedback'],stable_id=state['stable_id'],active_versions=[parent['id']],explorers=[],
        current_programs=program_references(role.broker.current_sources()),explorer_programs=[],
        available_traces=[],research_objective=research_task(service.runtime),scope=research_task(service.runtime))
    original = role.propose(prompt,slot)
    decoded = engine.read(engine.pin(Path(slot)/'decision.json'))
    if decoded['original'] != original: raise ValueError('Original Controller response lost')
    return engine.save(Path(slot)/'population-decision.json',decoded['decision'])


def selection(manager, role, args, kwargs):
    """Independent current role selection; never call a legacy campaign loader."""
    from earnings_population_runtime import _local
    task, scope = read_task(manager.value)
    slot = Path(args[-1])
    if kwargs or str(slot) not in manager.value['slots'][role]: raise ValueError('Exact clean role slot required')
    if task['mode']=='repair_review':
        fixed=repair_metadata(task['repair'],manager.value['id'])
        if role!='review' or args!=(fixed['candidate'],repair_state(task,fixed),str(slot)):
            raise ValueError('Repair permits exactly one original Review, no C/A/forecast')
        version=fixed['candidate'];company=task['company_id'];packet_binding=None
    elif task['mode'] == 'evaluate':
        if role != 'forecast' or len(args) != 3: raise ValueError('Candidate-only frozen evaluation')
        version = load_frozen(task['frozen_candidate'])['candidate']
        company=task['company_ids'][manager.value['slots']['forecast'].index(str(slot))]
        if args[:2] != (version,company): raise ValueError('Frozen candidate/company substitution')
        packet_binding = None
    else:
        packet_binding = engine.pin(manager.root/'packet-01.json'); packet = _local(packet_binding)
        if (packet['company_id'] != task['company_id'] or packet.get('round_index') != 1
                or packet['feedback'] != task['feedback'] or packet['population'] != task['scaffold']):
            raise ValueError('Clean proposal packet feedback/state differs')
        origin=round2_origin(manager.value) if second_round(manager.value) else None
        parent=selected_parent(packet['population'],origin)
        if role == 'controller':
            if len(args) != 2 or args[0] != packet: raise ValueError('Controller packet substitution')
            version = parent
        elif role == 'author':
            if len(args) != 3 or args[1] != packet['population'] or args[0]['feedback_sha256'] != digest(task['feedback']):
                raise ValueError('Author feedback/state substitution')
            version = packet['population']['versions'][args[0]['parent_pair_sha256']]
            # Services.author prepares the original registered Native record.
            # selected_parent already authenticates the exact descriptor and
            # any historical incumbent anchor projection without rewriting it.
            if version['id']!=parent['id'] or any(version[a]!=parent[a] for a in ('R','H')):
                raise ValueError('Author replaced the selected actual parent')
        elif role == 'review':
            if len(args) != 3 or args[1] != packet['population'] or args[0]['parent'] != parent['id']:
                raise ValueError('Review child/scaffold substitution')
            version = args[0]
        else: raise ValueError('Proposal cannot forecast scaffold or candidate')
    if version['id'] != digest({a:version[a]['sha256'] for a in ('R','H')}): raise ValueError('Source identity differs')
    company=task['company_id'] if task['mode'] in ('proposal','repair_review') else company
    resident = tasks.resident(training.admit(scope,company))
    saved = _local(manager.value['forecast_study'])
    bindings = [manager.binding,manager.value['forecast_study'],manager.value['initial_population'],
        manager.value['population_plan'],manager.value['review'],saved['clean_slate_task'],task['feedback'],
        SPLIT,ROUND0,manager.value['model_budget_amendment'],tasks.FULL_PLAN,tasks.METADATA,tasks.MANIFEST,
        tasks.RUNTIME,tasks.SCORER,resident['kernel']['qa'],version['R'],version['H']]
    if packet_binding is not None: bindings.append(packet_binding)
    if task['frozen_candidate'] is not None: bindings += frozen_inputs(task['frozen_candidate'])
    if second_round(manager.value):
        origin=round2_origin(manager.value)
        bindings += [task['round2_origin'],origin['public_feedback'],origin['prior_comparison'],origin['prior_stable'],origin['prior_descriptor']]
        if followup_round(manager.value.get('clean_learning_round')):
            bindings += [origin[k] for k in ('parent_feedback','parent_comparison','direct_authority')]
        if manager.value.get('clean_learning_round')==5:bindings.append(STABLE03A_YIELD_AUTHORITY)
        if manager.value.get('clean_learning_round')==6:
            bindings += [STABLE03A_ROUND6_YIELD_AUTHORITY,origin['group_progress'],origin['previous_complete_checkpoint']]
        if manager.value.get('clean_learning_round')==7:
            bindings += [STABLE03A_ROUND7_YIELD_AUTHORITY,origin['group_progress'],origin['previous_complete_checkpoint']]
        if continuous_round(manager.value.get('clean_learning_round')):
            from earnings_population_coevolution import yield_authority
            bindings += [yield_authority(manager.value),origin['previous_complete_checkpoint'],
                *[origin[k] for k in ('incumbent_descriptor','incumbent_comparison','incumbent_feedback','group_start_stable','carried_population')]]
            if frontier_round(manager.value['clean_learning_round']):
                from earnings_population_coevolution import expansion
                claim=expansion(origin)
                bindings += [origin['frontier_expansion'],claim['frontier']]
                frontier=engine.read(claim['frontier'])
                if frontier.get('schema')=='edgar25_depth_frontier_v4':
                    from earnings_population_layered import AUTHORITY as layered_authority,POLICY as layered_policy
                    bindings += [layered_authority,layered_policy,frontier['preceding_outcomes'],origin['additional_budget_amendment']]
    if task['mode']=='repair_review':
        if manager.value['id'] in SOURCE_TRIVIA_IDS:
            if manager.value['id']==TRIVIA154_ID:
                from earnings_population_source_trivia154 import bindings as trivia_bindings
            elif manager.value['id']==TRIVIA144_ID:
                from earnings_population_source_trivia144 import bindings as trivia_bindings
            else:
                from earnings_population_source_trivia import bindings as trivia_bindings
            bindings += [task['repair'],repair_authority(manager.value['id']),*trivia_bindings(fixed)]
        else:
            bindings += [task['repair'],repair_authority(manager.value['id']),*[fixed[k] for k in ('closure','original_git','original_review','source','tests','validation')],fixed['original_candidate']['R'],fixed['original_candidate']['H']]
        if case_contract_review(manager.value['id']) and manager.value['id'] not in SOURCE_TRIVIA_IDS:
            bindings += [fixed[k] for k in ('original_inputs_git','original_implement','scientific_decision','original_tests','original_case_results','original_feedback','exact_saved_replay')]
        if manager.value['id']==CASE146_ID:
            from earnings_population_case_expectation146 import EXTRA_KEYS
            bindings += [fixed[k] for k in EXTRA_KEYS]
        if manager.value['id']==FIXTURE_REVIEW_ID:
            bindings += [fixed[k] for k in ('full_diagnostic','financial_audit','distinct_financial_review','integration_contract')]
        if manager.value['id']==ACQUISITION_REVIEW_ID:
            bindings += [fixed[k] for k in ('distinct_financial_review','integration_contract')]
        if manager.value['id']==RATE_SCALE_REVIEW_ID:bindings += [fixed['original_implement'],fixed['scientific_decision']]
        if manager.value['id']==ANCHOR_REVIEW_ID:bindings += [fixed['prior_inputs_git'],fixed['scientific_decision']]
        if manager.value['id']==CONCISE_REVIEW_ID:
            concise=concise_review_metadata(task['repair'],fixed)
            bindings += [CONCISE_REVIEW_AUTHORITY,concise['failed_closure'],concise['failed_private_git']]
    bindings += [dict(path=str(Path(resident['company']['visible_root'])/r['path']),sha256=r['sha256'])
        for r in resident['company']['allowed_files']]
    return dict(role=role,slot=str(slot),version=deepcopy(version),company=company,
        resident=resident,bindings=bindings,registered=False,extra_contexts={})


def case_contract_review(identifier):
    return identifier in (CASE_EXPECTATION_REVIEW_ID,FIXTURE_REVIEW_ID,ACQUISITION_REVIEW_ID,CASE146_ID,*SOURCE_TRIVIA_IDS)


def repair_metadata(binding,identifier):
    """Original51 repair or separately authorized52 format attempt, never generic retry."""
    if identifier==CASE146_ID:
        from earnings_population_case_expectation146 import metadata
        return metadata(binding)
    if identifier==TRIVIA154_ID:
        from earnings_population_source_trivia154 import metadata
        return metadata(binding)
    if identifier==CASE_EXPECTATION_REVIEW_ID:return case_expectation_metadata(binding)
    if identifier==FIXTURE_REVIEW_ID:return fixture_contract_metadata(binding)
    if identifier==ACQUISITION_REVIEW_ID:return acquisition_fixture_metadata(binding)
    if identifier==TRIVIA144_ID:
        from earnings_population_source_trivia144 import metadata
        return metadata(binding)
    if identifier==SOURCE_TRIVIA_REVIEW_ID:
        from earnings_population_source_trivia import metadata
        return metadata(binding)
    if identifier==RATE_SCALE_REVIEW_ID:return rate_scale_repair_metadata(binding)
    if identifier==ANCHOR_REVIEW_ID:return anchor_date_repair_metadata(binding)
    if identifier not in ('edgar-population-20261016-51',CONCISE_REVIEW_ID) or binding['path']!=str(training.ROOT/'clean50-minimal-repair/repair-review.json'):
        raise ValueError('Exactly one new repair Review ID required')
    e.checked(REPAIR_AUTHORITY);fixed=engine.read(binding)
    if fixed.get('schema')!='earnings_clean50_interface_repair_v1' or fixed.get('authority')!=REPAIR_AUTHORITY:
        raise ValueError('Exact human once-repair authority required')
    audit=engine.read(fixed['closure']);old=fixed['original_candidate'];child=fixed['candidate']
    if (audit.get('candidate')!=old or audit.get('status')!='PROPOSAL_NOT_ACCEPTED'
            or audit.get('original_exec_true_exit')!=0 or audit.get('current_pending_count')!=0
            or fixed['closure']['sha256']!='b77ecb21c755cb68cffb48625bbb8a9fa9d938dada5627d2b7eba65d306892fd'
            or child['parent']!=old['id'] or child['H']!=old['H'] or child['R']!=fixed['source']
            or child['axis']!='R' or child['method']!=old['method']
            or child['author']!='human_authorized_interface_repair_of_model:DeltaAuthor'
            or child['id']!=digest({a:child[a]['sha256'] for a in ('R','H')})):
        raise ValueError('Original rejected candidate or human repair identity differs')
    before=ast.parse(e.checked(old['R']));after=ast.parse(e.checked(child['R']))
    unchanged=lambda tree:[ast.dump(n) for n in tree.body if not isinstance(n,ast.FunctionDef) or n.name!='_plan']
    if unchanged(before)!=unchanged(after):raise ValueError('Only acquisition _plan may change, not science')
    for bound in (fixed['tests'],fixed['validation'],fixed['original_review']):e.checked(bound)
    if identifier==CONCISE_REVIEW_ID:concise_review_metadata(binding,fixed)
    return fixed


def repair_authority(identifier):
    if case_contract_review(identifier):
        from earnings_population_coevolution import AUTHORITY
        return AUTHORITY
    return RATE_SCALE_REPAIR_AUTHORITY if identifier==RATE_SCALE_REVIEW_ID else ANCHOR_REPAIR_AUTHORITY if identifier==ANCHOR_REVIEW_ID else REPAIR_AUTHORITY


def case_expectation_metadata(binding):
    """Exact107: unchanged0994 PROGRAM, full exact CASES, no original model Review.

    Supervisor engineering under the continuous routine-repair authority; never
    a permission to resend a paid request, regenerate code or relax equality.
    """
    from earnings_population_coevolution import AUTHORITY
    if binding!=CASE_EXPECTATION_DESCRIPTOR:raise ValueError('Exact once107 case-correction descriptor required')
    e.checked(AUTHORITY);fixed=engine.read(binding)
    old=fixed['original_candidate'];child=fixed['candidate'];audit=engine.read(fixed['closure'])
    if (fixed.get('schema')!='edgar25_once107_exact_case_expectation_correction_v1'
            or fixed.get('review_id')!=CASE_EXPECTATION_REVIEW_ID or fixed.get('logical_round')!=11
            or fixed.get('authority')!=AUTHORITY or fixed.get('PROGRAM_unchanged') is not True
            or fixed.get('source_axis')!='H' or child.get('axis')!='H' or old!=child or fixed['source']!=child['H']
            or child['id']!='09948af24e569097d7dc6fd784ecdaea2b9637431843a59d024270ced329c8a1'
            or child['parent']!='eece7c670f69cd64afb65c65f509422e9e3f12199f8c8da344a6f9da0f5b34a3'
            or child['R']['sha256']!='da3d237ee8b78924bac90c18facbcf335c866a586c45d5521746836ec0edfe30'
            or child['H']['sha256']!='9fc9ba152f059e44d96c8587806bab6fbb13e9c5c095acd3ab391e25f6e155af'
            or child['id']!=digest({a:child[a]['sha256'] for a in ('R','H')})
            or audit.get('status')!='PROPOSAL_NOT_ACCEPTED' or audit.get('original_true_exit')!=0
            or audit.get('owned_generations')!=16 or audit.get('owned_cost_nano_usd')!=754796000
            or audit.get('all_owned_settled') is not True or audit.get('pending_count')!=0
            or engine.read(fixed['original_git']).get('commit')!='ecf868c2c91d0366a37123849d7c3f869f5e6566'
            or engine.read(fixed['original_implement'])['output']['candidate']!=child
            or engine.read(fixed['original_review']).get('rationale')!='MODEL_CASES_FAILED; inspect preserved case evidence'
            or (training.ROOT/'attempts/edgar-population-20261016-106/roles/review-01').exists()):
        raise ValueError('Once107 requires exact closed106, same PROGRAM/parent and no original paid Review')
    tests=engine.read(fixed['tests']);validation=engine.read(fixed['validation']);replay=engine.read(fixed['exact_saved_replay'])
    if (not 1<=len(e.checked(fixed['tests']))<=32768 or type(tests) is not list or len(tests)!=6
            or any(type(c) is not dict or set(c)!={'input','expected'} for c in tests)
            or validation.get('PROGRAM_unchanged') is not True or validation.get('run_cases_exact_equality_unchanged') is not True
            or validation.get('corrected_tests')!=fixed['tests'] or validation.get('test_bytes')!=len(e.checked(fixed['tests']))
            or validation.get('host_candidate_execution') is not False or validation.get('model_calls')!=0
            or validation.get('ledger_writes')!=0 or validation.get('heldout_read') is not False
            or replay.get('source')!=child['H'] or replay.get('tests')!=fixed['tests']
            or replay.get('all6_exact_equal') is not True or len(replay.get('rows',[]))!=6
            or replay.get('validated_learning') is not False):
        raise ValueError('Original32KiB/full-exact test contract and independently audited replay required')
    for bound in (child['R'],child['H'],fixed['original_tests'],fixed['original_case_results'],fixed['scientific_decision'],fixed['original_feedback']):e.checked(bound)
    return fixed


def fixture_contract_metadata(binding):
    """Exact113 only: same112 PROGRAM, corrected test interface, no paid retry."""
    from earnings_population_coevolution import AUTHORITY
    if binding!=FIXTURE_REVIEW_DESCRIPTOR:raise ValueError('Exact once113 fixture descriptor required')
    e.checked(AUTHORITY);fixed=engine.read(binding)
    child=fixed['candidate'];audit=engine.read(fixed['closure'])
    if (fixed.get('schema')!='edgar25_once113_fixture_contract_repair_v1'
            or fixed.get('review_id')!=FIXTURE_REVIEW_ID or fixed.get('logical_round')!=12
            or fixed.get('authority')!=AUTHORITY or fixed.get('PROGRAM_unchanged') is not True
            or fixed.get('source_axis')!='H' or child!=fixed['original_candidate'] or child.get('axis')!='H'
            or child['id']!='8ce5fbc23967571b1f5b0e5d7394c6eea228d98bb84e24168ef116938dccd0a4'
            or child['parent']!='09948af24e569097d7dc6fd784ecdaea2b9637431843a59d024270ced329c8a1'
            or child['R']['sha256']!='da3d237ee8b78924bac90c18facbcf335c866a586c45d5521746836ec0edfe30'
            or child['H']['sha256']!='eadec59e4e7f5e95089dd88faff49a41fc27e86527f9f330d43a7c399ff8df19'
            or fixed['source']!=child['H'] or child['id']!=digest({a:child[a]['sha256'] for a in ('R','H')})
            or audit.get('status')!='PROPOSAL_NOT_ACCEPTED' or audit.get('original_true_exit')!=0
            or audit.get('owned_generations')!=16 or audit.get('owned_cost_nano_usd')!=731617300
            or audit.get('all_owned_settled') is not True or audit.get('pending_count')!=0
            or engine.read(fixed['original_git']).get('commit')!='59fff4b29d17bb77defdcb5c58552e12c02e22e3'
            or engine.read(fixed['original_implement'])['output']['candidate']!=child
            or engine.read(fixed['original_review']).get('rationale')!='MODEL_CASES_FAILED; inspect preserved case evidence'
            or (training.ROOT/'attempts/edgar-population-20261016-112/roles/review-01').exists()):
        raise ValueError('Once113 requires sealed112, identical PROGRAM/parent and no previous paid Review')
    tests=engine.read(fixed['tests']);validation=engine.read(fixed['validation']);replay=engine.read(fixed['exact_saved_replay'])
    diagnostic=engine.read(fixed['full_diagnostic']);financial=engine.read(fixed['financial_audit']);distinct=engine.read(fixed['distinct_financial_review'])
    if (len(e.checked(fixed['tests']))!=32731 or type(tests) is not list or len(tests)!=4
            or any(type(c) is not dict or set(c)!={'input','expected'} for c in tests)
            or validation.get('PROGRAM_unchanged') is not True or validation.get('run_cases_exact_equality_unchanged') is not True
            or validation.get('tests')!=fixed['tests'] or validation.get('test_bytes')!=32731
            or validation.get('formal_case_count')!=4 or validation.get('selected_original_indices')!=[0,3,4,5]
            or validation.get('host_candidate_execution') is not False or validation.get('model_calls')!=0 or validation.get('ledger_writes')!=0
            or replay.get('source')!=child['H'] or replay.get('tests')!=fixed['tests']
            or replay.get('all4_exact_equal') is not True or len(replay.get('rows',[]))!=4 or replay.get('validated_learning') is not False
            or diagnostic.get('source')!=child['H'] or len(diagnostic.get('rows',[]))!=6
            or diagnostic.get('PROGRAM_unchanged') is not True or diagnostic.get('model_calls')!=0
            or validation.get('additional_mandatory_full_Review_diagnostic')!=fixed['full_diagnostic']
            or financial.get('diagnostic')!=fixed['full_diagnostic'] or financial.get('fixed_synthetic_financial_semantics_verified') is not True
            or distinct.get('verdict')!='PASS_SAVED_SYNTHETIC_FINANCIAL_INTERFACE_AUDIT_ONLY'
            or distinct.get('candidate_id')!=child['id'] or distinct.get('reviewer')!='/root/clean_slate_readonly_review'
            or distinct.get('bindings',{}).get('formal4_tests')!=fixed['tests']):
        raise ValueError('Unchanged exact32KiB contract, four formal cases and all six audited diagnostics required')
    for bound in (child['R'],child['H'],fixed['original_tests'],fixed['original_case_results'],fixed['scientific_decision'],fixed['original_feedback'],fixed['integration_contract']):e.checked(bound)
    return fixed


def acquisition_fixture_metadata(binding):
    """Exact119: same118 R/H, full exact negatives, first paid Review only."""
    from earnings_population_coevolution import AUTHORITY
    if binding!=ACQUISITION_REVIEW_DESCRIPTOR:raise ValueError('Exact once119 fixture descriptor required')
    e.checked(AUTHORITY);fixed=engine.read(binding)
    child=fixed['candidate'];audit=engine.read(fixed['closure'])
    if (fixed.get('schema')!='edgar25_once119_fixture_contract_repair_v1'
            or fixed.get('review_id')!=ACQUISITION_REVIEW_ID or fixed.get('logical_round')!=13
            or fixed.get('authority')!=AUTHORITY or fixed.get('PROGRAM_unchanged') is not True
            or fixed.get('source_axis')!='R' or child!=fixed['original_candidate'] or child.get('axis')!='R'
            or child['id']!='5e2270f66472d1faf3ae84c22cc79bfaef387a3e83133836ce06dc718fd71570'
            or child['parent']!='03a87b7b84629aed9dc5fc738b3f2be42e7c49fda8aba346718d8e7359ca67da'
            or child['R']['sha256']!='be29280556415e4de24f94375e5bcc8bfa1f3d756554478670d5c7b74c4207a0'
            or child['H']['sha256']!='6d80fa56d0625188f4357d791a725083a6bab75119c0736424516b3dc5681350'
            or fixed['source']!=child['R'] or child['id']!=digest({a:child[a]['sha256'] for a in ('R','H')})
            or audit.get('status')!='PROPOSAL_NOT_ACCEPTED' or audit.get('original_true_exit')!=0
            or audit.get('owned_generations')!=16 or audit.get('owned_cost_nano_usd')!=686786500
            or audit.get('all_owned_settled') is not True or audit.get('pending_count')!=0
            or audit.get('pending_full_reserved_nano_usd')!=0
            or engine.read(fixed['original_git']).get('commit')!='d687fe9918f6ccb7d1efbfd95cd39e0929988132'
            or engine.read(fixed['original_implement'])['output']['candidate']!=child
            or engine.read(fixed['original_review']).get('rationale')!='MODEL_CASES_FAILED; inspect preserved case evidence'
            or (training.ROOT/'attempts/edgar-population-20261016-118/roles/review-01').exists()):
        raise ValueError('Once119 requires closed118, identical R/H/parent and no previous paid Review')
    tests=engine.read(fixed['tests']);validation=engine.read(fixed['validation']);replay=engine.read(fixed['exact_saved_replay'])
    distinct=engine.read(fixed['distinct_financial_review'])
    if (len(e.checked(fixed['tests']))!=32244 or type(tests) is not list or len(tests)!=8
            or any(type(c) is not dict or set(c)!={'input','expected'} for c in tests)
            or validation.get('PROGRAM_unchanged') is not True or validation.get('run_cases_exact_equality_unchanged') is not True
            or validation.get('corrected_tests')!=fixed['tests'] or validation.get('test_bytes')!=32244
            or validation.get('corrected_only_indices')!=[6,7] or validation.get('original_inputs_and_first6_expected_unchanged') is not True
            or validation.get('new_candidate_execution') is not False or validation.get('model_calls')!=0
            or validation.get('ledger_writes')!=0 or validation.get('original_paid_Review_calls')!=0
            or replay.get('source')!=child['R'] or replay.get('tests')!=fixed['tests']
            or replay.get('all8_exact_equal') is not True or len(replay.get('rows',[]))!=8
            or replay.get('host_candidate_execution') is not False or replay.get('validated_learning') is not False
            or distinct.get('verdict')!='PASS_SAVED_SYNTHETIC_FINANCIAL_INTERFACE_AUDIT_ONLY'
            or distinct.get('candidate_id')!=child['id'] or distinct.get('reviewer')!='/root/clean_slate_readonly_review'
            or distinct.get('bindings',{}).get('corrected_full8_tests')!=fixed['tests']):
        raise ValueError('All8 full-exact32KiB tests and independent synthetic-only review required')
    for bound in (child['R'],child['H'],fixed['original_tests'],fixed['original_case_results'],fixed['scientific_decision'],fixed['original_feedback'],fixed['integration_contract']):e.checked(bound)
    return fixed


def case_expectation_originals(fixed):
    """Bounded exact private-blob proof, not a repeated Native/history gate."""
    if fixed.get('schema')=='edgar25_once154_source_trivia_first_review_v1':
        from earnings_population_source_trivia154 import originals
        return originals(fixed)
    if fixed.get('schema')=='edgar25_once144_source_trivia_first_review_v1':
        from earnings_population_source_trivia144 import originals
        return originals(fixed)
    if fixed.get('schema')=='edgar25_once126_source_trivia_first_review_v1':
        from earnings_population_source_trivia import originals
        return originals(fixed)
    checkpoints=[engine.read(fixed[k]) for k in ('original_git','original_inputs_git')]
    if any(c.get('every_blob_readback_verified') is not True for c in checkpoints):
        raise ValueError('Original106 private seals required')
    keys=('closure','original_review','original_implement','scientific_decision','original_tests','original_case_results','original_feedback','source')
    if fixed.get('schema')=='edgar25_once146_unchanged_program_first_review_case_v1':
        keys+=('original_runtime','original_decision','parent_R')
    for bound in [fixed[k] for k in keys]+[fixed['candidate']['R']]:
        found=[(cp,alias) for cp in checkpoints for alias,value in cp['artifacts'].items() if value==bound]
        if not found:raise ValueError('Original106 sealed binding missing')
        cp,alias=found[0]
        raw=subprocess.run(['git','show',cp['commit']+':'+alias],cwd=e.REPO,check=True,capture_output=True).stdout
        if raw!=e.checked(bound):raise ValueError('Original106 saved blob differs')


def rate_scale_repair_metadata(binding):
    """One human-authorized68 repair, not a generic followup retry switch."""
    if binding.get('path')!=str(training.ROOT/'clean67-rate-scale-repair/repair-review-final.json'):
        raise ValueError('Exact once68 repair descriptor required')
    authority=engine.read(RATE_SCALE_REPAIR_AUTHORITY);fixed=engine.read(binding)
    audit=engine.read(fixed['closure']);old=fixed['original_candidate'];child=fixed['candidate']
    original=engine.read(fixed['original_implement'])['output']['candidate']
    if (fixed.get('schema')!='earnings_clean67_rate_scale_repair_v1' or fixed.get('authority')!=RATE_SCALE_REPAIR_AUTHORITY
            or authority.get('review_id')!=RATE_SCALE_REVIEW_ID or fixed['closure']!=authority['original_closed_closure']
            or audit.get('original_true_exit')!=0 or audit.get('status')!='PROPOSAL_NOT_ACCEPTED' or audit.get('pending_count')!=0
            or old!=original or old['id']!=authority['source_parent_candidate']
            or old['parent']!=authority['comparison_parent_candidate']
            or engine.read(fixed['original_git'])['commit']!=authority['original_closed_git']
            or child['parent']!=old['id'] or child['H']!=old['H'] or child['R']!=fixed['source']
            or child['axis']!='R' or child['method']!=old['method']
            or child['author']!='human_authorized_rate_scale_repair_of_model:DeltaAuthor'
            or child['id']!=digest({a:child[a]['sha256'] for a in ('R','H')})):
        raise ValueError('Exact rejected67 lineage, unchanged strategy/H and once68 authority required')
    allowed={'_ci_debt','_ci_rate'}
    untouched=lambda bound:[ast.dump(n) for n in ast.parse(e.checked(bound)).body if not isinstance(n,ast.FunctionDef) or n.name not in allowed]
    if untouched(old['R'])!=untouched(child['R']):raise ValueError('Only rate and principal-unit parsing may change')
    validation=engine.read(fixed['validation'])
    if (validation.get('source')!=child['R'] or validation.get('actual_parent')!=old['R']
            or validation.get('allowed_functions')!=sorted(allowed) or validation.get('host_candidate_execution') is not False
            or validation.get('model_calls')!=0 or validation.get('ledger_writes')!=0 or validation.get('heldout_read') is not False
            or len(validation.get('original_case_results',[]))!=4 or not all(v['passed'] for v in validation['original_case_results'])
            or len(validation.get('extra_isolated_tests',[]))!=9 or not all(v['passed'] for v in validation['extra_isolated_tests'])):
        raise ValueError('Exact isolated original and rate/scale boundary tests required')
    for bound in (fixed['tests'],fixed['original_review'],fixed['scientific_decision']):e.checked(bound)
    return fixed


def anchor_date_repair_metadata(binding):
    if binding!=ANCHOR_REPAIR_DESCRIPTOR:
        raise ValueError('Exact once53 anchor/date repair descriptor required')
    authority=engine.read(ANCHOR_REPAIR_AUTHORITY);fixed=engine.read(binding)
    old=fixed['original_candidate'];child=fixed['candidate'];audit=engine.read(fixed['closure'])
    if (fixed.get('schema')!='earnings_clean52_anchor_date_repair_v1' or fixed.get('authority')!=ANCHOR_REPAIR_AUTHORITY
            or authority.get('review_id')!=ANCHOR_REVIEW_ID or old['id']!=authority.get('actual_parent')
            or audit.get('candidate')!=old or audit.get('scientific_verdict') is not False
            or audit.get('original_exec_true_exit')!=0 or audit.get('status')!='PROPOSAL_NOT_ACCEPTED'
            or audit.get('pending_count')!=0 or fixed['closure']!=authority.get('rejected52_closure')
            or child['parent']!=old['id'] or child['H']!=old['H'] or child['R']!=fixed['source']
            or child['axis']!='R' or child['method']!=old['method']
            or child['author']!='human_authorized_anchor_date_repair_of_model:DeltaAuthor'
            or child['id']!=digest({a:child[a]['sha256'] for a in ('R','H')})):
        raise ValueError('Exact rejected52 parent and unchanged-strategy repair required')
    allowed={'_plan','_spans','_table_notes','_event_for','_table_columns','_table_unit'}
    def untouched(bound):
        return [ast.dump(n) for n in ast.parse(e.checked(bound)).body if not isinstance(n,ast.FunctionDef) or n.name not in allowed]
    if untouched(old['R'])!=untouched(child['R']):raise ValueError('Only numerical acquisition/table and event-date functions may change')
    validation=engine.read(fixed['validation'])
    if (validation.get('source')!=child['R'] or validation.get('actual_parent')!=old['R']
            or validation.get('host_candidate_execution') is not False or validation.get('model_calls')!=0
            or len(validation.get('real_training_probes',[]))!=2):raise ValueError('Actual isolated real-material validation required')
    for bound in (fixed['tests'],fixed['original_review'],fixed['original_git'],fixed['prior_inputs_git'],fixed['scientific_decision']):e.checked(bound)
    return fixed


def concise_review_metadata(binding,fixed):
    authority=engine.read(CONCISE_REVIEW_AUTHORITY)
    audit=engine.read(authority['failed_closure']);saved=engine.read(authority['failed_private_git'])
    if (authority.get('schema')!='earnings_clean52_once_concise_review_authority_v1'
            or authority.get('id')!=CONCISE_REVIEW_ID or authority.get('repair_descriptor')!=binding
            or audit.get('original_exec_true_exit')!=1 or audit.get('decision')!='INCOMPLETE_NO_SELECTION'
            or audit.get('incomplete_details')!={'reason':'max_output_tokens'}
            or audit.get('pending_count')!=0 or audit.get('candidate')!=fixed['candidate']
            or audit.get('frozen') is not False or audit.get('scientific_verdict') is not None
            or authority.get('candidate')!=fixed['candidate']['id']
            or any(authority.get(a+'_sha256')!=fixed['candidate'][a]['sha256'] for a in ('R','H'))
            or saved.get('commit')!=authority.get('failed_commit') or saved.get('true_exit_code')!=0
            or saved.get('closure')!=authority.get('failed_closure')):
        raise ValueError('Exact closed51 failure and unchanged once52 candidate required')
    return authority


def repair_state(task,fixed):
    # Rejected50 is a derivative source, never a new stable/best or pool adoption.
    return deepcopy(task['scaffold'])


def repair_review(service,live,task):
    """Original owner/guard/Services.review only; no synthetic model stages."""
    from earnings_open_program import program
    fixed=repair_metadata(task['repair'],service.runtime['id']);child=fixed['candidate']
    service.current=task['company_id'];service.prior_feedback=engine.read(task['feedback'])
    cases=(engine.read(fixed['tests']) if case_contract_review(service.runtime['id'])
        else ast.literal_eval(ast.parse(e.checked(fixed['tests'])).body[-1].value))
    if type(cases)!=list or not 1<=len(cases)<=8 or any(set(c)!={'input','expected'} for c in cases):
        raise ValueError('Bounded literal repair tests required')
    axis=child['axis'] if case_contract_review(service.runtime['id']) else 'R'
    trivia=service.runtime['id'] in SOURCE_TRIVIA_IDS
    original_stage=fixed['original_failure'] if trivia else fixed['original_review']
    decision_binding=fixed['scientific_decision'] if trivia else fixed.get('scientific_decision',fixed['original_candidate']['evidence'][1])
    service.authored[child['id']]=dict(source=e.checked(child[axis]).decode(),
        parsed=dict(profile=program(e.checked(child[axis]),axis),cases=cases),
        decision=engine.read(decision_binding)['scientific_decision'],
        originals=[task['repair'],repair_authority(service.runtime['id']),fixed['closure'],original_stage,fixed['source'],fixed['tests'],fixed['validation']],
        human_interface_repair=dict(receipt=task['repair'],**{'original_implementation_failure' if trivia else 'original_review':engine.read(original_stage)},
            validation=fixed['validation'],attribution=('Supervisor one79byte comment removal; exact AST and original5 CASES unchanged. Original125 failed source-size admission; no prior candidate execution/paidReview. FIRST Review only, no newC/A, research change or gain claim.' if trivia else
                'Human-directed _plan only; no new Controller/Author, science change or gain claim. Inspect real zero-anchor risk.')))
    if trivia:
        service.authored[child['id']]['human_interface_repair'].update(
            complete_public_feedback=deepcopy(service.prior_feedback),comparison_parent=child['parent'],
            PROGRAM_AST_unchanged=True,original_source=fixed['original_source'],source_size_diagnosis=fixed['original_source_diagnosis'],
            original_Controller=fixed['original_decision'],original_Author=fixed['original_response'],
            validation_summary='65,571->65,492 bytes via exactly one79byte comment deletion; full AST and original5tests unchanged. Static admission only, original isolatedCASE and authenticReview must decide. No synthetic correctness/financialuse/learning claim.')
        if service.runtime['id']==TRIVIA144_ID:
            service.authored[child['id']]['human_interface_repair'].update(
                attribution='Supervisor COMMENT-token and STRING-external blankline removal only. Original143 failed before CASE/Review; original Author remains output_accepted=false. No prior admitted143 candidate, no C/A regeneration or new scientific hypothesis. FIRST Review, not provider retry or candidateH learning.',
                validation_summary='67,082->62,637 bytes; exact full AST and original3 full-exact CASES unchanged. Original143 decision/feedback identity preserved separately from this complete144 Review feedback. Calendar extraction AND cumulative-quarter derivation may confound attribution; verify source, financial definitions and real use. Static proof is not correctness or learning.',
                original_Controller_feedback=fixed['original_feedback'],original_runtime=fixed['original_runtime'],
                original_controller_context=fixed['original_controller_context'],original_author_context=fixed['original_author_context'])
        if service.runtime['id']==TRIVIA154_ID:
            service.authored[child['id']]['human_interface_repair'].update(
                attribution='Supervisor deletes ONLY one81byte model-appended COMMENT. Original153 failed65561byte source bounds before CASE/Review; Author remains output_accepted=false. Parent5e22 bytes, full AST and all4 original CASES unchanged. FIRST Review only, no newC/A, provider retry, new scientific child or H learning.',
                validation_summary='65,561->65,480 bytes within original65,536. Original153 decision/feedback and C/A Native contexts remain153; complete154 Review feedback separately bound. Financial/numerical/lag-vintage correctness remains unverified: original isolatedCASE/coldprobes/genuineReview must decide. No static-test-as-learning claim.',
                original_Controller_feedback=fixed['original_feedback'],original_runtime=fixed['original_runtime'],
                original_controller_context=fixed['original_controller_context'],original_author_context=fixed['original_author_context'])
    if service.runtime['id']==CASE146_ID:
        service.authored[child['id']]['human_interface_repair'].update(
            attribution='Supervisor correction of one incomplete expected request list only. Same145 PROGRAM/candidatee094/R/H/actual5e22, all5 CASE inputs and other4 expected objects unchanged. Original145 was a local CASE gate failure, not paid Review. No C/A regeneration, model retry, scientific child or autonomous H learning.',
            validation_summary='Original parent and child acquisition callables are AST-identical; CASE0 omitted parent offset20000. Five full-exact CASES fit original32KiB. Other4 synthetic outputs are no_targets: provenance accounting alone is not financial compatibility, correct publication dating, real target-bearing use or learning. Inspect original cold probes and downstream correctness; rejection remains possible.',
            exact_saved_replay=fixed['exact_saved_replay'],original_case_results=fixed['original_case_results'],
            independent_static_diagnosis=engine.read(fixed['static_diagnosis']),
            original_Controller_feedback=fixed['original_feedback'],complete_public_feedback=deepcopy(service.prior_feedback),
            comparison_parent=child['parent'],PROGRAM_unchanged=True)
    if service.runtime['id']==CASE_EXPECTATION_REVIEW_ID:
        service.authored[child['id']]['human_interface_repair'].update(
            attribution='Supervisor test-expectation serialization correction only under continuous routine-engineering authority. PROGRAM, candidate0994, R/H, actualeece parent and science unchanged; no paid Review had occurred106. Do not attribute this engineering to autonomous H learning.',
            validation_summary='Six full-exact expected objects within27145 bytes/unchanged32KiB. Original6 CASES and2/6 exact results preserved; all original intended fields match. Three synthetic historical financial cells independently checked. One missing-scope fixture uses literal originalT001 prefix, keeping issuer separation>800; original full5-target negative retained/audited. No live25/public forecast decision proof.',
            exact_saved_replay=fixed['exact_saved_replay'],original_case_results=fixed['original_case_results'],
            complete_public_feedback=deepcopy(service.prior_feedback),
            comparison_parent=child['parent'],PROGRAM_unchanged=True)
    if service.runtime['id']==FIXTURE_REVIEW_ID:
        service.authored[child['id']]['human_interface_repair'].update(
            attribution='Supervisor synthetic fixture/interface and exact-test serialization correction only. Same model112 PROGRAM/R/H and actual0994 parent; no previous paid Review or new C/A. Not autonomous H learning.',
            validation_summary='Four full-exact32731-byte formal cases: heading/unit positive plus duration/scale/ambiguous-segment negatives. All six corrected diagnostic executions and six original invalid-path failures remain evidence. Six synthetic financial cells and four negative guards independently audited; one original expected offset is wrong by2 characters. No live25 or public decision-use validation.',
            exact_saved_replay=fixed['exact_saved_replay'],original_case_results=fixed['original_case_results'],
            complete_public_feedback=deepcopy(service.prior_feedback),
            full_corrected_fixture_diagnostic=engine.read(fixed['full_diagnostic']),
            independent_synthetic_financial_audit=engine.read(fixed['financial_audit']),
            distinct_synthetic_financial_review=engine.read(fixed['distinct_financial_review']),
            comparison_parent=child['parent'],PROGRAM_unchanged=True)
    if service.runtime['id']==ACQUISITION_REVIEW_ID:
        service.authored[child['id']]['human_interface_repair'].update(
            attribution='Supervisor exact-test expectation serialization only. Same model118 R/H and03a parent; no prior paid Review or newC/A. Frontier-selection amendment is pending this candidate path, not active here.',
            validation_summary='All8 original inputs, first6 acquisition expectations unchanged. Last2 now full exact outputs;32244B<=32768. Independent synthetic-only audit below must not be represented as authenticated real filing evidence; a*64 source-hash fixtures are placeholders. Reported2/0 verified periods and conservative abstention are synthetic behavior, not real financial-source certification or learning.',
            exact_saved_replay=fixed['exact_saved_replay'],original_case_results=fixed['original_case_results'],
            complete_public_feedback=deepcopy(service.prior_feedback),
            fixture_diagnosis=engine.read(fixed['validation']),
            distinct_synthetic_financial_review=engine.read(fixed['distinct_financial_review']),
            comparison_parent=child['parent'],PROGRAM_unchanged=True)
    if service.runtime['id']==ANCHOR_REVIEW_ID:
        service.authored[child['id']]['human_interface_repair'].update(
            attribution='Human-authorized numerical-anchor acquisition/table decoding and event-date linkage only; unchanged original scientific hypothesis/H. Original52 reject and all history preserved.',
            validation_summary='Actual isolated real-material probes deliver4/5 anchors, T001 stillmissing; components/bridge unknown. Eight R calls share80 with finalpredictor, not all80exhausted. Fullfilehash not invented; Root checks exact originalmanifest/path/offset/quote.',
            concise_output_authority=ANCHOR_REPAIR_AUTHORITY)
    if service.runtime['id']==RATE_SCALE_REVIEW_ID:
        service.authored[child['id']]['human_interface_repair'].update(
            attribution='Human-authorized floating-rate/all-in distinction and pre-table monetary-scale correctness repair only. Original67 rejection and fees retained. No new Controller/Author, strategy/H/resource change or score gain claim.',
            validation_summary='Original4 examples plus9 Docker boundary tests cover thousands/millions, floating spread abstention including post-table footnotes, dated explicit all-in rate, ambiguous dates, spread-column and unknown/conflicting scales. USD alone is not magnitude. Inspect exact source and preserved assertions; tests do not guarantee financial correctness or acceptance.',
            comparison_parent=task['scaffold']['stable_id'],source_parent=fixed['original_candidate']['id'])
    if service.runtime['id']==CONCISE_REVIEW_ID:
        concise_review_metadata(task['repair'],fixed)
        service.authored[child['id']]['human_interface_repair']['concise_output_authority']=CONCISE_REVIEW_AUTHORITY
    reviewed=live['roles']['review'](deepcopy(child),repair_state(task,fixed),service.runtime['slots']['review'][0])
    return engine.save(Path(service.runtime['root'])/'repair-review.json',dict(candidate=child,review=reviewed,new_Controller_or_Author_called=False,repair=task['repair']))


def _contains_summary(payload, summary):
    def visit(value):
        if isinstance(value,dict):
            return value == summary or any(visit(v) for v in value.values())
        if isinstance(value,list): return any(visit(v) for v in value)
        if isinstance(value,str):
            start = value.find('{')
            if start >= 0:
                try: return visit(json.JSONDecoder().raw_decode(value[start:])[0])
                except (ValueError,RecursionError): return False
        return False
    return any(visit(row.get('content')) for row in payload.get('input',[])
        if type(row) is dict and row.get('role') == 'user')


def physical_requests(slot, *, summary=None):
    """Rejoin actual generation/count intents; hash raw bodies without decoding."""
    slot = Path(slot); evidence = []; requests = sorted(slot.glob('[0-9][0-9]-request.json'))
    if not requests: raise ValueError('No genuine model generation')
    intents = [(p,engine.read(engine.pin(p))) for p in slot.glob('http-*.intent.json')]
    for index,path in enumerate(requests,1):
        if path.name != f'{index:02d}-request.json': raise ValueError('Noncontiguous model generations')
        bound = engine.pin(path); request = engine.read(bound)
        matches = [(p,v) for p,v in intents if v.get('endpoint') == '/v1/responses'
            and v.get('budget_request_id') == request['request_id']]
        if len(matches) != 1: raise ValueError('Unique actual HTTP generation intent required')
        actual,intent = matches[0]
        maximum = intent.get('payload',{}).get('max_output_tokens')
        if (type(maximum) is not int or maximum <= 0
                or intent.get('complete_reservation') != request or intent.get('retry_allowed') is not False
                or intent['payload'] != dict(request['payload'],max_output_tokens=maximum,service_tier='default',store=False)
                or intent['request_receipt_sha256'] != bound['sha256']):
            raise ValueError('Actual HTTP payload differs from saved model request')
        if summary is not None and not _contains_summary(intent['payload'],summary):
            raise ValueError('Full Round0 feedback missing from an actual research-model input')
        numbered = engine.pin(slot/f'{index:02d}-response.json')
        prefix = Path(str(actual).removesuffix('.intent.json'))
        sidecar = engine.pin(Path(str(prefix)+'.response.json'))
        if sidecar['sha256'] != numbered['sha256']: raise ValueError('Physical/numbered response differs')
        raw = engine.pin(Path(str(prefix)+'.raw.bin'))
        count = engine.pin(slot/f'{index:02d}-count.json')
        counted = [(p,v) for p,v in intents if v.get('endpoint') == '/v1/responses/input_tokens'
            and v.get('payload',{}).get('input') == request['payload'].get('input')
            and engine.pin(Path(str(p).removesuffix('.intent.json')+'.response.json'))['sha256'] == count['sha256']]
        if not counted: raise ValueError('Actual counted input/numbered token count differs')
        evidence += [bound,engine.pin(actual),numbered,sidecar,raw,count,*[engine.pin(p) for p,v in counted]]
    return evidence


def _registered_author_parent(task, stages, seed):
    """Match Services.author's registered Native metadata, not code genealogy.

    selected_parent has already authenticated the actual descriptor and any
    incumbent anchor projection. Do not rewrite that historical projection or
    allow a different R/H/evidence/method record to pass Native replay.
    """
    packet = engine.read(stages[0]['output']['packet'])
    chosen = engine.read(stages[1]['output']['decision'])
    if (packet['population'] != task['scaffold'] or packet['feedback'] != task['feedback']
            or chosen['parent_pair_sha256'] != seed['id']):
        raise ValueError('Original Author packet/selected parent differs')
    registered = packet['population']['versions'][seed['id']]
    if (set(registered) != set(seed)
            or any(registered[k] != seed[k] for k in seed if k not in ('axis', 'parent'))
            or registered != seed and (registered['axis'] != 'baseline' or registered['parent'] is not None)):
        raise ValueError('Only authenticated incumbent anchor metadata may differ')
    return registered


def closed_evidence(result_binding, *, proposal):
    """Reuse original financial, Docker-cleanup and pure Native replay checks."""
    from earnings_population_runtime import _local, _sources
    from earnings_population_continuation import _Reader
    import earnings_population_completed as completed
    from earnings_native_failure import _cleanup
    from earnings_population_run import PYTHON
    from supervisor_harness.feedback_linked_loop import _read_pair
    path = Path(result_binding['path']); ident = path.parent.name
    expected_name = 'training-proposal-result.json' if proposal else 'clean-slate-window-result.json'
    if (path != training.ROOT/'attempts'/ident/expected_name
            or not re.fullmatch(r'edgar-population-20261016-[0-9]{2,}',ident)):
        raise ValueError('Canonical new clean-slate result required')
    result = _local(result_binding); runtime_binding = result['runtime']; value = _local(runtime_binding)
    if (not enabled(value) or value['id'] != ident or runtime_binding['path'] !=
            str(training.ROOT/'inputs'/ident/'runtime-reviewed.json')
            or (path.parent/('training-proposal-failure.json' if proposal else 'clean-slate-window-failure.json')).exists()
            or result.get('retry_allowed') is not False or result.get('improvement_proven') is not False):
        raise ValueError('Original successful clean result/runtime required')
    _sources(value); study(value)
    task, scope = read_task(value)
    review = _local(value['review'])
    if (review.get('verdict') != 'PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY'
            or review.get('blocking_findings') != []
            or str(review.get('reviewer','')).strip().lower() in ('','root','/root')
            or review.get('source_commit') != value['source_commit']
            or review.get('reviewed_configuration_sha256') != digest({k:v for k,v in value.items() if k!='review'})):
        raise ValueError('Original independent runtime review changed')
    if (task['mode'] in ('proposal','repair_review')) != proposal: raise ValueError('Proposal/evaluation route differs')
    token = hashlib.sha256(ident.encode()).hexdigest()
    registry = Path(value['ledger']).parent/'.capacity-runtime-claims'
    claim = engine.pin(registry/(token+'.json')); owner_bound = engine.pin(registry/(token+'.result.json'))
    owner = engine.read(owner_bound)
    if (engine.read(claim).get('runtime') != runtime_binding or owner.get('runtime') != runtime_binding
            or owner.get('status') != 'COMPLETED_COMPONENT_CONTEXT' or owner.get('error_type') is not None
            or owner.get('retry_allowed') is not False):
        raise ValueError('Genuine original owner closure required, never synthesize missing receipt')
    clock = engine.read(owner['clock'])
    if any(clock.get(k) != value[k] for k in ('source_commit','cutoff_utc','deadline_utc')):
        raise ValueError('Original closed owner clock differs')
    expected = {}; evidence = [result_binding,runtime_binding,claim,owner_bound]
    feedback = engine.read(task['feedback'])
    if proposal and task['mode']=='repair_review':
        if result.get('status') != 'PROPOSAL_REVIEWED_ACCEPTED': raise ValueError('No accepted fresh proposal')
        fixed=repair_metadata(task['repair'],ident);record=_local(result['proposal_stages'][0])
        child=fixed['candidate']
        if (result['proposal_stages']!=[engine.pin(path.parent/'repair-review.json')]
                or record['candidate']!=child or record['review']['accepted_for_exploration'] is not True
                or record['new_Controller_or_Author_called'] is not False
                or any(Path(slot).exists() for role in ('controller','author','forecast') for slot in value['slots'][role])):
            raise ValueError('Actual new Review only, no C/A or forecast permitted')
        expected['review-01']=dict(role='review',company_id=task['company_id'],version=child)
        evidence+=physical_requests(path.parent/'roles/review-01',summary=feedback if case_contract_review(ident) else None)
    elif proposal:
        if result.get('status') != 'PROPOSAL_REVIEWED_ACCEPTED': raise ValueError('No accepted fresh proposal')
        stages = [_read_pair(path.parent/'loop'/f'round-0001-{stage}.done.json')
            for stage in ('input','controller','implement','source_review')]
        stage_bindings = [engine.pin(path.parent/'loop'/f'round-0001-{stage}.done.json')
            for stage in ('input','controller','implement','source_review')]
        if (result.get('result') != dict(status='stopped',completed_rounds=0,round_index=1,stage='execute')
                or result.get('proposal_stages') != stage_bindings
                or any(Path(s).exists() for s in value['slots']['forecast'])):
            raise ValueError('Genuine four-stage stop before any forecast required')
        child = stages[2]['output']['candidate']; reviewed = stages[3]['output']
        origin=round2_origin(value) if second_round(value) else None
        seed=selected_parent(task['scaffold'],origin)
        if (child is None or reviewed.get('accepted_for_exploration') is not True
                or child['parent'] != seed['id']
                or child['id'] in task['scaffold']['versions'] or child.get('author') != 'model:DeltaAuthor'):
            raise ValueError('New model-authored candidate and genuine Review required')
        for role in ('controller','author','review'):
            expected[role+'-01'] = dict(role=role,company_id=task['company_id'],version=child if role=='review' else _registered_author_parent(task,stages,seed) if role=='author' else seed)
            evidence += physical_requests(path.parent/'roles'/(role+'-01'),
                summary=feedback if role in ('controller','author') else None)
    else:
        if result.get('status') != 'COMPLETED_CLEAN_SLATE_CANDIDATE_WINDOW': raise ValueError('Not a completed candidate window')
        child = load_frozen(task['frozen_candidate'])['candidate']
        rows = result.get('result',{}).get('results')
        from earnings_population_company_batch import enabled as batch_enabled, verify_closed, completed_companies
        companies=completed_companies(value) if batch_enabled(value) else task['company_ids']
        if (type(rows) is not list or len(rows)!=len(companies)
                or [r.get('company_id') for r in rows]!=companies
                or any(r.get('arm')!='candidate' for r in rows)):
            raise ValueError('Exactly one candidate result per admitted company required')
        for i,(company,item) in enumerate(zip(companies,rows)):
            row=item['result'];name=f'forecast-01-{i:02d}'
            if row['version_id']!=child['id']:raise ValueError('Frozen version differs')
            expected[name]=dict(role='forecast',company_id=company,version=child,forecast_result=row)
            evidence+=physical_requests(path.parent/'roles'/name)
        if batch_enabled(value):
            evidence+=verify_closed(runtime_binding,value,rows)['evidence']
    for name,item in expected.items():
        guard = engine.pin(path.parent/'role-validation'/(name+'.json')); checked = engine.read(guard)
        if (checked.get('runtime') != runtime_binding or checked.get('selected_version_id') != item['version']['id']
                or checked.get('entry_full_audit') != 'PASS' or checked.get('exit_full_audit') != 'PASS'
                or checked.get('exit_current_guard') != 'PASS' or checked.get('output_accepted') is not True):
            raise ValueError('Original selected-role entry/exit validation missing')
        evidence.append(guard)
    reader = _Reader(training.ROOT,Path(value['ledger']),e.REPO,ident); reader.register_sources(value)
    reader.extra.update(Path(b['path']) for b in (claim,owner_bound,SPLIT,ROUND0,value['review'],
        value['budget_amendment'],value['model_budget_amendment']))
    evidence += completed._budget(reader,value,owner,result)
    evidence += [r['result'] for r in _cleanup(path.parent, runtime=value)]
    evidence += completed._native(reader,Path('/private/tmp')/('market-rsi-'+ident),runtime_binding,
        value,expected,tasks.resident(task['company_id']),PYTHON,training_scope=scope)
    return dict(candidate=child,runtime=value,task=task,evidence=evidence,result=result)


def freeze(result_binding, output):
    verified = closed_evidence(result_binding,proposal=True); value = verified['runtime']
    descriptor = dict(schema='earnings_training25_clean_frozen_candidate_v1',policy=POLICY,
        authority=value['sources'][PLAN],split=SPLIT,round0=ROUND0,
        training=training.load_scope(SPLIT)['training'],candidate=verified['candidate'],
        proposal=result_binding,source_commit=value['source_commit'],
        forecast_sources={k:value['sources'][k] for k in ('forecaster','tools/earnings_entry.py',
            'tools/earnings_open_worker.py','tools/earnings_population_execution.py')},
        forecast_limits=value['limits']['forecast'],rates=value['rates'])
    if second_round(value):descriptor.update(learning_round=value['clean_learning_round'],parent_basis=verified['task']['round2_origin'])
    if Path(output).parent != training.ROOT: raise ValueError('Own immutable descriptor path required')
    return engine.save(Path(output),descriptor)


def backpressure_rebind(binding):
    return binding.get('path')==str(training.ROOT/'TRAIN25-CLEAN71-REBIND-FROZEN-CANDIDATE.json')


def frozen_inputs(binding):
    """Keep the exact prospective rebind and human authority fresh per send."""
    descriptor=engine.read(binding)
    from earnings_population_additional_execution import selected,inputs
    if selected(binding):return inputs(binding,descriptor)
    if 'execution_rebind' not in descriptor:return [binding]
    if native137_rebind(binding):return [binding,descriptor['execution_rebind'],NATIVE137_CLOSURE,NATIVE137_ARCHIVE]
    if descriptor.get('learning_round')==4:return [binding,descriptor['execution_rebind'],WINDOW_YIELD_AUTHORITY]
    extra=[BACKPRESSURE_AUTHORITY,engine.read(BACKPRESSURE_AUTHORITY)['partial_closure']] if backpressure_rebind(binding) else []
    return [binding,descriptor['execution_rebind'],SLOT_REBIND_AUTHORITY]+extra


def window_execution_rebind(binding,descriptor):
    """Authenticate accepted73 from its exact archive; no repeated old Native gate."""
    from earnings_population_runtime import _local
    from supervisor_harness.feedback_linked_loop import _read_pair
    authority=_local(WINDOW_YIELD_AUTHORITY)
    if (binding['path']!=str(training.ROOT/'TRAIN25-CLEAN74-REBIND-FROZEN-CANDIDATE.json')
            or descriptor.get('learning_round')!=4
            or descriptor.get('execution_rebind',{}).get('path')!=str(training.ROOT/'TRAIN25-CLEAN74-EXECUTION-REBIND.json')):
        raise ValueError('Finite accepted73 window-yield rebind required')
    receipt=_local(descriptor['execution_rebind']);old=_local(authority['accepted_descriptor'])
    closure=_local(authority['accepted_closure']);archive=_local(authority['accepted_private_Git'])
    runtime=_local(closure['runtime']);result=_local(closure['terminal'])
    if (descriptor!=dict(old,source_commit=receipt.get('new_source_commit'),execution_rebind=descriptor['execution_rebind'])
            or receipt.get('authority')!=WINDOW_YIELD_AUTHORITY or receipt.get('original_descriptor')!=authority['accepted_descriptor']
            or receipt.get('original_source_commit')!=authority['old_source_commit']
            or runtime['source_commit']!=old['source_commit'] or old['source_commit']!=authority['old_source_commit']
            or old['candidate']['id']!=authority['candidate_id'] or closure.get('candidate')!=old['candidate']
            or closure.get('frozen')!=authority['accepted_descriptor'] or closure.get('status')!='VERIFIED_ACCEPTED_PROPOSAL'
            or closure.get('original_true_exit')!=0 or closure.get('original_accepted_gate_passed') is not True
            or closure.get('pending_count')!=0 or closure.get('all_owned_settled') is not True
            or result.get('status')!='PROPOSAL_REVIEWED_ACCEPTED' or len(result.get('proposal_stages',[]))!=4
            or _read_pair(Path(result['proposal_stages'][2]['path']))['output']['candidate']!=old['candidate']
            or _read_pair(Path(result['proposal_stages'][3]['path']))['output']['accepted_for_exploration'] is not True
            or archive.get('commit')!=authority['accepted_private_commit'] or archive.get('every_blob_readback_verified') is not True
            or type(receipt.get('new_source_commit')) is not str or not re.fullmatch('[0-9a-f]{40}',receipt['new_source_commit'])
            or receipt['new_source_commit']==runtime['source_commit']):
        raise ValueError('Original accepted73/source/Review cannot be substituted')
    for bound in (authority['accepted_descriptor'],authority['accepted_closure'],closure['runtime'],closure['terminal'],*result['proposal_stages']):
        alias='original/'+str(Path(bound['path']).relative_to(training.ROOT))
        if archive['artifacts'].get(alias)!=bound:raise ValueError('Original73 archive binding missing')
        raw=subprocess.run(['git','show',archive['commit']+':'+alias],cwd=e.REPO,check=True,capture_output=True).stdout
        if raw!=e.checked(bound):raise ValueError('Original73 immutable blob differs')
    allowed=authority['allowed_production_changes'];sources=receipt.get('sources',{})
    if (allowed!=['tools/earnings_population_clean_slate.py','tools/earnings_population_company_batch.py']
            or set(sources)!=set(runtime['sources']) or sorted(k for k in sources if sources[k]!=runtime['sources'][k])!=allowed):
        raise ValueError('Only two window/closure adapters may change')
    changed=subprocess.run(['git','diff','--name-only',runtime['source_commit'],receipt['new_source_commit']],
        cwd=e.REPO,check=True,capture_output=True,text=True).stdout.splitlines()
    if sorted(changed)!=sorted(allowed+authority['allowed_test_changes']):raise ValueError('Window-yield checkpoint scope exceeded')
    for name,bound in sources.items():
        if bound['path']!=runtime['sources'][name]['path']:raise ValueError('Rebound source path changed')
        e.checked(bound)
        if name in allowed:
            raw=subprocess.run(['git','show',receipt['new_source_commit']+':'+name],cwd=e.REPO,check=True,capture_output=True).stdout
            if raw!=e.checked(bound):raise ValueError('Committed window adapter differs')
    for axis in ('R','H'):e.checked(old['candidate'][axis])
    return dict(candidate=old['candidate'],runtime=runtime,task=dict(round2_origin=old['parent_basis']))


NATIVE137_CLOSURE = dict(path=str(training.ROOT/'TRAIN25-CLEAN137-CLOSED-CLOSURE.json'),
    sha256='38ba90c743e0dfb3d9248e6de884894a1b84300a75109ddeaac4c4d72414958f')
NATIVE137_ARCHIVE = dict(path=str(training.ROOT/'TRAIN25-CLEAN137-CLOSED-GIT.json'),
    sha256='ee2ad3e1aac1d255e28609976172f0a187f1b020f790d7055f6d3b0ee9ba61d0')


def native137_rebind(binding):
    return binding.get('path')==str(training.ROOT/'TRAIN25-CLEAN138-REBIND-FROZEN-CANDIDATE.json')


def native137_execution_rebind(binding, descriptor):
    """Finite historical137 closure -> prospective unchanged forecast sources.

    The original gate failed; its explicitly corrected saved-evidence gate and
    true owner closure are sealed in private Git. Never rerun C/A/Review/Native,
    rewrite old runtime/source/ancestry, or call this an unmodified gate PASS.
    """
    from earnings_population_runtime import _local
    from supervisor_harness.feedback_linked_loop import _read_pair
    if (not native137_rebind(binding) or descriptor.get('learning_round')!=15
            or descriptor.get('execution_rebind',{}).get('path')!=str(training.ROOT/'TRAIN25-CLEAN138-EXECUTION-REBIND.json')):
        raise ValueError('Finite accepted137 metadata-closure rebind required')
    closure=_local(NATIVE137_CLOSURE);archive=_local(NATIVE137_ARCHIVE)
    old=_local(closure['frozen']);runtime=_local(closure['runtime']);result=_local(closure['terminal'])
    receipt=_local(descriptor['execution_rebind'])
    if (closure.get('status')!='VERIFIED_ACCEPTED_PROPOSAL' or closure.get('original_true_exit')!=0
            or closure.get('original_accepted_gate_passed') is not False
            or closure.get('corrected_native_metadata_gate_passed') is not True
            or closure.get('all_owned_settled') is not True or closure.get('pending_count')!=0
            or closure.get('pending_full_reserved_nano_usd')!=0
            or archive.get('commit')!='eb4a765b62aedc7e2ef0fc4d9ececf65867351a6'
            or archive.get('every_blob_readback_verified') is not True
            or old['source_commit']!=runtime['source_commit'] or runtime['source_commit']!='772e5a6746513666902c52f64924476196ee8c7b'
            or old['candidate']!=closure['candidate'] or old['candidate']['id']!='37af4ddad70dad464e6a795fd8a4eec9425c283e1c18f583ff0287c8d16eb971'
            or old['proposal']!=closure['terminal'] or result.get('status')!='PROPOSAL_REVIEWED_ACCEPTED'
            or receipt.get('schema')!='edgar25_native137_metadata_execution_rebind_v1'
            or receipt.get('original_descriptor')!=closure['frozen']
            or receipt.get('corrected_closure')!=NATIVE137_CLOSURE or receipt.get('archive')!=NATIVE137_ARCHIVE
            or descriptor!=dict(old,source_commit=receipt.get('new_source_commit'),execution_rebind=descriptor['execution_rebind'])
            or type(receipt.get('new_source_commit')) is not str or not re.fullmatch('[0-9a-f]{40}',receipt['new_source_commit'])):
        raise ValueError('Original137 accepted code/corrected closure/resources cannot be substituted')
    bounds=[closure['frozen'],NATIVE137_CLOSURE,closure['runtime'],closure['terminal'],
        closure['closure_correction'],closure['original_failed_closure'],*result['proposal_stages']]
    for bound in bounds:
        alias='original/'+str(Path(bound['path']).relative_to(training.ROOT))
        if archive['artifacts'].get(alias)!=bound:raise ValueError('Original137 archive binding missing')
        raw=subprocess.run(['git','show',archive['commit']+':'+alias],cwd=e.REPO,check=True,capture_output=True).stdout
        if raw!=e.checked(bound):raise ValueError('Original137 immutable blob differs')
    stages=[_read_pair(Path(b['path'])) for b in result['proposal_stages']]
    if (len(stages)!=4 or stages[2]['output']['candidate']!=old['candidate']
            or stages[3]['output'].get('accepted_for_exploration') is not True):
        raise ValueError('Original137 genuine Author/Review differs')
    sources=receipt.get('sources',{});allowed=['tools/earnings_population_clean_slate.py']
    if (set(sources)!=set(runtime['sources'])
            or sorted(k for k in sources if sources[k]!=runtime['sources'][k])!=allowed):
        raise ValueError('Only Native metadata closure adapter may change')
    changed=subprocess.run(['git','diff','--name-only',runtime['source_commit'],receipt['new_source_commit']],
        cwd=e.REPO,check=True,capture_output=True,text=True).stdout.splitlines()
    if sorted(changed)!=sorted(allowed+['tests/test_earnings_clean_author_native_metadata.py']):
        raise ValueError('Native metadata repair checkpoint scope exceeded')
    for name,bound in sources.items():
        if bound['path']!=runtime['sources'][name]['path']:raise ValueError('Rebound source path changed')
        raw=e.checked(bound)
        if name in allowed:
            relative=str(Path(bound['path']).relative_to(e.REPO))
            committed=subprocess.run(['git','show',receipt['new_source_commit']+':'+relative],cwd=e.REPO,check=True,capture_output=True).stdout
            if committed!=raw:raise ValueError('Rebound source checkpoint differs')
    for axis in ('R','H'):e.checked(old['candidate'][axis])
    return dict(candidate=old['candidate'],runtime=runtime,task=dict(round2_origin=old['parent_basis']))


def slot_execution_rebind(binding, descriptor):
    """Finite human-approved adapter rebind; never relabel the original Review.

    Authenticate the already closed68 evidence against its immutable private Git
    instead of executing old code/current-source admission or another Review.
    R/H, all four forecast sources, data and resources remain identical.
    """
    from earnings_population_additional_execution import selected,verify
    if selected(binding):return verify(binding,descriptor)
    if native137_rebind(binding):return native137_execution_rebind(binding,descriptor)
    if descriptor.get('learning_round')==4:return window_execution_rebind(binding,descriptor)
    from earnings_population_runtime import _local
    pending=backpressure_rebind(binding);authority_binding=BACKPRESSURE_AUTHORITY if pending else SLOT_REBIND_AUTHORITY
    authority=_local(authority_binding);number=71 if pending else 70
    if (binding['path']!=str(training.ROOT/f'TRAIN25-CLEAN{number}-REBIND-FROZEN-CANDIDATE.json')
            or descriptor.get('learning_round')!=3
            or descriptor.get('execution_rebind',{}).get('path')!=str(training.ROOT/f'TRAIN25-CLEAN{number}-EXECUTION-REBIND.json')
            or authority.get('schema')!=('edgar25_once_pending_backpressure_execution_rebind_authority_v1' if pending else 'edgar25_once_slot_execution_rebind_direct_authority_v1')
            or authority.get('answer')!=('agree. get back to the co-evolve progress' if pending else 'yes')
            or authority.get('direct_human_in_this_chat') is not True):
        raise ValueError('Exact directly authorized once slot rebind required')
    if pending and (authority.get('previous_slot_authority')!=SLOT_REBIND_AUTHORITY
            or authority.get('retry_only_failed_unscored_companies')!=['CIK0000063296']
            or authority.get('window_cap_nano_usd')!=5000000000 or authority.get('window_minutes')!=90
            or authority.get('max_concurrent_companies')!=8):raise ValueError('Exact unchanged pending-wait authority required')
    receipt=_local(descriptor['execution_rebind']);old=_local(authority['accepted_descriptor'])
    closure=_local(authority['accepted_closure']);archive=_local(authority['accepted_private_Git'])
    runtime=_local(closure['runtime']);result=_local(closure['terminal']);record=_local(result['result'])
    expected=dict(old,source_commit=receipt.get('new_source_commit'),execution_rebind=descriptor['execution_rebind'])
    if (descriptor!=expected or receipt.get('schema')!=('edgar25_pending_backpressure_execution_rebind_v1' if pending else 'edgar25_single_slot_execution_rebind_v1')
            or receipt.get('authority')!=authority_binding or receipt.get('original_descriptor')!=authority['accepted_descriptor']
            or receipt.get('original_source_commit')!=authority['old_source_commit']
            or runtime['source_commit']!=authority['old_source_commit'] or old['source_commit']!=runtime['source_commit']
            or old['candidate']['id']!=authority['candidate_id'] or old['candidate']!=record['candidate']
            or closure.get('candidate')!=old['candidate'] or closure.get('frozen')!=authority['accepted_descriptor']
            or closure.get('status')!='VERIFIED_ACCEPTED_PROPOSAL' or closure.get('original_true_exit')!=0
            or closure.get('original_accepted_gate_passed') is not True or closure.get('pending_count')!=0
            or closure.get('all_owned_settled') is not True or result.get('status')!='PROPOSAL_REVIEWED_ACCEPTED'
            or record.get('new_Controller_or_Author_called') is not False
            or record.get('review',{}).get('accepted_for_exploration') is not True
            or archive.get('commit')!=authority['accepted_private_commit'] or archive.get('every_blob_readback_verified') is not True
            or type(receipt.get('new_source_commit')) is not str or not re.fullmatch('[0-9a-f]{40}',receipt['new_source_commit'])
            or receipt['new_source_commit']==runtime['source_commit']):
        raise ValueError('Original accepted candidate/Review/Source rebind differs')
    # Check original bytes, not only a new JSON declaration of old success.
    for bound in (authority['accepted_descriptor'],authority['accepted_closure'],closure['runtime'],closure['terminal'],result['result']):
        alias='original/'+str(Path(bound['path']).relative_to(training.ROOT))
        if archive['artifacts'].get(alias)!=bound:raise ValueError('Original archive binding missing')
        raw=subprocess.run(['git','show',archive['commit']+':'+alias],cwd=e.REPO,check=True,capture_output=True).stdout
        if raw!=e.checked(bound):raise ValueError('Immutable accepted68 bytes differ')
    allowed=authority['allowed_production_changes'];sources=receipt.get('sources',{})
    if (allowed!=['tools/earnings_population_clean_slate.py','tools/earnings_population_company_batch.py']
            or set(sources)!=set(runtime['sources'])
            or sorted(k for k in sources if sources[k]!=runtime['sources'][k])!=allowed):
        raise ValueError('Only the two approved adapter sources may change')
    for name,bound in sources.items():
        if bound['path']!=runtime['sources'][name]['path']:raise ValueError('Rebound source path changed')
        e.checked(bound)
    changed=subprocess.run(['git','diff','--name-only',runtime['source_commit'],receipt['new_source_commit']],
        cwd=e.REPO,check=True,capture_output=True,text=True).stdout.splitlines()
    if sorted(changed)!=sorted(allowed+authority['allowed_test_changes']):
        raise ValueError('Source checkpoint exceeds finite slot repair')
    for name in allowed:
        raw=subprocess.run(['git','show',receipt['new_source_commit']+':'+name],cwd=e.REPO,check=True,capture_output=True).stdout
        if raw!=e.checked(sources[name]):raise ValueError('Committed repaired adapter differs')
    for axis in ('R','H'):e.checked(old['candidate'][axis])
    return dict(candidate=old['candidate'],runtime=runtime,task=dict(round2_origin=old['parent_basis']))


def load_frozen(binding):
    from earnings_population_runtime import _local
    descriptor = _local(binding)
    if (set(descriptor) != {'schema','policy','authority','split','round0','training','candidate',
            'proposal','source_commit','forecast_sources','forecast_limits','rates'} | (
                {'learning_round','parent_basis'} if parent_round(descriptor.get('learning_round')) else set()) | (
                {'execution_rebind'} if 'execution_rebind' in descriptor else set())
            or descriptor['schema'] != 'earnings_training25_clean_frozen_candidate_v1'
            or descriptor['policy'] != POLICY or descriptor['split'] != SPLIT or descriptor['round0'] != ROUND0
            or descriptor['training'] != training.load_scope(SPLIT)['training']):
        raise ValueError('Exact frozen full25 candidate descriptor required')
    key=digest(binding)
    if parent_round(descriptor.get('learning_round')) and key in _ROUND2_FROZEN:
        if _ROUND2_FROZEN[key]!=descriptor:raise ValueError('Current frozen descriptor changed')
        for axis in ('R','H'):e.checked(descriptor['candidate'][axis])
        e.checked(descriptor['parent_basis'])
        if 'execution_rebind' in descriptor:
            for bound in frozen_inputs(binding)[1:]:e.checked(bound)
        return descriptor  # Complete proposal verified once in THIS process; current role/source/data guards remain.
    rebound='execution_rebind' in descriptor
    original = slot_execution_rebind(binding,descriptor) if rebound else closed_evidence(descriptor['proposal'],proposal=True)
    value = original['runtime']
    if value.get('clean_learning_round',1)!=descriptor.get('learning_round',1):
        raise ValueError('Frozen logical round differs from genuine proposal')
    if (descriptor['candidate'] != original['candidate'] or not rebound and descriptor['source_commit'] != value['source_commit']
            or descriptor['authority'] != value['sources'][PLAN] or descriptor['rates'] != value['rates']
            or descriptor['forecast_limits'] != value['limits']['forecast']
            or descriptor['forecast_sources'] != {k:value['sources'][k] for k in
                ('forecaster','tools/earnings_entry.py','tools/earnings_open_worker.py','tools/earnings_population_execution.py')}):
        raise ValueError('Frozen descriptor differs from actual new proposal/resources')
    if parent_round(descriptor.get('learning_round')):
        if not second_round(value) or descriptor['parent_basis']!=original['task']['round2_origin']:
            raise ValueError('Round2 frozen parent basis differs')
        _ROUND2_FROZEN[key]=deepcopy(descriptor)
    return descriptor


def preserved70_rows(descriptor, partial_binding):
    """Consume seven immutable scored originals, not a successful failed window.

    No original70 full gate/Native/scorer replay. Authenticate only saved public
    evidence against its exact private Git; retain original runtime/Source/exit.
    """
    authority=engine.read(BACKPRESSURE_AUTHORITY)
    if partial_binding!=authority['partial_closure']:raise ValueError('Exact authorized partial70 closure required')
    archive=engine.read(engine.pin(training.ROOT/'TRAIN25-CLEAN70-CLOSED-GIT.json'))
    if archive.get('commit')!=authority['partial_private_commit'] or archive.get('every_blob_readback_verified') is not True:
        raise ValueError('Original partial70 private archive required')
    def saved(bound):
        path=Path(bound['path'])
        if not path.is_relative_to(training.ROOT):raise ValueError('Own saved public evidence only')
        alias='original/'+str(path.relative_to(training.ROOT))
        if archive['artifacts'].get(alias)!=bound:raise ValueError('Original partial70 archive binding missing')
        raw=subprocess.run(['git','show',archive['commit']+':'+alias],cwd=e.REPO,check=True,capture_output=True).stdout
        if raw!=e.checked(bound):raise ValueError('Original partial70 archived bytes differ')
        return e.strict_json(raw)
    audit=saved(partial_binding);runtime=saved(audit['runtime']);old=saved(audit['frozen']);batch=saved(audit['batch'])
    if (audit.get('original_true_exit')!=1 or audit.get('status')!='FAILED_NO_RETRY'
            or audit.get('all_owned_settled') is not True or audit.get('pending_count')!=0
            or audit.get('window_scored')!=7 or audit.get('owned_generations')!=181
            or audit.get('owned_cost_nano_usd')!=3351981600
            or audit['candidate']!=descriptor['candidate'] or audit['source_commit']!=authority['previous_execution_source']
            or batch.get('failed_companies')!=['CIK0000063296'] or batch.get('not_measured')!=['CIK0000069633']
            or any(descriptor[k]!=old[k] for k in old if k not in ('source_commit','execution_rebind'))
            or descriptor['forecast_sources']!={k:runtime['sources'][k] for k in descriptor['forecast_sources']}
            or descriptor['rates']!=runtime['rates'] or descriptor['forecast_limits']!=runtime['limits']['forecast']):
        raise ValueError('Partial70 identity/resources/failure boundary differs')
    rows=[];expected=authority['preserve_completed_companies']
    for worker in batch['workers']:
        company=worker['company_id']
        if company not in expected:continue
        closed=saved(worker['closure']);checkpoint=saved(worker['checkpoint']);exit_record=saved(worker['process_exit_receipt'])
        guard=saved(closed['role_guard'])
        if (worker['true_exit_code']!=0 or exit_record['true_exit_code']!=0
                or checkpoint.get('status')!='COMPLETED_SCORED' or checkpoint.get('error_type') is not None
                or checkpoint.get('candidate_id')!=descriptor['candidate']['id']
                or checkpoint.get('runtime')!=audit['runtime'] or closed.get('runtime')!=audit['runtime']
                or closed.get('company_id')!=company or closed.get('checkpoint')!=worker['checkpoint']
                or guard.get('runtime')!=audit['runtime'] or guard.get('selected_version_id')!=descriptor['candidate']['id']
                or guard.get('output_accepted') is not True
                or any(guard.get(k)!='PASS' for k in ('entry_full_audit','exit_full_audit','exit_current_guard'))
                or not closed['fees'] or any(f['status']!='settled' for f in closed['fees'])):
            raise ValueError('Original partial70 company is not closed/scored')
        index=runtime['companies'].index(company);slot=Path(runtime['slots']['forecast'][index])
        requests=sorted(slot.glob('[0-9][0-9]-request.json'))
        for path in (slot/'population-public-feedback.json',slot/'predictions.json',requests[-1],
                requests[-1].with_name(requests[-1].name.replace('-request.json','-response.json'))):saved(engine.pin(path))
        row=_comparison_row(descriptor,runtime,company,index,checkpoint['result'],worker['closure'])
        if row!=next(r for r in audit['window_comparison_rows'] if r['company_id']==company):
            raise ValueError('Original partial70 public row differs')
        row.update(runtime=audit['runtime'],source_commit=runtime['source_commit'],execution_descriptor=audit['frozen'],
            slot=str(slot),preserved_partial=True)
        rows.append(row)
    if [r['company_id'] for r in rows]!=expected:raise ValueError('Exactly seven unique original70 scores required')
    return rows


def compare(descriptor_binding, window_results, *, preserved_partial=None):
    descriptor = load_frozen(descriptor_binding); rows = []
    if preserved_partial is not None:
        if not backpressure_rebind(descriptor_binding):raise ValueError('Finite partial70 receiver only')
        rows=preserved70_rows(descriptor,preserved_partial)
    for binding in window_results:
        verified = closed_evidence(binding,proposal=False)
        task = verified['task']; runtime = verified['runtime']
        if task['frozen_candidate'] != descriptor_binding: raise ValueError('Another frozen candidate')
        for index,item in enumerate(verified['result']['result']['results']):
            company=task['company_ids'][index]
            row=_comparison_row(descriptor,runtime,company,index,item['result'],binding)
            if backpressure_rebind(descriptor_binding):
                row.update(runtime=verified['result']['runtime'],source_commit=runtime['source_commit'],execution_descriptor=descriptor_binding,
                    slot=runtime['slots']['forecast'][index],preserved_partial=False)
            rows.append(row)
    ids = [r['company_id'] for r in rows]
    if len(ids) != len(set(ids)) or not set(ids) <= set(descriptor['training']):
        raise ValueError('Duplicate or nontraining scored company')
    complete = len(rows) == 25
    mean = sum(r['points'] for r in rows)/25 if complete else None
    parent_mean=engine.read(descriptor['parent_basis'])['prior_mean'] if parent_round(descriptor.get('learning_round')) else 3.0
    threshold=parent_mean
    if continuous_round(descriptor.get('learning_round')):
        from earnings_population_coevolution import selection_threshold
        threshold=selection_threshold(engine.read(descriptor['parent_basis']))
    result=dict(schema='earnings_training25_clean_comparison_v1',descriptor=descriptor_binding,
        rows=rows,scored=len(rows),not_measured=25-len(rows),round0_mean=3.0,candidate_mean=mean,
        decision=('ADOPT_CANDIDATE' if mean>threshold else ('RETAIN_ADOPTED_PARENT' if parent_round(descriptor.get('learning_round')) else 'RETAIN_ROUND0')) if complete else 'INCOMPLETE_NO_SELECTION',
        next_mutation_allowed=complete,scope='Discovery, historical Round0 comparison; not generalization or causal-method proof.')
    if parent_round(descriptor.get('learning_round')):
        origin=engine.read(descriptor['parent_basis'])
        result.update(logical_round=descriptor['learning_round'],parent_mean=origin['prior_mean'],parent_version_id=origin['parent']['id'],
            next_mutation_allowed=False,scope=('Discovery versus saved full25 adopted parent; scheduler changed by human, no causal attribution or generalization. '
                + ('Direct next-group03a authority; complete25 feedback before next mutation, no extra budget.' if descriptor['learning_round'] in (5,6,7) else
                    'No automatic mutation; only directly authorized bounded followups3/4.' if descriptor['learning_round'] in (3,4) else 'No further round authorized.')))
        if continuous_round(descriptor['learning_round']):
            result.update(next_mutation_allowed=complete,
                selection_threshold=threshold,selection_incumbent_descriptor=origin['incumbent_descriptor'],
                selection_incumbent_mean=origin['incumbent_mean'],
                scope='Discovery versus saved parent/Round0; complete feedback and meaningful-next/original-budget admission, not a count stop. No causal/generalization claim.')
    return result


def _comparison_row(descriptor,runtime,company,index,result,binding):
        slot = Path(runtime['slots']['forecast'][index])
        public = engine.read(engine.pin(slot/'population-public-feedback.json'))
        requests = sorted(slot.glob('[0-9][0-9]-request.json'))
        predictions = e.strict_predictions(engine.read(engine.pin(requests[-1].with_name(
            requests[-1].name.replace('-request.json','-response.json')))),training.TARGETS)
        if (engine.read(engine.pin(slot/'predictions.json')) != predictions
                or public['version_id'] != descriptor['candidate']['id']
                or public['company_id'] != company or public['points'] != result['points']
                or [r['target_id'] for r in public['target_scores']] != training.TARGETS
                or sum(r['points_awarded'] for r in public['target_scores']) != public['points']
                or any(r['points_awarded'] not in (0,.5,1) for r in public['target_scores'])):
            raise ValueError('Original final prediction/public awards differ')
        if parent_round(descriptor.get('learning_round')):
            origin=engine.read(descriptor['parent_basis'])
            baseline=next(r for r in engine.read(origin.get('parent_feedback',origin['public_feedback']))['rows'] if r['company_id']==company)
        else:baseline = next(r for r in round0_feedback()['rows'] if r['company_id']==company)
        predicted = {r['target_id']:r['predicted_value'] for r in predictions['predictions']}
        awards = {r['target_id']:r['points_awarded'] for r in public['target_scores']}
        if parent_round(descriptor.get('learning_round')):
            targets=[dict(target_id=r['target_id'],parent_prediction=r['predicted_value'],candidate_prediction=predicted[r['target_id']],
                parent_award=r['points_awarded'],candidate_award=awards[r['target_id']],delta=awards[r['target_id']]-r['points_awarded']) for r in baseline['targets']]
            return dict(company_id=company,points=public['points'],parent_points=baseline['points'],delta=public['points']-baseline['points'],
                targets=targets,regressions=[r['target_id'] for r in targets if r['delta']<0],result=binding)
        targets = [dict(target_id=r['target_id'],round0_prediction=r['predicted_value'],
            candidate_prediction=predicted[r['target_id']],round0_award=r['points_awarded'],
            candidate_award=awards[r['target_id']],delta=awards[r['target_id']]-r['points_awarded']) for r in baseline['targets']]
        return dict(company_id=company,points=public['points'],round0_points=baseline['points'],
            delta=public['points']-baseline['points'],targets=targets,
            regressions=[r['target_id'] for r in targets if r['delta']<0],result=binding)
