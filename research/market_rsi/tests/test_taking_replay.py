import copy
import itertools
import unittest
from decimal import Decimal

from label_materializer import LabelPolicy
from taking_replay import FeeRule, TakingPolicy, objective_bounds, paired_simulation, simulate, trade_outcome
from test_market_scoring import rows, spec


def sample(index=0, offset=0, movement=2000, day=1):
    row = rows(day, movement, f"m{index}", f"g{index}")[0]
    for key in ("decision_ms", "feature_available_ms", "entry_ms", "label_end_ms", "label_available_ms"):
        row[key] += offset
    return row


def fee(market="m0", **overrides):
    kw = dict(market_id=market, coefficient="0.07", quantum_usd="0.01", valid_from_ms=0,
              valid_until_ms=100 * 86400000, source_sha256="f" * 64,
              rounding="raw_fee_ceil_declared_approximation")
    kw.update(overrides)
    return FeeRule(**kw)


def policy(data, **overrides):
    kw = dict(contracts=1, threshold="0.01", adverse_slippage_per_leg="0", initial_cash="10",
              max_open_orders=1, fees=tuple(fee(m) for m in sorted({r["market_id"] for r in data})),
              label_policy=LabelPolicy(100, 10, 20, 20, 1000, 10000))
    kw.update(overrides)
    return TakingPolicy(**kw)


def predictions(data, value=.5):
    return {r["row_id"]: value for r in data}


