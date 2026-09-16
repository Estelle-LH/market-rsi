"""Bounded causal minute-grid primitives for a controller-selected diagnostic pilot.

This materializes observed states, not labels, a fitted model, or an executable
trading tape. Physical provenance and missing states survive aggregation. The
controller chooses cadence, dates, age and sources; this code never substitutes
an objective or removes quiet grid rows.
"""
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
import math

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

from historical_source_contract import CANDLE_MS, CLOCK_ASSUMPTION, project, require_causal_feature
from market_rsi import canonical, digest


DAY_MS = 86_400_000
MAX_TIES = 4096
MAX_NODES = 1_500_000


def day_start(day):
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()) * 1000


def day_windows(plan, *, padded=False):
    padding = plan['max_age_ms'] + plan['cadence_ms'] if padded else 0
    return [(day_start(d) - padding, day_start(d) + DAY_MS) for d in plan['open_train_utc_dates']]


def clock_array(table, stream):
    names = (['ingest_ts_ms'] if stream == 'polymarket_ticks_ms' else
             ['received_at'] if stream == 'binance_trades' else
             ['created_at', 'candle_end'] if stream in CANDLE_MS else [])
    if not names or not set(names) <= set(table.column_names):
        raise ValueError('unsupported stream or missing clock')
    values = []
    for name in names:
        if table[name].null_count:raise ValueError('null receipt clock')
        array = table[name].to_numpy()
        if not np.issubdtype(array.dtype, np.integer):raise ValueError('integer receipt clock required')
        values.append(array.astype(np.int64))
    result = values[0] if len(values) == 1 else np.maximum(values[0], values[1] + 1)
    if np.any((result < 946684800000) | (result >= 4102444800000)):
        raise ValueError('receipt clock outside bounded epoch range')
    return result


def window_mask(clocks, windows):
    mask = np.zeros(len(clocks), dtype=bool)
    for start, end in windows:mask |= (clocks >= start) & (clocks < end)
    return mask


def latest_indices(slots, entities, clocks):
    """All latest-ms ties per entity/grid bin, independent of raw batch ordering."""
    if not len(clocks):return np.array([], dtype=np.int64)
    order = np.lexsort((clocks, entities, slots))
    starts = np.r_[0, np.flatnonzero((np.diff(slots[order]) != 0) | (np.diff(entities[order]) != 0)) + 1]
    ends = np.r_[starts[1:], len(order)]
    maxima = clocks[order[ends - 1]]
    keep = clocks[order] == np.repeat(maxima, ends - starts)
    return order[keep]


def visible_state(records, decision_ms, plan, stream):
    if not records:return {'values': {}, 'reason': 'no_visible_observation', 'sources': []}
    fields = (['reported_bid', 'reported_ask', 'midpoint_from_reported_bbo']
              if stream == 'polymarket_ticks_ms' else ['trade_price', 'trade_quantity']
              if stream == 'binance_trades' else ['open_price', 'high_price', 'low_price', 'close_price'])
    refs = [r['source'] for r in records]
    values = []
    try:
        for record in records:
            values.append({name: require_causal_feature(record, name, decision_ms,
                max_age_ms=plan['max_age_ms'], clock_assumption=plan['clock_assumption']) for name in fields})
    except ValueError as exc:
        return {'values': {}, 'reason': str(exc), 'sources': refs}
    if len({canonical(v) for v in values}) != 1:
        return {'values': {}, 'reason': 'conflicting_same_receipt_timestamp_values', 'sources': refs}
    return {'values': values[0], 'reason': 'recorded_source_only_not_execution_proof', 'sources': refs,
            'available_ms': records[0]['recorded_available_ms'],
            'max_source_age_ms': max(decision_ms-r['source_event_ms'] for r in records)}


