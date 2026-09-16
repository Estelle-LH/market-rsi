"""Independent full-row reconciliation of an existing recorded-trade index.

Never imports the builder or its projection/quality functions. No labels,
models, new dates, downloads, or modifications to the source/index artifacts.
"""
import argparse
import fcntl
from pathlib import Path
import sys

import numpy as np
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_rsi import canonical, digest, file_hash, fresh_json, load_json

FIELDS = {'received_at': 'received_ms', 'trade_time': 'event_ms',
          'trade_id': 'aggregate_trade_id', 'price': 'price', 'quantity': 'quantity',
          'quote_volume': 'reported_quote_volume', 'is_buyer_maker': 'reported_maker'}
EXPECTED = set(FIELDS.values()) | {'source_index', 'row_ordinal', 'quality_bits'}
QUALITY = {'invalid_price_or_quantity': 1, 'invalid_maker': 2, 'invalid_quote_amount': 4,
           'arrival_precedes_source_event': 8, 'invalid_aggregate_trade_id': 16}


def signed(path):
    value = load_json(path)
    if value.get('result_sha256') != digest({k: v for k, v in value.items() if k != 'result_sha256'}):
        raise ValueError('signed evidence changed')
    return value


def inspect_arrays(a, dates, sources):
    if set(a) != EXPECTED:
        raise ValueError('exact index schema required')
    n = len(a['received_ms'])
    if not 0 < n <= 8_000_000 or any(v.shape != (n,) for v in a.values()):
        raise ValueError('bounded aligned index required')
    for name in EXPECTED - {'price', 'quantity', 'reported_quote_volume'}:
        if not np.issubdtype(a[name].dtype, np.integer):
            raise ValueError('integer clocks, identifiers and quality flags required')
    if np.any(a['received_ms'] < 0) or np.any(a['event_ms'] < 0):
        raise ValueError('negative clock')
    if np.any((a['source_index'] < 0) | (a['source_index'] >= len(sources))):
        raise ValueError('invalid physical source')
    allowed = np.array(dates, dtype='datetime64[D]').astype(np.int64)
    day = a['received_ms'] // 86_400_000
    if not np.all(np.isin(day, allowed)):
        raise ValueError('unopened receipt date')
    order = np.lexsort((a['row_ordinal'], a['source_index'], a['received_ms']))
    if not np.array_equal(order, np.arange(n)):
        raise ValueError('index not in declared receipt/physical order')
    del order
    # Recompute flags independently, retaining every invalid record.
    p, q, v, maker = (a[k] for k in ('price', 'quantity', 'reported_quote_volume', 'reported_maker'))
    predicates = [~np.isfinite(p) | (p <= 0) | ~np.isfinite(q) | (q < 0),
                  ~np.isin(maker, [0, 1]),
                  ~np.isfinite(v) | (v < 0) | ~np.isfinite(p*q)
                  | (np.abs(v-p*q) > 1e-8 + 1e-10*np.abs(p*q)),
                  a['event_ms'] > a['received_ms'], a['aggregate_trade_id'] < 0]
    flags = np.zeros(n, dtype=np.uint8)
    for bit, predicate in zip(QUALITY.values(), predicates, strict=True):
        flags[predicate] |= bit
    if not np.array_equal(flags, a['quality_bits']):
        raise ValueError('quality flags do not match raw values')
    for i, source in enumerate(sources):
        ordinals = a['row_ordinal'][a['source_index'] == i]
        if (len(np.unique(ordinals)) != len(ordinals) or np.any(ordinals < 0)
                or np.any(ordinals >= source['full_source_rows_scanned'])):
            raise ValueError('duplicated or out-of-range physical key')
    return {'rows': n, 'rows_by_receipt_date': {
                str(np.datetime64(int(d), 'D')): int(np.count_nonzero(day == d)) for d in allowed},
            'quality_counts': {k: int(np.count_nonzero(flags & b)) for k, b in QUALITY.items()},
            'duplicate_aggregate_id_excess': n-len(np.unique(a['aggregate_trade_id'])),
            'recorded_receipt_tie_excess': n-len(np.unique(a['received_ms'])),
            'uncompressed_bytes': sum(v.nbytes for v in a.values())}


