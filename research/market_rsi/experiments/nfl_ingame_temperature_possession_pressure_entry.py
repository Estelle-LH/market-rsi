"""Thin reviewed D1 worker entry; no scientific or scoring modifications."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
from experiments import nfl_ingame_temperature_possession_pressure_joint_offset as d1
from experiments import nfl_ingame_candidate_evidence_adapter as harness
from supervisor_harness import opened_train_discovery_worker as worker

REPO = Path(__file__).parents[3]
ENVELOPE = "research/market_rsi/supervisor_harness/COEVO_D1_ENTRY_ENVELOPE_2026-10-05-v1.json"
ENVELOPE_SHA256 = "fb968b7ff45b22211d4de581cdf43784bc7b734e7eef7348adaff8bf9761cab0"
SOURCE_REVIEW_SHA256 = "13913664f1f24590adcbd265f5d39121e95f2e71615651795242b87d372dd4cb"
MODULE = "experiments.nfl_ingame_temperature_possession_pressure_entry"
common = d1.common

def utc_now():
    return datetime.now(timezone.utc)

def require_admission(source_root, output):
    path = REPO / ENVELOPE
    if path.is_symlink() or common._sha256(path) != ENVELOPE_SHA256:
        raise ValueError("D1 operational envelope changed")
    envelope = common.settlement._strict_json(path)
    authority, science, h, gates = [envelope[key] for key in ("operational_authority", "fixed_scientific_bindings", "fixed_harness_bindings", "mandatory_live_review_gates")]
    start, deadline = [datetime.fromisoformat(authority[key].replace("Z", "+00:00")) for key in ("start_utc", "deadline_utc")]
    if not start <= utc_now() < deadline:
        raise ValueError("D1 fresh execution authority expired or not started")
    output = Path(output)
    if output.is_symlink() or output.parent.name != "runs" or not output.name:
        raise ValueError("D1 output must be exclusive worker pilot/runs/attempt")
    request_path = output.parents[1] / "worker" / f"{output.name}.request.json"
    if request_path.is_symlink():
        raise ValueError("D1 request is symlinked")
    request = common.settlement._strict_json(request_path)
    if (request["attempt_id"] != output.name or request["candidate_id"] != science["candidate_id"]
            or request["module"] != MODULE or request["spec_sha256"] != ENVELOPE_SHA256
            or request["max_fits"] != 4 or request["max_wall_seconds"] > 900
            or request["python"] != envelope["runtime"]["python"] or request["python_sha256"] != envelope["runtime"]["python_sha256"]):
        raise ValueError("D1 exact request/operational spec/runtime changed")
    worker.validate(request, REPO)
    binding = harness.held_c7_binding()
    required = {ENVELOPE: ENVELOPE_SHA256, h["adapter_path"]: h["adapter_source_sha256"], h["worker_path"]: h["worker_sha256"], h["adapter_contract_path"]: h["adapter_contract_sha256"], gates["source_review_path"]: SOURCE_REVIEW_SHA256}
    for key in ("scientific_source", "scientific_test", "scientific_contract", "parent_source", "basis_source"):
        required[science[key + "_path"]] = science[key + "_sha256"]
    required[h["adapter_path"].replace("/nfl_", "/test_nfl_")] = h["adapter_test_sha256"]
    for filename, digest in binding["dependency_source_hashes"].items():
        required[str(Path(filename).relative_to(Path(__file__).parents[3]))] = digest
    if any(request["files"].get(relative) != digest for relative, digest in required.items()):
        raise ValueError("D1 exact source/helper/review coverage changed")
    review_paths = [gates[key] for key in ("source_review_path", "live_parity_review_path")]
    if any(relative not in request["files"] for relative in review_paths):
        raise ValueError("D1 missing independently admitted H source/parity")
    source_review, parity = [common.settlement._strict_json(REPO / relative) for relative in review_paths]
    if (source_review.get("passed") is not True or source_review.get("source_sha256") != h["adapter_source_sha256"]
            or source_review.get("verdict") != "EXACT_SOURCE_ADMITTED_FOR_ONE_BOUNDED_HELD_C7_TRIAL"):
        raise ValueError("D1 H source is not independently admitted")
    expected = {**gates["required_parity_fields"], "source_review_sha256": request["files"][gates["source_review_path"]]}
    if any(type(parity.get(key)) is not type(value) or parity.get(key) != value for key, value in expected.items()):
        raise ValueError("D1 H live parity gate failed")
    contract = common.settlement._strict_json(d1.CONTRACT)
    binding.update(candidate_id=d1.TASK_ID, arm=d1.ARM_CANDIDATE, candidate_source_path=str(Path(d1.__file__).resolve()), candidate_source_sha256=science["scientific_source_sha256"], candidate_contract_path=str(d1.CONTRACT.resolve()), candidate_contract_sha256=d1.CONTRACT_SHA256, research_parent=contract["research_parent"], feature_names=d1.FEATURE_NAMES, comparison_incumbent_sha256=contract["comparison_incumbent"]["sha256"], attribution=contract["attribution"])
    binding["dependency_source_hashes"].update({str(Path(d1.__file__).resolve()): science["scientific_source_sha256"], str(Path(d1.pressure.__file__).resolve()): science["basis_source_sha256"]})
    binding["callback_source_bindings"] = {name: str(Path(d1.__file__).resolve()) for name in ("prepare_features", "fit_predict", "replay_predictor")}
    harness.validate_binding(binding, {name: getattr(d1, name) for name in binding["callback_source_bindings"]})
    return binding

def run(source_root, output, *, allow_test_paths=False):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("D1 output already exists; inspect without relaunch")
    try:
        binding = require_admission(source_root, output)
        if not allow_test_paths and Path(source_root).resolve() != worker.TRAIN.resolve():
            raise ValueError("D1 source is not resident authorized Train")
        return d1.run(source_root, output, binding=binding, allow_test_paths=allow_test_paths)
    except Exception as error:
        if not output.exists():
            output.mkdir(parents=True, exist_ok=False)
            common.base._atomic_json(output / "failure.json", {"task_id": d1.TASK_ID, "phase": "entry_admission", "error_type": type(error).__name__, "error": str(error)[:1200], "model_fits": 0, "automatic_retries": 0, **common.BOUNDARY_FLAGS})
        raise

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(common.settlement.json.dumps(run(args.source_root, args.output), sort_keys=True, indent=2))

if __name__ == "__main__":
    main()
