"""Trace the first crossed CSV quote on one already-open diagnostic day.

Read-only on Linode: no API/model calls, source modifications or raw exports.
Selection by failure is appropriate for debugging, NOT population inference.
"""
import argparse
import ast
from collections import Counter, deque
import csv
from datetime import datetime, timezone
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import resource
import selectors
import subprocess
import sys
import time
from types import SimpleNamespace

DAY = '2026-08-21'
CSV_PATH = Path('/opt/d10/research/2026-08-21/topofbook_2026-08-21.csv.gz')
CSV_HASH = '45c0fbe9de206fce28dd58d7ae37789dfa488f2a1596f799464af1e87af5e050'
RAW_PATH = Path('/opt/d10/raw/data/polymarket/polymarket-20260821T00.jsonl.zst')
RAW_HASH = '27621845de8cc31ca2055235b2a4b69e11a0c6116f3d316f3eda84e647bb4255'
ETL_HASH = '584c7682d9d6ed331bc192da31e75890b7fc4158f4082137f2e2c028b6b1bf8b'
MAX_LINE = 1024 * 1024
MAX_CSV_ROWS = 13_000_000
MAX_RAW_ROWS = 12_000_000
MAX_RETAINED = 200_000
HEADER = {'ts_utc', 'ts_ms', 'venue', 'market', 'outcome', 'bid', 'bid_size',
          'ask', 'ask_size', 'mid', 'spread'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()


def checked_file(path, expected):
    if path.is_symlink() or not path.is_file(): raise ValueError('exact source missing')
    st = path.stat()
    if file_hash(path) != expected: raise ValueError('source hash changed')
    return st


def unchanged(path, before):
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError('source changed during read')


def check_time(t):
    if datetime.fromtimestamp(int(t) / 1000, timezone.utc).date().isoformat() != DAY:
        raise ValueError('outside exact diagnostic date')


def num(v):
    d = Decimal(str(v))
    if not d.is_finite(): raise ValueError('nonfinite quote')
    return d


def status(bid, ask):
    if bid is None or ask is None: return 'one_sided'
    return 'crossed' if num(bid) > num(ask) else ('locked' if num(bid) == num(ask) else 'uncrossed')


def public_quote(row):
    return {'timestamp_ms': int(row['ts_ms']), 'row_sha256': digest(row),
            'status': status(row['bid'], row['ask']),
            'spread_probability_bps': str((num(row['ask']) - num(row['bid'])) * 10000)}


def bounded_lines(stream, byte_limit):
    consumed = 0
    while True:
        b = stream.readline(MAX_LINE + 1)
        if not b: return
        consumed += len(b)
        if len(b) > MAX_LINE or consumed > byte_limit: raise ValueError('decoded byte/line bound')
        yield b


def locate_csv(path):
    before = checked_file(path, CSV_HASH)
    target = None; neighbors = []; previous = {}; counts = Counter()
    with gzip.open(path, 'rb') as f:
        lines = (line.decode('utf-8-sig') for line in bounded_lines(f, 4 * 1024**3))
        reader = csv.DictReader(lines)
        if set(reader.fieldnames or []) != HEADER: raise ValueError('CSV schema changed')
        for ordinal, row in enumerate(reader, 1):
            if ordinal > MAX_CSV_ROWS: raise ValueError('CSV row bound')
            counts['csv_rows_scanned'] += 1
            if row['venue'] != 'polymarket': continue
            check_time(row['ts_ms']); counts['polymarket_rows_scanned'] += 1
            key = (row['market'], row['outcome'])
            if not all(key): raise ValueError('CSV identity missing')
            if target is None:
                if status(row['bid'], row['ask']) == 'crossed':
                    target = {'row': row, 'ordinal': ordinal}
                    if key in previous: neighbors.append(previous[key])
                    neighbors.append({'ordinal': ordinal, **public_quote(row)})
                else:
                    if len(previous) > 100_000: raise ValueError('entity bound')
                    previous[key] = {'ordinal': ordinal, **public_quote(row)}
            elif key == (target['row']['market'], target['row']['outcome']):
                neighbors.append({'ordinal': ordinal, **public_quote(row)})
                if len(neighbors) >= 8: break
    unchanged(path, before)
    if target is None: raise ValueError('no crossed quote in bounded source')
    # First-hour source and identity were fixed before observation. Do not guess a different file.
    t = int(target['row']['ts_ms'])
    if datetime.fromtimestamp(t/1000, timezone.utc).hour != 0:
        raise ValueError('first crossed quote outside fixed first-hour source')
    return target, {'csv_sha256': CSV_HASH, 'csv_bytes': before.st_size,
                   'case': {'ordinal': target['ordinal'], **public_quote(target['row'])},
                   'same_entity_neighbor_quotes': neighbors, 'counts': dict(counts),
                   'selection': 'first crossed Polymarket CSV row in file order, diagnostic only'}


def target_record(record, token, market):
    """Filter by exact token without merging complementary outcomes or reordering."""
    check_time(record['t'])
    messages = record['m'] if isinstance(record['m'], list) else [record['m']]
    selected = []
    for m in messages:
        if not isinstance(m, dict): raise ValueError('invalid message')
        if m.get('event_type') == 'price_change':
            changes = [c for c in m.get('price_changes', []) if c.get('asset_id') == token]
            if changes:
                if m.get('market') != market: raise ValueError('token-market disagreement')
                selected.append({**m, 'price_changes': changes})
        elif m.get('asset_id') == token:
            if m.get('market') not in (None, market): raise ValueError('token-market disagreement')
            selected.append(m)
    if not selected: return None
    out = {**record, 'm': selected[0] if isinstance(record['m'], dict) else selected}
    return out


def read_target(target, progress):
    before = checked_file(RAW_PATH, RAW_HASH)
    token, market = target['row']['outcome'], target['row']['market']
    proc = subprocess.Popen(['zstd', '-dc', '--', str(RAW_PATH)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    retained = []; counts = Counter(); content = hashlib.sha256(); eof = False
    try:
        for ordinal, line in enumerate(bounded_lines(proc.stdout, 8 * 1024**3), 1):
            if ordinal > MAX_RAW_ROWS: raise ValueError('raw record bound')
            content.update(line); counts['raw_records_scanned'] += 1
            r = json.loads(line)
            chosen = target_record(r, token, market)
            if chosen is not None:
                if len(retained) >= MAX_RETAINED: raise ValueError('retained token bound')
                retained.append({'ordinal': ordinal, 'raw_record_sha256': hashlib.sha256(line).hexdigest(), 'record': chosen})
            if ordinal % 500_000 == 0:
                progress({'stage': 'raw_progress', 'scanned': ordinal, 'target_records': len(retained)})
        eof = True
    finally:
        proc.stdout.close()
        if not eof and proc.poll() is None: proc.terminate()
        try: code = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill(); code = proc.wait(timeout=5)
    if code != 0: raise ValueError('raw decoder incomplete')
    unchanged(RAW_PATH, before)
    return retained, {'raw_sha256': RAW_HASH, 'raw_bytes': before.st_size,
                     'decoded_sha256': content.hexdigest(), 'counts': dict(counts),
                     'target_records': len(retained), 'full_fixed_hour_decoded': eof,
                     'decoder_exit_code': code, 'decoder_reaped': True}


def legacy_rows(records, source):
    if hashlib.sha256(source).hexdigest() != ETL_HASH: raise ValueError('ETL source changed')
    names = {'iso', 'emit_tob', 'write_depth', 'run_polymarket'}
    body = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in names]
    if len(body) != 4: raise ValueError('ETL functions changed')
    ns = {'datetime': datetime, 'timezone': timezone, 'glob': SimpleNamespace(glob=lambda _: ['fixed']),
          'rows': lambda _: iter(records), 'TOB_HEADER': [], 'TRADE_HEADER': [], 'DEPTH_HEADER': []}
    exec(compile(ast.Module(body=body, type_ignores=[]), '<reviewed-etl>', 'exec'), ns)
    result = []
    class Writer:
        def __init__(self, name): self.name = name
        def writerow(self, row):
            if self.name == 'topofbook':
                if len(result) >= MAX_RETAINED: raise ValueError('legacy output bound')
                result.append(row)
    out = SimpleNamespace(csv=lambda name, _: Writer(name))
    ns['run_polymarket']('/unused', DAY, out, 60, {}, set())
    return result


def replay(records, snapshots):
    """One token; inspect complete messages and each contained update separately."""
    book = None; states = []; before_snapshot = []; counts = Counter()
    def emit(meta, r, kind, c=None):
        bid = max(book['bids'], default=None) if book else None
        ask = min(book['asks'], default=None) if book else None
        item = {'ordinal': meta['ordinal'], 'record_sha256': meta['raw_record_sha256'],
                'timestamp_ms': int(r['t']), 'kind': kind,
                'status': 'unanchored' if book is None else status(bid, ask),
                'bid': bid, 'ask': ask}
        if c is not None and 'best_bid' in c and 'best_ask' in c:
            item.update(source_bbo_status=status(c['best_bid'], c['best_ask']),
                        source_bid=num(c['best_bid']), source_ask=num(c['best_ask']),
                        replay_matches_source_bbo=(bid == num(c['best_bid']) and ask == num(c['best_ask'])))
        states.append(item)
    for meta in records:
        r = meta['record']; messages = r['m'] if isinstance(r['m'], list) else [r['m']]
        for m in messages:
            is_snapshot = r.get('src') == 'rest' or m.get('event_type') == 'book'
            if is_snapshot:
                counts['rest_snapshot' if r.get('src') == 'rest' else 'ws_snapshot'] += 1
                if r.get('src') != 'rest' and not snapshots: continue
                fresh = {s: {num(x['price']): num(x['size']) for x in m.get(s, []) if num(x['size']) > 0}
                         for s in ('bids', 'asks')}
                if book is not None:
                    before_snapshot.append({'ordinal': meta['ordinal'], 'timestamp_ms': int(r['t']),
                        'old_status': status(max(book['bids'], default=None), min(book['asks'], default=None)),
                        'new_status': status(max(fresh['bids'], default=None), min(fresh['asks'], default=None)),
                        'extra_levels': sum(len(book[s].keys() - fresh[s].keys()) for s in book),
                        'missing_levels': sum(len(fresh[s].keys() - book[s].keys()) for s in book)})
                book = fresh; emit(meta, r, 'snapshot'); continue
            if m.get('event_type') != 'price_change': continue
            for c in m.get('price_changes', []):
                if c['side'] not in ('BUY', 'SELL'): raise ValueError('invalid side')
                price, size = num(c['price']), num(c['size'])
                if not 0 <= price <= 1 or size < 0: raise ValueError('invalid level')
                if book is not None:
                    side = 'bids' if c['side'] == 'BUY' else 'asks'
                    if size == 0: book[side].pop(price, None)
                    else: book[side][price] = size
                emit(meta, r, 'delta_entry', c)
                if len(states) > MAX_RETAINED * 4: raise ValueError('state bound')
            emit(meta, r, 'message_complete')
    return states, before_snapshot, dict(counts)


def public_state(s, target):
    out = {k: v for k, v in s.items() if k not in {'bid', 'ask', 'source_bid', 'source_ask'}}
    out['replay_matches_csv_price_pair'] = (s['bid'] == num(target['bid']) and s['ask'] == num(target['ask']))
    if 'source_bid' in s:
        out['source_matches_csv_price_pair'] = (s['source_bid'] == num(target['bid']) and s['source_ask'] == num(target['ask']))
    if s['bid'] is not None and s['ask'] is not None:
        out['spread_probability_bps'] = str((s['ask'] - s['bid']) * 10000)
    return out


def analyze(target, records, source):
    row = target['row']; t = int(row['ts_ms'])
    old = legacy_rows([m['record'] for m in records], source)
    at_t = [r for r in old if int(r[1]) == t]
    exact = [r for r in at_t if all(num(r[i]) == num(row[k]) for i, k in
             ((5, 'bid'), (6, 'bid_size'), (7, 'ask'), (8, 'ask_size')))]
    variants = {}
    for name, snapshots in (('rest_only_decimal', False), ('ws_and_rest_decimal', True)):
        states, snaps, counts = replay(records, snapshots)
        matches = [i for i, s in enumerate(states) if s['timestamp_ms'] == t]
        indices = set()
        for i in matches: indices.update(range(max(0, i-3), min(len(states), i+4)))
        if len(indices) > 120: raise ValueError('ambiguous event context exceeds bound')
        variants[name] = {'counts': counts, 'state_counts': dict(Counter(s['status'] for s in states)),
            'same_timestamp_state_count': len(matches),
            'case_context': [public_state(states[i], row) for i in sorted(indices)],
            'snapshot_checks_near_case': sorted(snaps, key=lambda s: abs(s['timestamp_ms']-t))[:6]}
    return {'legacy_quote_rows': len(old), 'legacy_same_timestamp_rows': len(at_t),
            'legacy_exact_csv_price_size_matches': len(exact), 'variants': variants,
            'historical_etl_version_attested': False, 'population_cause_established': False}


def remote():
    resource.setrlimit(resource.RLIMIT_AS, (512*1024**2, 512*1024**2))
    progress = lambda v: print(json.dumps(v, sort_keys=True), flush=True)
    target, locator = locate_csv(CSV_PATH)
    progress({'stage': 'csv_case_located', 'locator': locator})
    records, raw_receipt = read_target(target, progress)
    progress({'stage': 'raw_hour_read', 'receipt': raw_receipt})
    result = {'schema': 'capture_cross_forensic_v1', 'locator': locator, 'raw_receipt': raw_receipt,
              'analysis': analyze(target, records, Path('/opt/d10/bin/etl.py').read_bytes()),
              'raw_frames_exported': 0, 'identifiers_exported': 0, 'source_mutated': False,
              'fits': 0, 'source_admitted': False, 'new_test_opened': False}
    progress({'stage': 'complete', 'report': result})


def local(output):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from market_rsi import fresh_json
    output.mkdir(parents=True, exist_ok=False)
    fresh_json(output/'claim.json', {'reader_sha256': file_hash(Path(__file__)), 'csv_sha256': CSV_HASH,
        'raw_sha256': RAW_HASH, 'etl_sha256': ETL_HASH, 'day': DAY, 'max_csv_rows': MAX_CSV_ROWS,
        'max_raw_rows': MAX_RAW_ROWS, 'remote_wall_seconds': 600, 'max_retained': MAX_RETAINED,
        'selection': 'first CSV crossing; diagnostic failure case, not model/data selection'})
    p = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'root@173.255.231.4',
        'nice -n 10 timeout --signal=TERM --kill-after=10s 600s python3 -u - --remote'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    p.stdin.write(Path(__file__).read_bytes()); p.stdin.close()
    # Read progress nonblocking and persist each packet immediately, including on failures.
    import os
    os.set_blocking(p.stdout.fileno(), False)
    selector = selectors.DefaultSelector(); selector.register(p.stdout, selectors.EVENT_READ)
    pending = b''; received = 0; seq = 0; completed = None; deadline = time.monotonic()+630
    try:
        eof = False
        while not eof:
            if time.monotonic() > deadline: raise TimeoutError('transport deadline; remote exit unverified')
            if not selector.select(1): continue
            data = os.read(p.stdout.fileno(), 65536)
            if not data: eof = True; continue
            pending += data; received += len(data)
            if received > 1024*1024: raise ValueError('output bound')
            while b'\n' in pending:
                line, pending = pending.split(b'\n', 1); packet = json.loads(line)
                fresh_json(output/f'progress-{seq:03d}.json', packet); seq += 1
                print(json.dumps({'progress': seq, 'stage': packet.get('stage'),
                                  'scanned': packet.get('scanned')}), flush=True)
                if packet.get('stage') == 'complete': completed = packet['report']
        code = p.wait(timeout=15)
        if pending or code or completed is None: raise ValueError('missing terminal receipt')
        completed['reader_sha256'] = file_hash(Path(__file__))
        completed['claim_sha256'] = file_hash(output/'claim.json')
        completed['exit_code'] = code; completed['ssh_reaped'] = True
        completed['result_sha256'] = digest(completed)
        fresh_json(output/'report.json', completed)
        print(json.dumps({'completed': str(output/'report.json'), 'result_sha256': completed['result_sha256']}))
    except BaseException as error:
        fresh_json(output/'failure.json', {'failure_type': type(error).__name__, 'progress_receipts': seq,
            'remote_exit_unverified': p.poll() is None, 'automatic_retry': False})
        if p.poll() is None: p.terminate()
        try: p.wait(timeout=10)
        except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=5)
        raise
    finally:
        selector.close(); p.stdout.close()


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--remote', action='store_true'); ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    if args.remote:
        try: remote()
        except Exception as error:
            print(json.dumps({'stage': 'failure', 'failure_type': type(error).__name__}), flush=True)
            sys.exit(1)
    elif args.output: local(args.output)
    else: ap.error('--output required')
