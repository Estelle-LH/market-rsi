"""Prospective continuation policy for the existing clean owner, not a runner.

Old finite round authorities remain immutable. Count/group completion is never
a prospective stop. Source-bound per-round origins still select exact inputs.
"""
import re
import earnings_entry as e
import earnings_population_training25 as training

PLAN = 'configs/earnings_coevolution/training25_continuation_authority.json'
AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-CONTINUOUS-COEVOLUTION-DIRECT-AUTHORITY.json'),
    sha256='28e113ddf8829baf101f0e81d25a020b017e9cdb7d25da7cc316453739e77639')
FRONTIER_AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-DIRECT-MULTIPARENT-FRONTIER-AUTHORITY.json'),
    sha256='a823208d19a24499147c3482903d7f149beb15acc1b22fd04ad4e5ef33843267')
NO_BACKFILL_AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-DIRECT-HISTORICAL-RECONSTRUCTION-NO-BACKFILL-AUTHORITY.json'),
    sha256='0bb307dacb50433ddcc32685f369aeadba3f24b1a15361582fec4a0810dc9b4d')
EXACT3_AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-DIRECT-EXACT3-GLOBAL-FRONTIER-AUTHORITY.json'),
    sha256='b35310167c279950329730ad78378420f58bfa945cb17aac67112fa0e0e55530')
PROVISIONAL_AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-DIRECT-PROVISIONAL-FRONTIER-AMENDMENT-AUTHORITY.json'),
    sha256='c6af6a3aea5566711bb837440e8a6bbf597ca879af75818ed1ffd5832c7136c1')
PROVISIONAL_PLAN = 'configs/earnings_coevolution/training25_frontier_provisional_amendment_v1.json'
PROVISIONAL_POLICY = dict(path=str(e.REPO/PROVISIONAL_PLAN),
    sha256='cfd8b6383913c9b31581eb9f3f3673a256d234473f7a837f8d3a7ab2fb547a58')


def saved(bound):
    return e.strict_json(e.checked(bound))


def frontier_round(n):
    return type(n) is int and n >= 9


def complete_member(member, training_ids):
    """Saved full25 is a historical comparator, never a new matched rerun."""
    descriptor, report = saved(member['descriptor']), saved(member['report'])
    candidate = descriptor['candidate']; comparison = report['comparison']
    rows = comparison['rows']
    if (member['version_id'] != candidate['id'] or report['frozen'] != member['descriptor']
            or comparison.get('scored') != 25 or descriptor['training'] != training_ids
            or [r['company_id'] for r in rows] != training_ids or len(set(training_ids)) != 25
            or any(type(r.get('points')) not in (int,float) or r['points'] not in [i/2 for i in range(11)] for r in rows)
            or sum(r['points'] for r in rows)/25 != comparison.get('candidate_mean')
            or member.get('mean') != comparison['candidate_mean']):
        raise ValueError('Frontier requires exact complete same-candidate historical25 evidence')
    for row in rows:
        targets=row.get('targets',[])
        if ([t.get('target_id') for t in targets]!=training.TARGETS
                or any(type(t.get('candidate_award')) not in (int,float)
                    or t['candidate_award'] not in (0,.5,1) for t in targets)
                or sum(t['candidate_award'] for t in targets)!=row['points']):
            raise ValueError('Frontier eligibility requires all125 saved public target awards, not a scored header')
    for axis in ('R','H'):e.checked(candidate[axis])
    from market_rsi import digest
    if candidate['id'] != digest({a:candidate[a]['sha256'] for a in ('R','H')}):
        raise ValueError('Frontier source identity differs')
    for bound in member.get('evidence',[]):e.checked(bound)
    if not member.get('evidence'):raise ValueError('Frontier retention requires observed capability evidence')
    return candidate


