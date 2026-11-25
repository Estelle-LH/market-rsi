"""Finite +100 execution-source bridge for the last two Round15 companies.

Authenticate saved accepted137 and original10222 execution from private Git;
never rerun an old scientific gate, regenerate code, or treat finance as H gain.
"""
from pathlib import Path
import hashlib
import subprocess

from earnings_entry import checked
from earnings_population_additional_budget import ROOT,HUMAN,PLAN,IMPLEMENTATIONS
from supervisor_harness import capacity_feedback_engine as engine

SOURCE='10222cacae90c90bbdf526a327ccc0aaaa0aaadf'
CANDIDATE='37af4ddad70dad464e6a795fd8a4eec9425c283e1c18f583ff0287c8d16eb971'
OLD=dict(path=str(ROOT/'TRAIN25-CLEAN138-REBIND-FROZEN-CANDIDATE.json'),
    sha256='7806c34867d771c05b6441a989e635f91bec2f8f3f2d86235cba9edd4fe6f85d')
ARCHIVE138=dict(path=str(ROOT/'TRAIN25-CLEAN138-CLOSED-GIT.json'),
    sha256='9cabb91d6b39374a2e5cac954d73a524c0aba138191139cd076f076849fe5005')
NAME='TRAIN25-CLEAN142-ADDITIONAL100-FROZEN-CANDIDATE.json'
RECEIPT='TRAIN25-CLEAN142-ADDITIONAL100-EXECUTION-REBIND.json'
PRODUCTION=set(IMPLEMENTATIONS)|{'tools/earnings_population_additional_execution.py',
    'tools/earnings_population_clean_slate.py',PLAN}
TESTS={'tests/test_earnings_population_additional_budget.py',
    'tests/test_earnings_population_additional_execution.py'}


def selected(binding):
    return type(binding) is dict and binding.get('path')==str(ROOT/NAME)


def inputs(binding,descriptor):
    import earnings_population_clean_slate as clean
    return [binding,descriptor['execution_rebind'],HUMAN,OLD,ARCHIVE138,
        clean.NATIVE137_CLOSURE,clean.NATIVE137_ARCHIVE]


def _saved(archive,bound,*,binary=False):
    import earnings_population_budget as budget
    path=Path(bound['path'])
    if not path.is_relative_to(ROOT):raise ValueError('Owned saved evidence only')
    alias='original/'+str(path.relative_to(ROOT))
    if archive['artifacts'].get(alias)!=bound:raise ValueError('Original private archive binding missing')
    raw=budget._git(archive['commit'],alias)
    if hashlib.sha256(raw).hexdigest()!=bound['sha256'] or checked(bound)!=raw:
        raise ValueError('Original private Git blob differs')
    return raw if binary else engine.read(bound)


