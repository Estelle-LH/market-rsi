"""Exact forecast-only successor authority; no real ledger, clock or provider."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_open_fresh_grant as fresh
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_author24_grant as previous
import test_earnings_author24_output as previous_entry
import earnings_open_author_followthrough as flow


class Forecast26GrantTests(unittest.TestCase):
    def setUp(self):
        self.old = previous.Author24GrantTests()
        self.old.setUp()
        self.addCleanup(self.old.doCleanups)
        self.fixture = self.old.old.old.f
        self.root = self.fixture.home
        guard = patch.object(fresh, 'ROOT', self.root)
        guard.start()
        self.addCleanup(guard.stop)
        self.body = deepcopy(self.old.body)
        review = {'verdict': 'PASS_NATIVE25_FAILURE_CLOSURE_NO_RETRY',
                  'reviewer': 'independent-synthetic-reviewer', 'blocking_findings': [],
                  'closed_forecast_review': deepcopy(fresh.FORECAST25_CLOSURE)}
        self.review_path = self.root / 'NATIVE25-CLOSURE-REVIEW.json'
        self.review = engine.save(self.review_path, review)
        opening = dict(fresh.BASELINE, max_rowid=5295, request_count=5295,
                       charged_nano_usd=159_010_752_500, rows_sha256='c' * 64)
        self.body['forecast_recovery'] = {
            'human_authorization': fresh.FORECAST26_AUTHORIZATION,
            'author_id': fresh.AUTHOR24_IDS[0], 'forecast_id': fresh.FORECAST26_ID,
            'closed_forecast_review': deepcopy(fresh.FORECAST25_CLOSURE),
            'native_failure_closure_review': self.review,
            'allocation': {'opening': opening, 'max_new_nano_usd': 2_000_000_000,
                           'author_id': fresh.AUTHOR24_IDS[0], 'forecast_id': fresh.FORECAST26_ID}}

    def policy(self, body=None):
        return self.fixture.policy(self.body if body is None else body)

    def test_only26_can_spend_new2_without_reopening_author_or_closed_forecasts(self):
        self.assertEqual(self.policy(), self.body)
        self.fixture.body = deepcopy(self.body)
        for identifier in (*fresh.AUTHOR20_IDS, *fresh.AUTHOR22_IDS, *fresh.AUTHOR24_IDS,
                           fresh.FORECAST26_ID, 'edgar-research-20261016-27'):
            grant = dict(self.fixture.grant, id=identifier,
                         root=str(self.root / 'attempts' / identifier),
                         additional_cap_nano_usd=fresh.pilot_cap(self.body),
                         **{k: self.body['window'][k] for k in ('cutoff_utc', 'deadline_utc')})
            if identifier == fresh.FORECAST26_ID:
                self.assertEqual(self.fixture.validate(grant), self.body)
            else:
                with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                    self.fixture.validate(grant)

    def test_original_history50_200_100_and_old_allocations_are_retained(self):
        body = self.policy()
        self.assertEqual(body['continuation'], self.old.body['continuation'])
        self.assertEqual(body['baseline'], fresh.BASELINE)
        self.assertEqual((body['new_subgrant_nano_usd'], body['original_total_cap_nano_usd'],
                          body['original_per_model_cap_nano_usd']),
                         (50_000_000_000, 200_000_000_000, 100_000_000_000))
        self.assertEqual(fresh.pilot_cap(body), 23_467_987_500)
        self.assertEqual(fresh.allocation(body), body['forecast_recovery']['allocation'])
        for amount in (1, 1_000_000_000, 2_000_000_000):
            variant = deepcopy(body)
            variant['forecast_recovery']['allocation']['max_new_nano_usd'] = amount
            self.assertEqual(fresh.pilot_cap(self.policy(variant)), 21_467_987_500 + amount)

    def test_bad_authority_review_ids_and_changed_caps_fail_before_dispatch(self):
        variants = []
        for key, value in [('human_authorization', 'yes'), ('author_id', fresh.AUTHOR22_IDS[0]),
                           ('forecast_id', fresh.AUTHOR24_IDS[1]), ('extra', True),
                           ('closed_forecast_review', dict(fresh.FORECAST25_CLOSURE, sha256='0' * 64))]:
            body = deepcopy(self.body)
            body['forecast_recovery'][key] = value
            variants.append(body)
        for key, value in [('original_total_cap_nano_usd', 201_000_000_000),
                           ('original_per_model_cap_nano_usd', 101_000_000_000),
                           ('new_subgrant_nano_usd', 51_000_000_000)]:
            variants.append(dict(self.body, **{key: value}))
        for value in (True, 0, -1, 2_000_000_001, 2_000_000_000.0):
            body = deepcopy(self.body)
            body['forecast_recovery']['allocation']['max_new_nano_usd'] = value
            variants.append(body)
        for key, value in [('max_rowid', 5294), ('request_count', True),
                           ('charged_nano_usd', 159_010_752_499), ('rows_sha256', 'bad')]:
            body = deepcopy(self.body)
            body['forecast_recovery']['allocation']['opening'][key] = value
            variants.append(body)
        body = deepcopy(self.body)
        body['forecast_recovery']['allocation']['opening']['charged_nano_usd'] = fresh.BASELINE['charged_nano_usd'] + 49_000_000_001
        variants.append(body)
        body = deepcopy(self.body)
        del body['continuation']['output_followthrough']
        variants.append(body)
        for index, body in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.policy(body)

    def test_native_closure_must_be_exact_distinct_and_intact(self):
        original = engine.read(self.review)
        for change in ({'reviewer': 'Root'}, {'reviewer': '/root'}, {'reviewer': ' '},
                       {'blocking_findings': ['unclosed']}, {'verdict': 'PASS_TESTS_ONLY'},
                       {'closed_forecast_review': dict(fresh.FORECAST25_CLOSURE, sha256='0' * 64)}):
            # Invented fixture mutation only, not a historical or live report.
            self.review_path.write_text(__import__('json').dumps(dict(original, **change)))
            body = deepcopy(self.body)
            body['forecast_recovery']['native_failure_closure_review'] = engine.pin(self.review_path)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.policy(body)
        with self.assertRaises(ValueError):
            self.policy(self.body)  # The original binding no longer matches fixture bytes.

    def entry_fixture(self):
        entry=previous_entry.Author24EntryTests();entry.setUp();self.addCleanup(entry.doCleanups)
        entry.body=deepcopy(self.body)
        scope=deepcopy(entry.scope);a=fresh.allocation(self.body)
        scope.update(forecast_id=fresh.FORECAST26_ID,continuation_human_approval=fresh.FORECAST26_AUTHORIZATION,
            allocation=a,opening_rows=a['opening']['max_rowid'],opening_rows_sha256=a['opening']['rows_sha256'],
            continuation_cumulative_cap_nano_usd=fresh.pilot_cap(self.body),
            closed_forecast_review=fresh.FORECAST25_CLOSURE,native_failure_closure_review=self.review)
        entry.scope=scope
        return entry

    def test_actual_entry_scope_keeps_reviewed24_and_accepts_only_new_forecast(self):
        entry=self.entry_fixture()
        self.assertEqual(entry.authority(),entry.scope)
        for change in ({'forecast_id':fresh.AUTHOR24_IDS[1]}, {'continuation_human_approval':fresh.AUTHOR24_AUTHORIZATION},
                {'closed_forecast_review':dict(fresh.FORECAST25_CLOSURE,sha256='0'*64)},
                {'native_failure_closure_review':dict(self.review,sha256='0'*64)},
                {'requires_cold_probe':False},{'author_max_output_tokens':49153}):
            with self.subTest(change=change),self.assertRaises(ValueError):entry.authority(change)
        with patch.object(flow,'authority',return_value=entry.scope),patch.object(flow,'prior') as prior:
            with self.assertRaises(ValueError):flow.prepare('author')
            prior.assert_not_called()

    def test_original_container80_includes_closed25_in_addition_to_current26(self):
        entry=self.entry_fixture()
        for identifier,number in ((fresh.AUTHOR24_IDS[1],9),(fresh.FORECAST26_ID,2),(fresh.AUTHOR24_IDS[0],3)):
            root=self.root/'attempts'/identifier/'code';root.mkdir(parents=True)
            for index in range(number):(root/f'call-{index:032x}').mkdir()
        with patch.object(flow,'authority',return_value=entry.scope),patch.object(flow,'ROOT',self.root):
            self.assertEqual(flow.containers_remaining(),66)

    def test_source_manifest_binds_new_helper_and_only_reviewed_Native_change(self):
        repo=self.root/'sources26';actual=Path(flow.__file__).resolve().parents[1]
        names=['tools/earnings_open_author_followthrough.py','tools/earnings_native_failure.py',
            'tools/earnings_open_fresh_grant.py','configs/scope.json','configs/context.json',
            'research/market_rsi/supervisor_harness/continuous_discovery_batch.py','tools/protected.py']
        for name in names:
            path=repo/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes((actual/name).read_bytes() if (actual/name).is_file() else b'inert protected source')
        native=names[-2];old={'sources':{native:dict(engine.pin(repo/native),sha256='0'*64),
            names[-1]:engine.pin(repo/names[-1])}}
        with patch.object(flow.e,'REPO',repo),patch.object(flow,'__file__',str(repo/names[0])),\
                patch.object(flow,'SCOPE',repo/names[3]),patch.object(flow,'CONTEXT',repo/names[4]):
            pins=flow.source_bindings(old,scope=self.entry_fixture().scope)
            self.assertEqual(pins[names[1]],engine.pin(repo/names[1]))
            self.assertEqual(pins[native]['sha256'],'8bc7a9072d7f7f5d18f1f852bd0de9d0b288190c4e94c16b49c2ff61aee2d03b')
            for name in (native,names[-1]):
                path=repo/name;raw=path.read_bytes();path.write_bytes(raw+b'\n# drift')
                with self.subTest(name=name),self.assertRaises(ValueError):flow.source_bindings(old,scope=self.entry_fixture().scope)
                path.write_bytes(raw)


if __name__ == '__main__':
    unittest.main()
