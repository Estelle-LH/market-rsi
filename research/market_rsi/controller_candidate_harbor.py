"""Runner-owned Harbor/E2B Train-CV execution for a controller candidate.

The candidate receives an older Train fit slice and one later Train-CV feature
row at a time.  CV labels stay in the trusted job directory and scoring happens
only after the sandbox is killed.  This module accepts neither a current Dev
path nor a Future-Test path.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.models.task.config import NetworkMode
from harbor.models.trial.config import AgentConfig, EnvironmentConfig, TaskConfig, TrialConfig, VerifierConfig
from harbor.trial.trial import Trial

from market_harbor import BoundedMarketE2B, ISOLATION_CHECKS, PRIVATE, PUBLIC, RATES, TEMPLATE
from market_rsi import canonical, digest, file_hash, fresh_json, identifier
from objective_contract import label_delay_bounds_ms, validate_objective_contract
from paid_budget import PaidBudget
from polymarket_scoring import (PolymarketScoreContract,
                                score_contract_from_objective,
                                score_polymarket)
from prediction_stream import PUBLIC_FIELDS, fingerprint, validate_rows
from time_series_split_policy import (policy_contract, train_cv_split,
                                      validate_outer_dev)


HERE = Path(__file__).resolve().parent
TASK = HERE / "fixtures" / "harbor-stream-01"
TTL = 180
UPPER_USD = "0.10"
DEPLOYED = {
    "private/sandbox_prediction_runner.py": HERE / "sandbox_prediction_runner.py",
    "private/prediction_stream.py": HERE / "prediction_stream.py",
    "private/diagnostic_channel.py": HERE / "diagnostic_channel.py",
    "public/prediction_candidate_server.py": HERE / "prediction_candidate_server.py",
    "public/isolation_probe.py": HERE / "fixtures/harbor-stream-01/isolation_probe.py",
}
OUTPUTS = ("isolation.json", "execution.json", "failure.json", "protocol.json",
           "candidate-stderr.json",
           "predictions/claim.json", "predictions/predictions.jsonl", "predictions/complete.json")
def _read(path: Path, maximum: int = 32 * 1024 * 1024) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("missing, symlinked or oversized controller execution input")
    return path.read_bytes()


def _json(path: Path):
    return json.loads(_read(path))


def _artifact(path: Path, split: str, sha256: str) -> dict:
    raw = _read(path, 16 * 1024 * 1024)
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise ValueError("controller Train/Dev artifact changed")
    value = json.loads(raw)
    if (value.get("schema") != "market_permitted_rows_v1" or value.get("split") != split
            or not isinstance(value.get("rows"), list) or not value["rows"]):
        raise ValueError("invalid controller Train/Dev artifact")
    return value


def temporal_train_cv(
    rows: list[dict], *, evidence_class: str = "diagnostic",
    label_delay_bounds: tuple[int, int] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Compatibility wrapper around the frozen runner-owned split policy."""
    fit, cv, _ = train_cv_split(
        rows, evidence_class=evidence_class,
        label_delay_bounds_ms=label_delay_bounds,
    )
    return fit, cv


def validate_train_cv_artifact(
    path: Path, sha256: str, task_id: str, *, evidence_class: str = "diagnostic",
    label_delay_bounds_ms: tuple[int, int] | None = None,
) -> dict:
    """Fail locally before a paid controller starts if Train-CV is impossible."""
    train = _artifact(Path(path), "train", sha256)
    if train.get("task_id") != task_id:
        raise ValueError("controller execution task changed")
    _, _, audit = train_cv_split(
        train["rows"], evidence_class=evidence_class,
        label_delay_bounds_ms=label_delay_bounds_ms,
    )
    return audit


def _objective_label_delay_bounds(runner_config: dict) -> tuple[int, int] | None:
    if runner_config.get("evidence_class") != "formal_learning":
        return None
    objective_path = Path(runner_config["objective_contract_path"])
    objective = validate_objective_contract(
        _json(objective_path), experiment_id=runner_config["experiment_id"]
    )
    binding_path = Path(runner_config["round_binding_path"])
    binding = _json(binding_path)
    if (objective["objective_contract_sha256"]
            != runner_config["objective_contract_sha256"]
            or file_hash(binding_path) != runner_config["round_binding_sha256"]
            or binding.get("schema") != "market_archive_formal_round_binding_v1"
            or (binding.get("objective_id") is not None
                and (binding.get("objective_id") != objective["objective_id"]
                     or binding.get("objective_contract_sha256")
                     != objective["objective_contract_sha256"]))):
        raise ValueError("candidate runner objective binding changed")
    return label_delay_bounds_ms(objective)


