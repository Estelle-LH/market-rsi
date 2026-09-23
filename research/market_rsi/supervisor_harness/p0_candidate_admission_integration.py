"""Compose the reviewed 2024 Train candidate under an explicit local receipt.

The trusted outer supervisor supplies a machine-local receipt path and the
SHA-256 of its exact bytes.  This module never discovers either value from the
environment, caller CWD, home directory, Git configuration, or a default.  It
performs local, read-only checks and emits a candidate-only result.  It cannot
publish a release, access a provider, admit Train data, or open Dev/Final.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile
import threading
from types import MappingProxyType

from market_rsi import digest
from supervisor_harness import build_2024_train_candidate_ledger as ledger_builder
from supervisor_harness import formal_train_admission
from supervisor_harness import p0_2024_outcome_orientation as orientation
from supervisor_harness import p0_polymarket_v2_cursor_acquisition as cursor_v2
from supervisor_harness import protocol_source_release


SCHEMA = "market_rsi_p0_candidate_admission_integration_v1"
TRUST_RECEIPT_SCHEMA = "market_rsi_trusted_local_root_receipt_v1"
TRUST_RECEIPT_PURPOSE = "p0_2024_train_candidate_read_only"
AUTHORIZED_ORIGIN = "https://github.com/Estelle-LH/market-rsi.git"
PROTOCOL_PREFIX = PurePosixPath("research/market_rsi")
INTEGRATION_SOURCE_RELATIVE = PurePosixPath(
    "research/market_rsi/supervisor_harness/"
    "p0_candidate_admission_integration.py"
)
LEDGER_RELATIVE = PurePosixPath(
    "artifacts/nfl-2024-train-candidate-ledger-20260922-03/ledger.json"
)
LEDGER_RECEIPT_RELATIVE = PurePosixPath(
    "artifacts/nfl-2024-train-candidate-ledger-20260922-03/receipt.json"
)
CATALOG_RELATIVE = PurePosixPath(str(ledger_builder.SOURCE_FILES["catalog_payload"]))
MAPPING_RELATIVE = PurePosixPath(str(ledger_builder.SOURCE_FILES["mapped_rows"]))
# name -> (relative path, exact SHA-256, exact size, hard maximum)
PINNED_FILES = MappingProxyType({
    "ledger": (
        LEDGER_RELATIVE,
        "1c12f53955d1b80a79896c845a563745c910a639036fa9c1ff280a0990c35819",
        348_282, 2_000_000),
    "ledger_receipt": (
        LEDGER_RECEIPT_RELATIVE,
        "245d70bbfbd0e7f4432829640e8da1eca1e620ce94dcbb0971b170cba9c2e38f",
        370, 16_384),
    "catalog": (
        CATALOG_RELATIVE,
        "c89f097b6538ceee46bb7b2950c3fd9ab6971fc5a39ddf00da61e5f589a3c0eb",
        2_491_979, 8_000_000),
    "mapping": (
        MAPPING_RELATIVE,
        "a8621f15ed703f01add64aaf4869b2ef262b4762d7bd241ba3168d040942008b",
        105_285, 2_000_000),
})
MISSING_GAME_ID = "2024_22_KC_PHI"
MISSING_EVENT = MappingProxyType({
    "event_id": "17330",
    "event_slug": "nfl-kc-phi-2025-02-09",
    "reason": "moneyline_missing_or_ambiguous",
})
CANDIDATE_CONTRACT = MappingProxyType({
    "candidate_rows": 285,
    "mapped_rows": 284,
    "mapping_resolved": False,
    "missing_rows": 1,
    "orientation_resolved": False,
    "season": 2024,
    "unresolved_event_id": "17330",
    "unresolved_event_slug": "nfl-kc-phi-2025-02-09",
    "unresolved_reason": "moneyline_missing_or_ambiguous",
    "unresolved_schedule_game_id": "2024_22_KC_PHI",
})
CLAIM_BOUNDARIES = MappingProxyType({
    "candidate_only": True,
    "dev_data_read": False,
    "final_data_read": False,
    "formal_train_admitted": False,
    "network_execution_authorized": False,
    "prediction_improvement_proven": False,
    "provider_origin_authenticated": False,
    "source_rights_verified": False,
})
_RECEIPT_MAX_BYTES = 65_536
_PATH_MAX_BYTES = 4_096
_SOURCE_MAX_BYTES = 16_000_000
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_RECEIPT_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_RELEASE_TAG = re.compile(r"market-rsi-protocol-v[a-z0-9][a-z0-9.-]*\Z")
_LEDGER_FIELDS = {
    "schema", "season", "role", "admission_claim", "provider_cost_usd",
    "denominator", "source_artifacts", "rows",
}
_RECEIPT_FIELDS = {
    "schema", "ledger_path", "ledger_sha256", "candidate_rows",
    "mapped_rows", "missing_rows", "admission_claim", "provider_cost_usd",
}
_MAPPED_ROW_FIELDS = {
    "candidate_id", "schedule_game_id", "game_date", "source_event_id",
    "source_event_slug", "source_event_start_utc", "mapping_status",
    "missing_reason", "source_binding", "row_commitment_sha256",
}
_MISSING_ROW_FIELDS = _MAPPED_ROW_FIELDS | {"unmapped_catalog_event_evidence"}
_MAPPED_BINDING_FIELDS = {
    "schedule_identity_sha256", "catalog_identity_sha256",
    "mapping_evidence_sha256", "source_artifact_sha256",
}
_MISSING_BINDING_FIELDS = {
    "schedule_identity_sha256", "catalog_identity_sha256",
    "mapping_failure_sha256", "source_artifact_sha256",
}
_MAPPED_SOURCE_ARTIFACT_FIELDS = {
    "schedule_source", "catalog_payload", "mapped_rows", "mapping_manifest",
}
_MISSING_SOURCE_ARTIFACT_FIELDS = {
    "schedule_source", "catalog_payload", "mapping_failures", "mapping_manifest",
}
_SENSITIVE_FALSE_FIELDS = {
    "admission_claim", "formal_train_admitted", "formal_data_admitted",
    "source_rights_verified", "provider_origin_authenticated",
    "network_execution_authorized", "dev_data_opened", "final_data_opened",
    "dev_data_read", "final_data_read", "prediction_improvement_proven",
}
_CRITICAL_MODULES = MappingProxyType({
    "supervisor_harness/build_2024_train_candidate_ledger.py": ledger_builder,
    "supervisor_harness/formal_train_admission.py": formal_train_admission,
    "supervisor_harness/p0_2024_outcome_orientation.py": orientation,
    "supervisor_harness/p0_polymarket_v2_cursor_acquisition.py": cursor_v2,
    "supervisor_harness/protocol_source_release.py": protocol_source_release,
})
_seen_receipt_ids: dict[str, str] = {}
_seen_receipt_ids_lock = threading.Lock()


@dataclass(frozen=True)
class CandidateSnapshot:
    """Exact bytes retained after canonical no-follow reads."""

    ledger: bytes
    ledger_receipt: bytes
    catalog: bytes
    mapping: bytes
    sha256: MappingProxyType


@dataclass(frozen=True)
class _SecureRead:
    raw: bytes
    identity: tuple[int, ...]


@dataclass(frozen=True)
class _DirectoryHandle:
    descriptor: int
    name: str | None
    before: os.stat_result


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def _nonzero_hex(value: object, pattern: re.Pattern[str], label: str) -> str:
    if (not isinstance(value, str) or pattern.fullmatch(value) is None
            or not any(character != "0" for character in value)):
        raise ValueError(f"exact nonzero lowercase {label} required")
    return value


def _absolute_path(value: object, label: str) -> Path:
    if not isinstance(value, Path):
        raise ValueError(f"{label} must be an explicit pathlib.Path")
    text = os.fspath(value)
    if (not isinstance(text, str) or "\x00" in text
            or len(text.encode("utf-8")) > _PATH_MAX_BYTES
            or not value.is_absolute() or text == "/" or text.endswith("/")
            or "//" in text):
        raise ValueError(f"canonical absolute {label} required")
    parts = value.parts
    if (not parts or parts[0] != "/"
            or any(part in {"", ".", "..", "~"} for part in parts[1:])
            or text != "/" + "/".join(parts[1:])):
        raise ValueError(f"canonical absolute {label} required")
    return value


def _absolute_path_text(value: object, label: str) -> Path:
    if (not isinstance(value, str) or "\x00" in value
            or len(value.encode("utf-8")) > _PATH_MAX_BYTES
            or not value.startswith("/") or value == "/"
            or value.endswith("/") or "//" in value
            or any(part in {"", ".", "..", "~"}
                   for part in value.split("/")[1:])):
        raise ValueError(f"{label} must be a canonical absolute path string")
    return _absolute_path(Path(value), label)


def _relative_path(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"canonical relative {label} required")
    path = PurePosixPath(value)
    if (path.is_absolute() or str(path) != value
            or any(part in {"", ".", ".."} for part in path.parts)):
        raise ValueError(f"canonical relative {label} required")
    return path


def _path_from_posix(root: Path, relative: PurePosixPath) -> Path:
    return root.joinpath(*relative.parts)


def _is_within(child: Path, parent: Path) -> bool:
    child_parts = child.parts
    parent_parts = parent.parts
    return (len(child_parts) >= len(parent_parts)
            and child_parts[:len(parent_parts)] == parent_parts)


def _require_posix_descriptor_support() -> None:
    if (os.name != "posix" or not getattr(os, "O_NOFOLLOW", 0)
            or not getattr(os, "O_DIRECTORY", 0)
            or not getattr(os, "O_CLOEXEC", 0)
            or os.open not in os.supports_dir_fd
            or os.stat not in os.supports_dir_fd
            or not hasattr(os.stat_result, "st_mtime_ns")
            or not hasattr(os.stat_result, "st_ctime_ns")):
        raise ValueError("required POSIX descriptor safety is unavailable")


def _validate_directory_stat(value: os.stat_result) -> None:
    if (not stat.S_ISDIR(value.st_mode)
            or value.st_uid not in {0, os.geteuid()}
            or value.st_mode & (stat.S_IWGRP | stat.S_IWOTH
                                | stat.S_ISUID | stat.S_ISGID)):
        raise ValueError("unsafe directory ownership or mode")


def _open_directory_chain(path: Path) -> list[_DirectoryHandle]:
    _require_posix_descriptor_support()
    path = _absolute_path(path, "directory path")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY
    handles: list[_DirectoryHandle] = []
    try:
        root_fd = os.open("/", flags)
        root_stat = os.fstat(root_fd)
        _validate_directory_stat(root_stat)
        handles.append(_DirectoryHandle(root_fd, None, root_stat))
        for component in path.parts[1:]:
            parent_fd = handles[-1].descriptor
            entry = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
            descriptor = os.open(component, flags, dir_fd=parent_fd)
            opened = os.fstat(descriptor)
            if _file_identity(entry) != _file_identity(opened):
                os.close(descriptor)
                raise ValueError("directory entry changed while opening")
            _validate_directory_stat(opened)
            handles.append(_DirectoryHandle(descriptor, component, opened))
        return handles
    except OSError as exc:
        for handle in reversed(handles):
            os.close(handle.descriptor)
        raise ValueError("path cannot be opened without following links") from exc
    except Exception:
        for handle in reversed(handles):
            os.close(handle.descriptor)
        raise


def _recheck_directory_chain(handles: list[_DirectoryHandle]) -> None:
    for index, handle in enumerate(handles):
        after = os.fstat(handle.descriptor)
        if _file_identity(after) != _file_identity(handle.before):
            raise ValueError("ancestor directory changed while reading")
        if index == 0:
            entry = os.stat("/", follow_symlinks=False)
        else:
            entry = os.stat(
                handle.name, dir_fd=handles[index - 1].descriptor,
                follow_symlinks=False)
        if _file_identity(entry) != _file_identity(handle.before):
            raise ValueError("ancestor directory chain changed while reading")


def _secure_directory_identity(path: Path) -> tuple[int, ...]:
    handles = _open_directory_chain(path)
    try:
        _recheck_directory_chain(handles)
        return _file_identity(handles[-1].before)
    finally:
        for handle in reversed(handles):
            os.close(handle.descriptor)


def _secure_read_file(
    path: Path,
    *,
    maximum_bytes: int,
    exact_size: int | None = None,
    expected_sha256: str | None = None,
    receipt_leaf: bool = False,
) -> _SecureRead:
    """Read one file once through a retained descriptor chain."""
    path = _absolute_path(path, "file path")
    if (isinstance(maximum_bytes, bool) or not isinstance(maximum_bytes, int)
            or maximum_bytes <= 0):
        raise ValueError("positive hard byte limit required")
    handles = _open_directory_chain(path.parent)
    descriptor: int | None = None
    try:
        leaf = path.name
        entry_before = os.stat(
            leaf, dir_fd=handles[-1].descriptor, follow_symlinks=False)
        descriptor = os.open(
            leaf, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=handles[-1].descriptor)
        before = os.fstat(descriptor)
        if _file_identity(entry_before) != _file_identity(before):
            raise ValueError("file entry changed while opening")
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size <= 0 or before.st_size > maximum_bytes):
            raise ValueError("bounded single-link regular file required")
        if receipt_leaf:
            if (before.st_uid != os.geteuid()
                    or stat.S_IMODE(before.st_mode) != 0o600):
                raise ValueError(
                    "receipt must be owned by the effective user at mode 0600")
        elif (before.st_uid not in {0, os.geteuid()}
              or before.st_mode & (stat.S_IWGRP | stat.S_IWOTH
                                   | stat.S_ISUID | stat.S_ISGID)):
            raise ValueError("unsafe file ownership or mode")
        if exact_size is not None and before.st_size != exact_size:
            raise ValueError("file size differs from its reviewed binding")
        chunks: list[bytes] = []
        observed = 0
        while True:
            chunk = os.read(
                descriptor, min(1024 * 1024, maximum_bytes + 1 - observed))
            if not chunk:
                break
            chunks.append(chunk)
            observed += len(chunk)
            if observed > maximum_bytes:
                raise ValueError("file exceeds its hard byte limit")
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        entry_after = os.stat(
            leaf, dir_fd=handles[-1].descriptor, follow_symlinks=False)
        _recheck_directory_chain(handles)
        if (_file_identity(before) != _file_identity(after)
                or _file_identity(before) != _file_identity(entry_after)
                or observed != before.st_size):
            raise ValueError("file changed while being read")
        if (expected_sha256 is not None
                and hashlib.sha256(raw).hexdigest() != expected_sha256):
            raise ValueError("file hash differs from its reviewed binding")
        return _SecureRead(raw=raw, identity=_file_identity(before))
    except OSError as exc:
        raise ValueError("file cannot be opened without following links") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        for handle in reversed(handles):
            os.close(handle.descriptor)


def _load_snapshot(artifact_root: Path) -> CandidateSnapshot:
    raw: dict[str, bytes] = {}
    hashes: dict[str, str] = {}
    for name, (relative, expected_sha, exact_size, maximum) in PINNED_FILES.items():
        read = _secure_read_file(
            _path_from_posix(artifact_root, relative),
            maximum_bytes=maximum, exact_size=exact_size,
            expected_sha256=expected_sha)
        raw[name] = read.raw
        hashes[name] = hashlib.sha256(read.raw).hexdigest()
    return CandidateSnapshot(
        ledger=raw["ledger"], ledger_receipt=raw["ledger_receipt"],
        catalog=raw["catalog"], mapping=raw["mapping"],
        sha256=MappingProxyType(hashes))


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON member: {key}")
        value[key] = item
    return value


def _reject_json_number(value: str) -> None:
    raise ValueError(f"forbidden non-integer JSON number: {value}")


def _strict_pretty_json(raw: bytes, label: str) -> dict:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{label} must not contain a BOM")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object,
            parse_float=_reject_json_number,
            parse_constant=_reject_json_number)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not strict JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be one JSON object")
    try:
        canonical = (json.dumps(
            value, indent=2, sort_keys=True, ensure_ascii=True,
            allow_nan=False) + "\n").encode("ascii")
    except (UnicodeEncodeError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} is not canonical ASCII JSON") from exc
    if raw != canonical:
        raise ValueError(f"{label} bytes are not canonical reviewed serialization")
    return value


def _assert_sensitive_false(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = key.lower()
            tokens = set(lowered.replace("-", "_").split("_"))
            authority_key = (
                lowered in _SENSITIVE_FALSE_FIELDS
                or "rights" in lowered
                or "admission" in lowered
                or "admitted" in lowered
                or "authorized" in lowered
                or "authorizes" in lowered
                or "authorization" in lowered
                or ("provider" in tokens and bool(tokens & {
                    "verified", "authenticated", "trusted", "authorized",
                    "access", "allowed"}))
                or ("network" in tokens and bool(tokens & {
                    "access", "allowed", "enabled", "verified"}))
                or ("formal" in tokens and bool(tokens & {
                    "training", "train", "data", "allowed", "verified"}))
                or ("improvement" in tokens and bool(tokens & {
                    "claim", "allowed", "proven", "verified"}))
                or any(part in lowered for part in ("dev_", "final_"))
            )
            if authority_key and not isinstance(item, (dict, list)):
                if item is not False:
                    raise ValueError(f"candidate authority escalation rejected: {key}")
            _assert_sensitive_false(item)
    elif isinstance(value, list):
        for item in value:
            _assert_sensitive_false(item)


def _exact_keys(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} fields differ from the reviewed schema")
    return value


def _validate_trust_receipt(raw: bytes) -> dict:
    value = _strict_pretty_json(raw, "trusted local-root receipt")
    _exact_keys(value, {"schema", "config", "config_sha256"}, "receipt")
    if value["schema"] != TRUST_RECEIPT_SCHEMA:
        raise ValueError("wrong trusted local-root receipt schema")
    config = _exact_keys(
        value["config"],
        {"receipt_id", "purpose", "repository", "artifact_store",
         "candidate_contract", "claim_boundaries"},
        "receipt config")
    config_sha = _nonzero_hex(value["config_sha256"], _HEX64, "config SHA-256")
    if digest(config) != config_sha:
        raise ValueError("trusted local-root config digest mismatch")
    if (not isinstance(config["receipt_id"], str)
            or _RECEIPT_ID.fullmatch(config["receipt_id"]) is None):
        raise ValueError("canonical receipt ID required")
    if config["purpose"] != TRUST_RECEIPT_PURPOSE:
        raise ValueError("wrong trusted local-root receipt purpose")

    repository = _exact_keys(
        config["repository"],
        {"code_root", "origin", "integration_source_relative", "release_tag",
         "release_commit", "release_tag_object", "controlled_source_sha256",
         "controlled_source_file_count", "publication_receipt_sha256"},
        "repository binding")
    _absolute_path_text(repository["code_root"], "code root")
    if repository["origin"] != AUTHORIZED_ORIGIN:
        raise ValueError("receipt origin is not the standalone repository")
    if repository["integration_source_relative"] != str(INTEGRATION_SOURCE_RELATIVE):
        raise ValueError("wrong integration source binding")
    if (not isinstance(repository["release_tag"], str)
            or len(repository["release_tag"]) > 96
            or _RELEASE_TAG.fullmatch(repository["release_tag"]) is None):
        raise ValueError("canonical protocol release tag required")
    _nonzero_hex(repository["release_commit"], _HEX40, "release commit")
    _nonzero_hex(repository["release_tag_object"], _HEX40, "tag object")
    _nonzero_hex(repository["controlled_source_sha256"], _HEX64,
                 "controlled-source SHA-256")
    count = repository["controlled_source_file_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("positive controlled-source file count required")
    _nonzero_hex(repository["publication_receipt_sha256"], _HEX64,
                 "publication-receipt SHA-256")

    artifact_store = _exact_keys(
        config["artifact_store"], {"artifact_root", "role", "artifacts"},
        "artifact-store binding")
    _absolute_path_text(artifact_store["artifact_root"], "artifact root")
    if artifact_store["role"] != "read_only_pinned_candidate_bytes_only":
        raise ValueError("wrong artifact-store role")
    artifacts = _exact_keys(
        artifact_store["artifacts"], set(PINNED_FILES), "artifact bindings")
    for name, (relative, expected_sha, exact_size, _) in PINNED_FILES.items():
        binding = _exact_keys(
            artifacts[name], {"relative_path", "size_bytes", "sha256"},
            f"{name} artifact binding")
        if (_relative_path(binding["relative_path"], f"{name} artifact") != relative
                or binding["sha256"] != expected_sha
                or isinstance(binding["size_bytes"], bool)
                or binding["size_bytes"] != exact_size):
            raise ValueError(f"{name} artifact differs from its code-owned binding")
    if config["candidate_contract"] != dict(CANDIDATE_CONTRACT):
        raise ValueError("candidate contract differs from code-owned semantics")
    if config["claim_boundaries"] != dict(CLAIM_BOUNDARIES):
        raise ValueError("claim boundaries differ from code-owned false authority")
    _assert_sensitive_false(value)
    return value


def _validate_separation(receipt_path: Path, code_root: Path,
                         artifact_root: Path) -> None:
    if (_is_within(receipt_path, code_root) or _is_within(receipt_path, artifact_root)
            or _is_within(code_root, artifact_root)
            or _is_within(artifact_root, code_root)):
        raise ValueError("receipt, code root and artifact root must remain separate")
    code_identity = _secure_directory_identity(code_root)
    artifact_identity = _secure_directory_identity(artifact_root)
    if code_identity[:2] == artifact_identity[:2]:
        raise ValueError("code root and artifact root cannot alias")


def _git(code_root: Path, *args: str) -> bytes:
    # A fixed minimal environment prevents GIT_DIR/GIT_WORK_TREE/config
    # overrides and keeps Git independent of the caller's environment/CWD.
    # Replacement objects may alter the bytes addressed by a reviewed commit,
    # optional locks are unnecessary for these read-only checks, and a
    # repository-local fsmonitor command must never execute at this boundary.
    environment = {
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "LC_ALL": "C",
    }
    try:
        completed = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-C", str(code_root), *args],
            cwd="/", env=environment,
            capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("local Git identity check failed") from exc
    if completed.returncode:
        raise ValueError("local Git identity check failed")
    return completed.stdout


def _controlled_relative_files() -> tuple[PurePosixPath, ...]:
    values: list[PurePosixPath] = []
    for name in protocol_source_release.FILES:
        values.append(PROTOCOL_PREFIX / _relative_path(name, "controlled source"))
    if len(set(values)) != len(values):
        raise ValueError("duplicate controlled source path")
    return tuple(sorted(values, key=str))


def _validate_loaded_source_paths(
    code_root: Path, controlled: set[PurePosixPath]
) -> None:
    modules = dict(_CRITICAL_MODULES)
    modules["supervisor_harness/p0_candidate_admission_integration.py"] = __file__
    for relative_text, module in modules.items():
        relative = PROTOCOL_PREFIX / PurePosixPath(relative_text)
        if relative not in controlled:
            raise ValueError("critical loaded source is outside the controlled manifest")
        expected = _path_from_posix(code_root, relative)
        loaded_value = module if isinstance(module, str) else getattr(module, "__file__", None)
        if not isinstance(loaded_value, str):
            raise ValueError("critical module lacks an exact source path")
        loaded = _absolute_path_text(loaded_value, "loaded source")
        if loaded != expected:
            raise ValueError("critical module is loaded from another checkout")


def _controlled_source_hashes(
    code_root: Path, controlled: tuple[PurePosixPath, ...]
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in controlled:
        read = _secure_read_file(
            _path_from_posix(code_root, relative), maximum_bytes=_SOURCE_MAX_BYTES)
        hashes[str(relative.relative_to(PROTOCOL_PREFIX))] = hashlib.sha256(
            read.raw).hexdigest()
    return hashes


def _tagged_source_hashes(
    code_root: Path, release_commit: str,
    controlled: tuple[PurePosixPath, ...],
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    names = [str(path) for path in controlled]
    for start in range(0, len(names), 16):
        archive = _git(
            code_root, "archive", "--format=tar", release_commit, "--",
            *names[start:start + 16])
        try:
            with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
                for member in stream:
                    if not member.isfile():
                        continue
                    path = _relative_path(member.name, "tagged source")
                    if path not in controlled or member.name in hashes:
                        raise ValueError("unexpected or duplicate tagged source")
                    extracted = stream.extractfile(member)
                    if extracted is None:
                        raise ValueError("tagged source cannot be read")
                    hashes[member.name] = hashlib.sha256(extracted.read()).hexdigest()
        except tarfile.TarError as exc:
            raise ValueError("tagged source archive is invalid") from exc
    return {
        str(path.relative_to(PROTOCOL_PREFIX)): hashes[str(path)]
        for path in controlled
    }


def _verify_repository(code_root: Path, repository: dict) -> dict[str, str]:
    top = _git(code_root, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    if top != str(code_root):
        raise ValueError("receipt code root is not the exact Git worktree root")
    # `remote get-url` applies url.*.insteadOf rewrites.  Read the local
    # repository key itself, with includes disabled, so the receipt binds the
    # exact configured origin rather than a rewritten presentation of it.
    origins = _git(
        code_root, "config", "--local", "--no-includes", "--get-all",
        "remote.origin.url").decode("utf-8").splitlines()
    if (len(origins) != 1 or origins[0] != AUTHORIZED_ORIGIN
            or origins[0] != repository["origin"]):
        raise ValueError("origin is not the authorized standalone repository")
    tag = repository["release_tag"]
    ref = "refs/tags/" + tag
    if _git(code_root, "cat-file", "-t", ref).decode("utf-8").strip() != "tag":
        raise ValueError("annotated protocol release tag required")
    tag_object = _git(code_root, "rev-parse", ref).decode("utf-8").strip()
    release_commit = _git(
        code_root, "rev-parse", ref + "^{commit}").decode("utf-8").strip()
    if (tag_object != repository["release_tag_object"]
            or release_commit != repository["release_commit"]):
        raise ValueError("release tag object or commit differs from receipt")

    controlled = _controlled_relative_files()
    _validate_loaded_source_paths(code_root, set(controlled))
    paths = [str(path) for path in controlled]
    if _git(
            code_root, "status", "--porcelain", "--untracked-files=all",
            "--", *paths).strip():
        raise ValueError("controlled protocol source is not clean")
    hashes = _controlled_source_hashes(code_root, controlled)
    controlled_sha = digest(hashes)
    if (len(hashes) != repository["controlled_source_file_count"]
            or controlled_sha != repository["controlled_source_sha256"]):
        raise ValueError("controlled source count or digest differs from receipt")
    if _tagged_source_hashes(code_root, release_commit, controlled) != hashes:
        raise ValueError("annotated release differs from current controlled source")
    publication = {
        "schema": "market_rsi_protocol_publication_v1",
        "origin": AUTHORIZED_ORIGIN,
        "tag": tag,
        "commit": release_commit,
        "tag_object": tag_object,
        "source_sha256": controlled_sha,
        "source_hashes": hashes,
        "isolation_proven": False,
        "model_authorship_proven": False,
    }
    if digest(publication) != repository["publication_receipt_sha256"]:
        raise ValueError("publication receipt digest differs from local release")
    return hashes


def _reject_protected_fields(value: object) -> None:
    """Ledger inputs may not contain Dev/Final fields, even when false."""
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = key.lower()
            if "dev" in lowered or "final" in lowered:
                raise ValueError(f"Dev/Final candidate field rejected: {key}")
            _reject_protected_fields(item)
    elif isinstance(value, list):
        for item in value:
            _reject_protected_fields(item)


def _validate_ledger(snapshot: CandidateSnapshot) -> tuple[dict, dict]:
    ledger = _strict_pretty_json(snapshot.ledger, "candidate ledger")
    receipt = _strict_pretty_json(
        snapshot.ledger_receipt, "candidate ledger receipt")
    if set(ledger) != _LEDGER_FIELDS:
        raise ValueError("candidate ledger fields differ from reviewed schema")
    if set(receipt) != _RECEIPT_FIELDS:
        raise ValueError("candidate ledger receipt fields differ from schema")
    _reject_protected_fields(ledger)
    _reject_protected_fields(receipt)
    expected_source_artifacts = {
        name: {
            "path": str(ledger_builder.SOURCE_FILES[name]),
            "sha256": ledger_builder.PINNED_SHA256[name],
        }
        for name in sorted(ledger_builder.SOURCE_FILES)
    }
    if (ledger.get("schema") != ledger_builder.SCHEMA
            or ledger.get("season") != 2024
            or ledger.get("role") != "train_candidate_only"
            or ledger.get("admission_claim") is not False
            or ledger.get("provider_cost_usd") != "0"
            or ledger.get("denominator") != {
                "candidate_rows": 285, "mapped_rows": 284, "missing_rows": 1}
            or ledger.get("source_artifacts") != expected_source_artifacts):
        raise ValueError("candidate ledger identity or boundaries changed")
    if receipt != {
        "schema": "market_rsi_2024_train_candidate_denominator_receipt_v1",
        "ledger_path": str(LEDGER_RELATIVE),
        "ledger_sha256": snapshot.sha256["ledger"],
        "candidate_rows": 285,
        "mapped_rows": 284,
        "missing_rows": 1,
        "admission_claim": False,
        "provider_cost_usd": "0",
    }:
        raise ValueError("candidate ledger receipt does not bind exact ledger")
    rows = ledger.get("rows")
    if not isinstance(rows, list) or len(rows) != 285:
        raise ValueError("candidate ledger denominator changed")
    _assert_sensitive_false(ledger)
    _assert_sensitive_false(receipt)
    identifiers: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("candidate ledger row must be an object")
        status = row.get("mapping_status")
        expected_row_fields = (_MAPPED_ROW_FIELDS if status == "mapped"
                               else _MISSING_ROW_FIELDS if status == "missing"
                               else None)
        expected_binding_fields = (
            _MAPPED_BINDING_FIELDS if status == "mapped"
            else _MISSING_BINDING_FIELDS if status == "missing" else None)
        if expected_row_fields is None or set(row) != expected_row_fields:
            raise ValueError("candidate ledger row fields differ from schema")
        binding = row.get("source_binding")
        if (not isinstance(binding, dict)
                or set(binding) != expected_binding_fields):
            raise ValueError("candidate source binding fields differ from schema")
        expected_artifact_fields = (
            _MAPPED_SOURCE_ARTIFACT_FIELDS if status == "mapped"
            else _MISSING_SOURCE_ARTIFACT_FIELDS)
        if (not isinstance(binding.get("source_artifact_sha256"), dict)
                or set(binding["source_artifact_sha256"])
                != expected_artifact_fields):
            raise ValueError("candidate row source artifacts differ from schema")
        commitment = row.get("row_commitment_sha256")
        committed = dict(row)
        committed.pop("row_commitment_sha256", None)
        if commitment != ledger_builder.canonical_digest(committed):
            raise ValueError("candidate row commitment changed")
        candidate_id = row.get("candidate_id")
        if not isinstance(candidate_id, str) or candidate_id in identifiers:
            raise ValueError("candidate ledger identity is missing or duplicated")
        identifiers.add(candidate_id)
    return ledger, receipt


def _cross_check(ledger: dict, orientations: dict) -> tuple[list[dict], dict]:
    mapped = [row for row in ledger["rows"] if row.get("mapping_status") == "mapped"]
    missing = [row for row in ledger["rows"] if row.get("mapping_status") == "missing"]
    receipts = orientations.get("candidate_orientation_receipts")
    if (len(mapped) != 284 or len(missing) != 1
            or not isinstance(receipts, list) or len(receipts) != 284):
        raise ValueError("ledger/orientation denominator mismatch")
    by_game = {item.get("nflverse_game_id"): item for item in receipts}
    if len(by_game) != 284:
        raise ValueError("orientation game identity is duplicated")
    streams = []
    for row in mapped:
        item = by_game.get(row.get("schedule_game_id"))
        if (item is None
                or item.get("polymarket_event_id") != row.get("source_event_id")
                or item.get("event_slug") != row.get("source_event_slug")
                or item.get("catalog_sha256")
                != row["source_binding"]["source_artifact_sha256"]["catalog_payload"]
                or item.get("mapping_sha256")
                != row["source_binding"]["source_artifact_sha256"]["mapped_rows"]):
            raise ValueError("ledger/orientation identity mismatch")
        streams.append({
            "stream_id": "game_" + row["schedule_game_id"],
            "condition_id": item["condition_id"],
            "asset_ids": [item["away_token_id"], item["home_token_id"]],
        })
    unresolved = missing[0]
    expected_evidence = {
        "source_event_id": MISSING_EVENT["event_id"],
        "source_event_slug": MISSING_EVENT["event_slug"],
        "claimed_as_mapping": False,
    }
    if (unresolved.get("schedule_game_id") != MISSING_GAME_ID
            or unresolved.get("candidate_id") != f"game:{MISSING_GAME_ID}"
            or unresolved.get("source_event_id") is not None
            or unresolved.get("source_event_slug") is not None
            or unresolved.get("missing_reason") != MISSING_EVENT["reason"]
            or unresolved.get("unmapped_catalog_event_evidence") != expected_evidence
            or orientations.get("unoriented_source_events") != [{
                "event_id": MISSING_EVENT["event_id"],
                "event_slug": MISSING_EVENT["event_slug"],
                "reason": "absent_from_candidate_mapping",
            }]
            or orientations.get("missing_orientation_inferred") is not False):
        raise ValueError("event 17330 must remain explicitly unresolved")
    return streams, unresolved


def _compose_snapshot(snapshot: CandidateSnapshot) -> dict:
    """Validate a retained exact snapshot and produce no admission authority."""
    if dict(formal_train_admission.TRUSTED_RECEIPT_COMMITMENTS):
        raise ValueError("candidate integration cannot consume formal admission authority")
    ledger, _ = _validate_ledger(snapshot)
    orientations = orientation.verify_preserved_2024_orientation(
        snapshot.catalog, snapshot.mapping)
    _assert_sensitive_false(orientations)
    streams, unresolved = _cross_check(ledger, orientations)
    caps = {
        "max_requests": cursor_v2.HARD_MAX_REQUESTS,
        "max_pages": cursor_v2.HARD_MAX_PAGES,
        "max_pages_per_stream": cursor_v2.HARD_MAX_PAGES_PER_STREAM,
        "max_page_response_bytes": cursor_v2.HARD_MAX_PAGE_RESPONSE_BYTES,
        "max_total_response_bytes": cursor_v2.HARD_MAX_TOTAL_RESPONSE_BYTES,
        "max_elapsed_seconds": cursor_v2.HARD_MAX_ELAPSED_SECONDS,
    }
    cursor_manifest = cursor_v2.build_manifest(streams, caps)
    cursor_manifest = cursor_v2.validate_manifest(cursor_manifest)
    cursor_contract = cursor_v2.build_receipt_contract(cursor_manifest)
    _assert_sensitive_false(cursor_manifest)
    _assert_sensitive_false(cursor_contract)
    result = {
        "schema": SCHEMA,
        "status": "candidate_only",
        "source_snapshot_sha256": dict(snapshot.sha256),
        "ledger_sha256": snapshot.sha256["ledger"],
        "ledger_receipt_sha256": snapshot.sha256["ledger_receipt"],
        "orientation_receipt_set_sha256": digest(orientations),
        "cursor_manifest_sha256": digest(cursor_manifest),
        "cursor_receipt_contract_sha256": digest(cursor_contract),
        "denominator": {
            "candidate_rows": 285,
            "mapped_oriented_rows": 284,
            "explicitly_unresolved_rows": 1,
            "cursor_candidate_streams": 284,
        },
        "unresolved_event": {
            "schedule_game_id": unresolved["schedule_game_id"],
            **dict(MISSING_EVENT),
            "mapping_resolved": False,
            "orientation_resolved": False,
        },
        "formal_train_receipt_boundary": {
            "schema": formal_train_admission.SCHEMA,
            "trusted_receipt_commitments": 0,
            "formal_receipt_validated": False,
            "formal_train_admitted": False,
            "blocker": "no_code_owned_formal_train_receipt",
        },
        "claim_boundaries": {
            "candidate_only": True,
            "source_rights_verified": False,
            "provider_origin_authenticated": False,
            "network_execution_authorized": False,
            "v2_execution_receipt_validated": False,
            "formal_train_admitted": False,
            "dev_data_read": False,
            "final_data_read": False,
            "prediction_improvement_proven": False,
        },
    }
    _assert_sensitive_false(result)
    return result


def _register_receipt_id(receipt_id: str, receipt_sha256: str) -> None:
    with _seen_receipt_ids_lock:
        previous = _seen_receipt_ids.get(receipt_id)
        if previous is not None and previous != receipt_sha256:
            raise ValueError("receipt ID was reused with different bytes")
        _seen_receipt_ids[receipt_id] = receipt_sha256


def integrate_candidate(
    *,
    trust_receipt_path: Path,
    expected_trust_receipt_sha256: str,
) -> dict:
    """Consume reviewed local bytes under one explicit trusted receipt."""
    receipt_path = _absolute_path(trust_receipt_path, "trust receipt path")
    expected_receipt_sha = _nonzero_hex(
        expected_trust_receipt_sha256, _HEX64, "trust-receipt SHA-256")
    receipt_read = _secure_read_file(
        receipt_path, maximum_bytes=_RECEIPT_MAX_BYTES, receipt_leaf=True)
    observed_receipt_sha = hashlib.sha256(receipt_read.raw).hexdigest()
    if observed_receipt_sha != expected_receipt_sha:
        raise ValueError("trusted receipt bytes differ from caller-supplied digest")
    receipt = _validate_trust_receipt(receipt_read.raw)
    config = receipt["config"]
    repository = config["repository"]
    artifact_store = config["artifact_store"]
    code_root = _absolute_path_text(repository["code_root"], "code root")
    artifact_root = _absolute_path_text(
        artifact_store["artifact_root"], "artifact root")
    _validate_separation(receipt_path, code_root, artifact_root)
    _verify_repository(code_root, repository)
    snapshot = _load_snapshot(artifact_root)
    result = _compose_snapshot(snapshot)
    result.update({
        "trusted_local_root_receipt_sha256": observed_receipt_sha,
        "trusted_local_root_config_sha256": receipt["config_sha256"],
        "trusted_local_root_receipt_id": config["receipt_id"],
        "repository_binding": {
            "origin": repository["origin"],
            "release_tag": repository["release_tag"],
            "release_commit": repository["release_commit"],
            "release_tag_object": repository["release_tag_object"],
            "controlled_source_sha256": repository["controlled_source_sha256"],
            "controlled_source_file_count": repository["controlled_source_file_count"],
            "publication_receipt_sha256": repository["publication_receipt_sha256"],
        },
        "artifact_bindings": {
            name: {
                "relative_path": binding["relative_path"],
                "size_bytes": binding["size_bytes"],
                "sha256": binding["sha256"],
            }
            for name, binding in sorted(artifact_store["artifacts"].items())
        },
    })
    _assert_sensitive_false(result)
    _register_receipt_id(config["receipt_id"], observed_receipt_sha)
    return result


def _cli_path(value: str) -> Path:
    if (not isinstance(value, str) or "\x00" in value or value.startswith("~")
            or not value.startswith("/") or value.endswith("/") or "//" in value
            or any(part in {".", "..", "~"} for part in value.split("/"))):
        raise argparse.ArgumentTypeError("canonical absolute receipt path required")
    try:
        return _absolute_path(Path(value), "trust receipt path")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trust-receipt", required=True, type=_cli_path)
    parser.add_argument("--expected-trust-receipt-sha256", required=True)
    arguments = parser.parse_args(argv)
    value = integrate_candidate(
        trust_receipt_path=arguments.trust_receipt,
        expected_trust_receipt_sha256=arguments.expected_trust_receipt_sha256)
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
