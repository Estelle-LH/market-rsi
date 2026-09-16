"""Frozen, aggregate-only workspace for controller-led data research."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from data_discovery_harness import data_discovery_harness_contract
from data_source_catalog import data_source_catalog, get_data_source
from literature_catalog import literature_snapshot
from market_rsi import digest, file_hash, fresh_json, identifier
from training_population_policy import audit_open_train, policy_contract


SCHEMA = "market_data_discovery_workspace_v1"


def _json(path: Path, maximum: int = 1_073_741_824):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("missing, symlinked or oversized data-discovery input")
    return json.loads(path.read_bytes())


def _write(path: Path, value: dict) -> None:
    fresh_json(path, value)
    os.chmod(path, 0o600)


def _receipt(path: Path) -> dict:
    raw = path.read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _utc_date(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).date().isoformat()


def prepare_workspace(output: Path, *, session_id: str, experiment_id: str,
                      current_source_path: Path,
                      opened_train_utc_dates: list[str],
                      source_canary_report: Path | None = None) -> dict:
    identifier(session_id)
    identifier(experiment_id)
    if (not opened_train_utc_dates
            or opened_train_utc_dates != sorted(set(opened_train_utc_dates))):
        raise ValueError("unique chronological opened Train dates required")
    source_path = Path(current_source_path).resolve()
    source = _json(source_path)
    rows = [row for row in source.get("rows", [])
            if _utc_date(row.get("decision_ms", 0)) in opened_train_utc_dates]
    current_audit = audit_open_train(rows)
    current_audit["bound_source_sha256"] = file_hash(source_path)
    current_audit["opened_train_utc_dates"] = opened_train_utc_dates

    output = Path(output).resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    (output / "data-plans").mkdir(mode=0o700)
    (output / "data-plan-audits").mkdir(mode=0o700)
    canary = {"status": "not_provided"}
    canary_sha256 = None
    if source_canary_report is not None:
        source_canary_report = Path(source_canary_report).resolve()
        canary = _json(source_canary_report, 32 * 1024 * 1024)
        supported = (
            (
                canary.get("schema") == "openmarket_public_sample_clean_canary_v1"
                and canary.get("canary_pass") is True
            )
            or (
                canary.get("schema") == "market_source_canary_controller_evidence_v1"
                and canary.get("canary_status") in {
                    "data_path_pass_terms_review_pending", "rejected_by_frozen_plan"}
            )
            or (
                canary.get("schema") == "market_source_terms_gate_controller_evidence_v1"
                and canary.get("status") == "rejected_before_data_access"
            )
            or (
                canary.get("schema") == "openmarket_partition_clean_canary_v1"
                and canary.get("canary_pass") is True
            )
        )
        if not supported or canary.get("full_download_authorized") is not False:
            raise ValueError("valid bounded source canary report required")
        canary_sha256 = file_hash(source_canary_report)
    visible = {
        "current-data-audit.json": current_audit,
        "source-canary-evidence.json": canary,
        "data-source-catalog.json": data_source_catalog(),
        "literature-snapshot.json": literature_snapshot(),
        "population-policy.json": policy_contract(),
        "data-discovery-harness.json": data_discovery_harness_contract(),
    }
    for name, value in visible.items():
        _write(output / name, value)
    manifest = {
        "schema": SCHEMA,
        "session_id": session_id,
        "experiment_id": experiment_id,
        "files": {name: _receipt(output / name) for name in visible},
        "current_source_path": str(source_path),
        "current_source_sha256": file_hash(source_path),
        "opened_train_utc_dates": opened_train_utc_dates,
        "source_canary_report_sha256": canary_sha256,
        "dev_artifact_present": False,
        "future_test_artifact_present": False,
        "selection_state": "unfrozen",
    }
    _write(output / "data-discovery-workspace.json", manifest)
    validate_workspace(output)
    return manifest


def validate_workspace(workspace: Path) -> dict:
    workspace = Path(workspace).resolve()
    manifest = _json(workspace / "data-discovery-workspace.json", 2_000_000)
    expected = {"schema", "session_id", "experiment_id", "files",
                "current_source_path", "current_source_sha256",
                "opened_train_utc_dates", "source_canary_report_sha256", "dev_artifact_present",
                "future_test_artifact_present", "selection_state"}
    if (set(manifest) != expected or manifest.get("schema") != SCHEMA
            or manifest.get("dev_artifact_present") is not False
            or manifest.get("future_test_artifact_present") is not False
            or manifest.get("selection_state") != "unfrozen"):
        raise ValueError("data-discovery workspace manifest changed")
    identifier(manifest["session_id"])
    identifier(manifest["experiment_id"])
    expected_files = {"current-data-audit.json", "source-canary-evidence.json", "data-source-catalog.json",
                      "literature-snapshot.json", "population-policy.json",
                      "data-discovery-harness.json"}
    if set(manifest["files"]) != expected_files:
        raise ValueError("data-discovery visible files changed")
    for name, receipt in manifest["files"].items():
        if _receipt(workspace / name) != receipt:
            raise ValueError("data-discovery input changed")
    source_path = Path(manifest["current_source_path"])
    if (source_path.is_symlink() or not source_path.is_file()
            or file_hash(source_path) != manifest["current_source_sha256"]):
        raise ValueError("current opened-Train source changed")
    if list(workspace.glob("*dev*")):
        raise ValueError("Dev artifact is forbidden during data discovery")
    return manifest


def read_json(workspace: Path, name: str) -> dict:
    validate_workspace(workspace)
    return _json(Path(workspace) / name, 32 * 1024 * 1024)


def search_sources(workspace: Path, query: str, max_results: int = 5) -> dict:
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        raise ValueError("nonempty bounded data-source query required")
    if type(max_results) is not int or not 1 <= max_results <= 8:
        raise ValueError("invalid result limit")
    catalog = read_json(workspace, "data-source-catalog.json")
    terms = {term.lower() for term in query.split() if term.strip()}
    ranked = []
    for source in catalog["sources"]:
        haystack = json.dumps(source, sort_keys=True).lower()
        score = sum(haystack.count(term) for term in terms)
        if score:
            ranked.append((score, source["source_id"], source))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return {"query": query, "catalog_sha256": catalog["catalog_sha256"],
            "results": [item[2] for item in ranked[:max_results]]}


def inspect_source(workspace: Path, source_id: str) -> dict:
    read_json(workspace, "data-source-catalog.json")
    return get_data_source(source_id)


def search_literature(workspace: Path, query: str, max_results: int = 5) -> dict:
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        raise ValueError("nonempty bounded literature query required")
    if type(max_results) is not int or not 1 <= max_results <= 8:
        raise ValueError("invalid result limit")
    snapshot = read_json(workspace, "literature-snapshot.json")
    terms = {term.lower() for term in query.split() if term.strip()}
    ranked = []
    for paper in snapshot["papers"]:
        haystack = f"{paper['title']} {paper['abstract']}".lower()
        score = sum(haystack.count(term) for term in terms)
        if score:
            ranked.append((score, paper["paper_id"], paper))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return {"query": query, "snapshot_sha256": digest(snapshot),
            "results": [item[2] for item in ranked[:max_results]]}