def prepare_job(request: dict, workspace: Path, runner_config: dict, output: Path) -> dict:
    """Prepare a controller-visible execution using open Train data only."""
    return _prepare_job(request, workspace, runner_config, output, expected_role="train_cv")


def prepare_sealed_dev_job(
    request: dict, workspace: Path, runner_config: dict, output: Path
) -> dict:
    """Prepare the one post-session Dev execution; never call from the MCP service."""
    return _prepare_job(request, workspace, runner_config, output, expected_role="sealed_dev")


def _prepare_job(
    request: dict,
    workspace: Path,
    runner_config: dict,
    output: Path,
    *,
    expected_role: str,
) -> dict:
    from controller_workspace import validate_workspace
    workspace = Path(workspace).resolve()
    manifest = validate_workspace(workspace)
    if (not isinstance(request, dict)
            or request.get("schema") != "market_controller_execution_request_v1"
            or request.get("session_id") != manifest["session_id"]
            or request.get("experiment_id") != manifest["experiment_id"]
            or request.get("task_id") != manifest["task_id"]
            or request.get("workspace_manifest_sha256") != digest(manifest)
            or request.get("evaluation_role") != expected_role
            or request.get("automatic_retry") is not False):
        raise ValueError("controller execution request changed")
    common_config = {"schema", "session_id", "experiment_id", "task_id", "train_path",
                     "train_sha256", "budget_path", "env_file",
                     "budget_bucket", "evidence_class"}
    evidence_class = (runner_config.get("evidence_class")
                      if isinstance(runner_config, dict) else None)
    if evidence_class == "formal_learning":
        common_config |= {"round_binding_path", "round_binding_sha256",
                          "objective_contract_path", "objective_contract_sha256"}
    expected_config = (common_config if expected_role == "train_cv" else common_config | {
        "dev_path", "dev_sha256", "lifecycle_root", "round_id",
        "controller_view_sha256", "train_dataset_ids", "dev_dataset_ids",
        "session_assessment_path",
    })
    expected_schema = ("market_controller_runner_v1" if expected_role == "train_cv"
                       else "market_controller_sealed_dev_runner_v1")
    if (not isinstance(runner_config, dict) or set(runner_config) != expected_config
            or runner_config["schema"] != expected_schema
            or any(runner_config[key] != manifest[key]
                   for key in ("session_id", "experiment_id", "task_id"))
            or runner_config["budget_bucket"] not in {"setup", "learning"}
            or runner_config["evidence_class"] not in {
                "synthetic", "diagnostic", "formal_learning"}):
        raise ValueError("controller runner config changed")
    if evidence_class == "formal_learning":
        binding_path = Path(runner_config["round_binding_path"])
        binding_raw = _read(binding_path, 2 * 1024 * 1024)
        binding = json.loads(binding_raw)
        if (not binding_path.is_absolute()
                or hashlib.sha256(binding_raw).hexdigest()
                != runner_config["round_binding_sha256"]
                or binding.get("schema") != "market_archive_formal_round_binding_v1"
                or binding.get("experiment_id") != runner_config["experiment_id"]
                or binding.get("task_id") != runner_config["task_id"]
                or binding.get("train_path") != runner_config["train_path"]
                or binding.get("train_sha256") != runner_config["train_sha256"]
                or (expected_role == "sealed_dev" and (
                    binding.get("dev_path") != runner_config["dev_path"]
                    or binding.get("dev_sha256") != runner_config["dev_sha256"]
                    or binding.get("round_id") != runner_config["round_id"]
                    or binding.get("lifecycle_root") != runner_config["lifecycle_root"]
                    or binding.get("controller_view_sha256")
                    != runner_config["controller_view_sha256"]))):
            raise ValueError("controller job differs from formal round binding")
    objective_bounds = _objective_label_delay_bounds(runner_config)
    candidate = workspace / request["candidate_name"]
    source = _read(candidate, 131_072)
    if hashlib.sha256(source).hexdigest() != request["candidate_sha256"]:
        raise ValueError("controller candidate changed before execution")
    train = _artifact(Path(runner_config["train_path"]), "train", runner_config["train_sha256"])
    if train["task_id"] != manifest["task_id"]:
        raise ValueError("controller execution task changed")
    if expected_role == "train_cv":
        fit_rows, evaluation_rows, split_audit = train_cv_split(
            train["rows"], evidence_class=runner_config["evidence_class"],
            label_delay_bounds_ms=objective_bounds)
    else:
        dev = _artifact(Path(runner_config["dev_path"]), "dev", runner_config["dev_sha256"])
        if (dev["task_id"] != manifest["task_id"]
                or dev["feature_names"] != train["feature_names"]):
            raise ValueError("sealed Dev execution task changed")
        fit_rows, evaluation_rows = train["rows"], dev["rows"]
        split_audit = validate_outer_dev(
            fit_rows, evaluation_rows, evidence_class=runner_config["evidence_class"],
            label_delay_bounds_ms=objective_bounds)
    evaluation = [{key: row[key] for key in PUBLIC_FIELDS} for row in evaluation_rows]
    packet = {"train": fit_rows, "evaluation": evaluation,
              "feature_names": train["feature_names"], "limits": {
                  "prediction_min": 0.0, "prediction_max": 1.0,
                  "fit_timeout_seconds": 60, "predict_timeout_seconds": 5,
                  "wall_seconds": 120, "max_request_bytes": 8 * 1024 * 1024}}
    validate_rows(packet["train"], packet["evaluation"], packet["feature_names"])
    labels = {row["row_id"]: row["target"] for row in evaluation_rows}
    output = Path(output).resolve()
    identifier(output.name)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    deployed = {name: path.read_text() for name, path in DEPLOYED.items()}
    deployed["public/candidate.py"] = source.decode()
    claim = {"schema": "market_controller_candidate_job_v1", "job_id": output.name,
             "execution_id": request["execution_id"], "session_id": manifest["session_id"],
             "experiment_id": manifest["experiment_id"], "task_id": manifest["task_id"],
             "request_sha256": digest(request), "runner_config_sha256": digest(runner_config),
             "packet_sha256": fingerprint(packet), "labels_sha256": digest(labels),
             "candidate_sha256": request["candidate_sha256"],
             "time_series_policy_sha256": policy_contract()["policy_sha256"],
             "split_audit_sha256": digest(split_audit),
             "evaluation_role": expected_role,
             "current_dev_used": expected_role == "sealed_dev",
             "deployed_hashes": {name: hashlib.sha256(text.encode()).hexdigest()
                                 for name, text in deployed.items()},
             "template": TEMPLATE, "ttl_seconds": TTL, "upper_usd": UPPER_USD,
             "budget_bucket": runner_config["budget_bucket"], "rates": RATES,
             "evidence_class": runner_config["evidence_class"],
             "future_test_used": False, "automatic_retry": False}
    fresh_json(output / "claim.json", claim)
    fresh_json(output / "request.json", request)
    fresh_json(output / "runner-config.json", runner_config)
    fresh_json(output / "packet.json", packet)
    fresh_json(output / "evaluation-labels.json", labels)
    fresh_json(output / "sources.json", {"deployed": deployed})
    fresh_json(output / "split-audit.json", split_audit)
    verify_job(output)
    return claim


