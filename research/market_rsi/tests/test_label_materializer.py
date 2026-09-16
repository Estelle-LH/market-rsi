import gzip
import json
import tempfile
import unittest
from pathlib import Path

from label_materializer import LabelBuilder, LabelPolicy, materialize_diagnostic
from market_rsi import file_hash, fresh_json, load_json


def policy(**overrides):
    values = dict(horizon_ms=100, latency_ms=10, max_entry_lateness_ms=20,
                  max_label_lateness_ms=20, max_quote_gap_ms=1000, decision_interval_ms=10000)
    values.update(overrides)
    return LabelPolicy(**values)


def quote(t=1000, line=0, **overrides):
    row = dict(source_key=[0, line], receive_ms=t, sid=1, seq=line + 1, stream_epoch=0,
               market_id="a", anchor_key=[0, 0], anchor_ms=1000, quote_segment=0,
               bid_1e4=4000, ask_1e4=5000, bid_size_1e2=1000, ask_size_1e2=2000)
    row.update(overrides)
    return row


class LabelTests(unittest.TestCase):
    def builder(self, **kw):
        return LabelBuilder(policy(**kw), {"a": "game-a"}, ["a" * 64, "b" * 64])

    def test_numeric_labels_are_separate_from_decision_features(self):
        b = self.builder()
        b.accept(quote())
        b.accept(quote(1010, 1, bid_1e4=4100, ask_1e4=5100))
        rows = b.accept(quote(1110, 2, bid_1e4=4500, ask_1e4=5500))
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["features"]["mid"], 0.45)
        self.assertAlmostEqual(r["labels"]["mid_change"], 0.05)
        self.assertAlmostEqual(r["labels"]["buy_yes_gross_price_change"], -0.06)
        self.assertAlmostEqual(r["labels"]["buy_no_gross_price_change"], -0.14)
        self.assertEqual(r["feature_available_ms"], 1000)
        self.assertEqual(r["label_available_ms"], 1110)
        self.assertNotIn("labels", r["features"])
        self.assertNotEqual(r["input_source"], r["label_source"])

    def test_first_eligible_future_observation_not_best_future_price(self):
        b = self.builder()
        b.accept(quote())
        b.accept(quote(1010, 1))
        self.assertEqual(b.accept(quote(1109, 2)), [])
        first = b.accept(quote(1112, 3))
        self.assertEqual(first[0]["label_end_ms"], 1112)
        self.assertEqual(b.accept(quote(1113, 4, bid_1e4=7000, ask_1e4=8000)), [])

    def test_changing_future_does_not_change_decision_features_or_identity(self):
        rows = []
        for bid, ask in ((2000, 3000), (6000, 7000)):
            b = self.builder()
            b.accept(quote())
            b.accept(quote(1010, 1))
            rows.append(b.accept(quote(1110, 2, bid_1e4=bid, ask_1e4=ask))[0])
        self.assertEqual(rows[0]["features"], rows[1]["features"])
        self.assertEqual(rows[0]["row_id"], rows[1]["row_id"])
        self.assertNotEqual(rows[0]["labels"], rows[1]["labels"])

    def test_real_replay_one_sided_gap_never_becomes_training_label(self):
        from kalshi_replay import Replay
        replay, builder = Replay("yes_asks"), self.builder()
        records = [
            {"t": 1000, "m": {"type": "orderbook_snapshot", "sid": 1, "seq": 1,
             "msg": {"market_ticker": "a", "yes_dollars_fp": [["0.4000", "10.00"]],
                     "no_dollars_fp": [["0.5000", "20.00"]]}}},
        ]
        for seq, t, delta in ((2, 1005, "-10.00"), (3, 1010, "10.00"), (4, 1110, "1.00")):
            records.append({"t": t, "m": {"type": "orderbook_delta", "sid": 1, "seq": seq,
                "msg": {"market_ticker": "a", "side": "yes", "price_dollars": "0.4000",
                        "delta_fp": delta}}})
        emitted = []
        for i, record in enumerate(records):
            q = replay.accept(record, [0, i])
            if q is not None:
                emitted.extend(builder.accept(q))
        self.assertEqual(emitted, [])
        self.assertEqual(builder.finish()["continuity_break"], 1)

    def test_capture_tail_is_censored_not_zero_return(self):
        b = self.builder()
        b.accept(quote())
        b.accept(quote(1010, 1))
        summary = b.finish()
        self.assertEqual(summary["capture_tail_censored"], 1)
        self.assertEqual(summary.get("labeled_rows", 0), 0)
        self.assertEqual(summary, b.finish())
        with self.assertRaises(ValueError):
            b.accept(quote(1110, 2))

    def test_entry_lateness_censors(self):
        b = self.builder()
        b.accept(quote())
        self.assertEqual(b.accept(quote(1031, 1)), [])
        self.assertEqual(b.counts["entry_endpoint_late"], 1)

    def test_label_lateness_censors(self):
        b = self.builder()
        b.accept(quote())
        b.accept(quote(1010, 1))
        self.assertEqual(b.accept(quote(1131, 2)), [])
        self.assertEqual(b.counts["label_endpoint_late"], 1)

    def test_gap_cannot_be_filled_with_last_quote(self):
        b = self.builder(max_quote_gap_ms=50)
        b.accept(quote())
        b.accept(quote(1010, 1))
        self.assertEqual(b.accept(quote(1110, 2)), [])
        self.assertEqual(b.counts["quote_gap"], 1)

    def test_all_continuity_barriers_censor_pending_labels(self):
        for change in ({"sid": 2}, {"stream_epoch": 1}, {"quote_segment": 1},
                       {"anchor_key": [0, 1], "anchor_ms": 1010}):
            with self.subTest(change=change):
                b = self.builder()
                b.accept(quote())
                b.accept(quote(1010, 1))
                self.assertEqual(b.accept(quote(1110, 2, **change)), [])
                self.assertEqual(b.counts["continuity_break"], 1)

    def test_cross_file_valid_continuity_is_preserved(self):
        b = self.builder()
        b.accept(quote())
        b.accept(quote(1010, 1))
        r = b.accept(quote(1110, 2, source_key=[1, 0]))[0]
        self.assertEqual(r["label_source"], {"sha256": "b" * 64, "ordinal": 0})

    def test_repeated_timestamp_keeps_source_order(self):
        b = self.builder()
        b.accept(quote())
        b.accept(quote(1000, 1))
        with self.assertRaises(ValueError):
            b.accept(quote(1000, 1))

    def test_time_reversal_rejected(self):
        b = self.builder()
        b.accept(quote())
        with self.assertRaises(ValueError):
            b.accept(quote(999, 1))

    def test_zero_latency_uses_only_decision_quote_for_entry(self):
        b = self.builder(latency_ms=0)
        b.accept(quote())
        row = b.accept(quote(1100, 1))[0]
        self.assertEqual(row["entry_source"], row["input_source"])
        self.assertNotEqual(row["label_source"], row["input_source"])

    def test_sampling_count_does_not_depend_on_price_moves(self):
        summaries = []
        for price in (4000, 6000):
            b = self.builder(decision_interval_ms=100)
            for i, t in enumerate(range(1000, 1400, 10)):
                b.accept(quote(t, i, bid_1e4=price, ask_1e4=price + 1000))
            summaries.append(b.finish())
        self.assertEqual(summaries[0], summaries[1])
        self.assertEqual(summaries[0]["scheduled_decisions"], 4)

    def test_bad_policy_or_quote_schema_rejected(self):
        for kwargs in ({"horizon_ms": 0}, {"latency_ms": True},
                       {"max_entry_lateness_ms": 100}, {"decision_interval_ms": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                policy(**kwargs)
        bad = quote()
        del bad["quote_segment"]
        with self.assertRaises(ValueError):
            self.builder().accept(bad)

    def test_unknown_markets_not_reassigned(self):
        b = self.builder()
        self.assertEqual(b.accept(quote(market_id="b")), [])
        self.assertEqual(b.counts["outside_frozen_market_map"], 1)
        self.assertEqual(b.finish().get("scheduled_decisions", 0), 0)


class FileTests(unittest.TestCase):
    def source(self, root):
        replay = root / "replay"
        replay.mkdir()
        quotes = replay / "quotes.jsonl.gz"
        with gzip.open(quotes, "xt") as f:
            for row in (quote(), quote(1010, 1), quote(1110, 2)):
                f.write(json.dumps(row) + "\n")
        fresh_json(replay / "report.json", {"quotes_sha256": file_hash(quotes),
                   "sources": [{"sha256": "a" * 64}]})
        spec = root / "spec.json"
        fresh_json(spec, {"schema": "market_labels_v1", "evidence_class": "fixture",
                   "policy": policy().__dict__, "market_games": {"a": "game-a"}})
        return replay, spec

    def test_exclusive_diagnostic_artifact_with_numeric_labels(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            replay, spec = self.source(root)
            out = root / "labels-01"
            report = materialize_diagnostic(replay, spec, out)
            self.assertEqual(report["counts"]["labeled_rows"], 1)
            self.assertFalse(report["scoring_ready"])
            self.assertFalse(report["research_result"])
            self.assertFalse(report["net_pnl_computed"])
            self.assertEqual(out.stat().st_mode & 0o777, 0o700)
            with gzip.open(out / "runner-labels.jsonl.gz", "rt") as f:
                rows = [json.loads(line) for line in f]
            self.assertEqual(len(rows), 1)
            with self.assertRaises(FileExistsError):
                materialize_diagnostic(replay, spec, out)

    def test_mutated_quote_file_rejected_before_claim(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            replay, spec = self.source(root)
            with (replay / "quotes.jsonl.gz").open("ab") as f:
                f.write(b"changed")
            with self.assertRaises(ValueError):
                materialize_diagnostic(replay, spec, root / "out")
            self.assertFalse((root / "out").exists())

    def test_old_replay_schema_preserves_failure_not_completion(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            replay, spec = self.source(root)
            bad = quote()
            del bad["quote_segment"]
            with gzip.open(replay / "quotes.jsonl.gz", "wt") as f:
                f.write(json.dumps(bad) + "\n")
            report = load_json(replay / "report.json")
            report["quotes_sha256"] = file_hash(replay / "quotes.jsonl.gz")
            (replay / "report.json").write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                materialize_diagnostic(replay, spec, root / "out")
            self.assertTrue((root / "out" / "claim.json").exists())
            self.assertTrue((root / "out" / "failure.json").exists())
            self.assertFalse((root / "out" / "complete.json").exists())


if __name__ == "__main__":
    unittest.main()
