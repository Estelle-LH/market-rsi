"""Tests for the proposed ``max_file_bytes`` keyword on ``BoundMetadata``.

Fixtures are fabricated with tempfile only; no network or repository access.
The module under test is expected to expose ``BoundMetadata`` and
``MetadataError`` with the public contract described in the proposal.
"""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

try:
    from bound_metadata import BoundMetadata, MetadataError
except ImportError:  # pragma: no cover - tolerate an alternate module name
    try:
        from metadata import BoundMetadata, MetadataError
    except ImportError:
        from pinned_metadata import BoundMetadata, MetadataError

MIB = 1024 * 1024


def manifest_digest(manifest):
    raw = json.dumps(
        manifest, sort_keys=True, separators=(',', ':'), allow_nan=False
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def row_for(name, data):
    return {
        'path': name,
        'size': len(data),
        'sha256': hashlib.sha256(data).hexdigest(),
    }


def oversized_json(target):
    """Return JSON bytes of exactly ``target`` bytes, slightly above 1 MiB."""
    overhead = len(json.dumps({'payload': ''}))
    return json.dumps({'payload': 'x' * (target - overhead)}).encode()


class MaxFileBytesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # resolve() removes symlinked components (e.g. /var on macOS) and the
        # chmod guarantees the private-mode invariant the API requires.
        self.root = Path(self._tmp.name).resolve()
        os.chmod(self.root, 0o700)

    def write_file(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def bind(self, manifest, **kwargs):
        return BoundMetadata(
            self.root, manifest, manifest_digest(manifest), **kwargs
        )

    def test_explicit_limit_accepts_json_above_one_mib(self):
        data = oversized_json(MIB + 64)
        self.assertGreater(len(data), MIB)
        self.assertLessEqual(len(data), 2 * MIB)
        self.write_file('big.json', data)
        manifest = [row_for('big.json', data)]
        bound = self.bind(manifest, max_file_bytes=2 * MIB)

        binding = bound.pin(str(self.root / 'big.json'))
        self.assertEqual(binding['path'], str(self.root / 'big.json'))
        self.assertEqual(binding['sha256'], manifest[0]['sha256'])
        parsed = bound.read(binding)
        self.assertEqual(len(parsed['payload']), MIB + 64 - len(json.dumps({'payload': ''})))
        self.assertEqual([r['path'] for r in bound.audit], ['big.json', 'big.json'])

    def test_default_limit_rejects_json_above_one_mib(self):
        data = oversized_json(MIB + 64)
        self.write_file('big.json', data)
        manifest = [row_for('big.json', data)]
        with self.assertRaises(MetadataError):
            self.bind(manifest)

    def test_explicit_limit_rejects_oversize_row(self):
        manifest = [
            {'path': 'too-big.json', 'size': 2 * MIB + 1, 'sha256': '0' * 64}
        ]
        with self.assertRaises(MetadataError):
            self.bind(manifest, max_file_bytes=2 * MIB)

    def test_max_file_bytes_must_be_bounded_genuine_int(self):
        data = b'{"k": "v"}'
        self.write_file('f.json', data)
        manifest = [row_for('f.json', data)]
        for bad in (True, False, 0, -1, 4 * MIB + 1, 1.5, '1048576', None, 2**63):
            with self.subTest(max_file_bytes=bad):
                with self.assertRaises((ValueError, TypeError)):
                    self.bind(manifest, max_file_bytes=bad)
        # Upper boundary remains usable.
        bound = self.bind(manifest, max_file_bytes=4 * MIB)
        self.assertEqual(
            bound.pin(str(self.root / 'f.json'))['sha256'], manifest[0]['sha256']
        )

    def test_total_bound_still_enforced_with_raised_limit(self):
        rows = [
            {'path': name, 'size': 1536 * 1024, 'sha256': '0' * 64}
            for name in ('a.json', 'b.json', 'c.json')
        ]
        # 3 x 1.5 MiB exceeds the 4 MiB aggregate bound even though each row is
        # individually below the raised per-file limit.
        with self.assertRaises(MetadataError):
            self.bind(rows, max_file_bytes=4 * MIB)

    def test_changed_bytes_and_binding_digest_refused(self):
        data = b'{"k": "v"}'
        self.write_file('f.json', data)
        bound = self.bind([row_for('f.json', data)])
        binding = bound.pin(str(self.root / 'f.json'))

        with self.assertRaises(MetadataError):
            bound.read(dict(binding, sha256='0' * 64))

        (self.root / 'f.json').write_bytes(b'{"k": "w"}')
        with self.assertRaises(MetadataError):
            bound.pin(str(self.root / 'f.json'))
        with self.assertRaises(MetadataError):
            bound.read(binding)

    def test_symlink_target_refused(self):
        if not hasattr(os, 'symlink'):
            self.skipTest('os.symlink unavailable')
        data = b'{"k": "v"}'
        self.write_file('real.json', data)
        link = self.root / 'link.json'
        os.symlink(str(self.root / 'real.json'), link)
        bound = self.bind([row_for('link.json', data)])
        with self.assertRaises(MetadataError):
            bound.pin(str(link))
        with self.assertRaises(MetadataError):
            bound.read({'path': str(link), 'sha256': hashlib.sha256(data).hexdigest()})


if __name__ == '__main__':
    unittest.main()
