"""Causal windows over ALL recorded aggregate-trade receipts, not grid snapshots.

Pure capability: the researcher must explicitly choose the statistic, window,
minimum count and recorded-gap tolerance. No labels, defaults or imputation.
Receipt continuity is only a recorded-feed proxy, never exchange completeness.
This additive module does not modify existing feature engines or profiles.
"""
from pathlib import Path
import zipfile

import numpy as np

from market_rsi import digest, file_hash, identifier, load_json

SPEC_FIELDS = {'name', 'source', 'statistic', 'window_ms', 'minimum_records',
               'maximum_recorded_gap_ms'}
SOURCE = 'binance_trades.recorded_aggregate_events'
STATISTICS = {
    'record_count': 'Number of recorded aggregate-trade rows, not constituent trades.',
    'quantity_sum': 'Sum of recorded BTC quantity.',
    'quote_volume_sum': 'Sum of recorded quote amount (USDT).',
    'recorded_vwap': 'Recorded quote amount sum divided by quantity sum; zero denominator unknown.',
    'maker0_minus_maker1_quantity': 'Quantity with reported maker0 minus quantity with maker1.',
    'maker0_minus_maker1_quote_volume': 'Quote amount with reported maker0 minus amount with maker1.',
    'maker_quantity_imbalance': '(maker0 quantity minus maker1 quantity)/total quantity; zero denominator unknown.',
    'maker_quote_volume_imbalance': '(maker0 amount minus maker1 amount)/total amount; zero denominator unknown.',
}
REASONS = {'available': 0, 'unopened_window_context': 1, 'unobserved_window_beginning': 2,
           'insufficient_record_count': 3, 'recorded_gap_exceeds_limit': 4,
           'invalid_record_in_window': 5, 'zero_denominator': 6}


def load_audited_index(index, audit):
    """Verify existing full-row reconciliation; never creates or rescans a source."""
    index, audit = Path(index), Path(audit)
    report = load_json(index/'result.json')
    evidence = load_json(audit)
    for value in (report, evidence):
        if value.get('result_sha256') != digest({k: v for k, v in value.items() if k != 'result_sha256'}):
            raise ValueError('signed recorded-event evidence changed')
    if (report.get('schema') != 'historical_trade_event_index_v1' or report.get('complete') is not True
            or evidence.get('schema') != 'trade_index_independent_full_audit_v1' or evidence.get('passed') is not True
            or evidence['index_result_sha256'] != report['result_sha256']
            or evidence['aggregate']['rows'] != report['rows']
            or evidence['raw_values_compared_byte_identical'] != report['rows']*7
            or evidence.get('source_hashes_unchanged') is not True
            or report.get('training_admitted') is not False
            or file_hash(index/'claim.json') != report['claim_sha256']
            or file_hash(audit.parent/'claim.json') != evidence['claim_sha256']):
        raise ValueError('exact completed full-row reconciliation required')
    archive = index/'events.npz'
    if file_hash(archive) != report['archive_sha256']:
        raise ValueError('audited event archive changed')
    expected = {'received_ms', 'event_ms', 'aggregate_trade_id', 'price', 'quantity',
                'reported_quote_volume', 'reported_maker', 'source_index', 'row_ordinal', 'quality_bits'}
    with zipfile.ZipFile(archive) as z:
        if (len(z.infolist()) != len(expected) or set(z.namelist()) != {k+'.npy' for k in expected}
                or sum(f.file_size for f in z.infolist()) > 550_010_000):
            raise ValueError('bounded exact recorded-event archive required')
    with np.load(archive, allow_pickle=False) as z:
        arrays = {k: z[k] for k in expected}
    if (any(v.shape != (report['rows'],) for v in arrays.values())
            or sum(v.nbytes for v in arrays.values()) != report['uncompressed_bytes']
            or file_hash(archive) != report['archive_sha256']):
        raise ValueError('recorded-event shape or bytes changed during load')
    return arrays, report['opened_train_utc_dates'], {
        'index_result_sha256': report['result_sha256'], 'archive_sha256': report['archive_sha256'],
        'independent_audit_sha256': file_hash(audit), 'source_rows': report['rows']}


