"""Add recorded-event leaves without changing any earlier feature engine/hash."""
from pathlib import Path

import numpy as np

import historical_feature_composition as old
import historical_trade_windows as windows
from market_rsi import digest, file_hash, identifier


def contains_recorded(spec):
    if not isinstance(spec, dict): return False
    if set(spec) == windows.SPEC_FIELDS: return True
    return set(spec) == old.COMPOSITION_FIELDS and isinstance(spec.get('operands'), list) and any(
        contains_recorded(s) for s in spec['operands'])


def validate_feature(spec, names, cadence_ms):
    if not contains_recorded(spec):
        return old.validate_feature(spec, names, cadence_ms)
    leaves = 0

    def walk(node, depth):
        nonlocal leaves
        if not isinstance(node, dict): raise ValueError('explicit feature node required')
        if set(node) == old.COMPOSITION_FIELDS:
            identifier(node['name'])
            if depth >= old.MAX_DEPTH or node['operator'] not in old.OPERATORS:
                raise ValueError('bounded supported composition required')
            parts = node['operands']
            if (not isinstance(parts, list) or not 2 <= len(parts) <= 4
                    or node['operator'] == 'difference' and len(parts) != 2):
                raise ValueError('sum/product require2..4 operands; difference exactly2')
            for part in parts: walk(part, depth+1)
        else:
            leaves += 1
            if leaves > old.MAX_LEAVES: raise ValueError('at most8 feature leaves')
            if set(node) == windows.SPEC_FIELDS: windows.validate_spec(node)
            else: old.validate_feature(node, names, cadence_ms)
        return node

    return walk(spec, 0)


def feature_engine_sha256(spec):
    if not contains_recorded(spec): return old.feature_engine_sha256(spec)
    return digest({'recorded_dispatch': file_hash(Path(__file__)),
                   'windows': file_hash(Path(windows.__file__)),
                   'composition': file_hash(Path(old.__file__)),
                   'primitive': file_hash(Path(old.primitive.__file__))})


def derive(entity, decision_ms, values, names, *, spec, cadence_ms, recorded_events=None):
    validate_feature(spec, names, cadence_ms)
    if not contains_recorded(spec):
        return old.derive(entity, decision_ms, values, names, spec=spec, cadence_ms=cadence_ms)
    if not isinstance(recorded_events, windows.RecordedTradeWindows):
        raise ValueError('recorded-event capability not attached to this workspace')
    if set(spec) == windows.SPEC_FIELDS:
        return recorded_events.derive(decision_ms, spec=spec)
    parts = [derive(entity, decision_ms, values, names, spec=p, cadence_ms=cadence_ms,
                    recorded_events=recorded_events) for p in spec['operands']]
    result = parts[0]['values'].copy()
    with np.errstate(invalid='ignore', over='ignore'):
        for part in parts[1:]:
            if spec['operator'] == 'sum': result += part['values']
            elif spec['operator'] == 'difference': result -= part['values']
            else: result *= part['values']
    valid = np.logical_and.reduce([p['available'] for p in parts])
    if np.any(np.isinf(result)) or np.any(valid & ~np.isfinite(result)):
        raise ValueError('invalid or overflowing feature composition; no clipping')
    result[~valid] = np.nan
    return {'values': result, 'available': valid,
            'observations_used': np.minimum.reduce([p['observations_used'] for p in parts]),
            'feature_available_ms': np.maximum.reduce([p['feature_available_ms'] for p in parts]),
            'spec': spec, 'full_population_rows': len(decision_ms),
            'future_labels_used': False, 'normalizer_fitted': False,
            'exchange_completeness_verified': False}
