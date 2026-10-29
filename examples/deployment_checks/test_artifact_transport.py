"""Two local-only test units; fake HTTPS checks are not network/crash proof."""
import base64
import gzip
import hashlib
from pathlib import Path
import stat
import tempfile
import traceback
import unittest
from unittest import mock

import artifact_transport as transport


WORKSPACE = Path(__file__).resolve().parent
BINARY_LIMIT = 8 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


class B2(unittest.TestCase):
    """Real local binary files and deterministic ordered chunk assembly."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='b2-', dir=str(WORKSPACE))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        self.assertEqual(self.root.parent, WORKSPACE)

    def test_binary_roundtrips(self):
        for payload in (b'', b'\x00', b'\xff\x00', bytes(range(256))):
            for width in (4, 12, 48000):
                with self.subTest(payload_bytes=len(payload), width=width):
                    parts = transport.encode_parts(payload, width)
                    self.assertEqual(parts, transport.encode_parts(payload, width))
                    self.assertTrue(all(type(p) is str and len(p) <= width for p in parts))
                    self.assertEqual(''.join(parts), base64.b64encode(payload).decode('ascii'))
                    result = transport.join_parts(parts, digest(payload), len(payload))
                    self.assertIs(type(result), bytes)
                    self.assertEqual(result, payload)

    def test_binary_files_and_ordered_assembly(self):
        payload = bytes(range(63))
        parts = transport.encode_parts(payload, 12)
        for index in reversed(range(len(parts))):
            receipt = transport.write_part(self.root, index, parts[index])
            written = (self.root / ('part-%03d.txt' % index)).read_bytes()
            self.assertIs(type(written), bytes)
            self.assertEqual(written, parts[index].encode('ascii'))
            self.assertEqual(receipt, {'bytes': len(written), 'sha256': digest(written)})
        paths = sorted(self.root.iterdir())
        self.assertEqual([p.name for p in paths], ['part-%03d.txt' % i for i in range(len(parts))])
        ordered = [p.read_bytes().decode('ascii') for p in paths]
        self.assertEqual(transport.join_parts(ordered, digest(payload)), payload)

    def test_tampering_missing_reordered_and_added_parts(self):
        payload = bytes(range(63))
        parts = transport.encode_parts(payload, 12)
        changed = [('B' if parts[0][0] != 'B' else 'C') + parts[0][1:]] + parts[1:]
        for label, candidate in (
            ('tampered', changed), ('missing', parts[:-1]),
            ('reordered', list(reversed(parts))), ('added', parts + [parts[0]]),
        ):
            with self.subTest(case=label), self.assertRaises(transport.ArtifactError):
                transport.join_parts(candidate, digest(payload))
        bad_digest = ('0' if digest(payload)[0] != '0' else '1') + digest(payload)[1:]
        with self.assertRaises(transport.ArtifactError):
            transport.join_parts(parts, bad_digest)

    def test_encode_bounds_and_types(self):
        for value in ('text', bytearray(b'x'), memoryview(b'x'), None, 1, True):
            with self.subTest(value=repr(value)), self.assertRaises(transport.ArtifactError):
                transport.encode_parts(value)
        for width in (True, False, None, '4', 4.0, -4, 0, 3, 5, 48004):
            with self.subTest(width=width), self.assertRaises(transport.ArtifactError):
                transport.encode_parts(b'x', width)
        payload = b'x' * BINARY_LIMIT
        parts = transport.encode_parts(payload, 48000)
        self.assertEqual(transport.join_parts(parts, digest(payload)), payload)
        with self.assertRaises(transport.ArtifactError):
            transport.encode_parts(payload + b'x')

    def test_write_bounds_types_and_indices(self):
        for index in (True, False, None, '0', 0.0, -1, 512):
            with self.subTest(index=index), self.assertRaises(transport.ArtifactError):
                transport.write_part(self.root, index, 'AA==')
        for encoded in (b'AA==', bytearray(b'AA=='), None, 1, True, '\u00e9', 'A' * 48001):
            with self.subTest(encoded_type=type(encoded).__name__, length=len(encoded) if isinstance(encoded, (str, bytes, bytearray)) else None):
                with self.assertRaises(transport.ArtifactError):
                    transport.write_part(self.root, 0, encoded)
        self.assertEqual(list(self.root.iterdir()), [])
        transport.write_part(self.root, 0, '')
        transport.write_part(self.root, 511, 'A' * 48000)
        self.assertEqual((self.root / 'part-000.txt').read_bytes(), b'')
        self.assertEqual((self.root / 'part-511.txt').read_bytes(), b'A' * 48000)

    def test_join_bounds_types_and_encoding(self):
        for parts in (None, 'AA==', ('AA==',), [b'AA=='], [None], [True], ['A' * 48001], [''] * 513):
            with self.subTest(parts_type=type(parts).__name__), self.assertRaises(transport.ArtifactError):
                transport.join_parts(parts, digest(b''))
        for limit in (True, False, None, '1', 1.0, -1, BINARY_LIMIT + 1):
            with self.subTest(limit=limit), self.assertRaises(transport.ArtifactError):
                transport.join_parts([], digest(b''), limit)
        self.assertEqual(transport.join_parts([''] * 512, digest(b''), 0), b'')
        with self.assertRaises(transport.ArtifactError):
            transport.join_parts(['eA=='], digest(b'x'), 0)
        for parts in (['%%%'], ['AA='], ['\u00e9']):
            with self.subTest(parts=parts), self.assertRaises(transport.ArtifactError):
                transport.join_parts(parts, digest(b''))

    def test_existing_and_symlink_destinations_are_not_overwritten(self):
        destination = self.root / 'part-000.txt'
        destination.write_bytes(b'existing sentinel')
        with self.assertRaises(FileExistsError):
            transport.write_part(self.root, 0, 'AA==')
        self.assertEqual(destination.read_bytes(), b'existing sentinel')
        target = self.root / 'target'
        target.write_bytes(b'target sentinel')
        for index, link_target in ((1, target), (2, self.root / 'absent')):
            link = self.root / ('part-%03d.txt' % index)
            link.symlink_to(link_target)
            with self.subTest(index=index), self.assertRaises(FileExistsError):
                transport.write_part(self.root, index, 'AA==')
            self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_bytes(), b'target sentinel')
        self.assertFalse((self.root / 'absent').exists())

    def test_symlink_relative_and_non_directory_roots(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        ordinary_file = self.root / 'ordinary-file'
        ordinary_file.write_bytes(b'sentinel')
        for root in (alias, Path('.'), ordinary_file):
            with self.subTest(root=str(root)), self.assertRaises(transport.ArtifactError):
                transport.write_part(root, 0, 'AA==')
        self.assertEqual(ordinary_file.read_bytes(), b'sentinel')


class FakeResponse:
    def __init__(self, body, url, read_error=None):
        self.body = body
        self.url = url
        self.read_error = read_error
        self.read_sizes = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.closed = True

    def geturl(self):
        return self.url

    def read(self, size):
        self.read_sizes.append(size)
        if size < 0:
            raise AssertionError('unbounded read')
        if self.read_error is not None:
            raise self.read_error
        return self.body[:size]


class FakeOpener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def __call__(self, url, *, timeout):
        self.calls.append((url, timeout))
        if self.error is not None:
            raise self.error
        return self.response


class B3(unittest.TestCase):
    """Injected fake HTTPS objects and real, in-memory gzip/JSON decoding."""

    HOST = 'artifacts.example.test'
    URL = 'https://artifacts.example.test/archive.gz'
    BODY = b'\x00\xffbinary archive'
    SECRET_URL = 'https://fake-user:FAKE_SECRET_TOKEN@untrusted.example.test/archive?token=FAKE_QUERY_SECRET'

    def setUp(self):
        for name in ('build_opener', 'urlopen'):
            patcher = mock.patch.object(transport.urllib.request, name, side_effect=AssertionError('network forbidden'))
            self.addCleanup(patcher.stop)
            guard = patcher.start()
            self.addCleanup(guard.assert_not_called)

    def fetch(self, opener, **overrides):
        url = overrides.pop('url', self.URL)
        options = dict(allowed_host=self.HOST, expected_size=len(self.BODY), expected_sha256=digest(self.BODY))
        options.update(overrides)
        return transport.fetch_archive(url, opener=opener, **options)

    def test_https_exact_host_and_port(self):
        for url in (self.URL, 'https://' + self.HOST + ':443/archive.gz'):
            with self.subTest(url=url):
                response = FakeResponse(self.BODY, url)
                opener = FakeOpener(response)
                self.assertEqual(self.fetch(opener, url=url), self.BODY)
                self.assertEqual(opener.calls, [(url, 30)])
                self.assertEqual(response.read_sizes, [len(self.BODY) + 1])
                self.assertTrue(response.closed)
        for url in (
            'http://' + self.HOST + '/a', 'https://sub.' + self.HOST + '/a',
            'https://' + self.HOST + '.evil.test/a', 'https://' + self.HOST + './a',
            'https://' + self.HOST + ':80/a', 'https://' + self.HOST + ':444/a',
            'https://' + self.HOST + ':0/a', 'https://' + self.HOST + ':65536/a',
            'https://' + self.HOST + ':oops/a', '//'+self.HOST+'/a',
            'https:///a', 'https://[broken/a',
        ):
            opener = FakeOpener()
            with self.subTest(url=url), self.assertRaises(transport.ArtifactError):
                self.fetch(opener, url=url)
            self.assertEqual(opener.calls, [])

    def test_request_credentials_rejected(self):
        for userinfo in ('user@', 'user:password@', ':password@', '@'):
            opener = FakeOpener()
            with self.subTest(userinfo=userinfo), self.assertRaises(transport.ArtifactError):
                self.fetch(opener, url='https://' + userinfo + self.HOST + '/a')
            self.assertEqual(opener.calls, [])

    def test_response_credentials_and_redirects_rejected(self):
        # Final-URL checks must also reject userinfo and same-host URL changes.
        for url in (
            'http://' + self.HOST + '/archive.gz', 'https://other.example.test/archive.gz',
            'https://' + self.HOST + ':444/archive.gz', 'https://' + self.HOST + ':oops/archive.gz',
            'https://user:password@' + self.HOST + '/archive.gz',
            'https://' + self.HOST + '/redirected.gz',
        ):
            response = FakeResponse(self.BODY, url)
            with self.subTest(final_url=url):
                with self.assertRaises(transport.ArtifactError):
                    self.fetch(FakeOpener(response))
                self.assertEqual(response.read_sizes, [])
                self.assertTrue(response.closed)

    def test_no_redirect_without_a_request(self):
        handler = transport._NoRedirect()
        for code in (301, 302, 303, 307, 308):
            with self.subTest(code=code), self.assertRaisesRegex(transport.ArtifactError, 'redirects'):
                handler.redirect_request(None, None, code, 'Found', {}, self.URL)

    def test_bounded_reads_and_size_hash_mismatches(self):
        response = FakeResponse(b'', self.URL)
        self.assertEqual(self.fetch(FakeOpener(response), expected_size=0, expected_sha256=digest(b'')), b'')
        self.assertEqual(response.read_sizes, [1])
        for body, expected_hash in (
            (self.BODY[:-1], digest(self.BODY)),
            (self.BODY + b'extra' * 1000, digest(self.BODY)),
            (b'x' * len(self.BODY), digest(self.BODY)),
            (self.BODY, '0' * 64),
        ):
            response = FakeResponse(body, self.URL)
            with self.subTest(body_size=len(body), expected_hash=expected_hash):
                with self.assertRaises(transport.ArtifactError):
                    self.fetch(FakeOpener(response), expected_sha256=expected_hash)
                self.assertEqual(response.read_sizes, [len(self.BODY) + 1])
                self.assertTrue(response.closed)
        for size in (True, False, None, '1', 1.0, -1, BINARY_LIMIT + 1):
            opener = FakeOpener()
            with self.subTest(size=size), self.assertRaises(transport.ArtifactError):
                self.fetch(opener, expected_size=size)
            self.assertEqual(opener.calls, [])

    def test_exception_messages_redact_fake_secret_url(self):
        for stage in ('open', 'read'):
            error = RuntimeError('failed to download ' + self.SECRET_URL)
            response = FakeResponse(self.BODY, self.URL, read_error=error if stage == 'read' else None)
            opener = FakeOpener(response, error=error if stage == 'open' else None)
            with self.subTest(stage=stage):
                with self.assertRaises(transport.ArtifactError) as caught:
                    self.fetch(opener)
                self.assertEqual(str(caught.exception), 'artifact fetch failed: RuntimeError')
                rendered = str(caught.exception) + repr(caught.exception) + ''.join(traceback.format_exception(caught.exception))
                for secret in (self.SECRET_URL, 'FAKE_SECRET_TOKEN', 'FAKE_QUERY_SECRET'):
                    self.assertNotIn(secret, rendered)

    def test_gzip_json_and_expansion_bounds(self):
        raw = b'{"value":"' + b'a' * 8192 + b'","items":[1,2]}'
        archive = gzip.compress(raw, mtime=0)
        self.assertEqual(transport.gzip_json(archive, len(raw)), {'value': 'a' * 8192, 'items': [1, 2]})
        for limit in (0, 64, len(raw) - 1):
            with self.subTest(limit=limit), self.assertRaises(transport.ArtifactError):
                transport.gzip_json(archive, limit)
        self.assertEqual(transport.gzip_json(gzip.compress(b'0', mtime=0), 1), 0)
        for value in ('not bytes', bytearray(archive), None):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(transport.ArtifactError):
                transport.gzip_json(value)
        for limit in (True, False, None, '1', 1.0, -1, 32 * 1024 * 1024 + 1):
            with self.subTest(limit=limit), self.assertRaises(transport.ArtifactError):
                transport.gzip_json(archive, limit)

    def test_malformed_gzip_and_json(self):
        valid = gzip.compress(b'{}', mtime=0)
        corrupt = valid[:-8] + bytes([valid[-8] ^ 1]) + valid[-7:]
        for archive in (
            b'not gzip', valid[:-4], corrupt,
            gzip.compress(b'{bad}', mtime=0), gzip.compress(b'{} trailing', mtime=0),
            gzip.compress(b'\xff', mtime=0),
        ):
            with self.subTest(archive=archive), self.assertRaises(transport.ArtifactError):
                transport.gzip_json(archive)
