"""Explain the already-selected crossing, using a fixed 120k-record raw prefix.

This composes the frozen forensic helpers; no source repairs, new data selection,
raw prices/identifiers exported, or model calls. New output, never mutate parent.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

CASE_ORDINAL = 5311264
CASE_HASH = 'f016a2ecde5dcf4811830ac436b7bcba95816f24c5b27a521ba2507461b3545c'
CASE_T = 1787270630696
RAW_CASE_HASHES = {
    116007: '387e05f05d147553cf5ec427d249a01c0361ee79ce93a6d0fefffc47bdbddfd4',
    116008: 'af00dd4f2bd1addc165bb82ac410cfdfc550eea812c7c9bb739a76f8f750c9d5',
    116009: 'c4efa119b3561ecf1699275a355a5ef6fd91d561d3e3d6ff3c84bde9866d8e45',
}


def exact_csv_row():
    before = checked_file(CSV_PATH, CSV_HASH)
    target = None
    with gzip.open(CSV_PATH, 'rb') as f:
        lines = bounded_lines(f, 4*1024**3)
        head = next(csv.reader([next(lines).decode('utf-8-sig')]))
        if set(head) != HEADER: raise ValueError('CSV header changed')
        for ordinal, line in enumerate(lines, 1):
            if ordinal == CASE_ORDINAL:
                target = dict(zip(head, next(csv.reader([line.decode()])))); break
    unchanged(CSV_PATH, before)
    if target is None or digest(target) != CASE_HASH or int(target['ts_ms']) != CASE_T:
        raise ValueError('exact parent quote changed')
    check_time(target['ts_ms'])
    return target


def trace_window(records, token):
    book = None; trace = []; snapshot_checks = []; source_pairs = []; case_indices = []
    for ordinal, record, raw_sha in records:
        messages = record['m'] if isinstance(record['m'], list) else [record['m']]
        for m in messages:
            if record.get('src') == 'rest' or m.get('event_type') == 'book':
                fresh = {s: {num(x['price']): num(x['size']) for x in m.get(s, []) if num(x['size']) > 0}
                         for s in ('bids', 'asks')}
                if book is not None and 116009 < ordinal < 116050:
                    snapshot_checks.append({'ordinal': ordinal, 'record_sha256': raw_sha,
                        'timestamp_ms': record['t'], 'full_price_size_maps_equal_before_reset': book == fresh,
                        'status': status(max(fresh['bids'], default=None), min(fresh['asks'], default=None))})
                book = fresh; continue
            if m.get('event_type') != 'price_change': continue
            for c in m.get('price_changes', []):
                if c.get('asset_id') != token: raise ValueError('unfiltered token')
                if book is None: continue
                side = 'bids' if c['side'] == 'BUY' else 'asks'
                px, size = num(c['price']), num(c['size'])
                old_best = (max if side == 'bids' else min)(book[side], default=None)
                present = px in book[side]
                if size == 0: book[side].pop(px, None)
                else: book[side][px] = size
                if ordinal not in RAW_CASE_HASHES: continue
                if raw_sha != RAW_CASE_HASHES[ordinal]: raise ValueError('raw case record changed')
                if record['t'] != CASE_T: raise ValueError('case wrapper clock changed')
                pair = (num(c['best_bid']), num(c['best_ask']))
                source_pairs.append(pair); case_indices.append(ordinal)
                bid, ask = max(book['bids'], default=None), min(book['asks'], default=None)
                trace.append({'ordinal': ordinal, 'record_sha256': raw_sha,
                    'wrapper_timestamp_ms': record['t'], 'source_timestamp_ms': int(m['timestamp']),
                    'changed_side': side, 'operation': 'remove' if size == 0 else 'set_absolute_size',
                    'level_previously_present': present, 'changed_level_was_best_on_side': px == old_best,
                    'changed_level_is_best_on_side_now': px == ((max if side == 'bids' else min)(book[side], default=None)),
                    'replay_bid_matches_source_bid': bid == pair[0], 'replay_ask_matches_source_ask': ask == pair[1],
                    'replay_status': status(bid, ask), 'source_bbo_status': status(*pair),
                    'replay_spread_probability_bps': str((ask-bid)*10000) if bid is not None and ask is not None else None,
                    'source_spread_probability_bps': str((pair[1]-pair[0])*10000)})
    if case_indices != list(RAW_CASE_HASHES): raise ValueError('missing/repeated/out-of-order case entries')
    return {'trace': trace, 'source_bbo_identical_across_three_records': len(set(source_pairs)) == 1,
            'source_timestamps_identical': len({s['source_timestamp_ms'] for s in trace}) == 1,
            'snapshot_checks': snapshot_checks,
            'atomic_exchange_transaction_proven': False, 'receive_clock_proven': False,
            'population_frequency_proven': False}


def remote_window():
    resource.setrlimit(resource.RLIMIT_AS, (512*1024**2, 512*1024**2))
    target = exact_csv_row()
    before = checked_file(RAW_PATH, RAW_HASH)
    p = subprocess.Popen(['zstd', '-dc', '--', str(RAW_PATH)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    selected = []; prefix = hashlib.sha256(); n = 0
    try:
        for n, line in enumerate(bounded_lines(p.stdout, 128*1024**2), 1):
            prefix.update(line); r = json.loads(line)
            chosen = target_record(r, target['outcome'], target['market'])
            if chosen is not None: selected.append((n, chosen, hashlib.sha256(line).hexdigest()))
            if n == 120000: break
    finally:
        p.stdout.close()
        if p.poll() is None: p.terminate()
        try: code = p.wait(timeout=5)
        except subprocess.TimeoutExpired: p.kill(); code = p.wait(timeout=5)
    if n != 120000: raise ValueError('prefix incomplete')
    unchanged(RAW_PATH, before)
    return {'schema': 'capture_cross_window_v1', 'csv_case_sha256': CASE_HASH,
        'raw_sha256': RAW_HASH, 'prefix_sha256': prefix.hexdigest(), 'prefix_records': n,
        'decoder_exit_code': code, 'decoder_reaped': True, 'stop_reason': 'fixed_prefix',
        'analysis': trace_window(selected, target['outcome']), 'raw_frames_exported': 0,
        'identifiers_exported': 0, 'source_mutated': False, 'fits': 0, 'source_admitted': False}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--remote', action='store_true'); ap.add_argument('--output', type=Path)
    a = ap.parse_args()
    if a.remote:
        try: print(json.dumps(remote_window(), sort_keys=True))
        except Exception as error:
            print(json.dumps({'failure_type': type(error).__name__})); sys.exit(1)
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from market_rsi import fresh_json, load_json, file_hash
        if not a.output: ap.error('--output required')
        parent = Path(__file__).resolve().parents[1]/'artifacts/capture-cross-forensic-20260911-01/report.json'
        if file_hash(parent) != '2a22a6c2ba2040303a8426c1f4b824a6c575456733601ff123ddac7f19f16ff0':
            raise ValueError('parent changed')
        helper = Path(__file__).with_name('capture_cross_forensic.py')
        if file_hash(helper) != '97d9c13c5aa5d6f118b562f73a4ff3db2c93cffb3af18377199873fb9c4319f5':
            raise ValueError('frozen forensic helper changed')
        source = (helper.read_text().split("if __name__ == '__main__':")[0]+'\n'+Path(__file__).read_text()).encode()
        a.output.mkdir(parents=True, exist_ok=False)
        fresh_json(a.output/'claim.json', {'reader_sha256': hashlib.sha256(source).hexdigest(),
            'parent_report_sha256': file_hash(parent), 'case_sha256': CASE_HASH,
            'max_records': 120000, 'max_decoded_bytes': 128*1024**2, 'remote_wall_seconds': 120})
        try:
            response = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                'root@173.255.231.4', 'nice -n 10 timeout --kill-after=10s 120s python3 -u - --remote'],
                input=source, capture_output=True, timeout=140)
            if response.returncode or len(response.stdout) > 100000: raise ValueError('remote trace failed')
            value = json.loads(response.stdout)
            value['claim_sha256'] = file_hash(a.output/'claim.json')
            # Same canonical digest as the parent forensic helper.
            value['result_sha256'] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            fresh_json(a.output/'report.json', value); print(json.dumps(value))
        except BaseException as error:
            fresh_json(a.output/'failure.json', {'failure_type': type(error).__name__, 'automatic_retry': False})
            raise
