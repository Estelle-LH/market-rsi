"""Label-free data and time-series gates. Never repair, normalize, or select."""
from dataclasses import asdict, dataclass
import hashlib
import json
import re

import numpy as np

from .feature_batch import validate_feature_batch
from .moments import moments


@dataclass(frozen=True)
class FeatureRule:
    rationale: str
    min_available_fraction: float = 1.0
    max_missing_fraction: float = 0.0
    max_zero_fraction: float = 1.0
    allow_constant: bool = False
    lower: float | None = None
    upper: float | None = None
    max_abs_step: float | None = None
    max_flat_run_ns: int | None = None
    max_half_shift_iqr: float | None = None
    max_session_shift_iqr: float | None = None
    max_scale_ratio: float | None = None


@dataclass(frozen=True)
class DataSpec:
    feature_names: tuple[str, ...]
    units: dict[str, str]
    expected_groups: tuple[tuple[str, str], ...]
    source_hashes: dict[str, str]
    clock_domain: str
    session_timezone: str
    rules: dict[str, FeatureRule]
    implementation_sha256: str
    allowed_unavailable_reasons: tuple[str, ...] = ()
    min_rows_per_group: int = 3


@dataclass(frozen=True)
class TimeSeriesSpec:
    max_gap_ns: int
    rationale: str
    event_lags: tuple[int, ...] = (1, 5, 20)
    elapsed_bins: int = 4
    max_pair_gap_ns: int | None = None


def json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                    separators=(',', ':')).encode()).hexdigest()


def batch_hash(batch):
    """Bind values, masks, order and schema; never accept a stale PASS receipt."""
    h = hashlib.sha256()
    for name in sorted(batch):
        value = batch[name]
        h.update(name.encode())
        if isinstance(value, np.ndarray):
            h.update(str(value.dtype).encode()); h.update(str(value.shape).encode())
            h.update(np.ascontiguousarray(value).tobytes())
        else:
            h.update(json.dumps(value, sort_keys=True, allow_nan=False).encode())
    return h.hexdigest()


def _issue(issues, code, detail, **context):
    issues.append(dict(code=code, detail=detail, **context))


def _validate_specs(data, series=None):
    names = data.feature_names
    if (not names or len(set(names)) != len(names)
            or set(data.units) != set(names) or set(data.rules) != set(names)):
        raise ValueError('explicit ordered features, units and per-feature rules required')
    if any(not isinstance(v, str) or not v.strip() for v in (*names, *data.units.values(), data.clock_domain, data.session_timezone)):
        raise ValueError('nonempty feature/unit/clock/timezone declarations required')
    groups = data.expected_groups
    if (not groups or len(set(groups)) != len(groups)
            or any(len(g) != 2 or any(not isinstance(v, str) or not v for v in g) for g in groups)):
        raise ValueError('explicit unique entity/session coverage required')
    if (not data.source_hashes or any(not isinstance(k, str) or not k
            or not isinstance(v, str) or not re.fullmatch('[0-9a-f]{64}', v)
            for k, v in data.source_hashes.items())):
        raise ValueError('verified source hash declarations required')
    if not isinstance(data.implementation_sha256, str) or not re.fullmatch('[0-9a-f]{64}', data.implementation_sha256):
        raise ValueError('implementation hash required')
    if type(data.min_rows_per_group) is not int or data.min_rows_per_group < 3:
        raise ValueError('min_rows_per_group must be an integer >= 3')
    if any(not isinstance(r, str) or not r.strip() for r in data.allowed_unavailable_reasons):
        raise ValueError('unavailability reason names cannot be empty')
    for rule in data.rules.values():
        if not isinstance(rule, FeatureRule) or not rule.rationale.strip():
            raise ValueError('each feature needs a frozen rule and rationale')
        if type(rule.allow_constant) is not bool:
            raise ValueError('allow_constant must be boolean')
        for x in (rule.min_available_fraction, rule.max_missing_fraction, rule.max_zero_fraction):
            if not np.isfinite(x) or not 0 <= x <= 1:
                raise ValueError('coverage fractions must be finite in [0,1]')
        for x in (rule.lower, rule.upper, rule.max_abs_step, rule.max_half_shift_iqr, rule.max_session_shift_iqr, rule.max_scale_ratio):
            if x is not None and not np.isfinite(x):
                raise ValueError('numeric limits must be finite')
        if rule.lower is not None and rule.upper is not None and rule.lower > rule.upper:
            raise ValueError('lower bound exceeds upper bound')
        for x in (rule.max_abs_step, rule.max_half_shift_iqr, rule.max_session_shift_iqr):
            if x is not None and x < 0:
                raise ValueError('step/drift limits must be nonnegative')
        if rule.max_scale_ratio is not None and rule.max_scale_ratio < 1:
            raise ValueError('maximum symmetric scale ratio must be >= 1')
        if rule.max_flat_run_ns is not None and (type(rule.max_flat_run_ns) is not int or rule.max_flat_run_ns < 0):
            raise ValueError('flat-run nanoseconds must be a nonnegative integer')
    if series is not None:
        if type(series.max_gap_ns) is not int or series.max_gap_ns <= 0 or not series.rationale.strip():
            raise ValueError('explicit positive gap limit and rationale required')
        if type(series.elapsed_bins) is not int or not 2 <= series.elapsed_bins <= 100:
            raise ValueError('elapsed_bins must be between 2 and 100')
        if series.max_pair_gap_ns is not None and (type(series.max_pair_gap_ns) is not int
                or not 0 < series.max_pair_gap_ns <= series.max_gap_ns):
            raise ValueError('pair gap must be positive and no larger than the data gap limit')
        if (not series.event_lags or len(set(series.event_lags)) != len(series.event_lags)
                or any(type(k) is not int or k < 1 for k in series.event_lags)):
            raise ValueError('explicit positive integer event lags required')


