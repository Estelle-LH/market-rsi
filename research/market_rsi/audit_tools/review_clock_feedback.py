"""Bind the completed continuation and distinguish executable scope from prose.

No raw read, request activation, plan rewriting, dispatch or source admission.
"""
import argparse,json
from pathlib import Path,PurePosixPath
from market_rsi import digest,file_hash,load_json,fresh_json
from data_scientist_harness.store import Store
from data_scientist_harness.source_study import current
from causal_event_samples import SampleKernel
from prepare_temporal_feedback import checked_result
from source_inventory_context import INVENTORY,SHA

ROOT=Path(__file__).resolve().parents[1]
WORKSPACE=ROOT/'artifacts/clock-feedback-controller-20260913-01'
MANIFEST='72f9bbdfed56b606f0ee71a87505693dcf1d3b4aa2e228e1b7d901243461dbae'
PROPOSAL='d54e550e13c5a483fec4450ae5ad4f91ef91e0b1c11832f4968b0222210f1500'
AUDIT=ROOT/'artifacts/clock-feedback-controller-audit-20260913-01/audit.json'
AUDIT_SHA='0a9248f13c6d160f2b1e5cf7ada762db205303c6fabda197492de285dade7e22'


def exact_object(request,inventory):
    if len(request['exact_objects'])!=1:raise ValueError('one exact object required')
    o=request['exact_objects'][0]
    if o['host']!=inventory['host'] or o['source_root']!=inventory['source_root']:
        raise ValueError('host/root differs from authorized inventory')
    name=o['relative_path']
    if PurePosixPath(name).name!=name or name in ('.','..'):raise ValueError('relative filename only')
    found=[x for x in inventory['files'] if x['filename']==name]
    if len(found)!=1 or found[0]['compressed_bytes']!=o['advertised_bytes'] or found[0]['date']!=o['date']:
        raise ValueError('exact inventory match required')
    if (type(request['max_input_bytes']) is not int or request['max_input_bytes']!=o['advertised_bytes']
            or not 0<request['max_decoded_bytes']<=2147483648 or not 0<request['wall_seconds']<=600
            or not 0<request['memory_bytes']<=1073741824):raise ValueError('resource request outside ceiling')
    return {**o,'path':str(PurePosixPath(o['source_root'])/name),'current_remote_availability_verified':False}


def closure_example(contract):
    h=contract['horizon_ms']
    rows=[{'key':(i,0,0),'entity':'synthetic','clock_domain':'synthetic','source_kind':'synthetic',
        'time_ms':t,'valid':True,'value':v} for i,(t,v) in enumerate(((0,.2),(h,.3),(2*h,.4)))]
    k=SampleKernel(rows,entity='synthetic',clock_domain='synthetic',clock_field=contract['clock'],
        allowed_kinds=['synthetic'],max_rows=3)
    label=k.label_at(1,contract,same_utc_day=True)
    assert label['available'] is False and label['reason']=='unbounded_tail'
    return {'schema':'strict_closure_counterexample_v1','synthetic_only':True,'decision_ms':h,
        'target_ms':2*h,'last_observation_ms':2*h,'target_extends_past_last_observation':False,
        'typed_kernel_label':label,'meaning':'A target not beyond the last timestamp is insufficient. '
            'An exactly-on-target final record has no strictly later closing observation. '
            'Date cutoff alone also cannot create that missing observation.'}


def review():
    store=Store(WORKSPACE,MANIFEST)
    audited=checked_result(AUDIT,AUDIT_SHA)
    if (not audited['controller_valid'] or not audited['process_reaped'] or audited['fits_completed']!=0
            or audited['assessment_sha256']!=file_hash(WORKSPACE/'session/assessment.json')
            or current(store)!={'path':str(WORKSPACE/'source-study-proposal.json'),'sha256':PROPOSAL}):
        raise ValueError('completed first proposal required')
    record=load_json(WORKSPACE/'records/0008.json')
    if record['tool']!='request_capability' or record['status']!='ok' or record['result']['activated'] is not False:
        raise ValueError('exact unactivated capability required')
    request=json.loads(record['arguments']['verification_needed'])
    if file_hash(INVENTORY)!=SHA:raise ValueError('inventory changed')
    obj=exact_object(request,load_json(INVENTORY))
    contract=load_json(WORKSPACE/'source-study-proposal.json')['typed_temporal_contract']['contract']
    return {'schema':'clock_feedback_independent_review_v1','manifest_sha256':MANIFEST,
        'session_audit_result_sha256':AUDIT_SHA,'proposal_sha256':PROPOSAL,
        'request_record_sha256':file_hash(WORKSPACE/'records/0008.json'),'request_json_valid':True,
        'exact_inventory_object':obj,'resource_envelope_matches_prior_ceiling':True,
        'controller_choice':'WS book+price_change on source_ms; rest_snapshot excluded; not reviewer-selected',
        'closure_counterexample':closure_example(contract),
        'manual_semantic_review_not_an_automatic_proof':[
            'No baseline-registration waiver was supplied by the runner. The proposal claims one; it has no authority.',
            'New ws_shot_gap relies on unspecified slots and at/near coverage; no width, tolerance or deterministic predicate is defined.',
            'Check tails use a September9 date cutoff in prose, whereas the typed probe requires a strictly later observed record; request tail prose is incomplete on equality.',
            'Feature window coverage/minimum-observation terms still do not specify a complete executable policy. Prototype semantics were not automatically adopted.',
            'book snapshots in the delivered official example have bids/asks rather than direct best_bid/best_ask fields. A handling rule is needed; never silently derive a different input.',
            'The existing raw diagnostic did not materialize labels, and the new kernel is not a raw-source adapter. Calling this full operation already implemented is unsupported.',
            'The proposal marks changed_layer=features but explicitly changes message-kind population. Do not attribute a future score difference to feature improvement.',
            'Original clock/heartbeat provenance remains unavailable. Another price scan cannot close those pre-fit gates.'
        ],'request_activated':False,'raw_rows_read':0,'provider_calls':0,'fits':0,'source_admitted':False,
        'next_engineering':'Require structured sample rules (clock/kinds/quote fields/window/closure/maturity/gaps) before any raw label operation; '
            'let the controller fill them, validate with tests, and preserve this original failed-to-admit proposal unchanged.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=review();r['review_source_sha256']=file_hash(__file__)
    r['result_sha256']=digest(r);a.output.parent.mkdir(parents=True,exist_ok=True);fresh_json(a.output,r)
    print({k:r[k] for k in ('result_sha256','request_json_valid','request_activated','raw_rows_read','provider_calls','fits')})
