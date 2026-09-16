"""Additive, source-reported direction fields; does not alter frozen v1 caches.

These are observations, not a prescribed signal or proof of historical trading
availability. Missing/invalid fields are absent, never silently coerced to zero.
The collector snapshot is evidence about a possible implementation, not proof
that this exact version produced every historical row.
"""
import math
from pathlib import PurePosixPath

from historical_source_contract import (_finite, _ms, physical_reference, project,
    require_causal_feature)
from market_rsi import digest


PUBLISHER_COMMIT = '6e6cc240f32ab9fd2f8fa602bd0aba823b24bfee'
MAPPING_ASSUMPTION = 'publisher_snapshot_token_mapping_as_static_research_proxy'
MAKER = 'reported_is_buyer_maker'
QUOTE_VOLUME = 'reported_quote_volume'
UP = 'publisher_up_token'
DOWN = 'publisher_down_token'


def direction_contract():
    value = {
        'schema': 'historical_reported_direction_contract_v1',
        'publisher_commit': PUBLISHER_COMMIT,
        'binance_fields': [MAKER, QUOTE_VOLUME],
        'polymarket_fields': [UP, DOWN],
        'binance_stream_in_pinned_code': 'btcusdt@aggTrade',
        'trade_id_in_pinned_code': 'a: aggregate trade ID, not individual execution ID',
        'maker_definition': 'Reported 1 means buyer maker; 0 means buyer not maker OR upstream default.',
        'maker_default_caveat': 'Pinned collector uses as_bool().unwrap_or(false); stored 0 cannot disambiguate an absent/malformed upstream flag.',
        'quote_volume_definition': 'Publisher price * quantity; USDT in pinned BTCUSDT collector.',
        'orientation_definition': 'Publisher UP/DOWN token role, not a future outcome or verified settlement.',
        'mapping_assumption_required': MAPPING_ASSUMPTION,
        'metadata_clock': 'first_seen_ms; mapping history/deployed version are unverified',
        'historical_deployed_collector_verified': False,
        'raw_upstream_envelopes_available': False,
        'missing_or_invalid': 'absent value with field-specific flags; cache may encode NaN, never zero',
        'same_receipt_ties': 'agree for this field or remain ambiguous; no arbitrary tie winner',
        'training_admitted': False, 'new_signal_formula_selected': False,
        'aggregation_windows_selected': False, 'frozen_cache_modified': False,
    }
    return {**value, 'contract_sha256': digest(value)}


def _stream(item, expected):
    if PurePosixPath(item['path']).parts[1] != expected:
        raise ValueError('exact source stream required for reported direction')


def project_reported_trade(row, item, ordinal):
    """Attach two raw fields to the original projection, preserving its checks."""
    _stream(item, 'binance_trades')
    record = project(row, item, ordinal)
    flags = {MAKER: [], QUOTE_VOLUME: []}
    maker = row.get('is_buyer_maker')
    if type(maker) is not int or maker not in (0, 1):
        flags[MAKER].append('missing_or_invalid_recorded_maker_flag')
    else:
        record['values'][MAKER] = maker
    volume, price, quantity = (row.get(k) for k in ('quote_volume', 'price', 'quantity'))
    if not (_finite(volume) and volume >= 0):
        flags[QUOTE_VOLUME].append('missing_or_invalid_recorded_quote_volume')
    elif not (_finite(price) and price > 0 and _finite(quantity) and quantity >= 0):
        flags[QUOTE_VOLUME].append('invalid_trade_price_or_quantity')
    elif not math.isclose(volume, price * quantity, rel_tol=1e-10, abs_tol=1e-8):
        flags[QUOTE_VOLUME].append('quote_volume_disagrees_with_price_times_quantity')
    else:
        record['values'][QUOTE_VOLUME] = float(volume)
    record.update(direction_field_flags=flags, direction_contract_sha256=direction_contract()['contract_sha256'],
        raw_reported_maker=maker, maker_upstream_default_cannot_be_disambiguated=True,
        individual_execution_count_verified=False)
    return record


