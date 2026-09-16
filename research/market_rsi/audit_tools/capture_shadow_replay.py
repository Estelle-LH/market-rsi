"""Compare reviewed ETL with explicit snapshot/invalid states on a fixed prefix.

This is a source diagnostic, not a released trading feed or fitted experiment.
The current production ETL and original archives remain unchanged. Raw values
exist only in Linode process memory; the response contains counters and hashes.
"""
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

EXPECTED_ETL = '584c7682d9d6ed331bc192da31e75890b7fc4158f4082137f2e2c028b6b1bf8b'
EXPECTED_SOURCE = '27621845de8cc31ca2055235b2a4b69e11a0c6116f3d316f3eda84e647bb4255'
EXPECTED_PREFIX = '03d5f2ec3c8d9f24bb76797071ce2b2a1af432620c5385ab4c2aef657507f56e'


def number(value, price=False):
    result = Decimal(str(value))
    if not result.is_finite() or result < 0 or (price and result > 1):
        raise ValueError('invalid price/size')
    return result


def shadow(records, atomic=True, ws_snapshots=True):
    books = {}; states = []; counts = Counter(); identities = {}

    def emit(i, a):
        b = books.get(a)
        if b is None:
            states.append((i, a, 'unanchored', None, None)); return
        bid = max(b['bids'], default=None); ask = min(b['asks'], default=None)
        status = 'one_sided' if bid is None or ask is None else ('crossed' if bid > ask else 'two_sided')
        states.append((i, a, status, bid, ask))

    def snapshot(i, m):
        a = m.get('asset_id')
        if not isinstance(a, str) or not a: raise ValueError('missing token')
        books[a] = {side: {number(x['price'], True): number(x['size']) for x in m.get(side, [])
                           if number(x['size']) > 0} for side in ('bids', 'asks')}
        counts['snapshots'] += 1; emit(i, a)

    for i, r in enumerate(records):
        messages = r['m'] if isinstance(r['m'], list) else [r['m']]
        for m in messages:
            if r.get('src') == 'rest': snapshot(i, m); continue
            et = m.get('event_type')
            a = m.get('asset_id'); market = m.get('market')
            if a and market:
                if a in identities and identities[a] != market: raise ValueError('token changed market')
                identities[a] = market
            if et == 'book':
                if ws_snapshots: snapshot(i, m)
                continue
            if et != 'price_change': continue
            affected = []
            for c in m.get('price_changes', []):
                a = c.get('asset_id')
                if not isinstance(a, str) or not a: raise ValueError('missing token')
                if market:
                    if a in identities and identities[a] != market: raise ValueError('token changed market')
                    identities[a] = market
                if a not in affected: affected.append(a)
                if c['side'] not in ('BUY', 'SELL'): raise ValueError('invalid side')
                price, size = number(c['price'], True), number(c['size'])
                counts['delta_entries'] += 1
                if a not in books:
                    counts['unanchored_delta_entries'] += 1
                else:
                    side = 'bids' if c['side'] == 'BUY' else 'asks'
                    if size == 0: books[a][side].pop(price, None)
                    else: books[a][side][price] = size
                if not atomic: emit(i, a)
            if atomic:
                for a in affected: emit(i, a)
    return states, dict(counts)


def summarize(states, counts):
    return {'state_records': len(states), 'state_counts': dict(Counter(s[2] for s in states)),
            'tokens_with_states': len({s[1] for s in states}), **counts}


