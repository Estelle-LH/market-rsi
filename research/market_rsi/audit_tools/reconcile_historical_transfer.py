"""Reconcile historical payload evidence without downloading or reading prices.

Payload accounting is not disk usage, HTTP-wire traffic, or provider billing.
Early canaries are shown separately; missing transfer logs never imply zero.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller_activity_log import read_activity_events,verify_activity_log
from market_rsi import canonical,digest,file_hash,fresh_json,load_json


def reconcile_ingest(events,selected):
    manifest={i['path']:i for i in selected}
    if len(manifest)!=len(selected):raise ValueError('duplicate selected path')
    acquired={};starts={}
    for event in events:
        kind=event.get('event');path=event.get('path')
        if kind not in {'download_started','file_acquired'}:continue
        if path not in manifest:raise ValueError('transfer outside frozen manifest')
        item=manifest[path]
        if kind=='download_started':
            if path in starts or path in acquired:raise ValueError('duplicate or out-of-order transfer start')
            if event['bytes']!=item['bytes']:raise ValueError('transfer size changed')
            starts[path]=event
        else:
            if path in acquired:raise ValueError('duplicate acquisition receipt')
            if event['sha256']!=item['lfs_sha256']:raise ValueError('acquisition hash changed')
            if event['mode']=='copied_hash_verified_cache':
                if event['new_payload_bytes']!=0 or path in starts:raise ValueError('copy incorrectly counted as download')
            elif event['mode']=='downloaded_public_frozen_object':
                if path not in starts or event['new_payload_bytes']!=item['bytes']:
                    raise ValueError('download lacks exact start/terminal byte receipt')
            else:raise ValueError('unknown acquisition mode')
            acquired[path]=event
    if set(acquired)!=set(manifest):raise ValueError('incomplete acquisitions or unresolved transfer starts')
    return {'selected_files':len(selected),'selected_object_bytes':sum(i['bytes'] for i in selected),
        'recorded_new_payload_bytes':sum(e['new_payload_bytes'] for e in acquired.values()),
        'copy_files':sum(e['mode']=='copied_hash_verified_cache' for e in acquired.values()),
        'download_files':len(starts),'unmatched_starts':0,'duplicate_transfers':0}


def run(artifacts,output):
    if output.exists():raise ValueError('fresh transfer audit required')
    ingest=artifacts/'historical-raw-ingest-20260909-01'
    canary=artifacts/'openmarket-partition-canary-20260909-01'
    sample=artifacts/'openmarket-sample-canary-20260909-01'
    official=artifacts/'polymarket-history-canary-20260909-01/clean-data-report.json'
    evidence=[ingest/'frozen-plan.json',ingest/'completion.json',ingest/'progress.jsonl',
        canary/'frozen-inventory.json',canary/'failure.json',sample/'validated/clean-data-report.json',official]
    evidence += [artifacts/f'openmarket-partition-canary-20260909-0{n}/clean-data-report.json' for n in (3,4)]
    before={str(p):file_hash(p) for p in evidence}
    chain=verify_activity_log(ingest/'progress.jsonl')
    selected=load_json(ingest/'frozen-plan.json')['audit']['selected_files']
    summary=reconcile_ingest(read_activity_events(ingest/'progress.jsonl'),selected)
    completion=load_json(ingest/'completion.json')
    if summary['recorded_new_payload_bytes']!=completion['new_payload_bytes']:
        raise ValueError('completion payload accounting disagrees with ledger')
    for item in selected:
        p=ingest/'raw'/item['path']
        if p.is_symlink() or not p.is_file() or p.stat().st_size!=item['bytes']:
            raise ValueError('manifest file missing or size changed')
    early=load_json(canary/'frozen-inventory.json')['selected']
    early_bytes=sum(i['bytes'] for i in early)
    if load_json(canary/'failure.json')['preserved_evidence']['selected_bytes']!=early_bytes:
        raise ValueError('early failed-canary bytes mismatch')
    for item in early:
        if file_hash(canary/'raw'/item['path'])!=item['lfs_sha256']:
            raise ValueError('early canary object changed')
    for n in (3,4):
        report=load_json(artifacts/f'openmarket-partition-canary-20260909-0{n}/clean-data-report.json')
        if report['raw_acquisition']!={'mode':'reused_hash_verified_canary_bytes','source':str((canary/'raw').resolve())}:
            raise ValueError('later canary lacks explicit reuse provenance')
        if report['selected_files']!=early:raise ValueError('later canary selected different bytes')
    small=load_json(sample/'validated/clean-data-report.json');sample_bytes=0
    for name,t in small['tables'].items():
        p=sample/'raw'/name
        if p.stat().st_size!=t['raw_bytes'] or file_hash(p)!=t['raw_sha256']:
            raise ValueError('early sample object changed')
        sample_bytes+=t['raw_bytes']
    api=load_json(official);api_bytes=sum(r['response_bytes'] for r in api['requests'])
    if api_bytes!=api['scope']['response_bytes']:raise ValueError('official API response sum differs')
    openmarket=summary['recorded_new_payload_bytes']+early_bytes+sample_bytes
    broad=openmarket+api_bytes;cap=5_000_000_000
    if before!={str(p):file_hash(p) for p in evidence}:raise ValueError('transfer evidence changed')
    result={'schema':'historical_payload_accounting_audit_v1','passed':True,'source_hashes':before,
        'ingest_chain':chain,'ingest':summary,'earlier_partition_canary_counted_once_bytes':early_bytes,
        'later_canary_copies_additional_payload_bytes':0,'earlier_sample_counted_once_bytes':sample_bytes,
        'earlier_official_api_recorded_response_bytes':api_bytes,
        'openmarket_workflow_accounted_payload_bytes':openmarket,
        'cross_source_workflow_accounted_payload_bytes':broad,'nominal_cap_bytes':cap,
        'openmarket_only_arithmetic_headroom_NOT_authorization':cap-openmarket,
        'cross_source_arithmetic_headroom_NOT_authorization':cap-broad,
        'new_downloads_admitted':False,'new_network_requests':0,'prices_or_labels_read':False,
        'limits':['Early sample/canary objects are conservatively counted once from retained evidence, not a full HTTP wire ledger.',
            'Official API responses include metadata as well as observations and predate the full-ingest selection.',
            'Request headers, inventory fetches, redirects and unlogged transient transfers are not reconstructed.',
            'The original five-GB scope/start must not be silently redefined. Neither arithmetic balance authorizes downloading.',
            'Stored copies and derived local indices are not additional network payload. Reuse is still allowed.'],
        'auditor_sha256':file_hash(Path(__file__))}
    result['result_sha256']=digest(result);output.mkdir(parents=True,exist_ok=False)
    fresh_json(output/'audit.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifacts',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    r=run(**vars(p.parse_args()))
    print(canonical({k:r[k] for k in ['passed','result_sha256','openmarket_workflow_accounted_payload_bytes',
        'cross_source_workflow_accounted_payload_bytes','new_downloads_admitted']}))