def generation_outcomes(frontier, progress, *, complete=False):
    """Saved child terminals, not paid retries or fabricated budget completion."""
    declared={(g['parent_id'],c['hypothesis_id']) for g in frontier['expansions'] for c in g['children']}
    if progress.get('generation')!=frontier['generation']:
        raise ValueError('Generation progress differs from declared parents/children')
    seen=set();evaluated=[];versions=set();proposals=set()
    for outcome in progress['outcomes']:
        key=(outcome['parent_id'],outcome['hypothesis_id'])
        if key not in declared or key in seen:
            raise ValueError('Duplicate or undeclared prospective child outcome')
        seen.add(key)
        if outcome['status']=='FULL25':
            member=outcome['member'];version=complete_member(member,frontier['training'])
            cp=saved(outcome['checkpoint'])
            if version['parent']!=key[0] or cp.get('report')!=member['report'] or cp.get('every_blob_readback_verified') is not True:
                raise ValueError('Child must branch actual parent and have verified full25 checkpoint')
            if version['id'] in versions:
                raise ValueError('One frozen child cannot fill two hypothesis outcomes')
            versions.add(version['id'])
            descriptor=saved(member['descriptor']);proposal=saved(descriptor['proposal'])
            runtime=saved(proposal['runtime']);source_plan=saved(outcome['source_plan'])
            stages=proposal['proposal_stages']
            if len(stages)==1:
                record=saved(stages[0]);reviewed=record['candidate'];accepted=record['review'].get('accepted_for_exploration')
            elif len(stages)==4:
                from pathlib import Path
                from supervisor_harness.feedback_linked_loop import _read_pair
                for stage in stages:e.checked(stage)
                reviewed=_read_pair(Path(stages[2]['path']))['output']['candidate']
                accepted=_read_pair(Path(stages[3]['path']))['output'].get('accepted_for_exploration')
            else:
                raise ValueError('Actual saved proposal stages required, not a fabricated accepted header')
            from earnings_population_layered import accepted_source
            if (proposal.get('status')!='PROPOSAL_REVIEWED_ACCEPTED'
                    or not accepted_source(descriptor,runtime,member,outcome['checkpoint'])
                    or descriptor['parent_basis']!=source_plan['origin'] or reviewed!=version or accepted is not True):
                raise ValueError('Full25 child must bind its genuine accepted proposal/runtime/Source/origin')
            origin=saved(descriptor['parent_basis'])
            evaluated.append(member)
        elif outcome['status']=='TERMINAL_INELIGIBLE':
            closure=saved(outcome['closure'])
            if (type(closure.get('original_true_exit')) is not int or type(closure.get('pending_count')) is not int
                    or closure['pending_count']!=0 or closure.get('pending_full_reserved_nano_usd')!=0
                    or closure.get('all_owned_settled') is not True
                    or closure.get('status') not in ('FAILED_NO_RETRY','PROPOSAL_NOT_ACCEPTED')
                    or not (closure.get('original_failure') or closure.get('original_result'))):
                raise ValueError('Ineligible terminal requires actual closed failure/rejection and settled fees')
            terminal=saved(closure.get('original_failure') or closure['original_result'])
            runtime=saved(closure['runtime']);source_plan=saved(outcome['source_plan'])
            if (outcome['source_plan']['sha256']!=runtime['sources'][PLAN]['sha256']
                    or runtime['id']!=source_plan['proposal_id']
                    or closure['source_commit']!=runtime['source_commit']
                    or terminal.get('runtime')!=closure['runtime']
                    or saved(closure['owner']).get('runtime')!=closure['runtime']):
                raise ValueError('Failure must bind its actual proposal source/runtime/owner, not an unrelated terminal')
            origin=saved(source_plan['origin'])
        else:
            raise ValueError('Deferred/incomplete children are not evaluated generation outcomes')
        claim=saved(origin['frontier_expansion'])
        if (claim['frontier']!=progress['frontier'] or claim['generation']!=frontier['generation']
                or (claim['parent_id'],claim['hypothesis_id'])!=key
                or origin['parent']['id']!=key[0] or claim['proposal_id'] in proposals
                or claim['proposal_id']!=runtime['id'] or source_plan['proposal_id']!=runtime['id']
                or claim['logical_round']!=runtime['clean_learning_round']
                or outcome['source_plan']['sha256']!=runtime['sources'][PLAN]['sha256']):
            raise ValueError('Terminal child must bind the exact actual frontier/parent/hypothesis and unique proposal')
        proposals.add(claim['proposal_id'])
    if complete and seen!=declared:
        raise ValueError('Evaluate every declared child before selecting the next generation')
    return evaluated


def provisional_budget(frontier):
    """Declared snapshot/planning only; original live admission still governs."""
    layered=frontier.get('schema')=='edgar25_depth_frontier_v4'
    if not layered and (frontier.get('provisional_authority')!=PROVISIONAL_AUTHORITY
            or frontier.get('amendment_policy')!=PROVISIONAL_POLICY):
        raise ValueError('Exact prospective provisional-frontier amendment required')
    if not layered:saved(PROVISIONAL_AUTHORITY);saved(PROVISIONAL_POLICY)
    b=frontier['budget'];record=saved(b['evidence'])
    snapshot=record.get('current_original_ledger',record.get('current_ledger_snapshot_not_lease',{}))
    pending_count=record.get('pending',record.get('pending_count'))
    pending=record.get('pending_full_reserved_nano_usd',0 if pending_count==0 else None)
    from earnings_population_layered import planning_ceiling
    ceiling=planning_ceiling(b.get('additional_budget_amendment')) if layered else 387429960800
    if (layered and b.get('additional_budget_amendment') is None
            or b.get('stage_total_cap_nano_usd')!=ceiling or b.get('planning_not_grant') is not True
            or any(type(b.get(k)) is not int or b[k]<0 for k in ('charged_nano_usd','pending_full_reserved_nano_usd'))
            or snapshot.get('charged_nano_usd')!=b['charged_nano_usd'] or pending!=b['pending_full_reserved_nano_usd']):
        raise ValueError('Original booked/full-pending snapshot and cap required; not new money')
    remaining=max(0,ceiling-b['charged_nano_usd']-b['pending_full_reserved_nano_usd'])
    if b.get('remaining_nano_usd')!=remaining:raise ValueError('Exact original remaining liabilities required')
    return remaining


