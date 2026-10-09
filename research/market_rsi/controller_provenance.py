"""Freeze and verify the complete source set used by a formal controller session."""
from __future__ import annotations

import json
from pathlib import Path

from market_rsi import file_hash, fresh_json
from data_scientist_harness.release import ROOT_SOURCE_FILES


HERE = Path(__file__).resolve().parent
# The formal controller manifest follows the same explicit root boundary as
# the release. These four files are the compatibility transport sources used by
# the retained Harbor/controller path.
SOURCE_NAMES = tuple(ROOT_SOURCE_FILES) + (
    "controller_tools_mcp.py",
    "diagnostic_channel.py",
    "prediction_candidate_server.py",
    "sandbox_prediction_runner.py",
    "fixtures/harbor-stream-01/environment/Dockerfile",
    "fixtures/harbor-stream-01/instruction.md",
    "fixtures/harbor-stream-01/isolation_probe.py",
    "fixtures/harbor-stream-01/task.toml",
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