def _groups(batch):
    groups = {}
    for i, key in enumerate(zip(batch['entity_id'], batch['session_id'])):
        groups.setdefault(tuple(map(str, key)), []).append(i)
    return {key: np.asarray(rows, dtype=np.int64) for key, rows in groups.items()}


def _profile(values):
    # Counts always retain infinities; finite-only moments are not an imputation.
    return dict(rows=len(values), nan=int(np.isnan(values).sum()),
        positive_inf=int(np.isposinf(values).sum()), negative_inf=int(np.isneginf(values).sum()),
        finite_moments=moments(values[np.isfinite(values)]))


def check_data_level(batch, spec, observed, unavailable_reasons):
    """Inspect raw or transformed cells with the same contract; retain failures."""
    issues = []; profiles = []
    report = dict(level='data', status='FAIL', issues=issues, features=profiles,
                  repairs_performed=False, provenance='declarations_checked_adapter_must_verify_sources')
    try:
        _validate_specs(spec)
        report['spec_sha256'] = json_hash(asdict(spec))
        report['frozen_spec'] = asdict(spec)
        report['observed_metadata'] = observed.copy()
        report['unavailable_reasons_sha256'] = batch_hash({'reasons': unavailable_reasons})
        report['input_sha256'] = batch_hash(batch)
        for key in ('units', 'source_hashes', 'clock_domain', 'session_timezone', 'implementation_sha256'):
            if observed.get(key) != getattr(spec, key):
                _issue(issues, 'metadata_mismatch', key)
        if tuple(batch.get('feature_names', ())) != spec.feature_names:
            _issue(issues, 'feature_order', 'feature names/order differ from frozen spec')
        x = batch.get('values')
        # Preserve useful raw counts even when Inf or available-NaN fails the
        # existing stricter FeatureBatch contract.
        if isinstance(x, np.ndarray) and x.ndim == 2 and x.dtype.kind == 'f' and x.shape[1] == len(spec.feature_names):
            report['raw_numeric_counts'] = [dict(feature=name, **_profile(x[:, j]))
                for j, name in enumerate(spec.feature_names)]
            if all(isinstance(batch.get(k), np.ndarray) and batch[k].shape == (len(x),)
                   and batch[k].dtype.kind == 'U' for k in ('entity_id','session_id')):
                report['raw_partition_counts'] = [dict(entity=e, session=s, feature=name,
                    **_profile(x[ix, j])) for (e,s),ix in _groups(batch).items()
                    for j,name in enumerate(spec.feature_names)]
        validate_feature_batch(batch)
        reasons = unavailable_reasons
        if not isinstance(reasons, np.ndarray) or reasons.shape != x.shape or reasons.dtype.kind != 'U':
            raise ValueError('per-cell string unavailability reasons required')
        available = batch['available']
        if np.any(available & (reasons != '')):
            _issue(issues, 'availability_reason', 'available cells cannot have exclusion reasons')
        if np.any(~available & ~np.isin(reasons, spec.allowed_unavailable_reasons)):
            _issue(issues, 'unexplained_unavailable', 'unavailable cells require a predeclared reason')
        groups = _groups(batch)
        if set(groups) != set(spec.expected_groups):
            _issue(issues, 'coverage', 'missing or unexpected entity/session groups',
                missing=[list(k) for k in sorted(set(spec.expected_groups)-set(groups))],
                unexpected=[list(k) for k in sorted(set(groups)-set(spec.expected_groups))])
        for (entity, session), ix in groups.items():
            if len(ix) < spec.min_rows_per_group:
                _issue(issues, 'insufficient_rows', 'too few observed rows', entity=entity, session=session)
            for j, name in enumerate(spec.feature_names):
                rule = spec.rules[name]; values = x[ix, j]; mask = available[ix, j]
                selected = values[mask]; context = dict(entity=entity, session=session, feature=name)
                profile = dict(**context, **_profile(values), available_rows=int(mask.sum()),
                    available_moments=moments(selected),
                    unavailable_reasons={r: int((reasons[ix, j] == r).sum()) for r in spec.allowed_unavailable_reasons},
                    zero_fraction=float(np.mean(selected == 0)) if len(selected) else None)
                profiles.append(profile)
                if len(selected) < spec.min_rows_per_group or mask.mean() < rule.min_available_fraction:
                    _issue(issues, 'available_coverage', 'too few available inputs', **context)
                if np.isnan(values).mean() > rule.max_missing_fraction:
                    _issue(issues, 'missing_fraction', 'raw missing fraction exceeds limit', **context)
                if len(selected):
                    if profile['zero_fraction'] > rule.max_zero_fraction:
                        _issue(issues, 'zero_fraction', 'zero fraction exceeds declared limit', **context)
                    if np.ptp(selected) == 0 and not rule.allow_constant:
                        _issue(issues, 'constant', 'constant feature not explicitly permitted', **context)
                    if ((rule.lower is not None and np.any(selected < rule.lower))
                            or (rule.upper is not None and np.any(selected > rule.upper))):
                        _issue(issues, 'value_bounds', 'feature outside declared unit-aware bounds', **context)
        report['status'] = 'FAIL' if issues else 'PASS'
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, FloatingPointError) as exc:
        _issue(issues, 'invalid_input', str(exc))
    return report