def verify(binding,descriptor):
    import earnings_population_budget as budget
    import earnings_population_clean_slate as clean
    from supervisor_harness.feedback_linked_loop import _read_pair
    if not selected(binding) or descriptor.get('execution_rebind',{}).get('path')!=str(ROOT/RECEIPT):
        raise ValueError('Only finite last-two Round15 additional100 execution bridge is admitted')
    archive138=engine.read(ARCHIVE138);archive137=engine.read(clean.NATIVE137_ARCHIVE)
    if (archive138.get('commit')!='6d9dbef8728f7e23a5cbdca3912c651835e619ce'
            or archive137.get('commit')!='eb4a765b62aedc7e2ef0fc4d9ececf65867351a6'
            or archive138.get('every_blob_readback_verified') is not True
            or archive137.get('every_blob_readback_verified') is not True):
        raise ValueError('Original137/138 private archives required')
    old=_saved(archive138,OLD);old_receipt=_saved(archive138,old['execution_rebind'])
    closure=_saved(archive137,clean.NATIVE137_CLOSURE)
    original=_saved(archive137,closure['frozen']);runtime=_saved(archive137,closure['runtime'])
    result=_saved(archive137,closure['terminal']);receipt=engine.read(descriptor['execution_rebind'])
    if (closure.get('status')!='VERIFIED_ACCEPTED_PROPOSAL' or closure.get('original_true_exit')!=0
            or closure.get('original_accepted_gate_passed') is not False
            or closure.get('corrected_native_metadata_gate_passed') is not True
            or closure.get('all_owned_settled') is not True or closure.get('pending_count')!=0
            or closure.get('pending_full_reserved_nano_usd')!=0
            or original['candidate']!=closure['candidate'] or original['candidate']['id']!=CANDIDATE
            or original['source_commit']!=runtime['source_commit']
            or runtime['source_commit']!='772e5a6746513666902c52f64924476196ee8c7b'
            or result.get('status')!='PROPOSAL_REVIEWED_ACCEPTED' or len(result.get('proposal_stages',[]))!=4
            or old_receipt.get('original_descriptor')!=closure['frozen']
            or old_receipt.get('corrected_closure')!=clean.NATIVE137_CLOSURE
            or old_receipt.get('archive')!=clean.NATIVE137_ARCHIVE
            or old_receipt.get('new_source_commit')!=SOURCE
            or old!=dict(original,source_commit=SOURCE,execution_rebind=old['execution_rebind'])):
        raise ValueError('Authentic accepted137/finite138 scientific identity differs')
    for bound in (closure['closure_correction'],closure['original_failed_closure'],*result['proposal_stages']):
        _saved(archive137,bound,binary=True)
    stages=[_read_pair(Path(b['path'])) for b in result['proposal_stages']]
    if stages[2]['output']['candidate']!=original['candidate'] or stages[3]['output'].get('accepted_for_exploration') is not True:
        raise ValueError('Genuine original Author/Review code differs')
    previous_sources=old_receipt['sources']
    if (set(previous_sources)!=set(runtime['sources']) or
            [k for k in previous_sources if previous_sources[k]!=runtime['sources'][k]]!=['tools/earnings_population_clean_slate.py']):
        raise ValueError('Original138 source bridge scope differs')
    current=receipt.get('sources',{});commit=receipt.get('new_source_commit')
    if (receipt.get('schema')!='edgar25_additional100_round15_execution_rebind_v1'
            or receipt.get('authority')!=HUMAN or receipt.get('original_descriptor')!=OLD
            or receipt.get('original_source_commit')!=SOURCE
            or descriptor!=dict(old,source_commit=commit,execution_rebind=descriptor['execution_rebind'])
            or type(commit) is not str or len(commit)!=40
            or set(current)!=set(previous_sources)|{PLAN,'tools/earnings_population_additional_budget.py',
                'tools/earnings_population_additional_execution.py'}
            or {str(Path(current[k]['path']).relative_to(budget.REPO)) for k in current
                if k not in previous_sources or current[k]!=previous_sources[k]}!=PRODUCTION):
        raise ValueError('Only exact additional100 financial/source bridge changes are admitted')
    changed=subprocess.run(['git','diff','--name-only',SOURCE,commit],cwd=budget.REPO,
        check=True,capture_output=True,text=True).stdout.splitlines()
    if set(changed)!=PRODUCTION|TESTS:raise ValueError('Financial bridge Git checkpoint scope exceeded')
    for name,bound in current.items():
        if name in previous_sources and bound['path']!=previous_sources[name]['path']:
            raise ValueError('Original source path changed')
        raw=checked(bound)
        relative=str(Path(bound['path']).relative_to(budget.REPO))
        if budget._git(commit,relative)!=raw:raise ValueError('Committed financial bridge source differs')
    for axis in ('R','H'):checked(original['candidate'][axis])
    checked(HUMAN)
    return dict(candidate=original['candidate'],runtime=runtime,task=dict(round2_origin=original['parent_basis']))