def provisional_eligible(assessment, remaining, *, incumbent=False):
    """Gain/forecast rank is deliberately absent from exploration eligibility."""
    checks=assessment['eligibility'];keys=('safe','technically_valid','authentic_evaluation','distinct_test','credible_test')
    cost=checks.get('estimated_next_test_nano_usd');test=assessment.get('next_test',{})
    if (any(type(checks.get(k)) is not bool for k in keys) or type(cost) is not int or cost<=0
            or any(not isinstance(test.get(k),str) or not test[k].strip() for k in
                ('hypothesis_id','question','support_observation','refute_observation','exit_criterion'))):
        raise ValueError('Explicit safety/validity/authentic evaluation and distinct credible bounded test required')
    # Prediction retention is protected independently of whether more work is affordable.
    return all(checks[k] for k in keys[:3]) if incumbent else all(checks[k] for k in keys) and cost<=remaining


def provisional_retention(frontier, previous, remaining):
    shortfall=3-len(frontier['members'])
    status='FRONTIER_SHORTFALL' if shortfall else 'READY_THREE_PARENT_FRONTIER'
    bootstrap=frontier.get('bootstrap',{})
    preceding_complete=len(previous['members'])==3
    epoch=(previous.get('bootstrap_epoch',0)+1 if previous.get('schema')=='edgar25_global_frontier_v3'
        and previous.get('frontier_status')=='FRONTIER_SHORTFALL' else (0 if preceding_complete else 1))
    if (frontier.get('frontier_status')!=status or frontier.get('preceding_generation_complete') is not preceding_complete
            or frontier.get('bootstrap_epoch')!=epoch
            or shortfall and (bootstrap.get('bounded') is not True or bootstrap.get('generation_complete') is not False)):
        raise ValueError('FRONTIER_SHORTFALL is bounded bootstrap/incomplete, never a completed generation')
    estimates=[c.get('estimated_cost_nano_usd') for g in frontier['expansions'] for c in g['children']]
    if not estimates or any(type(v) is not int or v<=0 for v in estimates):
        raise ValueError('Every retained-parent child needs an explicit cost estimate, not a grant')
    required=sum(estimates);gap=max(0,required-remaining)
    if (frontier.get('estimated_expansion_cost_nano_usd')!=required
            or frontier.get('expansion_budget_shortfall_nano_usd')!=gap
            or gap and not frontier.get('expansion_budget_shortfall_reason')):
        raise ValueError('Report exact estimated expansion budget shortfall; do not substitute a single chain')


def balanced_parent_expansion(frontier, progress, parent_id):
    """Use existing terminal progress; no second scheduler or child-count stop."""
    seen={(o['parent_id'],o['hypothesis_id']) for o in progress['outcomes']}
    counts={m['version_id']:sum(p==m['version_id'] for p,_ in seen) for m in frontier['members']}
    available={g['parent_id'] for g in frontier['expansions']
        if any((g['parent_id'],c['hypothesis_id']) not in seen for c in g['children'])}
    if parent_id not in available or counts[parent_id]!=min(counts[p] for p in available):
        raise ValueError('Expand every retained parent before another family advances again')