def verify_job(root: Path):
    root = Path(root).resolve()
    claim, request, config, packet, labels, sources, split_audit = [
        _json(root / name) for name in
        ("claim.json", "request.json", "runner-config.json", "packet.json",
         "evaluation-labels.json", "sources.json", "split-audit.json")]
    role = claim.get("evaluation_role")
    if role not in {"train_cv", "sealed_dev"}:
        raise ValueError("unknown controller evaluation role")
    expected_schema = ("market_controller_runner_v1" if role == "train_cv"
                       else "market_controller_sealed_dev_runner_v1")
    if (claim.get("schema") != "market_controller_candidate_job_v1"
            or claim["job_id"] != root.name or claim["execution_id"] != request["execution_id"]
            or claim["request_sha256"] != digest(request) or claim["runner_config_sha256"] != digest(config)
            or claim["packet_sha256"] != fingerprint(packet) or claim["labels_sha256"] != digest(labels)
            or claim["candidate_sha256"] != request["candidate_sha256"]
            or claim.get("time_series_policy_sha256")
            != policy_contract()["policy_sha256"]
            or claim.get("split_audit_sha256") != digest(split_audit)
            or request.get("evaluation_role") != role
            or config.get("schema") != expected_schema
            or claim["current_dev_used"] != (role == "sealed_dev")
            or claim["future_test_used"] is not False or claim["automatic_retry"] is not False
            or claim["template"] != TEMPLATE or claim["ttl_seconds"] != TTL
            or claim["upper_usd"] != UPPER_USD or claim["rates"] != RATES):
        raise ValueError("controller candidate job changed")
    objective_bounds = _objective_label_delay_bounds(config)
    if role == "train_cv":
        train = _artifact(Path(config["train_path"]), "train", config["train_sha256"])
        expected_fit, expected_cv, expected_audit = train_cv_split(
            train["rows"], evidence_class=config["evidence_class"],
            label_delay_bounds_ms=objective_bounds)
    else:
        train = _artifact(Path(config["train_path"]), "train", config["train_sha256"])
        dev = _artifact(Path(config["dev_path"]), "dev", config["dev_sha256"])
        expected_fit, expected_cv = train["rows"], dev["rows"]
        expected_audit = validate_outer_dev(
            expected_fit, expected_cv, evidence_class=config["evidence_class"],
            label_delay_bounds_ms=objective_bounds)
    expected_evaluation = [{key: row[key] for key in PUBLIC_FIELDS}
                           for row in expected_cv]
    if (packet["train"] != expected_fit
            or packet["evaluation"] != expected_evaluation
            or split_audit != expected_audit):
        raise ValueError("controller time-series split changed")
    validate_rows(packet["train"], packet["evaluation"], packet["feature_names"])
    if set(labels) != {row["row_id"] for row in packet["evaluation"]}:
        raise ValueError("Train-CV labels do not match evaluation mask")
    deployed = sources.get("deployed")
    if not isinstance(deployed, dict) or set(deployed) != set(DEPLOYED) | {"public/candidate.py"}:
        raise ValueError("controller deployment changed")
    for name, text in deployed.items():
        if hashlib.sha256(text.encode()).hexdigest() != claim["deployed_hashes"].get(name):
            raise ValueError("controller deployed source hash changed")
        if name in DEPLOYED and text != DEPLOYED[name].read_text():
            raise ValueError("trusted controller runner source changed")
    if claim["deployed_hashes"]["public/candidate.py"] != claim["candidate_sha256"]:
        raise ValueError("controller candidate source changed")
    return claim, request, config, packet, labels, deployed


