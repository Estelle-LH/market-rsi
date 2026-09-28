"""Pure verification of one exact Gate 1 production-CLI canary evidence tree.

The caller must supply the receipt path and every current commitment.  This
module performs no lookup, subprocess, network, credential, budget, or state
operation.  A bare digest is deliberately insufficient.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any

from market_rsi import canonical
from supervisor_harness import p0_gate1_controller_adapter as controller_adapter
from supervisor_harness import prospective_source_scope_decision as source_scope


SCHEMA = "market_gate1_canary_evidence_verification_v1"
CANARY_SCHEMA = "market_p0_gate1_controller_production_cli_canary_v1"
BOOTSTRAP_CANARY_SCHEMA = "market_p0_gate1_controller_production_cli_canary_v2"
FIRST_CANARY_BOOTSTRAP_SCHEMA = "market_gate1_first_canary_bootstrap_v2"
FIRST_CANARY_BOOTSTRAP_VERIFICATION_SCHEMA = (
    "market_gate1_first_canary_bootstrap_verification_v2")
FIRST_CANARY_BOOTSTRAP_FILE = "first-canary-bootstrap.json"
LEGACY_SYNTHETIC_RELEASE_TAG = "market-rsi-protocol-v-synthetic-cli-canary"
PUBLISHED_ORIGIN = "https://github.com/Estelle-LH/market-rsi.git"
FIRST_CANARY_CHILD_RELATIVE = (
    "supervisor_harness/p0_gate1_controller_cli_canary_child.py")
_SOURCE_ROOT = Path(__file__).resolve().parents[1]
FIRST_CANARY_CHILD_ENTRY = (_SOURCE_ROOT / FIRST_CANARY_CHILD_RELATIVE).resolve()
ZERO = "0" * 64
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_MAX_FILE_BYTES = 16 * 1024 * 1024
_MAX_PRIOR_CHAIN_DEPTH = 8
PRIOR_VERIFICATION_FILE = "prior-canary-verification.json"
_ADMISSION_V5_FIELDS = {
    "schema", "cycle_id", "execution_mode", "automatic_retry",
    "formal_data_admitted", "public_fetch_authorized",
    "provider_sample_max", "packet_sha256", "source_sha256",
    "prior_canary_sha256", "publication_sha256", "runtime_sha256",
    "budget_bucket", "budget_cap_usd", "budget_experiment_id", "provider",
    "upper_usd_not_invoice",
}
_ADMISSION_V6_FIELDS = _ADMISSION_V5_FIELDS | {
    "prior_canary_verification_sha256",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA256")
    return value


def _sha1(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA1.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase full Git object ID")
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def _parse_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number: {value}")))
        pending = [value]
        while pending:
            item = pending.pop()
            if type(item) is float and not math.isfinite(item):
                raise ValueError("non-finite JSON number")
            if type(item) is dict:
                pending.extend(item.values())
            elif type(item) is list:
                pending.extend(item)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid {label} JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _path_identity(info: os.stat_result) -> tuple[int, int, int]:
    """Stable ancestor identity; child activity may change directory times."""
    return (info.st_dev, info.st_ino, info.st_mode)


def _canonical_path_chain(
        path: Path, label: str) -> tuple[tuple[Path, tuple[int, int, int]], ...]:
    """Reject aliases/symlinked ancestors and snapshot their identities."""
    if not path.is_absolute():
        raise ValueError(f"{label} path must be absolute")
    try:
        resolved_parent = path.parent.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise ValueError(f"missing or unresolvable {label}") from exc
    _require(path.parent == resolved_parent,
             f"{label} path must be canonical")
    current = Path(path.anchor)
    snapshots = []
    for component in path.parts[1:-1]:
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError as exc:
            raise ValueError(f"missing {label} ancestor") from exc
        _require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
                 f"{label} ancestor directories must not be symlinks")
        snapshots.append((current, _path_identity(info)))
    return tuple(snapshots)


def _confirm_path_chain(
        snapshots: tuple[tuple[Path, tuple[int, int, int]], ...],
        label: str) -> None:
    for path, expected in snapshots:
        try:
            observed = path.lstat()
        except FileNotFoundError as exc:
            raise ValueError(f"{label} ancestor disappeared") from exc
        _require(stat.S_ISDIR(observed.st_mode) and
                 not stat.S_ISLNK(observed.st_mode) and
                 _path_identity(observed) == expected,
                 f"{label} ancestor changed during verification")


def _safe_directory(path: Path, label: str) -> None:
    snapshots = _canonical_path_chain(path, label)
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ValueError(f"missing {label}") from exc
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValueError(f"{label} must be an exact non-symlink directory")
    _confirm_path_chain(snapshots, label)


def _read_regular(path: Path, label: str) -> bytes:
    """Read one bounded regular file without following its final component."""
    snapshots = _canonical_path_chain(path, label)
    try:
        before_name = path.lstat()
    except FileNotFoundError as exc:
        raise ValueError(f"missing {label}") from exc
    if not stat.S_ISREG(before_name.st_mode) or path.is_symlink():
        raise ValueError(f"{label} must be an exact regular file")
    if before_name.st_size > _MAX_FILE_BYTES:
        raise ValueError(f"{label} exceeds safe size")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"cannot safely open {label}") from exc
    try:
        before_fd = os.fstat(descriptor)
        _require(stat.S_ISREG(before_fd.st_mode), f"{label} is not regular")
        _require((before_fd.st_dev, before_fd.st_ino) ==
                 (before_name.st_dev, before_name.st_ino),
                 f"{label} changed during open")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            _require(total <= _MAX_FILE_BYTES, f"{label} exceeds safe size")
            chunks.append(chunk)
        after_fd = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        after_name = path.lstat()
    except FileNotFoundError as exc:
        raise ValueError(f"{label} disappeared during verification") from exc
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size,
                             item.st_mtime_ns, item.st_ctime_ns)
    _require(identity(before_fd) == identity(after_fd) == identity(after_name),
             f"{label} changed during verification")
    _confirm_path_chain(snapshots, label)
    return b"".join(chunks)


def _load_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular(path, label)
    return _parse_json(raw, label), raw


def _exact(value: dict[str, Any], keys: set[str], label: str) -> None:
    _require(set(value) == keys, f"invalid {label} fields")


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate_first_canary_publication(
        publication: dict[str, Any], *, expected_tag: str,
        expected_source_sha256: str,
        child_entry: Path = FIRST_CANARY_CHILD_ENTRY) -> dict[str, Any]:
    """Validate exact credential-free evidence from ``verify_published``."""
    _require(isinstance(publication, dict),
             "verified first-canary publication must be an object")
    _exact(publication, {
        "schema", "origin", "tag", "commit", "tag_object",
        "source_sha256", "source_hashes", "isolation_proven",
        "model_authorship_proven",
    }, "verified first-canary publication")
    expected_source_sha256 = _sha256(
        expected_source_sha256, "verified publication source")
    _require(isinstance(expected_tag, str) and
             re.fullmatch(r"market-rsi-protocol-v[a-z0-9.-]+",
                          expected_tag) is not None and
             len(expected_tag) <= 96 and
             "synthetic" not in expected_tag,
             "exact real first-canary release tag required")
    source_hashes = publication.get("source_hashes")
    _require(publication.get("schema") ==
             "market_rsi_protocol_publication_v1" and
             publication.get("origin") == PUBLISHED_ORIGIN and
             publication.get("tag") == expected_tag and
             _sha1(publication.get("commit"), "verified release commit") and
             _sha1(publication.get("tag_object"),
                   "verified release tag object") and
             publication.get("source_sha256") == expected_source_sha256 and
             isinstance(source_hashes, dict) and bool(source_hashes) and
             all(isinstance(name, str) and name and
                 not Path(name).is_absolute() and ".." not in Path(name).parts and
                 isinstance(value, str) and _SHA256.fullmatch(value)
                 for name, value in source_hashes.items()) and
             _digest(source_hashes) == expected_source_sha256 and
             publication.get("isolation_proven") is False and
             publication.get("model_authorship_proven") is False,
             "verified first-canary publication differs from exact release")
    child_entry = Path(child_entry)
    _require(child_entry == FIRST_CANARY_CHILD_ENTRY and
             child_entry.is_absolute() and child_entry.is_file() and
             not child_entry.is_symlink() and child_entry.resolve() == child_entry,
             "exact first-canary child required")
    _require(source_hashes.get(FIRST_CANARY_CHILD_RELATIVE) ==
             _hash(_read_regular(child_entry, "first-canary child")),
             "verified publication does not bind exact first-canary child")
    # Canonical round-trip returns an isolated JSON-only copy.
    return json.loads(_canonical(publication).decode("ascii"))


def first_canary_bootstrap_document(
        *, publication: dict[str, Any], runtime_sha256: str,
        child_entry: Path = FIRST_CANARY_CHILD_ENTRY) -> dict[str, Any]:
    """Return the one typed, offline-only proof accepted for a first canary.

    This is deliberately not a CLI switch or a generic missing-prior marker.
    Its only authority is to let the exact controlled synthetic child create
    one independently verifiable zero-provider receipt.
    """
    runtime_sha256 = _sha256(runtime_sha256, "bootstrap runtime")
    _require(isinstance(publication, dict),
             "verified first-canary publication must be an object")
    publication = validate_first_canary_publication(
        publication, expected_tag=publication.get("tag"),
        expected_source_sha256=publication.get("source_sha256"),
        child_entry=child_entry)
    child_sha256 = _hash(_read_regular(child_entry, "first-canary child"))
    return {
        "schema": FIRST_CANARY_BOOTSTRAP_SCHEMA,
        "authority": "user-authorized-zero-provider-first-canary-only",
        "authorization_date": "2026-09-25",
        "source_sha256": publication["source_sha256"],
        "runtime_sha256": runtime_sha256,
        "release": {key: publication[key]
                    for key in ("tag", "commit", "tag_object")},
        "publication": publication,
        "child_entry": {
            "relative_path": FIRST_CANARY_CHILD_RELATIVE,
            "sha256": child_sha256,
        },
        "execution_mode": "offline_fake_only",
        "live_provider_constructor_allowed": False,
        "provider_calls_max": 0,
        "actual_provider_cost_usd": "0",
        "prior_canary_receipt_required": False,
        "public_fetch_authorized": False,
        "formal_data_admitted": False,
        "automatic_retry": False,
    }


def verify_first_canary_bootstrap(
        bootstrap_path: Path, *, expected_bootstrap_sha256: str,
        expected_source_sha256: str, expected_runtime_sha256: str,
        expected_release_tag: str, expected_release_commit: str,
        expected_release_tag_object: str,
        expected_child_entry: Path = FIRST_CANARY_CHILD_ENTRY) -> dict[str, Any]:
    """Purely verify the exact typed proof for the first offline canary."""
    bootstrap_path = Path(bootstrap_path)
    _require(bootstrap_path.is_absolute() and
             bootstrap_path.name == FIRST_CANARY_BOOTSTRAP_FILE,
             "exact absolute first-canary bootstrap path required")
    expected_bootstrap_sha256 = _sha256(
        expected_bootstrap_sha256, "first-canary bootstrap")
    expected_source_sha256 = _sha256(
        expected_source_sha256, "bootstrap source")
    expected_runtime_sha256 = _sha256(
        expected_runtime_sha256, "bootstrap runtime")
    expected_child_entry = Path(expected_child_entry)
    observed, raw = _load_json(bootstrap_path, "first-canary bootstrap")
    _require(_hash(raw) == expected_bootstrap_sha256,
             "first-canary bootstrap hash mismatch")
    publication = observed.get("publication")
    publication = validate_first_canary_publication(
        publication, expected_tag=expected_release_tag,
        expected_source_sha256=expected_source_sha256,
        child_entry=expected_child_entry)
    _require(publication.get("commit") ==
             _sha1(expected_release_commit, "release commit") and
             publication.get("tag_object") ==
             _sha1(expected_release_tag_object, "release tag object"),
             "verified publication Git identity changed")
    expected = first_canary_bootstrap_document(
        publication=publication, runtime_sha256=expected_runtime_sha256,
        child_entry=expected_child_entry)
    _require(observed == expected,
             "first-canary bootstrap commitments differ")
    return {
        "schema": FIRST_CANARY_BOOTSTRAP_VERIFICATION_SCHEMA,
        "passed": True,
        "bootstrap_path": str(bootstrap_path),
        "bootstrap_sha256": expected_bootstrap_sha256,
        "source_sha256": expected_source_sha256,
        "runtime_sha256": expected_runtime_sha256,
        "release": dict(expected["release"]),
        "publication": publication,
        "child_entry": {
            "path": str(expected_child_entry),
            "sha256": expected["child_entry"]["sha256"],
        },
        "execution_mode": "offline_fake_only",
        "provider_calls": 0,
        "actual_provider_cost_usd": "0",
        "public_fetch_performed": False,
        "formal_data_admitted": False,
        "automatic_retry": False,
    }


def _load_jsonl(path: Path, label: str) -> tuple[list[dict[str, Any]], bytes]:
    raw = _read_regular(path, label)
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError(f"invalid {label} encoding") from exc
    _require(bool(lines), f"empty {label}")
    return [_parse_json(line.encode(), f"{label} line {index}")
            for index, line in enumerate(lines, 1)], raw


def _generic_journal(records: list[dict[str, Any]], label: str) -> None:
    previous = ZERO
    for index, record in enumerate(records):
        _exact(record, {"seq", "previous", "time", "event", "payload", "hash"},
               f"{label} record")
        _require(type(record["seq"]) is int and record["seq"] == index,
                 f"invalid {label} sequence")
        body = {key: value for key, value in record.items() if key != "hash"}
        _require(record["previous"] == previous and
                 _sha256(record["hash"], f"{label} record hash") == _digest(body),
                 f"changed {label} hash chain")
        _require(isinstance(record["time"], str) and record["time"],
                 f"invalid {label} time")
        _require(isinstance(record["payload"], dict), f"invalid {label} payload")
        previous = record["hash"]


def _watchdog_journal(records: list[dict[str, Any]], cycle_id: str,
                      child_hash: str) -> tuple[str, str]:
    previous = ZERO
    events = [item.get("event") for item in records]
    _require(len(records) >= 4 and events[0:2] ==
             ["initialize", "task_claim"] and
             events[-1] == "task_close" and
             all(event == "heartbeat" for event in events[2:-1]),
             "unexpected watchdog event sequence")
    for index, record in enumerate(records, 1):
        _exact(record, {"schema", "seq", "time_utc", "event", "payload",
                        "prev_sha256", "sha256"}, "watchdog record")
        _require(record["schema"] == "market_supervisor_watchdog_v1" and
                 type(record["seq"]) is int and record["seq"] == index and
                 record["prev_sha256"] == previous,
                 "invalid watchdog chain")
        body = {key: value for key, value in record.items() if key != "sha256"}
        _require(_sha256(record["sha256"], "watchdog hash") == _digest(body),
                 "changed watchdog hash chain")
        previous = record["sha256"]
    _require(records[0]["payload"] == {},
             "invalid watchdog initialization")
    claim = records[1]["payload"]
    _require(claim.get("task_id") == cycle_id and
             claim.get("status") == "active" and
             claim.get("incident_id") is None and
             claim.get("data_gate") is None and
             claim.get("data_admission_sha256") is None,
             "invalid watchdog task claim")
    process = claim.get("process_identity")
    container = claim.get("container_identity")
    _require(isinstance(process, dict) and type(process.get("pid")) is int and
             process["pid"] > 0 and _SHA256.fullmatch(
                 str(process.get("command_sha256", ""))) is not None,
             "invalid watchdog process identity")
    _require(isinstance(container, dict) and
             container.get("name") == f"market-rsi-b-{cycle_id}" and
             container.get("label") == f"market-rsi-b-{cycle_id}",
             "invalid watchdog container identity")
    for record in records[2:-1]:
        heartbeat = record["payload"]
        _require(isinstance(heartbeat, dict),
                 "invalid watchdog heartbeat")
        _exact(heartbeat, {"task_id", "material_progress", "progress_sha256"},
               "watchdog heartbeat")
        material = heartbeat["material_progress"]
        _require(heartbeat["task_id"] == cycle_id and type(material) is bool,
                 "invalid watchdog heartbeat")
        if material:
            _sha256(heartbeat["progress_sha256"], "watchdog progress")
        else:
            _require(heartbeat["progress_sha256"] is None,
                     "non-material watchdog heartbeat has progress")
    close = records[-1]["payload"]
    _require(close == {"task_id": cycle_id, "outcome": "passed",
                       "old_id_reusable": False,
                       "result_sha256": child_hash},
             "watchdog did not terminally close exact child")
    return records[1]["sha256"], previous


def _reverify_prior_record(
        record: dict[str, Any], admission: dict[str, Any], *,
        expected_source_sha256: str, expected_runtime_sha256: str,
        expected_release_tag: str, expected_release_commit: str,
        expected_release_tag_object: str,
        visited_receipts: frozenset[str], depth: int,
        expected_bootstrap_path: Path | None = None) -> dict[str, Any]:
    """Replay the stored prior verification from its own exact commitments."""
    if record.get("schema") == FIRST_CANARY_BOOTSTRAP_VERIFICATION_SCHEMA:
        _require(expected_bootstrap_path is not None,
                 "bootstrap verification is not allowed for this receipt")
        _exact(record, {
            "schema", "passed", "bootstrap_path", "bootstrap_sha256",
            "source_sha256", "runtime_sha256", "release", "publication",
            "child_entry", "execution_mode", "provider_calls",
            "actual_provider_cost_usd", "public_fetch_performed",
            "formal_data_admitted", "automatic_retry",
        }, "first-canary bootstrap verification")
        _require(record.get("bootstrap_path") == str(expected_bootstrap_path) and
                 record.get("bootstrap_sha256") ==
                 admission.get("prior_canary_sha256") and
                 record.get("source_sha256") == expected_source_sha256 and
                 record.get("runtime_sha256") == expected_runtime_sha256 and
                 record.get("release") == {
                     "tag": expected_release_tag,
                     "commit": expected_release_commit,
                     "tag_object": expected_release_tag_object,
                 } and
                 isinstance(record.get("publication"), dict) and
                 record["publication"].get("source_sha256") ==
                 expected_source_sha256 and
                 record["publication"].get("tag") == expected_release_tag and
                 record["publication"].get("commit") ==
                 expected_release_commit and
                 record["publication"].get("tag_object") ==
                 expected_release_tag_object and
                 record.get("child_entry") == {
                     "path": str(FIRST_CANARY_CHILD_ENTRY),
                     "sha256": _hash(_read_regular(
                         FIRST_CANARY_CHILD_ENTRY, "first-canary child")),
                 } and
                 record.get("execution_mode") == "offline_fake_only" and
                 type(record.get("provider_calls")) is int and
                 record["provider_calls"] == 0 and
                 record.get("actual_provider_cost_usd") == "0" and
                 record.get("public_fetch_performed") is False and
                 record.get("formal_data_admitted") is False and
                 record.get("automatic_retry") is False,
                 "stored first-canary bootstrap verification is not exact")
        replayed = verify_first_canary_bootstrap(
            expected_bootstrap_path,
            expected_bootstrap_sha256=record["bootstrap_sha256"],
            expected_source_sha256=expected_source_sha256,
            expected_runtime_sha256=expected_runtime_sha256,
            expected_release_tag=expected_release_tag,
            expected_release_commit=expected_release_commit,
            expected_release_tag_object=expected_release_tag_object,
            expected_child_entry=FIRST_CANARY_CHILD_ENTRY,
        )
        _require(replayed == record,
                 "stored first-canary bootstrap differs from independent replay")
        return replayed
    _exact(record, {
        "schema", "passed", "receipt_path", "receipt_sha256", "cycle_id",
        "source_sha256", "runtime_sha256", "release", "provider_calls",
        "actual_provider_cost_usd", "public_fetch_performed",
        "formal_data_admitted", "automatic_retry", "compiled_plan_sha256",
        "terminal_cleanup_verified", "evidence_sha256",
    }, "prior canary verification")
    release = record.get("release")
    _require(isinstance(release, dict),
             "invalid prior canary release verification")
    _exact(release, {"tag", "commit", "tag_object"},
           "prior canary release verification")
    evidence = record.get("evidence_sha256")
    _require(record.get("schema") == SCHEMA and record.get("passed") is True and
             isinstance(record.get("receipt_path"), str) and
             Path(record["receipt_path"]).is_absolute() and
             _sha256(record.get("receipt_sha256"), "stored prior receipt") ==
             admission.get("prior_canary_sha256") and
             record.get("source_sha256") == expected_source_sha256 and
             record.get("runtime_sha256") == expected_runtime_sha256 and
             release == {"tag": expected_release_tag,
                         "commit": expected_release_commit,
                         "tag_object": expected_release_tag_object} and
             type(record.get("provider_calls")) is int and
             record["provider_calls"] == 0 and
             record.get("actual_provider_cost_usd") == "0" and
             record.get("public_fetch_performed") is False and
             record.get("formal_data_admitted") is False and
             record.get("automatic_retry") is False and
             record.get("compiled_plan_sha256") is None and
             record.get("terminal_cleanup_verified") is True and
             isinstance(evidence, dict) and bool(evidence) and
             all(isinstance(name, str) and name and
                 isinstance(value, str) and _SHA256.fullmatch(value)
                 for name, value in evidence.items()),
             "stored prior canary verification is not exact safe evidence")
    replayed = _verify_gate1_canary_receipt(
        Path(record["receipt_path"]),
        expected_receipt_sha256=record["receipt_sha256"],
        expected_source_sha256=record["source_sha256"],
        expected_runtime_sha256=record["runtime_sha256"],
        expected_release_tag=release["tag"],
        expected_release_commit=release["commit"],
        expected_release_tag_object=release["tag_object"],
        visited_receipts=visited_receipts,
        depth=depth + 1,
    )
    _require(replayed == record,
             "stored prior canary verification differs from independent replay")
    return replayed


def verify_gate1_canary_receipt(
        receipt_path: Path,
        *,
        expected_receipt_sha256: str,
        expected_source_sha256: str,
        expected_runtime_sha256: str,
        expected_release_tag: str,
        expected_release_commit: str,
        expected_release_tag_object: str) -> dict[str, Any]:
    """Verify one exact receipt and its bounded, acyclic prior chain."""
    return _verify_gate1_canary_receipt(
        receipt_path,
        expected_receipt_sha256=expected_receipt_sha256,
        expected_source_sha256=expected_source_sha256,
        expected_runtime_sha256=expected_runtime_sha256,
        expected_release_tag=expected_release_tag,
        expected_release_commit=expected_release_commit,
        expected_release_tag_object=expected_release_tag_object,
        visited_receipts=frozenset(),
        depth=0,
    )


def _verify_gate1_canary_receipt(
        receipt_path: Path,
        *,
        expected_receipt_sha256: str,
        expected_source_sha256: str,
        expected_runtime_sha256: str,
        expected_release_tag: str,
        expected_release_commit: str,
        expected_release_tag_object: str,
        visited_receipts: frozenset[str],
        depth: int) -> dict[str, Any]:
    """Verify one exact receipt and its evidence; return a compact PASS record."""
    _require(type(depth) is int and depth >= 0 and
             depth <= _MAX_PRIOR_CHAIN_DEPTH,
             "prior canary chain exceeds bounded depth")
    receipt_path = Path(receipt_path)
    if not receipt_path.is_absolute():
        raise ValueError("exact absolute canary receipt path required")
    _canonical_path_chain(receipt_path, "canary receipt")
    receipt_key = str(receipt_path)
    _require(receipt_key not in visited_receipts,
             "prior canary receipt path cycle detected")
    visited_receipts = visited_receipts | {receipt_key}
    expected_receipt_sha256 = _sha256(expected_receipt_sha256, "receipt")
    expected_source_sha256 = _sha256(expected_source_sha256, "source")
    expected_runtime_sha256 = _sha256(expected_runtime_sha256, "runtime")
    _sha1(expected_release_commit, "release commit")
    _sha1(expected_release_tag_object, "release tag object")
    _require(isinstance(expected_release_tag, str) and
             re.fullmatch(r"market-rsi-protocol-v[a-z0-9.-]+",
                          expected_release_tag) is not None and
             len(expected_release_tag) <= 96,
             "invalid exact release tag")
    _require(receipt_path.name == "canary-result.json",
             "canonical canary receipt filename required")
    root = receipt_path.parent
    _safe_directory(root, "canary evidence root")
    receipt, receipt_raw = _load_json(receipt_path, "canary receipt")
    _require(_hash(receipt_raw) == expected_receipt_sha256,
             "canary receipt hash mismatch")
    bootstrap_receipt = receipt.get("schema") == BOOTSTRAP_CANARY_SCHEMA
    receipt_fields = {
        "schema", "cycle_id", "passed", "production_parent_used",
        "production_cli_arguments_used", "supervisor_claim_verified_by_child",
        "offline_provider_substituted", "provider_calls",
        "actual_provider_cost_usd", "synthetic_ledger_metered_usd",
        "public_fetch_performed", "formal_data_admitted",
        "review_only_without_catalog", "automatic_retry",
        "packet_file_sha256", "packet_canonical_sha256",
        "child_result_sha256", "supervisor_claim_sha256",
        "supervisor_result_sha256"}
    if bootstrap_receipt:
        receipt_fields.add("first_canary_bootstrap_used")
    _exact(receipt, receipt_fields, "canary receipt")
    cycle_id = receipt["cycle_id"]
    _require(receipt["schema"] in {CANARY_SCHEMA, BOOTSTRAP_CANARY_SCHEMA} and
             isinstance(cycle_id, str) and cycle_id == root.name + "-transaction",
             "wrong canary schema or cycle identity")
    _require(receipt["passed"] is True and
             receipt["production_parent_used"] is True and
             receipt["production_cli_arguments_used"] is True and
             receipt["supervisor_claim_verified_by_child"] is True and
             receipt["offline_provider_substituted"] is True and
             type(receipt["provider_calls"]) is int and receipt["provider_calls"] == 0 and
             receipt["actual_provider_cost_usd"] == "0" and
             receipt["public_fetch_performed"] is False and
             receipt["formal_data_admitted"] is False and
             receipt["review_only_without_catalog"] is True and
             receipt["automatic_retry"] is False and
             (not bootstrap_receipt or
              receipt["first_canary_bootstrap_used"] is True),
             "canary did not prove the required zero-provider boundary")

    tx_root = root / cycle_id
    supervisor_root = root / "supervisor"
    adapter_root = tx_root / "adapter" / cycle_id
    for directory, label in ((tx_root, "transaction root"),
                             (supervisor_root, "supervisor root"),
                             (adapter_root, "adapter root"),
                             (root / "budget", "budget root"),
                             (root / "global-state", "global-state root"),
                             (supervisor_root / "watchdog", "watchdog root"),
                             (root / "claims", "claim registry")):
        _safe_directory(directory, label)

    child, child_raw = _load_json(tx_root / "result.json", "child result")
    supervisor_claim, supervisor_claim_raw = _load_json(
        supervisor_root / "supervisor-claim.json", "supervisor claim")
    supervisor_result, supervisor_result_raw = _load_json(
        supervisor_root / "result.json", "supervisor result")
    _require(_hash(child_raw) == _sha256(receipt["child_result_sha256"],
                                         "child result") and
             _hash(supervisor_claim_raw) == _sha256(
                 receipt["supervisor_claim_sha256"], "supervisor claim") and
             _hash(supervisor_result_raw) == _sha256(
                 receipt["supervisor_result_sha256"], "supervisor result"),
             "direct canary evidence hash mismatch")
    _exact(child, {"schema", "cycle_id", "passed", "execution_mode",
                   "provider_sample_max", "automatic_retry", "formal_data_admitted",
                   "public_fetch_performed", "input_sha256", "admission_sha256",
                   "preflight_sha256", "publication_sha256", "runtime_sha256",
                   "adapter_result_sha256", "review_sha256", "compiled_plan_sha256",
                   "submission_kind", "ledger_outcome", "supervisor_outcome",
                   "upper_usd_not_invoice"}, "child result")
    _require(child["schema"] == "market_p0_gate1_controller_outer_result_v1" and
             child["cycle_id"] == cycle_id and child["passed"] is True and
             child["execution_mode"] == "offline_fake" and
             type(child["provider_sample_max"]) is int and
             child["provider_sample_max"] == 1 and
             child["automatic_retry"] is False and
             child["formal_data_admitted"] is False and
             child["public_fetch_performed"] is False and
             child["compiled_plan_sha256"] is None and
             child["ledger_outcome"] == "metered_terminal" and
             child["supervisor_outcome"] == "passed",
             "child result violates canary boundary")

    linked: dict[str, tuple[str, str]] = {
        "input": ("input.json", child["input_sha256"]),
        "admission": ("admission.json", child["admission_sha256"]),
        "preflight": ("preflight.json", child["preflight_sha256"]),
        "publication": ("publication.json", child["publication_sha256"]),
        "runtime": ("runtime.json", child["runtime_sha256"]),
        "review": ("review.json", child["review_sha256"]),
    }
    documents: dict[str, dict[str, Any]] = {}
    evidence_hashes: dict[str, str] = {"canary-result.json": expected_receipt_sha256,
                                       f"{cycle_id}/result.json": _hash(child_raw)}
    for label, (name, expected_hash) in linked.items():
        document, raw = _load_json(tx_root / name, label)
        _require(_hash(raw) == _sha256(expected_hash, label),
                 f"changed linked {label}")
        documents[label] = document
        evidence_hashes[f"{cycle_id}/{name}"] = _hash(raw)

    packet, packet_raw = _load_json(root / "controller-input.json", "controller packet")
    packet_file_hash = _hash(packet_raw)
    packet_digest = _digest(packet)
    _require(packet_file_hash == _sha256(receipt["packet_file_sha256"], "packet file") and
             packet_digest == _sha256(receipt["packet_canonical_sha256"],
                                      "canonical packet"),
             "controller packet commitment mismatch")
    evidence_hashes["controller-input.json"] = packet_file_hash

    adapter, adapter_raw = _load_json(adapter_root / "result.json", "adapter result")
    _require(_hash(adapter_raw) == _sha256(child["adapter_result_sha256"],
                                           "adapter result"),
             "changed linked adapter result")
    evidence_hashes[f"{cycle_id}/adapter/{cycle_id}/result.json"] = _hash(adapter_raw)
    adapter_fields = {"schema", "cycle_id", "dispatch_gate_called", "execution_mode",
                     "automatic_retry", "provider_called", "sample_count_max",
                     "formal_data_admitted", "public_fetch_performed", "sealed_data_read",
                     "completed_live_decision_pending_review", "valid_plan_only_decision",
                     "valid_non_executable_proposal", "submission_kind", "failure_type",
                     "requested_model", "reported_model", "input_tokens", "output_tokens",
                     "cached_input_tokens", "metered_cost_usd_not_invoice", "tools",
                     "registry_claim_sha256", "artifact_sha256"}
    adapter_v6 = adapter.get("schema") == "market_p0_gate1_controller_adapter_result_v6"
    _require(not bootstrap_receipt or adapter_v6,
             "first-canary bootstrap requires the exact current adapter")
    if adapter_v6:
        adapter_fields.add("valid_source_scope_decision")
    _exact(adapter, adapter_fields, "adapter result")
    _require(adapter["schema"] in {
                 "market_p0_gate1_controller_adapter_result_v5",
                 "market_p0_gate1_controller_adapter_result_v6"} and
             adapter["cycle_id"] == cycle_id and
             adapter["dispatch_gate_called"] is True and
             adapter["execution_mode"] == "offline_fake" and
             adapter["automatic_retry"] is False and
             adapter["provider_called"] is False and
             type(adapter["sample_count_max"]) is int and
             adapter["sample_count_max"] == 1 and
             adapter["formal_data_admitted"] is False and
             adapter["public_fetch_performed"] is False and
             adapter["sealed_data_read"] is False and
             adapter["completed_live_decision_pending_review"] is False and
             adapter["valid_plan_only_decision"] is True and
             adapter["valid_non_executable_proposal"] is False and
             adapter["submission_kind"] == (
                 "source_scope_decision" if adapter_v6 else "bounded_plan") and
             (not adapter_v6 or adapter["valid_source_scope_decision"] is True) and
             adapter["failure_type"] is None,
             "adapter result violates zero-provider boundary")
    artifact_hashes = adapter["artifact_sha256"]
    allowed_artifacts = {"claim.json", "cost-preview.json", "decision.json",
                         "encoded.json", "failure.json", "field-provenance.json",
                         "input.json", "proposal.json", "provider-receipt.json",
                         "raw-response.json", "raw-response.txt", "request.json",
                         "submission.json", "task.json"}
    if adapter_v6:
        allowed_artifacts.add("decision-provenance.json")
    _require(isinstance(artifact_hashes, dict) and
             set(artifact_hashes) == allowed_artifacts and
             artifact_hashes["failure.json"] is None and
             artifact_hashes["proposal.json"] is None and
             (not adapter_v6 or (
                 artifact_hashes["field-provenance.json"] is None and
                 artifact_hashes["task.json"] is None and
                 artifact_hashes["decision-provenance.json"] is not None)),
             "invalid adapter artifact manifest")
    absent_artifacts = {name for name, value in artifact_hashes.items()
                        if value is None}
    for name in sorted(allowed_artifacts - absent_artifacts):
        raw = _read_regular(adapter_root / name, f"adapter artifact {name}")
        _require(_hash(raw) == _sha256(artifact_hashes[name], name),
                 f"changed adapter artifact: {name}")
        evidence_hashes[f"{cycle_id}/adapter/{cycle_id}/{name}"] = _hash(raw)
    for absent in sorted(absent_artifacts):
        _require(not (adapter_root / absent).exists() and
                 not (adapter_root / absent).is_symlink(),
                 f"unexpected adapter artifact: {absent}")

    if adapter_v6:
        # A generic schema-valid D0 is insufficient.  Reproduce the exact
        # current request, parse the immutable terminal response through the
        # current adapter, and require every derived artifact byte-for-byte.
        _require(controller_adapter._packet(packet) == packet,
                 "v6 canary packet is not the exact current Controller packet")
        adapter_input, adapter_input_raw = _load_json(
            adapter_root / "input.json", "v6 adapter input")
        request, _ = _load_json(adapter_root / "request.json", "v6 request")
        encoded, _ = _load_json(adapter_root / "encoded.json", "v6 encoding")
        sampled, _ = _load_json(
            adapter_root / "raw-response.json", "v6 raw response")
        raw_text_bytes = _read_regular(
            adapter_root / "raw-response.txt", "v6 raw response text")
        try:
            raw_text = raw_text_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("invalid v6 raw response text encoding") from exc
        decision, _ = _load_json(adapter_root / "decision.json",
                                 "source-scope decision")
        submission, _ = _load_json(adapter_root / "submission.json",
                                   "source-scope submission")
        provenance, _ = _load_json(adapter_root / "decision-provenance.json",
                                   "source-scope provenance")
        turn = controller_adapter.request_turn(packet)
        expected_request = {
            "schema": controller_adapter.REQUEST_SCHEMA,
            "model": controller_adapter.MODEL,
            "messages": turn["messages"],
            "tools": turn["tools"],
            "reasoning_effort": turn["reasoning_effort"],
            "num_samples": 1,
            "temperature": 1.0,
            "seed": 23,
            "max_output_tokens": controller_adapter.MAX_OUTPUT_TOKENS,
            "input_sha256": _hash(adapter_input_raw),
        }
        expected_encoded = {
            "rendered_prompt": "offline-gate1:" + canonical(turn),
            "token_ids": list(controller_adapter.OFFLINE_FAKE_TOKEN_IDS),
            "tokenizer_repo": controller_adapter.HF_MODEL,
            "tokenizer_revision": controller_adapter.TOKENIZER_REVISION,
            "chat_template_sha256": controller_adapter.CHAT_TEMPLATE_SHA256,
        }
        input_tokens = controller_adapter._encoding(encoded)
        reconstructed_kind, reconstructed_decision, reconstructed_submission = (
            controller_adapter._submitted_action(raw_text, packet, cycle_id))
        reconstructed_provenance = controller_adapter._decision_provenance(
            reconstructed_submission, reconstructed_decision, packet,
            cycle_id, raw_text)
        expected_provider = controller_adapter._provider_receipt(
            sampled, input_tokens, provider_called=False)
        provider_for_v6, _ = _load_json(
            adapter_root / "provider-receipt.json", "v6 provider receipt")
        cost_preview, _ = _load_json(
            adapter_root / "cost-preview.json", "v6 cost preview")
        expected_preview = {
            "schema": "market_p0_gate1_controller_cost_preview_v1",
            "input_tokens": input_tokens,
            "max_output_tokens": controller_adapter.MAX_OUTPUT_TOKENS,
            "rates": controller_adapter.RATES,
            "upper_usd_not_invoice": str(controller_adapter.cost(
                input_tokens, controller_adapter.MAX_OUTPUT_TOKENS)),
            "provider_called": False,
            "budget_mutated_by_adapter": False,
        }
        _require(adapter_input == packet and
                 request == expected_request and
                 encoded == expected_encoded and
                 sampled.get("text") == raw_text and
                 provider_for_v6 == expected_provider and
                 cost_preview == expected_preview and
                 reconstructed_kind == "source_scope_decision" and
                 submission == reconstructed_submission and
                 decision == reconstructed_decision and
                 provenance == reconstructed_provenance and
                 source_scope.validate_decision(decision) == decision and
                 decision.get("decision_status") == "scope_only_non_executable" and
                 all(value is False for value in decision["non_authority"].values()) and
                 adapter.get("tools") == [controller_adapter.SUBMIT_TOOL],
                 "v6 source-scope packet/response/decision lineage changed")

    provider, _ = _load_json(adapter_root / "provider-receipt.json",
                             "provider receipt")
    _require(provider.get("schema") ==
             "market_p0_gate1_controller_provider_receipt_v1" and
             provider.get("terminal") is True and
             provider.get("provider_called") is False and
             provider.get("automatic_retry") is False and
             type(provider.get("sample_count")) is int and
             provider["sample_count"] == 1,
             "provider receipt is not terminal zero-provider evidence")

    admission = documents["admission"]
    preflight = documents["preflight"]
    publication = documents["publication"]
    runtime = documents["runtime"]
    review = documents["review"]
    _exact(admission,
           _ADMISSION_V6_FIELDS if adapter_v6 else _ADMISSION_V5_FIELDS,
           "v6 admission" if adapter_v6 else "v5 admission")
    _require(admission.get("schema") == "market_p0_gate1_controller_outer_v1" and
             admission.get("cycle_id") == cycle_id and
             admission.get("execution_mode") == "offline_fake" and
             admission.get("automatic_retry") is False and
             admission.get("formal_data_admitted") is False and
             admission.get("public_fetch_authorized") is False and
             type(admission.get("provider_sample_max")) is int and
             admission["provider_sample_max"] == 1 and
             admission.get("packet_sha256") == packet_digest and
             admission.get("source_sha256") == expected_source_sha256,
             "admission does not bind the exact safe canary")
    bootstrap_verification = None
    if adapter_v6:
        prior_verification, prior_verification_raw = _load_json(
            tx_root / PRIOR_VERIFICATION_FILE,
            "persisted prior canary verification")
        _require(_digest(prior_verification) == _sha256(
                     admission.get("prior_canary_verification_sha256"),
                     "prior canary verification"),
                 "persisted prior canary verification digest mismatch")
        expected_bootstrap_path = (
            root / FIRST_CANARY_BOOTSTRAP_FILE if bootstrap_receipt else None)
        replayed_prior = _reverify_prior_record(
            prior_verification, admission,
            expected_source_sha256=expected_source_sha256,
            expected_runtime_sha256=expected_runtime_sha256,
            expected_release_tag=expected_release_tag,
            expected_release_commit=expected_release_commit,
            expected_release_tag_object=expected_release_tag_object,
            visited_receipts=visited_receipts,
            depth=depth,
            expected_bootstrap_path=expected_bootstrap_path,
        )
        if bootstrap_receipt:
            bootstrap_verification = replayed_prior
        evidence_hashes[f"{cycle_id}/{PRIOR_VERIFICATION_FILE}"] = _hash(
            prior_verification_raw)
        if bootstrap_receipt:
            bootstrap_raw = _read_regular(
                expected_bootstrap_path, "first-canary bootstrap")
            _require(_hash(bootstrap_raw) == admission.get("prior_canary_sha256"),
                     "first-canary bootstrap/admission hash mismatch")
            evidence_hashes[FIRST_CANARY_BOOTSTRAP_FILE] = _hash(bootstrap_raw)
    _require(preflight == {"schema": "market_bounded_live_outer_preflight_v3",
                           "cycle_id": cycle_id, "clear": True,
                           "matching_process_ids": [], "matching_container_ids": []},
             "process/container preflight was not clear")
    _exact(publication, {"schema", "origin", "tag", "commit", "tag_object",
                         "source_sha256", "source_hashes", "isolation_proven",
                         "model_authorship_proven"}, "publication")
    _require(publication["schema"] == "market_rsi_protocol_publication_v1" and
             publication["tag"] == expected_release_tag and
             publication["commit"] == expected_release_commit and
             publication["tag_object"] == expected_release_tag_object and
             publication["source_sha256"] == expected_source_sha256 and
             isinstance(publication["source_hashes"], dict) and
             _digest(publication["source_hashes"]) == expected_source_sha256 and
             admission.get("publication_sha256") == _digest(publication),
             "release/source commitment mismatch")
    if bootstrap_receipt:
        verified_publication = (bootstrap_verification or {}).get(
            "publication")
        _require(isinstance(bootstrap_verification, dict) and
                 isinstance(verified_publication, dict) and
                 verified_publication.get("origin") == PUBLISHED_ORIGIN and
                 all(verified_publication.get(key) == publication.get(key)
                     for key in (
                         "schema", "tag", "commit", "tag_object",
                         "source_sha256", "source_hashes",
                         "isolation_proven", "model_authorship_proven")) and
                 publication["source_hashes"].get(
                     FIRST_CANARY_CHILD_RELATIVE) ==
                 bootstrap_verification.get("child_entry", {}).get("sha256"),
                 "verified publication/first-canary source commitment differs")
    runtime_digest = _digest(runtime)
    _require(runtime.get("schema") == "market_bounded_live_outer_runtime_v3" and
             runtime_digest == expected_runtime_sha256 and
             admission.get("runtime_sha256") == expected_runtime_sha256,
             "runtime commitment mismatch")
    root_runtime, root_runtime_raw = _load_json(root / "runtime.json", "root runtime")
    _require(root_runtime == runtime and _hash(root_runtime_raw) == child["runtime_sha256"],
             "root and child runtime evidence differ")
    _require(review.get("schema") == "market_p0_gate1_controller_review_v1" and
             review.get("cycle_id") == cycle_id and
             review.get("adapter_passed") is True and
             review.get("adapter_result_sha256") == child["adapter_result_sha256"] and
             review.get("automatic_retry") is False and
             review.get("compiled_plan_sha256") is None and
             review.get("formal_data_admitted") is False and
             review.get("public_fetch_performed") is False and
             review.get("proposal_sha256") is None and
             review.get("provider_receipt_valid") is True and
             review.get("publication_runtime_state_unchanged") is True,
             "review did not preserve the non-executing canary boundary")

    claim, claim_raw = _load_json(root / "claims" / f"{cycle_id}.json",
                                  "adapter claim registry")
    adapter_claim, adapter_claim_raw = _load_json(adapter_root / "claim.json",
                                                  "adapter claim")
    _require(claim == adapter_claim and _hash(claim_raw) == _hash(adapter_claim_raw) ==
             adapter["registry_claim_sha256"] == artifact_hashes["claim.json"] and
             claim.get("cycle_id") == cycle_id and
             claim.get("execution_mode") == "offline_fake" and
             claim.get("automatic_retry") is False and
             claim.get("formal_data_admitted") is False and
             claim.get("num_samples") == 1 and
             claim.get("packet_sha256") == packet_digest and
             claim.get("runtime", {}).get("python_executable") ==
             runtime.get("python_executable") and
             claim.get("runtime", {}).get("python_version") == runtime.get("python_version"),
             "adapter claim does not bind exact packet/runtime")
    if adapter_v6:
        expected_claim = {
            "schema": controller_adapter.ADAPTER_SCHEMA,
            "cycle_id": cycle_id,
            "packet_sha256": packet_digest,
            "source_hashes": controller_adapter._sources(),
            "runtime": {
                "python_executable": runtime.get("python_executable"),
                "python_version": runtime.get("python_version"),
            },
            "requested_model": controller_adapter.MODEL,
            "tools": [controller_adapter.SUBMIT_TOOL],
            "scope_options_sha256": _digest(
                packet["prospective_source_scope_decision"]),
            "rights_status": (
                "unknown_each_requested_use_requires_later_D2_evidence"),
            "reasoning_effort": "low",
            "num_samples": 1,
            "temperature": 1.0,
            "seed": 23,
            "max_output_tokens": controller_adapter.MAX_OUTPUT_TOKENS,
            "sample_timeout_seconds": controller_adapter.SAMPLE_TIMEOUT_SECONDS,
            "automatic_retry": False,
            "execution_mode": "offline_fake",
            "formal_data_admitted": False,
        }
        _require(claim == expected_claim,
                 "v6 adapter claim differs from current adapter contract")
    tx_input_raw = _read_regular(tx_root / "input.json", "transaction input")
    tx_encoded_raw = _read_regular(tx_root / "preencoded.json", "preencoded request")
    _require(_hash(tx_input_raw) == artifact_hashes["input.json"] and
             _hash(tx_encoded_raw) == artifact_hashes["encoded.json"],
             "duplicated adapter evidence differs")

    _require(supervisor_claim.get("schema") ==
             "market_bounded_live_supervisor_claim_v1" and
             supervisor_claim.get("cycle_id") == cycle_id and
             supervisor_claim.get("task_id") == cycle_id and
             supervisor_claim.get("automatic_retry") is False,
             "invalid production supervisor claim")
    _require(supervisor_result == {
        "schema": "market_bounded_live_supervisor_parent_v1",
        "cycle_id": cycle_id, "passed": True, "automatic_retry": False,
        "child_exit_code": 0, "incident_created": False, "incident_id": None,
        "watchdog_head_sha256": supervisor_result.get("watchdog_head_sha256")},
        "production parent did not terminally reap the child")
    watchdog_records, watchdog_raw = _load_jsonl(
        supervisor_root / "watchdog" / "journal.jsonl", "watchdog journal")
    first_watchdog_head, final_watchdog_head = _watchdog_journal(
        watchdog_records, cycle_id, _hash(child_raw))
    _require(supervisor_claim.get("watchdog_head_sha256") == first_watchdog_head and
             supervisor_result.get("watchdog_head_sha256") == final_watchdog_head and
             watchdog_records[1]["payload"].get("process_identity", {}).get("pid") ==
             supervisor_claim.get("pid"),
             "supervisor/watchdog process chain mismatch")
    snapshot, snapshot_raw = _load_json(
        supervisor_root / "watchdog" / "snapshot.json", "watchdog snapshot")
    _require(snapshot.get("schema") == "market_supervisor_watchdog_v1" and
             snapshot.get("initialized") is True and
             snapshot.get("seq") == len(watchdog_records) and
             snapshot.get("head_sha256") == final_watchdog_head and
             snapshot.get("last_event_utc") ==
             watchdog_records[-1]["time_utc"] and
             snapshot.get("active_task") is None and
             snapshot.get("claimed_task_ids") == [cycle_id] and
             snapshot.get("incidents") == [],
             "watchdog snapshot is not terminal and clean")
    evidence_hashes["supervisor/watchdog/journal.jsonl"] = _hash(watchdog_raw)
    evidence_hashes["supervisor/watchdog/snapshot.json"] = _hash(snapshot_raw)
    child_log, child_log_raw = _load_json(supervisor_root / "child.log", "child log")
    _require(child_log == child, "supervisor child log differs from child result")

    global_records, global_raw = _load_jsonl(root / "global-state" / "journal.jsonl",
                                             "global-state journal")
    _generic_journal(global_records, "global-state journal")
    _require([record["event"] for record in global_records] ==
             ["initialize", "cycle_claim", "cycle_close"],
             "unexpected global-state sequence")
    global_claim = global_records[1]["payload"]
    global_close = global_records[2]["payload"]
    if adapter_v6:
        prior_receipt = _sha256(admission.get("prior_canary_sha256"),
                                "v6 prior canary receipt")
        prior_verification = _sha256(
            admission.get("prior_canary_verification_sha256"),
            "v6 prior canary verification")
        _require(prior_receipt != ZERO and prior_verification != ZERO and
                 global_claim.get("cycle_id") == cycle_id and
                 global_claim.get("source_sha256") == expected_source_sha256 and
                 global_claim.get("prior_canary_sha256") == prior_receipt and
                 global_close == {"cycle_id": cycle_id, "outcome": "passed",
                                  "review_sha256": child["review_sha256"]},
                 "v6 global state does not bind its verified prior receipt")
    else:
        runner_hash = publication["source_hashes"].get(
            "supervisor_harness/run_p0_gate1_controller_production_cli_canary.py")
        _require(global_claim.get("cycle_id") == cycle_id and
                 global_claim.get("source_sha256") == expected_source_sha256 and
                 global_claim.get("prior_canary_sha256") == runner_hash and
                 global_close == {"cycle_id": cycle_id, "outcome": "passed",
                                  "review_sha256": child["review_sha256"]},
                 "legacy v5 global state is not terminally closed on exact evidence")
    decision_raw = _read_regular(root / "decision.md", "canary decision document")
    _require(global_records[0]["payload"] ==
             {"decision_doc_sha256": _hash(decision_raw)} and
             global_claim.get("decision_doc_sha256") == _hash(decision_raw),
             "global-state decision commitment mismatch")
    evidence_hashes["global-state/journal.jsonl"] = _hash(global_raw)

    budget_records, budget_raw = _load_jsonl(root / "budget" / "journal.jsonl",
                                             "budget journal")
    _generic_journal(budget_records, "budget journal")
    _require([record["event"] for record in budget_records] ==
             ["authorized", "reserved", "dispatched", "metered_terminal"],
             "budget did not end in one terminal synthetic dispatch")
    reservation = budget_records[1]["payload"]
    dispatch = budget_records[2]["payload"]
    terminal = budget_records[3]["payload"]
    _require(reservation.get("job_id") == cycle_id and
             reservation.get("input_sha256") == packet_digest and
             dispatch == {"job_id": cycle_id} and
             terminal.get("job_id") == cycle_id and
             terminal.get("metered_usd") == receipt["synthetic_ledger_metered_usd"],
             "budget journal identity/terminal mismatch")
    meter, meter_raw = _load_json(
        root / "budget" / f"{cycle_id}.metering.json", "budget meter")
    _require(_digest(meter) == terminal.get("receipt_sha256") and
             meter.get("adapter_result_sha256") == child["adapter_result_sha256"] and
             meter.get("terminal") is True and meter.get("provider_called") is False and
             meter.get("automatic_retry") is False and
             type(meter.get("sample_count")) is int and meter["sample_count"] == 1 and
             meter.get("metered_cost_usd_not_invoice") ==
             receipt["synthetic_ledger_metered_usd"],
             "budget terminal receipt is not exact zero-provider evidence")
    evidence_hashes["budget/journal.jsonl"] = _hash(budget_raw)
    evidence_hashes[f"budget/{cycle_id}.metering.json"] = _hash(meter_raw)
    evidence_hashes["supervisor/child.log"] = _hash(child_log_raw)
    evidence_hashes["supervisor/supervisor-claim.json"] = _hash(supervisor_claim_raw)
    evidence_hashes["supervisor/result.json"] = _hash(supervisor_result_raw)

    return {
        "schema": SCHEMA,
        "passed": True,
        "receipt_path": str(receipt_path),
        "receipt_sha256": expected_receipt_sha256,
        "cycle_id": cycle_id,
        "source_sha256": expected_source_sha256,
        "runtime_sha256": expected_runtime_sha256,
        "release": {"tag": expected_release_tag,
                    "commit": expected_release_commit,
                    "tag_object": expected_release_tag_object},
        "provider_calls": 0,
        "actual_provider_cost_usd": "0",
        "public_fetch_performed": False,
        "formal_data_admitted": False,
        "automatic_retry": False,
        "compiled_plan_sha256": None,
        "terminal_cleanup_verified": True,
        "evidence_sha256": dict(sorted(evidence_hashes.items())),
    }
