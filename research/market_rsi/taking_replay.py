"""Explicit, conservative taking-simulation arithmetic; no live orders/CLI.

Only fully observed, independently admitted windows may eventually be scored.
This module does NOT establish that admission. Current tests use synthetic data.
Orders reserve worst-case cash at decision time. Later fills, exits and PnL may
affect another decision only after their timestamp, never through hindsight.
No passive fills, queue priority, settlement labels or actual execution are
inferred from changing quotes. The fee rounding here is an explicit simulation
approximation, not an assertion about the exchange's precise cash rounding.
"""
from __future__ import annotations

import bisect
import heapq
import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING

from label_materializer import LabelPolicy
from market_scoring import NumericScoreSpec, circular_interval, numeric_rows, utc_date
from prediction_stream import finite, fingerprint


def amount(value):
    if not isinstance(value, str):
        raise ValueError("decimal currency/rate strings required")
    result = Decimal(value)
    if not result.is_finite() or result < 0:
        raise ValueError("finite nonnegative amount required")
    return result


@dataclass(frozen=True)
class FeeRule:
    market_id: str
    coefficient: str
    quantum_usd: str
    valid_from_ms: int
    valid_until_ms: int
    source_sha256: str
    rounding: str

    def __post_init__(self):
        if not isinstance(self.market_id, str) or not self.market_id:
            raise ValueError("explicit market fee assignment required; no default fallback")
        if not 0 <= amount(self.coefficient) <= 1 or not 0 < amount(self.quantum_usd) <= 1:
            raise ValueError("invalid fee coefficient/rounding quantum")
        if (type(self.valid_from_ms) is not int or type(self.valid_until_ms) is not int
                or not 0 <= self.valid_from_ms < self.valid_until_ms):
            raise ValueError("historical fee validity interval required")
        if (not isinstance(self.source_sha256, str) or len(self.source_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.source_sha256)):
            raise ValueError("fee-source commitment required; syntax is not provenance proof")
        if self.rounding != "raw_fee_ceil_declared_approximation":
            raise ValueError("only explicitly declared approximate fee rounding is implemented")

    def round_up(self, value):
        quantum = amount(self.quantum_usd)
        return (value / quantum).to_integral_value(rounding=ROUND_CEILING) * quantum

    def fee(self, quantity, price):
        if type(quantity) is not int or quantity <= 0 or not Decimal(0) <= price <= Decimal(1):
            raise ValueError("positive integer quantity and bounded price required")
        return self.round_up(amount(self.coefficient) * quantity * price * (1 - price))

    def worst_cash(self, quantity):
        # Fully collateralized long YES or long NO, plus both maximum fees.
        return Decimal(quantity) + 2 * self.round_up(amount(self.coefficient) * quantity / 4)


@dataclass(frozen=True)
class TakingPolicy:
    contracts: int
    threshold: str
    adverse_slippage_per_leg: str
    initial_cash: str
    max_open_orders: int
    fees: tuple[FeeRule, ...]
    label_policy: LabelPolicy

    def __post_init__(self):
        if type(self.contracts) is not int or not 1 <= self.contracts <= 100:
            raise ValueError("bounded fixed integer trade size required")
        if not 0 <= amount(self.threshold) <= 1 or not 0 <= amount(self.adverse_slippage_per_leg) < 1:
            raise ValueError("invalid threshold/slippage")
        if amount(self.initial_cash) <= 0 or self.max_open_orders != 1 or type(self.max_open_orders) is not int:
            raise ValueError("positive cash and one global pending/open order in this first simulator")
        if (not isinstance(self.fees, tuple) or not self.fees or any(not isinstance(f, FeeRule) for f in self.fees)
                or len({f.market_id for f in self.fees}) != len(self.fees)
                or not isinstance(self.label_policy, LabelPolicy)):
            raise ValueError("immutable unique market fee rules and label policy required")