def exact3_selection(frontier):
    """Prospective override only; evidence qualification stays separate by axis."""
    if frontier.get('retention_authority')!=EXACT3_AUTHORITY:
        raise ValueError('Exact prospective three-node retention authority required')
    e.checked(EXACT3_AUTHORITY)
    previous=saved(frontier['previous_frontier'])
    amended=frontier.get('schema')=='edgar25_global_frontier_v3'
    bootstrap=amended and previous.get('schema')=='edgar25_global_frontier_v3' and previous.get('frontier_status')=='FRONTIER_SHORTFALL'
    if frontier['generation']!=previous['generation']+(0 if bootstrap else 1):
        raise ValueError('No skipped or rewritten generation')
    progress=saved(frontier['preceding_outcomes'])
    if progress.get('frontier')!=frontier['previous_frontier']:
        raise ValueError('Selection outcomes must bind the actual previous frontier')
    children=generation_outcomes(previous,progress,complete=True)
    selection_pool={m['version_id']:m for m in [*previous['members'],*children]}
    considered={m['version_id']:m for m in frontier['considered']}
    if set(considered)!=set(selection_pool) or any(
            any(considered[k][f]!=m[f] for f in ('descriptor','report','mean')) for k,m in selection_pool.items()):
        raise ValueError('Select only from surviving parents plus evaluated children; no archived backfill')
    assessments=frontier['qualification'];eligible=set();remaining=provisional_budget(frontier) if amended else None
    if len(assessments)!=len(considered) or {a['version_id'] for a in assessments}!=set(considered):
        raise ValueError('Exactly one evidence-backed qualification assessment for every selection-pool node')
    for assessment in assessments:
        if (type(assessment.get('eligible')) is not bool or not assessment.get('reason')
                or any(not isinstance(assessment.get(axis),str) or not assessment[axis].strip() for axis in
                       ('prediction_quality','research_capability','harness_capability'))
                or not assessment.get('evidence')):
            raise ValueError('Separate prediction/research/harness findings and actual evidence required')
        for bound in assessment['evidence']:e.checked(bound)
        if amended:
            incumbent=assessment['version_id']==frontier['incumbent_id']
            if assessment['eligible'] is not provisional_eligible(assessment,remaining,incumbent=incumbent):
                raise ValueError('Exploration eligibility is safety/validity/evidence/test affordability, not proven improvement')
            member=next((m for m in frontier['members'] if m['version_id']==assessment['version_id']),None)
            if member is not None:
                test=assessment['next_test']
                declared=[c for g in frontier['expansions'] if g['parent_id']==assessment['version_id']
                    for c in g['children'] if c['hypothesis_id']==test['hypothesis_id']]
                if (len(declared)!=1 or any(declared[0][k]!=test[k] for k in
                        ('question','support_observation','refute_observation'))
                        or declared[0]['estimated_cost_nano_usd']!=assessment['eligibility']['estimated_next_test_nano_usd']):
                    raise ValueError('Eligibility test and cost must bind one actual declared child, not an unrelated test')
            if member is not None and not incumbent and member.get('status')=='validated_within_scope':
                finding=saved(assessment['validated_gain_evidence']) if assessment.get('validated_gain_evidence') else {}
                if (assessment.get('demonstrated_improvement') is not True or finding.get('validated_learning') is not True
                        or finding.get('actual_use') is not True or not finding.get('measured_benefit')
                        or any(finding.get(k)!=member[k] for k in ('version_id','descriptor','report'))):
                    raise ValueError('Unproved gain must remain provisional, not validated improvement')
        if assessment['eligible']:eligible.add(assessment['version_id'])
    selected={m['version_id'] for m in frontier['members']}
    if not selected<=eligible or len(selected)!=min(3,len(eligible)):
        raise ValueError('Retain exactly three eligible GLOBAL nodes, or every eligible node if fewer')
    shortfall=3-len(selected)
    if (frontier.get('eligible_shortfall')!=shortfall
            or shortfall and not frontier.get('shortfall_reason')):
        raise ValueError('Explicit numerical shortfall and qualification evidence gaps required; never invent a third')
    if amended:provisional_retention(frontier,previous,remaining)


