import hashlib
from pathlib import Path
import tempfile
import unittest

from data_scientist_harness import fixtures, literature
from data_scientist_harness.broker import Broker
from data_scientist_harness.public_budget import PublicBudget, UPPER


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)/'public'
        self.b = PublicBudget(self.root, UPPER * 2, 'a'*64)

    def tearDown(self): self.tmp.cleanup()

    def test_many_small_reads_settle_actual_bytes(self):
        actual = 0
        for _ in range(12):
            raw, _ = self.b.fetch('https://example.org/paper', fixtures.fake_transport)
            actual += len(raw)
        self.assertEqual(self.b.snapshot()['charged_or_reserved_bytes'], actual)
        self.assertEqual(self.b.snapshot()['pending_attempts'], 0)

    def test_unknown_failure_survives_reopening(self):
        def crash(url): raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt): self.b.fetch('https://example.org/paper', crash)
        b = PublicBudget(self.root, UPPER*2, 'a'*64)
        self.assertEqual(b.snapshot()['charged_or_reserved_bytes'], UPPER)
        with self.assertRaises(KeyboardInterrupt): b.fetch('https://example.org/paper', crash)
        with self.assertRaisesRegex(RuntimeError, 'reservation cap'):
            b.fetch('https://example.org/paper', lambda _: self.fail('must not dispatch'))

    def test_bad_receipt_keeps_upper(self):
        def bad(url):
            raw, r = fixtures.fake_transport(url); r['body_bytes'] = 0
            return raw, r
        with self.assertRaisesRegex(ValueError, 'receipt mismatch'):
            self.b.fetch('https://example.org/paper', bad)
        self.assertEqual(self.b.snapshot()['charged_or_reserved_bytes'], UPPER)

    def test_invalid_url_never_dispatches_or_holds(self):
        with self.assertRaises(ValueError):
            self.b.fetch('file:///tmp/no', lambda _: self.fail('must not dispatch'))
        self.assertEqual(self.b.snapshot()['attempts'], 0)

    def test_manifest_change_is_not_new_budget(self):
        self.b.snapshot()
        with self.assertRaisesRegex(ValueError, 'binding changed'):
            PublicBudget(self.root, UPPER*2, 'b'*64).snapshot()

    def test_content_parse_failure_still_metered(self):
        def bad_json(url):
            raw = b'not json'
            return raw, {'body_bytes': len(raw), 'body_sha256': hashlib.sha256(raw).hexdigest(),
                         'requested_url': url, 'final_url': url, 'content_type': 'application/json'}
        with self.assertRaises(ValueError):
            literature.search('fixture', transport=lambda u: self.b.fetch(u, bad_json))
        self.assertEqual(self.b.snapshot()['charged_or_reserved_bytes'], 8)

    def test_ledger_tamper_rejected(self):
        self.b.snapshot()
        with (self.root/'journal.jsonl').open('a') as f: f.write('{}\n')
        with self.assertRaises((KeyError, ValueError)): self.b.snapshot()

    def test_broker_can_read_more_than_five_small_pages(self):
        root = Path(self.tmp.name)/'workspace'
        sha = fixtures.workspace(root, network=True)
        b = Broker(root, sha, transport=fixtures.fake_transport)
        b.call('inspect_harness', {})
        for _ in range(7):
            result = b.call('read_public_source', {'url': 'https://example.org/paper', 'offset': 0})
            self.assertIn('public_budget_attempt', result['receipt'])
        self.assertEqual(len(b.store.records('read_public_source')), 7)


class LinkTests(unittest.TestCase):
    def read(self, text, final='https://example.org/docs/start'):
        raw = text.encode()
        def transport(url):
            return raw, {'content_type': 'text/html', 'body_bytes': len(raw),
                         'final_url': final, 'body_sha256': hashlib.sha256(raw).hexdigest()}
        return literature.read('https://example.org/old', transport=transport)

    def test_actual_safe_links_relative_to_final_page(self):
        r = self.read('<p>Page</p><a href="../guide#part">A &amp; B</a>'
                      '<a href="https://example.org/guide">Duplicate</a>'
                      '<a href="file:///etc/passwd">Bad</a><a href="https://127.0.0.1/">Bad</a>'
                      '<a href="javascript:evil()">Bad</a><a href="#same">Here</a>'
                      '<script><a href="https://evil.example/">Hidden</a></script>')
        self.assertEqual(r['links'], [{'url': 'https://example.org/guide', 'label': 'A & B'}])
        self.assertFalse(r['linked_pages_read'])
        self.assertFalse(r['links_dns_verified'])

    def test_links_are_bounded_with_explicit_truncation(self):
        r = self.read('<p>Page</p>' + ''.join(f'<a href="/{i}">{i}</a>' for i in range(90)))
        self.assertEqual(len(r['links']), 80)
        self.assertEqual(r['unique_eligible_links'], 90)
        self.assertTrue(r['links_truncated'])


if __name__ == '__main__': unittest.main()
