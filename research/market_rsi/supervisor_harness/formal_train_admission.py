"""Validate one code-owned formal Train admission receipt, without admitting data.

The production commitment registry is deliberately empty.  Adding an exact
receipt is a reviewed protocol-source change; a caller-controlled path, issuer
name, Boolean, or SHA-256 string cannot create admission authority.  This
module performs no network access, data fetch, protected-data read, or write.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType


SCHEMA = "market_formal_train_admission_receipt_v1"
INDEPENDENT_ISSUER_ID = "market_rsi_independent_data_auditor_v1"
TRAIN_SCOPE = "train_only"
MAX_RECEIPT_BYTES = 128 * 1024
MAX_DATASET_BYTES = 100 * 1024 * 1024 * 1024
REQUIRED_GATES = ("rights", "coverage", "exposure")
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SEASON = re.compile(r"20[0-9]{2}\Z")
_TOP_FIELDS = {
    "schema", "receipt_id", "issuer_id", "issued_utc", "dataset", "gates",
    "claim_boundaries",
}
_DATASET_FIELDS = {
    "dataset_id", "dataset_sha256", "row_manifest_sha256",
    "source_version_sha256", "split_scope", "row_count", "season_ids",
    "question_id", "controller_task_sha256",
}
_GATE_FIELDS = {"status", "evidence_sha256"}
_BOUNDARY_FIELDS = {
    "formal_train_admitted", "dev_data_read", "final_data_read",
    "unknowns_remaining",
}
_COMMITMENT_FIELDS = {
    "receipt_file_sha256", "receipt_schema", "issuer_id", "dataset_id",
    "dataset_sha256", "season_ids", "question_id",
    "controller_task_sha256",
}

# No current data artifact is formally admitted.  A future entry must be an
# independently reviewed source change that pins exact receipt and dataset
# bytes.  Tests replace this immutable mapping only inside their own process.
TRUSTED_RECEIPT_COMMITMENTS = MappingProxyType({})


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError(f"{label} must be lowercase SHA256")
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"invalid {label}")
    return value


def _canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode()


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON member in admission receipt")
        value[key] = item
    return value


def _safe_open(path: Path, *, label: str) -> tuple[int, os.stat_result]:
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError(f"{label} path must be absolute")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"{label} is unavailable") from exc
    if resolved != path or path.is_symlink():
        raise ValueError(f"{label} path cannot use symlinks")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{label} cannot be opened safely") from exc
    opened = os.fstat(descriptor)
    if not stat.S_ISREG(opened.st_mode):
        os.close(descriptor)
        raise ValueError(f"{label} is not a regular file")
    observed = os.stat(path, follow_symlinks=False)
    if (opened.st_dev, opened.st_ino) != (observed.st_dev, observed.st_ino):
        os.close(descriptor)
        raise ValueError(f"{label} path changed")
    return descriptor, opened


def _read_exact_file(path: Path) -> bytes:
    descriptor, opened = _safe_open(
        path, label="formal Train admission receipt")
    try:
        if not 0 < opened.st_size <= MAX_RECEIPT_BYTES:
            raise ValueError("formal Train admission receipt is not a bounded file")
        chunks = []
        remaining = MAX_RECEIPT_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if not 0 < len(raw) <= MAX_RECEIPT_BYTES or len(raw) != opened.st_size:
            raise ValueError("formal Train admission receipt changed while reading")
        return raw
    finally:
        os.close(descriptor)


def _hash_exact_dataset(path: Path) -> tuple[str, int]:
    descriptor, before = _safe_open(path, label="formal Train dataset")
    try:
        if not 0 < before.st_size <= MAX_DATASET_BYTES:
            raise ValueError("formal Train dataset is not a bounded file")
        digest = hashlib.sha256()
        observed_bytes = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            observed_bytes += len(chunk)
            if observed_bytes > MAX_DATASET_BYTES:
                raise ValueError("formal Train dataset exceeds its hard byte limit")
            digest.update(chunk)
        after = os.fstat(descriptor)
        identity_before = (
            before.st_dev, before.st_ino, before.st_size,
            before.st_mtime_ns, before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev, after.st_ino, after.st_size,
            after.st_mtime_ns, after.st_ctime_ns,
        )
        if identity_after != identity_before or observed_bytes != before.st_size:
            raise ValueError("formal Train dataset changed while hashing")
        return digest.hexdigest(), observed_bytes
    finally:
        os.close(descriptor)


def _parse(raw: bytes) -> dict:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant is forbidden: {value}")

    try:
        receipt = json.loads(raw, object_pairs_hook=_unique_object,
                             parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("formal Train admission receipt is invalid JSON") from exc
    if not isinstance(receipt, dict) or set(receipt) != _TOP_FIELDS:
        raise ValueError("formal Train admission receipt fields differ from schema")
    if raw != _canonical(receipt):
        raise ValueError("formal Train admission receipt bytes are not canonical")
    return receipt


def _issued_utc(value: object) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("admission receipt time must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("admission receipt time is invalid") from exc
    if parsed.tzinfo != timezone.utc or parsed.isoformat().replace("+00:00", "Z") != value:
        raise ValueError("admission receipt time must be canonical UTC")
    return value


def _validate_receipt(receipt: dict, *, file_sha256: str,
                      expected_question_id: str,
                      expected_season_ids: tuple[str, ...],
                      expected_controller_task_sha256: str) -> dict:
    if receipt.get("schema") != SCHEMA:
        raise ValueError("wrong formal Train admission receipt schema")
    receipt_id = _identifier(receipt.get("receipt_id"), "admission receipt ID")
    issuer_id = _identifier(receipt.get("issuer_id"), "admission issuer ID")
    if issuer_id != INDEPENDENT_ISSUER_ID:
        raise ValueError("formal Train admission issuer is not trusted")
    _issued_utc(receipt.get("issued_utc"))

    dataset = receipt.get("dataset")
    if not isinstance(dataset, dict) or set(dataset) != _DATASET_FIELDS:
        raise ValueError("formal Train dataset binding differs from schema")
    dataset_id = _identifier(dataset.get("dataset_id"), "Train dataset ID")
    dataset_sha256 = _sha(dataset.get("dataset_sha256"), "Train dataset")
    _sha(dataset.get("row_manifest_sha256"), "Train row manifest")
    _sha(dataset.get("source_version_sha256"), "Train source version")
    if dataset.get("split_scope") != TRAIN_SCOPE:
        raise ValueError("formal Train admission is Train-only")
    if type(dataset.get("row_count")) is not int or dataset["row_count"] <= 0:
        raise ValueError("formal Train dataset row count must be positive")
    question_id = _identifier(dataset.get("question_id"), "admission question ID")
    if question_id != expected_question_id:
        raise ValueError("formal Train admission question differs from task")
    season_ids = dataset.get("season_ids")
    if (not isinstance(season_ids, list) or not season_ids
            or any(not isinstance(item, str) or not _SEASON.fullmatch(item)
                   for item in season_ids)
            or season_ids != sorted(set(season_ids))):
        raise ValueError("formal Train admission seasons are invalid")
    if tuple(season_ids) != expected_season_ids:
        raise ValueError("formal Train admission seasons differ from task")
    controller_task_sha256 = _sha(
        dataset.get("controller_task_sha256"), "Controller data task")
    if controller_task_sha256 != expected_controller_task_sha256:
        raise ValueError("formal Train admission Controller task differs from task")

    gates = receipt.get("gates")
    if not isinstance(gates, dict) or set(gates) != set(REQUIRED_GATES):
        raise ValueError("formal Train admission gates differ from schema")
    for gate_name in REQUIRED_GATES:
        gate = gates[gate_name]
        if not isinstance(gate, dict) or set(gate) != _GATE_FIELDS:
            raise ValueError(f"{gate_name} admission gate differs from schema")
        if gate.get("status") not in {"passed", "failed", "unknown"}:
            raise ValueError(f"{gate_name} admission gate status is invalid")
        _sha(gate.get("evidence_sha256"), f"{gate_name} admission evidence")
        if gate["status"] != "passed":
            raise ValueError(f"{gate_name} admission gate did not pass")

    boundaries = receipt.get("claim_boundaries")
    if not isinstance(boundaries, dict) or set(boundaries) != _BOUNDARY_FIELDS:
        raise ValueError("formal Train admission boundaries differ from schema")
    if boundaries != {
            "formal_train_admitted": True,
            "dev_data_read": False,
            "final_data_read": False,
            "unknowns_remaining": False}:
        raise ValueError("formal Train admission boundaries do not pass")

    commitment = TRUSTED_RECEIPT_COMMITMENTS.get(receipt_id)
    if not isinstance(commitment, Mapping) or set(commitment) != _COMMITMENT_FIELDS:
        raise ValueError("formal Train admission receipt is not code-owned")
    if commitment != {
            "receipt_file_sha256": file_sha256,
            "receipt_schema": SCHEMA,
            "issuer_id": issuer_id,
            "dataset_id": dataset_id,
            "dataset_sha256": dataset_sha256,
            "season_ids": season_ids,
            "question_id": question_id,
            "controller_task_sha256": controller_task_sha256}:
        raise ValueError("formal Train admission differs from code-owned commitment")
    return {
        "receipt_id": receipt_id,
        "receipt_file_sha256": file_sha256,
        "issuer_id": issuer_id,
        "dataset_id": dataset_id,
        "dataset_sha256": dataset_sha256,
        "row_manifest_sha256": dataset["row_manifest_sha256"],
        "source_version_sha256": dataset["source_version_sha256"],
        "row_count": dataset["row_count"],
        "split_scope": TRAIN_SCOPE,
        "season_ids": season_ids,
        "question_id": question_id,
        "controller_task_sha256": controller_task_sha256,
    }


def validate_formal_train_admission(
        receipt_path: Path,
        *,
        expected_receipt_sha256: str,
        dataset_path: Path,
        expected_question_id: str,
        expected_season_ids: tuple[str, ...],
        expected_controller_task_sha256: str,
) -> dict:
    """Validate exact receipt bytes against code-owned authority and dataset."""
    expected_receipt_sha256 = _sha(
        expected_receipt_sha256, "formal Train admission receipt")
    expected_question_id = _identifier(
        expected_question_id, "admission question ID")
    expected_controller_task_sha256 = _sha(
        expected_controller_task_sha256, "Controller data task")
    if (not isinstance(expected_season_ids, tuple) or not expected_season_ids
            or any(not isinstance(item, str) or not _SEASON.fullmatch(item)
                   for item in expected_season_ids)
            or list(expected_season_ids) != sorted(set(expected_season_ids))):
        raise ValueError("expected Train seasons are invalid")
    raw = _read_exact_file(receipt_path)
    file_sha256 = hashlib.sha256(raw).hexdigest()
    if file_sha256 != expected_receipt_sha256:
        raise ValueError("formal Train admission receipt hash changed")
    receipt = _parse(raw)
    validated = _validate_receipt(
        receipt, file_sha256=file_sha256,
        expected_question_id=expected_question_id,
        expected_season_ids=expected_season_ids,
        expected_controller_task_sha256=expected_controller_task_sha256)
    actual_dataset_sha256, actual_dataset_bytes = _hash_exact_dataset(dataset_path)
    if validated["dataset_sha256"] != actual_dataset_sha256:
        raise ValueError("Train dataset hash differs from exact task dataset bytes")
    return {**validated, "dataset_bytes": actual_dataset_bytes}
