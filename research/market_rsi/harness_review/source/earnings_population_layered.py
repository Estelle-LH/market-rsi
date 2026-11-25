# Source excerpt. Imports and other methods are omitted.

def child_breadth(frontier):
    """Prospective scientific slots, not attempts; no omitted-policy downgrade.

    Generation8 was already declared under v5's three-slot rule. Generation9+
    must bind the exact new policy even with zero outcomes or no growth seats.
    Hash-bound policy/authority join the existing input/archive/HTTP evidence;
    they are not another scheduler or a grant of technical retries or money.
    """
    generation=frontier.get('generation')
    if type(generation) is not int:raise ValueError('Strict integer generation required for child breadth')
    if generation<9:
        if 'child_breadth_policy' in frontier:
            raise ValueError('No retroactive child-breadth amendment before generation9')
        return 3,[]
    if (frontier.get('schema')!=TRANSITION_SCHEMA
            or frontier.get('child_breadth_policy')!=BREADTH16_POLICY):
        raise ValueError('Generation9+ requires exact breadth16 policy; no legacy downgrade')
    transition_policy(frontier)
    policy=saved(BREADTH16_POLICY);e.checked(policy['direct_instruction'])
    for group in frontier['expansions']:
        if len(group['children'])!=16:
            raise ValueError('Each retained growth parent requires EXACTLY16 distinct scientific slots')
    normalized=lambda text:' '.join(text.casefold().split()).strip(' .?!')
    for field in ('hypothesis_id','question','primary_hypothesis'):
        raw=[c.get(field) for g in frontier['expansions'] for c in g['children']]
        if any(not isinstance(value,str) for value in raw):
            raise ValueError('Sixteen slots require explicit scientific hypothesis text')
        values=[normalized(value) for value in raw]
        if any(not v for v in values) or len(set(values))!=len(values):
            raise ValueError('Sixteen slots require distinct nonempty scientific hypotheses and questions')
    return 16,[BREADTH16_POLICY,policy['direct_instruction']]


