"""Synthetic semantic and clean-process safety probes, no experiment imports."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import replay


class Memory:
    def __init__(self):self.values={};self.manifest={}
    def put(self,key,value):
        bound=dict(path=key,sha256=replay.sha(replay.canonical(value)));self.values[key]=deepcopy(value);return bound
    def json(self,b):return deepcopy(self.values[b['path']])


class RoundBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.b=Memory();self.ids=['CIK%010d'%i for i in range(1,26)];rows=[]
        for i,cik in enumerate(self.ids):
            pred=dict(predictions=[dict(target_id=t,predicted_value='17') for t in replay.TARGETS])
            response=dict(status='completed',error=None,output=[dict(type='message',content=[dict(type='output_text',text=json.dumps(pred))])])
            public=dict(cik=cik,score_out_of_5=3,per_target=[dict(target_id=t,points_awarded=p)
                for t,p in zip(replay.TARGETS,[1,1,1,0,0])])
            result=dict(cik=cik,status='COMPLETED_SCORED',scored_targets=5,points=3)
            rows.append(dict(cik=cik,predictions=self.b.put(cik+'p',pred),final_response=self.b.put(cik+'f',response),
                public_feedback=self.b.put(cik+'a',public),result=self.b.put(cik+'r',result)))
        scope=self.b.put('split',dict(training=self.ids,heldout=['heldout']))
        self.original=self.b.put('original',dict(rows=rows,split=scope))
        summary=self.b.put('summary',dict(sum_points=75,company_equal_mean_out_of5=3,excluded_failed_attempts=[]))
        self.round=dict(original_manifest=self.original,summary=summary,state='fixture')

    def call(self):
        from unittest.mock import patch
        with patch.object(replay,'fees',return_value=dict(synthetic=True)):
            return replay.replay_round0(self.b,self.round)

    def test_full25_scores_and_mean_recomputed(self):
        value=self.call();self.assertEqual((value['scored'],value['targets'],value['total_points'],value['company_equal_mean']),(25,125,75,3))

    def test_duplicate_company_cannot_be_a_complete_round(self):
        rows=self.b.values['original']['rows'];rows[-1]=deepcopy(rows[0])
        with self.assertRaisesRegex(replay.Unverifiable,'Duplicate'):self.call()

    def test_incomplete_coverage_refused_not_zero_filled(self):
        self.b.values['original']['rows'].pop()
        with self.assertRaisesRegex(replay.Unverifiable,'Incomplete'):self.call()

    def test_score_or_final_prediction_substitution_refused(self):
        self.b.values[self.ids[0]+'r']['points']=5
        with self.assertRaisesRegex(replay.Unverifiable,'score mismatch'):self.call()

    def test_wrong_candidate_and_false_closed_state_refused(self):
        baseline=self.call();feedback=dict(rows=[dict(company_id=r['company_id'],points=r['points'],targets=r['targets']) for r in baseline['rows']])
        task=self.b.put('task',dict(mode='proposal',frozen_candidate=None,feedback=self.b.put('feedback',feedback)))
        runtime=self.b.put('runtime',dict(forecast_study=self.b.put('study',dict(clean_slate_task=task))))
        manifest=dict(runtime=runtime,candidate={'id':'false-candidate'},scored=0,state='PROPOSAL_AT_LAUNCH_UNCLOSED_SNAPSHOT',
            decision='INCOMPLETE_NO_SELECTION',physical_run_ids=['fixture-run'],unverifiable=['not executed'])
        with self.assertRaisesRegex(replay.Unverifiable,'Wrong/nonexistent'):replay.replay_clean(self.b,manifest,baseline)
        manifest['candidate']=None;manifest['state']='COMPLETED'
        with self.assertRaisesRegex(replay.Unverifiable,'silently mark'):replay.replay_clean(self.b,manifest,baseline)
        manifest['state']='PROPOSAL_AT_LAUNCH_UNCLOSED_SNAPSHOT';value=replay.replay_clean(self.b,manifest,baseline)
        self.assertIsNone(value['company_equal_mean']);self.assertEqual(value['not_measured'],25)
        self.assertFalse(value['next_mutation_allowed']);self.assertIsNone(value['fees'])


class IntegrityAndSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();(self.root/'objects').mkdir()
        raw=b'original evidence';self.token=replay.sha(raw);self.asset=self.root/'objects'/self.token;self.asset.write_bytes(raw)
        self.value=dict(schema='edgar25_offline_bundle_v1',files={self.token:dict(relative_path='objects/'+self.token,bytes=len(raw),original_paths=['/unavailable/original'])},
            replay_code={'replay.py':dict(sha256=replay.sha(Path(replay.__file__).read_bytes()))},git_objects={},source_proofs=[])
        self.raw=replay.canonical(self.value);(self.root/'manifest.json').write_bytes(self.raw)

    def test_historical_path_is_only_a_mapping_never_a_read(self):
        bundle=replay.Bundle(self.root,replay.sha(self.raw))
        self.assertEqual(bundle.read(dict(path='/unavailable/original',sha256=self.token)),b'original evidence')

    def test_missing_hash_tamper_wrong_manifest_and_path_traversal_refused(self):
        self.asset.write_bytes(b'tampered')
        with self.assertRaisesRegex(replay.Unverifiable,'hash mismatch'):replay.Bundle(self.root,replay.sha(self.raw))
        self.asset.unlink()
        with self.assertRaisesRegex(replay.Unverifiable,'Missing evidence'):replay.Bundle(self.root,replay.sha(self.raw))
        with self.assertRaisesRegex(replay.Unverifiable,'trust-anchor'):replay.Bundle(self.root,'0'*64)

    def test_git_source_proof_rejects_unknown_commit(self):
        self.value['source_proofs']=[dict(commit='0'*40,repository_path='source.py',binding=dict(path='/unavailable/original',sha256=self.token))]
        raw=replay.canonical(self.value);(self.root/'manifest.json').write_bytes(raw)
        self.asset.write_bytes(b'original evidence')
        with self.assertRaisesRegex(replay.Unverifiable,'Missing Git object'):replay.Bundle(self.root,replay.sha(raw))

    def test_clean_subprocess_denies_network_process_write_and_original_path(self):
        for expression in ('__import__("socket").socket()',
                '__import__("subprocess").run(["/bin/echo","forbidden"])',
                'open("/original-workspace/forbidden","rb")',
                'open('+repr(str(self.root/'forbidden-write'))+',"wb")'):
            script='import sys;sys.path.insert(0,'+repr(str(Path(replay.__file__).parent))+');import replay;replay.offline_guard('+repr(str(self.root))+');'+expression
            result=subprocess.run([sys.executable,'-I','-B','-c',script],capture_output=True,text=True,timeout=15)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Unverifiable',result.stderr)
        self.assertFalse((self.root/'forbidden-write').exists())


if __name__=='__main__':unittest.main()