class TakingTests(unittest.TestCase):
    def run_sim(self, data=None, value=.5, score_spec=None, **changes):
        data = data or [sample()]
        return simulate(data, predictions(data, value), score_spec or spec(), policy(data, **changes), unresolved_windows=0)

    def test_yes_contra_prices_two_fees_and_cash_reconcile(self):
        result = self.run_sim()
        self.assertEqual(Decimal(result["net_pnl_usd"]), Decimal("0.06"))
        self.assertEqual(Decimal(result["fees_usd"]), Decimal("0.04"))
        self.assertEqual(Decimal(result["final_cash_usd"]), Decimal("10.06"))
        self.assertEqual(result["trades"], 1)
        self.assertFalse(result["scientific_admission"])
        self.assertEqual(result["actual_trades"], 0)

    def test_no_uses_complement_of_yes_bid_ask_not_second_complement(self):
        result = self.run_sim([sample(movement=-2000)], value=-.5)
        r = result["records"][0]
        self.assertEqual(Decimal(r["entry_price"]), Decimal("0.6"))
        self.assertEqual(Decimal(r["exit_price"]), Decimal("0.7"))
        self.assertEqual(Decimal(result["net_pnl_usd"]), Decimal("0.06"))

    def test_adverse_slippage_on_both_legs(self):
        result = self.run_sim(adverse_slippage_per_leg="0.01")
        self.assertEqual(Decimal(result["net_pnl_usd"]), Decimal("0.04"))
        self.assertEqual(Decimal(result["records"][0]["entry_implementation_shortfall"]), Decimal("0.01"))

    def test_future_exit_depth_failure_is_writeoff_not_exclusion(self):
        data = [sample()]
        data[0]["runner_endpoints"]["exit_bid_size_1e2"] = 50
        result = self.run_sim(data)
        self.assertEqual(result["trades"], 1)
        self.assertEqual(result["counts"]["exit_depth_writeoff"], 1)
        self.assertEqual(Decimal(result["net_pnl_usd"]), Decimal("-0.52"))

    def test_unfilled_exit_stops_further_trading_not_fake_successful_close(self):
        data = [sample(), sample(1, 111)]
        data[0]["runner_endpoints"]["exit_bid_size_1e2"] = 50
        result = self.run_sim(data)
        self.assertEqual(result["trades"], 1)
        self.assertEqual(result["records"][1]["status"], "exit_unresolved_halt")
        self.assertTrue(result["halted_after_unfilled_exit"])
        self.assertFalse(result["all_modeled_exits_filled"])
        self.assertEqual(result["pnl_interpretation"], "conservative write-off diagnostic")

    def test_entry_depth_failure_keeps_cash_reserved_until_observable(self):
        data = [sample(), sample(1, 5), sample(2, 11)]
        data[0]["runner_endpoints"]["entry_ask_size_1e2"] = 50
        result = self.run_sim(data)
        self.assertEqual(result["records"][0]["status"], "entry_not_filled")
        self.assertEqual(result["records"][1]["status"], "pending_or_open_limit")
        self.assertEqual(result["records"][2]["status"], "modeled_roundtrip")

    def test_overlap_and_same_timestamp_exit_cannot_fund_next_decision(self):
        for offset in (50, 110):
            data = [sample(), sample(1, offset)]
            result = self.run_sim(data)
            self.assertEqual(result["trades"], 1)
            self.assertEqual(result["counts"]["pending_or_open_limit"], 1)

    def test_later_decision_may_use_settled_cash(self):
        result = self.run_sim([sample(), sample(1, 111)])
        self.assertEqual(result["trades"], 2)
        self.assertEqual(Decimal(result["net_pnl_usd"]), Decimal("0.12"))

    def test_worst_case_collateral_not_future_cheap_entry(self):
        result = self.run_sim(initial_cash="1.00")
        self.assertEqual(result["trades"], 0)
        self.assertEqual(result["counts"]["cash_limit"], 1)
        self.assertFalse(result["zero_trade_success"])

    def test_changed_future_does_not_change_order_selection_before_exit(self):
        outputs = []
        for move in (-2000, 2000):
            data = [sample(movement=move), sample(1, 50)]
            result = self.run_sim(data)
            outputs.append([(r["row_id"], r["direction"], r.get("reserved_cash"), r["status"]) for r in result["records"]])
        self.assertEqual(outputs[0], outputs[1])

    def test_zero_trade_and_zero_profit_trade_are_distinct(self):
        empty = self.run_sim(value=0)
        self.assertEqual(empty["trades"], 0)
        self.assertEqual(empty["active_sessions"], 0)
        data = [sample(movement=1000)]
        traded = self.run_sim(data, fees=(fee(coefficient="0"),))
        self.assertEqual(traded["trades"], 1)
        self.assertEqual(traded["active_sessions"], 1)
        self.assertEqual(traded["nonzero_pnl_sessions"], 0)

    def test_realized_drawdown_not_claimed_as_intrahorizon_mtm(self):
        result = self.run_sim([sample(movement=0)])
        self.assertEqual(Decimal(result["max_realized_drawdown_usd"]), Decimal(".14"))
        self.assertIsNone(result["intrahorizon_mark_to_market"])

    def test_missing_prediction_or_unresolved_windows_rejected(self):
        data = [sample()]
        for p, unresolved in (({}, 0), (predictions(data), 1), (predictions(data), True)):
            with self.subTest(unresolved=unresolved), self.assertRaises(ValueError):
                simulate(data, p, spec(), policy(data), unresolved_windows=unresolved)

    def test_wrong_horizon_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            self.run_sim(label_policy=LabelPolicy(200, 10, 20, 20, 1000, 10000))

    def test_missing_market_fee_or_expired_rule_rejected(self):
        for rule in (fee("other"), fee(valid_until_ms=1000)):
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                self.run_sim(fees=(rule,))

    def test_fee_rounding_is_explicit_approximation_not_inferred_exchange_bill(self):
        f = fee()
        self.assertEqual(f.fee(1, Decimal("0.5")), Decimal("0.02"))
        self.assertEqual(f.fee(100, Decimal("0.5")), Decimal("1.75"))
        self.assertEqual(f.worst_cash(1), Decimal("1.04"))
        with self.assertRaises(ValueError):
            fee(rounding="official_exact")

    def test_missing_evaluation_calendar_days_not_imputed(self):
        data = [sample(day=1), sample(1, day=3)]
        with self.assertRaises(ValueError):
            self.run_sim(data, score_spec=spec(sessions=("1970-01-02", "1970-01-04")))

    def test_exit_after_midnight_does_not_create_an_extra_evaluated_session(self):
        data = [sample(offset=86400000 - 1050)]
        p = predictions(data)
        result = paired_simulation(data, p, p, spec(), policy(data), unresolved_windows=0)
        a = result["baseline"]
        self.assertEqual(a["evaluated_sessions"], 1)
        self.assertEqual(a["settlement_accounting_only_sessions"], ["1970-01-03"])
        self.assertEqual(a["active_sessions"], 1)
        self.assertIsNone(result["daily_delta_mean_95pct_circular_block"])

    def test_unchanged_predictions_zero_paired_pnl_delta(self):
        data = [sample()]
        p = predictions(data)
        result = paired_simulation(data, p, p, spec(), policy(data), unresolved_windows=0)
        self.assertEqual(result["mean_daily_delta_usd"], 0)
        self.assertIsNone(result["daily_delta_sharpe_unannualized"])
        self.assertFalse(result["promotion"])

    def test_paired_daily_accounting_keeps_no_trade_dates(self):
        data = [sample(), sample(1, day=2)]
        p = predictions(data)
        candidate = dict(p)
        candidate[data[1]["row_id"]] = 0
        s = spec(sessions=("1970-01-02", "1970-01-03"))
        result = paired_simulation(data, p, candidate, s, policy(data), unresolved_windows=0)
        self.assertEqual(len(result["candidate"]["daily_net_pnl_usd"]), 2)
        self.assertEqual(Decimal(result["candidate"]["daily_net_pnl_usd"]["1970-01-03"]), 0)
        self.assertEqual(Decimal(result["candidate_minus_baseline_daily_usd"]["1970-01-03"]), Decimal("-.06"))

    def test_oracle_uses_nonoverlap_dynamic_program_not_greedy(self):
        data = [sample(), sample(1, 50, movement=4000), sample(2, 170)]
        bounds = objective_bounds(data, policy(data), 2)
        self.assertEqual(Decimal(bounds["unconstrained_positive_sum_usd"]), Decimal(".38"))
        self.assertEqual(Decimal(bounds["nonoverlap_capital_relaxed_usd"]), Decimal(".32"))
        self.assertEqual(Decimal(bounds["same_count_nonoverlap_capital_relaxed_usd"]), Decimal(".32"))
        self.assertTrue(bounds["capital_relaxed"])

    def test_volume_matched_oracle_requires_exact_trade_count_even_if_negative(self):
        data = [sample(movement=0)]
        bounds = objective_bounds(data, policy(data), 1)
        self.assertEqual(Decimal(bounds["nonoverlap_capital_relaxed_usd"]), 0)
        self.assertEqual(Decimal(bounds["same_count_nonoverlap_capital_relaxed_usd"]), Decimal("-.14"))

    def test_oracle_matches_independent_exhaustive_interval_enumeration(self):
        data = [sample(i, offset, move) for i, (offset, move) in enumerate(
            [(0, 1000), (30, 2000), (100, -1000), (111, 0), (220, 4000), (400, -2000)])]
        pol = policy(data)
        by_market = {f.market_id: f for f in pol.fees}
        values = [max(trade_outcome(r, side, pol, by_market[r["market_id"]])["net"]
                      for side in ("yes", "no")) for r in data]
        for count in range(4):
            feasible = []
            for selected in itertools.combinations(range(len(data)), count):
                if all(data[a]["label_end_ms"] < data[b]["decision_ms"] for a, b in zip(selected, selected[1:])):
                    feasible.append(sum((values[i] for i in selected), Decimal(0)))
            result = objective_bounds(data, pol, count)
            actual = result["same_count_nonoverlap_capital_relaxed_usd"]
            self.assertEqual(None if actual is None else Decimal(actual), max(feasible) if feasible else None)

    def test_policy_disallows_unimplemented_multi_position_or_float_size(self):
        data = [sample()]
        for change in ({"contracts": 1.5}, {"max_open_orders": 2}, {"initial_cash": "0"},
                       {"threshold": "NaN"}, {"adverse_slippage_per_leg": "-0.01"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                policy(data, **change)


if __name__ == "__main__":
    unittest.main()
