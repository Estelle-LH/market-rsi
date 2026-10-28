"""Read only separately pinned ordinary JSON metadata; never follow its links.

The root and manifest are trusted deployment inputs, not a scientific closure
certificate. A private/exclusive parent is assumed; this is not protection from
a malicious process with the same filesystem authority.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat


class MetadataError(ValueError):
    pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MetadataError('duplicate metadata field')
        result[key] = value
    return result


def _nonfinite(unused):
    raise MetadataError('nonfinite JSON metadata')


class BoundMetadata:
    def __init__(self, root, manifest, expected_manifest_sha256):
        if type(manifest) is not list or not 1 <= len(manifest) <= 64:
            raise MetadataError('bounded explicit metadata manifest required')
        try:
            raw = json.dumps(manifest, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        except Exception:
            raise MetadataError('serializable metadata manifest required') from None
        if hashlib.sha256(raw).hexdigest() != expected_manifest_sha256:
            raise MetadataError('independent manifest digest mismatch')
        entries = {}
        total = 0
        for row in manifest:
            if type(row) is not dict or set(row) != {'path', 'size', 'sha256'}:
                raise MetadataError('exact metadata manifest row required')
            name = row['path']
            if (type(name) is not str or not name or len(name) > 512
                    or '\\' in name or '\x00' in name or PurePosixPath(name).is_absolute()
                    or str(PurePosixPath(name)) != name or '..' in PurePosixPath(name).parts
                    or name in ('.', '..') or name in entries):
                raise MetadataError('unique canonical relative metadata path required')
            if (type(row['size']) is not int or not 0 <= row['size'] <= 1024 * 1024
                    or type(row['sha256']) is not str
                    or re.fullmatch('[0-9a-f]{64}', row['sha256']) is None):
                raise MetadataError('bounded byte size and digest required')
            total += row['size']
            entries[name] = dict(row)
        if total > 4 * 1024 * 1024:
            raise MetadataError('metadata manifest total exceeds bound')
        try:
            literal = str(root)
            root = Path(root)
            if (str(root) != literal or not root.is_absolute() or root.resolve(strict=True) != root
                    or not root.is_dir() or root.stat().st_mode & 0o077):
                raise MetadataError('canonical private metadata root required')
        except (OSError, TypeError, RuntimeError):
            raise MetadataError('canonical private metadata root required') from None
        self.root = root
        self._entries = entries
        self._audit = []

    def _raw(self, path):
        literal = str(path)
        path = Path(path)
        if str(path) != literal:
            raise MetadataError('canonical metadata spelling required')
        try:
            name = str(path.relative_to(self.root))
        except ValueError:
            raise MetadataError('metadata path outside explicit scope') from None
        row = self._entries.get(name)
        if row is None or str(path) != str(self.root / name):
            raise MetadataError('metadata path absent from explicit manifest')
        try:
            if path.is_symlink() or path.resolve(strict=True) != path:
                raise MetadataError('canonical ordinary metadata file required')
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_size != row['size']:
                    raise MetadataError('metadata type or size changed')
                with os.fdopen(descriptor, 'rb', closefd=False) as stream:
                    raw = stream.read(row['size'] + 1)
            finally:
                os.close(descriptor)
        except OSError as error:
            raise MetadataError('metadata read failed: ' + type(error).__name__) from None
        if len(raw) != row['size'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise MetadataError('metadata bytes changed')
        self._audit.append(dict(row))
        return raw, row

    def pin(self, path):
        unused, row = self._raw(path)
        return {'path': str(self.root / row['path']), 'sha256': row['sha256']}

    def read(self, binding):
        if (type(binding) is not dict or set(binding) != {'path', 'sha256'}
                or type(binding['path']) is not str or type(binding['sha256']) is not str):
            raise MetadataError('exact metadata binding required')
        if str(Path(binding['path'])) != binding['path']:
            raise MetadataError('canonical metadata binding spelling required')
        try:
            name = str(Path(binding['path']).relative_to(self.root))
        except ValueError:
            raise MetadataError('metadata binding outside explicit scope') from None
        row = self._entries.get(name)
        if row is None or binding['sha256'] != row['sha256']:
            raise MetadataError('metadata binding differs from manifest')
        raw, unused = self._raw(binding['path'])
        try:
            return json.loads(raw, object_pairs_hook=_unique, parse_constant=_nonfinite)
        except Exception as error:
            raise MetadataError('metadata JSON rejected: ' + type(error).__name__) from None

    @property
    def audit(self):
        return [dict(row) for row in self._audit]
