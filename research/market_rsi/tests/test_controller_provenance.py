from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from controller_provenance import (SOURCE_NAMES, freeze_source_manifest,
                                   validate_source_manifest)
from market_rsi import canonical


class ControllerProvenanceTests(unittest.TestCase):
    def test_complete_source_set_freezes_and_validates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            manifest = freeze_source_manifest(path)
            self.assertEqual(set(manifest["sources"]), set(SOURCE_NAMES))
            self.assertEqual(validate_source_manifest(path), manifest)

    def test_manifest_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            manifest = freeze_source_manifest(path)
            manifest["sources"][SOURCE_NAMES[0]] = "0" * 64
            path.write_text(canonical(manifest))
            with self.assertRaisesRegex(ValueError, "source changed"):
                validate_source_manifest(path)


if __name__ == "__main__":
    unittest.main()