def validate_frontier(frontier, population):
    """One global width, separate incumbent and provisional capability choices."""
    from earnings_population import validate
    validate(population)
    preserved=validate(saved(frontier['preserved_population']))
    if (population['anchor_id']!=preserved['anchor_id'] or population['protected']!=preserved['protected']
            or population['history'][:len(preserved['history'])]!=preserved['history']
            or any(population['versions'].get(k)!=v for k,v in preserved['versions'].items())
            or population['observations'][:len(preserved['observations'])]!=preserved['observations']
            or population['exposed_companies'][:len(preserved['exposed_companies'])]!=preserved['exposed_companies']):
        raise ValueError('Preserve original pool/journal/observations/exposure; no frontier reset')
    if frontier.get('schema')=='edgar25_depth_frontier_v4':
        from earnings_population_layered import validate as layered_validate
        return layered_validate(frontier,population,preserved)
    exact3=frontier.get('schema') in ('edgar25_global_frontier_v2','edgar25_global_frontier_v3')
    if (frontier.get('schema') not in ('edgar25_global_frontier_v1','edgar25_global_frontier_v2','edgar25_global_frontier_v3')
            or frontier.get('direct_authority') != FRONTIER_AUTHORITY
            or frontier.get('no_backfill_authority') != NO_BACKFILL_AUTHORITY
            or frontier.get('prospective') is not True or frontier.get('historical_backfill') is not False
            or type(frontier.get('generation')) is not int or frontier['generation'] < 1):
        raise ValueError('Exact prospective frontier and no historical backfill authority required')
    e.checked(FRONTIER_AUTHORITY);e.checked(NO_BACKFILL_AUTHORITY)
    members=frontier['members'];ids=[m['version_id'] for m in members]
    if not 1 <= len(ids) <= 3 or len(set(ids)) != len(ids) or frontier['incumbent_id'] not in ids:
        raise ValueError('At most three GLOBAL members including incumbent, not three per family')
    if frontier['training'] != training.load_scope(dict(path=str(training.SPLIT),sha256=training.SPLIT_SHA))['training']:
        raise ValueError('Original frozen training panel required')
    for member in members:
        version=complete_member(member,frontier['training'])
        registered=population['versions'].get(version['id'])
        # Earlier clean rounds recorded an explicit anchor projection with the
        # same R/H but baseline metadata. Preserve it, and preserve the authentic
        # descriptor's genealogy separately; never pretend that was code ancestry.
        legacy_anchor=(version['id']==frontier['incumbent_id'] and registered is not None
            and registered==preserved['versions'].get(version['id'])
            and all(registered[k]==version[k] for k in ('id','R','H')))
        if registered != version and not legacy_anchor:
            raise ValueError('Frontier actual frozen code is not registered in preserved pool')
        if member['version_id'] == frontier['incumbent_id']:
            if member.get('status') != 'prediction_incumbent':raise ValueError('Separate incumbent required')
        elif (member.get('status') not in ('provisional','validated_within_scope')
                or any(not isinstance(member.get(k),str) or not member[k].strip() for k in
                    ('capability','observed_use','uncertainty','information_value','opportunity_cost','next_test','exit_criterion'))):
            raise ValueError('Exploration needs actual evidence, uncertainty, named next test and exit criterion')
    incumbent=next(m for m in members if m['version_id']==frontier['incumbent_id'])
    candidates=frontier['considered']
    if not candidates or len({m['version_id'] for m in candidates}) != len(candidates):
        raise ValueError('Explicit unique considered parents and eligible children required')
    for member in candidates:complete_member(member,frontier['training'])
    if (not set(ids) <= {m['version_id'] for m in candidates}
            or any(m['mean'] > incumbent['mean'] for m in candidates)
            or frontier['prediction_decision'].get('selected') != incumbent['descriptor']
            or not frontier.get('pruning_reasons') or not frontier.get('expansions')):
        raise ValueError('Strict prediction winner, complementary retention and pruning must be separate')
    previous=saved(frontier['previous_stable'])
    if previous['selected'] != incumbent['descriptor']:
        raise ValueError('Cannot silently replace the retained full25 incumbent')
    if exact3:exact3_selection(frontier)
    planned=set()
    for group in frontier['expansions']:
        if group['parent_id'] not in ids or group['parent_id'] in planned:
            raise ValueError('Only current frontier members may expand, not archived missing branches')
        planned.add(group['parent_id']);children=group['children']
        if not (2 if exact3 else 0) <= len(children) <= 3 or len({c['hypothesis_id'] for c in children}) != len(children):
            raise ValueError('Exactly two to three prospective children per parent under v2; historical omissions remain history')
        if exact3 and len({c.get('question') for c in children})!=len(children):
            raise ValueError('Distinct questions required, not duplicated quota entries')
        if len(children)<2 and not group.get('omitted_expansion_reason'):
            raise ValueError('Explain an omitted second informative child')
        for child in children:
            if any(not isinstance(child.get(k),str) or not child[k].strip() for k in
                    ('hypothesis_id','question','support_observation','refute_observation')):
                raise ValueError('Every prospective child needs a distinguishable named test')
    if planned != set(ids):raise ValueError('Explicit expansion or omission for every retained parent required')
    return frontier