def reconcile_source(path, source_index, arrays, dates):
    """Compare EVERY selected raw physical row, not a sample or global-ID join."""
    selected = np.flatnonzero(arrays['source_index'] == source_index)
    selected = selected[np.argsort(arrays['row_ordinal'][selected])]
    allowed = np.array(dates, dtype='datetime64[D]').astype(np.int64)
    offset = used = 0
    for batch in pq.ParquetFile(path).iter_batches(batch_size=65536, columns=list(FIELDS)):
        raw = {k: batch.column(k).to_numpy(zero_copy_only=False) for k in FIELDS}
        mask = np.isin(raw['received_at'] // 86_400_000, allowed)
        ordinals = np.flatnonzero(mask) + offset
        take = selected[used:used+len(ordinals)]
        if not np.array_equal(arrays['row_ordinal'][take], ordinals):
            raise ValueError('raw physical row missing, duplicated or extra')
        for raw_name, name in FIELDS.items():
            expected, actual = raw[raw_name][mask], arrays[name][take]
            if expected.dtype != actual.dtype or expected.tobytes() != actual.tobytes():
                raise ValueError('indexed field is not byte-identical to physical raw row: '+name)
        used += len(ordinals)
        offset += batch.num_rows
    if used != len(selected):
        raise ValueError('extra indexed physical rows')
    return {'source_index': source_index, 'full_rows_scanned': offset,
            'selected_rows_compared': used, 'raw_fields_compared': len(FIELDS),
            'byte_identical_values': used*len(FIELDS)}


def run(index, ingest, materialized, availability, provenance, controller, output):
    root = Path(__file__).resolve().parents[1]
    with (root/'artifacts/historical-ingest-controller.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        report = signed(index/'result.json')
        claim = load_json(index/'claim.json')
        material = signed(materialized/'result.json')
        available = signed(availability/'audit.json')
        publisher = signed(provenance/'provenance.json')
        if not report['complete'] or file_hash(index/'claim.json') != report['claim_sha256']:
            raise ValueError('completed index and unchanged claim required')
        sources = sorted([r for r in material['all_source_receipts'] if '/binance_trades/' in r['path']],
                         key=lambda r: r['path'])
        dates = material['controller_requested_utc_dates']
        if (claim['sources'] != sources or claim['dates'] != dates
                or report['opened_train_utc_dates'] != dates or claim['direction_contract'] != publisher['direction_contract']
                or claim['materialization_result_sha256'] != material['result_sha256']
                or available['materialization_result_sha256'] != material['result_sha256']
                or available['already_open_train_utc_dates'] != dates):
            raise ValueError('index not bound to exact prior opened data')
        bindings = {index/'events.npz': report['archive_sha256'],
                    index/'claim.json': report['claim_sha256'],
                    availability/'audit.json': claim['field_audit_sha256'],
                    provenance/'provenance.json': claim['publisher_provenance_sha256'],
                    controller/'session/assessment.json': claim['controller_assessment_sha256'],
                    controller/'workspace/submitted-grid-learning-decision.json': claim['controller_decision_sha256'],
                    root/'historical_trade_event_index.py': claim['source_code_sha256']}
        bindings.update({ingest/'raw'/s['path']: s['source_sha256'] for s in sources})
        for path in (index/'result.json', materialized/'result.json', Path(__file__), root/'market_rsi.py'):
            bindings[path] = file_hash(path)
        if any(file_hash(p) != h for p, h in bindings.items()):
            raise ValueError('input, controller request or frozen source changed')
        output.mkdir(parents=True, exist_ok=False)
        fresh_json(output/'claim.json', {'schema': 'trade_index_independent_audit_claim_v1',
            'input_hashes': {str(p): h for p, h in bindings.items()},
            'comparison': 'every selected physical raw row, every field byte, no target-based sampling',
            'provider_calls': 0, 'fits': 0, 'labels_read': False, 'new_downloads': 0})
        try:
            with np.load(index/'events.npz', allow_pickle=False) as data:
                arrays = {k: data[k] for k in data.files}
            aggregate = inspect_arrays(arrays, dates, sources)
            for key in aggregate.keys() - {'rows_by_receipt_date'}:
                if report[key] != aggregate[key]:
                    raise ValueError('independent count differs: '+key)
            audited = {r['path']: r for r in available['trade_field_audits']}
            receipts = []
            for i, source in enumerate(sources):
                item = reconcile_source(ingest/'raw'/source['path'], i, arrays, dates)
                if (item['full_rows_scanned'] != source['full_source_rows_scanned']
                        or item['selected_rows_compared'] != audited[source['path']]['opened_train_only_counts'].get('rows', 0)):
                    raise ValueError('full raw count differs from prior audit')
                receipts.append(item | {'path': source['path'], 'source_sha256': source['source_sha256']})
            if any(file_hash(p) != h for p, h in bindings.items()):
                raise ValueError('bound source changed during audit')
            result = {'schema': 'trade_index_independent_full_audit_v1', 'passed': True,
                'index_result_sha256': report['result_sha256'], 'claim_sha256': file_hash(output/'claim.json'),
                'aggregate': aggregate, 'source_reconciliations': receipts,
                'raw_values_compared_byte_identical': sum(r['byte_identical_values'] for r in receipts),
                'all_physical_rows_retained': True, 'source_hashes_unchanged': True,
                'provider_calls': 0, 'fits': 0, 'labels_read': False, 'new_downloads': 0,
                'training_admitted': False, 'auditor_sha256': file_hash(Path(__file__)),
                'boundary': 'Exact stored-record reconciliation only. No proof of complete exchange feed, historical deployment, or predictive value.'}
            result['result_sha256'] = digest(result)
            fresh_json(output/'audit.json', result)
            return result
        except Exception as error:
            fresh_json(output/'failure.json', {'type': type(error).__name__, 'error': str(error), 'no_automatic_retry': True})
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('index', 'ingest', 'materialized', 'availability', 'provenance', 'controller', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    result = run(**{k: v.resolve() for k, v in vars(parser.parse_args()).items()})
    print(canonical({k: result[k] for k in ('passed', 'raw_values_compared_byte_identical', 'result_sha256')}))
