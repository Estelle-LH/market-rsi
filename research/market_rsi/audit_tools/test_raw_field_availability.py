import unittest
import numpy as np
from audit_raw_field_availability import flag_counts


class FlagTests(unittest.TestCase):
    def test_valid_zero_one_are_not_missing(self):
        self.assertEqual(flag_counts(np.array([0,1,1])),{'zero':1,'one':2,'missing':0,'invalid':0})

    def test_missing_and_invalid_stay_distinct(self):
        self.assertEqual(flag_counts(np.array([np.nan,np.inf,-1.,2.,.5])),
                         {'zero':0,'one':0,'missing':1,'invalid':4})


if __name__=='__main__':unittest.main()
