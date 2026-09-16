from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

import pyarrow.parquet as pq

from polymarket_historical_source_canary import DEFAULT_DATES, run_canary


def _timestamp(day: str) -> int:
    return int(datetime.fromisoformat(day + "T12:00:00+00:00").timestamp())


class FakeClient:
    def __init__(self):
        self.requests = []
        self.total_bytes = 0
        self.event_counts = {DEFAULT_DATES[0]: 2, DEFAULT_DATES[1]: 2,
                             DEFAULT_DATES[2]: 1}

    def get(self, endpoint, url, params):
        self.requests.append({"endpoint": endpoint, "host": url.split("/")[2],
                              "path": "/" + url.split("/", 3)[-1],
                              "query": params, "http_status": 200,
                              "response_bytes": 100, "response_sha256": "a" * 64})
        self.total_bytes += 100
        if endpoint == "gamma_events":
            day = params["end_date_min"][:10]
            return [self._event(day, index) for index in range(self.event_counts[day])]
        if endpoint == "data_api_trades":
            condition = params["market"]
            token = str(int(condition[-4:], 16) + 10**70)
            return [{"conditionId": condition, "asset": token, "side": "BUY",
                     "size": 2.0, "price": 0.55, "timestamp": _timestamp(DEFAULT_DATES[0]),
                     "outcome": "A", "outcomeIndex": 0,
                     "transactionHash": "0x" + condition[-16:],
                     "proxyWallet": "not-retained-in-clean-output"}]
        if endpoint == "clob_price_history":
            base = _timestamp(DEFAULT_DATES[0])
            return {"history": [{"t": base, "p": 0.50},
                                {"t": base + 300, "p": 0.52}]}
        raise AssertionError(endpoint)

    def _event(self, day, index):
        marker = int(day.replace("-", "")) + index
        condition = "0x" + f"{marker:064x}"
        token = str(int(condition[-4:], 16) + 10**70)
        slug = f"game-{day}-{index}"
        next_day = date.fromisoformat(day) + timedelta(days=1)
        return {"id": str(marker), "slug": slug, "title": slug,
                "endDate": f"{day}T18:00:00Z", "closed": True,
                "tags": [{"slug": "sports"}, {"slug": "games"}],
                "markets": [{"id": str(marker), "slug": slug, "closed": True,
                             "conditionId": condition,
                             "gameStartTime": f"{day} 18:00:00+00",
                             "outcomes": json.dumps(["A", "B"]),
                             "outcomePrices": json.dumps(["1", "0"]),
                             "clobTokenIds": json.dumps([token, str(int(token) + 1)])}]}


class PolymarketHistoricalCanaryTests(unittest.TestCase):
    def test_builds_minimized_clean_history_without_profile_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "canary"
            report = run_canary(output, client=FakeClient())
            self.assertEqual(report["tables"]["markets"], 5)
            self.assertEqual(report["scope"]["selected_market_dates"], sorted(DEFAULT_DATES))
            self.assertEqual(report["canary_status"],
                             "data_path_pass_terms_review_pending")
            self.assertFalse(report["formal_dataset_ready"])
            trades = pq.read_table(output / "clean" / "trades.parquet")
            self.assertNotIn("proxyWallet", trades.column_names)
            self.assertNotIn("name", trades.column_names)
            self.assertEqual(trades.num_rows, 5)
            evidence = json.loads((output / "controller-evidence.json").read_text())
            self.assertEqual(evidence["whole_markets"], 5)
            self.assertNotIn("per_market", evidence)
            self.assertNotIn("requests", evidence)

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "canary"
            output.mkdir()
            with self.assertRaises(FileExistsError):
                run_canary(output, client=FakeClient())

    def test_inclusive_api_upper_boundary_is_filtered_locally(self):
        client = FakeClient()
        payload = client._event(DEFAULT_DATES[0], 0)
        payload["endDate"] = DEFAULT_DATES[1] + "T00:00:00Z"
        from polymarket_historical_source_canary import _event_candidates
        self.assertEqual(_event_candidates([payload], DEFAULT_DATES[0]), [])

    def test_failed_stream_retention_is_archived_as_a_rejection(self):
        class NoPrices(FakeClient):
            def get(self, endpoint, url, params):
                result = super().get(endpoint, url, params)
                return {"history": []} if endpoint == "clob_price_history" else result

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "canary"
            report = run_canary(output, client=NoPrices())
            self.assertEqual(report["canary_status"], "rejected_by_frozen_plan")
            self.assertEqual(report["checks"]["price_history_nonempty_for_majority"],
                             "fail")
            self.assertTrue((output / "clean-data-report.json").is_file())


if __name__ == "__main__":
    unittest.main()
