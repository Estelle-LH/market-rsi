"""Actual two-window driver persistence with explicitly synthetic role calls."""
from copy import deepcopy
import unittest

from earnings_population import observe
import earnings_population_loop as loop
import test_earnings_population_loop as loop_fixture


class WindowInheritanceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = loop_fixture.PopulationLoopTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def first(self):
        return self.fixture.run_loop(rounds=2)['result']

    def next_window(self, state, *, companies=None):
        f = self.fixture
        return loop.run(f.root/'window-02', state, companies or ['synthetic-next-01'], f.services(),
            admit=lambda _: True, max_rounds=1, identity=lambda: f.identities)

    def test_exact_pool_history_and_last_feedback_flow_into_new_window(self):
        f = self.fixture
        first = self.first()
        inherited = deepcopy(first['population'])
        before = deepcopy(inherited)
        f.trace = ['continue']
        counts = {name: len(rows) for name, rows in f.calls.items()}
        result = self.next_window(inherited)
        packet = f.calls['controller'][-1]
        self.assertEqual(packet['population'], before)
        self.assertEqual(packet['feedback'], first['feedback'])
        self.assertEqual(packet['company_id'], 'synthetic-next-01')
        after = result['result']['population']
        self.assertEqual(after['stable_id'], inherited['stable_id'])
        self.assertEqual(after['explorers'], inherited['explorers'])
        self.assertEqual(after['versions'], inherited['versions'])
        self.assertEqual(after['history'][:len(inherited['history'])], inherited['history'])
        self.assertEqual(after['observations'][:-1], inherited['observations'])
        self.assertEqual(after['exposed_companies'][:-1], inherited['exposed_companies'])
        self.assertEqual(inherited, before)
        self.assertEqual(len(f.calls['author']), counts['author'])
        self.assertEqual(len(f.calls['forecast'])-counts['forecast'], 2)
        second_counts = {name: len(rows) for name, rows in f.calls.items()}
        self.assertEqual(self.next_window(inherited), result)
        self.assertEqual({name: len(rows) for name, rows in f.calls.items()}, second_counts)

    def test_exposed_company_is_rejected_before_any_new_callback(self):
        first = self.first()
        counts = {name: len(rows) for name, rows in self.fixture.calls.items()}
        with self.assertRaises(ValueError):
            self.next_window(first['population'], companies=[self.fixture.companies[0]])
        self.assertEqual({name: len(rows) for name, rows in self.fixture.calls.items()}, counts)

    def test_semantically_wrong_last_feedback_is_not_accepted_as_new_seed(self):
        f = self.fixture
        result = {'version_id': f.stable['id'], 'points': 1.0, 'evidence': f.evidence}
        feedback = f.artifact(dict(schema='earnings_population_feedback_v1',
            company_id='wrong-company', stable_id=f.stable['id'], results=[result]))
        state = observe(f.initial, 'synthetic-previous', [result], feedback=feedback)
        with self.assertRaisesRegex(ValueError, 'exact last observed feedback'):
            self.next_window(state)
        self.assertFalse((f.root/'window-02').exists())
        self.assertEqual(sum(map(len, f.calls.values())), 0)

    def test_changed_old_feedback_bytes_fail_without_mutating_old_journal(self):
        first = self.first()
        f = self.fixture
        journal = f.journal_root/'manifest.json'
        before = journal.read_bytes()
        path = first['feedback']['path']
        from pathlib import Path
        Path(path).write_text('{"changed":true}')
        with self.assertRaises(Exception):
            self.next_window(first['population'])
        self.assertEqual(journal.read_bytes(), before)
        self.assertFalse((f.root/'window-02').exists())


if __name__ == '__main__':
    unittest.main()
