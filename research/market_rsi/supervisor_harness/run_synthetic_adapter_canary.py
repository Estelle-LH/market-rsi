"""Run the one authorized synthetic adapter Docker canary exactly once.

The production entry point accepts no arguments.  Read-only preflight finishes
before the fixed attempt directory is created.  Exclusive creation of that
directory is the irreversible ID-consumption event; no code path retries or
removes it.  A successful run proves only this exact synthetic transport path
and keeps every real-data, scoring, training, release, and promotion authority
false.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from minimal_prediction_loop.container_adapter import (
    DOCKER_CLI_SHA256,
    GUEST_SOURCE,
    DockerClientBinding,
    docker_prediction_command,
    freeze_docker_client,
    run_local_candidate_prediction,
    verify_adapter_terminal,
)
from minimal_prediction_loop.prediction_protocol import (
    LabelFreePredictionProtocol,
    PREDICTION_SCHEMA,
    deterministic_run_id,
    fingerprint,
    validate_public_rows,
)
from supervisor_harness.local_b_container import IMAGE


CANARY_ID = "market-rsi-real-candidate-isolation-canary-20260929-01"
RUN_KEY = "synthetic-market-rsi-real-candidate-isolation-canary-20260929-01"
AUTHORIZATION_USER_TEXT = "授权"
AUTHORIZATION_CONTEXT = (
    "User authorized the exact one-shot zero-provider synthetic-only Docker "
    "canary proposed under this ID in the supervisor thread on 2026-09-29."
)
MAX_ATTEMPTS = 1
AUTOMATIC_RETRY = False
SCHEMA = "market_rsi_synthetic_adapter_canary_launch_intent_v1"
SUCCESS_SCHEMA = "market_rsi_synthetic_adapter_canary_success_v1"
FAILURE_SCHEMA = "market_rsi_synthetic_adapter_canary_failure_v1"
VERIFICATION_SCHEMA = "market_rsi_synthetic_adapter_canary_verification_v1"

HERE = Path(__file__).resolve().parent
MARKET_RSI_ROOT = HERE.parent
REPOSITORY_ROOT = MARKET_RSI_ROOT.parents[1]
PERSISTENT_ROOT = Path(
    "/Users/estelle/Library/Application Support/MarketRSI"
)
CANARY_PARENT = PERSISTENT_ROOT / "synthetic-adapter-canaries"
ATTEMPT_ROOT = CANARY_PARENT / CANARY_ID
ARTIFACT_ROOT = ATTEMPT_ROOT / "adapter"
PROTOCOL_ROOT = ATTEMPT_ROOT / "protocol"
CANDIDATE_SOURCE = (
    MARKET_RSI_ROOT
    / "minimal_prediction_loop/synthetic_isolation_canary_candidate.py"
)
TEST_SOURCE = HERE / "test_run_synthetic_adapter_canary.py"
# Supervisor must replace this only after the dedicated offline test file is
# final.  ``None`` is an intentional fail-closed prelaunch gate, never a
# wildcard and never permission to launch without the test snapshot.
EXPECTED_TEST_SHA256: str | None = None
ADAPTER_DECOY = ATTEMPT_ROOT / "adapter-host-decoy-synthetic.txt"
PROTOCOL_DECOY = ATTEMPT_ROOT / "protocol-host-decoy-synthetic.txt"
ADAPTER_DECOY_BYTES = b"synthetic adapter host decoy; never mounted\n"
PROTOCOL_DECOY_BYTES = b"synthetic protocol host decoy; never mounted\n"

PUBLIC_ROWS = (
    {
        "event_id": "synthetic-isolation-event-000",
        "market_id": "synthetic-isolation-market-000",
        "cutoff_ms": 1_700_000_000_000,
        "feature_available_ms": 1_699_999_999_000,
        "market_probability": 0.4,
    },
    {
        "event_id": "synthetic-isolation-event-001",
        "market_id": "synthetic-isolation-market-001",
        "cutoff_ms": 1_700_000_060_000,
        "feature_available_ms": 1_700_000_059_000,
        "market_probability": 0.6,
    },
)
EXPECTED_PROBABILITIES = (0.25, 0.75)
CANDIDATE_SHA256 = "260165e6f2681ac5d4e93bd473bc15abca7bd4f70d10e469e7b875da4c09e80d"
V4_ORDERED_AGGREGATE_SHA256 = (
    "87a32217bca2919e1a4724785ef578a6b7cda23b10bf99c56319017235e9472b"
)
_SOURCE_HASHES = {
    "research/market_rsi/minimal_prediction_loop/container_adapter.py":
        "34d4df25da4cea9807a39874cf04c0ed52af1c83f23d3851476a947f998590c9",
    "research/market_rsi/minimal_prediction_loop/container_candidate_guest.py":
        "d79d927d0ca3affda43639455c18b164c59014186092a2183fe765fcf4ac7b36",
    "research/market_rsi/minimal_prediction_loop/prediction_protocol.py":
        "eb6bdc1367f62c2910225218389d7381cebb2477e92a523c83f0693ae21a5dd3",
    "research/market_rsi/supervisor_harness/local_b_container.py":
        "76b0420fdd9c0fdc6b90cbfdc35979e5c196f0917102936edb9ea3f03e8525be",
    "research/market_rsi/tests/test_minimal_prediction_container_adapter.py":
        "98cda5b55bad2b29e4fd6f139125ced9abc740a4500fe2e85770c185610dfc2d",
    "research/market_rsi/tests/test_minimal_prediction_protocol.py":
        "9931c44f8d689386b3cb134965bcf704743226c02f587ae6aa7aa5a79e38197a",
}
_V4_SOURCE_ORDER = tuple(_SOURCE_HASHES)
_RUNNER_SELF_SENTINEL = "0" * 64
RUNNER_SELF_SHA256 = "92b9126c4327c18dbb42542d2ea62e7870239adb5351d71ed020b1ea12a33557"
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_DOCKER_CLIENT_FIELDS = {
    "cli", "cli_sha256", "cli_size", "cli_mtime_ns", "environment_keys",
    "environment_sha256", "context", "daemon_identity_sha256",
}
_DOCKER_ENVIRONMENT_KEYS = {
    "PATH", "HOME", "LANG", "LC_ALL", "DOCKER_API_VERSION",
    "DOCKER_CERT_PATH", "DOCKER_CONFIG", "DOCKER_CONTEXT", "DOCKER_HOST",
    "DOCKER_TLS_VERIFY",
}
_AUTHORITY = {
    "real_data_admitted": False,
    "protected_splits_opened": False,
    "fetch_authorized": False,
    "provider_authorized": False,
    "scoring_authorized": False,
    "training_authorized": False,
    "release_authorized": False,
    "promotion_authorized": False,
}
_CLOUD_PARTS = {
    "icloud", "mobile documents", "cloudstorage", "dropbox", "google drive",
    "googledrive", "onedrive", "box",
}
_INTENT_FIELDS = {
    "schema", "canary_id", "authorization_user_text", "authorization_context",
    "max_attempts", "automatic_retry", "zero_provider",
    "provider_calls_allowed", "cost_limit_usd", "run_key", "run_id",
    "container_name", "candidate_sha256", "guest_sha256",
    "runner_normalized_sha256", "runner_file_sha256",
    "reviewed_v4_ordered_aggregate_sha256", "source_hashes", "public_rows",
    "public_rows_sha256", "expected_probabilities", "image",
    "docker_cli_sha256", "docker_client", "image_observation",
    "preflight_container_absence", "command", "command_sha256",
    "attempt_root", "artifact_root", "protocol_root", "decoys",
    "synthetic_only", "test_mode", "live_canary_eligible",
    "real_input_eligible", "scored", "provider_calls", "provider_cost_usd",
    "authority", "intent_sha256",
}
_SUCCESS_FIELDS = {
    "schema", "canary_id", "run_id", "intent_file_sha256",
    "adapter_receipt_file_sha256", "protocol_complete_file_sha256",
    "synthetic_only", "test_mode", "provider_calls",
    "provider_cost_usd", "scored", "authority", "receipt_sha256",
}


class SyntheticCanaryError(RuntimeError):
    """Raised when the one-shot synthetic canary must fail closed."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise SyntheticCanaryError("canonical JSON value required") from error


