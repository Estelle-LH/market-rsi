import unittest

from memory_policy.source_preflight import selected_sources, source_path, validate_complete


def manifest():
    return {
        "initial_train": [{"session": "2026-01-01T00", "compressed_bytes": 1}],
        "dev": [{"session": "2026-01-02T00", "compressed_bytes": 2}],
        "final": [{"session": "2026-01-03T00", "compressed_bytes": 3}],
    }


def report(row):
    return {
        "complete": True,
        "session": row["session"],
        "role": row["role"],
        "advertised_bytes": row["compressed_bytes"],
        "receipt": {
            "complete": True,
            "compressed_bytes": row["compressed_bytes"],
            "json_object_records": 1,
            "raw_rows_exported": 0,
            "target_statistics_computed": 0,
            "provider_calls": 0,
        },
    }


class SourcePreflightTests(unittest.TestCase):
    def test_requires_every_unique_role_source(self):
        rows = selected_sources(manifest())
        self.assertEqual([row["role"] for row in rows], ["initial_train", "dev", "final"])
        self.assertTrue(validate_complete(manifest(), [report(row) for row in rows]))
        with self.assertRaises(ValueError):
            validate_complete(manifest(), [report(row) for row in rows[:-1]])

    def test_duplicate_and_bad_receipt_are_rejected(self):
        value = manifest()
        value["final"][0]["session"] = value["dev"][0]["session"]
        with self.assertRaises(ValueError):
            selected_sources(value)
        value = manifest()
        rows = selected_sources(value)
        reports = [report(row) for row in rows]
        reports[-1]["receipt"]["provider_calls"] = 1
        with self.assertRaises(ValueError):
            validate_complete(value, reports)

    def test_session_cannot_escape_frozen_source_directory(self):
        self.assertEqual(source_path("2026-01-01T00"),
            "/opt/d10/raw/data/polymarket/polymarket-20260101T00.jsonl.zst")
        for value in ("2026-1-1T00", "../../tmp/x", "2026-01-01T99"):
            with self.assertRaises(ValueError):
                source_path(value)


if __name__ == "__main__":
    unittest.main()