def slot_resolution(frontier,entry,*,frontier_binding=None,plan=None):
    """Resolve one scientific slot identically for dispatch and terminal counting.

    Replacement evidence is a finite public-metadata chain anchored in the
    original private manifest, not a caller-supplied label or a fresh quota.
    The original failed outcome remains nested and its immutable progress stays
    retained. Returning evidence also lets the EXISTING HTTP guard pin it.
    """
    needs_breadth=(frontier.get('schema') in (SCHEMA,TRANSITION_SCHEMA)
        or type(frontier.get('generation')) is int and frontier['generation']>=9)
    breadth_evidence=child_breadth(frontier)[1] if needs_breadth else []
    parent_id=entry['parent_id'];hypothesis=entry['hypothesis_id']
    slot=entry.get('slot_hypothesis_id',hypothesis)
    children=[c for g in frontier['expansions'] if g['parent_id']==parent_id for c in g['children']]
    declared=[c for c in children if c['hypothesis_id']==slot]
    if len(declared)!=1:raise ValueError('Exactly one original declared parent/slot required')
    base=dict(parent_id=parent_id,slot_hypothesis_id=slot,hypothesis_id=hypothesis,
        contract=declared[0],evidence=[*breadth_evidence,
            *([entry['generation_progress']] if 'generation_progress' in entry else [])])
    if slot==hypothesis:
        if 'substitution' in entry or plan is not None and 'slot_substitution' in plan:
            raise ValueError('Original hypothesis cannot masquerade as a replacement')
        return base
    transition_policy(frontier)
    import earnings_population_coevolution as policy
    from earnings_population_technical_retry import eligible_mechanical_failure, POLICY as named_delivery_policy
    from pathlib import Path
    import re
    item=entry.get('substitution',{});prior=item.get('prior_slot_outcome',{})
    if (item.get('ordinal')!=1 or type(item.get('ordinal')) is not int
            or item.get('approved_extra_repairs')!=0 or type(item.get('approved_extra_repairs')) is not int
            or 'substitution' in prior or 'slot_hypothesis_id' in prior
            or prior.get('status')!='TERMINAL_INELIGIBLE'
            or prior.get('parent_id')!=parent_id or prior.get('hypothesis_id')!=slot
            or item.get('frontier')!=frontier_binding
            or hypothesis in {c['hypothesis_id'] for g in frontier['expansions'] for c in g['children']}):
        raise ValueError('Only one new distinct hypothesis after exhausted unscored mechanical slot; no old quota reset')
    policy.generation_outcomes(frontier,dict(generation=frontier['generation'],
        frontier=item['frontier'],outcomes=[prior]))
    closed=saved(prior['closure']);runtime=saved(closed['runtime']);identifier=runtime['id']
    if not re.fullmatch(r'edgar-population-20261016-[0-9]{3,}',identifier):
        raise ValueError('Canonical own original proposal ID required')
    # The Source alias is immutable A metadata. Never bind the old mutable D/PLAN
    # path even though its historical hash remains in the sealed runtime.
    alias=Path(prior['source_plan']['path'])
    if (alias.parent!=training.ROOT or alias.resolve()!=alias or alias.is_symlink()
            or prior['source_plan']['sha256']!=runtime['sources'][policy.PLAN]['sha256']
            or runtime.get('sources',{}).get(TRANSITION_POLICY['path'].split('/earnings-engine-checkout/')[-1],{}).get('sha256')!=TRANSITION_POLICY['sha256']):
        raise ValueError('Sealed new-layer original Source with zero extra repairs required')
    original_plan=saved(prior['source_plan'])
    if (original_plan.get('proposal_id')!=identifier or original_plan.get('technical_continuation') is not None
            or original_plan.get('slot_substitution') is not None):
        raise ValueError('New slot allowance is zero extra owners; never inherit old or replacement quotas')
    original_origin=saved(original_plan['origin']);original_claim=saved(original_origin['frontier_expansion'])
    if (original_claim.get('slot_hypothesis_id',slot)!=slot or 'substitution' in original_claim
            or original_claim['proposal_id']!=identifier
            or (original_claim['parent_id'],original_claim['hypothesis_id'])!=(parent_id,slot)):
        raise ValueError('Original failed Source/claim cannot itself be a replacement')
    root=training.ROOT;number=identifier.rsplit('-',1)[-1]
    canonical=dict(private=f'TRAIN25-CLEAN{number}-CLOSED-GIT.json',
        author_result=f'attempts/{identifier}/roles/author-01/result.json',
        delivery=f'attempts/{identifier}/roles/author-01/technical-delivery-failure.json',
        guard=f'attempts/{identifier}/role-validation/author-01.json',
        decision=f'attempts/{identifier}/roles/controller-01/population-decision.json')
    if any(item.get(k,{}).get('path')!=str(root/name) for k,name in canonical.items()):
        raise ValueError('Canonical original mechanical evidence required')
    if (prior['closure'].get('path')!=str(root/f'TRAIN25-CLEAN{number}-CLOSED-CLOSURE.json')
            or closed['runtime'].get('path')!=str(root/f'inputs/{identifier}/runtime-reviewed.json')):
        raise ValueError('Canonical closed original runtime required')
    private=saved(item['private']);manifest=private.get('artifacts',{})
    sealed=[prior['closure'],closed['runtime'],*[item[k] for k in canonical if k!='private']]
    def member(bound):
        path=Path(bound['path'])
        if manifest.get('original/'+str(path.relative_to(root)))!=bound:
            raise ValueError('Mechanical proof must be a member of the original sealed private manifest')
    for bound in sealed:member(bound)
    study_binding=runtime['forecast_study'];member(study_binding);study=saved(study_binding)
    task_binding=study['clean_slate_task'];member(task_binding);task=saved(task_binding)
    sealed += [study_binding,task_binding]
    docs={k:saved(item[k]) for k in canonical if k!='private'};docs['private']=private
    # This already-authenticated ordinary substitution accepts its new schema
    # and immutable older normal-v5 failures. Named continuation stays strict.
    normal_policy='earnings_normal_same_slot_delivery_v1'
    delivery_policy=(normal_policy if docs['delivery'].get('schema')==normal_policy else named_delivery_policy)
    eligible_mechanical_failure(closed,docs['private'],docs['author_result'],docs['delivery'],
        docs['guard'],closed['runtime'],docs['decision'],delivery_policy=delivery_policy)
    from market_rsi import digest
    if (docs['decision'].get('parent_pair_sha256')!=parent_id
            or docs['decision'].get('feedback_sha256')!=digest(task['feedback'])
            or task.get('round2_origin')!=original_plan['origin'] or task.get('mode')!='proposal'
            or task.get('frozen_candidate') is not None
            or declared[0]['change_axis'] in ('R','H') and docs['decision'].get('axis')!=declared[0]['change_axis']):
        raise ValueError('Original Controller proof must bind actual parent, feedback and declared axis')
    parent=policy.complete_member(next(m for m in frontier['members'] if m['version_id']==parent_id),frontier['training'])
    if original_origin.get('parent')!=parent:raise ValueError('Original actual R/H parent changed')
    contract=item['new_hypothesis_contract'];validate_slot(contract,parent)
    for field in ('hypothesis_id','question','support_observation','refute_observation'):
        if not isinstance(contract.get(field),str) or not contract[field].strip():
            raise ValueError('Complete replacement scientific contract required')
    normalized=lambda text:' '.join(text.casefold().split()).strip(' .?!')
    for child in [c for g in frontier['expansions'] for c in g['children']]:
        if any(normalized(contract[f])==normalized(child[f]) for f in ('question','primary_hypothesis')):
            raise ValueError('A different ID cannot replay an existing primary hypothesis or question')
    if contract['hypothesis_id']!=hypothesis:
        raise ValueError('Replacement contract must bind the actual new hypothesis')
    if plan is None:plan=saved(entry['source_plan'])
    origin=saved(plan['origin']);claim=saved(origin['frontier_expansion'])
    new_id=plan['proposal_id']
    if (not re.fullmatch(r'edgar-population-20261016-[0-9]{3,}',new_id)
            or int(new_id.rsplit('-',1)[-1])<=max(167,int(number))
            or plan.get('technical_continuation') is not None or plan.get('slot_substitution')!=item
            or plan.get('frontier_expansion')!=origin['frontier_expansion']
            or plan.get('group_parent_id')!=parent_id
            or plan.get('discriminating_next',{}).get('question')!=contract['question']
            or claim.get('substitution')!=item or claim.get('slot_hypothesis_id')!=slot
            or claim.get('hypothesis_id')!=hypothesis or claim.get('parent_id')!=parent_id
            or claim.get('frontier')!=frontier_binding or claim.get('generation')!=frontier['generation']
            or claim.get('proposal_id')!=new_id or origin.get('parent')!=parent):
        raise ValueError('Fresh replacement Source/origin/claim must bind the same slot, parent and entire contract')
    if 'source_plan' not in entry and entry!=claim:
        raise ValueError('Dispatch claim differs from its Source-bound replacement')
    return dict(base,contract=contract,evidence=[*breadth_evidence,claim['generation_progress'],item['private'],*sealed,prior['source_plan'],
        original_plan['origin'],original_origin['frontier_expansion'],*contract['trigger_feedback']])


