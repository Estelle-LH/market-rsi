"""V4 validation for the existing coevolution selector, not another runner.

Historical v1-v3 rules remain in their original branches. A read-only prediction
reference is separate from the 2-3 same-code-depth growth parents.
"""
from contextlib import closing
import sqlite3
import earnings_entry as e
import earnings_population_training25 as training

SCHEMA='edgar25_depth_frontier_v4'
AUTHORITY=dict(path=str(training.ROOT/'TRAIN25-DIRECT-LAYERED-PARENTS-THREE-CHILDREN-20261023.json'),
    sha256='7ad0c0093202a8a6fc5e93e588645bba00ab97d00ce0e1db430a716d978d97fd')
POLICY=dict(path=str(training.ROOT/'TRAIN25-DEPTH-LAYERED-POLICY-V4.json'),
    sha256='8745adbeb397d300ef6a968473ee84a2fc0bea3c51cdb2d68b3013bc3c5822d7')
FINAL_REPORT=dict(path=str(training.ROOT/'TRAIN25-CLEAN-ROUND15-FINAL-COMPARISON.json'),
    sha256='155990653110d479e7dc1fab089af63097bb9ede58cc51f5d680d617cd0d82f0')
FINAL_GIT=dict(path=str(training.ROOT/'TRAIN25-CLEAN-ROUND15-FINAL-GIT.json'),
    sha256='60c203b19c98e02fef0b8e40aaea8ad27ff38822f5ebc6bf4666a9d7d358a31d')
FINANCIAL_DESCRIPTOR=dict(path=str(training.ROOT/'TRAIN25-CLEAN142-ADDITIONAL100-FROZEN-CANDIDATE.json'),
    sha256='c4c4bf8fc292456d397c7a2931afa38a7ad36ec70e6e905269d3b7e6cf0dba1b')
ORIGINAL_PROPOSAL_SOURCE='772e5a6746513666902c52f64924476196ee8c7b'
FINANCIAL_SOURCE='f467c11678fb75097d1d448eefc2a2aff33fa388'

def saved(bound):return e.strict_json(e.checked(bound))

def planning_ceiling(binding=None):
    """Explicit activated amendment only; legacy planning retains stage200."""
    if binding is None:return 387429960800
    import earnings_population_additional_budget as budget
    with closing(sqlite3.connect('file:'+str(budget.old.LEDGER)+'?mode=ro',uri=True)) as db:
        grant=budget.read_grant(db,required_binding=binding)
    if grant is None:raise ValueError('Activated original additional100 grant required')
    return grant['stage']['charged_nano_usd']+grant['stage_additional_ceiling_nano_usd']

def accepted_source(descriptor,runtime,member,checkpoint):
    """One sealed137->138->142 exception, never generic Source equivalence.

    The completed report already authenticated every original private closure
    and public row. Pin that exact evidence and checkpoint, not current source
    files or repeated Native gates. Original137 gatefalse stays false.
    """
    if descriptor['source_commit']==runtime['source_commit']:return True
    if (member.get('descriptor')!=FINANCIAL_DESCRIPTOR or member.get('report')!=FINAL_REPORT
            or checkpoint!=FINAL_GIT or runtime['source_commit']!=ORIGINAL_PROPOSAL_SOURCE
            or descriptor['source_commit']!=FINANCIAL_SOURCE):return False
    report=saved(FINAL_REPORT);cp=saved(FINAL_GIT);exact=saved(FINANCIAL_DESCRIPTOR)
    if (descriptor!=exact or report['frozen']!=FINANCIAL_DESCRIPTOR
            or cp.get('report')!=FINAL_REPORT or cp.get('commit')!='2012979470bba20cae9812358da16a064b5eccd7'
            or cp.get('every_blob_readback_verified') is not True
            or report['comparison']['scored']!=25 or report['comparison']['not_measured']!=0):return False
    proposal=saved(descriptor['proposal'])
    if (saved(proposal['runtime'])!=runtime or proposal.get('status')!='PROPOSAL_REVIEWED_ACCEPTED'
            or descriptor['candidate']['id']!='37af4ddad70dad464e6a795fd8a4eec9425c283e1c18f583ff0287c8d16eb971'):
        return False
    from earnings_population_additional_execution import OLD
    old=saved(OLD)
    bridge=saved(descriptor['execution_rebind']);native=saved(old['execution_rebind'])
    if (descriptor!=dict(old,source_commit=FINANCIAL_SOURCE,execution_rebind=descriptor['execution_rebind'])
            or bridge.get('original_descriptor')!=OLD
            or bridge.get('original_source_commit')!='10222cacae90c90bbdf526a327ccc0aaaa0aaadf'
            or bridge.get('new_source_commit')!=FINANCIAL_SOURCE
            or descriptor['execution_rebind']['sha256']!='ae2591c430c646d846082837e6338c8f84a71d7b86184fedbf0f82cccac1a743'
            or old['execution_rebind']['sha256']!='b535ff4cc41b7a1bcfb8c93d370c2da4b0a39f53fcad991cbfb91fa9ca980019'):
        return False
    original=saved(native['original_descriptor']);archive=saved(native['archive'])
    if (original['source_commit']!=ORIGINAL_PROPOSAL_SOURCE
            or original['proposal']!=descriptor['proposal'] or original['candidate']!=descriptor['candidate']
            or archive.get('commit')!='eb4a765b62aedc7e2ef0fc4d9ececf65867351a6'
            or archive.get('every_blob_readback_verified') is not True):return False
    closure=saved(dict(path=str(training.ROOT/'TRAIN25-CLEAN137-CLOSED-CLOSURE.json'),
        sha256='38ba90c743e0dfb3d9248e6de884894a1b84300a75109ddeaac4c4d72414958f'))
    return (closure.get('original_accepted_gate_passed') is False
        and closure.get('corrected_native_metadata_gate_passed') is True
        and closure.get('candidate')==descriptor['candidate']
        and descriptor['forecast_limits']==runtime['limits']['forecast']
        and descriptor['rates']==runtime['rates']
        and descriptor['forecast_sources']=={k:runtime['sources'][k] for k in descriptor['forecast_sources']})

