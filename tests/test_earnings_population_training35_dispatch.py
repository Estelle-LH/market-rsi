"""New attachment marker must not reach legacy recursion when tags are erased.

Original _study and the existing temporary RuntimeFixture are used. The only
new sentinels deny initial pool validation and task-body admission; there are
no actual training/heldout files, paid calls, real ledger or Native evidence.
"""
from copy import deepcopy
from unittest.mock import patch
import unittest

import earnings_population_runtime as runtime
from test_earnings_population_runtime import Fixture, save


class AttachmentEarlyDispatch(Fixture):
    def test_surviving_attachment_without_training_tags_refused_before_legacy_pool(self):
        for attachment in (None, {}, {'path': str(self.home/'missing.json'), 'sha256': 'f'*64}):
            with self.subTest(attachment=attachment):
                study = dict(deepcopy(self.study), training_stage_attachment=attachment)
                value = dict(deepcopy(self.value), forecast_study=save(self.owned/'study-with-attachment.json', study))
                original_local = runtime._local
                def metadata_only(bound):
                    if bound == value['initial_population']:
                        raise AssertionError('Forbidden initial-state body read')
                    return original_local(bound)
                with patch.object(runtime, '_local', side_effect=metadata_only), \
                     patch.object(runtime.pool, 'validate', side_effect=AssertionError('Forbidden legacy pool recursion')) as pool, \
                     patch.object(runtime.tasks, 'resident', side_effect=AssertionError('Forbidden task body')) as resident:
                    with self.assertRaisesRegex(ValueError, 'Exact forward training task/link and model budget required'):
                        runtime._study(value)
                pool.assert_not_called()
                resident.assert_not_called()

    def test_plain_legacy_study_keeps_original_route_without_attachment(self):
        cases = runtime._study(deepcopy(self.value))
        self.assertEqual(cases, self.original)


if __name__ == '__main__':
    unittest.main()
