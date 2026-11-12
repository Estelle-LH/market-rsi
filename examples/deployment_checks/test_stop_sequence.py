"""C2 local orchestration tests; fakes cannot certify real quiescence or closure."""
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import traceback
import unittest
from dataclasses import replace
from unittest import mock

import command_journal as journal
import stop_sequence as sequence


WORKSPACE = Path(__file__).resolve().parent
FACETS = ('cleanup', 'finance', 'memory', 'private_seal', 'requests', 'terminal')
SECRET = 'FAKE_C2_PRIVATE_ADAPTER_SECRET'
SNAPSHOT = sequence.Snapshot('run-c2', 'owner-c2', 'boot-c2', 'target-c2', 0, 0, 0, 0)
CLOSURE = sequence.Closure('run-c2', 'owner-c2', tuple(
    (name, hashlib.sha256(name.encode()).hexdigest()) for name in FACETS))


class FakeLease:
    def __init__(self, harness):
        self.harness = harness

    def __enter__(self):
        h = self.harness
        h.fail('lease_enter')
        h.case.assertFalse(h.held)
        h.held = True
        h.events.append('acquire exclusion')
        return self

    def __exit__(self, *exc):
        h = self.harness
        h.assert_held(self)
        h.events.append('release')
        h.held = False
        h.fail('lease_exit')
        return False


class Harness:
    def __init__(self, case, root, *, first=SNAPSHOT, second=None,
                 closure=CLOSURE, failure=None, ack=None):
        self.case, self.root = case, root
        self.first = first
        self.second = first if second is None else second
        self.closure, self.failure = closure, failure
        self.ack = {'command_id': 'command-c2', 'target': SNAPSHOT.target} if ack is None else ack
        self.events = []
        self.held = False
        self.observations = self.verifications = self.stops = 0
        self.verified = False
        self.lease = FakeLease(self)

    def fail(self, stage):
        if self.failure == stage:
            raise RuntimeError(SECRET)

    def assert_held(self, lease):
        self.case.assertIs(lease, self.lease)
        self.case.assertTrue(self.held, 'callback ran outside exclusion')

    def quiesce(self):
        self.fail('lease_factory')
        return self.lease

    def observe(self, lease):
        self.assert_held(lease)
        self.observations += 1
        self.events.append('observe' if self.observations % 2 else 're-observe')
        self.fail('observe_first' if self.observations % 2 else 'observe_second')
        return self.first if self.observations % 2 else self.second

    def verify(self, lease, snapshot):
        self.assert_held(lease)
        self.case.assertIs(snapshot, self.first)
        self.events.append('original verifier')
        self.verifications += 1
        self.fail('verifier')
        self.verified = True
        return self.closure

    def stop(self, lease, snapshot, closure):
        self.assert_held(lease)
        self.case.assertTrue(self.verified)
        self.case.assertIs(snapshot, self.second)
        self.case.assertIs(closure, self.closure)
        self.case.assertTrue((self.root / 'stop.intent.json').is_file())
        self.case.assertFalse((self.root / 'stop.ack.json').exists())
        self.events.append('one stop callback')
        self.stops += 1
        self.fail('stop')
        return self.ack

    def run(self):
        return sequence.guarded_stop(self.root, 'stop', quiesce=self.quiesce,
                                     observe=self.observe,
                                     verify_original_closure=self.verify, stop=self.stop)