def expansion(origin, plan=None):
    """No archived backfill, no incumbent substitution, no old-feedback reset."""
    from earnings_population import validate
    if not frontier_round(origin.get('logical_round')):return None
    bound=origin['frontier_expansion'];claim=saved(bound)
    frontier=saved(claim['frontier']);state=validate(saved(origin['carried_population']))
    validate_frontier(frontier,state)
    parent=origin['parent'];members={m['version_id']:m for m in frontier['members']}
    incumbent=(frontier['prediction_reference'] if frontier.get('schema')=='edgar25_depth_frontier_v4'
        else members[frontier['incumbent_id']])
    if (incumbent['descriptor']!=origin['incumbent_descriptor']
            or incumbent['report']!=origin['incumbent_comparison']
            or incumbent['mean']!=origin['incumbent_mean']
            or frontier['previous_stable']!=origin['group_start_stable']):
        raise ValueError('Frontier membership/pool and current prediction incumbent threshold differ')
    member=members.get(claim.get('parent_id'))
    registered=state['versions'].get(parent['id'])
    legacy_parent=(member is not None and parent['id']==frontier['incumbent_id']
        and parent==saved(member['descriptor'])['candidate']
        and registered==saved(frontier['preserved_population'])['versions'].get(parent['id'])
        and all(registered[k]==parent[k] for k in ('id','R','H')))
    if (claim.get('schema')!='edgar25_prospective_frontier_expansion_v1' or claim.get('prospective') is not True
            or claim.get('historical_backfill') is not False or member is None
            or claim.get('generation')!=frontier['generation'] or claim.get('logical_round')!=origin['logical_round']
            or claim.get('parent_id')!=parent['id'] or member['descriptor']!=origin['prior_descriptor']
            or member['report']!=origin['parent_comparison'] or member['mean']!=origin['prior_mean']
            or registered!=parent and not legacy_parent
            or state['stable_id']!=frontier['incumbent_id']
            or state['explorers']!=([parent['id']] if parent['id']!=state['stable_id'] else [])
            or claim.get('previous_complete_report')!=origin['prior_comparison']):
        raise ValueError('Exact selected actual frontier parent and serial working projection required')
    group=next(g for g in frontier['expansions'] if g['parent_id']==parent['id'])
    if frontier.get('schema') in ('edgar25_global_frontier_v2','edgar25_global_frontier_v3','edgar25_depth_frontier_v4'):
        progress=saved(claim['generation_progress'])
        if progress.get('frontier')!=claim['frontier']:
            raise ValueError('Current generation progress must bind this frontier')
        generation_outcomes(frontier,progress)
        if any((o['parent_id'],o['hypothesis_id'])==(parent['id'],claim['hypothesis_id']) for o in progress['outcomes']):
            raise ValueError('Declared child already terminal; no silent hypothesis retry')
        if frontier.get('schema') in ('edgar25_global_frontier_v3','edgar25_depth_frontier_v4'):
            balanced_parent_expansion(frontier,progress,parent['id'])
    hypotheses=[c for c in group['children'] if c['hypothesis_id']==claim.get('hypothesis_id')]
    if len(hypotheses)!=1:raise ValueError('Expansion must select one declared informative child')
    if plan is not None and (plan.get('frontier_expansion')!=bound or plan.get('proposal_id')!=claim.get('proposal_id')
            or plan.get('group_parent_id')!=parent['id'] or plan.get('discriminating_next',{}).get('question')!=hypotheses[0]['question']):
        raise ValueError('Current source-bound proposal route differs from selected frontier expansion')
    latest=saved(origin['prior_comparison']);checkpoint=saved(origin['previous_complete_checkpoint'])
    if latest.get('comparison',{}).get('scored')!=25 or checkpoint.get('report')!=origin['prior_comparison']:
        raise ValueError('Complete previous full25 feedback and closure checkpoint required before mutation')
    return claim


def selected_parent(state, origin=None):
    from copy import deepcopy
    identifier=state['stable_id'] if origin is None or not frontier_round(origin.get('logical_round')) else origin['parent']['id']
    if identifier not in [state['stable_id'],*state.get('explorers',[])]:
        raise ValueError('Selected frontier parent is not active in exact working projection')
    parent=state['versions'][identifier]
    if origin is not None and parent!=origin['parent']:
        # Preserve the old anchor projection as history; use the independently
        # authenticated descriptor's actual genealogy, never rewrite the pool.
        claim=expansion(origin);frontier=saved(claim['frontier'])
        if (identifier!=frontier['incumbent_id']
                or parent!=saved(origin['carried_population'])['versions'][identifier]
                or any(parent[k]!=origin['parent'][k] for k in ('id','R','H'))):
            raise ValueError('Actual R/H parent substitution')
        return deepcopy(origin['parent'])
    return deepcopy(parent)


def declared_test(origin):
    """Small literal projection into C/A/Review, not just an unread path/hash."""
    claim=expansion(origin)
    frontier=saved(claim['frontier'])
    group=next(g for g in frontier['expansions'] if g['parent_id']==claim['parent_id'])
    hypothesis=next(c for c in group['children'] if c['hypothesis_id']==claim['hypothesis_id'])
    return dict(generation=claim['generation'],logical_round=claim['logical_round'],
        actual_parent_id=claim['parent_id'],frontier_expansion=origin['frontier_expansion'],**hypothesis)


