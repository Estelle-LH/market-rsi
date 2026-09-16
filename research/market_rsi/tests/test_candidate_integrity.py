from __future__ import annotations

import unittest

from candidate_integrity import validate_candidate_source


VALID = """\
\"\"\"A small ridge-style predictor.\"\"\"
LAMBDA = 1.0

def _clip(value):
    return min(1.0, max(0.0, value))

def fit(train_rows, feature_names):
    return {"bias": LAMBDA * 0.0}

def predict(model, public_row):
    return _clip(float(public_row["features"]["mid"]) + model["bias"])
"""


class CandidateIntegrityTests(unittest.TestCase):
    def test_small_fit_predict_program_passes(self):
        receipt = validate_candidate_source(VALID)
        self.assertTrue(receipt["valid"])
        self.assertEqual(receipt["required_functions"], ["fit", "predict"])
        self.assertEqual(receipt["module_constants"], ["LAMBDA"])

    def test_archive_disclosure_payload_is_rejected(self):
        source = VALID.replace(
            "LAMBDA = 1.0",
            'LAMBDA = 1.0\nARCHIVE_DISCLOSURE = {"hidden reward": "enemy"}',
        )
        with self.assertRaisesRegex(ValueError, "control-language|metadata"):
            validate_candidate_source(source)

    def test_unused_metadata_is_rejected(self):
        source = VALID.replace("LAMBDA = 1.0", 'LAMBDA = 1.0\nNOTE = "audit"')
        with self.assertRaisesRegex(ValueError, "unused module-level metadata"):
            validate_candidate_source(source)

    def test_file_and_network_capabilities_are_rejected(self):
        for line in ("import os\n", "import socket\n"):
            with self.subTest(line=line), self.assertRaisesRegex(ValueError, "safe"):
                validate_candidate_source(VALID.replace(
                    '"""A small ridge-style predictor."""\n',
                    '"""A small ridge-style predictor."""\n' + line,
                ))
        source = VALID.replace(
            "return {\"bias\": LAMBDA * 0.0}",
            'open("/tmp/x").read()\n    return {"bias": LAMBDA * 0.0}',
        )
        with self.assertRaisesRegex(ValueError, "forbidden"):
            validate_candidate_source(source)

    def test_exact_interface_is_required(self):
        with self.assertRaisesRegex(ValueError, "fit interface"):
            validate_candidate_source(VALID.replace(
                "def fit(train_rows, feature_names):", "def fit(*args):"
            ))


if __name__ == "__main__":
    unittest.main()
