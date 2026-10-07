from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock

from experiments import nfl_settlement_probability_train_diagnostic as diagnostic


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_source(root: Path, *, tie_index: int | None = None,
                 shifted_game_date_index: int | None = None) -> None:
    (root / "catalog").mkdir(parents=True)
    (root / "trades").mkdir()
    cohort = []
    first = datetime(2025, 1, 1, 20, tzinfo=timezone.utc)
    for index in range(42):
        start = first + timedelta(days=index)
        game_date = (
            (start - timedelta(days=1)).date().isoformat()
            if shifted_game_date_index == index else start.date().isoformat()
        )
        game_id = f"2025_{index + 1:02d}_BAL_KC"
        event_slug = f"nfl-bal-kc-{start.date().isoformat()}-{index + 1}"
        event_id = str(1000 + index)
        market_id = str(2000 + index)
        condition = "0x" + f"{index + 1:064x}"
        home_token, away_token = str(10**40 + index * 2), str(10**40 + index * 2 + 1)
        outcome = index % 2
        prices = (["1", "0"] if outcome else ["0", "1"])
        if tie_index == index:
            prices = ["0.5", "0.5"]
        event = {
            "id": event_id,
            "slug": event_slug,
            "closed": True,
            "finishedTimestamp": _iso(start + timedelta(hours=4, minutes=30)),
            "markets": [{
                "id": market_id,
                "conditionId": condition,
                "sportsMarketType": "moneyline",
                "outcomes": json.dumps(["Chiefs", "Ravens"]),
                "clobTokenIds": json.dumps([home_token, away_token]),
                "outcomePrices": json.dumps(prices),
                "closed": True,
                "closedTime": _iso(start + timedelta(hours=4)),
                "umaEndDate": _iso(start + timedelta(hours=5)),
            }],
        }
        raw = json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
        stored = gzip.compress(raw, mtime=0)
        raw_path = root / "catalog" / f"{game_id}.raw.json.gz"
        raw_path.write_bytes(stored)
        meta = {
            "game_id": game_id,
            "game_date": game_date,
            "event_slug": event_slug,
            "event_id": event_id,
            "market_id": market_id,
            "condition_id": condition,
            "tokens": sorted([home_token, away_token]),
            "event_start_utc": _iso(start),
            "stored_sha256": hashlib.sha256(stored).hexdigest(),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
        }
        _write_json(root / "catalog" / f"{game_id}.json", meta)
        game_root = root / "trades" / game_id
        game_root.mkdir()
        cutoff = int((start - timedelta(minutes=15)).timestamp())
        trade_rows = [
            # The first three rows ensure every frozen window is nonempty.
            (cutoff - 10_000, home_token, "Chiefs", 0, 1.0, 0.45),
            (cutoff - 3_000, away_token, "Ravens", 1, 2.0, 0.52),
            (cutoff - 600, home_token, "Chiefs", 0, 1.5, 0.50),
            # Latest-second baseline: (1*.60 + 3*(1-.30)) / 4 = .675.
            (cutoff - 10, home_token, "Chiefs", 0, 1.0, 0.60),
            (cutoff - 10, away_token, "Ravens", 1, 3.0, 0.30),
            # Must never affect the cutoff-causal baseline or features.
            (cutoff + 1, home_token, "Chiefs", 0, 1000.0, 0.99),
        ]
        trade_path = game_root / "trade_window.csv"
        with trade_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=diagnostic.TRADE_FIELDS)
            writer.writeheader()
            for ordinal, (timestamp, token, name, outcome_index, size, price) in enumerate(
                    trade_rows):
                writer.writerow({
                    "side": "BUY", "token_id": token, "condition_id": condition,
                    "size": size, "price": price, "timestamp": timestamp,
                    "event_slug": event_slug, "outcome": name,
                    "outcome_index": outcome_index,
                    "transaction_hash": f"0x{index:02x}{ordinal:02x}",
                })
        _write_json(game_root / "manifest.json", {
            "game_id": game_id,
            "condition_id": condition,
            "tokens": sorted([home_token, away_token]),
            "complete": True,
            "dev_final_opened": False,
            "trade_window_sha256": _sha(trade_path),
        })
        cohort.append({
            "game_id": game_id,
            "game_date": game_date,
            "event_slug": event_slug,
        })
    with (root / "cohort.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("game_id", "game_date", "event_slug"))
        writer.writeheader()
        writer.writerows(cohort)
    _write_json(root / "manifest.json", {
        "schema": "nfl_2025_train_fresh_source_audit_v1",
        "complete": True,
        "source_games": 42,
        "train_distinct_dates": 42,
        "dev_final_opened": False,
        "model_fits": 0,
        "provider_cost_usd": "0",
    })


class OrientationAndFeatureTests(unittest.TestCase):
    def test_exact_lar_rams_alias_orients_without_fuzzy_matching(self) -> None:
        market = {
            "outcomes": ["Rams", "Panthers"],
            "clobTokenIds": ["101", "202"],
        }
        result = diagnostic.orient_market(
            "2025_13_LA_CAR", market, ["101", "202"]
        )
        self.assertEqual(result["away_team"], "LAR")
        self.assertEqual(result["away_token"], "101")
        self.assertEqual(result["home_team"], "CAR")
        self.assertEqual(result["home_token"], "202")
        market["outcomes"] = ["Rams", "Rams"]
        with self.assertRaisesRegex(diagnostic.EventExclusion, "game teams"):
            diagnostic.orient_market("2025_13_LA_CAR", market, ["101", "202"])

    def test_same_second_weighting_cutoff_leakage_and_endpoint_rejection(self) -> None:
        cutoff = 20_000
        rows = [
            {"timestamp": cutoff - 10_000, "size": 1.0, "home_probability": 0.4},
            {"timestamp": cutoff - 3_000, "size": 1.0, "home_probability": 0.5},
            {"timestamp": cutoff - 600, "size": 1.0, "home_probability": 0.5},
            {"timestamp": cutoff - 10, "size": 1.0, "home_probability": 0.6},
            {"timestamp": cutoff - 10, "size": 3.0, "home_probability": 0.7},
            {"timestamp": cutoff + 1, "size": 999.0, "home_probability": 0.01},
        ]
        baseline, features, available = diagnostic.build_features(rows, cutoff)
        self.assertAlmostEqual(baseline, 0.675)
        self.assertEqual(available, (cutoff - 10) * 1000)
        self.assertEqual(len(features), len(diagnostic.FEATURE_NAMES))
        endpoint = list(rows)
        endpoint[-3] = {"timestamp": cutoff - 10, "size": 1.0,
                        "home_probability": 1.0}
        endpoint[-2] = {"timestamp": cutoff - 10, "size": 3.0,
                        "home_probability": 1.0}
        with self.assertRaisesRegex(diagnostic.EventExclusion, "epsilon"):
            diagnostic.build_features(endpoint, cutoff)

    def test_resolution_uses_maximum_availability_clock_and_rejects_tie(self) -> None:
        start = datetime(2025, 1, 1, 20, tzinfo=timezone.utc)
        event = {
            "closed": True,
            "finishedTimestamp": _iso(start + timedelta(hours=5)),
            # This non-frozen field must not affect target availability.
            "closedTime": _iso(start + timedelta(hours=7)),
        }
        market = {
            "closed": True, "outcomePrices": ["1", "0"],
            "closedTime": _iso(start + timedelta(hours=4)),
            "umaEndDate": _iso(start + timedelta(hours=6)),
        }
        outcome, available, field = diagnostic.resolved_home_outcome(
            event, market, 0, start
        )
        self.assertEqual(outcome, 1)
        self.assertEqual(available, int((start + timedelta(hours=6)).timestamp() * 1000))
        self.assertIn("market.umaEndDate", field)
        market["outcomePrices"] = ["0.5", "0.5"]
        with self.assertRaisesRegex(diagnostic.EventExclusion, "exact"):
            diagnostic.resolved_home_outcome(event, market, 0, start)


class FoldAndDecisionTests(unittest.TestCase):
    def test_folds_are_22_then_four_nonoverlapping_five_date_checks(self) -> None:
        dates = [f"2025-02-{day:02d}" for day in range(1, 29)] + [
            f"2025-03-{day:02d}" for day in range(1, 15)
        ]
        folds = diagnostic.chronological_date_folds(dates)
        self.assertEqual([len(fold["fit_dates"]) for fold in folds], [22, 27, 32, 37])
        self.assertEqual([len(fold["check_dates"]) for fold in folds], [5, 5, 5, 5])
        self.assertEqual(len({date for fold in folds for date in fold["check_dates"]}), 20)
        for fold in folds:
            self.assertLess(max(fold["fit_dates"]), min(fold["check_dates"]))

    def test_keep_rule_is_exact_and_has_no_tie_escape(self) -> None:
        decision, conditions = diagnostic.diagnostic_keep(
            0.19, 0.20, 0.58, 0.60, [True, True, True, False]
        )
        self.assertEqual(decision, "KEEP")
        self.assertTrue(conditions["candidate_brier_fold_wins_at_least_3_of_4"])
        self.assertEqual(diagnostic.diagnostic_keep(
            0.20, 0.20, 0.58, 0.60, [True, True, True, False]
        )[0], "REVERT")

    def test_exact_real_cohort_allows_only_declared_tie_attrition(self) -> None:
        valid = [{"game_id": "2025_04_GB_DAL", "reason": "unresolved_outcome"}]
        diagnostic.validate_exact_cohort_attrition(195, 194, valid)
        for materialized, exclusions in (
            (195, []),
            (193, valid + [{"game_id": "other", "reason": "empty_trade_tape"}]),
            (194, [{"game_id": "2025_04_GB_DAL", "reason": "invalid_trade"}]),
        ):
            with self.subTest(materialized=materialized, exclusions=exclusions):
                with self.assertRaisesRegex(ValueError, "194/195"):
                    diagnostic.validate_exact_cohort_attrition(
                        195, materialized, exclusions
                    )

    def test_split_uses_frozen_game_date_not_cutoff_utc_date(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "synthetic-train"
            source.mkdir()
            _make_source(source, shifted_game_date_index=0)
            cohort = diagnostic._read_cohort(source / "cohort.csv")
            first = diagnostic._materialize_event(source, cohort[0])
            cutoff_utc_date = datetime.fromtimestamp(
                first.trusted["cutoff_ms"] / 1000, timezone.utc
            ).date().isoformat()
            self.assertNotEqual(first.game_date, cutoff_utc_date)
            self.assertEqual(first.split_date, first.game_date)
            folds = diagnostic.chronological_date_folds(
                [row["game_date"] for row in cohort]
            )
            self.assertIn(first.game_date, folds[0]["fit_dates"])


class EndToEndSyntheticTests(unittest.TestCase):
    def test_deterministic_full_denominator_exclusion_masks_and_no_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "synthetic-train"
            source.mkdir()
            _make_source(source, tie_index=3)
            first_output, second_output = root / "result-a", root / "result-b"
            fixed_time = "2026-09-29T12:00:00+00:00"
            # Any accidental provider/network path makes this test fail.
            with mock.patch.object(socket, "socket", side_effect=AssertionError("network used")):
                first = diagnostic.run(
                    source, first_output, expected_events=42, expected_dates=42,
                    allow_test_paths=True, generated_utc=fixed_time,
                )
                second = diagnostic.run(
                    source, second_output, expected_events=42, expected_dates=42,
                    allow_test_paths=True, generated_utc=fixed_time,
                )
            self.assertTrue(first["complete"])
            self.assertEqual(first["source_events"], 42)
            self.assertEqual(first["materialized_events"], 41)
            self.assertEqual(first["excluded_events"], 1)
            self.assertEqual(first["provider_cost_usd"], "0")
            self.assertFalse(first["route_dev_opened"])
            self.assertFalse(first["sealed_final_opened"])
            exclusions = json.loads((first_output / "exclusions.json").read_text())
            self.assertTrue(exclusions["reconciles_to_source_denominator"])
            self.assertEqual(exclusions["exclusions"][0]["reason"], "unresolved_outcome")
            receipts = json.loads((first_output / "input_receipts.json").read_text())
            self.assertEqual(len(receipts["all_source_file_receipts"]), 42)
            self.assertEqual(len(receipts["materialized_event_receipts"]), 41)
            scorecard = json.loads((first_output / "scorecard.json").read_text())
            self.assertTrue(scorecard["identical_masks"][
                "market_ordinary_candidate_check_keys_identical"
            ])
            self.assertEqual(len(scorecard["folds"]), 4)
            paired = scorecard["paired_candidate_minus_ordinary"]
            self.assertEqual(
                paired["delta_convention"],
                "candidate_minus_ordinary; negative loss is better",
            )
            self.assertIn("candidate_minus_ordinary_brier", paired["events"][0])
            for key in (
                    "event_brier_summary", "event_log_loss_summary",
                    "date_block_brier_summary", "date_block_log_loss_summary"):
                self.assertEqual(
                    paired[key]["delta_convention"],
                    "candidate_minus_ordinary; negative loss is better",
                )
            lock = json.loads((first_output / "pre_score_lock.json").read_text())
            self.assertEqual(lock["outcome_availability"], (
                "maximum of present selected-market closedTime, selected-market "
                "umaEndDate, and event finishedTimestamp; no other clock admitted"
            ))
            self.assertEqual(
                (first_output / "predictions.csv").read_bytes(),
                (second_output / "predictions.csv").read_bytes(),
            )
            self.assertEqual(
                (first_output / "scorecard.json").read_bytes(),
                (second_output / "scorecard.json").read_bytes(),
            )
            self.assertEqual(first, second)

    def test_output_must_be_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            existing = root / "existing"
            existing.mkdir()
            with self.assertRaisesRegex(FileExistsError, "fresh"):
                diagnostic._validate_roots(root / "source", existing,
                                           allow_test_paths=True)


if __name__ == "__main__":
    unittest.main()
