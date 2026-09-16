import unittest
from audit_capture_cross_forensic import evidence


def fixture(context):
    return {'locator': {'case': {'timestamp_ms': 1}}, 'analysis': {
        'legacy_exact_csv_price_size_matches': 1,
        'variants': {'test': {'case_context': context}}}}


class EvidenceTests(unittest.TestCase):
    def test_empty_evidence_does_not_pass(self):
        result = evidence(fixture([]))['test']
        self.assertFalse(result['all_complete_messages_uncrossed'])
        self.assertFalse(result['all_source_bbos_uncrossed'])

    def test_partial_update_distinguished_from_message_end(self):
        context = [
            {'timestamp_ms': 1, 'kind': 'delta_entry', 'status': 'crossed',
             'source_bbo_status': 'uncrossed', 'source_matches_csv_price_pair': False},
            {'timestamp_ms': 1, 'kind': 'message_complete', 'status': 'uncrossed'}]
        result = evidence(fixture(context))['test']
        self.assertEqual(result['replay_crossed_entries'], 1)
        self.assertEqual(result['replay_crossed_complete_messages'], 0)
        self.assertTrue(result['all_complete_messages_uncrossed'])
        self.assertTrue(result['all_source_bbos_uncrossed'])

    def test_missing_bbo_and_locked_book_are_not_uncrossed_proof(self):
        result = evidence(fixture([{'timestamp_ms': 1, 'kind': 'delta_entry', 'status': 'locked'},
             {'timestamp_ms': 1, 'kind': 'message_complete', 'status': 'locked'}]))['test']
        self.assertFalse(result['all_complete_messages_uncrossed'])
        self.assertFalse(result['all_source_bbos_uncrossed'])


if __name__ == '__main__': unittest.main()
