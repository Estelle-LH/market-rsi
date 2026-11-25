"""Source-bound outer window only; role, forecast and budget caps are unchanged."""
from datetime import datetime, timedelta, timezone
import math
import re

from earnings_night_budget import utc_epoch
from edgar_forecast_budget import BudgetStop

GRACE_SECONDS = 60


def minutes(runtime):
    """Missing means the historical90;180 is one amended-budget decision only."""
    if type(runtime) is not dict:
        raise ValueError('Exact population window runtime required')
    value = runtime.get('window_minutes', 90)
    if type(value) is not int or value not in (90, 180):
        raise ValueError('Population window must be an exact90/180 integer')
    if value == 180:
        grant, companies = runtime.get('budget_amendment'), runtime.get('companies')
        if (type(grant) is not dict or set(grant) != {'path', 'sha256'}
                or type(grant['path']) is not str or not grant['path']
                or type(grant['sha256']) is not str or re.fullmatch('[0-9a-f]{64}', grant['sha256']) is None
                or type(companies) is not list or len(companies) != 1):
            raise ValueError('180-minute window requires existing budget amendment and one decision')
    return value


def bounds(start, runtime):
    """Fresh preparation only; no runtime/clock renewal at admission or replay."""
    if not isinstance(start, datetime) or start.tzinfo is None:
        raise ValueError('Aware original preparation time required')
    cutoff = start.astimezone(timezone.utc).replace(microsecond=0) + timedelta(minutes=minutes(runtime))
    utc = lambda value: value.strftime('%Y-%m-%dT%H:%M:%SZ')
    return dict(cutoff_utc=utc(cutoff), deadline_utc=utc(cutoff + timedelta(seconds=GRACE_SECONDS)))


def start_utc(runtime):
    """Reconstruct the same original Native start without consulting wall time."""
    cutoff = datetime.fromtimestamp(utc_epoch(runtime['cutoff_utc']), timezone.utc)
    return (cutoff - timedelta(minutes=minutes(runtime))).strftime('%Y-%m-%dT%H:%M:%SZ')


def check(runtime, now_epoch):
    duration = minutes(runtime) * 60
    cutoff, deadline = utc_epoch(runtime['cutoff_utc']), utc_epoch(runtime['deadline_utc'])
    if (type(now_epoch) not in (int, float) or not math.isfinite(now_epoch)
            or not now_epoch < cutoff <= now_epoch + duration
            or not cutoff <= deadline <= cutoff + GRACE_SECONDS):
        raise BudgetStop('Population bound send window or terminal grace invalid')