def validate_spec(spec):
    if not isinstance(spec, dict) or set(spec) != SPEC_FIELDS:
        raise ValueError('complete explicit recorded-window specification required')
    identifier(spec['name'])
    if spec['source'] != SOURCE or spec['statistic'] not in STATISTICS:
        raise ValueError('unsupported recorded-trade source/statistic')
    for key, lo, hi in [('window_ms', 1, 86_400_000), ('minimum_records', 1, 8_000_000),
                        ('maximum_recorded_gap_ms', 1, 86_400_000)]:
        if type(spec[key]) is not int or not lo <= spec[key] <= hi:
            raise ValueError('explicit bounded positive integer required: '+key)
    if spec['maximum_recorded_gap_ms'] > spec['window_ms']:
        raise ValueError('recorded-gap tolerance cannot exceed window')
    return spec


def opened_blocks(dates):
    if not isinstance(dates, list) or not dates or dates != sorted(set(dates)):
        raise ValueError('sorted unique opened UTC dates required')
    days = np.array(dates, dtype='datetime64[D]').astype(np.int64)
    if np.any(days < 0) or not np.array_equal(days.astype('datetime64[D]').astype(str), dates):
        raise ValueError('valid explicit opened UTC dates required')
    starts = np.r_[True, np.diff(days) != 1]
    ends = np.r_[np.diff(days) != 1, True]
    return days[starts]*86_400_000, (days[ends]+1)*86_400_000


