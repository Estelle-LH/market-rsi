"""Regression tests for proposed strict recovery-input contract.

Duplicate JSON field names anywhere in a stored intent or ack document must
raise command_journal.JournalError before the query callback is invoked --
even when the repeated values are identical, or when the last value parses
to an otherwise fully valid document.

These tests intentionally assert the STRICTER contract; they are expected to
fail against an implementation that silently applies last-wins parsing.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import command_journal as journal


PAYLOAD_SHA = hashlib.sha256(b'fake-payload').hexdigest()
COMMAND_ID = 'cmd-fake-0001'
TARGET = 'i-fake0001'


def _pairs(mapping):
    return sorted(mapping.items())


def _raw_object(pairs):
    return b'{' + b','.join(
        json.dumps(name).encode('utf-8') + b':' + json.dumps(value).encode('utf-8')
        for name, value in pairs) + b'}'


def _intent_pairs(key):
    return _pairs({
        'schema': 'dispatch-intent-v1',
        'key': key,
        'payload_sha256': PAYLOAD_SHA,
    })


def _ack_pairs(key, pin):
    return _pairs({
        'schema': 'dispatch-ack-v1',
        'key': key,
        'intent_sha256': pin,
        'command_id': COMMAND_ID,
        'target': TARGET,
    })


class DuplicateFieldContractTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.root.chmod(0o700)

    def _seed(self, key, intent_raw, ack_raw=None):
        (self.root / (key + '.intent.json')).write_bytes(intent_raw)
        if ack_raw is None:
            pin = hashlib.sha256(intent_raw).hexdigest()
            ack_raw = _raw_object(_ack_pairs(key, pin))
        (self.root / (key + '.ack.json')).write_bytes(ack_raw)

    @staticmethod
    def _recording_query(calls):
        def query(command_id, target):
            calls.append((command_id, target))
            return {'command_id': command_id, 'target': target,
                    'status': 'Success', 'response_code': 0}
        return query

    def _assert_strict_reject(self, key):
        calls = []
        with self.assertRaises(journal.JournalError) as cm:
            journal.observe(str(self.root), key, self._recording_query(calls))
        self.assertNotIsInstance(cm.exception, journal.DispatchUnknown)
        self.assertEqual(calls, [])

    def test_unmodified_round_trip_control(self):
        key = 'roundtrip0'
        self._seed(key, _raw_object(_intent_pairs(key)))
        calls = []
        result = journal.observe(str(self.root), key, self._recording_query(calls))
        self.assertEqual(calls, [(COMMAND_ID, TARGET)])
        self.assertEqual(result['status'], 'Success')
        self.assertEqual(result['command_id'], COMMAND_ID)
        self.assertEqual(result['target'], TARGET)
        self.assertEqual(result['response_code'], 0)
        self.assertTrue(result['terminal'])
        self.assertTrue(result['success'])

        bare = 'noackyet0'
        (self.root / (bare + '.intent.json')).write_bytes(
            _raw_object(_intent_pairs(bare)))
        calls = []
        unknown = journal.observe(str(self.root), bare, self._recording_query(calls))
        self.assertEqual(unknown,
                         {'status': 'ACK_UNKNOWN', 'terminal': False, 'success': False})
        self.assertEqual(calls, [])

    def test_duplicate_intent_fields_identical_values(self):
        for i, field in enumerate(('key', 'payload_sha256', 'schema')):
            key = 'dupintent%d' % i
            with self.subTest(field=field):
                pairs = _intent_pairs(key)
                raw = _raw_object(pairs + [(field, dict(pairs)[field])])
                # Ack binds to the EXACT mutated bytes, so any rejection
                # must come from duplicate-field validation, not pin mismatch.
                self._seed(key, raw)
                self._assert_strict_reject(key)

    def test_duplicate_intent_fields_last_value_valid(self):
        decoys = {
            'key': 'zzzzzzzz',
            'payload_sha256': 'b' * 64,
            'schema': 'dispatch-intent-v0',
        }
        for i, field in enumerate(sorted(decoys)):
            key = 'duplastint%d' % i
            with self.subTest(field=field):
                # First occurrence is a decoy; the later (last) occurrence is
                # valid, so last-wins parsing yields a fully valid intent.
                raw = _raw_object([(field, decoys[field])] + _intent_pairs(key))
                self._seed(key, raw)
                self._assert_strict_reject(key)

    def test_duplicate_ack_fields_identical_values(self):
        for i, field in enumerate(
                ('schema', 'key', 'intent_sha256', 'command_id', 'target')):
            key = 'dupackid%d' % i
            with self.subTest(field=field):
                intent_raw = _raw_object(_intent_pairs(key))
                pin = hashlib.sha256(intent_raw).hexdigest()
                pairs = _ack_pairs(key, pin)
                ack_raw = _raw_object(pairs + [(field, dict(pairs)[field])])
                self._seed(key, intent_raw, ack_raw)
                self._assert_strict_reject(key)

    def test_duplicate_ack_fields_last_value_valid(self):
        decoys = {
            'schema': 'dispatch-ack-v0',
            'key': 'zzzzzzzz',
            'intent_sha256': '0' * 64,
            'command_id': 'cmd-decoy-9999',
            'target': 'i-decoy9',
        }
        for i, field in enumerate(sorted(decoys)):
            key = 'duplastack%d' % i
            with self.subTest(field=field):
                intent_raw = _raw_object(_intent_pairs(key))
                pin = hashlib.sha256(intent_raw).hexdigest()
                # Decoy first, valid value last: last-wins parsing produces a
                # fully bound ack, so rejection requires duplicate detection.
                ack_raw = _raw_object([(field, decoys[field])] + _ack_pairs(key, pin))
                self._seed(key, intent_raw, ack_raw)
                self._assert_strict_reject(key)


if __name__ == '__main__':
    unittest.main()
