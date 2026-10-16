"""Carry the already audited closed pilot forward, never reopen its authority.

This first continuation deliberately accepts one known completed anchor, not an
arbitrary result supplied by a candidate. Historical hashes were recorded at
the prior source version; this is not a replay claim under changed handlers.
No owner, credential, reservation or candidate execution occurs here.
"""
from copy import deepcopy
from pathlib import Path

import earnings_entry as e
import earnings_completed_replay as completed
import earnings_live_capacity as original
from earnings_feedback import project_feedback
from earnings_open_feedback import project_target_scores
from earnings_research_diagnostics import validate_diagnostics
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine

PRIOR_ID='edgar-open-20261014-04'
PRIOR_ROOT=e.PILOT.parent.parent/'edgar-open-research-20261014'
PINS={
    'result':('attempts/'+PRIOR_ID+'/open-result.json','4ce29279340389ce73b6da16e6e2bd14a430e83ae8dcd864461512731f59dd31'),
    'closure':('attempts/'+PRIOR_ID+'/completed-replay.json','b7f50945997e006473af5bb138f048add38d200778d486c803d0cf6e7ad7b9cb'),
    'audit':('ACTUAL-NEXT-USE-AUDIT-04.json','17c1ba286dc3f1495db4403d286c2de453321fecbde89dd43cce0e5bb6d225cc'),
    'root_audit':('ROOT-FINAL-AUDIT-04.json','5e262418db84c03752909ff2ba7f8c95bce236a7fca9e60877914d29d378fa8d')}


def prior():
    """Verify pinned prior completion and current immutable selected originals."""
    pins={key:{'path':str(PRIOR_ROOT/name),'sha256':token} for key,(name,token) in PINS.items()}
    result,body,audit,root_audit=(engine.read(pins[key]) for key in ('result','closure','audit','root_audit'))
    envelope=engine.read(body['episode'])
    if (envelope['id']!=PRIOR_ID or result['completed_driver']!=pins['closure']
            or result['outcome']!=body['outcome'] or body['sources']!=completed.sources()
            or body['outcome']['status']!='completed' or body['outcome']['completed_rounds']!=2
            or audit.get('blocking_findings')!=[] or audit.get('episode_id')!=PRIOR_ID):
        raise ValueError('Exact previously audited completed anchor required')
    state=completed._native_snapshot(body)
    completed._selected(body,state)
    completed._work(body,envelope,state)
    if state['micro_evolution']['pending'] is not None:
        raise ValueError('A pending historical proposal cannot become a new baseline')
    selected=engine.read(body['selected_version'])
    manifest=selected['manifest'];outcome=body['outcome']['result']
    output=engine.driver._read_pair(Path(envelope['root'])/'loop'/'round-0002-execute.done.json')['output']
    if digest(state['micro_evolution']['active_pair'])!=outcome['pair_sha256']:
        raise ValueError('Historical active selection differs from completed ordinary use')
    if output['pair_sha256']!=outcome['pair_sha256']:
        raise ValueError('Retained execution differs from the reconciled selection')
    terminal=engine.read(body['runtime_terminal'])
    if (terminal.get('status')!='COMPLETED_COMPONENT_CONTEXT' or terminal.get('error_type') is not None
            or terminal.get('retry_allowed') is not False
            or terminal['budget_summary']['blocked'] is not False
            or terminal['budget_summary']['unresolved_reserved_usd']!=0):
        raise ValueError('Historical owner must be closed with no uncertain reservation')
    # Only the exact independently audited selected programs, not its terminal
    # unapplied proposal, may be copied. No historical memory is relabelled new.
    sources={}
    for axis in ('R','H'):
        name=selected['entrypoints'][axis]
        matches=[b for b in body['selected_sources'] if Path(b['path']).name==name
                 and b['sha256']==manifest['components'][axis]['sources'][name]]
        if len(matches)!=1 or len(manifest['components'][axis]['sources'])!=1:
            raise ValueError('One exact verified selected program per axis required')
        engine.read(body['selected_version']);e.checked(matches[0])
        sources[axis]=matches[0]
    observation=project_feedback(engine.read(output['result']),engine.read(output['score']),
        task_id=PRIOR_ID,cik=envelope['cik'])
    old_feedback=outcome['feedback']
    if observation!=old_feedback['observation']:
        raise ValueError('Historical feedback differs from its original scorer result')
    diagnostics=validate_diagnostics(old_feedback['research_diagnostics'],observation)
    company,_=original.task(engine.read(envelope['grant']))
    questions=e.FilingTools(company).files['questions.md']
    feedback={'observation':observation,'baseline_score_out_of_5':old_feedback['baseline_score_out_of_5'],
        'research_diagnostics':diagnostics,
        'target_scores':project_target_scores(engine.read(output['score']),questions)}
    if completed._native_snapshot(body)!=state:
        raise ValueError('Historical selection changed during verification')
    return {'schema':'earnings_verified_program_lineage_v1','prior_episode':body['episode'],
        'provenance':pins,'prior_pair_sha256':outcome['pair_sha256'],'selected_version':body['selected_version'],
        'sources':sources,'protected':{key:deepcopy(manifest[key]) for key in ('K','C','M','runtime')},
        'feedback':feedback,'trace_slots':{f'prior-{key}-{i:02d}':str(Path(envelope['root'])/'roles'/f'{key}-{i:02d}')
            for key in ('forecast',) for i in (1,2)},
        'scope':'Historical exposed Discovery evidence; new task namespace/memory/identity, same selected program bytes. No fresh forecast, new authority or predictive-gain claim.'}


def verify(binding):
    body=engine.read(binding)
    if body!=prior():raise ValueError('Historical lineage drift or fabricated carry-forward')
    return body
