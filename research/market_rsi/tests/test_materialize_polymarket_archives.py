import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from materialize_polymarket_archives import load_days


class ArchiveMaterializerTests(unittest.TestCase):
    def test_archive_hashes_are_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            day = Path(tmp) / "2026-09-01"
            day.mkdir()
            files = []
            for name in ("event_changes.jsonl.gz", "book_observations.jsonl.gz"):
                path = day / name
                with gzip.open(path, "wb") as stream:
                    stream.write(b"{}\n")
                raw = path.read_bytes()
                files.append({"archive": name, "archive_sha256": hashlib.sha256(raw).hexdigest(),
                              "content_sha256": hashlib.sha256(b"{}\n").hexdigest(),
                              "original_bytes": 3, "compressed_bytes": len(raw)})
            (day / "archive_manifest.json").write_text(json.dumps({
                "schema": "ez-capture-archive.v1", "date": day.name, "files": files}))
            self.assertEqual(load_days(Path(tmp), [day.name])[0]["date"], day.name)
            with (day / "book_observations.jsonl.gz").open("ab") as stream:
                stream.write(b"changed")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                load_days(Path(tmp), [day.name])


if __name__ == "__main__":
    unittest.main()
