"""Install an explicit, hash-pinned ordinary-file bundle without executing it.

The destination parent must already be a trusted private directory. A failed
install is retained as incomplete and cannot be retried at the same destination.
This tool does not discover files, transfer credentials, or authorize workloads.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

MAX_FILES = 64
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _path(value):
    if (type(value) is not str or len(value) > 240
            or re.fullmatch(r"[A-Za-z0-9_./-]+", value) is None
            or any(part in {"", ".", ".."} or part.startswith(".") for part in value.split("/"))
            or value.split("/")[0] == "BUNDLE_COMPLETE.json"):
        raise ValueError("noncanonical bundle path")
    return value


def validate(raw, expected_manifest_sha256):
    if type(raw) is not bytes or len(raw) > 4 * MAX_TOTAL_BYTES:
        raise ValueError("bundle size or type")
    if (type(expected_manifest_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256) is None):
        raise ValueError("manifest pin required")
    bundle = json.loads(raw, object_pairs_hook=_unique)
    if type(bundle) is not dict or set(bundle) != {"manifest", "payload"}:
        raise ValueError("bundle fields")
    manifest = bundle["manifest"]
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(canonical).hexdigest() != expected_manifest_sha256:
        raise ValueError("manifest pin mismatch")
    if type(manifest) is not list or not 1 <= len(manifest) <= MAX_FILES:
        raise ValueError("manifest count")
    payload = bundle["payload"]
    if type(payload) is not dict:
        raise ValueError("payload type")
    decoded = {}
    total = 0
    for row in manifest:
        if type(row) is not dict or set(row) != {"path", "size", "sha256"}:
            raise ValueError("manifest entry fields")
        name = _path(row["path"])
        if name in decoded:
            raise ValueError("duplicate manifest path")
        if (type(row["size"]) is not int or not 0 <= row["size"] <= MAX_FILE_BYTES
                or type(row["sha256"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None):
            raise ValueError("manifest size or digest")
        encoded = payload.get(name)
        if type(encoded) is not str or len(encoded) > 2 * MAX_FILE_BYTES:
            raise ValueError("payload encoding or size")
        content = base64.b64decode(encoded, validate=True)
        if len(content) != row["size"] or hashlib.sha256(content).hexdigest() != row["sha256"]:
            raise ValueError("payload size or digest mismatch")
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("total payload size")
        decoded[name] = content
    if set(payload) != set(decoded):
        raise ValueError("payload does not match allowlist")
    for name in decoded:
        parts = name.split("/")
        if any("/".join(parts[:i]) in decoded for i in range(1, len(parts))):
            raise ValueError("file/directory path collision")
    return decoded


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def install(raw, expected_manifest_sha256, destination):
    decoded = validate(raw, expected_manifest_sha256)  # No writes before full validation.
    literal_destination = os.fspath(destination)
    destination = Path(literal_destination)
    parent = destination.parent
    if (not destination.is_absolute() or str(destination) != literal_destination
            or parent.resolve(strict=True) != parent or not parent.is_dir()
            or parent.stat().st_mode & 0o077):
        raise ValueError("canonical private destination parent required")
    destination.mkdir(mode=0o700)  # Never reopen, overwrite, or resume an existing directory.
    for name, content in sorted(decoded.items()):
        path = destination / name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, 0o444)
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashlib.sha256(content).hexdigest():
            raise ValueError("installed file readback mismatch")
    # Persist all directory entries before creating the completion record.
    directories = [p for p in destination.rglob("*") if p.is_dir()] + [destination]
    for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        _sync_dir(directory)
    receipt = {"schema": "ordinary-file-bundle-v1", "manifest_sha256": expected_manifest_sha256,
               "files": len(decoded), "bytes": sum(map(len, decoded.values())),
               "payload_executed": False, "workload_admission": False}
    temporary = destination / (".bundle-receipt-" + uuid.uuid4().hex)
    completion = destination / "BUNDLE_COMPLETE.json"
    published = False
    try:
        with temporary.open("x") as stream:
            json.dump(receipt, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, completion)  # Only a fully written and synced receipt is published.
        published = True
        temporary.unlink()
        _sync_dir(destination)
        _sync_dir(parent)
    except BaseException:
        if published:
            completion.unlink()
        raise
    return receipt
