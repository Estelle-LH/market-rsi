"""No-network tests for the bounded 2025 source-only trade-coverage screen."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from supervisor_harness import screen_2025_trade_coverage as coverage


def fixture(root: Path) -> tuple[Path, Path, list[dict]]:
    mapping_dir = root / "mapping"
    mapping_dir.mkdir()
    catalog = root / "catalog"
    catalog.mkdir()
    mapping = []
    events = []
    for number in range(coverage.GAME_COUNT):
        suffix = f"{number:03d}"
        mapping.append({"game_id": f"game-{suffix}", "event_id": f"event-{suffix}",
                        "market_id": f"market-{suffix}", "condition_id": f"condition-{suffix}",
                        "game_date": "2025-09-04"})
        events.append({"id": f"event-{suffix}", "startTime": "2025-09-04T20:00:00Z",
                       "markets": [{"id": f"market-{suffix}",
                                    "conditionId": f"condition-{suffix}",
                                    "sportsMarketType": "moneyline",
                                    "clobTokenIds": json.dumps([f"asset-{suffix}-a", f"asset-{suffix}-b"]),
                                    "outcomes": '["DO_NOT_SAVE_OUTCOME_A","DO_NOT_SAVE_OUTCOME_B"]'}]})
    raw = coverage.encoded(mapping)
    (mapping_dir / "mapping.json").write_bytes(raw)
    (mapping_dir / "manifest.json").write_bytes(coverage.encoded({
        "schema": "market_p0_2025_schedule_screen_v1",
        "formal_data_admitted": False, "trade_coverage_verified": False,
        "mapped_unique_games": coverage.GAME_COUNT,
        "schedule_games": coverage.GAME_COUNT, "catalog_events": len(events),
        "mapping_sha256": coverage.sha(raw)}))
    return mapping_dir, catalog, events


def selected_game() -> dict:
    start = int(datetime(2025, 9, 4, 20, tzinfo=timezone.utc).timestamp())
    return {"game_id": "game", "event_id": "event", "market_id": "market",
            "condition_id": "condition", "game_date": "2025-09-04",
            "start_timestamp": start - 12 * 3600, "game_start_timestamp": start,
            "end_timestamp": start + 5 * 3600, "_tokens": frozenset(("a", "b"))}


class CoverageScreenTests(unittest.TestCase):
    def test_all_285_games_metadata_only_and_hashed_receipts(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            mapping_dir, catalog, events = fixture(root)
            calls = []

            def fake_fetch(condition: str, offset: int, lower: int, upper: int,
                           timeout: float, byte_cap: int) -> tuple[bytes, str]:
                calls.append((condition, offset, lower, upper, byte_cap))
                suffix = condition.split("-")[-1]
                raw = json.dumps([{"conditionId": condition, "asset": f"asset-{suffix}-a",
                                   "timestamp": lower + 1, "price": 0.7,
                                   "outcome": "DO_NOT_SAVE_OUTCOME",
                                   "wallet": "DO_NOT_SAVE_WALLET",
                                   "score": "DO_NOT_SAVE_SCORE"}]).encode()
                return raw, f"https://example.invalid/trades?market={condition}&offset={offset}"

            with patch.object(coverage, "load_events", return_value=(events, [{"sha256": "catalog-hash"}])), \
                    patch.object(coverage, "fetch_page", side_effect=fake_fetch):
                report = coverage.screen(mapping_dir, catalog, root / "result")
            self.assertEqual(report["games_screened"], 285)
            self.assertEqual(report["games_with_trades"], 285)
            self.assertEqual(report["total_trades"], 285)
            self.assertEqual(report["requests_used"], 285)
            self.assertFalse(report["formal_data_admitted"])
            self.assertFalse(report["event_aligned_labels_verified"])
            self.assertEqual(len(calls), 285)
            self.assertTrue(all(offset == 0 for _, offset, _, _, _ in calls))
            self.assertTrue(all(upper - lower == 17 * 3600 for _, _, lower, upper, _ in calls))
            self.assertEqual(sorted(path.name for path in (root / "result").iterdir()),
                             ["coverage.json", "coverage.partial.json",
                              "manifest.json", "manifest.partial.json"])
            raw_coverage = (root / "result" / "coverage.json").read_bytes()
            self.assertEqual(report["coverage_sha256"], coverage.sha(raw_coverage))
            rows = json.loads(raw_coverage)
            self.assertEqual(len(rows), 285)
            self.assertEqual(rows[0]["page_receipts"][0]["rows"], 1)
            self.assertEqual(rows[0]["pre_game_trades"], 1)
            self.assertEqual(rows[0]["game_to_plus_five_hours_trades"], 0)
            self.assertNotIn("DO_NOT_SAVE", raw_coverage.decode())
            self.assertNotIn("_tokens", raw_coverage.decode())
            self.assertNotIn("price", raw_coverage.decode())

    def test_rejects_mapping_hash_before_any_request(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            mapping_dir, catalog, events = fixture(root)
            (mapping_dir / "mapping.json").write_text("[]")
            with patch.object(coverage, "load_events", return_value=(events, [])), \
                    patch.object(coverage, "fetch_page") as fetch:
                with self.assertRaisesRegex(ValueError, "mapping hash changed"):
                    coverage.screen(mapping_dir, catalog, root / "result")
            fetch.assert_not_called()
            self.assertFalse((root / "result").exists())

    def test_failure_after_one_game_keeps_only_incomplete_metadata_checkpoint(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            mapping_dir, catalog, events = fixture(root)
            calls = 0

            def fail_on_second(condition: str, offset: int, lower: int, upper: int,
                               timeout: float, byte_cap: int) -> tuple[bytes, str]:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("source unavailable")
                raw = json.dumps([{"conditionId": condition, "asset": "asset-000-a",
                                   "timestamp": lower + 1,
                                   "outcome": "DO_NOT_SAVE_OUTCOME"}]).encode()
                return raw, "https://example.invalid/first"

            with patch.object(coverage, "load_events", return_value=(events, [{"sha256": "catalog-hash"}])), \
                    patch.object(coverage, "fetch_page", side_effect=fail_on_second):
                with self.assertRaisesRegex(RuntimeError, "source unavailable"):
                    coverage.screen(mapping_dir, catalog, root / "result")
            self.assertEqual(calls, 2)
            self.assertFalse((root / "result" / "manifest.json").exists())
            self.assertFalse((root / "result" / "coverage.json").exists())
            partial = json.loads((root / "result" / "manifest.partial.json").read_text())
            self.assertEqual(partial["status"], "failed")
            self.assertEqual(partial["completed_games"], 1)
            self.assertEqual(partial["failed_game_id"], "game-001")
            self.assertFalse(partial["complete_within_bounded_windows"])
            self.assertFalse(partial["formal_data_admitted"])
            partial_raw = (root / "result" / "coverage.partial.json").read_bytes()
            self.assertEqual(partial["coverage_partial_sha256"], coverage.sha(partial_raw))
            self.assertEqual(len(json.loads(partial_raw)), 1)
            self.assertNotIn("DO_NOT_SAVE", partial_raw.decode())

    def test_full_last_page_fails_instead_of_claiming_completeness(self) -> None:
        game = selected_game()

        def full_page(condition: str, offset: int, lower: int, upper: int,
                      timeout: float, byte_cap: int) -> tuple[bytes, str]:
            batch = [{"conditionId": condition, "asset": "a", "timestamp": lower + 1,
                      "transactionHash": str(offset + index)} for index in range(2)]
            return json.dumps(batch).encode(), "https://example.invalid/full"

        with patch.object(coverage, "PAGE_LIMIT", 2), \
                patch.object(coverage, "fetch_page", side_effect=full_page):
            with self.assertRaisesRegex(ValueError, "pagination incomplete"):
                coverage.screen_game(game, timeout=1, request_budget=2,
                                     byte_budget=100_000, page_byte_cap=10_000)

    def test_overlap_and_out_of_window_fail_closed(self) -> None:
        game = selected_game()
        trade = {"conditionId": "condition", "asset": "a",
                 "timestamp": game["start_timestamp"] + 1}
        with patch.object(coverage, "PAGE_LIMIT", 1), \
                patch.object(coverage, "fetch_page", return_value=(json.dumps([trade]).encode(), "url")):
            with self.assertRaisesRegex(ValueError, "overlapping trade pages"):
                coverage.screen_game(game, timeout=1, request_budget=2,
                                     byte_budget=100_000, page_byte_cap=10_000)
        trade["timestamp"] = game["end_timestamp"] + 1
        with patch.object(coverage, "fetch_page", return_value=(json.dumps([trade]).encode(), "url")):
            with self.assertRaisesRegex(ValueError, "ignored fixed time bounds"):
                coverage.screen_game(game, timeout=1, request_budget=2,
                                     byte_budget=100_000, page_byte_cap=10_000)

    def test_byte_and_request_caps_fail_closed(self) -> None:
        game = selected_game()
        with patch.object(coverage, "fetch_page") as fetch:
            with self.assertRaisesRegex(ValueError, "budget exhausted"):
                coverage.screen_game(game, timeout=1, request_budget=0,
                                     byte_budget=100, page_byte_cap=100)
        fetch.assert_not_called()
        with patch.object(coverage, "fetch_page", return_value=(b"x" * 101, "url")):
            with self.assertRaisesRegex(ValueError, "exceeded byte budget"):
                coverage.screen_game(game, timeout=1, request_budget=2,
                                     byte_budget=100, page_byte_cap=100)

    def test_start_requires_timezone_and_cli_requires_explicit_network_flag(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone"):
            coverage.parse_utc("2025-09-04T20:00:00")
        with patch("sys.argv", ["screen_2025_trade_coverage", "--mapping", "x",
                                "--catalog", "y", "--output", "z"]), \
                patch.object(coverage, "screen") as screen:
            with self.assertRaises(SystemExit):
                coverage.main()
        screen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
