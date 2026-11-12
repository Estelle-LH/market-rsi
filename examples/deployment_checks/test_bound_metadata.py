"""Bounded metadata unit checks; all fixtures live in owned workspace roots."""
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import traceback
import unittest
from unittest import mock

import bound_metadata as metadata


WORKSPACE = Path(__file__).resolve().parent
MIB = 1024 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def manifest_digest(rows):
    return digest(json.dumps(rows, sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode())


class BoundMetadataTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='metadata-unit-', dir=WORKSPACE)
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'root'
        self.root.mkdir(mode=0o700)
        for directory in (self.base, self.root):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        self.raw = b'{"answer":42}'
        self.path = self.root / 'meta.json'
        self.write_new(self.path, self.raw)
        self.row = {'path': 'meta.json', 'size': len(self.raw), 'sha256': digest(self.raw)}
        self.rows = [self.row]

    def write_new(self, path, raw):
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
            stream.write(raw)

    def bound(self, rows=None):
        rows = self.rows if rows is None else rows
        return metadata.BoundMetadata(self.root, rows, manifest_digest(rows))

    def before_open(self, operation, *args):
        with mock.patch.object(metadata.os, 'open', side_effect=AssertionError('unexpected os.open')) as opened:
            with self.assertRaises(metadata.MetadataError):
                operation(*args)
            opened.assert_not_called()

    def reject_path(self, owner, path, sha256=None):
        self.before_open(owner.pin, path)
        self.before_open(owner.read, {'path': str(path), 'sha256': sha256 or self.row['sha256']})

    def test_exact_manifest_digest(self):
        canonical = ('[{"path":"meta.json","sha256":"' + self.row['sha256'] + '","size":13}]').encode()
        expected = digest(canonical)
        metadata.BoundMetadata(self.root, self.rows, expected)
        for bad in ('0' * 64, expected.upper(), expected.encode(), None,
                    digest(json.dumps(self.rows).encode())):
            with self.subTest(digest=bad), self.assertRaises(metadata.MetadataError):
                metadata.BoundMetadata(self.root, self.rows, bad)
        changed = [dict(self.row, size=12)]
        with self.assertRaises(metadata.MetadataError):
            metadata.BoundMetadata(self.root, changed, expected)

    def test_manifest_container_and_exact_rows(self):
        invalid = (None, {}, (), [None], [[]], [{}],
                   [dict(self.row, extra=True)],
                   [{key: value for key, value in self.row.items() if key != 'size'}])
        for rows in invalid:
            with self.subTest(rows=rows), self.assertRaises(metadata.MetadataError):
                self.bound(rows) if rows is not None else metadata.BoundMetadata(self.root, None, '0' * 64)
        for size in (b'13', float('nan'), float('inf')):
            with self.subTest(size=size), self.assertRaisesRegex(metadata.MetadataError, 'serializable'):
                metadata.BoundMetadata(self.root, [dict(self.row, size=size)], '0' * 64)

    def test_manifest_names_and_duplicate_paths(self):
        names = ('', '.', '..', '../meta.json', 'sub/../meta.json', './meta.json',
                 'sub//meta.json', 'sub/./meta.json', 'meta.json/', 'sub\\meta.json',
                 'meta\x00.json', str(self.path), 'x' * 513, None, 7, True, [])
        for name in names:
            with self.subTest(name=name), self.assertRaises(metadata.MetadataError):
                self.bound([dict(self.row, path=name)])
        with self.assertRaises(metadata.MetadataError):
            self.bound([self.row, dict(self.row)])
        self.bound([dict(self.row, path='x' * 512)])
        self.bound([dict(self.row, path='nested/meta.json')])

    def test_manifest_size_and_digest_types(self):
        cases = [('size', value) for value in (-1, MIB + 1, True, 1.0, '13', None)]
        cases += [('sha256', value) for value in ('a' * 63, 'a' * 65, 'A' * 64, 'g' * 64, '', 7, None)]
        for key, value in cases:
            with self.subTest(key=key, value=value), self.assertRaises(metadata.MetadataError):
                self.bound([dict(self.row, **{key: value})])
        for size in (0, MIB):
            self.bound([dict(self.row, size=size)])

    def test_manifest_count_and_total_bounds(self):
        rows = [dict(self.row, path=f'{index}.json', size=0) for index in range(65)]
        for count in (1, 64):
            self.bound(rows[:count])
        for count in (0, 65):
            with self.subTest(count=count), self.assertRaises(metadata.MetadataError):
                self.bound(rows[:count])
        total = [dict(self.row, path=f'{index}.json', size=MIB) for index in range(4)]
        self.bound(total)
        with self.assertRaises(metadata.MetadataError):
            self.bound(total + [dict(self.row, path='excess.json', size=1)])

    def test_pin_read_and_defensive_audit(self):
        owner = self.bound()
        self.assertEqual(owner.audit, [])
        binding = owner.pin(self.path)
        self.assertEqual(binding, {'path': str(self.path), 'sha256': self.row['sha256']})
        self.assertEqual(owner.audit, [self.row])
        self.assertEqual(owner.read(binding), {'answer': 42})
        expected = [dict(self.row), dict(self.row)]
        snapshot = owner.audit
        snapshot[0]['size'] = -1
        snapshot.append({})
        self.row['size'] = 0
        self.assertEqual(owner.audit, expected)
        self.assertEqual(owner.read(binding), {'answer': 42})
        self.assertEqual(owner.audit, expected + [expected[0]])

    def test_invalid_duplicate_and_nonfinite_json(self):
        cases = (b'', b'{', b'{}{}', b'\xff', b'{"x":1,"x":2}',
                 b'{"outer":{"x":1,"x":2}}', b'{"n":NaN}',
                 b'{"n":Infinity}', b'{"n":-Infinity}')
        for raw in cases:
            with self.subTest(raw=raw):
                self.path.write_bytes(raw)
                owner = self.bound([dict(self.row, size=len(raw), sha256=digest(raw))])
                binding = owner.pin(self.path)
                with self.assertRaisesRegex(metadata.MetadataError, 'metadata JSON rejected:'):
                    owner.read(binding)

    def test_same_length_tampering_and_short_long_writes(self):
        for changed in (b'{"answer":43}', self.raw[:-1], self.raw + b' '):
            with self.subTest(length=len(changed)):
                self.path.write_bytes(self.raw)
                owner = self.bound()
                binding = owner.pin(self.path)
                self.path.write_bytes(changed)
                for operation, argument in ((owner.pin, self.path), (owner.read, binding)):
                    with self.assertRaises(metadata.MetadataError):
                        operation(argument)
                self.assertEqual(owner.audit, [self.row])

    def test_forged_extra_key_and_wrong_type_bindings(self):
        owner = self.bound()
        good = {'path': str(self.path), 'sha256': self.row['sha256']}
        cases = (None, [], {}, {'path': str(self.path)}, {'sha256': self.row['sha256']},
                 dict(good, extra=True), dict(good, path=self.path), dict(good, path=7),
                 dict(good, sha256=b'0' * 64), dict(good, sha256=None),
                 dict(good, sha256='0' * 64), dict(good, sha256=self.row['sha256'].upper()))
        for binding in cases:
            with self.subTest(binding=binding):
                self.before_open(owner.read, binding)
        self.assertEqual(owner.audit, [])

    def test_unlisted_outside_relative_and_noncanonical_paths_before_open(self):
        owner = self.bound()
        unlisted = self.root / 'unlisted.json'
        outside = self.base / 'outside-root.json'
        self.write_new(unlisted, b'{}')
        self.write_new(outside, b'{}')
        alias = self.root / 'alias.json'
        alias.symlink_to(self.path)
        paths = (unlisted, outside, alias, 'meta.json', './meta.json',
                 str(self.root) + '/./meta.json', str(self.root) + '//meta.json',
                 str(self.path) + '/', str(self.root) + '/../outside-root.json',
                 str(self.root) + '/branch/../meta.json', str(self.path) + '/..')
        for path in paths:
            with self.subTest(path=str(path)):
                self.reject_path(owner, path)
        self.assertEqual(owner.audit, [])

    def test_nonprivate_missing_noncanonical_and_symlink_roots(self):
        nonprivate = self.base / 'nonprivate'
        nonprivate.mkdir(mode=0o755)
        self.assertNotEqual(nonprivate.stat().st_mode & 0o077, 0, 'creation umask masked nonprivate fixture')
        alias = self.base / 'root-alias'
        alias.symlink_to(self.root, target_is_directory=True)
        parent_alias = self.base / 'parent-alias'
        parent_alias.symlink_to(self.base, target_is_directory=True)
        roots = (nonprivate, self.base / 'missing-root', self.path, 'relative-root',
                 str(self.root) + '/', str(self.root) + '/.',
                 str(self.root) + '/../root', alias, parent_alias / 'root')
        for root in roots:
            with self.subTest(root=str(root)):
                self.before_open(metadata.BoundMetadata, root, self.rows, manifest_digest(self.rows))

    def test_existing_and_dangling_leaf_symlinks(self):
        for name, target in (('live.json', self.path), ('dangling.json', self.base / 'missing-target')):
            with self.subTest(name=name):
                leaf = self.root / name
                leaf.symlink_to(target)
                row = dict(self.row, path=name)
                owner = self.bound([row])
                self.reject_path(owner, leaf)
                self.assertEqual(owner.audit, [])

    def test_symlink_parent_before_open(self):
        actual = self.root / 'actual'
        actual.mkdir(mode=0o700)
        self.write_new(actual / 'meta.json', self.raw)
        alias = self.root / 'linked-parent'
        alias.symlink_to(actual, target_is_directory=True)
        owner = self.bound([dict(self.row, path='linked-parent/meta.json')])
        self.reject_path(owner, alias / 'meta.json')

    def test_nonregular_directory_and_fifo(self):
        directory = self.root / 'directory'
        directory.mkdir(mode=0o700)
        fifo = self.root / 'fifo'
        os.mkfifo(fifo, mode=0o600)
        for path in (directory, fifo):
            with self.subTest(kind=path.name):
                row = dict(self.row, path=path.name, size=0, sha256=digest(b''))
                owner = self.bound([row])
                for operation, argument in ((owner.pin, path),
                        (owner.read, {'path': str(path), 'sha256': row['sha256']})):
                    with self.assertRaises(metadata.MetadataError):
                        operation(argument)
                self.assertEqual(owner.audit, [])

    def test_absent_manifest_file_before_open(self):
        owner = self.bound([dict(self.row, path='missing.json')])
        self.reject_path(owner, self.root / 'missing.json')
        self.assertEqual(owner.audit, [])

    def test_json_link_does_not_open_separate_sentinel(self):
        sentinel = self.base / 'sentinel.json'
        self.write_new(sentinel, b'not JSON: sentinel must not be read')
        value = {'link': str(sentinel), '$ref': str(sentinel), 'nested': {'path': str(sentinel)}}
        raw = json.dumps(value).encode()
        self.path.write_bytes(raw)
        owner = self.bound([dict(self.row, size=len(raw), sha256=digest(raw))])
        with mock.patch.object(metadata.os, 'open', wraps=os.open) as low, \
                mock.patch('builtins.open', wraps=open) as builtin, \
                mock.patch.object(io, 'open', wraps=io.open) as streams:
            self.assertEqual(owner.read(owner.pin(self.path)), value)
        self.assertEqual([call.args[0] for call in low.call_args_list], [self.path, self.path])
        for call in low.call_args_list:
            self.assertEqual(call.args[1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        for call in builtin.call_args_list + streams.call_args_list:
            self.assertIsInstance(call.args[0], int, 'unexpected pathname open')

    def test_read_oserror_redacts_marker_and_formatted_traceback(self):
        owner = self.bound()
        binding = owner.pin(self.path)
        marker = 'FAKE_PRIVATE_METADATA_UNIT_MARKER_6284'
        failure = OSError(errno.EIO, marker, str(self.path))
        self.assertIn(marker, str(failure))
        with mock.patch.object(metadata.os, 'open', side_effect=failure):
            try:
                owner.read(binding)
            except metadata.MetadataError as error:
                rendered = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
                self.assertEqual(str(error), 'metadata read failed: OSError')
                self.assertIn('Traceback (most recent call last)', rendered)
                for text in (str(error), repr(error), rendered):
                    self.assertNotIn(marker, text)
                self.assertIsNone(error.__cause__)
                self.assertTrue(error.__suppress_context__)
            else:
                self.fail('mocked OSError was not rejected')
        self.assertEqual(owner.audit, [self.row])