def _longest_run(values, times, valid, connected, zero_only=False):
    count = best_count = 0; start = best_ns = 0
    for i in range(len(values)):
        if not valid[i] or (zero_only and values[i] != 0):
            count = 0; continue
        if count and connected[i-1] and values[i] == values[i-1]:
            count += 1
        else:
            count = 1; start = int(times[i])
        best_count = max(best_count, count)
        best_ns = max(best_ns, int(times[i])-start)
    return dict(events=best_count, elapsed_ns=best_ns)


def _distribution(values):
    if not len(values):
        return None
    q25, median, q75 = np.quantile(values, [.25,.5,.75])
    return dict(median=float(median), iqr=float(q75-q25), std=float(np.std(values)))


def _summary_shift(a, b):
    if a is None or b is None:
        return dict(median_change=None, prior_iqr=None, shift_iqr=None, estimable=False)
    scale = a['iqr']; delta = b['median']-a['median']
    scale_ratio = b['std']/a['std'] if a['std'] > 0 else (1. if b['std'] == 0 else None)
    return dict(median_change=delta, prior_iqr=scale,
                shift_iqr=abs(delta)/scale if scale > 0 else (0. if delta == 0 else None),
                std_ratio=scale_ratio,
                estimable=bool(scale > 0 or delta == 0))


def _shift(a, b):
    return _summary_shift(_distribution(a), _distribution(b))