class GridMaterializer:
    def __init__(self, plan, metadata):
        if (plan['purpose'] != 'diagnostic_learning_pilot' or plan['primary_observation'] != 'pm_reported_bbo'
                or plan['market_time_scope'] != 'observed_arrival_interval'
                or plan['clock_assumption'] != CLOCK_ASSUMPTION
                or type(plan['cadence_ms']) is not int or plan['cadence_ms'] <= 0
                or type(plan['max_age_ms']) is not int or plan['max_age_ms'] < 0
                or not 0 < plan['max_materialized_rows'] <= 500000):
            raise ValueError('unsupported or unbounded controller data-use proposal')
        if not set(plan['context_streams']) <= {'binance_trades', *CANDLE_MS}:
            raise ValueError('context implementation unavailable; never substitute streams')
        if not metadata or len(metadata) > 20000:raise ValueError('bounded metadata required')
        self.plan = plan
        self.metadata = {r['market_slug']: {r['up_token_id'], r['down_token_id']} for r in metadata}
        if len(self.metadata) != len(metadata) or any(len(v) != 2 or None in v for v in self.metadata.values()):
            raise ValueError('unique market and two distinct token identities required')
        self.market_names = list(self.metadata)
        self.market_array = pa.array(self.market_names)
        # Pair codes are stable only within this materialization, never raw IDs.
        self.pairs = [(m, token) for m, tokens in self.metadata.items() for token in sorted(tokens)]
        self.pair_array = pa.array([m + '\x1f' + a for m, a in self.pairs])
        self.nodes = {}
        self.bounds = {}
        self.counts = Counter()
        self.event_bins = Counter()
        self.windows = day_windows(plan)
        self.padded_windows = day_windows(plan, padded=True)

    def consume(self, table, item, ordinal_offset=0, *, raw_ordinals=None):
        if isinstance(table, pa.RecordBatch):table = pa.Table.from_batches([table])
        if table.num_rows > 100000:raise ValueError('bounded 100000-row batch required')
        stream = item['path'].split('/')[1]
        if stream not in {'polymarket_ticks_ms', *self.plan['context_streams']}:
            raise ValueError('stream not selected by controller')
        clocks = clock_array(table, stream)
        self.counts[stream + ':scanned_rows'] += table.num_rows
        positions = np.flatnonzero(window_mask(clocks, self.padded_windows))
        if not len(positions):return
        ordinals = np.arange(table.num_rows, dtype=np.int64) + ordinal_offset if raw_ordinals is None else raw_ordinals
        if len(ordinals) != table.num_rows or np.any(np.asarray(ordinals) < 0):raise ValueError('physical ordinals required')
        ordinals = np.asarray(ordinals)[positions]
        table = table.take(pa.array(positions));clocks = clocks[positions]
        slots = (clocks + self.plan['cadence_ms'] - 1) // self.plan['cadence_ms']
        self.counts[stream + ':in_clock_window_rows'] += len(clocks)
        if stream == 'polymarket_ticks_ms':
            pair_strings = pc.binary_join_element_wise(table['market_slug'], table['asset_id'], '\x1f')
            entities = pc.fill_null(pc.index_in(pair_strings, value_set=self.pair_array), -1).to_numpy().astype(np.int64)
            markets = pc.fill_null(pc.index_in(table['market_slug'], value_set=self.market_array), -1).to_numpy().astype(np.int64)
            if np.any(markets < 0):raise ValueError('unrecognized market requires independent metadata audit')
            self.counts['identity_mismatch_rows'] += int(np.sum(entities < 0))
            in_dates = window_mask(clocks, self.windows)
            groups = np.stack([markets[in_dates], clocks[in_dates] // DAY_MS], axis=1)
            if len(groups):
                keys, inverse = np.unique(groups, axis=0, return_inverse=True)
                lo = np.full(len(keys), np.iinfo(np.int64).max, dtype=np.int64)
                hi = np.full(len(keys), -1, dtype=np.int64)
                np.minimum.at(lo, inverse, clocks[in_dates]);np.maximum.at(hi, inverse, clocks[in_dates])
                for (m, day), start, end in zip(keys, lo, hi):
                    key = (int(m), int(day));old = self.bounds.get(key, (int(start), int(end)))
                    self.bounds[key] = (min(old[0], int(start)), max(old[1], int(end)))
            # Count only records that are known by each cadence tick. No final-day activity feature.
            valid = entities >= 0
            keys, counts = np.unique(np.stack([entities[valid], slots[valid]], axis=1), axis=0, return_counts=True)
            for (entity, slot), count in zip(keys, counts):self.event_bins[(int(entity), int(slot))] += int(count)
            self.counts['mismatched_rows_retained_only_in_raw'] += int(np.sum(~valid))
            use = np.flatnonzero(valid)
            table = table.take(pa.array(use));clocks = clocks[use];slots = slots[use];ordinals = ordinals[use];entities = entities[use]
        else:entities = np.zeros(len(clocks), dtype=np.int64)
        selected = latest_indices(slots, entities, clocks)
        rows = table.take(pa.array(selected)).to_pylist()
        for index, row in zip(selected, rows):
            record = project(row, item, int(ordinals[index]), metadata=self.metadata)
            key = (stream, int(entities[index]), int(slots[index]))
            previous = self.nodes.get(key, [])
            available = record['recorded_available_ms']
            if previous and available < previous[0]['recorded_available_ms']:continue
            if not previous or available > previous[0]['recorded_available_ms']:
                self.nodes[key] = [record]
            else:
                # Ties may be duplicates or conflicts: preserve every physical reference.
                if len(previous) >= MAX_TIES:raise ValueError('same-ms tie memory guard exceeded')
                previous.append(record)
            if len(self.nodes) > MAX_NODES:raise ValueError('materializer state memory guard exceeded')
            self.counts[stream + ':representatives_projected'] += 1

    def rows(self):
        # Count BEFORE producing output; never silently clip the final dates/quiet rows.
        n = 0
        cadence = self.plan['cadence_ms']
        for lo, hi in self.bounds.values():
            n += max(0, hi // cadence - (lo + cadence-1) // cadence + 1) * 2
        if n > self.plan['max_materialized_rows']:raise ValueError('grid exceeds row cap; no truncation allowed')
        index = defaultdict(dict)
        for (stream, entity, slot), records in self.nodes.items():index[(stream, entity)][slot] = records
        ordered = {key: sorted(v) for key, v in index.items()}
        streams = ['polymarket_ticks_ms', *self.plan['context_streams']]
        for (market, day), (lo, hi) in sorted(self.bounds.items()):
            for slot in range((lo + cadence-1)//cadence, hi//cadence + 1):
                when = slot * cadence
                for side in range(2):
                    entity = market * 2 + side
                    values = {}
                    for stream in streams:
                        key = (stream, entity if stream == 'polymarket_ticks_ms' else 0)
                        slots = ordered.get(key, [])
                        j = bisect_right(slots, slot)-1
                        records = index[key][slots[j]] if j >= 0 else []
                        values[stream] = visible_state(records, when, self.plan, stream)
                    m, asset = self.pairs[entity]
                    body = {'market_slug': m, 'asset_id': asset, 'decision_ms': when,
                            'utc_date': datetime.fromtimestamp(when/1000, timezone.utc).date().isoformat(),
                            'pm_events_since_previous_grid_tick': self.event_bins[(entity, slot)],
                            'observations': values, 'training_admitted': False, 'target': None}
                    body['row_id'] = digest({'market_slug':m, 'asset_id':asset, 'decision_ms':when})
                    yield body

    def summary(self):
        return {'counts':dict(self.counts), 'retained_latest_state_nodes':len(self.nodes),
                'observed_market_days':len(self.bounds), 'training_admitted':False,
                'objective_selected':False, 'future_label_filter':False, 'raw_records_deleted':False}
