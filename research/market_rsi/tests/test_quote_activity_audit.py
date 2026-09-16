import unittest

import pyarrow as pa

from quote_activity_audit import audit_activity


def row(i, **changes):
    result = dict(id=i, market_slug="m", asset_id="yes", ingest_ts_ms=i * 10,
                  source_ts_ms=i * 10 - 1, event_type="price_change",
                  side_label="buy", price=0.4, size=100., best_bid=0.4, best_ask=0.6)
    result.update(changes)
    return result


class QuoteActivityAuditTests(unittest.TestCase):
    def test_flat_quote_does_not_mean_no_information(self):
        result = audit_activity(pa.Table.from_pylist([
            row(1), row(2, size=200.), row(3, size=200.), row(4, best_bid=0.5)]))
        self.assertEqual(result["best_quote_unchanged"], 2)
        self.assertEqual(result["unchanged_quote_but_other_payload_changed"], 1)
        self.assertEqual(result["unchanged_quote_and_visible_payload"], 1)
        self.assertEqual(result["best_quote_changed"], 1)
        self.assertEqual(result["repeated_row_ids"], 0)
        self.assertEqual(result["rows_removed"], 0)

    def test_never_compare_different_tokens_or_markets(self):
        result = audit_activity(pa.Table.from_pylist([
            row(1), row(2, asset_id="no"), row(3, market_slug="other")]))
        self.assertEqual(result["streams"], 3)
        self.assertEqual(result["within_stream_transitions"], 0)
        self.assertIsNone(result["unchanged_best_quote_fraction"])

    def test_missing_quotes_are_not_called_flat(self):
        result = audit_activity(pa.Table.from_pylist([row(1), row(2, best_bid=None)]))
        self.assertEqual(result["best_quote_unchanged"], 0)
        self.assertEqual(result["incomplete_quote_transitions"], 1)

    def test_unused_future_labels_cannot_change_audit(self):
        table = pa.Table.from_pylist([row(1), row(2)])
        a = table.append_column("future_return", pa.array([0., 0.]))
        b = table.append_column("future_return", pa.array([1., -1.]))
        self.assertEqual(audit_activity(a), audit_activity(b))

    def test_input_is_not_modified(self):
        table = pa.Table.from_pylist([row(3), row(1), row(2)])
        original = table.to_pylist()
        audit_activity(table)
        self.assertEqual(table.to_pylist(), original)

    def test_equal_clock_ties_are_reported(self):
        result = audit_activity(pa.Table.from_pylist([row(1), row(2, ingest_ts_ms=10)]))
        self.assertEqual(result["same_receive_timestamp_transitions"], 1)

    def test_duplicate_identity_is_not_silently_dropped(self):
        with self.assertRaisesRegex(ValueError, "repeated row IDs"):
            audit_activity(pa.Table.from_pylist([row(1), row(1)]))

    def test_nonfinite_values_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-finite"):
            audit_activity(pa.Table.from_pylist([row(1), row(2, price=float("nan"))]))

    def test_single_row(self):
        result = audit_activity(pa.Table.from_pylist([row(1)]))
        self.assertEqual(result["streams"], 1)
        self.assertEqual(result["within_stream_transitions"], 0)


if __name__ == "__main__":
    unittest.main()
