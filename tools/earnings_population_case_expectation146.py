"""Exact145->146 FIRST Review: unchanged PROGRAM, one incomplete expected list.

Not a generic test-repair or provider-retry switch. Static/saved evidence does
not establish financial correctness; original isolated CASE/probes/Review do.
"""
import ast
from earnings_entry import checked
from earnings_open_program import program
from earnings_population_roles import scientific
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness.feedback_linked_loop import _read_pair
import earnings_population_training25 as training
from pathlib import Path

REVIEW_ID='edgar-population-20261016-146'
DESCRIPTOR=dict(path=str(training.ROOT/'TRAIN25-CLEAN146-CASE-EXPECTATION-REPAIR.json'),
    sha256='7fd4b48f93d21bb7a936edfa1936bdecdb3d74b84dbc8e0ba21f8b9d5873b1be')
SCHEMA='edgar25_once146_unchanged_program_first_review_case_v1'
EXTRA_KEYS=('original_runtime','original_decision','parent_R','static_diagnosis')


def metadata(binding):
    from earnings_population_coevolution import AUTHORITY
    if binding!=DESCRIPTOR: raise ValueError('Exact146 descriptor required')
    checked(AUTHORITY)
    f=engine.read(binding);child=f['candidate'];c=engine.read(f['closure'])
    root=training.ROOT/'attempts/edgar-population-20261016-145'
    if (f.get('schema')!=SCHEMA or f.get('review_id')!=REVIEW_ID
            or type(f.get('logical_round')) is not int or f['logical_round']!=16
            or f.get('authority')!=AUTHORITY or f.get('PROGRAM_unchanged') is not True
            or f.get('C_A_regeneration') is not False or f.get('source_axis')!='R'
            or child!=f['original_candidate'] or child.get('axis')!='R'
            or child.get('parent')!='5e2270f66472d1faf3ae84c22cc79bfaef387a3e83133836ce06dc718fd71570'
            or child.get('id')!='e0942156058d8f2477250cbb2316200317666e1dc9c3cd324f79073ee4befb28'
            or child['R']!=f['source'] or child['R']['sha256']!='942a4bfe975277cdb8e9f5331cc2348f5a0e022295996e5870afe677737daea3'
            or child['H']['sha256']!='6d80fa56d0625188f4357d791a725083a6bab75119c0736424516b3dc5681350'
            or child['id']!=digest({a:child[a]['sha256'] for a in ('R','H')})
            or _read_pair(Path(f['original_implement']['path']))['output']['candidate']!=child
            or f['closure']['sha256']!='72770e184a77822d8eedbc5131dda06507ba7723cc2a7062a3073ced52641a5b'
            or any(c.get(k)!=v for k,v in dict(status='PROPOSAL_NOT_ACCEPTED',original_true_exit=0,
                owned_generations=16,owned_cost_nano_usd=695323000,pending_count=0,pending_full_reserved_nano_usd=0).items())
            or c.get('all_owned_settled') is not True or c['runtime']!=f['original_runtime']
            or engine.read(f['original_git']).get('commit')!='0950533f179833adbb6553d9697751ffecced18e'
            or list((root/'roles/review-01').glob('[0-9][0-9]-request.json'))
            or engine.read(f['original_review']).get('rationale')!='MODEL_CASES_FAILED; inspect preserved case evidence'):
        raise ValueError('Sealed145 CASE-only rejection, identical PROGRAM/parent and no paid Review required')
    runtime=engine.read(f['original_runtime']);task=engine.read(engine.read(runtime['forecast_study'])['clean_slate_task'])
    chosen=engine.read(f['original_decision'])['decision']
    if (runtime['id']!='edgar-population-20261016-145'
            or runtime['source_commit']!='5b3ec2eae7d15a96c26530e9ad70cc284e446616'
            or task['feedback']!=f['original_feedback'] or chosen['feedback_sha256']!=digest(task['feedback'])
            or chosen['parent_pair_sha256']!=child['parent'] or child['method']!=chosen['hypothesis']
            or engine.read(f['scientific_decision'])['scientific_decision']!=scientific(chosen)
            or f['parent_R']['sha256']!='be29280556415e4de24f94375e5bcc8bfa1f3d756554478670d5c7b74c4207a0'):
        raise ValueError('Original145 decision/feedback identity and actual5e22 parent must remain original')
    source=checked(child['R']);program(source,'R')  # Original static validator, never run().
    syntax=ast.parse(checked(f['original_tests']))
    if len(syntax.body)!=1 or not isinstance(syntax.body[0],ast.Assign): raise ValueError('Literal original CASES required')
    old=ast.literal_eval(syntax.body[0].value);new=engine.read(f['tests'])
    results=engine.read(f['original_case_results'])['results']
    expected=dict(research_requests=[dict(tool='read_file',arguments=dict(path='filings/apple.txt',offset=n,characters=20000)) for n in (0,20000)])
    if (len(source)!=63341 or type(new) is not list or len(old)!=5 or len(new)!=5
            or len(checked(f['tests']))>32768 or any(type(c) is not dict or set(c)!={'input','expected'} for c in new)
            or any(new[i]['input']!=old[i]['input'] for i in range(5)) or new[1:]!=old[1:]
            or old[0]['expected']!=dict(research_requests=expected['research_requests'][:1]) or new[0]['expected']!=expected
            or [r['passed'] for r in results]!=[False,True,True,True,True]
            or any(r['execution']['value']!=new[i]['expected'] for i,r in enumerate(results))):
        raise ValueError('Only CASE0 omitted original second page may change; all5 inputs/other4 expected stay exact')
    proof=engine.read(f['validation']);replay=engine.read(f['exact_saved_replay'])
    if (any(proof.get(k) is not True for k in ('PROGRAM_unchanged','inputs_unchanged','last4_expected_unchanged','run_cases_exact_equality_unchanged'))
            or any(proof.get(k)!=v for k,v in dict(source=child['R'],corrected_tests=f['tests'],original_tests=f['original_tests'],
                corrected_only_indices=[0],test_bytes=len(checked(f['tests'])),test_limit_bytes=32768,case_count=5,
                model_calls=0,Native_calls=0,ledger_writes=0,host_candidate_execution=False,heldout_read=False,validated_learning=False).items())
            or proof.get('independent_static_diagnosis')!=f['static_diagnosis']
            or engine.read(f['static_diagnosis']).get('bounded_first_Review_correction_technically_justified') is not True
            or any(replay.get(k)!=v for k,v in dict(source=child['R'],tests=f['tests'],all5_exact_equal=True,
                not_a_fresh_execution=True,host_candidate_execution=False,model_calls=0,ledger_writes=0,validated_learning=False).items())
            or replay['rows']!=[dict(index=i,execution=r['execution'],exact_equal=True) for i,r in enumerate(results)]):
        raise ValueError('Exact independent static/saved proof required; not a fresh execution or learning claim')
    before=ast.parse(checked(f['parent_R']));after=ast.parse(source)
    funcs=lambda tree,name:[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name]
    dump=lambda n:ast.dump(n,include_attributes=False)
    joins=[]
    for name,pi,ci in (('_plan',0,0),('_plan',-1,-1),('_index',-1,-1),('_targets',-1,-1),('_anchor_date_parent_run',-1,-1),('run',-1,-2)):
        p=funcs(before,name)[pi];n=funcs(after,name)[ci]
        if dump(p)!=dump(n): raise ValueError('Original parent acquisition callable changed')
        joins.append(dict(name=name,parent_line=p.lineno,child_line=n.lineno,AST_equal=True,AST_sha256=digest(dump(p))))
    if joins!=proof['unchanged_parent_callable_joins']: raise ValueError('Parent callable proof differs')
    for key in ('original_implement','original_tests','original_case_results','scientific_decision','original_feedback',*EXTRA_KEYS): checked(f[key])
    checked(child['H'])
    return f
