import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from historical_direction_fields import direction_contract
from historical_input_compatibility import require_compatible_inputs,verify_addition
from market_rsi import digest,file_hash,fresh_json,load_json
import test_historical_direction_input_extension as fixtures


class CompatibilityTests(unittest.TestCase):
    def prepare(self, root):
        old,new=fixtures.DirectionInputExtensionTests().arrays()
        before=root/'before';after=root/'after';before.mkdir();after.mkdir()
        np.savez_compressed(before/'current-inputs.npz',**old)
        np.savez_compressed(after/'current-inputs.npz',**new)
        a={'complete':True,'labels_present':False,'fresh_holdout':False,'rows':2,'panel_sha256':'p',
           'archive_sha256':file_hash(before/'current-inputs.npz'),'field_names':old['field_names'].tolist()}
        a['result_sha256']=digest(a);fresh_json(before/'input-result.json',a)
        b={'schema':'historical_direction_input_extension_v1','complete':True,'labels_present':False,
           'fresh_holdout':False,'training_admitted':False,'rows':2,'panel_sha256':'p',
           'archive_sha256':file_hash(after/'current-inputs.npz'),'field_names':new['field_names'].tolist(),
           'additive_parent':{'archive_sha256':a['archive_sha256'],'result_sha256':a['result_sha256'],'field_names':a['field_names']},
           'source_extension':{'direction_contract':direction_contract()},'compatibility':verify_addition(old,new)}
        b['result_sha256']=digest(b);fresh_json(after/'input-result.json',b)
        return before,after,new

    def test_exact_and_explicit_additive_inputs_only(self):
        with tempfile.TemporaryDirectory() as directory:
            before,after,_=self.prepare(Path(directory))
            self.assertEqual(require_compatible_inputs(before,before)['kind'],'identical')
            result=require_compatible_inputs(before,after)
            self.assertEqual(result['kind'],'additive_reported_direction_only')
            self.assertEqual(result['original_fields'],2)
            with self.assertRaises(ValueError):require_compatible_inputs(after,before)

    def test_rehashing_changed_old_values_cannot_bypass_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            before,after,new=self.prepare(Path(directory))
            new['values'][0,0]=.6;np.savez_compressed(after/'current-inputs.npz',**new)
            report=load_json(after/'input-result.json');del report['result_sha256']
            report['archive_sha256']=file_hash(after/'current-inputs.npz');report['result_sha256']=digest(report)
            (after/'input-result.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'byte-identical'):require_compatible_inputs(before,after)

    def test_alternative_parent_or_semantics_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            before,after,_=self.prepare(Path(directory))
            report=load_json(after/'input-result.json');del report['result_sha256']
            report['additive_parent']['result_sha256']='changed';report['result_sha256']=digest(report)
            (after/'input-result.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'ancestry'):require_compatible_inputs(before,after)


if __name__=='__main__':unittest.main()