def _file_sha256(path: Path, *, maximum: int = 2 * 1024 * 1024) -> str:
    path = Path(path)
    if not path.is_absolute() or path.is_symlink():
        raise SyntheticCanaryError("absolute non-symlink file required")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as error:
        raise SyntheticCanaryError(f"cannot safely open {path.name}") from error
    digest = hashlib.sha256()
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or not 0 < before.st_size <= maximum):
            raise SyntheticCanaryError(f"bounded single-link file required: {path.name}")
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                raise SyntheticCanaryError(f"file changed while reading: {path.name}")
            digest.update(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise SyntheticCanaryError(f"file grew while reading: {path.name}")
        after = os.fstat(descriptor)
        if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise SyntheticCanaryError(f"file identity changed: {path.name}")
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _read_regular(path: Path, *, maximum: int = 2 * 1024 * 1024) -> bytes:
    path = Path(path)
    if not path.is_absolute() or path.is_symlink():
        raise SyntheticCanaryError("absolute non-symlink file required")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or not 0 < before.st_size <= maximum):
            raise SyntheticCanaryError(f"bounded single-link file required: {path.name}")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                raise SyntheticCanaryError(f"short read: {path.name}")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise SyntheticCanaryError(f"file grew while reading: {path.name}")
        after = os.fstat(descriptor)
        if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise SyntheticCanaryError(f"file identity changed: {path.name}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _read_canonical(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular(path)
    if not raw.endswith(b"\n") or b"\n" in raw[:-1]:
        raise SyntheticCanaryError(f"one canonical JSON line required: {path.name}")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise SyntheticCanaryError("duplicate JSON member")
            result[key] = value
        return result

    def constant(_value: str) -> Any:
        raise SyntheticCanaryError("non-finite JSON number")

    try:
        value = json.loads(
            raw[:-1].decode("utf-8"), object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SyntheticCanaryError(f"strict JSON required: {path.name}") from error
    if not isinstance(value, dict) or raw != _canonical(value) + b"\n":
        raise SyntheticCanaryError(f"canonical JSON object required: {path.name}")
    return value, raw


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_once(path: Path, value: Mapping[str, Any]) -> bytes:
    raw = _canonical(dict(value)) + b"\n"
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    _fsync_directory(path.parent)
    return raw


def _write_bytes_once(path: Path, raw: bytes) -> None:
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    _fsync_directory(path.parent)


def _runner_normalized_sha256() -> str:
    raw = _read_regular(Path(__file__).resolve())
    current = f'RUNNER_SELF_SHA256 = "{RUNNER_SELF_SHA256}"'.encode("ascii")
    replacement = f'RUNNER_SELF_SHA256 = "{_RUNNER_SELF_SENTINEL}"'.encode("ascii")
    if raw.count(current) != 1:
        raise SyntheticCanaryError("runner self-hash field is ambiguous")
    return hashlib.sha256(raw.replace(current, replacement, 1)).hexdigest()


def _validate_path_boundary() -> None:
    expected = PERSISTENT_ROOT / "synthetic-adapter-canaries" / CANARY_ID
    if ATTEMPT_ROOT != expected or not ATTEMPT_ROOT.is_absolute():
        raise SyntheticCanaryError("fixed attempt root changed")
    for part in ATTEMPT_ROOT.parts:
        if part.casefold() in _CLOUD_PARTS:
            raise SyntheticCanaryError("cloud-backed path forbidden")
    lowered = str(ATTEMPT_ROOT).casefold()
    if (lowered.startswith("/tmp/") or lowered.startswith("/private/tmp/")
            or lowered.startswith("/private/var/folders/")
            or "/mobile documents/" in lowered
            or "/cloudstorage/" in lowered):
        raise SyntheticCanaryError("temporary or cloud-backed path forbidden")
    if PERSISTENT_ROOT.resolve(strict=True) != PERSISTENT_ROOT:
        raise SyntheticCanaryError("persistent root must be canonical")
    current = Path("/")
    for part in PERSISTENT_ROOT.parts[1:]:
        current /= part
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise SyntheticCanaryError("persistent ancestor must be a real directory")
        if metadata.st_mode & 0o022:
            raise SyntheticCanaryError("persistent ancestor must not be group/world writable")
    if os.path.lexists(ATTEMPT_ROOT):
        raise FileExistsError("authorized canary ID is already consumed")
    if CANARY_PARENT.exists() and (
        CANARY_PARENT.is_symlink() or not CANARY_PARENT.is_dir()
    ):
        raise SyntheticCanaryError("canary parent is not a real directory")
    if CANARY_PARENT.exists():
        parent_info = CANARY_PARENT.stat(follow_symlinks=False)
        root_info = PERSISTENT_ROOT.stat(follow_symlinks=False)
        if parent_info.st_dev != root_info.st_dev or parent_info.st_mode & 0o022:
            raise SyntheticCanaryError("canary parent is not local or is writable by others")


def _validate_source_snapshot() -> dict[str, str]:
    observed: dict[str, str] = {}
    lines = bytearray()
    for relative in _V4_SOURCE_ORDER:
        path = REPOSITORY_ROOT / relative
        digest = _file_sha256(path)
        if digest != _SOURCE_HASHES[relative]:
            raise SyntheticCanaryError(f"reviewed source changed: {relative}")
        observed[relative] = digest
        lines.extend(f"{digest}  {relative}\n".encode("utf-8"))
    if hashlib.sha256(lines).hexdigest() != V4_ORDERED_AGGREGATE_SHA256:
        raise SyntheticCanaryError("v4 ordered source aggregate changed")
    candidate_sha256 = _file_sha256(CANDIDATE_SOURCE)
    if candidate_sha256 != CANDIDATE_SHA256:
        raise SyntheticCanaryError("fixed synthetic candidate changed")
    guest_sha256 = _file_sha256(GUEST_SOURCE.resolve())
    if guest_sha256 != _SOURCE_HASHES[
        "research/market_rsi/minimal_prediction_loop/container_candidate_guest.py"
    ]:
        raise SyntheticCanaryError("guest source changed")
    if _runner_normalized_sha256() != RUNNER_SELF_SHA256:
        raise SyntheticCanaryError("runner differs from its frozen normalized hash")
    if (EXPECTED_TEST_SHA256 is None
            or _HEX64.fullmatch(EXPECTED_TEST_SHA256) is None):
        raise SyntheticCanaryError("dedicated offline test hash is not frozen")
    test_sha256 = _file_sha256(TEST_SOURCE)
    if test_sha256 != EXPECTED_TEST_SHA256:
        raise SyntheticCanaryError("dedicated offline test snapshot changed")
    return {
        **observed,
        str(CANDIDATE_SOURCE.relative_to(REPOSITORY_ROOT)): candidate_sha256,
        str(Path(__file__).resolve().relative_to(REPOSITORY_ROOT)):
            _file_sha256(Path(__file__).resolve()),
        str(TEST_SOURCE.relative_to(REPOSITORY_ROOT)): test_sha256,
    }


def _docker_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _DOCKER_CLIENT_FIELDS:
        raise SyntheticCanaryError("exact Docker client receipt schema required")
    if (not isinstance(value.get("cli"), str)
            or not Path(value["cli"]).is_absolute()
            or value.get("cli_sha256") != DOCKER_CLI_SHA256
            or type(value.get("cli_size")) is not int
            or value["cli_size"] <= 0
            or type(value.get("cli_mtime_ns")) is not int
            or value["cli_mtime_ns"] <= 0
            or not isinstance(value.get("environment_keys"), list)
            or value["environment_keys"] != sorted(value["environment_keys"])
            or len(value["environment_keys"]) != len(set(value["environment_keys"]))
            or not all(isinstance(item, str) for item in value["environment_keys"])
            or not {"PATH", "HOME", "LANG", "LC_ALL"}.issubset(
                value["environment_keys"]
            )
            or not set(value["environment_keys"]).issubset(_DOCKER_ENVIRONMENT_KEYS)
            or _HEX64.fullmatch(str(value.get("environment_sha256"))) is None
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}",
                            str(value.get("context"))) is None
            or _HEX64.fullmatch(str(value.get("daemon_identity_sha256"))) is None):
        raise SyntheticCanaryError("invalid Docker client receipt")
    return dict(value)