def feedback_expansion(full, initial):
    """Narrow opt-in for preserved multi-version history and complete feedback."""
    bound=full.get('frontier_expansion')
    if bound is None:return False
    plan=e.strict_json((e.REPO/PLAN).read_bytes())
    origin=saved(plan['origin']);claim=expansion(origin,plan)
    if bound!=origin['frontier_expansion'] or initial!=saved(origin['carried_population']) or full!=saved(origin['public_feedback']):
        raise ValueError('Frontier full-feedback/preserved-population substitution')
    return claim is not None


def parent_round(n):
    return type(n) is int and n >= 2


def followup_round(n):
    return type(n) is int and n >= 3


def continuous_round(n):
    return type(n) is int and n >= 8


def authorized(direct, binding, n):
    return (continuous_round(n) and binding == AUTHORITY
        and direct == e.strict_json(e.checked(AUTHORITY))
        and direct.get('schema') == 'edgar25_continuous_coevolution_direct_authority_v1'
        and direct.get('candidate_count_limit') is None and direct.get('group_count_limit') is None
        and direct.get('max_concurrent_companies') == 8 and direct.get('single_owner') is True
        and direct.get('max_inflight_per_company') == 1
        and direct.get('failed_paid_retry_authorized') is False and direct.get('heldout_access') is False)


def decision(charged, pending, minimum_next, *, meaningful_next, stagnation=None, additional_budget_amendment=None):
    """Original stage liabilities, NOT a refreshed grant or a candidate counter."""
    if any(type(v) is not int or v < 0 for v in (charged, pending, minimum_next)) or not minimum_next:
        raise ValueError('Exact nonnegative booked/full-pending liabilities and useful-work bound required')
    from earnings_population_layered import planning_ceiling
    remaining = planning_ceiling(additional_budget_amendment) - charged - pending
    if remaining < minimum_next:
        return 'STOP_ORIGINAL_BUDGET_INSUFFICIENT'
    if meaningful_next:
        return 'CONTINUE'
    required = ('consecutive_iterations_reviewed', 'feedback_behavior_changes',
        'repeated_errors_and_resolved_questions', 'new_diagnoses_and_validations',
        'actual_H_use_and_effect', 'remaining_discriminating_alternatives_and_cost')
    if not isinstance(stagnation, dict) or any(not stagnation.get(k) for k in required):
        raise ValueError('No-count-stop: stagnation requires the six evidence-backed trajectory checks')
    for key in required:
        section=e.strict_json(e.checked(stagnation[key]))
        if (section.get('schema')!='edgar25_learning_stagnation_evidence_v1'
                or section.get('section')!=key or not section.get('finding')
                or len(section.get('completed_iteration_reports',[]))<2
                or section.get('budget_feasible_meaningful_next') is not False):
            raise ValueError('Actual trajectory findings, not authority/count labels, required')
        reports=section['completed_iteration_reports']
        if len({repr(sorted(b.items())) if isinstance(b,dict) else repr(b) for b in reports})!=len(reports):
            raise ValueError('One iteration cannot be counted twice as learning stagnation')
        rounds=[]
        for bound in reports:
            report=e.strict_json(e.checked(bound))
            n=report.get('logical_round')
            if report.get('comparison',{}).get('scored')!=25 or type(n) is not int:
                raise ValueError('Stagnation evidence must identify actual completed iterations')
            rounds.append(n)
        if any(b-a!=1 for a,b in zip(rounds,rounds[1:])):
            raise ValueError('Actual consecutive distinct iterations required for stagnation')
    return 'STOP_EVIDENCE_SUPPORTED_LEARNING_STAGNATION'


