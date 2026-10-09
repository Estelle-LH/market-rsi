"""Runner-owned Git publication gate. No automatic commit, tag, push or payment.

The release receipt binds an annotated, pushed tag to exact executable sources
and a successful same-source/runtime canary. A version label alone is not proof.
"""
import argparse
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tarfile
from datetime import datetime, timezone

from data_scientist_harness import VERSION
from data_scientist_harness.core_dependency import CORE_FILES
from market_rsi import digest, file_hash, fresh_json, load_json

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://github.com/Estelle-LH/RSIBench-Data.git"
TAG = "dsh-v" + VERSION.rsplit("-v", 1)[1]
CHANGE_ORIGIN = "human_directed_engineering"

# Explicit root-level compatibility/runtime source boundary.  The previous
# root glob silently published every historical helper in this directory.  A
# module must be added here only when an active release entrypoint imports it;
# historical scripts and one-off diagnostics stay outside the release.
ROOT_SOURCE_FILES = (
    "archive_snapshot.py", "audit_historical_objective_numerics.py",
    "build_archive_continuation_data.py", "build_archive_formal_data.py",
    "codex_glm_model_catalog.py", "codex_glm_provider.py",
    "codex_glm_responses_adapter.py", "controller_activity_log.py",
    "controller_candidate_harbor.py", "controller_execution_service.py",
    "controller_harness_contract.py", "controller_provenance.py",
    "controller_workspace.py", "data_discovery_activity.py",
    "data_discovery_harness.py", "data_discovery_tools_mcp.py",
    "data_discovery_workspace.py", "data_lifecycle.py",
    "data_source_catalog.py", "formal_round_binding.py",
    "glm_canary.py", "harness_evolution.py",
    "historical_conditional_diagnostics.py", "historical_data_use_controller.py",
    "historical_delta_evaluation.py", "historical_direction_fields.py",
    "historical_feature_composition.py", "historical_grid_features.py",
    "historical_grid_learning.py", "historical_grid_learning_controller.py",
    "historical_grid_objective_controller.py", "historical_grid_objectives.py",
    "historical_ingest_controller.py", "historical_input_compatibility.py",
    "historical_learning_diagnostics.py", "historical_learning_recovery.py",
    "historical_recorded_features.py", "historical_source_contract.py",
    "historical_trade_windows.py", "literature_catalog.py", "market_harbor.py",
    "market_rsi.py", "market_scoring.py", "materialize_selected_grid_objective.py",
    "objective_contract.py", "objective_discovery_activity.py",
    "objective_discovery_harness.py", "objective_discovery_tools_mcp.py",
    "objective_discovery_workspace.py", "objective_train_audit.py",
    "paid_budget.py", "polymarket_scoring.py", "prediction_stream.py",
    "prospective_data_lifecycle.py", "run_codex_glm_controller.py",
    "time_series_data_diagnostics.py", "time_series_research_harness.py",
    "time_series_split_policy.py", "training_population_policy.py",
)


def source_files(root=ROOT):
    root = Path(root)
    files = [root / name for name in ROOT_SOURCE_FILES]
    for name in ("data_scientist_harness", "data_science_tools", "validation_tools",
                 "source_review_tools", "sports_event_research"):
        files.extend((root / name).glob("*.py"))
    # Aggregate controller preparation is part of the scientific input boundary.
    # Bind both the previous receipt validator and the current feedback adapter.
    files.extend(root / "audit_tools" / name for name in (
        "prepare_nfl_60s_baseline_feedback_controller.py",
        "prepare_nfl_full_cohort_feedback_controller.py"))
    files.extend(root / "ds_harness_core" / name for name in CORE_FILES)
    files.append(root / "data_scientist_harness/requirements-cpu.txt")
    return sorted(p for p in files if not p.name.startswith("test_"))


def source_hashes(root=ROOT):
    root = Path(root)
    result = {}
    for path in source_files(root):
        if path.is_symlink() or not path.is_file() or path.resolve() != path:
            raise ValueError("release source missing or noncanonical")
        result[str(path.relative_to(root))] = file_hash(path)
    return result