def validate_inputs(rows, predictions, score_spec, policy, unresolved_windows):
    if not isinstance(score_spec, NumericScoreSpec) or score_spec.target != "mid_change":
        raise ValueError("this direction policy requires frozen signed mid-change predictions")
    if not isinstance(policy, TakingPolicy):
        raise ValueError("explicit taking policy required")
    if type(unresolved_windows) is not int or unresolved_windows != 0:
        raise ValueError("unresolved/censored windows cannot disappear from simulated PnL")
    checked = numeric_rows(rows, score_spec)
    session_dates = [date.fromisoformat(s) for s in score_spec.sessions]
    if any(b - a != timedelta(days=1) for a, b in zip(session_dates, session_dates[1:])):
        raise ValueError("taking accounting cannot silently fill missing evaluation dates")
    if not isinstance(predictions, dict) or set(predictions) != {r["row_id"] for r in checked}:
        raise ValueError("complete identical prediction mask required")
    if any(not score_spec.prediction_min <= finite(p) <= score_spec.prediction_max for p in predictions.values()):
        raise ValueError("prediction outside declared bounds")
    fees = {f.market_id: f for f in policy.fees}
    if set(fees) != {r["market_id"] for r in rows}:
        raise ValueError("every admitted market needs its own frozen fee rule")
    lp = policy.label_policy
    for r in rows:
        first = r["decision_ms"] + lp.latency_ms
        end = first + lp.horizon_ms
        if not (first <= r["entry_ms"] <= first + lp.max_entry_lateness_ms
                and end <= r["label_end_ms"] <= end + lp.max_label_lateness_ms):
            raise ValueError("row does not match frozen latency/horizon/lateness")
        fee = fees[r["market_id"]]
        if not fee.valid_from_ms <= r["decision_ms"] <= r["label_end_ms"] < fee.valid_until_ms:
            raise ValueError("fee rule not valid for this entire trade window")
    return fees


def trade_outcome(row, direction, policy, fee):
    """Future accounting only. Never use this result to choose the action."""
    if direction not in {"yes", "no"}:
        raise ValueError("explicit long YES/NO direction required")
    ep, q = row["runner_endpoints"], policy.contracts
    slip = amount(policy.adverse_slippage_per_leg)
    if direction == "yes":
        entry_quote = Decimal(ep["entry_ask_1e4"]) / 10000
        exit_quote = Decimal(ep["exit_bid_1e4"]) / 10000
        entry_depth, exit_depth = ep["entry_ask_size_1e2"], ep["exit_bid_size_1e2"]
        decision_quote = Decimal(str(row["features"]["ask"]))
    else:
        entry_quote = 1 - Decimal(ep["entry_bid_1e4"]) / 10000
        exit_quote = 1 - Decimal(ep["exit_ask_1e4"]) / 10000
        entry_depth, exit_depth = ep["entry_bid_size_1e2"], ep["exit_ask_size_1e2"]
        decision_quote = 1 - Decimal(str(row["features"]["bid"]))
    entry = entry_quote + slip
    if entry_depth < q * 100 or entry >= 1:
        return {"status": "entry_not_filled", "event_ms": row["entry_ms"], "net": Decimal(0)}
    entry_fee = fee.fee(q, entry)
    shortfall = exit_depth < q * 100
    # A later lack of depth is a conservative write-off, NOT an exclusion or a
    # free zero-PnL trade. This is a risk bound, not a fabricated executed sale.
    exit_price = Decimal(0) if shortfall else max(Decimal(0), exit_quote - slip)
    exit_fee = Decimal(0) if shortfall else fee.fee(q, exit_price)
    gross = q * (exit_price - entry)
    return {"status": "exit_depth_writeoff" if shortfall else "modeled_roundtrip",
        "event_ms": row["label_end_ms"], "entry_price": entry, "exit_price": exit_price,
        "entry_fee": entry_fee, "exit_fee": exit_fee, "gross": gross,
        "net": gross - entry_fee - exit_fee,
        "entry_notional": q * entry, "turnover": q * (entry + exit_price),
        "entry_implementation_shortfall": q * (entry - decision_quote),
        "quote_gross_before_slippage": q * (exit_quote - entry_quote)}


def cash_string(value):
    return format(value, "f")