class RecordedTradeWindows:
    """One validated recorded index; no knowledge of target/outcomes or entities."""
    def __init__(self, arrays, dates):
        required = {'received_ms', 'event_ms', 'quantity', 'reported_quote_volume', 'reported_maker', 'quality_bits'}
        if not required <= set(arrays):
            raise ValueError('audited raw-event fields required')
        self.a = {k: np.asarray(arrays[k]) for k in required}
        self.t = self.a['received_ms']
        n = len(self.t)
        if (not 0 < n <= 8_000_000 or any(v.shape != (n,) for v in self.a.values())
                or not np.issubdtype(self.t.dtype, np.signedinteger)
                or not np.issubdtype(self.a['event_ms'].dtype, np.signedinteger)
                or not np.issubdtype(self.a['quality_bits'].dtype, np.integer)
                or np.any(self.t < 0) or np.any(self.a['event_ms'] < 0)
                or np.any(np.diff(self.t) < 0)):
            raise ValueError('bounded receipt-sorted aligned numeric event arrays required')
        self.starts, self.ends = opened_blocks(dates)
        block = np.searchsorted(self.starts, self.t, side='right')-1
        safe = np.maximum(block, 0)
        if np.any((block < 0) | (self.t >= self.ends[safe])):
            raise ValueError('recorded receipt outside opened dates')
        self.first = np.array([self.t[np.searchsorted(self.t, start)]
            if np.searchsorted(self.t, start) < n and self.t[np.searchsorted(self.t, start)] < end
            else end for start, end in zip(self.starts, self.ends, strict=True)])
        q, v, m = (self.a[k] for k in ('quantity', 'reported_quote_volume', 'reported_maker'))
        # Recheck minimum value/causality invariants even if a caller supplies bad flags.
        self.bad = ((self.a['quality_bits'] != 0) | (self.a['event_ms'] > self.t)
                    | ~np.isfinite(q) | (q < 0) | ~np.isfinite(v) | (v < 0) | ~np.isin(m, [0, 1]))
        self.bad_prefix = np.r_[0, np.cumsum(self.bad, dtype=np.int64)]

    def derive(self, decision_ms, *, spec):
        validate_spec(spec)
        decision = np.asarray(decision_ms)
        if (decision.ndim != 1 or not 0 < len(decision) <= 500_000
                or not np.issubdtype(decision.dtype, np.signedinteger) or np.any(decision < 0)):
            raise ValueError('bounded nonnegative integer decisions required')
        # Repeated times (UP/DOWN entities) share the same external recorded input.
        t, inverse = np.unique(decision, return_inverse=True)
        left = t-spec['window_ms']
        lo = np.searchsorted(self.t, left, side='right')
        hi = np.searchsorted(self.t, t, side='right')
        count = hi-lo
        reason = np.zeros(len(t), dtype=np.uint8)

        def exclude(mask, code):
            reason[(reason == 0) & mask] = code

        block = np.searchsorted(self.starts, left, side='right')-1
        safe = np.maximum(block, 0)
        exclude((block < 0) | (left < self.starts[safe]) | (t >= self.ends[safe]), 1)
        exclude(left < self.first[safe], 2)
        exclude(count < spec['minimum_records'], 3)
        # All tied receipts are included together; physical order is not a price path.
        first = self.t[np.minimum(lo, len(self.t)-1)]
        last = self.t[np.maximum(hi-1, 0)]
        long_gap = np.r_[False, np.diff(self.t) > spec['maximum_recorded_gap_ms']]
        gap_prefix = np.r_[0, np.cumsum(long_gap, dtype=np.int64)]
        internal = gap_prefix[hi]-gap_prefix[np.minimum(lo+1, hi)]
        exclude((internal > 0) | (first-left > spec['maximum_recorded_gap_ms'])
                | (t-last > spec['maximum_recorded_gap_ms']), 4)
        exclude(self.bad_prefix[hi]-self.bad_prefix[lo] > 0, 5)

        def window_sum(column, signed=False):
            raw = self.a[column]
            # Invalid records never yield an available window. Zero here is only a
            # private prefix-sum placeholder, not an imputed record/feature.
            valid = np.where(self.bad, 0, raw).astype(np.longdouble)
            if signed:
                valid *= np.where(self.a['reported_maker'] == 0, 1, -1)
            prefix = np.r_[np.longdouble(0), np.cumsum(valid, dtype=np.longdouble)]
            return prefix[hi]-prefix[lo]

        stat = spec['statistic']
        if stat == 'record_count':
            value = count.astype(np.longdouble)
        elif stat == 'quantity_sum':
            value = window_sum('quantity')
        elif stat == 'quote_volume_sum':
            value = window_sum('reported_quote_volume')
        elif stat.startswith('maker0_minus_maker1_'):
            col = 'quantity' if stat.endswith('_quantity') else 'reported_quote_volume'
            value = window_sum(col, signed=True)
        else:
            col = 'reported_quote_volume' if stat == 'maker_quote_volume_imbalance' else 'quantity'
            denominator = window_sum(col)
            numerator = (window_sum('reported_quote_volume') if stat == 'recorded_vwap'
                         else window_sum(col, signed=True))
            value = np.full(len(t), np.nan, dtype=np.longdouble)
            np.divide(numerator, denominator, out=value, where=denominator > 0)
            exclude(denominator <= 0, 6)
        value = value.astype(np.float64)
        if np.any((reason == 0) & ~np.isfinite(value)):
            raise ValueError('nonfinite recorded-window arithmetic; no silent clipping')
        value[reason != 0] = np.nan
        return {'values': value[inverse], 'available': (reason == 0)[inverse],
                'observations_used': count[inverse], 'feature_available_ms': decision.copy(),
                'reason': reason[inverse], 'reason_codes': dict(REASONS), 'spec': dict(spec),
                'full_population_rows': len(decision), 'future_labels_used': False,
                'normalizer_fitted': False, 'receipt_interval': '(decision-window, decision]',
                'exchange_completeness_verified': False,
                'limits': ['Only received records; elapsed-time gap is not independent feed coverage.',
                           'An empty recorded window is unknown, not zero activity.',
                           'Maker0 may include publisher defaults; signs refer to reported flags only.',
                           'Aggregate-trade rows and same-ms ties retained, not independent constituent trades.']}
