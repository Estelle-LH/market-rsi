import unittest
from audit_source_review_v2_result import require_completed


class CompletedV2Tests(unittest.TestCase):
    def test_only_completed_actual_v2_is_accepted(self):
        a={'schema':'historical_source_review_v2_controller_assessment_v1','controller_stage':'source_review_v2',
            'valid':True,'process_reaped':True,'failed':False,'evidence_mode':'paid_controller','model_authorship_proven':True}
        require_completed(a)
        for k,v in [('schema','old'),('controller_stage','source_review'),('valid',False),
                    ('process_reaped',False),('failed',True),('evidence_mode','synthetic_transport_fixture'),
                    ('model_authorship_proven',False)]:
            with self.subTest(field=k),self.assertRaises(ValueError):require_completed({**a,k:v})


if __name__=='__main__':unittest.main()
