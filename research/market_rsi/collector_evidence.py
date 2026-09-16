"""Import a small collector export without treating it as scientific proof.

The source server export is prepared by its owner. This module only checks that
the declared non-secret files arrived intact and freezes a read-only local copy.
Clock/reconnect semantics still require trusted source review; an uploaded JSON
claim cannot admit a market experiment by itself.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re

from market_rsi import canonical, file_hash, fresh_json


MAX_FILE_BYTES = 16 * 1024 * 1024
KINDS = {"collector_source", "service_unit", "session_record", "capture_manifest"}
MANIFEST_KEYS = {"schema", "source_host", "exported_at_utc", "files", "notes"}
FILE_KEYS = {"name", "kind", "sha256", "bytes"}
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}")
SHA = re.compile(r"[0-9a-f]{64}")
FORBIDDEN_NAME = re.compile(r"(^|[_.-])(env|key|keys|secret|secrets|token|tokens|credential|credentials|password|passwd)([_.-]|$)", re.I)
SECRET_TEXT = re.compile(
    rb"(?i)(api[_-]?key|private[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password)\s*[:=]\s*[^\s]{8,}"
)


def _regular(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("collector evidence must be a regular non-symlink file")
    size = path.stat().st_size
    if not 0 < size <= MAX_FILE_BYTES:
        raise ValueError("collector evidence file is empty or too large")
    raw = path.read_bytes()
    if len(raw) != size:
        raise ValueError("collector evidence changed while reading")
    return raw


def _expected_host(value):
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        raise ValueError("explicit source IP address required") from None
    if parsed.version != 4 or parsed.is_unspecified or parsed.is_multicast:
        raise ValueError("explicit IPv4 source host required")
    return str(parsed)


def validate_export(source, *, expected_source_host="173.255.234.236"):
    """Return verified bytes; make no clock, liveness or scoring claim."""
    source = Path(source).absolute()
    manifest_path = source / "manifest.json"
    manifest_raw = _regular(manifest_path)
    manifest = json.loads(manifest_raw)
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS:
        raise ValueError("exact collector export manifest required")
    if manifest["schema"] != "market_collector_evidence_export_v1":
        raise ValueError("unknown collector evidence schema")
    expected_source_host = _expected_host(expected_source_host)
    if manifest["source_host"] != expected_source_host:
        raise ValueError("evidence is not bound to the explicitly selected capture host")
    if not isinstance(manifest["exported_at_utc"], str) or not manifest["exported_at_utc"].endswith("Z"):
        raise ValueError("UTC export timestamp required")
    if not isinstance(manifest["notes"], str) or len(manifest["notes"]) > 2000:
        raise ValueError("bounded export notes required")
    files = manifest["files"]
    if not isinstance(files, list) or not files:
        raise ValueError("collector evidence files required")
    seen, kinds, verified = set(), set(), {}
    for item in files:
        if not isinstance(item, dict) or set(item) != FILE_KEYS:
            raise ValueError("exact collector evidence file declaration required")
        name, kind = item["name"], item["kind"]
        if (not isinstance(name, str) or not SAFE_NAME.fullmatch(name)
                or FORBIDDEN_NAME.search(name) or name in {"manifest.json", ".", ".."}):
            raise ValueError("unsafe or secret-like evidence filename")
        if name in seen or kind not in KINDS:
            raise ValueError("duplicate file or unknown evidence kind")
        if not isinstance(item["bytes"], int) or isinstance(item["bytes"], bool) or not 0 < item["bytes"] <= MAX_FILE_BYTES:
            raise ValueError("invalid declared evidence size")
        if not isinstance(item["sha256"], str) or not SHA.fullmatch(item["sha256"]):
            raise ValueError("SHA-256 commitment required")
        raw = _regular(source / name)
        if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("collector evidence bytes differ from manifest")
        if SECRET_TEXT.search(raw):
            raise ValueError("possible credential in collector export")
        seen.add(name)
        kinds.add(kind)
        verified[name] = raw
    if not {"collector_source", "service_unit", "session_record", "capture_manifest"} <= kinds:
        raise ValueError("source, unit, session record and capture manifest are all required")
    return manifest, manifest_raw, verified


def freeze_export(source, output, *, expected_source_host="173.255.234.236"):
    """Copy once with fsync and independent readback; never mark it admitted."""
    source, output = Path(source).absolute(), Path(output).absolute()
    manifest, manifest_raw, verified = validate_export(
        source, expected_source_host=expected_source_host)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    copied = {}
    for name, raw in verified.items():
        path = output / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        copied[name] = file_hash(path)
    manifest_path = output / "source-manifest.json"
    fd = os.open(manifest_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(manifest_raw)
        stream.flush()
        os.fsync(stream.fileno())
    if copied != {item["name"]: item["sha256"] for item in manifest["files"]}:
        raise ValueError("frozen collector evidence readback failed")
    receipt = {"schema": "market_collector_evidence_intake_v1",
        "source_host": manifest["source_host"], "source_manifest_sha256": file_hash(manifest_path),
        "file_sha256": copied, "evidence_class": "unreviewed_source_export",
        "scientific_admission": False, "scoring_ready": False,
        "remaining_review": ["receipt_clock_definition", "message_write_order",
            "subscription_sequence_scope", "reconnect_and_snapshot_reset", "capture_session_coverage"],
        "secrets_expected": False, "research_result": False}
    fresh_json(output / "intake-receipt.json", receipt)
    # Re-read the original export after the copy and the entire frozen copy.
    # This catches a source edit during intake without making the frozen
    # directory look like a new, independently produced server export.
    again, again_raw, again_files = validate_export(
        source, expected_source_host=expected_source_host)
    if again != manifest or again_raw != manifest_raw or set(again_files) != set(verified):
        raise ValueError("source export changed during intake")
    for name, expected in copied.items():
        if file_hash(output / name) != expected:
            raise ValueError("frozen collector evidence changed during readback")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-source-host", required=True)
    args = parser.parse_args()
    print(canonical(freeze_export(args.source, args.output,
                                  expected_source_host=args.expected_source_host)))