def _run_control(binding: DockerClientBinding, command: Sequence[str], *,
                 timeout: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command), capture_output=True, text=True, timeout=timeout,
            check=False, env=binding.environment_dict(),
        )
    except Exception as error:
        raise SyntheticCanaryError("Docker read-only control probe failed") from error


def _inspect_absent(binding: DockerClientBinding, name: str,
                    run_id: str) -> dict[str, Any]:
    result = _run_control(
        binding,
        [binding.cli, "inspect", "--format",
         '{{.Id}}|{{index .Config.Labels "market-rsi-candidate"}}|'
         '{{index .Config.Labels "market-rsi-task-id"}}', name],
        timeout=5,
    )
    if result.returncode == 0:
        parts = result.stdout.strip().split("|")
        if len(parts) != 3 or not parts[0]:
            raise SyntheticCanaryError("malformed exact-name Docker inspect")
        if parts[1:] == [run_id, run_id]:
            raise SyntheticCanaryError("owned candidate container is still present")
        raise SyntheticCanaryError("foreign exact-name container blocks canary")
    error = result.stderr or ""
    if name not in error or (
        "No such object" not in error and "No such container" not in error
    ):
        raise SyntheticCanaryError("exact container absence is unknown")
    return {"state": "absent", "container_name": name, "run_id": run_id}


