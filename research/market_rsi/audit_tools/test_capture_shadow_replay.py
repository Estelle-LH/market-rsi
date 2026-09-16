import copy
import unittest
from capture_shadow_replay import shadow


def book():
    return {'t': 1, 'm': {'event_type': 'book', 'asset_id': 'a', 'market': 'm',
        'bids': [{'price': '0.4', 'size': '1'}],
        'asks': [{'price': '0.6', 'size': '1'}, {'price': '0.8', 'size': '1'}]}}


def change():
    return {'t': 2, 'm': {'event_type': 'price_change', 'market': 'm', 'price_changes': [
        {'asset_id': 'a', 'side': 'BUY', 'price': '0.7', 'size': '1'},
        {'asset_id': 'a', 'side': 'SELL', 'price': '0.6', 'size': '0'}]}}


class ReplayTests(unittest.TestCase):
    def test_frame_atomicity_and_snapshot(self):
        rows = [book(), change()]
        per, _ = shadow(rows, False); atomic, _ = shadow(rows)
        self.assertEqual([x[2] for x in per], ['two_sided', 'crossed', 'two_sided'])
        self.assertEqual([x[2] for x in atomic], ['two_sided', 'two_sided'])

    def test_one_sided_is_explicit(self):
        r = change(); r['m']['price_changes'] = [
            {'asset_id': 'a', 'side': 'SELL', 'price': p, 'size': '0'} for p in ('0.6', '0.8')]
        states, _ = shadow([book(), r])
        self.assertEqual(states[-1][2], 'one_sided')
        self.assertIsNone(states[-1][-1])

    def test_unanchored_not_imputed(self):
        states, counts = shadow([change()])
        self.assertEqual(states[-1][2], 'unanchored')
        self.assertEqual(counts['unanchored_delta_entries'], 2)

    def test_future_mutation_and_append_preserve_prefix(self):
        rows = [book(), change()]; before, _ = shadow(rows[:1])
        altered = copy.deepcopy(rows); altered[1]['m']['price_changes'][0]['price'] = '0.9'
        for variant in (rows, altered, rows + [book()]):
            states, _ = shadow(variant)
            self.assertEqual([x for x in states if x[0] < 1], before)

    def test_bad_values_and_identity_fail(self):
        r = change(); r['m']['price_changes'][0]['size'] = 'NaN'
        with self.assertRaises(ValueError): shadow([book(), r])
        r = change(); r['m']['market'] = 'another'
        with self.assertRaisesRegex(ValueError, 'changed market'): shadow([book(), r])


if __name__ == '__main__': unittest.main()