class ControllerCandidateE2B(BoundedMarketE2B):
    async def start(self, force_build):
        if force_build or self.creation_attempted or self._sandbox is not None:
            raise ValueError("no builds or duplicate controller sandbox creation")
        if self.network_policy.network_mode != NetworkMode.NO_NETWORK:
            raise ValueError("no-network controller task required")
        claim, _, config, _, _, _ = verify_job(self.control_root)
        from dotenv import dotenv_values
        from e2b import AsyncSandbox
        key = dotenv_values(config["env_file"]).get("E2B_API_KEY")
        if not key:
            raise ValueError("E2B credential unavailable to trusted controller runner")
        budget = PaidBudget(config["budget_path"])
        if budget.snapshot()["experiment_id"] != claim["experiment_id"]:
            raise ValueError("wrong controller experiment budget")
        budget.reserve(claim["job_id"], claim["budget_bucket"], UPPER_USD, "e2b", digest(claim))
        budget.dispatch(claim["job_id"])
        self.creation_attempted = True
        self._begin_metering(cpu_count=2, memory_mb=512)
        self._sandbox = await AsyncSandbox.create(template=TEMPLATE, timeout=TTL, secure=True,
            api_key=key, request_timeout=15, allow_internet_access=False,
            network={"allow_out": [], "deny_out": ["0.0.0.0/0"], "allow_public_traffic": False},
            lifecycle={"on_timeout": "kill", "auto_resume": False},
            metadata={"experiment_id": claim["experiment_id"], "job_id": claim["job_id"]})
        fresh_json(self.control_root / "sandbox.json", {"sandbox_id": self._sandbox.sandbox_id})
        info = await self._sandbox.get_info(request_timeout=15)
        fresh_json(self.control_root / "runtime.json", {"sandbox_id": self._sandbox.sandbox_id,
            "template_id": info.template_id, "cpu_count": info.cpu_count, "memory_mb": info.memory_mb,
            "started_at": info.started_at.isoformat(), "expiry_at": info.end_at.isoformat(),
            "envd_version": info.envd_version, "allow_internet_access": info.allow_internet_access})
        if (info.template_id != TEMPLATE or info.cpu_count != 2 or info.memory_mb != 512
                or info.allow_internet_access is not False
                or (info.end_at - info.started_at).total_seconds() > TTL + 1):
            raise ValueError("unexpected controller sandbox identity")
        await self.ensure_dirs(self._mount_targets(writable_only=True))