def check_time_series_level(batch, data_spec, series_spec):
    issues = []; features = []; cross_session = []
    report = dict(level='time_series', status='FAIL', issues=issues, features=features,
        cross_session=cross_session, event_lags_are_not_time_horizons=True,
        resampled=False, leakage_claim='availability_contract_only_not_kernel_proof')
    try:
        _validate_specs(data_spec, series_spec); validate_feature_batch(batch)
        if tuple(batch['feature_names']) != data_spec.feature_names:
            raise ValueError('time-series features differ from frozen specification')
        report['spec_sha256'] = json_hash(asdict(series_spec))
        report['frozen_spec'] = asdict(series_spec)
        history = {}
        for (entity, session), ix in _groups(batch).items():
            ts = batch['decision_ns'][ix]; gaps = np.diff(ts)
            if np.any(gaps > series_spec.max_gap_ns):
                _issue(issues, 'time_gap', 'observed gap exceeds declared limit', entity=entity, session=session)
            for j, name in enumerate(data_spec.feature_names):
                x = batch['values'][ix, j]; valid = batch['available'][ix, j] & np.isfinite(x)
                pair_gap = series_spec.max_pair_gap_ns or series_spec.max_gap_ns
                connected = valid[:-1] & valid[1:] & (gaps <= pair_gap)
                selected = x[valid]; context = dict(entity=entity, session=session, feature=name)
                if len(selected) < data_spec.min_rows_per_group:
                    _issue(issues, 'insufficient_series', 'too few usable observations', **context)
                    continue
                with np.errstate(over='raise', invalid='raise', divide='raise'):
                    steps = x[1:][connected]-x[:-1][connected]
                    flat = _longest_run(x, ts, valid, connected)
                    zero = _longest_run(x, ts, valid, connected, True)
                    nonzero = connected & (x[:-1] != 0) & (x[1:] != 0)
                    flips = int(((np.sign(x[:-1]) != np.sign(x[1:])) & nonzero).sum())
                    std = float(np.std(selected))
                    mean = float(np.mean(selected)); denominator = float(np.sum((selected-mean)**2))
                    breaks = np.r_[0, np.cumsum(~connected)]
                    acf = []
                    for lag in series_spec.event_lags:
                        pairs = (valid[:-lag] & valid[lag:] & (breaks[lag:]-breaks[:-lag] == 0)) if lag < len(x) else np.zeros(0, dtype=bool)
                        value = float(np.sum((x[:-lag][pairs]-mean)*(x[lag:][pairs]-mean))/denominator) if pairs.any() and denominator > 0 else None
                        acf.append(dict(lag_events=lag, pairs=int(pairs.sum()), autocorrelation=value))
                    span = int(ts[-1])-int(ts[0])+1
                    width = max(1, (span+series_spec.elapsed_bins-1)//series_spec.elapsed_bins)
                    bucket = ((ts-ts[0])//width).astype(int)
                    bins = [dict(bin=k, **moments(x[(bucket == k) & valid])) for k in range(series_spec.elapsed_bins)]
                    midpoint = int(ts[0])+(int(ts[-1])-int(ts[0]))//2
                    drift = _shift(x[valid & (ts <= midpoint)], x[valid & (ts > midpoint)])
                    row = dict(**context, rows=len(x), available_rows=len(selected),
                        max_gap_ns=int(gaps.max(initial=0)), flat_run=flat, zero_run=zero,
                        pairing_gap_limit_ns=pair_gap, gaps_excluded_from_pairs=int((gaps > pair_gap).sum()),
                        adjacent_pairs=int(connected.sum()), sign_flips=flips,
                        nonzero_adjacent_pairs=int(nonzero.sum()),
                        sign_flip_fraction=flips/int(nonzero.sum()) if nonzero.any() else None,
                        max_abs_step=float(np.max(np.abs(steps))) if len(steps) else None,
                        roughness_std_ratio=float(np.std(steps)/std) if len(steps) and std > 0 else None,
                        event_acf=acf, elapsed_bins=bins, half_session_drift=drift)
                features.append(row); rule = data_spec.rules[name]
                if rule.max_abs_step is not None and len(steps) and row['max_abs_step'] > rule.max_abs_step:
                    _issue(issues, 'jump', 'adjacent step exceeds declared limit', **context)
                if rule.max_flat_run_ns is not None and flat['elapsed_ns'] > rule.max_flat_run_ns:
                    _issue(issues, 'flat_run', 'flat run exceeds declared duration', **context)
                if rule.max_half_shift_iqr is not None and (not drift['estimable'] or drift['shift_iqr'] > rule.max_half_shift_iqr):
                    _issue(issues, 'half_session_drift', 'shift not estimable or exceeds declared limit', **context)
                # Keep only summary statistics across sessions, not a second
                # full copy of every feature row in a large panel.
                history.setdefault((entity, name), []).append((int(ts[0]), int(ts[-1]), session, _distribution(selected)))
        for (entity, name), sessions in history.items():
            # Only diagnostic session-summary ordering, never data row sorting.
            sessions.sort(key=lambda v: v[0])
            for before, after in zip(sessions, sessions[1:]):
                drift = _summary_shift(before[3], after[3])
                row = dict(entity=entity, feature=name, from_session=before[2], to_session=after[2], **drift)
                cross_session.append(row)
                if before[1] >= after[0]:
                    _issue(issues, 'overlapping_sessions', 'entity sessions overlap; drift comparison invalid', entity=entity)
                limit = data_spec.rules[name].max_session_shift_iqr
                if limit is not None and (not drift['estimable'] or drift['shift_iqr'] > limit):
                    _issue(issues, 'cross_session_drift', 'shift not estimable or exceeds declared limit', entity=entity, feature=name)
                scale_limit = data_spec.rules[name].max_scale_ratio
                if scale_limit is not None and (drift['std_ratio'] is None
                        or not 1/scale_limit <= drift['std_ratio'] <= scale_limit):
                    _issue(issues, 'cross_session_scale', 'scale ratio exceeds declared limit', entity=entity, feature=name)
        # Reject overflow/non-JSON numeric evidence rather than write NaNs.
        json.dumps(report, allow_nan=False)
        report['status'] = 'FAIL' if issues else 'PASS'
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, FloatingPointError) as exc:
        _issue(issues, 'invalid_series', str(exc))
    return report