def within_slot_context(runtime,task,origin,*,chosen=None):
    """Current-C ordinary v5 R delivery, NOT the old fixed-C repair route.

    Reuse only existing R preflight and the original eight turns. H retains its
    original delivery path until its mechanical classifier is separately tested.
    """
    key='configs/earnings_coevolution/training25_layer_transition_v5.json'
    if (runtime.get('clean_slate_policy')!='round0_clean_slate_v1'
            or runtime.get('sources',{}).get(key,{}).get('sha256')!=TRANSITION_POLICY['sha256']
            or task.get('mode')!='proposal' or task.get('frozen_candidate') is not None or origin is None):
        return None
    import earnings_population_coevolution as policy
    from pathlib import Path
    from market_rsi import digest
    from earnings_population_roles import scientific
    plan=saved(runtime['sources'][policy.PLAN])
    if plan.get('technical_continuation') is not None:return None
    claim=policy.expansion(origin,plan);frontier=saved(claim['frontier'])
    if frontier.get('schema')!=TRANSITION_SCHEMA:return None
    decision_path=Path(runtime['slots']['controller'][0])/'population-decision.json'
    if (decision_path!=Path(runtime['root'])/'roles/controller-01/population-decision.json'
            or decision_path.resolve()!=decision_path or decision_path.is_symlink() or not decision_path.is_file()):
        raise ValueError('Current physically audited Controller slot required')
    bound=dict(path=str(decision_path),sha256=e.digest(decision_path.read_bytes()))
    decision=saved(bound)
    if chosen is not None and chosen!=decision:raise ValueError('Author decision differs from actual current Controller')
    resolved=slot_resolution(frontier,claim,frontier_binding=claim['frontier'],plan=plan)
    axis=resolved['contract']['change_axis']
    if (decision.get('parent_pair_sha256')!=origin['parent']['id']
            or decision.get('feedback_sha256')!=digest(task['feedback'])
            or axis in ('R','H') and decision.get('axis')!=axis):
        raise ValueError('Current Controller/slot axis, actual parent or public feedback differs')
    if decision.get('axis')!='R':return None
    return dict(schema='edgar25_v5_within_original_slot_R_delivery_v1',transition_policy=TRANSITION_POLICY,
        current_Controller_decision=bound,scientific_decision_sha256=digest(scientific(decision)),
        frontier_expansion=origin['frontier_expansion'],slot_hypothesis_id=resolved['slot_hypothesis_id'],
        contract=resolved['contract'],maximum_original_turns=8,extra_technical_owners=0,
        instruction='Check final assembled R source/tests mechanically; repair only within ORIGINAL8 turns and unchanged resources. Current Controller ran normally; no fixed-C reuse or new scientific child.')
