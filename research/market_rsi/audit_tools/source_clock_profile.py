"""Descriptive source-clock counts; NOT decision groups, labels or row admission.

See SINGLE_OBJECT_AUDIT_2026-09-13.md. Reuses the unchanged source BBO/depth
adapter and population counters. Source-clock runs count consecutive equal
timestamps in raw order; a later recurrence is not silently re-sorted/merged.
"""
from collections import Counter
import hashlib
import json

from population_quote_profile import PopulationProfile
from quote_source.reconstruct import QuoteReconstructor


def gap_bucket(dt):
    if dt < 0: return 'regression'
    if dt == 0: return '0ms'
    if dt <= 1000: return '1..1000ms'
    if dt <= 10000: return '1001..10000ms'
    if dt <= 60000: return '10001..60000ms'
    return '>60000ms'


class ClockCounts:
    def __init__(self):
        self.counts = Counter()
        self.gaps = Counter()
        self.group_sizes = Counter()
        self.previous = self.highwater = self.first = self.last = None
        self.group_size = 0
        self.previous_key = None

    def close_group(self):
        if self.group_size:
            self.group_sizes[self.group_size] += 1
            self.group_size = 0

    def observe(self, row):
        key = tuple(row['key'])
        if self.previous_key is not None and key <= self.previous_key:
            raise ValueError('immutable quote key repeated or regressed')
        self.previous_key = key
        self.counts['quote_rows'] += 1
        t = row['source_ms']
        if t is None:
            self.counts['missing_or_invalid_source_ms'] += 1
            self.close_group(); self.previous = None
            return
        self.counts['valid_shape_source_ms'] += 1
        self.first = t if self.first is None else min(t, self.first)
        self.last = t if self.last is None else max(t, self.last)
        if self.highwater is not None and t < self.highwater:
            self.counts['below_prior_highwater_rows'] += 1
        self.highwater = max(t, self.highwater or t)
        if self.previous is not None:
            self.gaps[gap_bucket(t-self.previous)] += 1
            self.counts['adjacent_timestamp_pairs'] += 1
        if t == self.previous:
            self.group_size += 1
        else:
            self.close_group(); self.group_size = 1
        self.previous = t

    def summary(self):
        groups = self.group_sizes.copy()
        if self.group_size: groups[self.group_size] += 1
        if sum(n*v for n,v in groups.items()) != self.counts['valid_shape_source_ms']:
            raise ValueError('source group denominator differs')
        return {'counts': dict(self.counts), 'adjacent_gap_histogram': dict(self.gaps),
            'consecutive_equal_source_ms_run_sizes': {str(k):v for k,v in sorted(groups.items())},
            'min_source_ms': self.first, 'max_source_ms': self.last,
            'timestamp_semantics_attested': False, 'decision_group_count': None}


class SourceProfile:
    def __init__(self):
        self.clocks = {}
        clocks = self.clocks
        class ObservedEngine(QuoteReconstructor):
            def __init__(self, asset, market):
                super().__init__(asset, market)
                self.clock_counts = ClockCounts()
                # Anonymous local key; no raw identifier goes into a report.
                clocks[hashlib.sha256(json.dumps([market,asset],sort_keys=True,separators=(',',':')).encode()).hexdigest()] = self.clock_counts
            def process(self, *args, **kwargs):
                rows = super().process(*args, **kwargs)
                for row in rows: self.clock_counts.observe(row)
                return rows
        self.population = PopulationProfile(ObservedEngine, max_entities=5000, max_total_levels=1000000)

    def consume(self, line, ordinal):
        record = json.loads(line)
        self.population.process(record, ordinal, hashlib.sha256(line).hexdigest())

    def summary(self):
        totals = {k: Counter() for k in ('counts','adjacent_gap_histogram','consecutive_equal_source_ms_run_sizes')}
        for c in self.clocks.values():
            s = c.summary()
            for k in totals: totals[k].update(s[k])
        return {'schema':'single_object_raw_profile_v1',
            'population': self.population.summary(include_entities=False),
            'source_clock_totals': {k:dict(v) for k,v in totals.items()},
            'source_clock_entities': [{'entity_sha256':k, **v.summary()} for k,v in sorted(self.clocks.items())],
            'clock_semantics_attested':False,'quiet_vs_outage_classified':False,
            'labels_computed':False,'features_computed':False,'source_admitted':False,
            'zero_change_rows_filtered':False,'independent_sample_size_estimated':False,
            'malformed_bbo_categories':'combined adapter count; malformed decimal and range errors not separated',
            'scope':'raw observation diagnostics only; no scientific row eligibility or QA pass'}
