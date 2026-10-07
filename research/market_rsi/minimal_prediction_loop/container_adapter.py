"""Synthetic-only local-Docker adapter for the label-free prediction protocol.

The trusted host retains the complete row sequence and durable journal.  The
container receives one current public row over stdin and returns one untrusted
probability over stdout.  This module does not score, open real data, or claim
isolation: every receipt keeps all external authority false until a separately
authorized fresh canary and independent review pass.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import signal
import shutil
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from supervisor_harness.local_b_container import IMAGE

from .prediction_protocol import (
    LabelFreePredictionProtocol,
    PredictionProtocolError,
    deterministic_run_id,
    fingerprint,
    validate_public_rows,
)


ADAPTER_SCHEMA = "minimal_prediction_local_container_adapter_v1"
RECEIPT_SCHEMA = "minimal_prediction_local_container_receipt_v1"
FAILURE_SCHEMA = "minimal_prediction_local_container_failure_v1"
SUCCESS_SCHEMA = "minimal_prediction_local_container_success_v1"
GUEST_SOURCE = Path(__file__).with_name("container_candidate_guest.py")
GUEST_PATH = "/opt/market-rsi/container_candidate_guest.py"
CANDIDATE_PATH = "/opt/market-rsi/candidate.py"
MAX_SOURCE_BYTES = 256 * 1024
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 16 * 1024
MAX_STDERR_BYTES = 64 * 1024
ROW_TIMEOUT_SECONDS = 10.0
TOTAL_TIMEOUT_SECONDS = 120.0
# Frozen local ARM64 Homebrew Docker CLI 27.1.1 used by this unreleased
# adapter snapshot. A client upgrade requires a new reviewed source snapshot.
DOCKER_CLI_SHA256 = "346b99a72cc44a7bdd91f6840aa46f14cdd9370b70eddcd7b0a48151fbfc060c"
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_DOCKER_ENV_KEYS = (
    "DOCKER_API_VERSION",
    "DOCKER_CERT_PATH",
    "DOCKER_CONFIG",
    "DOCKER_CONTEXT",
    "DOCKER_HOST",
    "DOCKER_TLS_VERIFY",
)
_DOCKER_INFO_FORMAT = (
    "{{.ID}}|{{.Name}}|{{.ServerVersion}}|{{.OSType}}|"
    "{{.Architecture}}|{{.DockerRootDir}}"
)
_MAX_DOCKER_IDENTITY_BYTES = 8 * 1024
_RECEIPT_FIELDS = frozenset({
    "schema", "run_id", "claim_sha256", "candidate_sha256", "guest_sha256",
    "public_rows_sha256", "command_sha256", "docker_client",
    "protocol_completion", "process", "cleanup",
    "candidate_terminated_before_protocol_completion",
    "exact_container_absent_before_protocol_completion", "synthetic_only",
    "test_mode", "scored", "real_data_admitted", "real_isolation_admitted",
    "promotion_authorized", "receipt_sha256",
})
_ADAPTER_CLAIM_FIELDS = frozenset({
    "schema", "run_id", "container_name", "candidate_sha256", "guest_sha256",
    "public_rows_sha256", "command_sha256", "image", "docker_client",
    "expected_predictions", "synthetic_only", "test_mode", "scored",
    "real_data_admitted", "real_isolation_admitted", "promotion_authorized",
})
_SUCCESS_FIELDS = frozenset({
    "schema", "run_id", "receipt_sha256", "receipt_file_sha256",
    "test_mode", "synthetic_only", "scored", "real_data_admitted",
    "real_isolation_admitted", "promotion_authorized", "marker_sha256",
})


class ContainerAdapterError(RuntimeError):
    """Raised when local candidate execution cannot be trusted as complete."""


class TransportLifecycleError(ContainerAdapterError):
    """Raised with structured evidence when client lifecycle is uncertain."""

    def __init__(self, message: str, process_evidence: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.process_evidence = dict(process_evidence)


@dataclass(frozen=True)
class DockerClientBinding:
    """One immutable Docker CLI, environment, context and daemon identity."""

    cli: str
    cli_sha256: str
    cli_size: int
    cli_mtime_ns: int
    environment: tuple[tuple[str, str], ...]
    context: str
    daemon_identity: str

    def environment_dict(self) -> dict[str, str]:
        return dict(self.environment)

    def public_receipt(self) -> dict[str, Any]:
        return {
            "cli": self.cli,
            "cli_sha256": self.cli_sha256,
            "cli_size": self.cli_size,
            "cli_mtime_ns": self.cli_mtime_ns,
            "environment_keys": [key for key, _ in self.environment],
            "environment_sha256": fingerprint(dict(self.environment)),
            "context": self.context,
            "daemon_identity_sha256": hashlib.sha256(
                self.daemon_identity.encode("utf-8")
            ).hexdigest(),
        }


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ContainerAdapterError("canonical JSON value required") from error


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_once(path: Path, value: Mapping[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(_canonical(dict(value)) + b"\n")
        output.flush()
        os.fsync(output.fileno())
    _fsync_directory(path.parent)


def _read_canonical_object(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular(path)
    if not raw.endswith(b"\n") or b"\n" in raw[:-1]:
        raise ContainerAdapterError("one canonical JSON line required")
    value = _strict_json_object(raw[:-1])
    if raw != _canonical(value) + b"\n":
        raise ContainerAdapterError("noncanonical adapter artifact")
    return value, raw


def verify_adapter_terminal(
    artifact_root: Path,
    *,
    protocol_root: Path,
    run_key: str,
    candidate_sha256: str,
    public_rows: Sequence[Mapping[str, Any]],
    allow_test_mode: bool = False,
) -> dict[str, Any]:
    """Accept only one verified success terminal; any failure dominates."""

    root = Path(artifact_root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ContainerAdapterError("real absolute adapter artifact root required")
    failure_path = root / "adapter-failure.json"
    if os.path.lexists(failure_path):
        raise ContainerAdapterError("adapter failure evidence dominates success")
    receipt, receipt_raw = _read_canonical_object(root / "adapter-receipt.json")
    marker, _marker_raw = _read_canonical_object(root / "adapter-success.json")
    if not isinstance(run_key, str) or not run_key.startswith("synthetic-"):
        raise ContainerAdapterError("synthetic run key required for terminal verification")
    candidate_sha256 = _require_hash(candidate_sha256, "candidate_sha256")
    rows = _synthetic_rows(public_rows)
    expected_run_id = deterministic_run_id(
        run_key=run_key,
        candidate_sha256=candidate_sha256,
        public_rows=rows,
    )
    receipt_body = dict(receipt)
    receipt_sha256 = receipt_body.pop("receipt_sha256", None)
    if (set(receipt) != _RECEIPT_FIELDS
            or receipt.get("schema") != RECEIPT_SCHEMA
            or receipt.get("run_id") != expected_run_id
            or receipt_sha256 != fingerprint(receipt_body)
            or type(receipt.get("test_mode")) is not bool
            or receipt.get("synthetic_only") is not True
            or receipt.get("scored") is not False
            or receipt.get("real_data_admitted") is not False
            or receipt.get("real_isolation_admitted") is not False
            or receipt.get("promotion_authorized") is not False
            or receipt.get("candidate_terminated_before_protocol_completion") is not True
            or receipt.get("exact_container_absent_before_protocol_completion") is not True
            or not isinstance(receipt.get("process"), dict)
            or receipt["process"].get("process_reaped") is not True
            or receipt["process"].get("exit_code") != 0
            or not isinstance(receipt.get("cleanup"), dict)
            or receipt["cleanup"].get("exact_container_cleanup_verified") is not True):
        raise ContainerAdapterError("adapter success receipt integrity failure")
    if receipt["test_mode"] and not allow_test_mode:
        raise ContainerAdapterError("test-mode adapter receipt has no canary authority")
    claim, _claim_raw = _read_canonical_object(root / "adapter-claim.json")
    expected_container_name = "market-rsi-candidate-" + expected_run_id[-20:]
    expected_rows_sha256 = fingerprint(list(rows))
    if (set(claim) != _ADAPTER_CLAIM_FIELDS
            or claim.get("schema") != ADAPTER_SCHEMA
            or claim.get("run_id") != expected_run_id
            or claim.get("container_name") != expected_container_name
            or claim.get("candidate_sha256") != candidate_sha256
            or claim.get("public_rows_sha256") != expected_rows_sha256
            or claim.get("expected_predictions") != len(rows)
            or type(claim.get("test_mode")) is not bool
            or claim.get("test_mode") is not receipt["test_mode"]
            or claim.get("synthetic_only") is not True
            or claim.get("scored") is not False
            or claim.get("real_data_admitted") is not False
            or claim.get("real_isolation_admitted") is not False
            or claim.get("promotion_authorized") is not False
            or fingerprint(claim) != receipt.get("claim_sha256")
            or receipt.get("candidate_sha256") != claim.get("candidate_sha256")
            or receipt.get("guest_sha256") != claim.get("guest_sha256")
            or receipt.get("public_rows_sha256") != claim.get("public_rows_sha256")
            or receipt.get("command_sha256") != claim.get("command_sha256")
            or receipt.get("docker_client") != claim.get("docker_client")):
        raise ContainerAdapterError("adapter claim integrity failure")
    staged = {
        "guest_path": root / "staging/container_candidate_guest.py",
        "candidate_path": root / "staging/candidate.py",
        "guest_sha256": claim["guest_sha256"],
        "candidate_sha256": claim["candidate_sha256"],
    }
    _verify_staged(staged)
    if hashlib.sha256(_read_regular(GUEST_SOURCE.resolve())).hexdigest() != claim["guest_sha256"]:
        raise ContainerAdapterError("current guest source differs from terminal claim")
    protocol_root = _protocol_root(
        protocol_root, allow_temporary=receipt["test_mode"] and allow_test_mode
    )
    try:
        with LabelFreePredictionProtocol.resume(
            protocol_root,
            candidate_sha256=candidate_sha256,
            public_rows=rows,
            run_id=expected_run_id,
            run_key=run_key,
        ) as protocol:
            actual_completion = protocol.completion_receipt()
    except PredictionProtocolError as error:
        raise ContainerAdapterError("protocol terminal integrity failure") from error
    if actual_completion != receipt.get("protocol_completion"):
        raise ContainerAdapterError("protocol completion differs from adapter receipt")
    marker_body = dict(marker)
    marker_sha256 = marker_body.pop("marker_sha256", None)
    if (set(marker) != _SUCCESS_FIELDS
            or marker.get("schema") != SUCCESS_SCHEMA
            or marker.get("run_id") != receipt["run_id"]
            or marker.get("receipt_sha256") != receipt_sha256
            or marker.get("receipt_file_sha256")
            != hashlib.sha256(receipt_raw).hexdigest()
            or marker.get("test_mode") is not receipt["test_mode"]
            or marker.get("synthetic_only") is not True
            or marker.get("scored") is not False
            or marker.get("real_data_admitted") is not False
            or marker.get("real_isolation_admitted") is not False
            or marker.get("promotion_authorized") is not False
            or marker_sha256 != fingerprint(marker_body)):
        raise ContainerAdapterError("adapter terminal success marker integrity failure")
    return receipt


def _strict_json_object(raw: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ContainerAdapterError("duplicate JSON member")
            result[key] = value
        return result

    def constant(_value: str) -> Any:
        raise ContainerAdapterError("non-finite JSON number")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContainerAdapterError("strict UTF-8 JSON object required") from error
    if not isinstance(value, dict):
        raise ContainerAdapterError("candidate response must be a JSON object")
    return value


def _require_hash(value: str, name: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise ContainerAdapterError(f"{name} must be a lowercase SHA-256")
    return value


def _docker_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    ambient = os.environ if source is None else source
    environment = {
        "PATH": ambient.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": ambient.get("HOME", str(Path.home())),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    for key in _DOCKER_ENV_KEYS:
        if key in ambient:
            environment[key] = ambient[key]
    if any(type(key) is not str or type(value) is not str
           for key, value in environment.items()):
        raise ContainerAdapterError("string Docker client environment required")
    return environment


def _executable_identity(path: Path) -> tuple[str, int, int]:
    path = Path(path)
    if not path.is_absolute() or path.is_symlink():
        raise ContainerAdapterError("resolved absolute Docker CLI required")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as error:
        raise ContainerAdapterError("Docker CLI cannot be opened safely") from error
    digest = hashlib.sha256()
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 256 * 1024 * 1024
                or before.st_mode & 0o111 == 0):
            raise ContainerAdapterError("bounded executable Docker CLI required")
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise ContainerAdapterError("Docker CLI changed while hashing")
            digest.update(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ContainerAdapterError("Docker CLI grew while hashing")
        after = os.fstat(descriptor)
        if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise ContainerAdapterError("Docker CLI identity changed while hashing")
        return digest.hexdigest(), before.st_size, before.st_mtime_ns
    finally:
        os.close(descriptor)


def _bounded_control_text(result: Any, name: str) -> str:
    if getattr(result, "returncode", None) != 0:
        raise ContainerAdapterError(f"Docker {name} probe failed")
    value = getattr(result, "stdout", None)
    if not isinstance(value, str):
        raise ContainerAdapterError(f"Docker {name} probe returned non-text")
    value = value.strip()
    if (not value or len(value.encode("utf-8")) > _MAX_DOCKER_IDENTITY_BYTES
            or any(ord(character) < 32 for character in value)):
        raise ContainerAdapterError(f"bounded printable Docker {name} required")
    return value


def _observe_docker_identity(*, cli: str, environment: Mapping[str, str],
                             run: Callable[..., Any]) -> tuple[str, str]:
    options = {
        "capture_output": True,
        "text": True,
        "timeout": 8,
        "check": False,
        "env": dict(environment),
    }
    try:
        context_result = run([cli, "context", "show"], **options)
        daemon_result = run(
            [cli, "info", "--format", _DOCKER_INFO_FORMAT], **options
        )
    except Exception as error:
        raise ContainerAdapterError("Docker identity probe failed") from error
    context = _bounded_control_text(context_result, "context")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", context) is None:
        raise ContainerAdapterError("conservative Docker context required")
    daemon_identity = _bounded_control_text(daemon_result, "daemon identity")
    return context, daemon_identity


def freeze_docker_client(*, run: Callable[..., Any] = subprocess.run,
                         docker_cli: Path | None = None,
                         environment: Mapping[str, str] | None = None,
                         expected_cli_sha256: str = DOCKER_CLI_SHA256,
                         ) -> DockerClientBinding:
    """Freeze the exact client executable, endpoint environment and daemon."""

    client_environment = _docker_environment(environment)
    if docker_cli is None:
        located = shutil.which("docker", path=client_environment["PATH"])
        if located is None:
            raise ContainerAdapterError("Docker CLI is unavailable")
        docker_cli = Path(located)
    try:
        resolved = Path(docker_cli).resolve(strict=True)
    except OSError as error:
        raise ContainerAdapterError("Docker CLI cannot be resolved") from error
    cli_sha256, cli_size, cli_mtime_ns = _executable_identity(resolved)
    if cli_sha256 != _require_hash(expected_cli_sha256, "expected_cli_sha256"):
        raise ContainerAdapterError("Docker CLI hash differs from frozen snapshot")
    context, daemon_identity = _observe_docker_identity(
        cli=str(resolved), environment=client_environment, run=run
    )
    return DockerClientBinding(
        cli=str(resolved),
        cli_sha256=cli_sha256,
        cli_size=cli_size,
        cli_mtime_ns=cli_mtime_ns,
        environment=tuple(sorted(client_environment.items())),
        context=context,
        daemon_identity=daemon_identity,
    )


def _verify_docker_client(binding: DockerClientBinding, *,
                          run: Callable[..., Any]) -> None:
    if not isinstance(binding, DockerClientBinding):
        raise ContainerAdapterError("frozen Docker client binding required")
    observed = _executable_identity(Path(binding.cli))
    if observed != (binding.cli_sha256, binding.cli_size, binding.cli_mtime_ns):
        raise ContainerAdapterError("Docker CLI identity changed")
    context, daemon_identity = _observe_docker_identity(
        cli=binding.cli, environment=binding.environment_dict(), run=run
    )
    if context != binding.context or daemon_identity != binding.daemon_identity:
        raise ContainerAdapterError("Docker context or daemon identity changed")


def _read_regular(path: Path, *, maximum: int = MAX_SOURCE_BYTES) -> bytes:
    path = Path(path)
    if not path.is_absolute() or path.is_symlink():
        raise ContainerAdapterError("absolute non-symlink source path required")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as error:
        raise ContainerAdapterError("source cannot be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
            raise ContainerAdapterError("bounded regular source required")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                raise ContainerAdapterError("source changed while reading")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ContainerAdapterError("source grew while reading")
        after = os.fstat(descriptor)
        if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise ContainerAdapterError("source identity changed while reading")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _copy_once(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
        os.fchmod(output.fileno(), 0o444)
        after = os.fstat(output.fileno())
        if (not stat.S_ISREG(after.st_mode)
                or stat.S_IMODE(after.st_mode) != 0o444
                or after.st_size != len(payload)):
            raise ContainerAdapterError("staged source mode or identity mismatch")
        os.fsync(output.fileno())


def _persistent_root(path: Path, *, allow_temporary: bool) -> Path:
    path = Path(path)
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise ContainerAdapterError("fresh absolute artifact root required")
    parent = path.parent.resolve(strict=True)
    resolved = parent / path.name
    if allow_temporary:
        return resolved
    required = (Path.home() / "Library" / "Application Support" / "MarketRSI").resolve()
    if not resolved.is_relative_to(required):
        raise ContainerAdapterError("persistent local MarketRSI artifact root required")
    return resolved


def _protocol_root(path: Path, *, allow_temporary: bool) -> Path:
    path = Path(path)
    if not path.is_absolute() or path.is_symlink():
        raise ContainerAdapterError("absolute non-symlink protocol root required")
    resolved = path.resolve(strict=False)
    if not allow_temporary:
        required = (Path.home() / "Library" / "Application Support" / "MarketRSI").resolve()
        if not resolved.is_relative_to(required):
            raise ContainerAdapterError("persistent local MarketRSI protocol root required")
    return resolved


def _stage_sources(artifact_root: Path, candidate_source: Path,
                   expected_candidate_sha256: str) -> dict[str, Any]:
    candidate_bytes = _read_regular(candidate_source)
    candidate_sha256 = hashlib.sha256(candidate_bytes).hexdigest()
    if candidate_sha256 != expected_candidate_sha256:
        raise ContainerAdapterError("candidate source hash mismatch")
    guest_bytes = _read_regular(GUEST_SOURCE.resolve())
    guest_sha256 = hashlib.sha256(guest_bytes).hexdigest()
    staging = artifact_root / "staging"
    staging.mkdir(mode=0o700)
    guest = staging / "container_candidate_guest.py"
    candidate = staging / "candidate.py"
    _copy_once(guest, guest_bytes)
    _copy_once(candidate, candidate_bytes)
    _fsync_directory(staging)
    return {
        "guest_path": guest,
        "candidate_path": candidate,
        "guest_sha256": guest_sha256,
        "candidate_sha256": candidate_sha256,
    }


def _verify_staged(staged: Mapping[str, Any]) -> None:
    for kind in ("guest", "candidate"):
        path = staged[f"{kind}_path"]
        metadata = path.stat(follow_symlinks=False)
        if (not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o444):
            raise ContainerAdapterError(f"staged {kind} source mode changed")
        observed = hashlib.sha256(_read_regular(path)).hexdigest()
        if observed != staged[f"{kind}_sha256"]:
            raise ContainerAdapterError(f"staged {kind} source changed")


def docker_prediction_command(*, docker_cli: str, container_name: str, run_id: str,
                              staged_guest: Path, staged_candidate: Path,
                              guest_sha256: str, candidate_sha256: str) -> list[str]:
    if not isinstance(docker_cli, str) or not Path(docker_cli).is_absolute():
        raise ContainerAdapterError("absolute Docker CLI required")
    if (not re.fullmatch(r"market-rsi-candidate-[0-9a-f]{20}", container_name)
            or not re.fullmatch(r"run-[0-9a-f]{64}", run_id)):
        raise ContainerAdapterError("bounded container and run identity required")
    for path in (staged_guest, staged_candidate):
        path = Path(path)
        if (not path.is_absolute() or path.is_symlink() or not path.is_file()
                or any(character in str(path) for character in ",\n\r")):
            raise ContainerAdapterError("safe staged source mount required")
    _require_hash(guest_sha256, "guest_sha256")
    _require_hash(candidate_sha256, "candidate_sha256")
    return [
        docker_cli, "run", "--rm", "--pull", "never", "--name", container_name,
        "-i", "--label", f"market-rsi-candidate={run_id}",
        "--label", f"market-rsi-task-id={run_id}",
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--ipc", "none",
        "--pids-limit", "32", "--memory", "512m", "--cpus", "1",
        "--user", "65534:65534", "--log-driver", "none",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m",
        "--mount", f"type=bind,src={staged_guest},dst={GUEST_PATH},readonly",
        "--mount", f"type=bind,src={staged_candidate},dst={CANDIDATE_PATH},readonly",
        IMAGE,
        "/usr/bin/env", "-i", "PATH=/usr/local/bin:/usr/bin:/bin",
        "LANG=C.UTF-8", "LC_ALL=C.UTF-8", "HOME=/nonexistent",
        "PYTHONHASHSEED=0", "PYTHONDONTWRITEBYTECODE=1",
        "/usr/local/bin/python", "-I", "-B", "-u", GUEST_PATH,
        CANDIDATE_PATH, "--candidate-sha256", candidate_sha256,
        "--guest-sha256", guest_sha256,
    ]


def _inspect_container(name: str, run_id: str, *, binding: DockerClientBinding,
                       run: Callable[..., Any]) -> dict[str, Any]:
    try:
        _verify_docker_client(binding, run=run)
    except Exception as error:
        return {"state": "unknown", "container_id": None,
                "error_type": type(error).__name__}
    command = [
        binding.cli, "inspect", "--format",
        '{{.Id}}|{{index .Config.Labels "market-rsi-candidate"}}|{{index .Config.Labels "market-rsi-task-id"}}',
        name,
    ]
    try:
        result = run(
            command, capture_output=True, text=True, timeout=5, check=False,
            env=binding.environment_dict(),
        )
    except Exception as error:
        return {"state": "unknown", "container_id": None,
                "error_type": type(error).__name__}
    if result.returncode == 0:
        parts = result.stdout.strip().split("|")
        if len(parts) != 3 or not parts[0]:
            return {"state": "unknown", "container_id": None,
                    "error_type": "MalformedInspect"}
        owned = parts[1] == run_id and parts[2] == run_id
        return {"state": "owned" if owned else "foreign",
                "container_id": parts[0], "labels": parts[1:]}
    error = result.stderr or ""
    if name in error and ("No such object" in error or "No such container" in error):
        return {"state": "absent", "container_id": None}
    return {"state": "unknown", "container_id": None,
            "error_type": "InspectFailed"}


def _cleanup_container(name: str, run_id: str, *, binding: DockerClientBinding,
                       run: Callable[..., Any]) -> dict[str, Any]:
    initial = _inspect_container(name, run_id, binding=binding, run=run)
    stopped = False
    if initial["state"] == "owned":
        try:
            result = run(
                [binding.cli, "stop", "--time", "2", initial["container_id"]],
                capture_output=True, text=True, timeout=8, check=False,
                env=binding.environment_dict(),
            )
            stopped = result.returncode == 0
        except Exception:
            stopped = False
    final = _inspect_container(name, run_id, binding=binding, run=run)
    verified = initial["state"] in {"owned", "absent"} and final["state"] == "absent"
    return {
        "initial": initial,
        "stop_acknowledged": stopped,
        "final": final,
        "exact_container_cleanup_verified": verified,
    }


def _terminate_and_reap(process: Any, *, timeout: float = 5.0) -> dict[str, Any]:
    before = process.poll()
    signal_attempted = before is None
    signal_acknowledged = before is not None
    signal_error: str | None = None
    wait_timed_out = False
    if before is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            signal_acknowledged = True
        except ProcessLookupError:
            signal_acknowledged = True
        except Exception as error:
            signal_error = type(error).__name__
    try:
        exit_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        wait_timed_out = True
        exit_code = process.poll()
    except Exception as error:
        exit_code = process.poll()
        if signal_error is None:
            signal_error = type(error).__name__
    close_errors: list[str] = []
    for stream in (process.stdin, process.stdout, process.stderr):
        try:
            stream.close()
        except Exception as error:
            close_errors.append(type(error).__name__)
    reaped = process.poll() is not None and not wait_timed_out
    return {
        "signal_attempted": signal_attempted,
        "signal_acknowledged": signal_acknowledged,
        "signal_error_type": signal_error,
        "wait_timed_out": wait_timed_out,
        "process_reaped": reaped,
        "exit_code": exit_code,
        "pipe_close_error_types": close_errors,
    }


class DockerJSONLTransport:
    """One-request/one-response bounded pipe transport for the Docker CLI."""

    def __init__(self, command: Sequence[str], artifact_root: Path,
                 client_environment: Mapping[str, str],
                 *, popen: Callable[..., Any] = subprocess.Popen) -> None:
        self.started = time.monotonic()
        self.command = list(command)
        self.stderr = bytearray()
        self.stdout_sha256 = hashlib.sha256()
        self.stdout_bytes = 0
        self.responses = 0
        self.closed = False
        self.process = popen(
            self.command, cwd=artifact_root, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=dict(client_environment),
            start_new_session=True, bufsize=0,
        )
        try:
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                if stream is None:
                    raise ContainerAdapterError("candidate client pipe missing")
                os.set_blocking(stream.fileno(), False)
        except Exception as error:
            evidence = _terminate_and_reap(self.process)
            self.closed = evidence["process_reaped"] is True
            raise TransportLifecycleError(
                "candidate client initialization failed", evidence
            ) from error

    def _remaining_total(self) -> float:
        return TOTAL_TIMEOUT_SECONDS - (time.monotonic() - self.started)

    def assert_quiet(self) -> None:
        """Reject bytes already queued before another row may be released."""

        if self.closed:
            raise ContainerAdapterError("candidate transport is closed")
        while True:
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdout, selectors.EVENT_READ, "stdout")
                selector.register(self.process.stderr, selectors.EVENT_READ, "stderr")
                events = selector.select(0)
            if not events:
                if self.process.poll() is not None:
                    raise ContainerAdapterError("candidate exited before protocol end")
                return
            for selected, _ in events:
                stream, kind = selected.fileobj, selected.data
                try:
                    chunk = os.read(stream.fileno(), 65_536)
                except BlockingIOError:
                    continue
                if not chunk:
                    raise ContainerAdapterError(
                        f"candidate {kind} closed before protocol end"
                    )
                if kind == "stderr":
                    self.stderr.extend(chunk)
                    if len(self.stderr) > MAX_STDERR_BYTES:
                        raise ContainerAdapterError("candidate stderr exceeds byte bound")
                    continue
                self.stdout_sha256.update(chunk)
                self.stdout_bytes += len(chunk)
                raise ContainerAdapterError(
                    "unsolicited candidate stdout before next row release"
                )

    def exchange(self, payload: Mapping[str, Any], timeout: float = ROW_TIMEOUT_SECONDS) -> dict[str, Any]:
        if self.closed:
            raise ContainerAdapterError("candidate transport is closed")
        self.assert_quiet()
        request = _canonical(dict(payload)) + b"\n"
        if len(request) > MAX_REQUEST_BYTES:
            raise ContainerAdapterError("public request exceeds byte bound")
        deadline = time.monotonic() + min(timeout, self._remaining_total())
        remaining = memoryview(request)
        output = bytearray()
        stdout_open = stderr_open = True
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdin, selectors.EVENT_WRITE, "stdin")
            selector.register(self.process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(self.process.stderr, selectors.EVENT_READ, "stderr")
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("candidate row response timeout")
                events = selector.select(left)
                if not events and self.process.poll() is not None:
                    raise ContainerAdapterError("candidate exited without a response")
                # Always inspect already-readable output before permitting the
                # next request write. Identity validation remains the fallback
                # for bytes that race this bounded readiness observation.
                events.sort(key=lambda item: item[0].data == "stdin")
                for selected, _ in events:
                    stream, kind = selected.fileobj, selected.data
                    if kind == "stdin":
                        try:
                            count = os.write(stream.fileno(), remaining)
                        except BlockingIOError:
                            continue
                        except BrokenPipeError as error:
                            raise ContainerAdapterError("candidate closed stdin") from error
                        remaining = remaining[count:]
                        if not remaining:
                            selector.unregister(stream)
                        continue
                    try:
                        chunk = os.read(stream.fileno(), 65_536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(stream)
                        if kind == "stdout":
                            stdout_open = False
                        else:
                            stderr_open = False
                        if kind == "stdout" and b"\n" not in output:
                            raise ContainerAdapterError("candidate stdout closed before response")
                        continue
                    if kind == "stderr":
                        self.stderr.extend(chunk)
                        if len(self.stderr) > MAX_STDERR_BYTES:
                            raise ContainerAdapterError("candidate stderr exceeds byte bound")
                        continue
                    if remaining:
                        raise ContainerAdapterError("candidate responded before request was sent")
                    output.extend(chunk)
                    self.stdout_sha256.update(chunk)
                    self.stdout_bytes += len(chunk)
                    if len(output) > MAX_RESPONSE_BYTES:
                        raise ContainerAdapterError("candidate response exceeds byte bound")
                    if b"\n" in output:
                        line, extra = bytes(output).split(b"\n", 1)
                        if extra:
                            raise ContainerAdapterError("multiple or trailing candidate output")
                        self.responses += 1
                        return _strict_json_object(line)
                if not stdout_open and not stderr_open:
                    raise ContainerAdapterError("candidate pipes closed")

    def finish(self) -> dict[str, Any]:
        if self.closed:
            raise ContainerAdapterError("candidate transport already closed")
        self.process.stdin.close()
        deadline = time.monotonic() + min(ROW_TIMEOUT_SECONDS, self._remaining_total())
        for stream in (self.process.stdout, self.process.stderr):
            while True:
                try:
                    chunk = os.read(stream.fileno(), 65_536)
                except BlockingIOError:
                    chunk = None
                if chunk is None:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("candidate did not terminate after final row")
                    if self.process.poll() is None:
                        time.sleep(0.01)
                        continue
                    time.sleep(0.001)
                    continue
                if not chunk:
                    break
                if stream is self.process.stdout:
                    self.stdout_sha256.update(chunk)
                    self.stdout_bytes += len(chunk)
                    raise ContainerAdapterError("unsolicited candidate stdout after final response")
                self.stderr.extend(chunk)
                if len(self.stderr) > MAX_STDERR_BYTES:
                    raise ContainerAdapterError("candidate stderr exceeds byte bound")
        remaining = max(0.001, deadline - time.monotonic())
        try:
            exit_code = self.process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            raise TimeoutError("candidate process did not exit") from error
        self.closed = True
        self.process.stdout.close()
        self.process.stderr.close()
        return {
            "process_reaped": self.process.poll() is not None,
            "exit_code": exit_code,
            "responses": self.responses,
            "stdout_bytes": self.stdout_bytes,
            "stdout_sha256": self.stdout_sha256.hexdigest(),
            "stderr_bytes": len(self.stderr),
            "stderr_sha256": hashlib.sha256(self.stderr).hexdigest(),
        }

    def abort(self) -> dict[str, Any]:
        if self.closed:
            return {
                "signal_attempted": False,
                "signal_acknowledged": True,
                "signal_error_type": None,
                "wait_timed_out": False,
                "process_reaped": self.process.poll() is not None,
                "exit_code": self.process.poll(),
                "pipe_close_error_types": [],
            }
        evidence = _terminate_and_reap(self.process)
        self.closed = evidence["process_reaped"] is True
        return evidence


def _synthetic_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    frozen = validate_public_rows(rows)
    if any(not row["event_id"].startswith("synthetic-")
           or not row["market_id"].startswith("synthetic-") for row in frozen):
        raise ContainerAdapterError("this snapshot accepts synthetic row identities only")
    return frozen


def run_local_candidate_prediction(
    *,
    protocol_root: Path,
    artifact_root: Path,
    run_key: str,
    candidate_source: Path,
    expected_candidate_sha256: str,
    public_rows: Sequence[Mapping[str, Any]],
    allow_temporary: bool = False,
    transport_factory: Callable[[Sequence[str], Path], Any] | None = None,
    control_run: Callable[..., Any] = subprocess.run,
    docker_binding: DockerClientBinding | None = None,
) -> dict[str, Any]:
    """Run one synthetic candidate once; never score or grant authority."""

    injected_test_hooks = (
        transport_factory is not None
        or control_run is not subprocess.run
        or docker_binding is not None
    )
    if injected_test_hooks and not allow_temporary:
        raise ContainerAdapterError(
            "test hooks require explicit temporary synthetic mode"
        )
    test_mode = allow_temporary
    if not isinstance(run_key, str) or not run_key.startswith("synthetic-"):
        raise ContainerAdapterError("synthetic run key required")
    expected_candidate_sha256 = _require_hash(
        expected_candidate_sha256, "expected_candidate_sha256"
    )
    rows = _synthetic_rows(public_rows)
    protocol_root = _protocol_root(protocol_root, allow_temporary=allow_temporary)
    artifact_root = _persistent_root(artifact_root, allow_temporary=allow_temporary)
    binding = docker_binding or freeze_docker_client(run=control_run)
    _verify_docker_client(binding, run=control_run)
    artifact_root.mkdir(mode=0o700, parents=False, exist_ok=False)
    _fsync_directory(artifact_root.parent)
    staged = _stage_sources(artifact_root, Path(candidate_source),
                            expected_candidate_sha256)
    run_id = deterministic_run_id(
        run_key=run_key, candidate_sha256=expected_candidate_sha256,
        public_rows=rows,
    )
    container_name = "market-rsi-candidate-" + run_id[-20:]
    command = docker_prediction_command(
        docker_cli=binding.cli, container_name=container_name, run_id=run_id,
        staged_guest=staged["guest_path"],
        staged_candidate=staged["candidate_path"],
        guest_sha256=staged["guest_sha256"],
        candidate_sha256=staged["candidate_sha256"],
    )
    preflight = _inspect_container(
        container_name, run_id, binding=binding, run=control_run
    )
    if preflight["state"] != "absent":
        raise ContainerAdapterError("candidate container identity is not fresh and absent")
    claim = {
        "schema": ADAPTER_SCHEMA,
        "run_id": run_id,
        "container_name": container_name,
        "candidate_sha256": staged["candidate_sha256"],
        "guest_sha256": staged["guest_sha256"],
        "public_rows_sha256": fingerprint(list(rows)),
        "command_sha256": hashlib.sha256(_canonical(command)).hexdigest(),
        "image": IMAGE,
        "docker_client": binding.public_receipt(),
        "expected_predictions": len(rows),
        "synthetic_only": True,
        "test_mode": test_mode,
        "scored": False,
        "real_data_admitted": False,
        "real_isolation_admitted": False,
        "promotion_authorized": False,
    }
    _write_once(artifact_root / "adapter-claim.json", claim)
    transport: Any | None = None
    cleanup: dict[str, Any] | None = None
    process: dict[str, Any] | None = None
    abort_evidence: dict[str, Any] | None = None
    protocol: LabelFreePredictionProtocol | None = None
    factory = transport_factory or (
        lambda argv, root: DockerJSONLTransport(
            argv, root, binding.environment_dict()
        )
    )
    try:
        _verify_staged(staged)
        protocol = LabelFreePredictionProtocol.create(
            protocol_root, run_key=run_key,
            candidate_sha256=expected_candidate_sha256, public_rows=rows,
        )
        with protocol:
            transport = factory(command, artifact_root)
            while True:
                release = protocol.release_next()
                if release is None:
                    break
                response = transport.exchange(release, ROW_TIMEOUT_SECONDS)
                protocol.commit_prediction(response)
                transport.assert_quiet()
            process = transport.finish()
            if (not isinstance(process, dict)
                    or process.get("process_reaped") is not True
                    or process.get("exit_code") != 0
                    or process.get("responses") != len(rows)):
                raise ContainerAdapterError("candidate process did not end cleanly")
            _verify_staged(staged)
            cleanup = _cleanup_container(
                container_name, run_id, binding=binding, run=control_run
            )
            if cleanup["exact_container_cleanup_verified"] is not True:
                raise ContainerAdapterError("exact candidate container absence unverified")
            completion = protocol.finish()
            receipt = {
                "schema": RECEIPT_SCHEMA,
                "run_id": run_id,
                "claim_sha256": fingerprint(claim),
                "candidate_sha256": staged["candidate_sha256"],
                "guest_sha256": staged["guest_sha256"],
                "public_rows_sha256": claim["public_rows_sha256"],
                "command_sha256": claim["command_sha256"],
                "docker_client": claim["docker_client"],
                "protocol_completion": completion,
                "process": process,
                "cleanup": cleanup,
                "candidate_terminated_before_protocol_completion": True,
                "exact_container_absent_before_protocol_completion": True,
                "synthetic_only": True,
                "test_mode": test_mode,
                "scored": False,
                "real_data_admitted": False,
                "real_isolation_admitted": False,
                "promotion_authorized": False,
            }
            receipt["receipt_sha256"] = fingerprint(receipt)
            _write_once(artifact_root / "adapter-receipt.json", receipt)
            receipt_raw = _read_regular(artifact_root / "adapter-receipt.json")
            marker_body = {
                "schema": SUCCESS_SCHEMA,
                "run_id": run_id,
                "receipt_sha256": receipt["receipt_sha256"],
                "receipt_file_sha256": hashlib.sha256(receipt_raw).hexdigest(),
                "test_mode": test_mode,
                "synthetic_only": True,
                "scored": False,
                "real_data_admitted": False,
                "real_isolation_admitted": False,
                "promotion_authorized": False,
            }
            marker = {**marker_body, "marker_sha256": fingerprint(marker_body)}
            _write_once(artifact_root / "adapter-success.json", marker)
        return verify_adapter_terminal(
            artifact_root,
            protocol_root=protocol_root,
            run_key=run_key,
            candidate_sha256=expected_candidate_sha256,
            public_rows=rows,
            allow_test_mode=test_mode,
        )
    except Exception as error:
        if transport is not None:
            try:
                abort_evidence = transport.abort()
            except Exception as abort_error:
                abort_evidence = {
                    "process_reaped": False,
                    "abort_error_type": type(abort_error).__name__,
                }
        elif isinstance(error, TransportLifecycleError):
            abort_evidence = dict(error.process_evidence)
        if process is None and abort_evidence is not None:
            process = dict(abort_evidence)
        if cleanup is None:
            cleanup = _cleanup_container(
                container_name, run_id, binding=binding, run=control_run
            )
        verified_completion: dict[str, Any] | None = None
        if protocol is not None:
            try:
                with LabelFreePredictionProtocol.resume(
                    protocol_root,
                    candidate_sha256=expected_candidate_sha256,
                    public_rows=rows,
                    run_key=run_key,
                ) as recovered:
                    verified_completion = recovered.completion_receipt()
            except Exception:
                verified_completion = None
        failure = {
            "schema": FAILURE_SCHEMA,
            "run_id": run_id,
            "error_type": type(error).__name__,
            "process": process,
            "abort": abort_evidence,
            "process_reaped": bool(process and process.get("process_reaped") is True),
            "cleanup": cleanup,
            "prediction_complete": verified_completion is not None,
            "protocol_completion": verified_completion,
            "adapter_receipt_finalized": False,
            "adapter_receipt_present": (artifact_root / "adapter-receipt.json").exists(),
            "adapter_success_present": (artifact_root / "adapter-success.json").exists(),
            "scored": False,
            "synthetic_only": True,
            "test_mode": test_mode,
            "real_data_admitted": False,
            "real_isolation_admitted": False,
            "promotion_authorized": False,
        }
        try:
            _write_once(artifact_root / "adapter-failure.json", failure)
        except Exception:
            pass
        if isinstance(error, (ContainerAdapterError, PredictionProtocolError,
                              TimeoutError)):
            raise
        raise ContainerAdapterError("synthetic candidate adapter failed closed") from error


__all__ = [
    "ADAPTER_SCHEMA",
    "ContainerAdapterError",
    "DockerClientBinding",
    "DOCKER_CLI_SHA256",
    "DockerJSONLTransport",
    "FAILURE_SCHEMA",
    "RECEIPT_SCHEMA",
    "SUCCESS_SCHEMA",
    "TransportLifecycleError",
    "docker_prediction_command",
    "freeze_docker_client",
    "run_local_candidate_prediction",
    "verify_adapter_terminal",
]