def git(repo, *args):
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
            timeout=20, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Git publication check timed out; no experiment started") from error
    if result.returncode:
        # Git stderr/remote configuration may contain credentials; do not echo it.
        raise ValueError("Git publication check failed; no experiment started")
    return result.stdout


def verify_git_publication(sources, *, root=ROOT, commit=None):
    """Check current runtime files against Git blobs and the live origin tag.

    Unrelated dirty notes elsewhere are preserved. Every executable source in
    this harness's explicit snapshot scope must be tracked, clean and exact.
    """
    root = Path(root).resolve()
    if source_hashes(root) != sources:
        raise ValueError("running source set differs from release/canary")
    repo = Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    prefix = str(root.relative_to(repo))
    if git(repo, "remote", "get-url", "origin").decode().strip() != ORIGIN:
        raise ValueError("release origin is not the authorized private repository")
    commit = commit or git(repo, "rev-parse", "HEAD").decode().strip()
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("full Git commit required")
    paths = [f"{prefix}/{p}" for p in sources]
    if git(repo, "status", "--porcelain", "--untracked-files=all", "--", *paths).strip():
        raise ValueError("uncommitted executable source; commit and push a new harness version")
    committed = {}
    # One archive with all 204 pathspecs repeatedly exceeded 20s in the real
    # repository; bounded 16-file batches read the same blobs in under 2s.
    # Keep the complete set/hash comparison: batching does not omit any source.
    for start in range(0, len(paths), 16):
        archive = git(repo, "archive", "--format=tar", commit, "--", *paths[start:start + 16])
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            for member in stream:
                if member.isfile():
                    name = member.name.removeprefix(prefix + "/")
                    if name in committed:
                        raise ValueError("duplicate source in Git archive batches")
                    committed[name] = hashlib.sha256(stream.extractfile(member).read()).hexdigest()
    if committed != sources:
        raise ValueError("Git commit does not contain the exact canary/runtime source set")
    ref = "refs/tags/" + TAG
    if git(repo, "cat-file", "-t", ref).decode().strip() != "tag":
        raise ValueError("annotated release tag required")
    tagged = git(repo, "rev-parse", ref + "^{commit}").decode().strip()
    tag_object = git(repo, "rev-parse", ref).decode().strip()
    if tagged != commit:
        raise ValueError("release tag belongs to another commit; never move an existing tag")
    remote = git(repo, "ls-remote", "--exit-code", "origin", ref, ref + "^{}").decode().splitlines()
    observed = {line.split()[1]: line.split()[0] for line in remote if len(line.split()) == 2}
    if observed != {ref: tag_object, ref + "^{}": commit}:
        raise ValueError("release tag is not published at origin with the exact commit")
    return {"origin": ORIGIN, "tag": TAG, "commit": commit, "tag_object": tag_object,
            "tree": git(repo, "rev-parse", commit + "^{tree}").decode().strip(),
            "checked_utc": datetime.now(timezone.utc).isoformat(), "source_prefix": prefix}


def validate_release(value, sources, runtime):
    if not isinstance(value, dict):
        raise ValueError("published harness release required before an experiment")
    unsigned = {k: v for k, v in value.items() if k != "release_sha256"}
    if (value.get("schema") != "data_scientist_release_v1"
            or value.get("release_sha256") != digest(unsigned)
            or value.get("harness_version") != VERSION or value.get("source_hashes") != sources
            or value.get("harness_change_origin") != CHANGE_ORIGIN
            or value.get("runtime") != runtime or value.get("publication", {}).get("origin") != ORIGIN
            or value.get("publication", {}).get("tag") != TAG):
        raise ValueError("release version/source/runtime/publication binding differs")
    return value