class ControllerCandidateAgent(BaseAgent):
    def __init__(self, *args, control_root, **kwargs):
        self.control_root = Path(control_root)
        super().__init__(*args, **kwargs)

    @staticmethod
    def name():
        return "market-controller-candidate"

    def version(self):
        return "1"

    async def setup(self, environment):
        _, _, _, packet, _, deployed = verify_job(self.control_root)
        sandbox = environment._sandbox
        result = await sandbox.commands.run(f"mkdir -m 700 {PRIVATE} && mkdir -m 755 {PUBLIC}",
                                            user="root", timeout=10)
        if result.exit_code != 0:
            raise ValueError("controller sandbox layout failed")
        for name, text in deployed.items():
            remote = (PRIVATE if name.startswith("private/") else PUBLIC) + "/" + name.split("/", 1)[1]
            await sandbox.files.write(remote, text, user="root", request_timeout=15)
        claim = verify_job(self.control_root)[0]
        await sandbox.files.write(PRIVATE + "/packet.json", canonical(packet), user="root", request_timeout=15)
        await sandbox.files.write(PRIVATE + "/input-claim.json", canonical({
            "packet_sha256": claim["packet_sha256"], "deployed_hashes": claim["deployed_hashes"]}),
            user="root", request_timeout=15)
        private = [name.split("/", 1)[1] for name in deployed if name.startswith("private/")]
        private += ["packet.json", "input-claim.json"]
        public = [name.split("/", 1)[1] for name in deployed if name.startswith("public/")]
        command = "chmod 600 " + " ".join(PRIVATE + "/" + name for name in private)
        command += " && chmod 444 " + " ".join(PUBLIC + "/" + name for name in public)
        result = await sandbox.commands.run(command, user="root", timeout=10)
        if result.exit_code != 0:
            raise ValueError("controller sandbox permissions failed")

    async def run(self, instruction, environment, context):
        sandbox = environment._sandbox
        verify_job(self.control_root)
        error_type = None
        try:
            result = await sandbox.commands.run(f"python3 -I {PRIVATE}/sandbox_prediction_runner.py",
                                                user="root", timeout=135)
            fresh_json(self.control_root / "command.json", {"exit_code": result.exit_code,
                       "stdout": result.stdout, "stderr": result.stderr})
            if result.exit_code != 0:
                error_type = "NonzeroExit"
        except Exception as error:
            terminal = terminal_nonzero_result(error)
            if terminal is not None:
                # E2B 2.x raises for an ordinary nonzero process exit.  Preserve
                # its stdout/stderr as terminal evidence so an early trusted-
                # runner failure can be diagnosed and a post-isolation
                # candidate failure can remain a candidate outcome.
                fresh_json(self.control_root / "command.json", terminal)
                error_type = "NonzeroExit"
            else:
                error_type = type(error).__name__
                fresh_json(self.control_root / "command-error.json", {"error_type": error_type})
        finally:
            collected = self.control_root / "collected"
            collected.mkdir(mode=0o700, exist_ok=False)
            missing = {}
            for name in OUTPUTS:
                try:
                    remote = PRIVATE + "/" + name
                    info = await sandbox.files.get_info(remote, user="root", request_timeout=5)
                    if info.size > 32 * 1024 * 1024 or info.symlink_target is not None:
                        raise ValueError("unbounded controller output")
                    raw = await sandbox.files.read(remote, format="bytes", user="root", request_timeout=5)
                    path = collected / name
                    path.parent.mkdir(mode=0o700, exist_ok=True)
                    with path.open("xb") as stream:
                        stream.write(raw)
                except Exception as error:
                    missing[name] = type(error).__name__
            fresh_json(self.control_root / "collection.json", {"missing_or_failed": missing})
        context.metadata = {"controller_candidate": True, "scored": False}
        if error_type or not (self.control_root / "collected/execution.json").is_file():
            raise ValueError("controller candidate did not complete; preserve outcome")