def _image_present(binding: DockerClientBinding) -> dict[str, Any]:
    result = _run_control(
        binding,
        [binding.cli, "image", "inspect", "--format", "{{json .RepoDigests}}", IMAGE],
        timeout=8,
    )
    if result.returncode != 0:
        raise SyntheticCanaryError("pinned image is not locally available")
    try:
        repo_digests = json.loads(result.stdout.strip())
    except json.JSONDecodeError as error:
        raise SyntheticCanaryError("pinned image receipt is malformed") from error
    if (not isinstance(repo_digests, list) or IMAGE not in repo_digests
            or not all(isinstance(item, str) for item in repo_digests)):
        raise SyntheticCanaryError("local image does not expose the exact pinned digest")
    return {
        "image": IMAGE,
        "repo_digests_sha256": fingerprint(repo_digests),
        "pull_performed": False,
    }


def _expected_command(*, binding: DockerClientBinding, run_id: str,
                      container_name: str, guest_sha256: str) -> list[str]:
    staged_guest = ARTIFACT_ROOT / "staging/container_candidate_guest.py"
    staged_candidate = ARTIFACT_ROOT / "staging/candidate.py"
    return [
        binding.cli, "run", "--rm", "--pull", "never", "--name", container_name,
        "-i", "--label", f"market-rsi-candidate={run_id}",
        "--label", f"market-rsi-task-id={run_id}",
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--ipc", "none",
        "--pids-limit", "32", "--memory", "512m", "--cpus", "1",
        "--user", "65534:65534", "--log-driver", "none",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m",
        "--mount", (
            f"type=bind,src={staged_guest},"
            "dst=/opt/market-rsi/container_candidate_guest.py,readonly"
        ),
        "--mount", (
            f"type=bind,src={staged_candidate},"
            "dst=/opt/market-rsi/candidate.py,readonly"
        ),
        IMAGE,
        "/usr/bin/env", "-i", "PATH=/usr/local/bin:/usr/bin:/bin",
        "LANG=C.UTF-8", "LC_ALL=C.UTF-8", "HOME=/nonexistent",
        "PYTHONHASHSEED=0", "PYTHONDONTWRITEBYTECODE=1",
        "/usr/local/bin/python", "-I", "-B", "-u",
        "/opt/market-rsi/container_candidate_guest.py",
        "/opt/market-rsi/candidate.py", "--candidate-sha256", CANDIDATE_SHA256,
        "--guest-sha256", guest_sha256,
    ]


def _preflight() -> dict[str, Any]:
    _validate_path_boundary()
    rows = validate_public_rows(PUBLIC_ROWS)
    if len(rows) != 2 or any(
        not row["event_id"].startswith("synthetic-")
        or not row["market_id"].startswith("synthetic-") for row in rows
    ):
        raise SyntheticCanaryError("exact two synthetic rows required")
    source_hashes = _validate_source_snapshot()
    run_id = deterministic_run_id(
        run_key=RUN_KEY, candidate_sha256=CANDIDATE_SHA256, public_rows=rows,
    )
    container_name = "market-rsi-candidate-" + run_id[-20:]
    binding = freeze_docker_client()
    docker_client = _docker_receipt(binding.public_receipt())
    image = _image_present(binding)
    absence = _inspect_absent(binding, container_name, run_id)
    guest_sha256 = source_hashes[
        "research/market_rsi/minimal_prediction_loop/container_candidate_guest.py"
    ]
    command = _expected_command(
        binding=binding, run_id=run_id, container_name=container_name,
        guest_sha256=guest_sha256,
    )
    return {
        "binding": binding,
        "rows": rows,
        "run_id": run_id,
        "container_name": container_name,
        "docker_client": docker_client,
        "image_observation": image,
        "absence": absence,
        "source_hashes": source_hashes,
        "guest_sha256": guest_sha256,
        "command": command,
        "command_sha256": hashlib.sha256(_canonical(command)).hexdigest(),
    }


