"""Freeze and verify the complete source set used by a formal controller session."""
from __future__ import annotations

import json
from pathlib import Path

from market_rsi import file_hash, fresh_json


HERE = Path(__file__).resolve().parent
SOURCE_NAMES = (
    "archive_snapshot.py",
    "candidate_integrity.py",
    "build_archive_formal_data.py",
    "build_archive_continuation_data.py",
    "codex_glm_model_catalog.py",
    "codex_glm_provider.py",
    "codex_glm_responses_adapter.py",
    "controller_candidate_harbor.py",
    "controller_activity_log.py",
    "controller_execution_service.py",
    "controller_harness_contract.py",
    "controller_provenance.py",
    "controller_tools_mcp.py",
    "controller_workspace.py",
    "data_lifecycle.py",
    "data_discovery_activity.py",
    "data_discovery_harness.py",
    "data_discovery_tools_mcp.py",
    "data_discovery_workspace.py",
    "data_source_catalog.py",
    "clean_openmarket_sample.py",
    "polymarket_historical_source_canary.py",
    "openmarket_partition_canary.py",
    "source_terms_gate.py",
    "formal_round_binding.py",
    "finalize_archive_formal_round.py",
    "literature_catalog.py",
    "build_objective_discovery_canary_data.py",
    "objective_contract.py",
    "objective_discovery_activity.py",
    "objective_discovery_harness.py",
    "objective_discovery_tools_mcp.py",
    "objective_discovery_workspace.py",
    "objective_train_audit.py",
    "polymarket_objective_data.py",
    "materialize_polymarket_objective_archives.py",
    "prospective_data_lifecycle.py",
    "prospective_time_series_materializer.py",
    "diagnostic_channel.py",
    "fixtures/harbor-stream-01/environment/Dockerfile",
    "fixtures/harbor-stream-01/instruction.md",
    "fixtures/harbor-stream-01/isolation_probe.py",
    "fixtures/harbor-stream-01/task.toml",
    "glm_canary.py",
    "harness_evolution.py",
    "market_harbor.py",
    "market_rsi.py",
    "market_scoring.py",
    "paid_budget.py",
    "polymarket_scoring.py",
    "prediction_candidate_server.py",
    "prediction_stream.py",
    "prepare_archive_carryover_canary.py",
    "prepare_archive_formal_round.py",
    "prepare_objective_discovery_session.py",
    "prepare_data_discovery_session.py",
    "promote_objective_for_formal.py",
    "project_selected_objective.py",
    "run_codex_glm_controller.py",
    "sandbox_prediction_runner.py",
    "sealed_dev_runner.py",
    "time_series_split_policy.py",
    "time_series_research_harness.py",
    "time_series_data_diagnostics.py",
    "training_population_policy.py",
    "prospective_sealed_dev_runner.py",
)


def source_manifest() -> dict:
    sources = {}
    for name in SOURCE_NAMES:
        path = HERE / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("controller source set missing or symlinked")
        sources[name] = file_hash(path)
    return {"schema": "market_controller_source_manifest_v1", "sources": sources}


def freeze_source_manifest(path: Path) -> dict:
    manifest = source_manifest()
    fresh_json(path, manifest)
    return manifest


def validate_source_manifest(path: Path) -> dict:
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256 * 1024:
        raise ValueError("missing, symlinked or oversized controller source manifest")
    manifest = json.loads(path.read_bytes())
    if manifest != source_manifest():
        raise ValueError("formal controller source changed after preparation")
    return manifest
