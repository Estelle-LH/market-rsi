"""Exact153 ->154 FIRST Review; one81-byte appended comment, no paid retry."""
import ast
import io
import tokenize
from pathlib import Path
from earnings_entry import checked
from earnings_open_program import program
from earnings_population_roles import message, scientific
from earnings_population_delta_author import _edit_source
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import earnings_population_training25 as training

REVIEW_ID='edgar-population-20261016-154'
DESCRIPTOR=dict(path=str(training.ROOT/'TRAIN25-CLEAN154-SOURCE-TRIVIA-REPAIR.json'),
 sha256='57be4dda17bd7eba27de40423feadee595a0a6dca7da9df2b3b93b42c55cce7a')
SCHEMA='edgar25_once154_source_trivia_first_review_v1'
PARENT='5e2270f66472d1faf3ae84c22cc79bfaef387a3e83133836ce06dc718fd71570'
COMMENT='# Origin-complete acquisition experiment. Index projections below are acquisition'
EXTRA_KEYS=('original_runtime','original_controller_context','original_author_context',
 'original_source_plan','original_origin','original_controller_fees','original_author_fees')

def normalize(source):
    """Delete the exact model-appended COMMENT only, preserving all other bytes."""
    tokens=[t for t in tokenize.generate_tokens(io.StringIO(source).readline)
        if t.type==tokenize.COMMENT and t.string==COMMENT]
    if len(tokens)!=1 or tokens[0].start!=(989,0) or tokens[0].end!=(989,81):
        raise ValueError('Exact original appended81byte comment required')
    token=tokens[0];lines=source.splitlines(keepends=True);row=token.start[0]-1
    lines[row]=lines[row][:token.start[1]]+lines[row][token.end[1]:]
    result=''.join(lines)
    if ast.dump(ast.parse(source),include_attributes=False)!=ast.dump(ast.parse(result),include_attributes=False):
        raise ValueError('Comment deletion changed full AST')
    return result

def bindings(fixed):
    from earnings_population_source_trivia import bindings as legacy_bindings
    return legacy_bindings(fixed)+[fixed[k] for k in EXTRA_KEYS]

