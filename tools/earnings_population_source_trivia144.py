"""Finite143 ->144 first Review: source trivia only, never a provider retry.

The original failed Author remains failed. Static AST equality is not CASE or
financial correctness; original Services.review must still decide both.
"""
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

REVIEW_ID = 'edgar-population-20261016-144'
DESCRIPTOR = dict(path=str(training.ROOT/'TRAIN25-CLEAN144-SOURCE-TRIVIA-REPAIR.json'),
    sha256='604c343c41b2c7e6b0f1b3e085c2c5dfbcc80909e1a6e4d48b911563f2db512c')
SCHEMA = 'edgar25_once144_source_trivia_first_review_v1'


def normalize(source):
    """Remove COMMENT tokens and blank lines not occupied by STRING tokens."""
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    protected = {r for t in tokens if t.type == tokenize.STRING
                 for r in range(t.start[0], t.end[0]+1)}
    lines = source.splitlines(keepends=True)
    for t in reversed([t for t in tokens if t.type == tokenize.COMMENT]):
        if t.start[0] != t.end[0]: raise ValueError('Unexpected multiline comment token')
        row = t.start[0]-1
        lines[row] = lines[row][:t.start[1]]+lines[row][t.end[1]:]
    result = ''.join(line for r,line in enumerate(lines,1) if r in protected or line.strip())
    if ast.dump(ast.parse(source), include_attributes=False) != ast.dump(ast.parse(result), include_attributes=False):
        raise ValueError('Source trivia changed the AST')
    return result


def bindings(fixed):
    from earnings_population_source_trivia import bindings as original_bindings
    return original_bindings(fixed) + [fixed[k] for k in
        ('original_runtime','original_controller_context','original_author_context')]


def metadata(binding):
    from earnings_population_coevolution import AUTHORITY
    if binding != DESCRIPTOR: raise ValueError('Exact144 descriptor required')
    checked(AUTHORITY)
    fixed=engine.read(binding);child=fixed['candidate'];audit=engine.read(fixed['closure'])
    original_root=training.ROOT/'attempts/edgar-population-20261016-143'
    if (fixed.get('schema') != SCHEMA or fixed.get('review_id') != REVIEW_ID
            or type(fixed.get('logical_round')) is not int or fixed['logical_round'] != 16
            or fixed.get('authority') != AUTHORITY or fixed.get('source_axis') != 'R'
            or fixed.get('PROGRAM_AST_unchanged') is not True or fixed.get('C_A_regeneration') is not False
            or fixed.get('original_Review_absent') is not True or fixed.get('original_implement_absent') is not True
            or child.get('axis') != 'R' or child.get('parent') != '37af4ddad70dad464e6a795fd8a4eec9425c283e1c18f583ff0287c8d16eb971'
            or child['R'] != fixed['source'] or child['H'] != fixed['original_parent_H']
            or child['H']['sha256'] != '6d80fa56d0625188f4357d791a725083a6bab75119c0736424516b3dc5681350'
            or child['id'] != digest({a:child[a]['sha256'] for a in ('R','H')})
            or fixed['closure']['sha256'] != '4bf5e329814f8ecfdbcf8e382b333ab80d40bb2a9fec0171cd3a357734848cda'
            or audit.get('status') != 'FAILED_NO_RETRY' or audit.get('original_true_exit') != 1
            or audit.get('owned_generations') != 16 or audit.get('owned_cost_nano_usd') != 626158700
            or audit.get('all_owned_settled') is not True or audit.get('pending_count') != 0
            or audit.get('pending_full_reserved_nano_usd') != 0
            or audit.get('original_failure') != fixed['original_failure'] or audit.get('runtime') != fixed['original_runtime']
            or engine.read(fixed['original_git']).get('commit') != '63b6371bfe9a3c39f99d27c3e0836ef92e5d8dc1'
            or (original_root/'roles/review-01').exists()
            or (original_root/'loop/round-0001-implement.done.json').exists()):
        raise ValueError('Exact143 failed size boundary, settled history and absent CASE/Review required')
    runtime=engine.read(fixed['original_runtime'])
    task=engine.read(engine.read(runtime['forecast_study'])['clean_slate_task'])
    if (runtime['id'] != 'edgar-population-20261016-143'
            or runtime['source_commit'] != '84d723bc875ec2ba171fb3d1e8bab206aeb8d022'
            or task['feedback'] != fixed['original_feedback']):
        raise ValueError('Original143 runtime and feedback must remain original')
    original=message(engine.read(fixed['original_response']));chosen=engine.read(fixed['original_decision'])['decision']
    before=engine.read(fixed['original_source'])['source_text'];after=checked(child['R']).decode()
    parent=checked(fixed['original_parent_R']).decode();proof=engine.read(fixed['validation'])
    if (original['parent_source_sha256'] != fixed['original_parent_R']['sha256']
            or fixed['original_parent_R']['sha256'] != 'c90367b744c83e3c02d9ff6f353a37b2559523893c9087e601aad1754a7f7e42'
            or chosen['parent_pair_sha256'] != child['parent'] or chosen['feedback_sha256'] != digest(task['feedback'])
            or original['decision_sha256'] != digest(scientific(chosen))
            or engine.read(fixed['scientific_decision'])['scientific_decision'] != scientific(chosen)
            or child['method'] != chosen['hypothesis'] or fixed['parent']['id'] != child['parent']
            or any(fixed['parent'][a] != fixed['original_parent_'+a] for a in ('R','H'))
            or _edit_source(parent,original['edits']) != before or normalize(before) != after
            or (len(before.encode()),len(after.encode())) != (67082,62637)
            or any(proof.get(k) is not True for k in ('PROGRAM_AST_unchanged','original_cases_unchanged'))
            or any(proof.get(k) != v for k,v in dict(original_bytes=67082,normalized_bytes=62637,
                removed_UTF8_bytes=4445,limit_bytes=65536,case_count=3,model_calls=0,Native_calls=0,
                ledger_writes=0,host_candidate_execution=False,heldout_read=False).items())
            or proof.get('normalized_source') != child['R'] or proof.get('tests') != fixed['tests']):
        raise ValueError('Exact original edits, original feedback and AST-identical trivia only')
    program(after.encode(),'R')  # Original static bounded-program validator, never run().
    syntax=ast.parse(original['test_text'])
    if len(syntax.body)!=1 or not isinstance(syntax.body[0],ast.Assign): raise ValueError('Original literal CASES only')
    tests=engine.read(fixed['tests'])
    if (tests != ast.literal_eval(syntax.body[0].value) or type(tests) is not list or len(tests)!=3
            or len(checked(fixed['tests']))>32768 or len(original['test_text'].encode())!=2133
            or any(type(c) is not dict or set(c)!={'input','expected'} for c in tests)):
        raise ValueError('Three original full-exact CASES unchanged')
    for key,sha in (('original_controller_context','5c0137d0f01b259e3034644711660548b5c6ef2c2d61b74f67fb1e36f457e5af'),
                    ('original_author_context','27adbb635b4c7ef1a69e7cd40822c4b46867eb2041af1d2ee2975e0a3c6757e4')):
        context=engine.read(fixed[key])
        if (fixed[key]['sha256'] != sha or context.get('authority') != fixed['original_runtime']
                or context.get('source_commit') != runtime['source_commit'] or context.get('pool_version') != fixed['parent']):
            raise ValueError('Historical C/A contexts must retain143 identity')
    for bound in bindings(fixed): checked(bound)
    return fixed


def originals(fixed):
    from earnings_population_source_trivia import originals as original_blobs
    original_blobs(fixed)
