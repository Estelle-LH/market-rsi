"""Bounded Harbor/E2B sequential-worker integration, initially fixture-only.

No market admission path exists here yet. The only live entry point builds the
specific human-authored fixture; it cannot load real data by relabeling a flag.
The installed Harbor package is not patched or replaced. Its trial lifecycle
uses this project-local E2B subclass to prohibit image builds, duplicate creation
and the stock 24-hour sandbox lifetime.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import time

from harbor.agents.base import BaseAgent
from harbor.environments.e2b import E2BEnvironment
from harbor.models.task.config import NetworkMode
from harbor.models.trial.config import (AgentConfig, EnvironmentConfig, TaskConfig,
                                       TrialConfig, VerifierConfig)
from harbor.trial.trial import Trial

from market_rsi import canonical, digest, file_hash, fresh_json, identifier
from paid_budget import PaidBudget
from prediction_stream import fingerprint, validate_rows


HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "harbor-stream-01"
TEMPLATE = "rki5dems9wqfm4r03t7g"  # Actual base template reported in the earlier preflight.
TTL = 180
UPPER_USD = "0.10"
PRIVATE = "/root/market-rsi-private"
PUBLIC = "/tmp/market-rsi-public"
RATES = {"vcpu_second": "0.000014", "gib_second": "0.0000045",
         "source": "https://e2b.dev/pricing", "checked_utc_date": "2026-09-07"}
SOURCES = {"private/sandbox_prediction_runner.py": HERE / "sandbox_prediction_runner.py",
           "private/prediction_stream.py": HERE / "prediction_stream.py",
           "private/diagnostic_channel.py": HERE / "diagnostic_channel.py",
           "public/prediction_candidate_server.py": HERE / "prediction_candidate_server.py",
           "public/candidate.py": FIXTURE / "candidate.py",
           "public/isolation_probe.py": FIXTURE / "isolation_probe.py"}
OUTPUTS = ("isolation.json", "execution.json", "failure.json", "protocol.json",
           "candidate-stderr.json",
           "predictions/claim.json", "predictions/predictions.jsonl", "predictions/complete.json")
ISOLATION_CHECKS = {"unprivileged", "no_groups", "no_new_privileges", "only_loopback", "network_blocked",
                    "private_read_denied", "private_write_denied", "public_write_denied", "provider_keys_absent"}


def fixture_packet():
    def row(name, day, x, target=None):
        r = {"row_id": name, "game_id": f"fixture-game-{day}", "market_id": f"fixture-market-{day}",
             "decision_ms": day * 86400000 + int((x + 1) * 1000),
             "feature_available_ms": day * 86400000, "features": {"x": x}}
        if target is not None:
            r.update(target=target, label_available_ms=r["decision_ms"] + 60000)
        return r
    return {"train": [row("train-0", 1, -0.1, -0.1), row("train-1", 1, 0.1, 0.1)],
            "evaluation": [row(f"eval-{i}", 2, x) for i, x in enumerate([-0.25, 0, 0.25])],
            "feature_names": ["x"], "limits": {"prediction_min": -1, "prediction_max": 1,
                "fit_timeout_seconds": 5, "predict_timeout_seconds": 2, "wall_seconds": 15,
                "max_request_bytes": 8 * 1024 * 1024}}


def verify_claim(root):
    root = Path(root)
    claim = json.loads((root / "claim.json").read_text())
    packet = json.loads((root / "packet.json").read_text())
    if (claim["evidence_class"] != "synthetic-worker-integration" or claim["research_result"] is not False
            or claim["job_id"] != root.name or claim["packet_sha256"] != fingerprint(packet)
            or fingerprint(packet) != fingerprint(fixture_packet()) or claim["ttl_seconds"] != TTL
            or claim["template"] != TEMPLATE or claim["upper_usd"] != UPPER_USD):
        raise ValueError("only the exact predeclared fixture is currently admitted")
    validate_rows(packet["train"], packet["evaluation"], packet["feature_names"])
    for name, path in SOURCES.items():
        if path.is_symlink() or file_hash(path) != claim["deployed_hashes"][name]:
            raise ValueError("deployment source changed")
    if file_hash(__file__) != claim["worker_sha256"]:
        raise ValueError("worker changed after permanent claim")
    return claim, packet


class BoundedMarketE2B(E2BEnvironment):
    def __init__(self, *args, control_root, budget_path, env_file, **kwargs):
        self.control_root, self.budget_path, self.env_file = Path(control_root), Path(budget_path), Path(env_file)
        self.creation_attempted = False
        self.cleanup_calls = 0
        self._metering_started_monotonic = None
        self._metering_started_utc = None
        self._metering_cpu_count = None
        self._metering_memory_mb = None
        super().__init__(*args, **kwargs)

    def _begin_metering(self, *, cpu_count: int, memory_mb: int) -> None:
        """Start one conservative host-side E2B usage interval before create."""
        if (getattr(self, "_metering_started_monotonic", None) is not None
                or type(cpu_count) is not int or cpu_count <= 0
                or type(memory_mb) is not int or memory_mb <= 0):
            raise ValueError("invalid or duplicate E2B metering start")
        self._metering_started_monotonic = time.monotonic()
        self._metering_started_utc = datetime.now(timezone.utc).isoformat()
        self._metering_cpu_count = cpu_count
        self._metering_memory_mb = memory_mb

    def _terminal_metering(self) -> tuple[str, dict] | None:
        """Price an acknowledged create-to-kill interval at the frozen rates.

        The interval starts before the create request and rounds up to a whole
        second, so it is a conservative usage estimate.  It is still not a
        provider invoice; a later invoice may replace it in PaidBudget.
        """
        started = getattr(self, "_metering_started_monotonic", None)
        if started is None:
            return None
        seconds = max(1, math.ceil(time.monotonic() - started))
        cpu_count = self._metering_cpu_count
        memory_mb = self._metering_memory_mb
        per_second = (
            Decimal(cpu_count) * Decimal(RATES["vcpu_second"])
            + (Decimal(memory_mb) / Decimal(1024)) * Decimal(RATES["gib_second"])
        )
        cost = Decimal(seconds) * per_second
        receipt = {
            "terminal": True,
            "provider": "e2b",
            "cost_basis": (
                "trusted host interval from before create to acknowledged kill, "
                "rounded up to one-second units and priced at frozen public rates; not invoice"
            ),
            "started_before_create_utc": self._metering_started_utc,
            "kill_acknowledged_utc": datetime.now(timezone.utc).isoformat(),
            "billed_seconds_upper": seconds,
            "cpu_count": cpu_count,
            "memory_mb": memory_mb,
            "rates": RATES,
            "metered_usd": str(cost),
        }
        return str(cost), receipt

    @classmethod
    def preflight(cls):
        # Credentials are read only by start(), from the host-owned path. Never
        # require exporting the key into Harbor's agent/candidate environment.
        return None

    async def _apply_network_policy(self, network_policy):
        if network_policy.network_mode != NetworkMode.NO_NETWORK:
            raise ValueError("market fixture cannot enable network")
        # Sandbox creation has already denied traffic; no policy relaxation.

    async def start(self, force_build):
        if force_build or self.creation_attempted or self._sandbox is not None:
            raise ValueError("no template build or duplicate sandbox creation")
        if self.network_policy.network_mode != NetworkMode.NO_NETWORK:
            raise ValueError("no-network task required")
        claim, _ = verify_claim(self.control_root)
        from dotenv import dotenv_values
        from e2b import AsyncSandbox
        key = dotenv_values(self.env_file).get("E2B_API_KEY")
        if not key:
            raise ValueError("E2B credential unavailable")
        budget = PaidBudget(self.budget_path)
        if budget.snapshot()["experiment_id"] != claim["experiment_id"]:
            raise ValueError("wrong experiment ledger")
        budget.reserve(self.control_root.name, "setup", UPPER_USD, "e2b", digest(claim))
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
            raise ValueError("unexpected sandbox resource/lifetime/network identity")
        await self.ensure_dirs(self._mount_targets(writable_only=True))

    async def stop(self, delete=True):
        if self._sandbox is None:
            return
        self.cleanup_calls += 1
        sid = self._sandbox.sandbox_id
        try:
            acknowledged = await self._sandbox.kill(request_timeout=15)
            settlement = self._terminal_metering() if acknowledged is True else None
            cleanup = {"sandbox_id": sid, "kill_acknowledged": acknowledged,
                "cost_reconciliation": (
                    "Conservative host-timed usage estimate recorded; provider invoice remains separate"
                    if settlement else
                    "No terminal usage interval; hold remains, not reported as spend")}
            if settlement:
                cleanup.update(metered_usd=settlement[0],
                               metering_receipt_sha256=digest(settlement[1]))
            fresh_json(self.control_root / f"cleanup-{self.cleanup_calls:02d}.json", cleanup)
            if acknowledged is not True:
                raise RuntimeError("sandbox kill not acknowledged; verify exact sandbox absence")
            self._sandbox = None
            if settlement:
                PaidBudget(self.budget_path).settle_metered(
                    self.control_root.name, settlement[0], settlement[1]
                )
        except BaseException as error:
            path = self.control_root / f"cleanup-error-{self.cleanup_calls:02d}.json"
            if not path.exists():
                fresh_json(path, {"sandbox_id": sid, "error_type": type(error).__name__})
            raise


class SequentialFixtureAgent(BaseAgent):
    def __init__(self, *args, control_root, **kwargs):
        self.control_root = Path(control_root)
        super().__init__(*args, **kwargs)

    @staticmethod
    def name():
        return "market-sequential-fixture"

    def version(self):
        return "1"

    async def setup(self, environment):
        claim, packet = verify_claim(self.control_root)
        sb = environment._sandbox
        if sb is None:
            raise RuntimeError("sandbox missing")
        result = await sb.commands.run(f"mkdir -m 700 {PRIVATE} && mkdir -m 755 {PUBLIC}",
                                       user="root", timeout=10)
        if result.exit_code != 0:
            raise ValueError("exclusive sandbox directory creation failed")
        for name, path in SOURCES.items():
            target = (PRIVATE if name.startswith("private/") else PUBLIC) + "/" + name.split("/", 1)[1]
            await sb.files.write(target, path.read_bytes(), user="root", request_timeout=15)
        await sb.files.write(PRIVATE + "/packet.json", canonical(packet), user="root", request_timeout=15)
        await sb.files.write(PRIVATE + "/input-claim.json", canonical({
            "packet_sha256": claim["packet_sha256"], "deployed_hashes": claim["deployed_hashes"]}),
            user="root", request_timeout=15)
        # Fresh known directories contain only the enumerated files above.
        private_names = [name.split("/", 1)[1] for name in SOURCES if name.startswith("private/")]
        private_names += ["packet.json", "input-claim.json"]
        public_names = [name.split("/", 1)[1] for name in SOURCES if name.startswith("public/")]
        cmd = "chmod 600 " + " ".join(PRIVATE + "/" + n for n in private_names)
        cmd += " && chmod 444 " + " ".join(PUBLIC + "/" + n for n in public_names)
        result = await sb.commands.run(cmd, user="root", timeout=10)
        if result.exit_code != 0:
            raise ValueError("sandbox input permissions failed")

    async def run(self, instruction, environment, context):
        sb = environment._sandbox
        verify_claim(self.control_root)
        command_error = None
        try:
            result = await sb.commands.run(f"python3 -I {PRIVATE}/sandbox_prediction_runner.py",
                                           user="root", timeout=40)
            fresh_json(self.control_root / "command.json", {"exit_code": result.exit_code,
                       "stdout": result.stdout, "stderr": result.stderr})
            if result.exit_code != 0:
                command_error = "NonzeroExit"
        except Exception as error:
            command_error = type(error).__name__
            fresh_json(self.control_root / "command-error.json", {"error_type": command_error})
        finally:
            collected = self.control_root / "collected"
            collected.mkdir(mode=0o700, exist_ok=False)
            missing = {}
            for name in OUTPUTS:
                try:
                    remote = PRIVATE + "/" + name
                    info = await sb.files.get_info(remote, user="root", request_timeout=10)
                    if info.size > 32 * 1024 * 1024 or info.symlink_target is not None:
                        raise ValueError("output size or symlink rejected")
                    data = await sb.files.read(remote, format="bytes", user="root", request_timeout=10)
                    if len(data) > 32 * 1024 * 1024:
                        raise ValueError("output changed beyond bound")
                    path = collected / name
                    path.parent.mkdir(mode=0o700, exist_ok=True)
                    with path.open("xb") as f:
                        f.write(data)
                        f.flush()
                        os.fsync(f.fileno())
                except Exception as error:
                    missing[name] = type(error).__name__
            fresh_json(self.control_root / "collection.json", {"missing_or_failed": missing,
                       "expected_optional": ["failure.json"], "scored": False})
        context.metadata = {"evidence_class": "synthetic-worker-integration", "scored": False}
        if command_error is not None or not (self.control_root / "collected/execution.json").is_file():
            raise ValueError("sandbox worker did not finish; preserved available outputs")


def verify_fixture_outputs(root):
    _, packet = verify_claim(root)
    root = Path(root)
    path = root / "collected/predictions/predictions.jsonl"
    complete = json.loads((root / "collected/predictions/complete.json").read_text())
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if (len(rows) != len(packet["evaluation"]) or complete["predictions"] != len(rows)
            or file_hash(path) != complete["predictions_sha256"] or complete["scored"] is not False):
        raise ValueError("prediction count/file hash mismatch")
    previous = "0" * 64
    for i, (row, features) in enumerate(zip(rows, packet["evaluation"], strict=True)):
        if (row["sequence"] != i or row["row_id"] != features["row_id"] or row["previous"] != previous
                or row["feature_row_sha256"] != fingerprint(features)
                or row["hash"] != fingerprint({k: v for k, v in row.items() if k != "hash"})
                or row["prediction"] != features["features"]["x"]):
            raise ValueError("synthetic fixture read-back failed")
        previous = row["hash"]
    if complete["last_prediction_hash"] != previous:
        raise ValueError("prediction completion chain mismatch")
    journal_claim = json.loads((root / "collected/predictions/claim.json").read_text())
    expected_claim = {"train_sha256": fingerprint(packet["train"]),
                      "evaluation_sha256": fingerprint(packet["evaluation"]),
                      "candidate_sha256": file_hash(SOURCES["public/candidate.py"]),
                      "expected_predictions": len(rows), "scoring_authorized": False}
    if journal_claim != expected_claim:
        raise ValueError("prediction journal is not bound to the admitted fixture")
    isolation = json.loads((root / "collected/isolation.json").read_text())
    if (set(isolation["checks"]) != ISOLATION_CHECKS
            or not all(v is True for v in isolation["checks"].values())
            or isolation["exit_code"] != 0
            or isolation["probe_sha256"] != file_hash(SOURCES["public/isolation_probe.py"])):
        raise ValueError("isolation checks failed")
    execution = json.loads((root / "collected/execution.json").read_text())
    if execution["complete"] != complete or execution["scored"] is not False:
        raise ValueError("execution receipt mismatch")
    return {"passed": True, "predictions": len(rows), "isolated_pre_import": True,
            "execution_only": True, "research_result": False, "market_score": None,
            "predictions_sha256": file_hash(path), "scored": False}


async def run_fixture(output, budget_path, env_file):
    output = Path(output).resolve()
    identifier(output.name)
    budget = PaidBudget(budget_path)
    state = budget.snapshot()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    packet = fixture_packet()
    claim = {"job_id": output.name, "experiment_id": state["experiment_id"],
             "evidence_class": "synthetic-worker-integration", "research_result": False,
             "worker_sha256": file_hash(__file__), "packet_sha256": fingerprint(packet),
             "deployed_hashes": {name: file_hash(path) for name, path in SOURCES.items()},
             "ttl_seconds": TTL, "template": TEMPLATE, "upper_usd": UPPER_USD, "rates": RATES,
             "note": "One new Harbor streaming-worker integration fixture; no model or market data"}
    fresh_json(output / "claim.json", claim)
    fresh_json(output / "packet.json", packet)
    fresh_json(output / "sources.json", {"worker": Path(__file__).read_text(),
               "deployed": {name: path.read_text() for name, path in SOURCES.items()}})
    config = TrialConfig(task=TaskConfig(path=FIXTURE), trial_name=output.name, trials_dir=output / "harbor",
        agent=AgentConfig(import_path="market_harbor:SequentialFixtureAgent", override_timeout_sec=60,
                          override_setup_timeout_sec=45, kwargs={"control_root": str(output)}),
        environment=EnvironmentConfig(import_path="market_harbor:BoundedMarketE2B", force_build=False,
            delete=True, kwargs={"control_root": str(output), "budget_path": str(Path(budget_path).resolve()),
                                 "env_file": str(Path(env_file).resolve())}),
        verifier=VerifierConfig(disable=True))
    fresh_json(output / "harbor-config.json", config.model_dump(mode="json"))
    trial = None
    try:
        trial = await Trial.create(config)
        result = await asyncio.wait_for(trial.run(), timeout=150)
        if result.exception_info is not None:
            raise ValueError("Harbor trial failed; no automatic retry")
        assessment = verify_fixture_outputs(output)
        cleanup = json.loads((output / "cleanup-01.json").read_text())
        if cleanup["kill_acknowledged"] is not True:
            raise ValueError("exact sandbox cleanup was not acknowledged")
        fresh_json(output / "assessment.json", assessment)
        return assessment
    except Exception as error:
        fresh_json(output / "failure.json", {"error_type": type(error).__name__,
                   "research_result": False, "automatic_retry": False})
        raise
    finally:
        # Harbor catches some teardown exceptions; retain an exact independent
        # cleanup responsibility rather than assuming its final result is proof.
        if trial is not None and trial.agent_environment._sandbox is not None:
            await asyncio.shield(trial.agent_environment.stop(delete=True))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--budget", type=Path, required=True)
    p.add_argument("--env-file", type=Path, required=True)
    args = p.parse_args()
    print(canonical(asyncio.run(run_fixture(args.output, args.budget, args.env_file))))
