"""Preserve an inspection-only session that exited without its required decision.

A recovery may close the protocol, not start or repeat a scientific trial.
All paid turns and the unaccepted narrative stay in the archive. No prose is
converted into a decision and no provider sample is chosen or discarded.
"""
from pathlib import Path

from controller_activity_log import read_activity_events, verify_activity_log
from market_rsi import digest, file_hash, load_json


def inspection_failure_evidence(session, parent):
    session=Path(session);parent=Path(parent)
    w=session/'workspace';old=parent/'workspace'
    a=load_json(session/'session/assessment.json')
    if (a.get('valid') is not False or not a.get('process_reaped') or a.get('exit_code')!=0
            or a.get('submitted_decision_present') or a.get('terminal_handshake') is not None
            or not a.get('final_message') or not a.get('codex_harness_runtime_unchanged')):
        raise ValueError('exact reaped unsubmitted narrative failure required')
    if (w/'submitted-grid-learning-decision.json').exists() or list((w/'features').iterdir()):
        raise ValueError('recovery cannot discard a decision or feature query')
    prior=load_json(w/'archive.json')['completed_diagnostic']
    if prior['completed_session_id']!=parent.name:
        raise ValueError('unsubmitted session has a different valid parent')
    if 'terminal_protocol_recovery' in load_json(w/'archive.json'):
        raise ValueError('only one protocol closure attempt; never loop on narrative failures')
    fixed=['current-inputs.npz','primary-labels.npz','objective-proposal.json','protocol.json',
           'input-result.json','label-result.json','panel-result.json','data-use-proposal.json']
    if any(file_hash(w/n)!=file_hash(old/n) for n in fixed):
        raise ValueError('unsubmitted session changed scientific inputs or protocol')
    names={p.name for p in (w/'trials').iterdir()}
    if names!={p.name for p in (old/'trials').iterdir()}:
        raise ValueError('unsubmitted session ran or removed a scientific trial')
    for name in names:
        for n in ('claim.json','result.json','predictions.npz'):
            if file_hash(w/'trials'/name/n)!=file_hash(old/'trials'/name/n):
                raise ValueError('unsubmitted session changed original trial artifacts')
    verify_activity_log(w/'learning-activity.jsonl')
    events=read_activity_events(w/'learning-activity.jsonl')
    read_only={'inspect_learning_contract','inspect_learning_library','inspect_learning_trial','search_public_literature'}
    if not events or any(e['tool'] not in read_only or e['status']!='ok' for e in events):
        raise ValueError('only successful read-only inspections may precede protocol recovery')
    preparation=load_json(session/'preparation.json')
    if any(file_hash(session/'source-snapshot'/n)!=h for n,h in preparation['source_hashes'].items()):
        raise ValueError('failed source snapshot changed')
    turns=sorted((session/'session').glob('turn-*'))
    if len(turns)!=a['turns'] or not turns:
        raise ValueError('all metered failure turns must be preserved')
    hashes={}
    for turn in turns:
        for n in ('request.json','response.json','assessment.json'):
            hashes[str((turn/n).resolve())]=file_hash(turn/n)
    jobs={k:v for k,v in a['provider_cost']['jobs'].items() if k.startswith(session.name+'-')}
    if len(jobs)!=len(turns) or any(v['state']!='metered_terminal' for v in jobs.values()):
        raise ValueError('every failure call must have an actual terminal receipt')
    return {'schema':'historical_learning_terminal_protocol_recovery_v1',
        'failed_session_id':session.name,'valid_parent_id':parent.name,
        'assessment_sha256':file_hash(session/'session/assessment.json'),
        'activity_sha256':file_hash(w/'learning-activity.jsonl'),
        'source_preparation_sha256':file_hash(session/'preparation.json'),
        'turn_file_hashes':hashes,
        'metered_usd_by_turn':{k:v['metered_usd'] for k,v in jobs.items()},
        'unaccepted_original_narrative':a['final_message'],
        'actual_inspection_results':[{'tool':e['tool'],'arguments':e['arguments'],'result':e['result']}
            for e in events if e['tool']=='inspect_learning_trial'],
        'new_model_trials':0,'new_feature_profiles':0,'original_trial_ids':sorted(names),
        'max_protocol_closure_continuations':1,
        'allowed_work':'Inspect already-existing artifacts and submit your own select/defer decision through the terminal tool. '
            'No feature profiles or fits are allowed in this closure-only session. No automatic conversion of prior prose.',
        'claim_boundary':'The previous narrative was not a decision and may contain unsupported claims. '
            'Use numeric artifacts and actual tool receipts, not claims about nonexistent APIs. '
            'No hidden data, objective change, budget reset or score retry.'}


def verify_recovery_files(evidence):
    for path,sha in evidence['turn_file_hashes'].items():
        if file_hash(Path(path))!=sha:
            raise ValueError('archived unsubmitted provider turn changed')
    first=Path(next(iter(evidence['turn_file_hashes']))).parent.parent.parent
    if (file_hash(first/'session/assessment.json')!=evidence['assessment_sha256']
            or file_hash(first/'workspace/learning-activity.jsonl')!=evidence['activity_sha256']):
        raise ValueError('archived unsubmitted assessment or activity changed')