def metadata(binding):
    from earnings_population_coevolution import AUTHORITY, PLAN
    if binding!=DESCRIPTOR:raise ValueError('Exact154 descriptor required')
    checked(AUTHORITY);fixed=engine.read(binding);child=fixed['candidate'];audit=engine.read(fixed['closure'])
    original_root=training.ROOT/'attempts/edgar-population-20261016-153'
    if (fixed.get('schema')!=SCHEMA or fixed.get('review_id')!=REVIEW_ID
            or type(fixed.get('logical_round')) is not int or fixed['logical_round']!=17
            or fixed.get('authority')!=AUTHORITY or fixed.get('source_axis')!='R'
            or fixed.get('PROGRAM_AST_unchanged') is not True or fixed.get('C_A_regeneration') is not False
            or fixed.get('original_Review_absent') is not True or fixed.get('original_implement_absent') is not True
            or child.get('axis')!='R' or child.get('parent')!=PARENT
            or child['id']!='2493840dd5316742386e4123999bb40ba8baac9cdb5251b216dbeed31fa26c74'
            or child['R']!=fixed['source'] or child['R']['sha256']!='75f698c2a138d6ddbc94b01c9f9eca3cd1d8043f8a3ac02ab24c1656bee06f54'
            or child['H']!=fixed['original_parent_H'] or child['H']['sha256']!='6d80fa56d0625188f4357d791a725083a6bab75119c0736424516b3dc5681350'
            or child['id']!=digest({a:child[a]['sha256'] for a in ('R','H')})
            or fixed['closure']['sha256']!='b6607cd0ee9691f9f762a85c473beb360a4693491af4df74cd5da2f6c6b5a7e1'
            or audit.get('status')!='FAILED_NO_RETRY' or audit.get('original_true_exit')!=1
            or audit.get('owned_generations')!=16 or audit.get('owned_cost_nano_usd')!=844902600
            or audit.get('all_owned_settled') is not True or audit.get('pending_count')!=0
            or audit.get('pending_full_reserved_nano_usd')!=0
            or len(audit.get('owned_fee_rows',[]))!=16
            or any(x.get('status')!='settled' for x in audit['owned_fee_rows'])
            or sum(x['charged_nano_usd'] for x in audit['owned_fee_rows'])!=844902600
            or audit.get('original_failure')!=fixed['original_failure'] or audit.get('runtime')!=fixed['original_runtime']
            or engine.read(fixed['original_git']).get('commit')!='809fdc3706ed3f820125610878d8681e4f7e4050'
            or engine.read(fixed['original_inputs_git']).get('commit')!='c9bdc091aba925e41aec3334cdc612f4086e098d'
            or (original_root/'roles/review-01').exists()
            or (original_root/'loop/round-0001-implement.done.json').exists()):
        raise ValueError('Exact153 closed size failure, all settled and absent CASE/Review required')
    runtime=engine.read(fixed['original_runtime']);task=engine.read(engine.read(runtime['forecast_study'])['clean_slate_task'])
    plan=engine.read(fixed['original_source_plan']);origin=engine.read(fixed['original_origin'])
    if (runtime['id']!='edgar-population-20261016-153'
            or runtime['source_commit']!='f8fd73c768088744759c23f36dfece80822a30c5'
            or type(runtime.get('clean_learning_round')) is not int or runtime['clean_learning_round']!=17
            or task['mode']!='proposal' or task['feedback']!=fixed['original_feedback']
            or task['round2_origin']!=fixed['original_origin'] or plan['origin']!=fixed['original_origin']
            or fixed['original_source_plan']['sha256']!=runtime['sources'][PLAN]['sha256']
            or origin['parent']!=fixed['parent'] or fixed['parent']['id']!=PARENT
            or origin['public_feedback']['sha256']!=fixed['original_feedback']['sha256']):
        raise ValueError('Original153 source-plan/origin/task/feedback must stay original')
    # The existing decoder selects ONLY final public output_text; reasoning is ignored.
    public=message(engine.read(fixed['original_response']));chosen=engine.read(fixed['original_decision'])['decision']
    before=engine.read(fixed['original_source'])['source_text'];after=checked(child['R']).decode()
    parent=checked(fixed['original_parent_R']).decode();proof=engine.read(fixed['validation'])
    if (public['parent_source_sha256']!=fixed['original_parent_R']['sha256']
            or fixed['original_parent_R']['sha256']!='be29280556415e4de24f94375e5bcc8bfa1f3d756554478670d5c7b74c4207a0'
            or chosen['parent_pair_sha256']!=PARENT or chosen['feedback_sha256']!=digest(task['feedback'])
            or public['decision_sha256']!=digest(scientific(chosen))
            or engine.read(fixed['scientific_decision'])['scientific_decision']!=scientific(chosen)
            or child['method']!=chosen['hypothesis']
            or any(fixed['parent'][a]!=fixed['original_parent_'+a] for a in ('R','H'))
            or _edit_source(parent,public['edits'])!=before or not before.startswith(parent) or not after.startswith(parent)
            or normalize(before)!=after or (len(before.encode()),len(after.encode()))!=(65561,65480)
            or any(proof.get(k) is not True for k in ('PROGRAM_AST_unchanged','exact_one_comment_removal','original_cases_unchanged'))
            or any(proof.get(k)!=v for k,v in dict(original_bytes=65561,normalized_bytes=65480,
                removed_UTF8_bytes=81,limit_bytes=65536,case_count=4,model_calls=0,Native_calls=0,
                ledger_writes=0,host_candidate_execution=False,heldout_read=False).items())
            or proof.get('normalized_source')!=child['R'] or proof.get('tests')!=fixed['tests']):
        raise ValueError('Exact81byte appended-comment deletion, original parent/decision only')
    program(after.encode(),'R')  # Static bounds/AST metadata only; never run().
    syntax=ast.parse(public['test_text']);tests=engine.read(fixed['tests'])
    if (len(syntax.body)!=1 or not isinstance(syntax.body[0],ast.Assign)
            or len(syntax.body[0].targets)!=1 or not isinstance(syntax.body[0].targets[0],ast.Name)
            or syntax.body[0].targets[0].id!='CASES' or type(tests) is not list or len(tests)!=4
            or tests!=ast.literal_eval(syntax.body[0].value) or len(checked(fixed['tests']))>32768
            or len(public['test_text'].encode())!=13905
            or any(type(c) is not dict or set(c)!={'input','expected'} for c in tests)):
        raise ValueError('Four original full-exact CASES unchanged, no expected repair')
    for key,sha in (('original_controller_context','26115890a4e1d304fb5d585e5e81a7f7c181736efc7f52274ac8aec15bda55eb'),
                    ('original_author_context','2ebc8bc801a569260d6f7fe6fe983c60e9b7e573e7812eabfbe7a7b59b164503')):
        context=engine.read(fixed[key])
        if (fixed[key]['sha256']!=sha or context.get('authority')!=fixed['original_runtime']
                or context.get('source_commit')!=runtime['source_commit'] or context.get('pool_version')!=fixed['parent']):
            raise ValueError('Original153 C/A Native context identity changed')
    for key in ('original_controller_fees','original_author_fees'):
        fees=engine.read(fixed[key])
        if fees.get('blocked') is not False or fees.get('unresolved_reserved_usd')!=0:
            raise ValueError('Original153 financial summaries not closed')
    for bound in bindings(fixed):checked(bound)
    return fixed

def originals(fixed):
    """Verify selected original153 private aliases; no repeated Native/gate."""
    import subprocess
    from earnings_entry import REPO
    checkpoints=[engine.read(fixed[k]) for k in ('original_git','original_inputs_git')]
    if any(c.get('every_blob_readback_verified') is not True for c in checkpoints):
        raise ValueError('Original153 private seals required')
    keys=('closure','original_failure','original_response','original_decision','original_feedback',
        'original_parent_R','original_parent_H',*EXTRA_KEYS)
    for key in keys:
        bound=fixed[key];found=[(cp,alias) for cp in checkpoints for alias,v in cp['artifacts'].items() if v==bound]
        if not found:raise ValueError('Original153 private saved binding missing: '+key)
        cp,alias=found[0]
        raw=subprocess.run(['git','show',cp['commit']+':'+alias],cwd=REPO,check=True,capture_output=True).stdout
        if raw!=checked(bound):raise ValueError('Original153 private blob differs: '+key)
