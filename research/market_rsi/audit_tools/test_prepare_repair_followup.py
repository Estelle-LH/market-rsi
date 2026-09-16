from pathlib import Path
import tempfile
import unittest
from market_rsi import digest, fresh_json
from prepare_repair_followup import evidence


class EvidenceTests(unittest.TestCase):
    def test_digest_and_no_admission_required(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'evidence.json'
            r = {'source_admitted': False, 'fits': 0}
            r['result_sha256'] = digest(r); fresh_json(path, r)
            self.assertFalse(evidence(path)['report']['source_admitted'])
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'digest changed'): evidence(path)

    def test_self_declared_admission_not_imported(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'evidence.json'
            r = {'source_admitted': True, 'fits': 0}
            r['result_sha256'] = digest(r); fresh_json(path, r)
            with self.assertRaisesRegex(ValueError, 'no empirical'): evidence(path)


if __name__ == '__main__': unittest.main()