def _launch_intent(preflight: Mapping[str, Any]) -> dict[str, Any]:
    body = {
        "schema": SCHEMA,
        "canary_id": CANARY_ID,
        "authorization_user_text": AUTHORIZATION_USER_TEXT,
        "authorization_context": AUTHORIZATION_CONTEXT,
        "max_attempts": MAX_ATTEMPTS,
        "automatic_retry": AUTOMATIC_RETRY,
        "zero_provider": True,
        "provider_calls_allowed": 0,
        "cost_limit_usd": "0.00",
        "run_key": RUN_KEY,
        "run_id": preflight["run_id"],
        "container_name": preflight["container_name"],
        "candidate_sha256": CANDIDATE_SHA256,
        "guest_sha256": preflight["guest_sha256"],
        "runner_normalized_sha256": RUNNER_SELF_SHA256,
        "runner_file_sha256": preflight["source_hashes"][
            str(Path(__file__).resolve().relative_to(REPOSITORY_ROOT))
        ],
        "reviewed_v4_ordered_aggregate_sha256": V4_ORDERED_AGGREGATE_SHA256,
        "source_hashes": preflight["source_hashes"],
        "public_rows": list(preflight["rows"]),
        "public_rows_sha256": fingerprint(list(preflight["rows"])),
        "expected_probabilities": list(EXPECTED_PROBABILITIES),
        "image": IMAGE,
        "docker_cli_sha256": DOCKER_CLI_SHA256,
        "docker_client": preflight["docker_client"],
        "image_observation": preflight["image_observation"],
        "preflight_container_absence": preflight["absence"],
        "command": preflight["command"],
        "command_sha256": preflight["command_sha256"],
        "attempt_root": str(ATTEMPT_ROOT),
        "artifact_root": str(ARTIFACT_ROOT),
        "protocol_root": str(PROTOCOL_ROOT),
        "decoys": {
            str(ADAPTER_DECOY): hashlib.sha256(ADAPTER_DECOY_BYTES).hexdigest(),
            str(PROTOCOL_DECOY): hashlib.sha256(PROTOCOL_DECOY_BYTES).hexdigest(),
        },
        "synthetic_only": True,
        "test_mode": False,
        "live_canary_eligible": True,
        "real_input_eligible": False,
        "scored": False,
        "provider_calls": 0,
        "provider_cost_usd": "0.00",
        "authority": dict(_AUTHORITY),
    }
    return {**body, "intent_sha256": fingerprint(body)}


def _verify_intent(attempt_root: Path, *, allow_test_mode: bool) -> tuple[dict[str, Any], bytes]:
    intent, raw = _read_canonical(attempt_root / "launch-intent.json")
    body = dict(intent)
    intent_sha256 = body.pop("intent_sha256", None)
    if (set(intent) != _INTENT_FIELDS
            or body.get("schema") != SCHEMA
            or body.get("canary_id") != CANARY_ID
            or body.get("authorization_user_text") != AUTHORIZATION_USER_TEXT
            or body.get("authorization_context") != AUTHORIZATION_CONTEXT
            or body.get("run_key") != RUN_KEY
            or body.get("max_attempts") != 1
            or body.get("automatic_retry") is not False
            or body.get("zero_provider") is not True
            or body.get("provider_calls_allowed") != 0
            or body.get("cost_limit_usd") != "0.00"
            or body.get("synthetic_only") is not True
            or type(body.get("test_mode")) is not bool
            or (body.get("test_mode") is True and not allow_test_mode)
            or body.get("live_canary_eligible") is not (not body.get("test_mode"))
            or body.get("real_input_eligible") is not False
            or body.get("scored") is not False
            or body.get("provider_calls") != 0
            or body.get("provider_cost_usd") != "0.00"
            or body.get("authority") != _AUTHORITY
            or intent_sha256 != fingerprint(body)):
        raise SyntheticCanaryError("launch intent integrity failure")
    return intent, raw


def _verify_decoys(attempt_root: Path, intent: Mapping[str, Any]) -> dict[str, str]:
    adapter_decoy = attempt_root / ADAPTER_DECOY.name
    protocol_decoy = attempt_root / PROTOCOL_DECOY.name
    expected = intent.get("decoys")
    if not isinstance(expected, dict) or set(expected) != {
        str(adapter_decoy), str(protocol_decoy)
    }:
        raise SyntheticCanaryError("exact synthetic decoy inventory required")
    observed: dict[str, str] = {}
    for path_text, expected_sha256 in expected.items():
        path = Path(path_text)
        digest = _file_sha256(path, maximum=1024)
        if digest != expected_sha256:
            raise SyntheticCanaryError("synthetic host decoy changed")
        observed[path_text] = digest
    return observed


def _expected_inventory(run_id: str, *, success_present: bool) -> set[str]:
    expected = {
        "launch-intent.json",
        ADAPTER_DECOY.name,
        PROTOCOL_DECOY.name,
        "adapter/adapter-claim.json",
        "adapter/adapter-receipt.json",
        "adapter/adapter-success.json",
        "adapter/staging/container_candidate_guest.py",
        "adapter/staging/candidate.py",
        f"protocol/{run_id}/claim.json",
        f"protocol/{run_id}/journal.jsonl",
        f"protocol/{run_id}/journal-head.json",
        f"protocol/{run_id}/complete.json",
        f"protocol/{run_id}/run.lock",
    }
    if success_present:
        expected.add("execution-success.json")
    return expected


def _closed_inventory(attempt_root: Path, run_id: str) -> list[str]:
    if os.path.lexists(attempt_root / "execution-failure.json"):
        raise SyntheticCanaryError("outer failure evidence dominates success")
    if os.path.lexists(attempt_root / "adapter/adapter-failure.json"):
        raise SyntheticCanaryError("adapter failure evidence dominates success")
    success_present = os.path.lexists(attempt_root / "execution-success.json")
    files: set[str] = set()
    directories: set[str] = set()
    for path in attempt_root.rglob("*"):
        relative = str(path.relative_to(attempt_root))
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise SyntheticCanaryError("symlink in canary evidence")
        if stat.S_ISREG(metadata.st_mode):
            files.add(relative)
        elif stat.S_ISDIR(metadata.st_mode):
            directories.add(relative)
        else:
            raise SyntheticCanaryError("special file in canary evidence")
    if files != _expected_inventory(run_id, success_present=success_present):
        raise SyntheticCanaryError("canary artifact inventory is not closed")
    if directories != {"adapter", "adapter/staging", "protocol", f"protocol/{run_id}"}:
        raise SyntheticCanaryError("canary directory inventory is not closed")
    return sorted(files)