def simulate(rows, predictions, score_spec, policy, *, unresolved_windows):
    fees = validate_inputs(rows, predictions, score_spec, policy, unresolved_windows)
    first = date.fromisoformat(min(score_spec.sessions))
    last = date.fromisoformat(max(utc_date(r["label_end_ms"]) for r in rows))
    sessions = [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)]
    daily = {s: Decimal(0) for s in sessions}
    daily_trades = {s: 0 for s in sessions}
    games = {r["game_id"]: Decimal(0) for r in rows}
    pending, records = [], []
    cash = initial = amount(policy.initial_cash)
    equity, peak, drawdown = initial, initial, Decimal(0)
    halted = False
    counts = {"flat": 0, "pending_or_open_limit": 0, "cash_limit": 0,
              "entry_not_filled": 0, "modeled_roundtrip": 0, "exit_depth_writeoff": 0, "exit_unresolved_halt": 0}
    fees_total = turnover = notional = gross_total = Decimal(0)

    def release(before=None):
        nonlocal cash, equity, peak, drawdown, fees_total, turnover, notional, gross_total, halted
        while pending and (before is None or pending[0][0] < before):
            _, _, reserved, record, outcome = heapq.heappop(pending)
            cash += reserved + outcome["net"]
            counts[outcome["status"]] += 1
            if outcome["status"] == "exit_depth_writeoff":
                halted = True  # A write-off is not proof of a successfully closed position.
            if outcome["status"] != "entry_not_filled":
                equity += outcome["net"]
                peak = max(peak, equity)
                drawdown = max(drawdown, peak - equity)
                daily[utc_date(outcome["event_ms"])] += outcome["net"]
                daily_trades[utc_date(outcome["event_ms"])] += 1
                games[record["game_id"]] += outcome["net"]
                fees_total += outcome["entry_fee"] + outcome["exit_fee"]
                turnover += outcome["turnover"]
                notional += outcome["entry_notional"]
                gross_total += outcome["gross"]
            record.update({k: cash_string(v) if isinstance(v, Decimal) else v for k, v in outcome.items()})

    for index, row in enumerate(rows):
        release(row["decision_ms"])  # Equal timestamps wait: cross-stream order is not invented.
        p = Decimal(str(predictions[row["row_id"]]))
        threshold = amount(policy.threshold)
        direction = "yes" if p > threshold else "no" if p < -threshold else "flat"
        record = {"row_id": row["row_id"], "game_id": row["game_id"], "market_id": row["market_id"],
                  "decision_ms": row["decision_ms"], "direction": direction}
        records.append(record)
        if direction == "flat":
            counts["flat"] += 1
            record["status"] = "flat"
            continue
        if halted:
            counts["exit_unresolved_halt"] += 1
            record["status"] = "exit_unresolved_halt"
            continue
        if pending:
            counts["pending_or_open_limit"] += 1
            record["status"] = "pending_or_open_limit"
            continue
        fee = fees[row["market_id"]]
        reserved = fee.worst_cash(policy.contracts)
        if cash < reserved:
            counts["cash_limit"] += 1
            record["status"] = "cash_limit"
            continue
        # Only after selection/collateral checks inspect entry/exit accounting.
        # Reserve is independent of later price/depth/fill/outcome information.
        cash -= reserved
        outcome = trade_outcome(row, direction, policy, fee)
        record["reserved_cash"] = cash_string(reserved)
        heapq.heappush(pending, (outcome["event_ms"], index, reserved, record, outcome))
    release()
    trades = counts["modeled_roundtrip"] + counts["exit_depth_writeoff"]
    net = cash - initial
    if cash != equity or sum(daily.values(), Decimal(0)) != net or gross_total - fees_total != net:
        raise ValueError("cash/PnL accounting mismatch")
    absolute_game = sum((abs(v) for v in games.values()), Decimal(0))
    return {"net_pnl_usd": cash_string(net), "gross_after_slippage_usd": cash_string(gross_total),
        "fees_usd": cash_string(fees_total), "turnover_usd": cash_string(turnover),
        "entry_notional_usd": cash_string(notional), "final_cash_usd": cash_string(cash),
        "max_realized_drawdown_usd": cash_string(drawdown), "intrahorizon_mark_to_market": None,
        "trades": trades, "counts": counts, "active_sessions": sum(v > 0 for v in daily_trades.values()),
        "daily_accounted_positions": daily_trades, "evaluated_sessions": len(score_spec.sessions),
        "settlement_accounting_only_sessions": [s for s in sessions if s not in score_spec.sessions],
        "nonzero_pnl_sessions": sum(v != 0 for v in daily.values()),
        "daily_net_pnl_usd": {s: cash_string(v) for s, v in daily.items()},
        "game_net_pnl_usd": {g: cash_string(v) for g, v in games.items()},
        "largest_absolute_game_pnl_share": float(max(map(abs, games.values())) / absolute_game) if absolute_game else None,
        "records": records, "row_ids_sha256": fingerprint([r["row_id"] for r in rows]),
        "fee_interpretation": "declared raw-fee ceiling approximation, not verified exchange cash accounting",
        "execution_model": "fixed-size top-of-book FOK approximation; one global pending/open order; no passive fills",
        "all_modeled_exits_filled": counts["exit_depth_writeoff"] == 0,
        "halted_after_unfilled_exit": halted,
        "pnl_interpretation": "conservative write-off diagnostic" if halted else "modeled cash PnL under declared assumptions",
        "scientific_admission": False, "promotion": False, "actual_trades": 0,
        "zero_trade_success": False, "coverage": "requires zero unresolved scheduled windows; no survivor-only PnL"}