def terminal_nonzero_result(error):
    """Recover the terminal process result carried by E2B 2.x."""
    from e2b.sandbox.commands.command_handle import CommandExitException
    if not isinstance(error, CommandExitException):
        return None
    if (type(error.exit_code) is not int or error.exit_code == 0
            or not isinstance(error.stdout, str) or not isinstance(error.stderr, str)):
        raise ValueError("invalid E2B terminal command exception")
    return {"exit_code": error.exit_code, "stdout": error.stdout,
            "stderr": error.stderr}


def verify_and_score(root: Path) -> dict:
    from market_scoring import read_predictions
    claim, _, config, packet, labels, _ = verify_job(root)
    root = Path(root)
    if (root / "collected/failure.json").exists() or _json(root / "command.json")["exit_code"] != 0:
        raise ValueError("controller candidate worker failed")
    isolation = _json(root / "collected/isolation.json")
    if (set(isolation["checks"]) != ISOLATION_CHECKS
            or any(value is not True for value in isolation["checks"].values())
            or isolation.get("exit_code") != 0
            or isolation.get("probe_sha256")
            != claim["deployed_hashes"]["public/isolation_probe.py"]):
        raise ValueError("controller candidate isolation failed")
    predictions = read_predictions(root / "collected/predictions", train=packet["train"],
        evaluation=packet["evaluation"], feature_names=packet["feature_names"],
        candidate_sha256=claim["candidate_sha256"], prediction_min=0.0, prediction_max=1.0)
    prediction_sha256 = digest([
        {"row_id": row_id, "prediction": predictions[row_id]}
        for row_id in sorted(predictions)
    ])
    score_contract = (
        score_contract_from_objective(
            _json(Path(config["objective_contract_path"])),
            split="dev", evidence_class=claim["evidence_class"],
        )
        if claim["evidence_class"] == "formal_learning"
        else PolymarketScoreContract(
            split="dev", evidence_class=claim["evidence_class"]
        )
    )
    rows = [{"row_id": row["row_id"], "game_id": row["game_id"], "market_id": row["market_id"],
             "decision_ms": row["decision_ms"],
             "target_ms": row["decision_ms"] + score_contract.horizon_ms,
             "midpoint": row["features"]["mid"], "target_midpoint": labels[row["row_id"]]}
            for row in packet["evaluation"]]
    submissions = [{"row_id": row["row_id"], "status": "ok",
                    "prediction": predictions[row["row_id"]]} for row in packet["evaluation"]]
    score = score_polymarket(rows, submissions, score_contract)
    fresh_json(root / "score.json", score)
    cleanup = _json(root / "cleanup-01.json")
    if cleanup.get("kill_acknowledged") is not True:
        raise ValueError("controller sandbox cleanup not acknowledged")
    return {"evaluation_role": claim["evaluation_role"],
            "prediction_sha256": prediction_sha256,
            "primary": score["primary"], "paired_success_diagnostic": score["paired_success_diagnostic"],
            "calibration_auxiliary": score["calibration_auxiliary"],
            "temporal_robustness": score["temporal_robustness"],
            "population": score["population"], "coverage": score["coverage"],
            "score_sha256": digest(score), "claim_boundary": score["claim_boundary"]}