def _verified_stdout(protocol_root: Path, run_id: str) -> dict[str, Any]:
    journal = _read_regular(protocol_root / run_id / "journal.jsonl")
    responses: list[bytes] = []
    events: list[tuple[str, int]] = []
    for raw_line in journal.splitlines():
        try:
            record = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SyntheticCanaryError("journal is not strict JSONL") from error
        if not isinstance(record, dict) or raw_line != _canonical(record):
            raise SyntheticCanaryError("journal record is not canonical")
        event = record.get("event")
        sequence = record.get("sequence")
        events.append((event, sequence))
        if event == "prediction_committed":
            response = {
                "schema": PREDICTION_SCHEMA,
                "run_id": run_id,
                "sequence": sequence,
                "row_id": record.get("row_id"),
                "probability": record.get("probability"),
            }
            responses.append(_canonical(response) + b"\n")
    if events != [
        ("row_released", 0), ("prediction_committed", 0),
        ("row_released", 1), ("prediction_committed", 1),
    ]:
        raise SyntheticCanaryError("protocol journal order is not exact")
    if len(responses) != 2:
        raise SyntheticCanaryError("exactly two stdout responses required")
    output = b"".join(responses)
    return {
        "responses": 2,
        "stdout_bytes": len(output),
        "stdout_sha256": hashlib.sha256(output).hexdigest(),
    }


def _verify_outer_success(path: Path, intent_raw: bytes,
                          receipt_raw: bytes, complete_raw: bytes) -> None:
    success, _raw = _read_canonical(path)
    body = dict(success)
    receipt_sha256 = body.pop("receipt_sha256", None)
    if (set(success) != _SUCCESS_FIELDS
            or body.get("schema") != SUCCESS_SCHEMA
            or body.get("canary_id") != CANARY_ID
            or body.get("intent_file_sha256") != hashlib.sha256(intent_raw).hexdigest()
            or body.get("adapter_receipt_file_sha256")
            != hashlib.sha256(receipt_raw).hexdigest()
            or body.get("protocol_complete_file_sha256")
            != hashlib.sha256(complete_raw).hexdigest()
            or body.get("synthetic_only") is not True
            or body.get("test_mode") is not False
            or body.get("provider_calls") != 0
            or body.get("provider_cost_usd") != "0.00"
            or body.get("scored") is not False
            or body.get("authority") != _AUTHORITY
            or receipt_sha256 != fingerprint(body)):
        raise SyntheticCanaryError("outer success receipt integrity failure")


