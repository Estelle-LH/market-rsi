"""Compact operational history survives genuine later completed rounds."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from earnings_population_completed import _delivery_lessons


class ForecastDeliveryLessonTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='forecast-lesson-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        self.recovery = dict(schema='earnings_population_delivery_failure_v1',
            mode='reviewed_candidate_forecast_deadline_failure_v1',
            failed_attempt={'path':str(root/'failure.json'),'sha256':'a'*64},
            audit={'path':str(root/'audit.json'),'sha256':'b'*64},stage='execute',
            error_type='BudgetStop', company_wall_seconds=1800,observed_wall_seconds=1799.8469,
            completed_forecast_generations=19,review_assessment='accepted_for_exploration',
            score_state='unscored',candidate_id='c'*64,probes=[{'do_not_copy':'large body'}],
            previous_delivery_failure={'do_not_copy':'nested history'},scope='already replayed fixture')

    def initial(self):
        return _delivery_lessons(dict(author_stage_reuse={'explicit_fixture':True},
                                      recovery_context=deepcopy(self.recovery)))

    def test_compact_lesson_survives_two_subsequent_completed_origins_without_active_reuse(self):
        lessons = self.initial()
        self.assertEqual(len(lessons),1)
        self.assertEqual(lessons[0]['failed_attempt'],self.recovery['failed_attempt'])
        self.assertEqual(lessons[0]['score_state'],'unscored')
        self.assertNotIn('probes',lessons[0]);self.assertNotIn('previous_delivery_failure',lessons[0])
        for _ in range(2):
            next_lessons = _delivery_lessons({'delivery_lessons':deepcopy(lessons)})
            self.assertEqual(next_lessons,lessons)
            self.assertNotIn('author_stage_reuse',next_lessons[0])
            self.assertNotIn('review_stage_reuse',next_lessons[0])
            lessons = next_lessons

    def test_duplicate_same_origin_deduplicates_but_conflicting_origin_refuses(self):
        lesson = self.initial()[0]
        self.assertEqual(_delivery_lessons({'delivery_lessons':[lesson,deepcopy(lesson)]}),[lesson])
        conflict = dict(lesson,completed_forecast_generations=18)
        with self.assertRaisesRegex(ValueError,'Conflicting duplicate'):
            _delivery_lessons({'delivery_lessons':[lesson,conflict]})

    def test_no_fake_score_quality_or_unbounded_raw_content_can_be_carried(self):
        lesson = self.initial()[0]
        for key,value in (('score_state','scored'),('review_assessment','rejected'),
                          ('company_wall_seconds',1801),('company_wall_seconds',1800.0),
                          ('observed_wall_seconds',float('nan')),('observed_wall_seconds',True),
                          ('completed_forecast_generations',True),('completed_forecast_generations',25),
                          ('stage','source_review'),('source_text','unbounded code')):
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                _delivery_lessons({'delivery_lessons':[dict(lesson,**{key:value})]})


if __name__ == '__main__':unittest.main()
