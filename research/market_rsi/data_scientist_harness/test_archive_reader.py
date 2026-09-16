import json
from pathlib import Path
import tempfile
import unittest
from market_rsi import fresh_json,load_json
from data_scientist_harness import archive_reader


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.body={'schema':'data_scientist_round_archive_v1','session_id':'old','text':'旧记录'*20000}
        fresh_json(self.root/'archive-input.json',{'prior_rounds':[{'origin':{'path':'old.json','sha256':'a'*64},
            'history_not_current_evidence':self.body}]})
    def tearDown(self):self.tmp.cleanup()
    def test_index_keeps_origin_not_full_body(self):
        v=archive_reader.index(self.root);self.assertTrue(v['full_history_preserved'])
        self.assertFalse(v['bodies_delivered']);self.assertNotIn('旧记录',json.dumps(v,ensure_ascii=False))
    def test_every_page_reconstructs_entire_archive(self):
        offset=0;parts=[]
        while True:
            v=archive_reader.read(self.root,0,offset);parts.append(v['text'])
            self.assertLessEqual(len(v['text']),12000);self.assertFalse(v['source_admitted'])
            if v['end']==v['total_characters']:break
            offset=v['end']
        self.assertEqual(json.loads(''.join(parts)),self.body)
        self.assertEqual(load_json(self.root/'archive-input.json')['prior_rounds'][0]['history_not_current_evidence'],self.body)
    def test_invalid_index_offset_and_bool_rejected(self):
        for i,o in ((-1,0),(1,0),(True,0),(0,-1),(0,999999),(0,False)):
            with self.assertRaises(ValueError):archive_reader.read(self.root,i,o)
    def test_no_arbitrary_path_parameter(self):
        with self.assertRaises(ValueError):archive_reader.read(self.root,'/etc/passwd',0)
    def test_read_tool_is_served_and_does_not_count_as_public_research(self):
        from data_scientist_harness.broker import TOOLS
        schema=next(t['inputSchema'] for t in TOOLS if t['name']=='read_archive')
        self.assertEqual(set(schema['required']),{'archive_index','offset'})
        self.assertFalse(schema['additionalProperties'])


if __name__=='__main__':unittest.main()