def verify_synthetic_canary_terminal(
    attempt_root: Path = ATTEMPT_ROOT,
    *,
    allow_test_mode: bool = False,
) -> dict[str, Any]:
    """Strictly verify one terminal synthetic canary without granting authority.

    ``allow_test_mode`` exists only for marked offline fixtures.  The production
    entry point never sets it; a test-mode chain therefore has no live-canary
    authority and is rejected by default.
    """

    attempt_root = Path(attempt_root)
    if (not attempt_root.is_absolute() or attempt_root.is_symlink()
            or not attempt_root.is_dir()):
        raise SyntheticCanaryError("real absolute attempt root required")
    if not allow_test_mode and attempt_root != ATTEMPT_ROOT:
        raise SyntheticCanaryError("production verifier accepts only the fixed attempt root")
    if os.path.lexists(attempt_root / "execution-failure.json"):
        raise SyntheticCanaryError("outer failure evidence dominates success")
    if os.path.lexists(attempt_root / "adapter/adapter-failure.json"):
        raise SyntheticCanaryError("adapter failure evidence dominates success")
    intent, intent_raw = _verify_intent(
        attempt_root, allow_test_mode=allow_test_mode
    )
    current_sources = _validate_source_snapshot()
    rows = validate_public_rows(intent["public_rows"])
    if rows != validate_public_rows(PUBLIC_ROWS):
        raise SyntheticCanaryError("launch intent synthetic rows changed")
    run_id = deterministic_run_id(
        run_key=RUN_KEY, candidate_sha256=CANDIDATE_SHA256, public_rows=rows,
    )
    if (intent.get("run_id") != run_id
            or intent.get("container_name") != "market-rsi-candidate-" + run_id[-20:]
            or intent.get("candidate_sha256") != CANDIDATE_SHA256
            or intent.get("public_rows_sha256") != fingerprint(list(rows))
            or intent.get("expected_probabilities") != list(EXPECTED_PROBABILITIES)
            or intent.get("image") != IMAGE
            or intent.get("docker_cli_sha256") != DOCKER_CLI_SHA256
            or intent.get("reviewed_v4_ordered_aggregate_sha256")
            != V4_ORDERED_AGGREGATE_SHA256
            or intent.get("source_hashes") != current_sources
            or intent.get("runner_normalized_sha256") != RUNNER_SELF_SHA256
            or intent.get("runner_file_sha256") != current_sources[
                str(Path(__file__).resolve().relative_to(REPOSITORY_ROOT))
            ]
            or intent.get("guest_sha256") != current_sources[
                "research/market_rsi/minimal_prediction_loop/container_candidate_guest.py"
            ]
            or intent.get("attempt_root") != str(attempt_root)
            or intent.get("artifact_root") != str(attempt_root / "adapter")
            or intent.get("protocol_root") != str(attempt_root / "protocol")):
        raise SyntheticCanaryError("launch intent does not bind the exact run")
    expected_decoys = {
        str(attempt_root / ADAPTER_DECOY.name):
            hashlib.sha256(ADAPTER_DECOY_BYTES).hexdigest(),
        str(attempt_root / PROTOCOL_DECOY.name):
            hashlib.sha256(PROTOCOL_DECOY_BYTES).hexdigest(),
    }
    image_observation = intent.get("image_observation")
    if (intent.get("decoys") != expected_decoys
            or intent.get("preflight_container_absence") != {
                "state": "absent", "container_name": intent["container_name"],
                "run_id": run_id,
            }
            or not isinstance(image_observation, dict)
            or set(image_observation) != {"image", "repo_digests_sha256", "pull_performed"}
            or image_observation.get("image") != IMAGE
            or _HEX64.fullmatch(str(image_observation.get("repo_digests_sha256"))) is None
            or image_observation.get("pull_performed") is not False):
        raise SyntheticCanaryError("preflight image/absence/decoy binding changed")
    artifact_root = attempt_root / "adapter"
    protocol_root = attempt_root / "protocol"
    receipt = verify_adapter_terminal(
        artifact_root,
        protocol_root=protocol_root,
        run_key=RUN_KEY,
        candidate_sha256=CANDIDATE_SHA256,
        public_rows=rows,
        allow_test_mode=allow_test_mode,
    )
    claim, _claim_raw = _read_canonical(artifact_root / "adapter-claim.json")
    receipt_file, receipt_raw = _read_canonical(
        artifact_root / "adapter-receipt.json"
    )
    if receipt_file != receipt:
        raise SyntheticCanaryError("adapter verifier and receipt differ")
    if (claim.get("image") != IMAGE
            or claim.get("test_mode") is not intent.get("test_mode")
            or receipt.get("test_mode") is not intent.get("test_mode")
            or _docker_receipt(claim.get("docker_client"))
            != _docker_receipt(intent.get("docker_client"))
            or receipt.get("docker_client") != claim.get("docker_client")):
        raise SyntheticCanaryError("image/client/test-mode binding changed")
    staged_guest = artifact_root / "staging/container_candidate_guest.py"
    staged_candidate = artifact_root / "staging/candidate.py"
    command = docker_prediction_command(
        docker_cli=claim["docker_client"]["cli"],
        container_name=intent["container_name"],
        run_id=run_id,
        staged_guest=staged_guest,
        staged_candidate=staged_candidate,
        guest_sha256=claim["guest_sha256"],
        candidate_sha256=CANDIDATE_SHA256,
    )
    command_sha256 = hashlib.sha256(_canonical(command)).hexdigest()
    if (command != intent.get("command")
            or command_sha256 != intent.get("command_sha256")
            or command_sha256 != claim.get("command_sha256")
            or command_sha256 != receipt.get("command_sha256")):
        raise SyntheticCanaryError("full Docker command binding changed")
    if (_file_sha256(staged_guest) != claim.get("guest_sha256")
            or _file_sha256(staged_candidate) != CANDIDATE_SHA256
            or stat.S_IMODE(staged_guest.stat().st_mode) != 0o444
            or stat.S_IMODE(staged_candidate.stat().st_mode) != 0o444):
        raise SyntheticCanaryError("staged source integrity failure")
    stdout = _verified_stdout(protocol_root, run_id)
    process = receipt.get("process")
    if (not isinstance(process, dict)
            or set(process) != {
                "process_reaped", "exit_code", "responses", "stdout_bytes",
                "stdout_sha256", "stderr_bytes", "stderr_sha256",
            }
            or process.get("process_reaped") is not True
            or process.get("exit_code") != 0
            or process.get("responses") != stdout["responses"]
            or process.get("stdout_bytes") != stdout["stdout_bytes"]
            or process.get("stdout_sha256") != stdout["stdout_sha256"]
            or process.get("stderr_bytes") != 0
            or process.get("stderr_sha256") != hashlib.sha256(b"").hexdigest()):
        raise SyntheticCanaryError("process/stdout terminal evidence mismatch")
    with LabelFreePredictionProtocol.resume(
        protocol_root,
        candidate_sha256=CANDIDATE_SHA256,
        public_rows=rows,
        run_id=run_id,
        run_key=RUN_KEY,
    ) as protocol:
        complete = protocol.completion_receipt()
        records = protocol.prediction_records()
    if ([record["probability"] for record in records]
            != list(EXPECTED_PROBABILITIES)):
        raise SyntheticCanaryError("fixed synthetic probabilities changed")
    complete_path = protocol_root / run_id / "complete.json"
    complete_file, complete_raw = _read_canonical(complete_path)
    if complete_file != complete or complete != receipt.get("protocol_completion"):
        raise SyntheticCanaryError("protocol completion cross-binding failed")
    decoys = _verify_decoys(attempt_root, intent)
    inventory = _closed_inventory(attempt_root, run_id)
    current_binding = freeze_docker_client()
    if _docker_receipt(current_binding.public_receipt()) != intent["docker_client"]:
        raise SyntheticCanaryError("Docker client/context/daemon identity drifted")
    if _image_present(current_binding) != image_observation:
        raise SyntheticCanaryError("pinned local image observation drifted")
    absence = _inspect_absent(current_binding, intent["container_name"], run_id)
    success_path = attempt_root / "execution-success.json"
    if os.path.lexists(success_path):
        if intent.get("test_mode") is True:
            raise SyntheticCanaryError("test-mode chain cannot carry production success")
        _verify_outer_success(success_path, intent_raw, receipt_raw, complete_raw)
    return {
        "schema": VERIFICATION_SCHEMA,
        "canary_id": CANARY_ID,
        "run_id": run_id,
        "synthetic_only": True,
        "test_mode": intent["test_mode"],
        "live_canary_eligible": intent["test_mode"] is False,
        "provider_calls": 0,
        "provider_cost_usd": "0.00",
        "scored": False,
        "authority": dict(_AUTHORITY),
        "stdout": stdout,
        "decoys": decoys,
        "inventory": inventory,
        "current_container_absence": absence,
        "adapter_receipt_file_sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "protocol_complete_file_sha256": hashlib.sha256(complete_raw).hexdigest(),
        "intent_file_sha256": hashlib.sha256(intent_raw).hexdigest(),
    }


