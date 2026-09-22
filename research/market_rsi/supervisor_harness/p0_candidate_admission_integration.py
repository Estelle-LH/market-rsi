"""Compose reviewed 2024 Train candidates without admitting them.

This is the non-test, zero-I/O-beyond-local-files consumer for the reviewed
2024 denominator ledger, outcome orientation and v2 cursor boundaries.  It
opens only exact canonical, pinned files; retains their bytes through every
validator; and emits a candidate-only integration receipt.  It deliberately
cannot validate or create a formal Train admission receipt.  Rights, provider
origin, network execution, Dev/Final access and formal admission remain false.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from types import MappingProxyType

from market_rsi import digest
from supervisor_harness import build_2024_train_candidate_ledger as ledger_builder
from supervisor_harness import formal_train_admission
from supervisor_harness import p0_2024_outcome_orientation as orientation
from supervisor_harness import p0_polymarket_v2_cursor_acquisition as cursor_v2


SCHEMA = "market_rsi_p0_candidate_admission_integration_v1"
CANONICAL_REPO = Path(
    "/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local"
)
LEDGER_RELATIVE = Path(
    "artifacts/nfl-2024-train-candidate-ledger-20260922-03/ledger.json"
)
LEDGER_RECEIPT_RELATIVE = Path(
    "artifacts/nfl-2024-train-candidate-ledger-20260922-03/receipt.json"
)
CATALOG_RELATIVE = ledger_builder.SOURCE_FILES["catalog_payload"]
MAPPING_RELATIVE = ledger_builder.SOURCE_FILES["mapped_rows"]
PINNED_FILES = MappingProxyType({
    "ledger": (LEDGER_RELATIVE,
               "1c12f53955d1b80a79896c845a563745c910a639036fa9c1ff280a0990c35819",
               2_000_000),
    "ledger_receipt": (
        LEDGER_RECEIPT_RELATIVE,
        "245d70bbfbd0e7f4432829640e8da1eca1e620ce94dcbb0971b170cba9c2e38f",
        16_384),
    "catalog": (CATALOG_RELATIVE,
                ledger_builder.PINNED_SHA256["catalog_payload"], 8_000_000),
    "mapping": (MAPPING_RELATIVE,
                ledger_builder.PINNED_SHA256["mapped_rows"], 2_000_000),
})
MISSING_GAME_ID = "2024_22_KC_PHI"
MISSING_EVENT = MappingProxyType({
    "event_id": "17330",
    "event_slug": "nfl-kc-phi-2025-02-09",
    "reason": "moneyline_missing_or_ambiguous",
})
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


@dataclass(frozen=True)
class CandidateSnapshot:
    """Exact bytes retained after canonical no-follow reads."""

    ledger: bytes
    ledger_receipt: bytes
    catalog: bytes
    mapping: bytes
    sha256: MappingProxyType


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def _exact_repo(repo: Path) -> Path:
    if not isinstance(repo, Path) or not repo.is_absolute():
        raise ValueError("candidate integration repository must be absolute")
    if (repo != CANONICAL_REPO or repo.is_symlink()
            or repo.resolve(strict=True) != CANONICAL_REPO):
        raise ValueError("exact canonical candidate repository required")
    return repo


def _no_symlink_components(repo: Path, path: Path) -> None:
    if path != repo / path.relative_to(repo):
        raise ValueError("candidate source path is not lexical-canonical")
    current = repo
    for component in path.relative_to(repo).parts:
        current = current / component
        if current.is_symlink():
            raise ValueError("candidate source path cannot use symlinks")
    if path.resolve(strict=True) != path:
        raise ValueError("candidate source path is not canonical")


def _read_pinned_file(repo: Path, path: Path, *, expected_path: Path,
                      expected_sha256: str, maximum_bytes: int) -> bytes:
    """Read one exact regular file once and retain immutable bytes.

    Device/inode/size/timestamps are checked before and after the descriptor
    read, and the directory entry is checked again before close.  Validators
    receive only the returned bytes, never the mutable pathname.
    """
    if (not isinstance(path, Path) or path != expected_path
            or expected_path != repo / expected_path.relative_to(repo)):
        raise ValueError("candidate source path substitution rejected")
    _no_symlink_components(repo, path)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    directory_flags = (os.O_RDONLY | cloexec | nofollow
                       | getattr(os, "O_DIRECTORY", 0))
    file_flags = os.O_RDONLY | cloexec | nofollow
    directories: list[tuple[int, os.stat_result, Path]] = []
    descriptor = None
    try:
        directory = os.open(repo, directory_flags)
        repository_stat = os.stat(repo, follow_symlinks=False)
        opened_repository = os.fstat(directory)
        if ((opened_repository.st_dev, opened_repository.st_ino)
                != (repository_stat.st_dev, repository_stat.st_ino)):
            raise ValueError("candidate repository path changed")
        directories.append((directory, opened_repository, repo))
        parts = path.relative_to(repo).parts
        if not parts:
            raise ValueError("candidate source file path required")
        for component in parts[:-1]:
            next_directory = os.open(component, directory_flags, dir_fd=directory)
            directory = next_directory
            directories.append((directory, os.fstat(directory),
                                directories[-1][2] / component))
        descriptor = os.open(parts[-1], file_flags, dir_fd=directory)
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        for opened_directory, _, _ in reversed(directories):
            os.close(opened_directory)
        raise ValueError("candidate source cannot be opened safely") from exc
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        for opened_directory, _, _ in reversed(directories):
            os.close(opened_directory)
        raise
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_size <= 0
                or before.st_size > maximum_bytes):
            raise ValueError("candidate source is not a bounded regular file")
        chunks: list[bytes] = []
        observed = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024,
                                            maximum_bytes + 1 - observed))
            if not chunk:
                break
            chunks.append(chunk)
            observed += len(chunk)
            if observed > maximum_bytes:
                raise ValueError("candidate source exceeds its hard byte limit")
        after = os.fstat(descriptor)
        entry_after = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
        _no_symlink_components(repo, path)
        path_after = os.stat(path, follow_symlinks=False)
        for index, (opened_directory, directory_before,
                    canonical_directory) in enumerate(directories):
            directory_after = os.fstat(opened_directory)
            canonical_after = os.stat(
                canonical_directory, follow_symlinks=False)
            if (_file_identity(directory_before)
                    != _file_identity(directory_after)
                    or (directory_after.st_dev, directory_after.st_ino)
                    != (canonical_after.st_dev, canonical_after.st_ino)):
                raise ValueError("candidate ancestor directory changed while reading")
            if index:
                parent_descriptor = directories[index - 1][0]
                entry = os.stat(
                    canonical_directory.name, dir_fd=parent_descriptor,
                    follow_symlinks=False)
                if ((directory_after.st_dev, directory_after.st_ino)
                        != (entry.st_dev, entry.st_ino)):
                    raise ValueError("candidate ancestor chain changed while reading")
        raw = b"".join(chunks)
        if (_file_identity(before) != _file_identity(after)
                or (after.st_dev, after.st_ino)
                != (entry_after.st_dev, entry_after.st_ino)
                or (after.st_dev, after.st_ino)
                != (path_after.st_dev, path_after.st_ino)
                or observed != before.st_size):
            raise ValueError("candidate source changed while being read")
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise ValueError("candidate source hash differs from reviewed bytes")
        return raw
    finally:
        os.close(descriptor)
        for opened_directory, _, _ in reversed(directories):
            os.close(opened_directory)


def _load_snapshot(repo: Path) -> CandidateSnapshot:
    repo = _exact_repo(repo)
    raw: dict[str, bytes] = {}
    hashes: dict[str, str] = {}
    for name, (relative, expected_sha, maximum) in PINNED_FILES.items():
        path = repo / relative
        value = _read_pinned_file(
            repo, path, expected_path=path, expected_sha256=expected_sha,
            maximum_bytes=maximum)
        raw[name] = value
        hashes[name] = hashlib.sha256(value).hexdigest()
    return CandidateSnapshot(
        ledger=raw["ledger"], ledger_receipt=raw["ledger_receipt"],
        catalog=raw["catalog"], mapping=raw["mapping"],
        sha256=MappingProxyType(hashes))


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate candidate JSON member: {key}")
        value[key] = item
    return value


def _strict_pretty_json(raw: bytes, label: str) -> dict:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite candidate JSON constant: {value}")

    try:
        value = json.loads(raw, object_pairs_hook=_unique_object,
                           parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not strict JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be one JSON object")
    canonical = (json.dumps(value, indent=2, sort_keys=True,
                            ensure_ascii=True, allow_nan=False) + "\n").encode()
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


def integrate_candidate(repo: Path = CANONICAL_REPO) -> dict:
    """Consume the exact local candidate snapshot and return its receipt."""
    return _compose_snapshot(_load_snapshot(repo))


def main() -> None:
    print(json.dumps(integrate_candidate(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