def code_depth(identifier,root,versions):
    depth=0;seen=set()
    while identifier!=root:
        if identifier in seen or identifier not in versions:raise ValueError('Unknown or cyclic actual code ancestry')
        seen.add(identifier);identifier=versions[identifier].get('parent');depth+=1
    return depth

def validate(frontier,population,preserved):
    import earnings_population_coevolution as policy
    if (frontier.get('layered_authority')!=AUTHORITY or frontier.get('layered_policy')!=POLICY
            or frontier.get('direct_authority')!=policy.FRONTIER_AUTHORITY
            or frontier.get('no_backfill_authority')!=policy.NO_BACKFILL_AUTHORITY
            or frontier.get('prospective') is not True or frontier.get('historical_backfill') is not False):
        raise ValueError('Exact prospective layered authority and no-backfill bindings required')
    saved(AUTHORITY);saved(POLICY)
    training_ids=training.load_scope(dict(path=str(training.SPLIT),sha256=training.SPLIT_SHA))['training']
    if frontier['training']!=training_ids:raise ValueError('Original frozen training25 required')
    reference=frontier['prediction_reference'];inc=policy.complete_member(reference,training_ids)
    if (reference.get('status')!='prediction_incumbent' or inc['id']!=frontier['incumbent_id']
            or saved(frontier['previous_stable'])['selected']!=reference['descriptor']
            or frontier['prediction_decision'].get('selected')!=reference['descriptor']):
        raise ValueError('Separate protected read-only full25 prediction reference required')
    registered=population['versions'].get(inc['id'])
    if registered!=inc and not (registered==preserved['versions'].get(inc['id'])
            and registered is not None and all(registered[k]==inc[k] for k in ('id','R','H'))):
        raise ValueError('Prediction reference code differs from preserved original pool')
    members=frontier['members'];ids=[m['version_id'] for m in members]
    if len(ids)>3 or len(set(ids))!=len(ids) or inc['id'] in ids:
        raise ValueError('Globally2-3 growth parents; prediction reference is not a growth seat')
    shortfall=max(0,2-len(ids))
    if (frontier.get('growth_shortfall')!=shortfall
            or frontier.get('layer_status')!=('FRONTIER_SHORTFALL' if shortfall else 'READY_DEPTH_LAYER')
            or shortfall and (not frontier.get('shortfall_reason') or frontier.get('layer_complete') is not False)):
        raise ValueError('Fewer2 is explicit incomplete FRONTIER_SHORTFALL, never invented seats')
    depth=frontier['growth_depth']
    if type(depth) is not int or depth<1:raise ValueError('Actual code depth required')
    previous=saved(frontier['previous_frontier']);progress=saved(frontier['preceding_outcomes'])
    if (type(frontier.get('generation')) is not int or frontier['generation']<1
            or progress.get('frontier')!=frontier['previous_frontier']
            or frontier['generation']!=previous['generation']+1):raise ValueError('No skipped generation or unrelated outcomes')
    children=policy.generation_outcomes(previous,progress,complete=True)
    pool={m['version_id']:m for m in [*previous['members'],*children]}
    considered={m['version_id']:m for m in frontier['considered']}
    if (len(considered)!=len(frontier['considered']) or set(considered)!=set(pool)
            or any(any(considered[k][f]!=m[f] for f in ('descriptor','report','mean')) for k,m in pool.items())):
        raise ValueError('Consider surviving parents plus genuine evaluated children; no archived backfill')
    if any(m['mean']>reference['mean'] for m in considered.values()):
        raise ValueError('Do not keep a worse prediction reference after strict full25 improvement')
    if previous.get('schema')==SCHEMA:
        next_ids={m['version_id'] for m in children}
        if (depth!=previous['growth_depth']+1 or not set(ids)<=next_ids
                or frontier['growth_root_id']!=previous['growth_root_id']):
            raise ValueError('Next depth layer selects evaluated children globally, not mixed-depth ancestors')
    elif (frontier.get('transition_from_legacy') is not True or not frontier.get('historical_omissions')
            or frontier.get('growth_root_id')!=inc['id']):
        raise ValueError('Explicit first v4 transition, not retroactive legacy tree compliance')
    remaining=policy.provisional_budget(frontier)
    assessments={a['version_id']:a for a in frontier['qualification']}
    if len(assessments)!=len(frontier['qualification']) or set(assessments)!=set(pool):
        raise ValueError('One separate-axis assessment for every considered node required')
    eligible=set()
    for identifier,node in considered.items():
        assessment=assessments[identifier]
        policy.complete_member(node,training_ids)
        same_depth=code_depth(identifier,frontier['growth_root_id'],population['versions'])==depth
        if previous.get('schema')==SCHEMA:same_depth=same_depth and identifier in next_ids
        qualified=policy.provisional_eligible(assessment,remaining) and same_depth
        if type(assessment.get('eligible')) is not bool or assessment['eligible'] is not qualified:
            raise ValueError('Eligibility must reflect real same-depth safe authentic affordable tests')
        if qualified:eligible.add(identifier)
        for axis in ('prediction_quality','research_capability','harness_capability'):
            if not isinstance(assessment.get(axis),str) or not assessment[axis].strip():raise ValueError('Separate three-axis findings required')
        if not assessment.get('evidence'):raise ValueError('Actual retention evidence required')
        for bound in assessment['evidence']:e.checked(bound)
    if (not set(ids)<=eligible or len(eligible)>=2 and not 2<=len(ids)<=min(3,len(eligible))
            or len(eligible)<2 and set(ids)!=eligible):
        raise ValueError('Select2-3 real eligible growth parents; cannot manufacture FRONTIER_SHORTFALL')
    if frontier['growth_shortfall']!=max(0,2-len(eligible)):
        raise ValueError('Shortfall derives from eligible states, not an arbitrarily reduced selection')
    for member in members:
        version=policy.complete_member(member,training_ids);assessment=assessments[version['id']]
        if (any(member[k]!=considered[version['id']][k] for k in ('descriptor','report','mean'))
                or population['versions'].get(version['id'])!=version
                or code_depth(version['id'],frontier['growth_root_id'],population['versions'])!=depth):
            raise ValueError('Every growth parent must have exact registered same-depth actual ancestry')
        if not policy.provisional_eligible(assessment,remaining) or assessment.get('eligible') is not True:
            raise ValueError('Safe authentic technically-valid distinct credible affordable growth test required')
        for axis in ('prediction_quality','research_capability','harness_capability'):
            if not isinstance(assessment.get(axis),str) or not assessment[axis].strip():raise ValueError('Separate three-axis findings required')
        if not assessment.get('evidence'):raise ValueError('Actual retention evidence required')
        for bound in assessment['evidence']:e.checked(bound)
        if member.get('status') not in ('provisional','validated_within_scope'):raise ValueError('Provisional is not demonstrated improvement')
        if member['status']=='validated_within_scope':
            finding=saved(assessment['validated_gain_evidence']) if assessment.get('validated_gain_evidence') else {}
            if (assessment.get('demonstrated_improvement') is not True or finding.get('validated_learning') is not True
                    or finding.get('actual_use') is not True or not finding.get('measured_benefit')
                    or any(finding.get(k)!=member[k] for k in ('version_id','descriptor','report'))):
                raise ValueError('Validated gain requires actual use and measured node-specific benefit')
    groups=frontier['expansions'];parents=[g['parent_id'] for g in groups]
    if len(set(parents))!=len(parents) or set(parents)!=set(ids):raise ValueError('Every retained growth parent must expand')
    questions=set();hypotheses=set();required=0
    for group in groups:
        if len(group['children'])!=3:raise ValueError('Each retained growth parent requires EXACTLY3 distinct children')
        for child in group['children']:
            for key in ('hypothesis_id','question','support_observation','refute_observation','exit_criterion'):
                if not isinstance(child.get(key),str) or not child[key].strip():raise ValueError('Observable distinct test and exit required')
            if child['hypothesis_id'] in hypotheses or child['question'] in questions:raise ValueError('Duplicate hypotheses are not independent children')
            hypotheses.add(child['hypothesis_id']);questions.add(child['question']);cost=child.get('estimated_cost_nano_usd')
            if type(cost) is not int or cost<=0:raise ValueError('Explicit positive cost estimate required')
            required+=cost
        assessment=assessments[group['parent_id']];first=assessment['next_test']
        matching=[c for c in group['children'] if c['hypothesis_id']==first['hypothesis_id']]
        if (len(matching)!=1 or any(first[k]!=matching[0][k] for k in ('question','support_observation','refute_observation','exit_criterion'))
                or matching[0]['estimated_cost_nano_usd']!=assessment['eligibility']['estimated_next_test_nano_usd']):
            raise ValueError('Eligibility must bind a declared actual next test')
    if (frontier.get('estimated_expansion_cost_nano_usd')!=required
            or frontier.get('expansion_budget_shortfall_nano_usd')!=max(0,required-remaining)
            or required>remaining and not frontier.get('expansion_budget_shortfall_reason')):
        raise ValueError('Exact planning shortfall required; estimates are not reservations or money')
    return frontier
