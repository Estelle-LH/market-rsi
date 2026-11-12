"""Generic bounded artifact transport; independent of any research runtime."""
import base64
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request


class ArtifactError(ValueError):
    pass


def encode_parts(data, chunk_chars=24000):
    if type(data) is not bytes or len(data) > 8 * 1024 * 1024:
        raise ArtifactError('bounded binary artifact required')
    if type(chunk_chars) is not int or not 4 <= chunk_chars <= 48000 or chunk_chars % 4:
        raise ArtifactError('base64 chunk bound')
    encoded = base64.b64encode(data).decode('ascii')
    return [encoded[i:i + chunk_chars] for i in range(0, len(encoded), chunk_chars)]


def write_part(root, index, encoded):
    root = Path(root)
    if (not root.is_absolute() or root.resolve(strict=True) != root
            or not root.is_dir() or root.stat().st_mode & 0o077):
        raise ArtifactError('canonical private part directory required')
    if type(index) is not int or not 0 <= index < 512 or type(encoded) is not str or len(encoded) > 48000:
        raise ArtifactError('bounded part index or data required')
    try:
        data = encoded.encode('ascii')
    except UnicodeEncodeError:
        raise ArtifactError('ASCII part required') from None
    path = root / ('part-%03d.txt' % index)
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def join_parts(parts, expected_sha256, maximum_bytes=8 * 1024 * 1024):
    if type(parts) is not list or len(parts) > 512 or any(type(p) is not str or len(p) > 48000 for p in parts):
        raise ArtifactError('bounded ordered part list required')
    if type(maximum_bytes) is not int or not 0 <= maximum_bytes <= 8 * 1024 * 1024:
        raise ArtifactError('archive byte limit required')
    try:
        data = base64.b64decode(''.join(parts), validate=True)
    except Exception:
        raise ArtifactError('invalid encoded artifact') from None
    if len(data) > maximum_bytes or hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ArtifactError('artifact size or digest mismatch')
    return data


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ArtifactError('artifact redirects are not permitted')


def fetch_archive(url, *, allowed_host, expected_size, expected_sha256, opener=None):
    try:
        parsed = urllib.parse.urlsplit(url)
        valid = (parsed.scheme == 'https' and parsed.hostname == allowed_host
                 and parsed.port in (None, 443) and parsed.username is None and parsed.password is None)
    except Exception:
        valid = False
    if not valid:
        raise ArtifactError('exact HTTPS artifact host required')
    if type(expected_size) is not int or not 0 <= expected_size <= 8 * 1024 * 1024:
        raise ArtifactError('expected artifact size required')
    opener = opener or urllib.request.build_opener(_NoRedirect()).open
    try:
        with opener(url, timeout=30) as response:
            final_url = response.geturl()
            actual = urllib.parse.urlsplit(final_url)
            if (final_url != url or actual.scheme != 'https' or actual.hostname != allowed_host
                    or actual.port not in (None, 443) or actual.username is not None or actual.password is not None):
                raise ArtifactError('artifact response destination changed')
            data = response.read(expected_size + 1)
    except Exception as error:
        raise ArtifactError('artifact fetch failed: ' + type(error).__name__) from None
    if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ArtifactError('artifact byte count or digest mismatch')
    return data


def gzip_json(archive, maximum_bytes=32 * 1024 * 1024):
    if type(archive) is not bytes or type(maximum_bytes) is not int or not 0 <= maximum_bytes <= 32 * 1024 * 1024:
        raise ArtifactError('bounded gzip input required')
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(archive)) as stream:
            raw = stream.read(maximum_bytes + 1)
        if len(raw) > maximum_bytes:
            raise ArtifactError('expanded artifact exceeds byte bound')
        return json.loads(raw)
    except Exception as error:
        raise ArtifactError('gzip JSON decode failed: ' + type(error).__name__) from None
