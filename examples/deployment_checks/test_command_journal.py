"""B4 local protocol tests; no APIs or physical power-loss claims."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import traceback
import unittest
from unittest.mock import Mock, patch

import command_journal as journal


WORKSPACE = Path(__file__).resolve().parent
PAYLOAD = hashlib.sha256(b"b4-payload").hexdigest()
CHANGED_PAYLOAD = hashlib.sha256(b"b4-changed-payload").hexdigest()
IDENTITY = {"command_id": "command-b4", "target": "target-b4"}


class CommandJournalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="b4-test-", dir=WORKSPACE)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.assertEqual(self.root.parent, WORKSPACE)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)

    def path(self, kind, key="b4-command"):
        return self.root / (key + "." + kind + ".json")

    def submit(self, key="b4-command"):
        return journal.submit_once(self.root, key, PAYLOAD, Mock(return_value=dict(IDENTITY)))

    def observation(self, status="Success", response_code=0):
        return dict(IDENTITY, status=status, response_code=response_code)

    def assert_no_resend(self, callback, key="b4-command", acknowledged=False):
        raw = self.path("intent", key).read_bytes()
        self.assertEqual(json.loads(raw), {
            "schema": "dispatch-intent-v1", "key": key, "payload_sha256": PAYLOAD,
        })
        self.assertEqual(self.path("ack", key).exists(), acknowledged)
        for digest in (PAYLOAD, CHANGED_PAYLOAD, PAYLOAD):
            with self.subTest(key=key, retry_digest=digest):
                with self.assertRaises(FileExistsError):
                    journal.submit_once(self.root, key, digest, callback)
        callback.assert_called_once_with()
        self.assertEqual(self.path("intent", key).read_bytes(), raw)

    def test_intent_is_synced_before_callback_and_ack_binds_identity(self):
        synced = []
        real_fsync = os.fsync

        def record_fsync(descriptor):
            mode = os.fstat(descriptor).st_mode
            synced.append("file" if stat.S_ISREG(mode) else "directory" if stat.S_ISDIR(mode) else "other")
            return real_fsync(descriptor)

        def callback():
            self.assertEqual(synced, ["file", "directory"])
            self.assertEqual(json.loads(self.path("intent").read_bytes()), {
                "schema": "dispatch-intent-v1", "key": "b4-command", "payload_sha256": PAYLOAD,
            })
            self.assertFalse(self.path("ack").exists())
            return dict(IDENTITY)

        submit = Mock(side_effect=callback)
        with patch.object(journal.os, "fsync", side_effect=record_fsync):
            ack = journal.submit_once(self.root, "b4-command", PAYLOAD, submit)
        expected = dict(IDENTITY, schema="dispatch-ack-v1", key="b4-command",
                        intent_sha256=hashlib.sha256(self.path("intent").read_bytes()).hexdigest())
        self.assertEqual(ack, expected)
        self.assertEqual(json.loads(self.path("ack").read_bytes()), expected)
        self.assertEqual(synced, ["file", "directory", "file", "directory"])
        submit.assert_called_once_with()
        query = Mock(return_value=self.observation())
        self.assertTrue(journal.observe(self.root, "b4-command", query)["success"])
        query.assert_called_once_with(IDENTITY["command_id"], IDENTITY["target"])

    def test_duplicate_and_changed_payload_attempts_call_submit_only_once(self):
        callback = Mock(return_value=dict(IDENTITY))
        journal.submit_once(self.root, "b4-command", PAYLOAD, callback)
        ack = self.path("ack").read_bytes()
        self.assert_no_resend(callback, acknowledged=True)
        self.assertEqual(self.path("ack").read_bytes(), ack)

    def test_failed_callback_retains_intent_suppresses_secret_and_never_resends(self):
        secret = "FAKE_B4_SECRET_NOT_A_REAL_CREDENTIAL"

        def fail():
            raise RuntimeError(secret)

        callback = Mock(side_effect=fail)
        try:
            journal.submit_once(self.root, "b4-command", PAYLOAD, callback)
        except journal.DispatchUnknown as error:
            # Format the live traceback, before unittest can discard its frames.
            rendered = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            self.assertIn("DispatchUnknown", rendered)
            self.assertNotIn(secret, rendered)
            self.assertNotIn("RuntimeError", rendered)
            self.assertTrue(error.__suppress_context__)
        else:
            self.fail("failed callback must raise DispatchUnknown")
        self.assert_no_resend(callback)

    def test_malformed_acknowledgements_retain_intent_and_never_resend(self):
        invalid = [None, [], "not-an-identity", {},
                   dict(IDENTITY, extra=True), dict(IDENTITY, command_id=""),
                   dict(IDENTITY, command_id=1), dict(IDENTITY, target=""),
                   dict(IDENTITY, target="x" * 129)]
        for index, identity in enumerate(invalid):
            with self.subTest(identity=identity):
                key = "malformed-" + str(index)
                callback = Mock(return_value=identity)
                with self.assertRaises(journal.DispatchUnknown):
                    journal.submit_once(self.root, key, PAYLOAD, callback)
                self.assert_no_resend(callback, key)

    def test_ack_unknown_never_queries(self):
        with self.assertRaises(journal.DispatchUnknown):
            journal.submit_once(self.root, "b4-command", PAYLOAD, Mock(return_value=None))
        query = Mock(side_effect=AssertionError("ACK_UNKNOWN must not query"))
        self.assertEqual(journal.observe(self.root, "b4-command", query), {
            "status": "ACK_UNKNOWN", "terminal": False, "success": False,
        })
        query.assert_not_called()

    def test_status_classification(self):
        self.submit()
        cases = [("Pending", -1, False, False), ("InProgress", -1, False, False),
                 ("Delayed", -1, False, False), ("Cancelling", -1, False, False),
                 ("Success", 0, True, True), ("Failed", 1, True, False),
                 ("Cancelled", -1, True, False), ("TimedOut", -1, True, False),
                 ("Undeliverable", -1, True, False), ("Terminated", -1, True, False)]
        for status, code, terminal, success in cases:
            with self.subTest(status=status):
                value = self.observation(status, code)
                query = Mock(return_value=value)
                self.assertEqual(journal.observe(self.root, "b4-command", query),
                                 dict(value, terminal=terminal, success=success))
                query.assert_called_once_with(IDENTITY["command_id"], IDENTITY["target"])

    def test_mismatched_identity_and_invalid_status_results_are_rejected(self):
        self.submit()
        invalid = [dict(self.observation(), command_id="wrong-command"),
                   dict(self.observation(), target="wrong-target"),
                   self.observation(response_code=1), self.observation(response_code=-1),
                   self.observation(response_code=True), self.observation(response_code="0"),
                   self.observation(status="Unknown"), dict(self.observation(), extra=True), None]
        for value in invalid:
            with self.subTest(value=value):
                query = Mock(return_value=value)
                with self.assertRaises(journal.JournalError):
                    journal.observe(self.root, "b4-command", query)
                query.assert_called_once_with(IDENTITY["command_id"], IDENTITY["target"])

    def test_modified_journal_bindings_are_rejected_before_query(self):
        changes = [("intent", "payload_sha256", CHANGED_PAYLOAD),
                   ("intent", "schema", "wrong-schema"), ("intent", "key", "wrong-key"),
                   ("ack", "intent_sha256", "0" * 64), ("ack", "schema", "wrong-schema"),
                   ("ack", "key", "wrong-key"), ("ack", "command_id", ""),
                   ("ack", "target", ""), ("ack", "unexpected", True)]
        for index, (kind, field, value) in enumerate(changes):
            with self.subTest(kind=kind, field=field):
                key = "modified-" + str(index)
                self.submit(key)
                path = self.path(kind, key)
                record = json.loads(path.read_bytes())
                record[field] = value
                path.write_text(json.dumps(record), encoding="utf-8")
                query = Mock()
                with self.assertRaises(journal.JournalError):
                    journal.observe(self.root, key, query)
                query.assert_not_called()

    def test_torn_journals_are_rejected_before_query(self):
        for kind in ("intent", "ack"):
            with self.subTest(kind=kind):
                key = "torn-" + kind
                self.submit(key)
                path = self.path(kind, key)
                path.write_bytes(path.read_bytes()[:-1])
                query = Mock()
                with self.assertRaises(json.JSONDecodeError):
                    journal.observe(self.root, key, query)
                query.assert_not_called()

    def test_oversize_valid_json_journals_are_rejected_before_query(self):
        for kind in ("intent", "ack"):
            with self.subTest(kind=kind):
                key = "oversize-" + kind
                self.submit(key)
                path = self.path(kind, key)
                raw = path.read_bytes()
                oversized = b" " * (16385 - len(raw)) + raw
                self.assertEqual(json.loads(oversized), json.loads(raw))
                path.write_bytes(oversized)
                query = Mock()
                with self.assertRaises(journal.JournalError):
                    journal.observe(self.root, key, query)
                query.assert_not_called()

    def test_symlink_journals_are_rejected_before_query(self):
        for kind in ("intent", "ack"):
            for dangling in (False, True):
                with self.subTest(kind=kind, dangling=dangling):
                    key = "symlink-" + kind + "-" + str(int(dangling))
                    self.submit(key)
                    path = self.path(kind, key)
                    target = self.root / (key + ".target.json")
                    if not dangling:
                        target.write_bytes(path.read_bytes())
                    path.unlink()
                    path.symlink_to(target)
                    query = Mock()
                    with self.assertRaises(journal.JournalError):
                        journal.observe(self.root, key, query)
                    query.assert_not_called()

    def test_symlink_intent_target_is_not_written_or_submitted(self):
        for dangling in (False, True):
            with self.subTest(dangling=dangling):
                key = "submit-link-" + str(int(dangling))
                target = self.root / (key + ".target.json")
                if not dangling:
                    target.write_bytes(b"test-owned target must stay unchanged")
                self.path("intent", key).symlink_to(target)
                callback = Mock(return_value=dict(IDENTITY))
                with self.assertRaises(FileExistsError):
                    journal.submit_once(self.root, key, PAYLOAD, callback)
                callback.assert_not_called()
                if dangling:
                    self.assertFalse(target.exists())
                else:
                    self.assertEqual(target.read_bytes(), b"test-owned target must stay unchanged")

    def test_symlink_ack_target_is_not_written_and_never_causes_resend(self):
        target = self.root / "ack-target.json"
        target.write_bytes(b"test-owned target must stay unchanged")
        self.path("ack").symlink_to(target)
        callback = Mock(return_value=dict(IDENTITY))
        with self.assertRaises(journal.DispatchUnknown):
            journal.submit_once(self.root, "b4-command", PAYLOAD, callback)
        self.assert_no_resend(callback, acknowledged=True)
        self.assertEqual(target.read_bytes(), b"test-owned target must stay unchanged")
        query = Mock()
        with self.assertRaises(journal.JournalError):
            journal.observe(self.root, "b4-command", query)
        query.assert_not_called()

    def test_symlink_root_is_rejected_without_callbacks(self):
        linked = self.root / "linked-root"
        linked.symlink_to(self.root, target_is_directory=True)
        callback, query = Mock(), Mock()
        with self.assertRaises(journal.JournalError):
            journal.submit_once(linked, "b4-command", PAYLOAD, callback)
        with self.assertRaises(journal.JournalError):
            journal.observe(linked, "b4-command", query)
        callback.assert_not_called()
        query.assert_not_called()


if __name__ == "__main__":
    unittest.main()
