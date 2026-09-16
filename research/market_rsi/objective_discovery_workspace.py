"""Isolated opened-Train workspace for autonomous objective discovery.

The workspace intentionally has no Dev artifact.  A runner-owned diagnostic
and objective audit are frozen before the controller starts.  The controller
can inspect those artifacts, search a bounded literature snapshot, propose
objective definitions and freeze one executable choice.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from literature_catalog import literature_snapshot as default_literature_snapshot
from market_rsi import canonical, digest, file_hash, fresh_json, identifier
from objective_contract import objective_catalog
from objective_discovery_harness import discovery_harness_contract
from objective_train_audit import audit as audit_objectives
from time_series_data_diagnostics import diagnose


SCHEMA = "market_objective_discovery_workspace_v1"
LITERATURE_SCHEMA = "market_public_literature_snapshot_v1"
MAX_LITERATURE_RESULTS = 8


def _json(path: Path, maximum: int = 1_073_741_824):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("missing, symlinked or oversized objective-discovery input")
    return json.loads(path.read_bytes())


def _write(path: Path, value: dict) -> None:
    fresh_json(path, value)
    os.chmod(path, 0o600)


def _file_receipt(path: Path) -> dict:
    raw = path.read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _inventory(source: dict, source_path: Path, dates: list[str]) -> dict:
    return {
        "schema": "market_open_train_source_inventory_v1",
        "source_schema": source.get("schema"),
        "source_path": str(source_path),
        "source_sha256": file_hash(source_path),
        "opened_train_utc_dates": dates,
        "row_count_all_dates": len(source.get("rows", [])),
        "streams": {
            "quote_book": {"present": True, "verified": True},
            "trade": {
                "present": isinstance(source.get("trade_stream_provenance"), dict),
                "verified": source.get("trade_stream_provenance", {}).get("verified") is True,
            },
            "resolution": {
                "present": isinstance(source.get("resolution_stream_provenance"), dict),
                "verified": source.get("resolution_stream_provenance", {}).get("verified") is True,
            },
        },
        "dev_artifact_present": False,
        "future_test_artifact_present": False,
    }


def prepare_workspace(
    output: Path,
    *,
    session_id: str,
    experiment_id: str,
    source_path: Path,
    opened_train_utc_dates: list[str],
    evidence_class: str = "diagnostic",
    literature_snapshot: dict | None = None,
) -> dict:
    """Freeze one objective-discovery workspace without creating a Dev split."""
    identifier(session_id)
    identifier(experiment_id)
    if evidence_class not in {"diagnostic", "formal_learning"}:
        raise ValueError("objective discovery evidence class is invalid")
    if (not isinstance(opened_train_utc_dates, list)
            or not opened_train_utc_dates
            or opened_train_utc_dates != sorted(set(opened_train_utc_dates))):
        raise ValueError("unique chronological opened Train dates required")
    source_path = Path(source_path).resolve()
    source = _json(source_path)
    diagnostics = diagnose(source, opened_train_utc_dates=opened_train_utc_dates)
    try:
        objective_audit = audit_objectives(
            source, train_utc_dates=opened_train_utc_dates
        )
        audit_state = {"status": "completed", "result": objective_audit}
    except ValueError as error:
        audit_state = {
            "status": "not_executable_on_current_materialization",
            "error_type": type(error).__name__,
            "message": str(error),
        }
    literature = default_literature_snapshot() if literature_snapshot is None \
        else literature_snapshot
    if (not isinstance(literature, dict)
            or literature.get("schema") != LITERATURE_SCHEMA
            or not isinstance(literature.get("papers"), list)):
        raise ValueError("frozen public literature snapshot required")

    output = Path(output).resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    (output / "objective-proposals").mkdir(mode=0o700)
    (output / "objective-audits").mkdir(mode=0o700)
    binding = {
        "schema": "market_open_train_source_binding_v1",
        "source_path": str(source_path),
        "source_sha256": file_hash(source_path),
        "opened_train_utc_dates": opened_train_utc_dates,
        "evidence_class": evidence_class,
    }
    visible = {
        "source-binding.json": binding,
        "source-inventory.json": _inventory(source, source_path, opened_train_utc_dates),
        "automatic-diagnostics.json": diagnostics,
        "automatic-objective-audit.json": audit_state,
        "objective-catalog.json": objective_catalog(),
        "literature-snapshot.json": literature,
        "discovery-harness.json": discovery_harness_contract(),
    }
    for name, value in visible.items():
        _write(output / name, value)
    manifest = {
        "schema": SCHEMA,
        "session_id": session_id,
        "experiment_id": experiment_id,
        "evidence_class": evidence_class,
        "files": {name: _file_receipt(output / name) for name in visible},
        "source_sha256": binding["source_sha256"],
        "opened_train_utc_dates": opened_train_utc_dates,
        "dev_artifact_present": False,
        "future_test_artifact_present": False,
        "selection_state": "unfrozen",
    }
    _write(output / "objective-discovery-workspace.json", manifest)
    validate_workspace(output)
    return manifest


def validate_workspace(workspace: Path) -> dict:
    workspace = Path(workspace).resolve()
    manifest = _json(workspace / "objective-discovery-workspace.json", 2_000_000)
    if (not isinstance(manifest, dict) or set(manifest) != {
            "schema", "session_id", "experiment_id", "evidence_class", "files",
            "source_sha256", "opened_train_utc_dates", "dev_artifact_present",
            "future_test_artifact_present", "selection_state"
            } or manifest["schema"] != SCHEMA
            or manifest["evidence_class"] not in {"diagnostic", "formal_learning"}
            or manifest["dev_artifact_present"] is not False
            or manifest["future_test_artifact_present"] is not False
            or manifest["selection_state"] != "unfrozen"):
        raise ValueError("objective-discovery workspace manifest changed")
    identifier(manifest["session_id"])
    identifier(manifest["experiment_id"])
    expected_files = {
        "source-binding.json", "source-inventory.json", "automatic-diagnostics.json",
        "automatic-objective-audit.json", "objective-catalog.json",
        "literature-snapshot.json", "discovery-harness.json",
    }
    if set(manifest["files"]) != expected_files:
        raise ValueError("objective-discovery visible files changed")
    for name, receipt in manifest["files"].items():
        path = workspace / name
        if path.is_symlink() or not path.is_file() or _file_receipt(path) != receipt:
            raise ValueError("objective-discovery input changed")
    binding = _json(workspace / "source-binding.json", 2_000_000)
    source_path = Path(binding.get("source_path", ""))
    if (binding.get("source_sha256") != manifest["source_sha256"]
            or binding.get("opened_train_utc_dates") != manifest["opened_train_utc_dates"]
            or binding.get("evidence_class") != manifest["evidence_class"]
            or source_path.is_symlink() or not source_path.is_file()
            or file_hash(source_path) != manifest["source_sha256"]):
        raise ValueError("opened Train source changed after discovery freeze")
    if list(workspace.glob("*dev*")):
        raise ValueError("Dev artifact or filename is forbidden during objective discovery")
    return manifest


def read_json(workspace: Path, name: str) -> dict:
    validate_workspace(workspace)
    return _json(Path(workspace) / name, 32 * 1024 * 1024)


def search_literature(workspace: Path, query: str, max_results: int = 5) -> dict:
    validate_workspace(workspace)
    if (not isinstance(query, str) or not query.strip() or len(query) > 1000
            or type(max_results) is not int or not 1 <= max_results <= MAX_LITERATURE_RESULTS):
        raise ValueError("invalid literature query")
    path = Path(workspace) / "literature-snapshot.json"
    snapshot = _json(path, 4 * 1024 * 1024)
    terms = {term.lower() for term in query.split() if term.strip()}
    ranked = []
    for paper in snapshot["papers"]:
        haystack = f"{paper['title']} {paper['abstract']}".lower()
        score = sum(haystack.count(term) for term in terms)
        if score:
            ranked.append((score, paper["paper_id"], paper))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return {
        "query": query,
        "snapshot_sha256": file_hash(path),
        "results": [paper for _, _, paper in ranked[:max_results]],
    }


def source_binding(workspace: Path) -> dict:
    return read_json(workspace, "source-binding.json")


def automatic_audit(workspace: Path) -> dict:
    return read_json(workspace, "automatic-objective-audit.json")