def _evidence_snapshot(attempt_root: Path) -> dict[str, Any]:
    paths = (
        "launch-intent.json", "adapter/adapter-claim.json",
        "adapter/adapter-failure.json", "adapter/adapter-receipt.json",
        "adapter/adapter-success.json", "execution-success.json",
    )
    result: dict[str, Any] = {}
    for relative in paths:
        path = attempt_root / relative
        if os.path.lexists(path):
            try:
                result[relative] = _file_sha256(path)
            except Exception:
                result[relative] = "present-but-unverifiable"
        else:
            result[relative] = None
    return result


def _write_execution_failure(error: BaseException) -> None:
    body = {
        "schema": FAILURE_SCHEMA,
        "canary_id": CANARY_ID,
        "error_type": type(error).__name__,
        "id_consumed": True,
        "automatic_retry": False,
        "retry_authorized": False,
        "synthetic_only": True,
        "test_mode": False,
        "provider_calls": 0,
        "provider_cost_usd": "0.00",
        "scored": False,
        "authority": dict(_AUTHORITY),
        "evidence": _evidence_snapshot(ATTEMPT_ROOT),
    }
    failure = {**body, "failure_sha256": fingerprint(body)}
    try:
        _write_once(ATTEMPT_ROOT / "execution-failure.json", failure)
    except Exception:
        # The exclusively created attempt directory remains the conservative
        # consumed/unknown tombstone even if terminal writing is interrupted.
        pass


def run_canary() -> dict[str, Any]:
    """Run the fixed production canary once; this function accepts no hooks."""

    preflight = _preflight()
    CANARY_PARENT.mkdir(mode=0o700, parents=False, exist_ok=True)
    _fsync_directory(PERSISTENT_ROOT)
    parent_info = CANARY_PARENT.lstat()
    if (not stat.S_ISDIR(parent_info.st_mode)
            or stat.S_ISLNK(parent_info.st_mode)
            or CANARY_PARENT.resolve(strict=True) != CANARY_PARENT
            or parent_info.st_dev != PERSISTENT_ROOT.stat().st_dev
            or parent_info.st_mode & 0o022):
        raise SyntheticCanaryError("canary parent changed before ID consumption")
    try:
        ATTEMPT_ROOT.mkdir(mode=0o700, parents=False, exist_ok=False)
    except FileExistsError as error:
        raise SyntheticCanaryError("authorized canary ID is already consumed") from error
    try:
        _fsync_directory(CANARY_PARENT)
        intent = _launch_intent(preflight)
        _write_once(ATTEMPT_ROOT / "launch-intent.json", intent)
        _write_bytes_once(ADAPTER_DECOY, ADAPTER_DECOY_BYTES)
        _write_bytes_once(PROTOCOL_DECOY, PROTOCOL_DECOY_BYTES)
        # Deliberately use the adapter's default production path.  No frozen
        # binding, transport, control runner, temporary flag, or other test
        # dependency is injected here.
        run_local_candidate_prediction(
            protocol_root=PROTOCOL_ROOT,
            artifact_root=ARTIFACT_ROOT,
            run_key=RUN_KEY,
            candidate_source=CANDIDATE_SOURCE,
            expected_candidate_sha256=CANDIDATE_SHA256,
            public_rows=PUBLIC_ROWS,
        )
        verified = verify_synthetic_canary_terminal()
        intent_raw = _read_regular(ATTEMPT_ROOT / "launch-intent.json")
        receipt_raw = _read_regular(ARTIFACT_ROOT / "adapter-receipt.json")
        complete_raw = _read_regular(
            PROTOCOL_ROOT / verified["run_id"] / "complete.json"
        )
        body = {
            "schema": SUCCESS_SCHEMA,
            "canary_id": CANARY_ID,
            "run_id": verified["run_id"],
            "intent_file_sha256": hashlib.sha256(intent_raw).hexdigest(),
            "adapter_receipt_file_sha256": hashlib.sha256(receipt_raw).hexdigest(),
            "protocol_complete_file_sha256": hashlib.sha256(complete_raw).hexdigest(),
            "synthetic_only": True,
            "test_mode": False,
            "provider_calls": 0,
            "provider_cost_usd": "0.00",
            "scored": False,
            "authority": dict(_AUTHORITY),
        }
        success = {**body, "receipt_sha256": fingerprint(body)}
        _write_once(ATTEMPT_ROOT / "execution-success.json", success)
        return verify_synthetic_canary_terminal()
    except BaseException as error:
        _write_execution_failure(error)
        if isinstance(error, SyntheticCanaryError):
            raise
        raise SyntheticCanaryError(
            "authorized synthetic canary failed closed; ID consumed; no retry"
        ) from error


def main() -> int:
    if len(sys.argv) != 1:
        raise SyntheticCanaryError("production canary runner accepts no arguments")
    result = run_canary()
    print(_canonical(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ATTEMPT_ROOT", "CANARY_ID", "RUN_KEY", "SyntheticCanaryError",
    "run_canary", "verify_synthetic_canary_terminal",
]