def project_reported_orientation(row, item, ordinal, metadata, metadata_item, metadata_ordinal):
    """Require row role and exact token mapping to agree; never relabel a row.

The recorded mapping is only exposed after its recorded first-seen clock. No
question, up/down price, last-seen clock or settlement field becomes a feature.
"""
    _stream(item, 'polymarket_ticks_ms'); _stream(metadata_item, 'market_meta')
    meta_ref = physical_reference(metadata_item, metadata_ordinal)
    market = metadata.get('market_slug')
    up, down = metadata.get('up_token_id'), metadata.get('down_token_id')
    tokens_ok = (isinstance(market, str) and bool(market) and isinstance(up, str)
                 and bool(up) and isinstance(down, str) and bool(down) and up != down)
    record = project(row, item, ordinal, metadata={market: {up, down}} if tokens_ok else {})
    flags = []
    side = row.get('side_label')
    role = side.upper() if isinstance(side, str) else None
    if role not in ('UP', 'DOWN'):
        flags.append('missing_or_invalid_publisher_side_label')
    if not tokens_ok or row.get('market_slug') != market or row.get('asset_id') not in (up, down):
        flags.append('publisher_token_mapping_mismatch_or_invalid')
    elif role in ('UP', 'DOWN') and row['asset_id'] != (up if role == 'UP' else down):
        flags.append('publisher_side_label_token_mapping_disagreement')
    try:
        first_seen = _ms(metadata.get('first_seen_ms'))
    except ValueError:
        first_seen = None; flags.append('missing_or_invalid_mapping_first_seen_clock')
    if not flags:
        record['values'].update({UP: int(role == 'UP'), DOWN: int(role == 'DOWN')})
    record.update(direction_field_flags={UP: list(flags), DOWN: list(flags)},
        direction_contract_sha256=direction_contract()['contract_sha256'],
        metadata_source=meta_ref, metadata_recorded_first_seen_ms=first_seen,
        metadata_mapping_assumption_required=MAPPING_ASSUMPTION,
        raw_reported_side_label=side, settlement_outcome_verified=False)
    return record


def require_reported_direction(record, field, decision_ms, *, max_age_ms, clock_assumption,
                               mapping_assumption=None):
    """Apply source, field, receipt and (for token roles) metadata time gates."""
    if record.get('direction_contract_sha256') != direction_contract()['contract_sha256']:
        raise ValueError('reported-direction semantic contract mismatch')
    allowed = {'binance_trades': (MAKER, QUOTE_VOLUME), 'polymarket_ticks_ms': (UP, DOWN)}
    if field not in allowed.get(record['stream'], ()):
        raise ValueError('no direction field alias or fabricated flow')
    if record['direction_field_flags'][field]:
        raise ValueError('flagged direction field: ' + ','.join(record['direction_field_flags'][field]))
    if field in (UP, DOWN):
        if mapping_assumption != MAPPING_ASSUMPTION:
            raise ValueError('explicit publisher mapping assumption required')
        if record['metadata_recorded_first_seen_ms'] > decision_ms:
            raise ValueError('publisher token mapping not yet recorded')
    return require_causal_feature(record, field, decision_ms, max_age_ms=max_age_ms,
                                  clock_assumption=clock_assumption)


def latest_reported_direction(records, field, decision_ms, *, max_age_ms, clock_assumption):
    """Only for a bounded Binance group; a bad latest row cannot revive an older one."""
    _ms(decision_ms)
    if len(records) > 100_000 or any(r['stream'] != 'binance_trades' for r in records):
        raise ValueError('bounded Binance-only replay group required')
    visible = [r for r in records if r['recorded_available_ms'] <= decision_ms]
    if not visible:
        return {'value': None, 'reason': 'no_visible_observation', 'sources': []}
    latest = max(r['recorded_available_ms'] for r in visible)
    group = [r for r in visible if r['recorded_available_ms'] == latest]
    sources = [r['source']['physical_row_id'] for r in group]
    try:
        values = [require_reported_direction(r, field, decision_ms, max_age_ms=max_age_ms,
                    clock_assumption=clock_assumption) for r in group]
    except ValueError as exc:
        return {'value': None, 'reason': str(exc), 'sources': sources}
    if len(set(values)) != 1:
        return {'value': None, 'reason': 'conflicting_same_receipt_direction_values', 'sources': sources}
    return {'value': values[0], 'reason': 'publisher_reported_field_only_not_verified_trade_direction',
            'sources': sources, 'available_ms': latest}
