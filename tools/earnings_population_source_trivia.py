"""Exact126 only: one-comment normalization of closed125, FIRST Review.

No new C/A, source execution, generic recovery flag or resource relaxation.
"""
import ast
from pathlib import Path
import subprocess
from earnings_entry import checked
from earnings_open_program import program
from earnings_population_roles import message,scientific
from earnings_population_delta_author import _edit_source
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import earnings_population_training25 as training

REVIEW_ID='edgar-population-20261016-126'
DESCRIPTOR=dict(path=str(training.ROOT/'TRAIN25-CLEAN126-SOURCE-TRIVIA-REPAIR.json'),
    sha256='f99963fe04e105694e653edd033bd28567f3a4a9bb8e4ac9b8d5a5c50ae24145')

def metadata(binding):
    from earnings_population_coevolution import AUTHORITY
    if binding!=DESCRIPTOR:raise ValueError('Exact126 source-trivia descriptor required')
    checked(AUTHORITY);fixed=engine.read(binding);child=fixed['candidate'];audit=engine.read(fixed['closure'])
    if (fixed.get('schema')!='edgar25_once126_source_trivia_first_review_v1' or fixed.get('review_id')!=REVIEW_ID
            or fixed.get('logical_round')!=14 or fixed.get('authority')!=AUTHORITY
            or fixed.get('source_axis')!='R' or fixed.get('PROGRAM_AST_unchanged') is not True
            or fixed.get('C_A_regeneration') is not False or fixed.get('original_Review_absent') is not True
            or fixed.get('original_implement_absent') is not True
            or child.get('axis')!='R' or child.get('id')!='8bd53392af4b7a151961a88dfd7c691f4b05d260dc1b662b4b83bfddbaccf03e'
            or child.get('parent')!='03a87b7b84629aed9dc5fc738b3f2be42e7c49fda8aba346718d8e7359ca67da'
            or child['R']!=fixed['source'] or child['R']['sha256']!='0c37f522327612605dda9c18fb4e1bbc277e80b703f59cd393b064da481a65c8'
            or child['H']!=fixed['original_parent_H'] or child['H']['sha256']!='6d80fa56d0625188f4357d791a725083a6bab75119c0736424516b3dc5681350'
            or child['id']!=digest({a:child[a]['sha256'] for a in ('R','H')})
            or audit.get('status')!='FAILED_NO_RETRY' or audit.get('original_true_exit')!=1
            or audit.get('owned_generations')!=16 or audit.get('owned_cost_nano_usd')!=885383200
            or audit.get('all_owned_settled') is not True or audit.get('pending_count')!=0
            or audit.get('pending_full_reserved_nano_usd')!=0
            or audit.get('original_failure')!=fixed['original_failure']
            or engine.read(fixed['original_git']).get('commit')!='c1b45e3e6b89b324a8edfb5faa040e795c17bb31'
            or (training.ROOT/'attempts/edgar-population-20261016-125/roles/review-01').exists()
            or (training.ROOT/'attempts/edgar-population-20261016-125/loop/round-0001-implement.done.json').exists()):
        raise ValueError('Closed125 size failure, exact source/parent, settled fees and no original Review required')
    original=message(engine.read(fixed['original_response']))
    chosen=engine.read(fixed['original_decision'])['decision'];before=engine.read(fixed['original_source'])['source_text']
    parent=checked(fixed['original_parent_R']).decode();after=checked(child['R']).decode()
    proof=engine.read(fixed['validation']);comment='# Target-specific row identity is an admission gate, not a new financial model.'
    if (original['parent_source_sha256']!=fixed['original_parent_R']['sha256']
            or original['decision_sha256']!=digest(scientific(chosen)) or chosen['parent_pair_sha256']!=child['parent']
            or engine.read(fixed['scientific_decision'])['scientific_decision']!=scientific(chosen)
            or child['method']!=chosen['hypothesis'] or fixed['parent']['id']!=child['parent']
            or fixed['parent']['R']!=fixed['original_parent_R'] or fixed['parent']['H']!=fixed['original_parent_H']
            or fixed['original_parent_R']['sha256']!='0f28a60a7cbf942674b5b9a95d12a16b9cd7c501a564519dd3553f34a75470d7'
            or _edit_source(parent,original['edits'])!=before or not before.startswith(parent)
            or before.count(comment)!=1 or comment in parent or after!=before.replace(comment,'',1)
            or len(before.encode())!=65571 or len(after.encode())!=65492
            or ast.dump(ast.parse(before),include_attributes=False)!=ast.dump(ast.parse(after),include_attributes=False)
            or proof.get('PROGRAM_AST_unchanged') is not True or proof.get('exact_one_comment_removal') is not True
            or proof.get('original_cases_unchanged') is not True or proof.get('model_calls')!=0
            or proof.get('normalized_bytes')!=65492 or proof.get('removed_UTF8_bytes')!=79 or proof.get('limit_bytes')!=65536
            or proof.get('normalized_source')!=child['R'] or proof.get('tests')!=fixed['tests']
            or proof.get('host_candidate_execution') is not False or proof.get('Native_calls')!=0
            or proof.get('ledger_writes')!=0 or proof.get('heldout_read') is not False):
        raise ValueError('Only the exact79byte comment deletion and original scientific decision are admitted')
    program(after.encode(),'R')  # Original65,536-byte AST/metadata checker; no code execution.
    syntax=ast.parse(original['test_text']);cases=ast.literal_eval(syntax.body[0].value)
    tests=engine.read(fixed['tests'])
    if (len(syntax.body)!=1 or type(tests) is not list or len(tests)!=5 or tests!=cases
            or len(checked(fixed['tests']))>32768 or len(original['test_text'].encode())!=9266
            or any(type(c) is not dict or set(c)!={'input','expected'} for c in tests)):
        raise ValueError('Five original full-exact CASES required, no test mutation or cap increase')
    for bound in bindings(fixed):checked(bound)
    return fixed

def bindings(fixed):
    return [fixed[k] for k in ('closure','original_git','original_inputs_git','original_failure','original_response',
        'original_decision','original_feedback','original_source','original_source_diagnosis','scientific_decision',
        'original_parent_R','original_parent_H','source','tests','validation','tree_reconciliation','tree_reconciliation_git')]

def originals(fixed):
    """Selected original bytes only; no repeated historical/Native/scorer gate."""
    from earnings_entry import REPO
    checkpoints=[engine.read(fixed[k]) for k in ('original_git','original_inputs_git')]
    if any(c.get('every_blob_readback_verified') is not True for c in checkpoints):raise ValueError('Original125 private seals required')
    for key in ('closure','original_failure','original_response','original_decision','original_feedback','original_parent_R','original_parent_H'):
        bound=fixed[key];found=[(cp,alias) for cp in checkpoints for alias,value in cp['artifacts'].items() if value==bound]
        if not found:raise ValueError('Original125 saved binding missing')
        cp,alias=found[0]
        raw=subprocess.run(['git','show',cp['commit']+':'+alias],cwd=REPO,check=True,capture_output=True).stdout
        if raw!=checked(bound):raise ValueError('Original125 private blob differs')
