"""Mandatory raw + transformed data/series checks at the fit/score boundary."""
from dataclasses import dataclass
import copy
import json
from pathlib import Path
import re

import numpy as np

from .quality_checks import (
    DataSpec, TimeSeriesSpec, batch_hash, check_data_level,
    check_time_series_level, json_hash,
)


@dataclass(frozen=True)
class PanelInput:
    batch: dict
    spec: DataSpec
    observed: dict
    unavailable_reasons: np.ndarray


class QualityGateError(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__('data/time-series quality gate failed; operation not invoked')


def quality_report(*, raw, transformed, time_series, lineage, adapter_evidence):
    """Run both levels even on a failed panel; never convert failure to a PASS."""
    report = dict(schema='research_quality_gate_v1', data_level={}, time_series_level={},
                  boundary_issues=[], status='FAIL', feature_selection=False,
                  alpha_or_leakage_clearance=False)
    for name, panel in [('raw', raw), ('transformed', transformed)]:
        report['data_level'][name] = check_data_level(
            panel.batch, panel.spec, panel.observed, panel.unavailable_reasons)
        report['time_series_level'][name] = check_time_series_level(
            panel.batch, panel.spec, time_series)
    issues = report['boundary_issues']
    try:
        if not isinstance(time_series, TimeSeriesSpec):
            raise ValueError('explicit time-series specification required')
        for key in ('row_id', 'entity_id', 'session_id', 'decision_ns', 'event_ordinal'):
            if not np.array_equal(raw.batch[key], transformed.batch[key]):
                raise ValueError(f'raw/transformed {key} differs; no silent row change')
        names = transformed.batch['feature_names']
        if not isinstance(lineage, dict) or set(lineage) != set(names):
            raise ValueError('explicit source-feature lineage required for every transformed feature')
        for j, name in enumerate(names):
            parents = lineage[name]
            if (not isinstance(parents, (tuple, list)) or not parents
                    or len(set(parents)) != len(parents)
                    or any(v not in raw.batch['feature_names'] for v in parents)):
                raise ValueError(f'invalid source features for {name}')
            indices = [raw.batch['feature_names'].index(v) for v in parents]
            ready = raw.batch['available'][:, indices].all(axis=1)
            if np.any(transformed.batch['available'][:, j] & ~ready):
                raise ValueError('transformation made unavailable input available; no hidden filling')
            pt = raw.batch['feature_available_ns'][:, indices]
            po = raw.batch['feature_available_ordinal'][:, indices]
            latest = pt.max(axis=1)
            latest_order = np.where(pt == latest[:, None], po, -1).max(axis=1)
            output_t = transformed.batch['feature_available_ns'][:, j]
            output_o = transformed.batch['feature_available_ordinal'][:, j]
            premature = (output_t < latest) | ((output_t == latest) & (output_o < latest_order))
            if np.any(transformed.batch['available'][:, j] & premature):
                raise ValueError('transformed value declared available before its dependencies')
        if not isinstance(adapter_evidence, dict) or set(adapter_evidence) != {'raw', 'transformed'}:
            raise ValueError('raw and transformed adapter evidence required')
        for name, panel in [('raw', raw), ('transformed', transformed)]:
            evidence = adapter_evidence[name]
            if evidence.get('implementation_sha256') != panel.spec.implementation_sha256:
                raise ValueError(f'{name} adapter evidence is for another implementation')
            for check in ('source_units_clock', 'kernel_future_mutation', 'preprocessing_parity'):
                item = evidence.get(check, {})
                if (item.get('status') != 'PASS' or not isinstance(item.get('receipt_sha256'), str)
                        or not re.fullmatch('[0-9a-f]{64}', item['receipt_sha256'])):
                    raise ValueError(f'{name}: missing or failed {check} adapter evidence')
        report['adapter_evidence'] = copy.deepcopy(adapter_evidence)
        report['lineage'] = copy.deepcopy(lineage)
        report['input_fingerprints'] = {name: batch_hash(p.batch)
                                        for name, p in [('raw', raw), ('transformed', transformed)]}
    except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
        issues.append(dict(code='research_boundary', detail=str(exc)))
    passed = not issues and all(
        report[level][name]['status'] == 'PASS'
        for level in ('data_level', 'time_series_level') for name in ('raw', 'transformed'))
    report['status'] = 'PASS' if passed else 'FAIL'
    report['report_sha256'] = json_hash(report)
    return report


def persist_quality_report(report, directory):
    """New run directory only; write split reports and complete manifest last.

    Consumer-only outputs may include sensitive feature names/statistics. Never
    publish them to the generic shared repo. Existing receipts are not replaced.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    payloads = {'data_check.json': report['data_level'],
                'time_series_check.json': report['time_series_level'],
                'quality_gate.json': report}
    if any((directory/name).exists() for name in payloads):
        raise FileExistsError('quality receipts already exist; use a new run directory')
    for name, payload in payloads.items():
        with (directory/name).open('x') as stream:
            json.dump(payload, stream, indent=2, allow_nan=False)
            stream.write('\n')


def guarded_research(*, stage, raw, transformed, time_series, lineage,
                     adapter_evidence, persist, operation):
    """Check fresh snapshots, persist PASS/FAIL, then invoke fit/score or raise.

    The callback must use its provided snapshot. This is a scientific execution
    contract, not a sandbox against malicious callbacks or unrelated legacy code.
    """
    if stage not in ('fit', 'score'):
        raise ValueError('research stage must be fit or score')
    if not callable(persist) or not callable(operation):
        raise ValueError('receipt persistence and checked-input callback required')
    raw, transformed = copy.deepcopy((raw, transformed))
    for panel in (raw, transformed):
        for value in panel.batch.values():
            if isinstance(value, np.ndarray):
                value.flags.writeable = False
    report = quality_report(raw=raw, transformed=transformed, time_series=time_series,
                            lineage=lineage, adapter_evidence=adapter_evidence)
    report['stage'] = stage
    # Rebind the stage in the final receipt rather than retain the earlier hash.
    report.pop('report_sha256')
    report['report_sha256'] = json_hash(report)
    persist(copy.deepcopy(report))
    if report['status'] != 'PASS':
        raise QualityGateError(report)
    checked = transformed.batch
    value = operation(checked)
    if batch_hash(checked) != report['input_fingerprints']['transformed']:
        raise RuntimeError('operation mutated checked input snapshot')
    return value, report
