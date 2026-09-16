import copy
import json
import unittest
from run_single_object_audit import partial_scope, SELECTED, LIMITS


class ScopeTests(unittest.TestCase):
    def fixture(self):
        text=json.dumps({'exact_objects':[SELECTED],**LIMITS})[:-1]+', "bad": ["item"}}'
        request={'tool':'request_capability','status':'ok','arguments':{'verification_needed':text}}
        inventory={'host':SELECTED['host'],'source_root':SELECTED['source_root'],
            'files':[{'filename':SELECTED['relative_path'],'date':SELECTED['date'],'compressed_bytes':SELECTED['advertised_bytes']}]}
        return request,inventory

    def test_partial_audit_not_silent_json_repair(self):
        r,i=self.fixture();s=partial_scope(r,i)
        self.assertFalse(s['entire_request_executed']);self.assertFalse(s['label_rules_executed'])
        self.assertFalse(s['original_request_json_valid']);self.assertEqual(s['object'],SELECTED)
        with self.assertRaises(json.JSONDecodeError):json.loads(r['arguments']['verification_needed'])

    def test_other_file_size_or_host_refused(self):
        for old,new in [(SELECTED['relative_path'],'other.zst'),(SELECTED['host'],'other-host'),('13166507','13166508')]:
            r,i=self.fixture();r['arguments']['verification_needed']=r['arguments']['verification_needed'].replace(old,new)
            with self.assertRaises(ValueError):partial_scope(r,i)

    def test_duplicate_object_field_refused(self):
        r,i=self.fixture();r['arguments']['verification_needed']+=' "exact_objects": []'
        with self.assertRaises(ValueError):partial_scope(r,i)

    def test_inventory_mismatch_refused(self):
        r,i=self.fixture();i['files'][0]['compressed_bytes']+=1
        with self.assertRaises(ValueError):partial_scope(r,i)

    def test_no_unreviewed_scope_on_corrected_json(self):
        r,i=self.fixture();r['arguments']['verification_needed']=json.dumps({'exact_objects':[SELECTED],**LIMITS})
        with self.assertRaises(ValueError):partial_scope(r,i)


if __name__=='__main__':unittest.main()
