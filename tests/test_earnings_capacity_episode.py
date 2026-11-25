"""Prospective scope parsing on invented receipts; no authority or provider."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import earnings_entry as entry
import earnings_loop_policy as p


class CapacityEpisodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve()
        (self.base/'source').mkdir();(self.base/'source/x.py').write_text('pass\n')
        self.root=self.base/'earnings-coevolution-plan-20261013/episodes/earnings-coevolution-20261013-fixture'
        self.study={'schema':'earnings_coevolution_study_v1','new_live_grant':None,'new_episode_deadline':None,
            'closed_episode':{'reopen':False,'status':'completed_bounded_overnight','binding':{'path':'fixture-old','sha256':'a'*64}},
            'cases':[{'cik':'fixture-cik'}]}
        kernel={'scorer':{'path':'fixture-scorer','sha256':'e'*64},'qa':{'path':'fixture-qa','sha256':'f'*64}}
        self.study['scorer']=kernel['scorer']
        self.study['cases'][0]['evaluation_kernel']=kernel
        self.envelope={'schema':'earnings_capacity_episode_v1','id':self.root.name,'mode':'offline_replay',
            'source_commit':'b'*40,'sources':{'x.py':hashlib.sha256(b'pass\n').hexdigest()},
            'study':{'path':'fixture-study','sha256':'c'*64},'root':str(self.root),'cik':'fixture-cik','max_rounds':2,
            'role_limits':{'controller':dict(p.LIMITS),'author':dict(p.LIMITS),'review':dict(p.LIMITS)},
            'slots':[{role:str(self.root/'roles'/f'{role}-{n}') for role in ('controller','author','review','forecast')} for n in (1,2)],
            'initial_state':{'path':'fixture-empty','sha256':'d'*64},'grant':None,'window':None,'evaluation_kernel':kernel}
        self.calls=[]
        def read(binding,*unused):
            self.calls.append(binding['path'])
            return deepcopy(self.study) if binding['path']=='fixture-study' else {'status':'completed'}
        patches=[patch.object(entry,'PILOT',self.base/'edgar/pilot'),patch.object(entry,'REPO',self.base/'source'),
            patch.object(p,'_read',side_effect=read),patch.object(entry,'checked',return_value=b'fixture'),patch.object(p,'capacity_sources',return_value=['x.py']),
            patch.object(p.subprocess,'run',return_value=type('Git',(),{'stdout':b'pass\n'})())]
        for fixture in patches:
            fixture.start();self.addCleanup(fixture.stop)

    def test_exact_new_offline_scope_and_independent_role_slots(self):
        self.assertEqual(p.validate_capacity_episode(self.envelope),self.study)
        self.assertEqual(self.calls,['fixture-study','fixture-old','fixture-qa'])

    def test_live_grant_window_and_old_id_cannot_be_reopened(self):
        for field,value in (('mode','live'),('grant',{'authorized':True}),('window',{'deadline':'2099-01-01'}),
                            ('id','earnings-feedback-recovery-01'),('max_rounds',4),('max_rounds',True)):
            with self.subTest(field=field),self.assertRaises(ValueError):
                p.validate_capacity_episode(dict(self.envelope,**{field:value}))
        self.assertEqual(self.calls,[])

    def test_scope_extra_fields_case_role_caps_and_slots_refused(self):
        for field,value in (('model','upgrade'),('cik','other'),('slots',[self.envelope['slots'][0]]*2),
                            ('root',str(self.base/'old-attempt')),('role_limits',{'controller':{'wall_seconds':9999}})):
            with self.subTest(field=field),self.assertRaises(ValueError):
                p.validate_capacity_episode(dict(self.envelope,**{field:value}))

    def test_changed_source_and_incomplete_source_closure_refused(self):
        with self.assertRaises(ValueError):
            p.validate_capacity_episode(dict(self.envelope,sources={}))
        (self.base/'source/x.py').write_text('changed\n')
        with self.assertRaisesRegex(ValueError,'source differs'):
            p.validate_capacity_episode(self.envelope)

    def test_original_closed_study_stays_closed(self):
        self.study['closed_episode']['reopen']=True
        with self.assertRaises(ValueError):p.validate_capacity_episode(self.envelope)

    def test_entry_source_failure_occurs_before_credentials_or_dispatch(self):
        with patch.object(entry,'credential') as key,patch.object(entry,'RawOpenAIHTTP') as transport:
            with self.assertRaises(ValueError):entry.preflight_capacity_episode(dict(self.envelope,mode='live'),for_live=True)
            key.assert_not_called();transport.assert_not_called()


if __name__=='__main__':unittest.main()
