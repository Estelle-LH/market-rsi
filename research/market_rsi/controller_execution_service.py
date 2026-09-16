"""Runner-owned bridge from controller requests to isolated Harbor/E2B jobs.

The MCP broker can only append a bound request and wait.  This service is the
only component that holds the budget and E2B configuration.  It executes each
permanent request at most once and returns only aggregate Train-CV evidence.
It has no Dev or Future-Test path.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
import time
from pathlib import Path

from controller_candidate_harbor import (prepare_job, run_job,
                                         validate_train_cv_artifact,
                                         verify_candidate_failure)
from controller_workspace import validate_workspace
from market_rsi import canonical, digest, fresh_json, identifier
from objective_contract import label_delay_bounds_ms, validate_objective_contract


RESULT_SCHEMA = "market_controller_execution_result_v1"
RUNNER_SCHEMA = "market_controller_runner_v1"


def _load_regular_json(path: Path, maximum: int = 2 * 1024 * 1024):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("missing, symlinked or oversized runner input")
    return json.loads(path.read_bytes())


def validate_runner_config(path: Path, workspace: Path) -> dict:
    config = _load_regular_json(path)
    manifest = validate_workspace(workspace)
    required = {"schema", "session_id", "experiment_id", "task_id", "train_path",
                "train_sha256", "budget_path", "env_file",
                "budget_bucket", "evidence_class"}
    evidence_class = config.get("evidence_class") if isinstance(config, dict) else None
    if evidence_class == "formal_learning":
        required |= {"round_binding_path", "round_binding_sha256",
                     "objective_contract_path", "objective_contract_sha256"}
    if (not isinstance(config, dict) or set(config) != required
            or config["schema"] != RUNNER_SCHEMA
            or any(config[key] != manifest[key]
                   for key in ("session_id", "experiment_id", "task_id"))
            or config["budget_bucket"] not in {"setup", "learning"}
            or config["evidence_class"] not in {
                "synthetic", "diagnostic", "formal_learning"}):
        raise ValueError("invalid formal controller runner config")
    for key in ("train_sha256", "objective_contract_sha256"):
        if key not in config:
            continue
        value = config[key]
        if (not isinstance(value, str) or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)):
            raise ValueError("runner artifact hash required")
    for key in ("train_path", "budget_path", "env_file",
                "objective_contract_path"):
        if key not in config:
            continue
        value = config[key]
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError("absolute trusted runner path required")
    if evidence_class == "formal_learning":
        from formal_round_binding import validate_binding
        binding_path = Path(config["round_binding_path"])
        if (not binding_path.is_absolute()
                or hashlib.sha256(binding_path.read_bytes()).hexdigest()
                != config["round_binding_sha256"]):
            raise ValueError("formal round binding hash changed")
        binding = validate_binding(binding_path)
        objective_path = Path(config["objective_contract_path"])
        objective = validate_objective_contract(
            _load_regular_json(objective_path),
            experiment_id=config["experiment_id"],
        )
        if (binding["experiment_id"] != config["experiment_id"]
                or binding["task_id"] != config["task_id"]
                or binding["train_path"] != config["train_path"]
                or binding["train_sha256"] != config["train_sha256"]
                or objective["objective_contract_sha256"]
                != config["objective_contract_sha256"]
                or (binding.get("objective_id") is not None
                    and (binding.get("objective_id") != objective["objective_id"]
                         or binding.get("objective_contract_sha256")
                         != objective["objective_contract_sha256"]))):
            raise ValueError("formal Train config differs from round binding")
    return config


def _write_result(workspace: Path, request: dict, *, status: str, score=None,
                  failure=None, job_claim_sha256: str) -> dict:
    if status not in {"completed", "candidate_failed", "infrastructure_failed"}:
        raise ValueError("invalid controller execution status")
    result = {
        "schema": RESULT_SCHEMA,
        "execution_id": request["execution_id"],
        "request_sha256": digest(request),
        "candidate_sha256": request["candidate_sha256"],
        "evaluation_role": "train_cv",
        "execution_verified": status != "infrastructure_failed",
        "future_test_used": False,
        "automatic_retry": False,
        "status": status,
        "score": score,
        "failure": failure,
        "job_claim_sha256": job_claim_sha256,
    }
    target = Path(workspace) / "execution-results" / f"{request['execution_id']}.json"
    fresh_json(target, result)
    return result


class ControllerExecutionService:
    """Single-threaded, no-retry execution owner for one controller session."""

    def __init__(self, workspace: Path, runner_config_path: Path, output: Path):
        self.workspace = Path(workspace).resolve()
        self.manifest = validate_workspace(self.workspace)
        self.config = validate_runner_config(runner_config_path, self.workspace)
        objective_bounds = None
        if self.config["evidence_class"] == "formal_learning":
            objective = validate_objective_contract(_load_regular_json(
                Path(self.config["objective_contract_path"])
            ), experiment_id=self.config["experiment_id"])
            objective_bounds = label_delay_bounds_ms(objective)
        # This is intentionally before the service directory and before any
        # controller/provider process.  A bad reusable split must cost $0.
        self.train_cv_preflight = validate_train_cv_artifact(
            Path(self.config["train_path"]), self.config["train_sha256"],
            self.config["task_id"], evidence_class=self.config["evidence_class"],
            label_delay_bounds_ms=objective_bounds)
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, mode=0o700, exist_ok=False)
        fresh_json(self.output / "service-claim.json", {
            "schema": "market_controller_execution_service_v1",
            "session_id": self.manifest["session_id"],
            "workspace_manifest_sha256": digest(self.manifest),
            "runner_config_sha256": digest(self.config),
            "automatic_retry": False,
            "future_test_used": False,
            "paid_concurrency": 1,
            "train_cv_preflight": self.train_cv_preflight,
        })
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._processed: set[str] = set()
        self._failure: dict | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread is not None:
            raise ValueError("controller execution service already started")
        self._thread = threading.Thread(target=self._serve, daemon=True,
                                        name=f"controller-exec-{self.manifest['session_id']}")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: float = 10) -> None:
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                raise RuntimeError("controller execution service did not stop")

    def snapshot(self) -> dict:
        requests = sorted((self.workspace / "execution-requests").glob("*.json"))
        with self._lock:
            failure = self._failure
            processed = sorted(self._processed)
        return {"processed_execution_ids": processed,
                "request_count": len(requests),
                "pending_requests": sorted(path.stem for path in requests
                                           if path.stem not in processed),
                "failure": failure,
                "running": self._thread is not None and self._thread.is_alive()}

    def execute_request(self, request_path: Path) -> dict:
        request = _load_regular_json(request_path)
        execution_id = request.get("execution_id")
        identifier(execution_id)
        if request_path.name != f"{execution_id}.json":
            raise ValueError("controller request filename changed")
        job_root = self.output / execution_id
        claim = prepare_job(request, self.workspace, self.config, job_root)
        try:
            score = asyncio.run(run_job(job_root, Path(self.config["budget_path"]),
                                        Path(self.config["env_file"])))
            if (score.get("evaluation_role") != "train_cv"
                    or score.get("primary", {}).get("valid") is not True):
                raise ValueError("completed candidate has no valid full-coverage Train-CV score")
            return _write_result(self.workspace, request, status="completed", score=score,
                                 failure=None, job_claim_sha256=digest(claim))
        except Exception as error:
            try:
                failure = verify_candidate_failure(job_root)
            except Exception as verification_error:
                record = {"schema": "market_controller_infrastructure_failure_v1",
                          "execution_id": execution_id,
                          "error_type": type(error).__name__,
                          "verification_error_type": type(verification_error).__name__,
                          "automatic_retry": False, "future_test_used": False}
                fresh_json(job_root / "service-failure.json", record)
                return _write_result(self.workspace, request, status="infrastructure_failed",
                                     score=None, failure=record,
                                     job_claim_sha256=digest(claim))
            return _write_result(self.workspace, request, status="candidate_failed", score=None,
                                 failure=failure, job_claim_sha256=digest(claim))

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                paths = sorted((self.workspace / "execution-requests").glob("*.json"))
                for path in paths:
                    if path.stem in self._processed:
                        continue
                    result = self.execute_request(path)
                    with self._lock:
                        self._processed.add(path.stem)
                    if result["status"] == "infrastructure_failed":
                        raise RuntimeError("controller candidate infrastructure failed; no retry")
            except Exception as error:
                failure = {"error_type": type(error).__name__,
                           "error_message": str(error),
                           "automatic_retry": False}
                with self._lock:
                    self._failure = failure
                fresh_json(self.output / "service-failure.json", failure)
                self._stop.set()
                break
            self._stop.wait(0.05)
        state = self.snapshot()
        state["running"] = False
        fresh_json(self.output / "service-final.json", state)
