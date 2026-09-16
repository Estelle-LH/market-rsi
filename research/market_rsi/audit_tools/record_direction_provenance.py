"""Snapshot two small pinned PUBLIC code files, not new historical observations."""
import argparse
import hashlib
from pathlib import Path
import sys
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from historical_direction_fields import PUBLISHER_COMMIT, direction_contract
from market_rsi import canonical, digest, file_hash, fresh_json, load_json


REMOTE = ('crates/exchange-binance/src/config.rs', 'crates/exchange-binance/src/tasks.rs')
LOCAL = ('crates/recorder/src/normalize.rs', 'crates/recorder/src/ingest.rs')
MAX_SOURCE_BYTES = 65536


def run(prior, fields, output):
    old=load_json(prior/'source-manifest.json'); field_audit=load_json(fields/'audit.json')
    if old['source_commit'] != PUBLISHER_COMMIT:
        raise ValueError('exact pinned publisher source required')
    if field_audit['result_sha256'] != digest({k:v for k,v in field_audit.items() if k!='result_sha256'}):
        raise ValueError('field audit changed')
    output.mkdir(parents=True, exist_ok=False)
    files=[]; texts={}
    for name in LOCAL:
        entry=next(f for f in old['files'] if f['path']==name)
        if file_hash(prior/name) != entry['sha256']:raise ValueError('prior publisher source changed')
        texts[name]=(prior/name).read_text()
        files.append({**entry, 'local_path':str((prior/name).resolve()), 'reused':True})
    for name in REMOTE:
        url=f'https://raw.githubusercontent.com/gregyoung14/openmarket/{PUBLISHER_COMMIT}/{name}'
        with urlopen(url,timeout=25) as response:
            if response.geturl()!=url:raise ValueError('unexpected publisher redirect')
            payload=response.read(MAX_SOURCE_BYTES+1)
        if len(payload)>MAX_SOURCE_BYTES:raise ValueError('public source-code byte cap exceeded')
        texts[name]=payload.decode('utf-8')
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(payload)
        files.append({'path':name,'url':url,'bytes':len(payload),
                      'sha256':hashlib.sha256(payload).hexdigest(),'local_path':str(path.resolve()),'reused':False})
    tokens={REMOTE[0]:['btcusdt@aggTrade'],REMOTE[1]:['data["a"].as_i64()',
        'data["m"].as_bool().unwrap_or(false)', 'let quote_volume = price * quantity;',
        '(trade_id, trade_time, price, quantity, quote_volume, is_buyer_maker, received_at)'],
        LOCAL[0]:['return ("UP".to_string(), mapping.market_slug.clone());',
                  'return ("DOWN".to_string(), mapping.market_slug.clone());'],
        LOCAL[1]:['map.up_token_id = Some(market.token_ids[0].clone());',
                  'map.down_token_id = Some(market.token_ids[1].clone());']}
    # Exact source evidence locations are recorded; no publisher code is executed.
    locations={}
    for name,needles in tokens.items():
        locations[name]={}
        for needle in needles:
            hits=[i+1 for i,line in enumerate(texts[name].splitlines()) if needle in line]
            if not hits:raise ValueError('pinned source evidence not found: '+needle)
            locations[name][needle]=hits
    value={'schema':'reported_direction_provenance_v1','complete':True,
        'publisher_commit':PUBLISHER_COMMIT,'files':files,'evidence_lines':locations,
        'prior_source_manifest_sha256':file_hash(prior/'source-manifest.json'),
        'raw_field_audit_sha256':file_hash(fields/'audit.json'),
        'direction_contract':direction_contract(),
        'official_semantic_reference':'https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams',
        'findings':['Pinned collector consumes BTCUSDT aggregate trades, retaining a as trade_id and m as an integer maker flag.',
            'Pinned collector defaults absent/nonboolean m to false, so stored 0 does not prove explicit upstream false.',
            'Pinned collector computes quote_volume as price * quantity and inserts the fields unchanged.',
            'Publisher token order maps to UP/DOWN; this is not independently verified contract outcome semantics.'],
        'historical_deployment_verified':False,'raw_upstream_envelopes_verified':False,
        'new_public_source_code_bytes':sum(f['bytes'] for f in files if not f['reused']),
        'new_historical_observation_bytes':0,'new_paid_calls':0,
        'new_dev_or_test_opened':False,'raw_data_modified':False}
    value['result_sha256']=digest(value);fresh_json(output/'provenance.json',value)
    return value


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('prior','fields','output'):p.add_argument('--'+name,type=Path,required=True)
    print(canonical(run(**vars(p.parse_args()))))