def validate_plan(plan, origin):
    direct = e.strict_json(e.checked(AUTHORITY))
    n = origin['logical_round']
    if n>=13:
        frontier=saved(saved(origin['frontier_expansion'])['frontier'])
        if frontier.get('schema') not in ('edgar25_global_frontier_v2','edgar25_global_frontier_v3','edgar25_depth_frontier_v4'):
            raise ValueError('Prospective Round13+ requires exact3 policy; legacy frontiers remain history only')
        if n>=14 and frontier.get('schema') not in ('edgar25_global_frontier_v3','edgar25_depth_frontier_v4'):
            raise ValueError('Round14+ requires prospective provisional eligibility and bootstrap clarification')
        if n>=16 and (frontier.get('schema')!='edgar25_depth_frontier_v4'
                or plan.get('additional_budget_amendment') is None
                or plan['additional_budget_amendment']!=origin.get('additional_budget_amendment')
                or frontier['budget']['additional_budget_amendment']!=plan['additional_budget_amendment']):
            raise ValueError('Round16+ requires activated layered policy and exact original additional100 opt-in')
    if (not authorized(direct, plan.get('direct_authority'), n)
            or plan.get('logical_round') != n or origin.get('direct_authority') != AUTHORITY
            or plan.get('group_is_organization_only') is not True
            or plan.get('automatic_retry') is not False or plan.get('budget_change') is not False
            or plan.get('heldout_access') is not False):
        raise ValueError('Exact continuous authority/source-bound prospective round required')
    hypothesis = plan.get('discriminating_next', {})
    if any(not isinstance(hypothesis.get(k), str) or not hypothesis[k].strip()
           for k in ('question', 'support_observation', 'refute_observation')):
        raise ValueError('A distinguishable information-value hypothesis is required, not a quota')
    for binding in hypothesis.get('evidence', []):
        e.checked(binding)
    if not hypothesis.get('evidence'):
        raise ValueError('Hypothesis must cite actual completed feedback/diagnostics')
    snapshot = origin['admission_snapshot_not_lease']
    minimum = plan.get('minimum_next_liability_nano_usd')
    # A $5 WINDOW CEILING is not a minimum useful-work cost. The declared next
    # request still undergoes original exact token/reservation/current fee checks.
    status = decision(snapshot['charged_nano_usd'], 0, minimum, meaningful_next=True,
        additional_budget_amendment=plan.get('additional_budget_amendment'))
    if status != 'CONTINUE':
        raise ValueError(status)
    checkpoint = e.strict_json(e.checked(origin['previous_complete_checkpoint']))
    if checkpoint.get('every_blob_readback_verified') is not True:
        raise ValueError('Actual preceding closed evidence checkpoint required')
    if frontier_round(n):expansion(origin,plan)
    return direct


def selection_threshold(origin):
    """Same group code parent and best comparable incumbent are separate."""
    parent, incumbent = origin['prior_mean'], origin['incumbent_mean']
    if (type(parent) not in (int,float) or type(incumbent) not in (int,float)
            or not 0 <= parent <= incumbent <= 5):
        raise ValueError('Complete comparable parent/incumbent means required')
    return incumbent


def route(identifier, n, frozen, repairing):
    if identifier == 'edgar-population-20261016-154' and (
            type(n) is not int or n != 17 or frozen is not False or repairing is not True):
        raise ValueError('Once154 is strictly logical17 FIRST Review, never legacy/C-A/forecast')
    if identifier == 'edgar-population-20261016-146' and (
            type(n) is not int or n != 16 or frozen is not False or repairing is not True):
        raise ValueError('Once146 is strictly logical16 first Review, never legacy/C-A/forecast')
    if identifier == 'edgar-population-20261016-144' and (
            type(n) is not int or n != 16 or frozen is not False or repairing is not True):
        raise ValueError('Once144 is strictly logical16 first Review, never legacy/C-A/forecast')
    # Reserved first-Review IDs must not escape through a legacy round route.
    if identifier == 'edgar-population-20261016-126' and (
            type(n) is not int or n != 14 or frozen is not False or repairing is not True):
        raise ValueError('Once126 is strictly logical14 first Review, never legacy/C-A/forecast')
    if not continuous_round(n):
        return
    plan = e.strict_json((e.REPO/PLAN).read_bytes())
    proposal = plan.get('proposal_id')
    # One source-bound, PROGRAM-unchanged CASE-expectation correction. The
    # clean adapter authenticates its exact sealed descriptor. No paid Review
    # existed in106; this is not a generic failed-provider retry/C-A reuse flag.
    case_round = {'edgar-population-20261016-107':11,'edgar-population-20261016-113':12,
        'edgar-population-20261016-119':13,'edgar-population-20261016-126':14,
        'edgar-population-20261016-144':16,'edgar-population-20261016-146':16,
        'edgar-population-20261016-154':17}.get(identifier)
    case_review = case_round is not None
    if case_review and (n != case_round or frozen or repairing is not True):
        raise ValueError('Exact once107/113/119/126 permits only source-bound first Review correction')
    if (plan.get('logical_round') != n or not isinstance(proposal, str)
            or not re.fullmatch(r'edgar-population-20261016-[0-9]{2,}', identifier)
            or repairing and not case_review or not frozen and identifier != proposal
            or frozen and int(identifier.rsplit('-', 1)[1]) <= int(proposal.rsplit('-', 1)[1])):
        raise ValueError('One declared fresh proposal, then only fresh frozen-evaluation IDs; no automatic retry')


def yield_authority(value):
    plan = e.strict_json(e.checked(value['sources'][PLAN]))
    if plan.get('logical_round') != value.get('clean_learning_round'):
        raise ValueError('Prospective rolling policy round differs')
    bound = plan['rolling_yield_authority']
    e.checked(bound)
    return bound


def bound_continuous_round(value):
    if not continuous_round(value.get('clean_learning_round')):
        return True
    bound=value.get('sources',{}).get(PLAN)
    return bool(bound and e.strict_json(e.checked(bound)).get('logical_round')==value['clean_learning_round'])