def objective_bounds(rows, policy, baseline_trade_count):
    """Perfect-foresight diagnostics, never researcher-generated predictions.

    Non-overlap limits count pending time from decision until exit. Capital is
    relaxed, as is the post-writeoff halt, so these are upper bounds rather than
    achievable strategies. The second
    bound uses EXACTLY the baseline's entered-position count, including losses.
    """
    if type(baseline_trade_count) is not int or not 0 <= baseline_trade_count <= 1000 or len(rows) > 20000:
        raise ValueError("oracle computation bound exceeded; do not truncate silently")
    fees = {f.market_id: f for f in policy.fees}
    options = []
    for r in rows:
        outcomes = [trade_outcome(r, side, policy, fees[r["market_id"]]) for side in ("yes", "no")]
        outcomes = [v for v in outcomes if v["status"] != "entry_not_filled"]
        if outcomes:
            options.append((r["label_end_ms"], r["decision_ms"], max(v["net"] for v in outcomes)))
    options.sort()
    ends = [o[0] for o in options]
    predecessors = [bisect.bisect_left(ends, start, 0, i) for i, (_, start, _) in enumerate(options)]
    best = [Decimal(0)]
    for i, (_, _, value) in enumerate(options):
        best.append(max(best[-1], value + best[predecessors[i]]))
    previous = [Decimal(0)] * (len(options) + 1)
    negative = Decimal("-Infinity")
    for count in range(1, baseline_trade_count + 1):
        current = [negative] * (len(options) + 1)
        for i, (_, _, value) in enumerate(options):
            current[i + 1] = max(current[i], value + previous[predecessors[i]])
        previous = current
    matched = previous[-1]
    return {"unconstrained_positive_sum_usd": cash_string(sum((max(Decimal(0), v) for _, _, v in options), Decimal(0))),
            "nonoverlap_capital_relaxed_usd": cash_string(best[-1]),
            "baseline_exact_trade_count": baseline_trade_count,
            "same_count_nonoverlap_capital_relaxed_usd": cash_string(matched) if matched.is_finite() else None,
            "not_a_model_result": True, "capital_relaxed": True, "post_writeoff_halt_relaxed": True}


def paired_simulation(rows, baseline, candidate, score_spec, policy, *, unresolved_windows):
    a = simulate(rows, baseline, score_spec, policy, unresolved_windows=unresolved_windows)
    b = simulate(rows, candidate, score_spec, policy, unresolved_windows=unresolved_windows)
    daily = {s: Decimal(b["daily_net_pnl_usd"][s]) - Decimal(v) for s, v in a["daily_net_pnl_usd"].items()}
    values = [float(v) for v in daily.values()]
    mean = math.fsum(values) / len(values)
    sd = math.sqrt(math.fsum((v - mean) ** 2 for v in values) / (len(values) - 1)) if len(values) > 1 else 0
    enough = len(score_spec.sessions) >= 20 and score_spec.evidence_class == "untouched"
    return {"baseline": a, "candidate": b,
        "candidate_minus_baseline_daily_usd": {s: cash_string(v) for s, v in daily.items()},
        "mean_daily_delta_usd": mean, "daily_delta_sharpe_unannualized": mean / sd if sd else None,
        "daily_delta_mean_95pct_circular_block": circular_interval(values, score_spec.block_sessions,
            score_spec.bootstrap_replicates, score_spec.bootstrap_seed) if enough else None,
        "objective_bounds": objective_bounds(rows, policy, a["trades"]),
        "scientific_admission": False, "promotion": False, "actual_trades": 0}