def legacy(records, source):
    if hashlib.sha256(source).hexdigest() != EXPECTED_ETL: raise ValueError('reviewed ETL changed')
    names = {'iso', 'emit_tob', 'write_depth', 'run_polymarket'}
    selected = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in names]
    if len(selected) != 4: raise ValueError('reviewed ETL functions missing')
    ns = {'datetime': datetime, 'timezone': timezone,
          'glob': SimpleNamespace(glob=lambda _: ['fixed-prefix']), 'rows': lambda _: iter(records),
          'TOB_HEADER': [], 'TRADE_HEADER': [], 'DEPTH_HEADER': []}
    exec(compile(ast.Module(body=selected, type_ignores=[]), '<reviewed-etl>', 'exec'), ns)
    class Writer:
        def __init__(self): self.count = self.crossed = 0
        def writerow(self, row):
            self.count += 1
    class QuoteWriter(Writer):
        def writerow(self, row):
            super().writerow(row); self.crossed += float(row[5]) > float(row[7])
    class Out:
        def __init__(self): self.writers = {}
        def csv(self, name, header):
            return self.writers.setdefault(name, QuoteWriter() if name == 'topofbook' else Writer())
    out = Out(); ns['run_polymarket']('/unused', '2026-08-21', out, 60, {}, set())
    return {'quote_rows': out.writers['topofbook'].count, 'crossed_quote_rows': out.writers['topofbook'].crossed}


def run_remote():
    records, receipt = read_prefix()  # Injected frozen prefix reader; no remote imports.
    if receipt['source_sha256'] != EXPECTED_SOURCE or receipt['prefix_sha256'] != EXPECTED_PREFIX:
        raise ValueError('fixed prefix changed')
    profile(records)  # Exact diagnostic day gate BEFORE interpreting prices.
    source = Path('/opt/d10/bin/etl.py').read_bytes()
    variants = {}
    for name, atomic, snapshots in [('atomic_rest_only', True, False),
                                     ('per_entry_with_ws_snapshots', False, True),
                                     ('atomic_with_ws_snapshots', True, True)]:
        states, counts = shadow(records, atomic, snapshots)
        variants[name] = summarize(states, counts)
    return {'schema': 'capture_shadow_prefix_v1', 'source': receipt, 'etl_sha256': EXPECTED_ETL,
        'legacy_current_code': legacy(records, source), 'shadow_variants': variants,
        'raw_rows_exported': 0, 'source_mutated': False, 'source_admitted': False, 'fits': 0,
        'actual_published_csv_compared': False, 'historical_error_frequency_proven': False,
        'limitations': ['First 5000 records only, most tokens may start unanchored.',
            'Compares current reviewed code, not an attested historical ETL version.',
            'Two-sided state does not establish freshness, clock semantics or complete venue sequence.',
            'No Gamma labels or future-price selection; historical identity mapping remains unverified.']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--remote', action='store_true')
    p.add_argument('--output', type=Path); a = p.parse_args()
    if a.remote:
        try: print(json.dumps(run_remote()))
        except Exception as error:
            print(json.dumps({'failure_type': type(error).__name__, 'raw_rows_exported': 0})); sys.exit(1)
        sys.exit(0)
    if not a.output or a.output.exists(): raise ValueError('fresh output required')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from market_rsi import digest, file_hash, fresh_json
    prefix = Path(__file__).with_name('capture_raw_prefix.py').read_text().split("if __name__ == '__main__':")[0]
    source = (prefix + '\n' + Path(__file__).read_text()).encode()
    a.output.mkdir(parents=True)
    fresh_json(a.output/'claim.json', {'reader_sha256': hashlib.sha256(source).hexdigest(),
        'source_sha256': EXPECTED_SOURCE, 'prefix_sha256': EXPECTED_PREFIX, 'etl_sha256': EXPECTED_ETL})
    response = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
        'root@173.255.231.4', 'nice -n 10 timeout 90s python3 - --remote'], input=source,
        capture_output=True, timeout=105)
    if response.returncode or len(response.stdout) > 100000:
        fresh_json(a.output/'failure.json', {'exit_code': response.returncode, 'raw_rows_exported': 0})
        raise RuntimeError('shadow replay failed; claim and failure preserved')
    value = json.loads(response.stdout); value['claim_sha256'] = file_hash(a.output/'claim.json')
    value['result_sha256'] = digest(value); fresh_json(a.output/'report.json', value); print(json.dumps(value))
