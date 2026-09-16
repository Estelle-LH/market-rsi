"""General development worker composition; live admission remains unavailable.

Both prepared fit/predict and inspection modes use Harbor/E2B. This is NOT a
fixture-to-production bypass: require_admission checks an immutable receipt from
an independent source/task/phase/deadline supervisor. There is no CLI switch or
caller-provided boolean to turn it on. Unit tests mock infrastructure only.
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

from inspection_stream import json_bound, verify_packet
from market_harbor import BoundedMarketE2B, ISOLATION_CHECKS, PRIVATE, PUBLIC, RATES, TEMPLATE
from market_rsi import canonical, digest, file_hash, fresh_json, identifier
from market_scoring import read_predictions
from paid_budget import PaidBudget
from prediction_stream import encoded, fingerprint, validate_rows
from trial_inputs import execution_profile
from worker_receipts import read_regular


HERE = Path(__file__).resolve().parent
TASK = HERE / "tasks/development-worker"
TTL, UPPER_USD = 240, "0.10"
COMMON = {"private/prediction_stream.py": HERE / "prediction_stream.py",
          "private/diagnostic_channel.py": HERE / "diagnostic_channel.py",
          "private/sandbox_development_runner.py": HERE / "sandbox_development_runner.py",
          "public/isolation_probe.py": HERE / "fixtures/harbor-stream-01/isolation_probe.py"}
MODE_SOURCES = {
    "fit_predict": {"public/prediction_candidate_server.py": HERE / "prediction_candidate_server.py"},
    "inspect": {"private/inspection_stream.py": HERE / "inspection_stream.py",
                "public/inspection_candidate_server.py": HERE / "inspection_candidate_server.py"}}
DEPENDENCIES = ("market_harbor.py", "trial_inputs.py", "worker_receipts.py", "inspection_stream.py", "market_scoring.py")
OUTPUTS = ("isolation.json", "execution.json", "failure.json", "protocol.json", "candidate-stderr.log", "candidate-diagnostic.json")
PREDICTIONS = ("predictions/claim.json", "predictions/predictions.jsonl", "predictions/complete.json")


def require_admission(root):
    from scientific_admission import owning_runner, verify_installed_admission
    runner = owning_runner(root)
    receipt = verify_installed_admission(runner)
    path = Path(root).absolute()
    claim_path = path / "claim.json"
    if claim_path.is_file():
        claim = _json(claim_path)
        # Development claims bind the experiment directly. Research and coding
        # claims bind it inside their immutable audit packet. Both are admitted
        # job roots, so validate the declared location instead of treating a
        # missing top-level field as a cross-experiment claim.
        audit = claim.get("audit")
        claim_experiment = claim.get("experiment_id")
        if claim_experiment is None and isinstance(audit, dict):
            claim_experiment = audit.get("experiment_id")
        if claim_experiment != receipt["experiment_id"]:
            raise ValueError("development job belongs to another admitted experiment")
    return receipt


def _json(path):
    return json.loads(read_regular(path))


def prepare_job(bundle, root):
    """Persist an exclusive execution proposal; this does not admit or run it."""
    binding, packet = bundle["binding"], bundle["packet"]
    if (fingerprint(binding) != bundle["binding_sha256"] or binding["mode"] not in MODE_SOURCES
            or fingerprint(packet) != binding["execution_packet_sha256"]
            or hashlib.sha256(bundle["candidate_source"].encode()).hexdigest() != binding["candidate_sha256"]
            or fingerprint(bundle["runtime"]) != binding["runtime_sha256"]):
        raise ValueError("development bundle changed before preparation")
    execution_profile(bundle["runtime"])
    bundle["research_receipts"].revalidate()
    bundle["coding_receipts"].revalidate()
    root = Path(root).absolute()
    identifier(root.name)
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    sources = {**COMMON, **MODE_SOURCES[binding["mode"]]}
    deployed = {name: read_regular(path).decode() for name, path in sources.items()}
    deployed["public/candidate.py"] = bundle["candidate_source"]
    claim = {"schema": "market_development_claim_v1", "job_id": root.name,
        "experiment_id": binding["owner"]["experiment_id"], "mode": binding["mode"],
        "phase": binding["owner"]["phase"], "binding_sha256": fingerprint(binding),
        "packet_sha256": fingerprint(packet), "runtime_sha256": fingerprint(bundle["runtime"]),
        "deployed_hashes": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in deployed.items()},
        "worker_sha256": file_hash(__file__), "dependencies": {k: file_hash(HERE / k) for k in DEPENDENCIES},
        "task_hashes": {n: file_hash(TASK / n) for n in ("instruction.md", "task.toml", "environment/Dockerfile")},
        "template": TEMPLATE, "ttl_seconds": TTL, "upper_usd": UPPER_USD, "rates": RATES,
        "scientific_admission": False, "research_result": False}
    fresh_json(root / "claim.json", claim)
    fresh_json(root / "binding.json", binding)
    fresh_json(root / "packet.json", packet)
    fresh_json(root / "declared-runtime.json", bundle["runtime"])
    fresh_json(root / "sources.json", {"deployed": deployed, "worker": Path(__file__).read_text()})
    return claim


def verify_job(root):
    root = Path(root).absolute()
    claim, binding, packet, runtime, archived = [_json(root / n) for n in
        ("claim.json", "binding.json", "packet.json", "declared-runtime.json", "sources.json")]
    if (claim["schema"] != "market_development_claim_v1" or claim["job_id"] != root.name
            or claim["mode"] not in MODE_SOURCES or claim["scientific_admission"] is not False
            or claim["binding_sha256"] != fingerprint(binding) or claim["packet_sha256"] != fingerprint(packet)
            or claim["runtime_sha256"] != fingerprint(runtime) or binding["mode"] != claim["mode"]
            or binding["execution_packet_sha256"] != claim["packet_sha256"]
            or binding["runtime_sha256"] != claim["runtime_sha256"]
            or binding["owner"]["experiment_id"] != claim["experiment_id"] or binding["owner"]["phase"] != claim["phase"]
            or claim["phase"] not in {"learning", "transfer"}
            or claim["worker_sha256"] != file_hash(__file__) or claim["template"] != TEMPLATE
            or claim["ttl_seconds"] != TTL or claim["upper_usd"] != UPPER_USD or claim["rates"] != RATES):
        raise ValueError("development claim/source/input mismatch")
    for name in DEPENDENCIES:
        if claim["dependencies"][name] != file_hash(HERE / name):
            raise ValueError("development dependency changed")
    if set(claim["task_hashes"]) != {"instruction.md", "task.toml", "environment/Dockerfile"}:
        raise ValueError("complete Harbor task source commitments required")
    for name, sha in claim["task_hashes"].items():
        if name not in {"instruction.md", "task.toml", "environment/Dockerfile"} or file_hash(TASK / name) != sha:
            raise ValueError("Harbor task changed")
    sources = {**COMMON, **MODE_SOURCES[claim["mode"]]}
    if hashlib.sha256(archived["worker"].encode()).hexdigest() != claim["worker_sha256"]:
        raise ValueError("archived worker source changed")
    if set(archived["deployed"]) != set(sources) | {"public/candidate.py"} or set(claim["deployed_hashes"]) != set(archived["deployed"]):
        raise ValueError("unexpected deployment file")
    for name, source in archived["deployed"].items():
        if hashlib.sha256(source.encode()).hexdigest() != claim["deployed_hashes"][name]:
            raise ValueError("archived deployment bytes changed")
        if name in sources and source != read_regular(sources[name]).decode():
            raise ValueError("deployed runner source changed")
    if claim["deployed_hashes"]["public/candidate.py"] != binding["candidate_sha256"]:
        raise ValueError("candidate differs from completed code job")
    for receipt_key in ("research_receipts", "coding_receipts"):
        receipts = binding[receipt_key]
        if digest({k: v for k, v in receipts.items() if k != "sha256"}) != receipts["sha256"]:
            raise ValueError("completed receipt commitment changed")
        for path, sha in receipts["files"].items():
            if hashlib.sha256(read_regular(path)).hexdigest() != sha:
                raise ValueError("completed worker evidence changed")
        if any(Path(p).exists() or Path(p).is_symlink() for p in receipts["absent_paths"]):
            raise ValueError("upstream worker has a failure receipt")
    profile = execution_profile(runtime)
    if claim["mode"] == "fit_predict":
        if set(packet) != {"train", "evaluation", "feature_names", "limits"}:
            raise ValueError("prediction payload contains unexpected fields")
        validate_rows(packet["train"], packet["evaluation"], packet["feature_names"])
        limits = dict(profile["prediction"], prediction_min=runtime["prediction_min"], prediction_max=runtime["prediction_max"])
        if packet["limits"] != limits or packet["feature_names"] != runtime["feature_names"]:
            raise ValueError("prediction execution profile changed")
    else:
        verify_packet(packet, {"payload", "audit"})
        if (packet["audit"]["limits"] != profile["inspection"]
                or packet["audit"]["action"] != binding["action"]
                or any(packet["audit"][k] != v for k, v in binding["owner"].items())
                or packet["audit"]["payload_sha256"] != fingerprint(packet["payload"])):
            raise ValueError("inspection execution profile changed")
    return claim, packet, runtime, archived["deployed"]


class DevelopmentE2B(BoundedMarketE2B):
    """Reuse the verified exact cleanup owner, with a separately gated start."""
    def _paid_key(self):
        from dotenv import dotenv_values
        return dotenv_values(self.env_file).get("E2B_API_KEY")

    async def start(self, force_build):
        if force_build or self.creation_attempted or self._sandbox is not None:
            raise ValueError("no builds or duplicate creation")
        require_admission(self.control_root)  # Before credentials, reservation or any network.
        claim, _, _, _ = verify_job(self.control_root)
        if self.network_policy.network_mode != NetworkMode.NO_NETWORK:
            raise ValueError("no-network task required")
        from e2b import AsyncSandbox
        key = self._paid_key()
        if not key:
            raise ValueError("E2B key unavailable")
        budget = PaidBudget(self.budget_path)
        if budget.snapshot()["experiment_id"] != claim["experiment_id"]:
            raise ValueError("wrong experiment ledger")
        require_admission(self.control_root)
        bucket = "final" if claim["phase"] == "transfer" else "learning"
        budget.reserve(self.control_root.name, bucket, UPPER_USD, "e2b", digest(claim))
        budget.dispatch(self.control_root.name)
        self.creation_attempted = True
        self._begin_metering(cpu_count=2, memory_mb=512)
        self._sandbox = await AsyncSandbox.create(template=TEMPLATE, timeout=TTL, secure=True,
            api_key=key, request_timeout=15, allow_internet_access=False,
            network={"allow_out": [], "deny_out": ["0.0.0.0/0"], "allow_public_traffic": False},
            lifecycle={"on_timeout": "kill", "auto_resume": False},
            metadata={"experiment_id": claim["experiment_id"], "job_id": self.control_root.name})
        fresh_json(self.control_root / "sandbox.json", {"sandbox_id": self._sandbox.sandbox_id})
        info = await self._sandbox.get_info(request_timeout=15)
        fresh_json(self.control_root / "runtime.json", {"sandbox_id": self._sandbox.sandbox_id,
            "template_id": info.template_id, "cpu_count": info.cpu_count, "memory_mb": info.memory_mb,
            "started_at": info.started_at.isoformat(), "expiry_at": info.end_at.isoformat(),
            "envd_version": info.envd_version, "allow_internet_access": info.allow_internet_access})
        if (info.template_id != TEMPLATE or info.cpu_count != 2 or info.memory_mb != 512
                or info.allow_internet_access is not False
                or (info.end_at - info.started_at).total_seconds() > TTL + 1):
            raise ValueError("unexpected sandbox identity or lifetime")
        await self.ensure_dirs(self._mount_targets(writable_only=True))


def terminal_nonzero_result(error):
    """Recover the exact terminal result carried by E2B 2.x.

    E2B raises CommandExitException for a completed nonzero command. That is a
    candidate outcome, not an ambiguous transport failure. Other exceptions
    remain command-error claims and must not be inferred as terminal.
    """
    from e2b.sandbox.commands.command_handle import CommandExitException
    if not isinstance(error, CommandExitException):
        return None
    if (type(error.exit_code) is not int or error.exit_code == 0
            or not isinstance(error.stdout, str) or not isinstance(error.stderr, str)):
        raise ValueError("invalid E2B terminal command exception")
    return {"exit_code": error.exit_code, "stdout": error.stdout, "stderr": error.stderr}


class DevelopmentAgent(BaseAgent):
    def __init__(self, *args, control_root, **kwargs):
        self.control_root = Path(control_root)
        super().__init__(*args, **kwargs)

    @staticmethod
    def name():
        return "market-development-worker"

    def version(self):
        return "1"

    async def setup(self, environment):
        require_admission(self.control_root)
        claim, packet, runtime, deployed = verify_job(self.control_root)
        sb = environment._sandbox
        if sb is None:
            raise RuntimeError("sandbox missing")
        result = await sb.commands.run(f"mkdir -m 700 {PRIVATE} && mkdir -m 755 {PUBLIC}", user="root", timeout=10)
        if result.exit_code != 0:
            raise ValueError("exclusive sandbox layout creation failed")
        for name, text in deployed.items():
            remote = (PRIVATE if name.startswith("private/") else PUBLIC) + "/" + name.split("/", 1)[1]
            await sb.files.write(remote, text, user="root", request_timeout=15)
        await sb.files.write(PRIVATE + "/packet.json", canonical(packet), user="root", request_timeout=15)
        await sb.files.write(PRIVATE + "/input-claim.json", canonical({"packet_sha256": claim["packet_sha256"],
            "deployed_hashes": claim["deployed_hashes"], "mode": claim["mode"]}), user="root", request_timeout=15)
        # Probe installed versions without importing any candidate or third-party
        # package. The names are JSON data on stdin, never shell fragments.
        await sb.files.write(PRIVATE + "/libraries.json", canonical(runtime["libraries"]), user="root", request_timeout=15)
        version_code = "import json,platform,importlib.metadata; names=json.load(open('" + PRIVATE + "/libraries.json')); print(json.dumps({n:platform.python_version() if n=='python' else importlib.metadata.version(n) for n in names}))"
        import shlex
        result = await sb.commands.run("python3 -I -c " + shlex.quote(version_code), user="root", timeout=10)
        actual = json.loads(result.stdout) if result.exit_code == 0 else None
        fresh_json(self.control_root / "libraries.json", {"expected": runtime["libraries"], "actual": actual,
                                                          "exit_code": result.exit_code})
        if actual != runtime["libraries"]:
            raise ValueError("declared runtime libraries not available; no downloads/fallback")
        private = [n.split("/", 1)[1] for n in deployed if n.startswith("private/")]
        private += ["packet.json", "input-claim.json", "libraries.json"]
        public = [n.split("/", 1)[1] for n in deployed if n.startswith("public/")]
        cmd = "chmod 600 " + " ".join(PRIVATE + "/" + n for n in private)
        cmd += " && chmod 444 " + " ".join(PUBLIC + "/" + n for n in public)
        result = await sb.commands.run(cmd, user="root", timeout=10)
        if result.exit_code != 0:
            raise ValueError("sandbox file permissions failed")

    async def run(self, instruction, environment, context):
        require_admission(self.control_root)
        claim, _, _, _ = verify_job(self.control_root)
        sb, error_type = environment._sandbox, None
        runner = "sandbox_development_runner.py"
        try:
            result = await sb.commands.run(f"python3 -I {PRIVATE}/{runner}", user="root", timeout=135)
            fresh_json(self.control_root / "command.json", {"exit_code": result.exit_code,
                       "stdout": result.stdout, "stderr": result.stderr})
            if result.exit_code != 0:
                error_type = "NonzeroExit"
        except Exception as error:
            terminal = terminal_nonzero_result(error)
            if terminal is None:
                error_type = type(error).__name__
                fresh_json(self.control_root / "command-error.json", {"error_type": error_type})
            else:
                error_type = "NonzeroExit"
                fresh_json(self.control_root / "command.json", terminal)
        finally:
            collected = self.control_root / "collected"
            collected.mkdir(mode=0o700, exist_ok=False)
            missing = {}
            names = OUTPUTS + (PREDICTIONS if claim["mode"] == "fit_predict" else ())
            for name in names:
                try:
                    remote = PRIVATE + "/" + name
                    info = await sb.files.get_info(remote, user="root", request_timeout=5)
                    if info.size > 32 * 1024 * 1024 or info.symlink_target is not None:
                        raise ValueError("unbounded or symlink output")
                    raw = await sb.files.read(remote, format="bytes", user="root", request_timeout=5)
                    if len(raw) > 32 * 1024 * 1024:
                        raise ValueError("output grew past limit")
                    path = collected / name
                    path.parent.mkdir(mode=0o700, exist_ok=True)
                    with path.open("xb") as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
                except Exception as error:
                    missing[name] = type(error).__name__
            fresh_json(self.control_root / "collection.json", {"missing_or_failed": missing, "scored": False})
        context.metadata = {"mode": claim["mode"], "scored": False, "scientific_admission": False}
        if error_type or not (collected / "execution.json").is_file():
            raise ValueError("development execution incomplete; preserve available outputs")


def verify_outputs(root):
    claim, packet, runtime, _ = verify_job(root)
    root = Path(root)
    if (root / "collected/failure.json").exists():
        raise ValueError("worker failure cannot become a result")
    if _json(root / "command.json")["exit_code"] != 0:
        raise ValueError("worker command failed")
    missing = _json(root / "collection.json")["missing_or_failed"]
    if set(missing) - {"failure.json"}:
        raise ValueError("required worker receipts were not collected")
    isolation = _json(root / "collected/isolation.json")
    if (set(isolation["checks"]) != ISOLATION_CHECKS or any(v is not True for v in isolation["checks"].values())
            or isolation["exit_code"] != 0
            or isolation["probe_sha256"] != claim["deployed_hashes"]["public/isolation_probe.py"]):
        raise ValueError("independent pre-import isolation not verified")
    library = _json(root / "libraries.json")
    if library != {"expected": runtime["libraries"], "actual": runtime["libraries"], "exit_code": 0}:
        raise ValueError("runtime library read-back failed")
    from diagnostic_channel import stderr_receipt
    diagnostic = stderr_receipt(root / "collected/candidate-stderr.log")
    if diagnostic != _json(root / "collected/candidate-diagnostic.json"):
        raise ValueError("candidate-only diagnostic receipt mismatch")
    execution = _json(root / "collected/execution.json")
    if execution["scored"] is not False:
        raise ValueError("candidate execution cannot score itself")
    if claim["mode"] == "fit_predict":
        predictions = read_predictions(root / "collected/predictions", train=packet["train"], evaluation=packet["evaluation"],
            feature_names=packet["feature_names"], candidate_sha256=claim["deployed_hashes"]["public/candidate.py"],
            prediction_min=packet["limits"]["prediction_min"], prediction_max=packet["limits"]["prediction_max"])
        if execution["complete"] != _json(root / "collected/predictions/complete.json"):
            raise ValueError("prediction completion read-back mismatch")
        protocol = _json(root / "collected/protocol.json")["events"]
        bodies = [{"type": "fit", "features": packet["feature_names"], "train": packet["train"]}]
        bodies += [{"type": "predict", "row": row} for row in packet["evaluation"]]
        if len(protocol) != len(bodies) * 2:
            raise ValueError("prediction protocol is incomplete")
        for i, body in enumerate(bodies):
            sent, received = protocol[2 * i:2 * i + 2]
            if sent["type"] != "request" or received["type"] != "response":
                raise ValueError("prediction protocol order changed")
            raw = received["raw"]
            if not raw.endswith("\n") or len(raw.splitlines()) != 1 or len(raw.encode()) > 16384:
                raise ValueError("prediction response is incomplete/unbounded")
            answer = json.loads(raw)
            nonce = answer.get("request_id")
            if not isinstance(nonce, str) or len(nonce) != 32 or any(c not in "0123456789abcdef" for c in nonce):
                raise ValueError("invalid prediction nonce")
            request = dict(body, request_id=nonce)
            expected = {"type": "fitted", "request_id": nonce} if i == 0 else {
                "type": "prediction", "request_id": nonce, "row_id": body["row"]["row_id"],
                "prediction": predictions[body["row"]["row_id"]]}
            if (answer != expected or sent["request_sha256"] != fingerprint(request)
                    or sent["request_bytes"] != len(encoded(request)) + 1
                    or len(encoded(request)) + 1 > packet["limits"]["max_request_bytes"]):
                raise ValueError("prediction protocol does not match committed inputs/outputs")
        result = {"predictions": predictions, "diagnostic": None}
    else:
        inspected = execution["inspection"]
        protocol = _json(root / "collected/protocol.json")["events"]
        if len(protocol) != 2 or protocol[0]["type"] != "request" or protocol[1]["type"] != "response":
            raise ValueError("inspection must have exactly one recorded exchange")
        raw = protocol[1]["raw"]
        if not raw.endswith("\n") or len(raw.splitlines()) != 1:
            raise ValueError("incomplete/multiple inspection responses")
        response = json.loads(raw)
        if set(response) != {"type", "request_id", "diagnostic"} or response["type"] != "inspection":
            raise ValueError("unexpected inspection response fields")
        nonce = response["request_id"]
        if not isinstance(nonce, str) or len(nonce) != 32 or any(c not in "0123456789abcdef" for c in nonce):
            raise ValueError("invalid recorded inspection nonce")
        request = {"type": "inspect", "request_id": nonce, **packet["payload"]}
        limits = packet["audit"]["limits"]
        json_bound(response["diagnostic"], max_nodes=limits["max_json_nodes"], max_depth=limits["max_json_depth"])
        expected = {"audit": packet["audit"], "request_sha256": fingerprint(request), "response_sha256": fingerprint(response),
            "diagnostic": response["diagnostic"], "origin": "candidate_code_untrusted_diagnostic",
            "independent_score": None, "scored": False, "scientific_admission": False, "logical_exchanges": 1}
        if (inspected != expected or protocol[0]["request_sha256"] != fingerprint(request)
                or protocol[0]["request_bytes"] != len(encoded(request)) + 1
                or len(encoded(request)) + 1 > limits["max_request_bytes"]
                or len(raw.encode()) > limits["max_response_bytes"]):
            raise ValueError("inspection read-back input/response mismatch")
        result = {"predictions": None, "diagnostic": inspected}
    return dict(result, candidate_stderr=diagnostic, execution_verified=True,
                scientific_admission=False, scored=False, market_score=None)


def trial_config(root, budget_path, env_file):
    return TrialConfig(task=TaskConfig(path=TASK), trial_name=Path(root).name, trials_dir=Path(root) / "harbor",
        agent=AgentConfig(import_path="development_harbor:DevelopmentAgent", override_timeout_sec=200,
                          override_setup_timeout_sec=35, kwargs={"control_root": str(root)}),
        environment=EnvironmentConfig(import_path="development_harbor:DevelopmentE2B", force_build=False, delete=True,
            kwargs={"control_root": str(root), "budget_path": str(budget_path), "env_file": str(env_file)}),
        verifier=VerifierConfig(disable=True))


async def run_development(root, budget_path, env_file):
    require_admission(root)
    root = Path(root).absolute()
    verify_job(root)
    config = trial_config(root, budget_path, env_file)
    fresh_json(root / "harbor-config.json", config.model_dump(mode="json"))
    trial = None
    try:
        trial = await Trial.create(config)
        result = await asyncio.wait_for(trial.run(), timeout=235)
        if result.exception_info is not None:
            raise ValueError("Harbor development trial failed; no retry")
        assessment = verify_outputs(root)
        if _json(root / "cleanup-01.json")["kill_acknowledged"] is not True:
            raise ValueError("exact cleanup not acknowledged")
        fresh_json(root / "assessment.json", assessment)
        return assessment
    except Exception as error:
        fresh_json(root / "failure.json", {"error_type": type(error).__name__, "automatic_retry": False, "scored": False})
        raise
    finally:
        if trial is not None and trial.agent_environment._sandbox is not None:
            await asyncio.shield(trial.agent_environment.stop(delete=True))
