import copy
import json
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_rsi import digest
from prepare_tonight_design import verify_dependency_receipt


class PreflightReceiptTests(unittest.TestCase):
    def test_serialization_does_not_invent_dependency_drift(self):
        current={'all_installed_distributions':[('tinker','0.25.0')],'provider_calls':0}
        saved=json.loads(json.dumps({**current,'result_sha256':digest(current)}))
        verify_dependency_receipt(saved,current)

    def test_actual_dependency_drift_is_rejected(self):
        current={'all_installed_distributions':[('tinker','0.25.0')],'provider_calls':0}
        saved={**current,'result_sha256':digest(current)}
        changed=copy.deepcopy(current); changed['all_installed_distributions']=[('tinker','0.26.0')]
        with self.assertRaisesRegex(ValueError,'environment changed'):
            verify_dependency_receipt(saved,changed)

    def test_bad_receipt_hash_is_rejected(self):
        current={'provider_calls':0}
        with self.assertRaises(ValueError):
            verify_dependency_receipt({**current,'result_sha256':'0'*64},current)


if __name__=='__main__':unittest.main()