class StopSequenceTests(unittest.TestCase):
    def private_root(self):
        temporary = tempfile.TemporaryDirectory(prefix='c2-stop-test-', dir=WORKSPACE)
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.assertEqual(root.parent, WORKSPACE)
        self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
        return root

    def harness(self, **kwargs):
        return Harness(self, self.private_root(), **kwargs)

    def blocked(self, harness):
        with self.assertRaises(sequence.StopBlocked):
            harness.run()
        self.assertEqual(harness.stops, 0)
        self.assertFalse(harness.held)
        self.assertFalse((harness.root / 'stop.intent.json').exists())

    def public_error(self, callback, expected):
        try:
            callback()
        except expected as error:
            public = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
            self.assertNotIn(SECRET, public)
            self.assertTrue(error.__suppress_context__)
            self.assertIsNone(error.__cause__)
            return public
        self.fail('expected sanitized public exception')

    def test_order_durable_intent_and_lease_held_through_callbacks(self):
        self.assertEqual(sequence.REQUIRED, frozenset(FACETS))
        h = self.harness()
        original_new, original_fsync = journal._new, journal.os.fsync
        syncs = []

        def fsync(descriptor):
            h.assert_held(h.lease)
            original_fsync(descriptor)
            syncs.append(descriptor)

        def durable_new(path, value):
            h.assert_held(h.lease)
            before = len(syncs)
            pin = original_new(path, value)
            self.assertEqual(len(syncs) - before, 2, 'file and directory must be synced')
            if path.name.endswith('.intent.json'):
                self.assertEqual(h.stops, 0)
                self.assertEqual(json.loads(path.read_text()), value)
                h.events.append('durable intent')
            return pin

        with mock.patch.object(journal.os, 'fsync', side_effect=fsync), \
                mock.patch.object(journal, '_new', side_effect=durable_new):
            ack = h.run()
        self.assertEqual(h.events, ['acquire exclusion', 'observe', 'original verifier',
                                   're-observe', 'durable intent', 'one stop callback', 'release'])
        self.assertEqual((h.observations, h.verifications, h.stops), (2, 1, 1))
        self.assertFalse(h.held)
        intent_bytes = (h.root / 'stop.intent.json').read_bytes()
        payload = {'schema': 'guarded-stop-intent-v1', 'snapshot': SNAPSHOT.__dict__,
                   'bindings': sorted(CLOSURE.bindings)}
        expected_pin = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(json.loads(intent_bytes), {
            'schema': 'dispatch-intent-v1', 'key': 'stop', 'payload_sha256': expected_pin})
        self.assertEqual(ack, {'schema': 'dispatch-ack-v1', 'key': 'stop',
                              'intent_sha256': hashlib.sha256(intent_bytes).hexdigest(),
                              'command_id': 'command-c2', 'target': SNAPSHOT.target})
        self.assertEqual(json.loads((h.root / 'stop.ack.json').read_text()), ack)

    def test_missing_flag_only_incomplete_duplicate_and_invalid_closures_block(self):
        bindings = CLOSURE.bindings
        invalid = [None, True, {'terminal': True}, replace(CLOSURE, bindings=()),
                   replace(CLOSURE, bindings=bindings[:-1]),
                   replace(CLOSURE, bindings=bindings[:-1] + (bindings[0],)),
                   replace(CLOSURE, bindings=list(bindings)),
                   replace(CLOSURE, bindings=bindings + (bindings[0],)),
                   replace(CLOSURE, bindings=(('other', 'a' * 64),) + bindings[1:]),
                   replace(CLOSURE, bindings=(list(bindings[0]),) + bindings[1:])]
        invalid.extend(replace(CLOSURE, bindings=((bindings[0][0], digest),) + bindings[1:])
                       for digest in ('', 'a' * 63, 'a' * 65, 'A' * 64, 'g' * 64, 7, None))
        invalid.extend((replace(CLOSURE, run_id='wrong-run'),
                        replace(CLOSURE, owner_epoch='wrong-owner')))
        for index, closure in enumerate(invalid):
            with self.subTest(case=index):
                self.blocked(self.harness(closure=closure))

    def test_active_workers_containers_or_pending_requests_block(self):
        for field in ('workers', 'containers', 'pending_requests'):
            for value in (1, -1, True, False, 0.0, '0', None):
                with self.subTest(field=field, value=value):
                    self.blocked(self.harness(first=replace(SNAPSHOT, **{field: value})))

    def test_nonterminal_or_invalid_exit_codes_block(self):
        for value in (None, True, False, '0', 0.0, [], -256, 256):
            with self.subTest(value=value):
                h = self.harness(first=replace(SNAPSHOT, terminal_exit_code=value))
                self.blocked(h)
                self.assertEqual(h.verifications, 0)
        self.blocked(self.harness(first={'terminal_exit_code': 0}))

    def test_invalid_execution_identities_block(self):
        for field in ('run_id', 'owner_epoch', 'boot_id', 'target'):
            for value in ('', 'x' * 129, None, 1):
                with self.subTest(field=field, value=value):
                    self.blocked(self.harness(first=replace(SNAPSHOT, **{field: value})))

    def test_changed_identity_exit_or_activity_on_reobserve_blocks(self):
        changes = {'run_id': 'other-run', 'owner_epoch': 'other-owner',
                   'boot_id': 'other-boot', 'target': 'other-target',
                   'terminal_exit_code': 1, 'workers': 1,
                   'containers': 1, 'pending_requests': 1}
        for field, value in changes.items():
            with self.subTest(field=field):
                h = self.harness(second=replace(SNAPSHOT, **{field: value}))
                self.blocked(h)
                self.assertEqual((h.observations, h.verifications), (2, 1))

    def test_nonzero_terminal_exit_requires_successful_original_verifier(self):
        for code in (-255, -1, 1, 255):
            with self.subTest(code=code):
                snapshot = replace(SNAPSHOT, terminal_exit_code=code)
                h = self.harness(first=snapshot)
                self.assertEqual(h.run()['target'], snapshot.target)
                self.assertEqual((h.verifications, h.stops), (1, 1))
                self.blocked(self.harness(first=snapshot, failure='verifier'))
                self.blocked(self.harness(first=snapshot, closure=None))

    def test_verifier_observer_and_lease_acquisition_errors_are_private_and_block(self):
        for stage in ('lease_factory', 'lease_enter', 'observe_first', 'verifier', 'observe_second'):
            with self.subTest(stage=stage):
                h = self.harness(failure=stage)
                self.public_error(h.run, sequence.StopBlocked)
                self.assertEqual(h.stops, 0)
                self.assertFalse(h.held)
                self.assertFalse((h.root / 'stop.intent.json').exists())

    def test_lease_release_error_retains_known_ack_and_never_resubmits(self):
        h = self.harness(failure='lease_exit')
        try:
            h.run()
        except sequence.StopReleaseFailed as error:
            public = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
            self.assertNotIn(SECRET, public)
            self.assertTrue(error.__suppress_context__)
            self.assertIsNone(error.__cause__)
            acknowledgement = error.acknowledgement
        else:
            self.fail('expected late release failure with known ACK')
        self.assertFalse(h.held)
        self.assertEqual((h.observations, h.verifications, h.stops), (2, 1, 1))
        self.assertEqual(h.events, ['acquire exclusion', 'observe', 'original verifier',
                                   're-observe', 'one stop callback', 'release'])
        intent = (h.root / 'stop.intent.json').read_bytes()
        durable_ack = (h.root / 'stop.ack.json').read_bytes()
        expected = {'schema': 'dispatch-ack-v1', 'key': 'stop',
                    'intent_sha256': hashlib.sha256(intent).hexdigest(),
                    'command_id': 'command-c2', 'target': SNAPSHOT.target}
        self.assertEqual(acknowledgement, expected)
        self.assertEqual(json.loads(durable_ack), expected)
        value = {'command_id': 'command-c2', 'target': SNAPSHOT.target,
                 'status': 'InProgress', 'response_code': -1}
        query = mock.Mock(return_value=value)
        self.assertEqual(journal.observe(h.root, 'stop', query),
                         dict(value, terminal=False, success=False))
        query.assert_called_once_with('command-c2', SNAPSHOT.target)
        self.public_error(h.run, sequence.StopBlocked)
        self.assertEqual(h.stops, 1)
        self.assertFalse(h.held)
        self.assertEqual((h.root / 'stop.intent.json').read_bytes(), intent)
        self.assertEqual((h.root / 'stop.ack.json').read_bytes(), durable_ack)

    def test_suppression_and_unknown_ack_release_failure_keep_failure_state(self):
        original_exit = FakeLease.__exit__
        cases = [('verifier', True, sequence.StopBlocked, 0),
                 (None, True, journal.DispatchUnknown, 1),
                 ('lease_exit', False, journal.DispatchUnknown, 1)]
        for failure, suppress, expected, stops in cases:
            with self.subTest(failure=failure, suppress=suppress):
                h = self.harness(failure=failure)
                h.ack = None
                exits = []

                def exit_lease(lease, *exc):
                    exits.append(exc[0])
                    original_exit(lease, *exc)
                    return suppress

                with mock.patch.object(FakeLease, '__exit__', exit_lease):
                    self.public_error(h.run, expected)
                self.assertEqual(exits, [RuntimeError if failure == 'verifier'
                                        else journal.DispatchUnknown])
                self.assertEqual(h.stops, stops)
                self.assertFalse(h.held)
                self.assertEqual((h.root / 'stop.intent.json').exists(), bool(stops))
                self.assertFalse((h.root / 'stop.ack.json').exists())
                if stops:
                    query = mock.Mock(side_effect=AssertionError('unknown ACK must not be queried'))
                    self.assertEqual(journal.observe(h.root, 'stop', query),
                                     {'status': 'ACK_UNKNOWN', 'terminal': False, 'success': False})
                    query.assert_not_called()
                    self.public_error(h.run, sequence.StopBlocked)
                    self.assertEqual(h.stops, 1)
                    self.assertFalse(h.held)

    def test_invalid_reobservations_block_after_original_verification(self):
        values = [None, {}, replace(SNAPSHOT, terminal_exit_code=False),
                  replace(SNAPSHOT, workers=False), replace(SNAPSHOT, containers=0.0),
                  replace(SNAPSHOT, pending_requests='0')]
        for index, value in enumerate(values):
            with self.subTest(case=index):
                h = self.harness()
                h.second = value
                self.blocked(h)
                self.assertEqual((h.observations, h.verifications), (2, 1))

    def test_lost_or_malformed_ack_keeps_intent_and_never_resubmits(self):
        cases = [('lost', None), ('null', None), ('empty', {}), ('boolean', True),
                 ('missing-command', {'target': SNAPSHOT.target}),
                 ('empty-command', {'command_id': '', 'target': SNAPSHOT.target}),
                 ('invalid-command', {'command_id': 7, 'target': SNAPSHOT.target}),
                 ('long-command', {'command_id': 'c' * 129, 'target': SNAPSHOT.target}),
                 ('extra-field', {'command_id': 'command-c2', 'target': SNAPSHOT.target, 'ok': True}),
                 ('wrong-target', {'command_id': 'command-c2', 'target': 'other-target'})]
        for name, ack in cases:
            with self.subTest(case=name):
                h = self.harness(failure='stop' if name == 'lost' else None)
                h.ack = ack
                self.public_error(h.run, journal.DispatchUnknown)
                self.assertEqual(h.stops, 1)
                self.assertFalse(h.held)
                intent = h.root / 'stop.intent.json'
                saved = intent.read_bytes()
                self.assertFalse((h.root / 'stop.ack.json').exists())
                query = mock.Mock(side_effect=AssertionError('unknown ACK must not be queried'))
                self.assertEqual(journal.observe(h.root, 'stop', query),
                                 {'status': 'ACK_UNKNOWN', 'terminal': False, 'success': False})
                query.assert_not_called()
                with self.assertRaises(sequence.StopBlocked):
                    h.run()
                self.assertEqual(h.stops, 1)
                self.assertFalse(h.held)
                self.assertEqual(intent.read_bytes(), saved)
                self.assertFalse((h.root / 'stop.ack.json').exists())

    def test_successful_ack_also_prevents_same_or_changed_payload_resubmission(self):
        h = self.harness()
        h.run()
        intent = (h.root / 'stop.intent.json').read_bytes()
        ack = (h.root / 'stop.ack.json').read_bytes()
        for code in (0, 1):
            with self.subTest(code=code):
                h.first = h.second = replace(SNAPSHOT, terminal_exit_code=code)
                with self.assertRaises(sequence.StopBlocked):
                    h.run()
                self.assertEqual(h.stops, 1)
                self.assertFalse(h.held)
                self.assertEqual((h.root / 'stop.intent.json').read_bytes(), intent)
                self.assertEqual((h.root / 'stop.ack.json').read_bytes(), ack)

    def test_journal_rejects_invalid_payload_digest_without_submission(self):
        for digest in ('', 'a' * 63, 'a' * 65, 'A' * 64, 'g' * 64, 7, None):
            with self.subTest(digest=digest):
                root = self.private_root()
                submit = mock.Mock(side_effect=AssertionError('invalid pin must not submit'))
                with self.assertRaises(journal.JournalError):
                    journal.submit_once(root, 'stop', digest, submit)
                submit.assert_not_called()
                self.assertFalse((root / 'stop.intent.json').exists())

    def test_journal_ack_must_bind_exact_intent_bytes_and_key(self):
        changes = [('ack', 'intent_sha256', '0' * 64), ('ack', 'key', 'other'),
                   ('ack', 'schema', 'other'), ('ack', 'command_id', ''),
                   ('ack', 'target', ''), ('ack', 'extra', True),
                   ('intent', 'payload_sha256', '1' * 64),
                   ('intent', 'payload_sha256', 'invalid'), ('intent', 'key', 'other'),
                   ('intent', 'schema', 'other'), ('intent', 'extra', True),
                   ('intent', 'whitespace-only', None)]
        for kind, field, value in changes:
            with self.subTest(kind=kind, field=field):
                h = self.harness()
                h.run()
                path = h.root / ('stop.' + kind + '.json')
                if field == 'whitespace-only':
                    path.write_bytes(path.read_bytes() + b'\n')
                else:
                    document = json.loads(path.read_text())
                    document[field] = value
                    path.write_text(json.dumps(document))
                query = mock.Mock(side_effect=AssertionError('unbound ACK must not be queried'))
                with self.assertRaises(journal.JournalError):
                    journal.observe(h.root, 'stop', query)
                query.assert_not_called()
                self.assertEqual(h.stops, 1)

    def test_journal_query_receives_pinned_identity_and_validates_reply(self):
        h = self.harness()
        ack = h.run()
        base = {'command_id': ack['command_id'], 'target': ack['target'],
                'status': 'Success', 'response_code': 0}
        terminals = {'Success', 'Failed', 'Cancelled', 'TimedOut', 'Undeliverable', 'Terminated'}
        for status in ('Pending', 'InProgress', 'Delayed', 'Success', 'Failed', 'Cancelled',
                       'Cancelling', 'TimedOut', 'Undeliverable', 'Terminated'):
            with self.subTest(status=status):
                value = dict(base, status=status, response_code=0 if status == 'Success' else 9)
                query = mock.Mock(return_value=value)
                self.assertEqual(journal.observe(h.root, 'stop', query),
                                 dict(value, terminal=status in terminals, success=status == 'Success'))
                query.assert_called_once_with(ack['command_id'], ack['target'])
        invalid = [None, {}, dict(base, command_id='other-command'),
                   dict(base, target='other-target'), dict(base, status='Unknown'),
                   dict(base, response_code=1), dict(base, response_code=True),
                   dict(base, response_code='0'), dict(base, response_code=0.0),
                   dict(base, extra=True)]
        for index, value in enumerate(invalid):
            with self.subTest(invalid=index):
                with self.assertRaises(journal.JournalError):
                    journal.observe(h.root, 'stop', mock.Mock(return_value=value))
        self.assertEqual(h.stops, 1)


if __name__ == '__main__':
    unittest.main()