def verify_candidate_failure(root: Path) -> dict:
    """Verify a post-isolation candidate failure without turning it into a score."""
    claim = verify_job(root)[0]
    root = Path(root)
    cleanup = _json(root / "cleanup-01.json")
    if cleanup.get("kill_acknowledged") is not True:
        raise ValueError("controller sandbox cleanup not acknowledged")
    isolation = _json(root / "collected/isolation.json")
    if (set(isolation.get("checks", {})) != ISOLATION_CHECKS
            or any(value is not True for value in isolation["checks"].values())
            or isolation.get("exit_code") != 0
            or isolation.get("probe_sha256")
            != claim["deployed_hashes"]["public/isolation_probe.py"]):
        raise ValueError("failure occurred before candidate isolation was proved")
    failure = _json(root / "collected/failure.json")
    if (set(failure) != {"error_type", "scored"} or failure["scored"] is not False
            or not isinstance(failure["error_type"], str) or not failure["error_type"]):
        raise ValueError("invalid candidate failure receipt")
    diagnostic = _json(root / "collected/candidate-stderr.json")
    if (set(diagnostic) != {"origin", "bytes", "sha256", "encoding", "text",
                            "truncated", "independent_diagnosis"}
            or diagnostic.get("origin") != "candidate_controlled_stderr"
            or type(diagnostic.get("bytes")) is not int
            or not 0 <= diagnostic["bytes"] <= 10 * 1024 * 1024
            or not isinstance(diagnostic.get("sha256"), str)
            or len(diagnostic["sha256"]) != 64
            or not isinstance(diagnostic.get("text"), str)
            or diagnostic.get("truncated") is not False
            or diagnostic.get("independent_diagnosis") is not False):
        raise ValueError("invalid candidate diagnostic receipt")
    command_path = root / "command.json"
    command_error_path = root / "command-error.json"
    if command_path.exists() and command_error_path.exists():
        raise ValueError("ambiguous duplicate command receipts")
    if command_path.exists():
        command = _json(command_path)
        if command.get("exit_code") == 0:
            raise ValueError("successful worker cannot be relabelled as candidate failure")
    elif command_error_path.exists():
        # E2B may raise CommandExitException instead of returning a nonzero
        # command object.  The independently collected sandbox failure and
        # isolation receipts distinguish that candidate outcome from a setup
        # or transport failure.
        command_error = _json(command_error_path)
        if (set(command_error) != {"error_type"}
                or not isinstance(command_error["error_type"], str)
                or not command_error["error_type"]):
            raise ValueError("invalid command exception receipt")
    else:
        raise ValueError("candidate failure lacks terminal command evidence")
    return {"candidate_sha256": claim["candidate_sha256"],
            "failure_code": failure["error_type"], "scored": False,
            "future_test_used": False, "automatic_retry": False,
            "candidate_diagnostic": {
                "origin": diagnostic["origin"],
                "text_prefix": diagnostic["text"][:32_768],
                "original_bytes": diagnostic["bytes"],
                "original_sha256": diagnostic["sha256"],
                "truncated_for_controller": len(diagnostic["text"]) > 32_768,
                "independent_diagnosis": False,
                "trusted_for_scoring": False,
            }}


async def run_job(root: Path, budget_path: Path, env_file: Path) -> dict:
    root = Path(root).resolve()
    claim, _, config, _, _, _ = verify_job(root)
    if (Path(budget_path).resolve() != Path(config["budget_path"]).resolve()
            or Path(env_file).resolve() != Path(config["env_file"]).resolve()):
        raise ValueError("controller runner credential/budget path changed")
    config = TrialConfig(task=TaskConfig(path=TASK), trial_name=root.name, trials_dir=root / "harbor",
        agent=AgentConfig(import_path="controller_candidate_harbor:ControllerCandidateAgent",
                          override_timeout_sec=160, override_setup_timeout_sec=45,
                          kwargs={"control_root": str(root)}),
        environment=EnvironmentConfig(import_path="controller_candidate_harbor:ControllerCandidateE2B",
            force_build=False, delete=True, kwargs={"control_root": str(root),
                "budget_path": str(Path(budget_path).resolve()), "env_file": str(Path(env_file).resolve())}),
        verifier=VerifierConfig(disable=True))
    fresh_json(root / "harbor-config.json", config.model_dump(mode="json"))
    trial = None
    try:
        trial = await Trial.create(config)
        result = await asyncio.wait_for(trial.run(), timeout=175)
        if result.exception_info is not None:
            raise ValueError("controller Harbor trial failed; no retry")
    finally:
        if trial is not None and trial.agent_environment._sandbox is not None:
            await asyncio.shield(trial.agent_environment.stop(delete=True))
    summary = verify_and_score(root)
    fresh_json(root / "assessment.json", summary)
    return summary
