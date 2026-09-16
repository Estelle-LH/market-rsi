"""Additive, bounded composition of unchanged causal feature primitives.

The researcher chooses every operand and operation. This exposes capabilities,
not a default direction formula. No labels, fitted coefficients or imputation.
"""
from pathlib import Path
import numpy as np

import historical_grid_features as primitive
from market_rsi import digest, file_hash, identifier

COMPOSITION_FIELDS = {'name', 'operator', 'operands'}
OPERATORS = {'sum', 'difference', 'product'}
MAX_DEPTH = 3
MAX_LEAVES = 8


def validate_feature(spec, names, cadence_ms):
    leaves = 0

    def walk(node, depth):
        nonlocal leaves
        if not isinstance(node, dict):
            raise ValueError('feature node must be an explicit object')
        if set(node) != COMPOSITION_FIELDS:
            leaves += 1
            if leaves > MAX_LEAVES:
                raise ValueError('at most8 primitive operands per composed feature')
            return primitive.validate_feature(node, names, cadence_ms)
        identifier(node['name'])
        if depth >= MAX_DEPTH or node['operator'] not in OPERATORS:
            raise ValueError('bounded supported composition depth/operator required')
        operands = node['operands']
        if (not isinstance(operands, list) or not 2 <= len(operands) <= 4
                or node['operator'] == 'difference' and len(operands) != 2):
            raise ValueError('sum/product require2..4 operands; difference exactly2')
        for operand in operands:
            walk(operand, depth + 1)
        return node

    return walk(spec, 0)


def feature_engine_sha256(spec):
    if isinstance(spec, dict) and set(spec) == COMPOSITION_FIELDS:
        return digest({'composition': file_hash(Path(__file__)),
                       'primitive': file_hash(Path(primitive.__file__))})
    return file_hash(Path(primitive.__file__))


def derive(entity, decision_ms, values, names, *, spec, cadence_ms):
    validate_feature(spec, names, cadence_ms)
    if set(spec) != COMPOSITION_FIELDS:
        # Preserve every existing primitive's bytes and missingness unchanged.
        return primitive.derive(entity, decision_ms, values, names, spec=spec, cadence_ms=cadence_ms)
    parts = [derive(entity, decision_ms, values, names, spec=s, cadence_ms=cadence_ms)
             for s in spec['operands']]
    result = parts[0]['values'].copy()
    with np.errstate(over='ignore', invalid='ignore'):
        for part in parts[1:]:
            if spec['operator'] == 'sum': result += part['values']
            elif spec['operator'] == 'difference': result -= part['values']
            else: result *= part['values']
    if np.any(np.isinf(result)):
        raise ValueError('composition overflow; no clipping or saturation')
    valid = np.logical_and.reduce([p['available'] for p in parts])
    if np.any(valid & ~np.isfinite(result)):
        raise ValueError('invalid arithmetic on finite operands')
    result[~valid] = np.nan
    return {'values': result, 'available': np.isfinite(result),
            'observations_used': np.minimum.reduce([p['observations_used'] for p in parts]),
            'feature_available_ms': np.maximum.reduce([p['feature_available_ms'] for p in parts]),
            'spec': spec, 'full_population_rows': len(decision_ms),
            'future_labels_used': False, 'normalizer_fitted': False,
            'operand_availability_rule': 'all operands required; missing remains missing, including zero times missing',
            'primitive_engine_sha256': file_hash(Path(primitive.__file__))}