def record_release(canary_path, output):
    from data_scientist_harness.run_controller import source_hashes as snapshot_hashes, harness
    from data_scientist_harness.store import Store
    canary_path, output = Path(canary_path).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("release receipt is append-only; use a fresh path")
    canary = load_json(canary_path)
    store = Store(canary_path.parent, canary["manifest_sha256"])
    assessment = load_json(canary_path.parent / "session/assessment.json")
    sources = source_hashes()
    if (canary.get("schema") != "data_scientist_codex_canary_v1" or not canary.get("passed")
            or canary.get("result_sha256") != digest({k:v for k,v in canary.items() if k != "result_sha256"})
            or canary.get("actual_tinker_calls") != 0 or canary.get("model_authorship_proven") is not False
            or canary.get("source_hashes") != sources or snapshot_hashes(store) != sources
            or canary.get("assessment_sha256") != file_hash(canary_path.parent / "session/assessment.json")
            or canary.get("codex_sha256") != file_hash(harness.CODEX)
            or assessment.get("valid") is not True or assessment.get("process_reaped") is not True
            or assessment.get("evidence_mode") != "synthetic_transport_fixture"
            or assessment.get("turns") != 18 or assessment.get("tool_calls") != 18):
        raise ValueError("passing exact-source/runtime real Codex fixture required for release")
    value = {"schema": "data_scientist_release_v1", "harness_version": VERSION,
        "harness_change_origin": CHANGE_ORIGIN, "harness_self_evolution_claim": False,
        "source_hashes": sources, "runtime": store.config["runtime"],
        "publication": verify_git_publication(sources),
        "canary": {"path": str(canary_path), "sha256": file_hash(canary_path),
                   "codex_sha256": canary["codex_sha256"]},
        "scientific_performance_claim": False}
    value["release_sha256"] = digest(value)
    output.parent.mkdir(parents=True, exist_ok=True)
    fresh_json(output, value)
    return value


def identity(config):
    value = config.get("release")
    return {"version": config["harness_version"], "published": value is not None,
            "change_origin": config["harness_change_origin"], "is_agent_self_evolution": False,
            "commit": value["publication"]["commit"] if value else None,
            "tag": value["publication"]["tag"] if value else None,
            "release_sha256": value["release_sha256"] if value else None}


def attribution(config, plan=None):
    """Hashes describe possible confounders; they do not prove a causal effect."""
    inputs = {Path(p).name: sha for p, sha in config["files"].items() if Path(p).parent.name == "inputs"}
    release_id = identity(config)
    result = {"harness": {k: release_id[k] for k in ("version", "commit", "change_origin")},
        "runtime_sha256": digest(config["runtime"]),
        "codex_sha256": config["release"]["canary"].get("codex_sha256") if config.get("release") else None,
        "research_context_sha256": digest({Path(p).name: sha for p, sha in config["files"].items()
            if Path(p).name in {"archive-input.json", "findings.json"}}),
        "data_sha256": digest({k: inputs.get(k) for k in ("current-inputs.npz", "input-result.json", "panel-result.json")}),
        "labels_sha256": digest({k: inputs.get(k) for k in ("primary-labels.npz", "label-result.json")}),
        "objective_sha256": inputs.get("objective-proposal.json"),
        "sanity_contract_sha256": inputs.get("sanity-contract.json"),
        "data_use_sha256": inputs.get("data-use-proposal.json")}
    if plan is not None:
        result.update(features_sha256=digest(plan["features"]),
            trainer_sha256=digest({k: plan[k] for k in ("model", "normalizer", "train_weighting",
                "missing_input_action", "output_transform", "seed")}),
            evaluation_sha256=digest({k: plan[k] for k in ("train_utc_dates", "check_utc_dates", "score_aggregation")}))
    return result


def compare_attribution(before, after):
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    # A same-harness comparison is necessary, never sufficient for learning claims.
    return {"changed_components": changed, "model_only_claim_blocked": any(k not in
        {"features_sha256", "trainer_sha256"} for k in changed) or len(changed) != 1,
        "performance_improvement_proven": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = record_release(args.canary, args.output)
    print({"version": receipt["harness_version"], "publication": receipt["publication"],
           "release_sha256": receipt["release_sha256"], "new_experiments": 0})
