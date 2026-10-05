"""Persistent, zero-authority orchestration for opened-Train Discovery.

The module records a Controller-selected candidate as an append-only branch and
advances it through implementation, one execution claim, terminal evidence,
independent review, and a compact next-Controller packet.  It deliberately has
no runner, scorer, data reader, provider, network, or authorization capability.

The append-only journal is authoritative.  ``batch.json`` is an atomically
replaced, self-hashed snapshot that can be reconstructed after a crash when it
is missing or is a valid prefix of the journal.  Corruption and non-prefix
divergence fail closed.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Callable, Iterator, Mapping

from data_scientist_harness import co_evolution_loop as micro_evolution
from supervisor_harness.learning_checkpoint_assessment import (
    EVIDENCE_SCHEMA_V4, assess_checkpoint, parent_eligibility,
    validate_saved_checkpoint, validate_validity,
)


SCHEMA = "market_rsi_continuous_discovery_batch_v1"
EVENT_SCHEMA = "market_rsi_continuous_discovery_event_v1"
EVIDENCE_SCHEMA = "market_rsi_discovery_controller_evidence_v1"
EVIDENCE_SCHEMA_V2 = "market_rsi_discovery_controller_evidence_v2"
# Opt-in for fresh batches only. Legacy v1/v2 replay stays byte-for-byte stable.
FINAL_SINGLETON_POLICY = "final-singleton-v1"
ZERO_SHA256 = "0" * 64

STAGES = (
    "controller_selected",
    "implementation_ready",
    "execution_claimed",
    "execution_terminal",
    "result_reviewed",
    "controller_feedback_ready",
)
TERMINAL_STAGE = STAGES[-1]
EXECUTION_OUTCOMES = frozenset(
    {"succeeded", "failed", "integrity_failed", "implementation_failed"}
)
REVIEW_DECISIONS = frozenset({"KEEP", "REVERT"})
POOL_ALLOCATIONS = frozenset({"exploration", "exploitation"})
RESOURCE_CLASSES = frozenset(
    {"local_analysis", "small_experiment", "metadata_lookup", "bounded_page_read"}
)
RESEARCH_OUTCOMES = frozenset({"invalid", "inconclusive", "support", "refute"})
ROUTE_ACTIONS = frozenset({"cooldown", "stop", "bounded_followup", "continue", "branch"})

BOUNDARY_FLAGS = {
    "resident_opened_train_only": True,
    "protected_dev_final_allowed": False,
    "external_acquisition_allowed": False,
    "network_allowed": False,
    "paid_provider_allowed": False,
    "publication_allowed": False,
    "promotion_allowed": False,
    "executes_runners": False,
    "scores_results": False,
    "opens_data": False,
    "grants_authority": False,
}

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_PENDING_JOURNAL = re.compile(r"\.pending-([0-9]{8})-[0-9a-f]{32}\.tmp\Z")
_CLOUD_PARTS = {
    "dropbox",
    "google drive",
    "icloud drive",
    "mobile documents",
    "onedrive",
    "box",
}


class DiscoveryBatchError(ValueError):
    """The persistent batch or a requested transition is invalid."""


class BatchStoppedError(DiscoveryBatchError):
    """The batch cannot accept another execution attempt."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DiscoveryBatchError("state must be finite canonical JSON") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha(value: object, label: str, *, allow_zero: bool = False) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise DiscoveryBatchError(f"{label} must be a lowercase SHA-256")
    if not allow_zero and value == ZERO_SHA256:
        raise DiscoveryBatchError(f"{label} must not be the zero SHA-256")
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise DiscoveryBatchError(f"invalid {label}")
    return value


def _reason(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 1024
        or any(ord(character) < 32 and character not in "\t" for character in value)
    ):
        raise DiscoveryBatchError(f"invalid {label}")
    return value


def _reserve_fraction(value: object) -> float:
    if type(value) not in (int, float):
        raise DiscoveryBatchError("exploration reserve fraction must be numeric")
    fraction = float(value)
    if not 0.20 <= fraction <= 0.40:
        raise DiscoveryBatchError("exploration reserve fraction must be in [0.20, 0.40]")
    return fraction


def _resource_hint(value: object) -> dict[str, Any]:
    item = _exact_mapping(
        value,
        {
            "resource_class", "max_attempts", "max_time_seconds", "max_bytes",
            "max_cost_usd", "authority_granted",
        },
        "bounded resource hint",
    )
    if item["resource_class"] not in RESOURCE_CLASSES:
        raise DiscoveryBatchError("unknown bounded resource class")
    if type(item["max_attempts"]) is not int or not 1 <= item["max_attempts"] <= 8:
        raise DiscoveryBatchError("resource max_attempts must be in [1, 8]")
    if (
        type(item["max_time_seconds"]) is not int
        or not 1 <= item["max_time_seconds"] <= 7200
    ):
        raise DiscoveryBatchError("resource max_time_seconds must be in [1, 7200]")
    if type(item["max_bytes"]) is not int or not 0 <= item["max_bytes"] <= 10_000_000:
        raise DiscoveryBatchError("resource max_bytes must be in [0, 10000000]")
    if type(item["max_cost_usd"]) not in (int, float) or not (
        0.0 <= float(item["max_cost_usd"]) <= 0.05
    ):
        raise DiscoveryBatchError("resource max_cost_usd must be in [0, 0.05]")
    if item["authority_granted"] is not False:
        raise DiscoveryBatchError("resource hints cannot grant authority")
    return {
        **item,
        "max_cost_usd": float(item["max_cost_usd"]),
    }


def _archived_parent(value: object) -> dict[str, Any]:
    item = _exact_mapping(
        value,
        {
            "candidate_id", "candidate_sha256", "source_batch_id",
            "source_attempt_id", "archive_manifest_sha256",
            "independent_review_sha256", "authority_snapshot_sha256",
            "problem_id", "question_digest_sha256", "evidence_bundle_sha256",
            "research_credit", "research_outcome", "route_action",
            "authority_granted",
        },
        "initial archived research parent",
    )
    credit = item["research_credit"]
    if type(credit) is not int or credit not in {1, 2}:
        raise DiscoveryBatchError("archived parent research credit must be 1 or 2")
    outcome = item["research_outcome"]
    action = item["route_action"]
    eligible_route = (
        credit == 1
        and outcome == "inconclusive"
        and action == "bounded_followup"
    ) or (credit == 2 and outcome == "support" and action == "continue") or (
        credit == 2 and outcome == "refute" and action == "branch"
    )
    if not eligible_route:
        raise DiscoveryBatchError("archived parent is not an eligible research route")
    if item["authority_granted"] is not False:
        raise DiscoveryBatchError("archived parent declarations cannot grant authority")
    return {
        "candidate_id": _identifier(item["candidate_id"], "archived candidate ID"),
        "candidate_sha256": _sha(item["candidate_sha256"], "archived candidate"),
        "source_batch_id": _identifier(item["source_batch_id"], "source batch ID"),
        "source_attempt_id": _identifier(
            item["source_attempt_id"], "source attempt ID"
        ),
        "archive_manifest_sha256": _sha(
            item["archive_manifest_sha256"], "archive manifest"
        ),
        "independent_review_sha256": _sha(
            item["independent_review_sha256"], "archived independent review"
        ),
        "authority_snapshot_sha256": _sha(
            item["authority_snapshot_sha256"], "archived authority snapshot"
        ),
        "problem_id": _identifier(item["problem_id"], "problem ID"),
        "question_digest_sha256": _sha(
            item["question_digest_sha256"], "archived question digest"
        ),
        "evidence_bundle_sha256": _sha(
            item["evidence_bundle_sha256"], "archived evidence bundle"
        ),
        "research_credit": credit,
        "research_outcome": outcome,
        "route_action": action,
        "authority_granted": False,
    }


def _archived_parent_v4(value: object) -> dict[str, Any]:
    """Prospective archive import explicitly carries original evidence/consumption."""
    keys = {"candidate_id", "candidate_sha256", "source_batch_id", "source_attempt_id",
            "archive_manifest_sha256", "independent_review_sha256", "authority_snapshot_sha256",
            "problem_id", "question_digest_sha256", "evidence_bundle_sha256", "research_credit",
            "research_outcome", "route_action", "authority_granted", "learning_checkpoint",
            "consumed_followups", "consumption_receipt_sha256", "consumed_question_sha256s"}
    item = _exact_mapping(value, keys, "v4 archived parent")
    checked = dict(item)
    for field in ("candidate_id", "source_batch_id", "source_attempt_id", "problem_id"):
        checked[field] = _identifier(item[field], field)
    for field in keys - {"candidate_id", "source_batch_id", "source_attempt_id", "problem_id",
                         "research_credit", "research_outcome", "route_action", "authority_granted",
                         "learning_checkpoint", "consumed_followups", "consumed_question_sha256s"}:
        checked[field] = _sha(item[field], field)
    if item["authority_granted"] is not False:
        raise DiscoveryBatchError("archived evidence cannot grant authority")
    if type(item["consumed_followups"]) is not int or item["consumed_followups"] not in {0, 1}:
        raise DiscoveryBatchError("archive must preserve bounded allowance consumption")
    questions = item["consumed_question_sha256s"]
    if not isinstance(questions, list) or len(set(questions)) != len(questions):
        raise DiscoveryBatchError("archive requires distinct consumed questions")
    checked["consumed_question_sha256s"] = [_sha(q, "consumed question") for q in questions]
    if not isinstance(item["learning_checkpoint"], dict):
        raise DiscoveryBatchError("archive learning checkpoint must be an object")
    branch = {"review_decision": item["learning_checkpoint"].get("prediction_decision"),
              "review_sha256": item["independent_review_sha256"], "execution_outcome": "succeeded",
              "independently_reviewed": True, "question_digest_sha256": item["question_digest_sha256"]}
    try:
        checked["learning_checkpoint"] = validate_saved_checkpoint(item["learning_checkpoint"], branch)
    except (ValueError, TypeError, KeyError) as exc:
        raise DiscoveryBatchError(str(exc)) from exc
    assessment = checked["learning_checkpoint"]
    if (type(item["research_credit"]) is not int or item["research_credit"] != assessment["learning"]["credit"]
            or item["route_action"] != assessment["exploration"]["action"]
            or item["research_outcome"] not in RESEARCH_OUTCOMES):
        raise DiscoveryBatchError("archive assessment projections changed")
    return checked


def _utc(value: str | datetime, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DiscoveryBatchError(f"{label} must be an ISO-8601 time") from exc
    else:
        raise DiscoveryBatchError(f"{label} must be an ISO-8601 time")
    if parsed.tzinfo is None:
        raise DiscoveryBatchError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _utc_text(value: str | datetime, label: str) -> str:
    return _utc(value, label).isoformat().replace("+00:00", "Z")


def _exact_mapping(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise DiscoveryBatchError(f"{label} must contain exactly {sorted(keys)!r}")
    return dict(value)


def _mapping_with_optional_event_time(
    value: object,
    keys: set[str],
    label: str,
) -> tuple[dict[str, Any], datetime | None]:
    if not isinstance(value, Mapping):
        raise DiscoveryBatchError(f"{label} must be an object")
    observed = set(value)
    if observed == keys:
        return dict(value), None
    if observed == keys | {"event_time_utc"}:
        item = dict(value)
        return item, _utc(item["event_time_utc"], f"{label} event time")
    raise DiscoveryBatchError(f"{label} must contain exactly {sorted(keys)!r}")


def _safe_root(root: str | os.PathLike[str], *, allow_temporary: bool) -> Path:
    path = Path(root)
    if not path.is_absolute() or ".." in path.parts:
        raise DiscoveryBatchError("batch root must be an absolute non-traversing path")
    folded = {part.casefold() for part in path.parts}
    if any(
        part == marker or part.startswith(marker + " ") or part.startswith(marker + " (")
        for part in folded
        for marker in _CLOUD_PARTS
    ):
        raise DiscoveryBatchError("cloud-backed batch roots are forbidden")
    if ".codex" in folded and "worktrees" in folded:
        raise DiscoveryBatchError("disposable Codex worktree roots are forbidden")

    resolved_temp = Path(tempfile.gettempdir()).resolve()
    candidate = path.resolve(strict=False)
    if not allow_temporary and (
        candidate == resolved_temp or resolved_temp in candidate.parents
    ):
        raise DiscoveryBatchError("temporary batch root requires test-only allowance")

    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.exists() or current.is_symlink():
            try:
                info = os.lstat(current)
            except OSError as exc:
                raise DiscoveryBatchError("cannot inspect batch-root ancestry") from exc
            if stat.S_ISLNK(info.st_mode):
                raise DiscoveryBatchError("batch-root ancestry must not contain symlinks")
    return path


def _private_identity(
    info: os.stat_result,
    label: str,
    *,
    regular: bool = False,
    directory: bool = False,
) -> tuple[int, int, int, int]:
    if regular and not stat.S_ISREG(info.st_mode):
        raise DiscoveryBatchError(f"{label} must be a regular file")
    if directory and not stat.S_ISDIR(info.st_mode):
        raise DiscoveryBatchError(f"{label} must be a directory")
    if info.st_uid != os.geteuid():
        raise DiscoveryBatchError(f"{label} must be owned by the effective user")
    if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise DiscoveryBatchError(f"{label} must not be group/world writable")
    if regular and info.st_nlink != 1:
        raise DiscoveryBatchError(f"{label} must have exactly one link")
    return (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode))


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("persistent JSON write made no progress")
        view = view[written:]


def _read_regular_at(
    directory_fd: int,
    name: str,
    *,
    max_bytes: int,
    label: str,
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise DiscoveryBatchError(f"cannot open {label} safely") from exc
    try:
        before = os.fstat(fd)
        identity = _private_identity(before, label, regular=True)
        if before.st_size > max_bytes:
            raise DiscoveryBatchError(f"{label} exceeds size bound")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(fd)
        if len(data) > max_bytes:
            raise DiscoveryBatchError(f"{label} exceeds size bound")
        stable_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        stable_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if stable_before != stable_after:
            raise DiscoveryBatchError(f"{label} changed while being read")
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if _private_identity(named, label, regular=True) != identity:
            raise DiscoveryBatchError(f"{label} pathname identity changed")
        return data
    finally:
        os.close(fd)


def _capture_existing_ancestry(path: Path) -> tuple[tuple[str, tuple[int, int, int, int]], ...]:
    captured: list[tuple[str, tuple[int, int, int, int]]] = []
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if not current.exists() and not current.is_symlink():
            break
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode):
            raise DiscoveryBatchError("batch-root ancestry must not contain symlinks")
        captured.append(
            (
                os.fspath(current),
                (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)),
            )
        )
    return tuple(captured)


def _state_hash(state: Mapping[str, Any]) -> str:
    body = dict(state)
    body.pop("state_sha256", None)
    return _digest(body)


def _with_state_hash(state: dict[str, Any]) -> dict[str, Any]:
    result = dict(state)
    result["state_sha256"] = _state_hash(result)
    return result


def _initial_incumbent(value: Mapping[str, Any]) -> dict[str, Any]:
    item = _exact_mapping(
        value,
        {"candidate_id", "candidate_sha256", "scorecard_sha256", "review_sha256"},
        "initial incumbent",
    )
    return {
        "candidate_id": _identifier(item["candidate_id"], "incumbent candidate ID"),
        "candidate_sha256": _sha(item["candidate_sha256"], "incumbent candidate"),
        "scorecard_sha256": _sha(
            item["scorecard_sha256"], "incumbent scorecard", allow_zero=True
        ),
        "review_sha256": _sha(
            item["review_sha256"], "incumbent review", allow_zero=True
        ),
        "source": "batch_start",
        "updated_by_attempt_id": None,
    }


class ContinuousDiscoveryBatch:
    """Append-only Discovery batch state with no experiment-side capability."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        allow_temporary: bool = False,
        test_clock: Callable[[], datetime] | None = None,
        allow_test_clock: bool = False,
    ) -> None:
        self.root = _safe_root(root, allow_temporary=allow_temporary)
        if test_clock is not None and allow_test_clock is not True:
            raise DiscoveryBatchError("an injected clock requires explicit test-only allowance")
        if allow_test_clock is True and test_clock is None:
            raise DiscoveryBatchError("test-only clock allowance requires an injected clock")
        if test_clock is not None and not callable(test_clock):
            raise DiscoveryBatchError("test clock must be callable")
        resolved_temp = Path(tempfile.gettempdir()).resolve()
        resolved_root = self.root.resolve(strict=False)
        if allow_test_clock is True and not (
            resolved_root == resolved_temp or resolved_temp in resolved_root.parents
        ):
            raise DiscoveryBatchError("test-only clock requires a temporary test root")
        self._clock = test_clock
        self._allow_test_clock = allow_test_clock is True
        self._ancestry = _capture_existing_ancestry(self.root)
        self._root_identity: tuple[int, int, int, int] | None = None
        self._journal_identity: tuple[int, int, int, int] | None = None
        self._lock_identity: tuple[int, int, int, int] | None = None
        self.journal_dir = self.root / "journal"
        self.snapshot_path = self.root / "batch.json"
        self.lock_path = self.root / ".batch.lock"

    def _trusted_now(self, supplied: str | datetime | None, label: str) -> datetime:
        if supplied is not None:
            if not self._allow_test_clock:
                raise DiscoveryBatchError("caller-supplied time is allowed only in tests")
            return _utc(supplied, label)
        source = self._clock() if self._clock is not None else datetime.now(timezone.utc)
        return _utc(source, label)

    def _verify_ancestry(self) -> None:
        for raw_path, expected in self._ancestry:
            try:
                info = os.lstat(raw_path)
            except OSError as exc:
                raise DiscoveryBatchError("batch-root ancestry changed") from exc
            observed = (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode))
            if stat.S_ISLNK(info.st_mode) or observed != expected:
                raise DiscoveryBatchError("batch-root ancestry identity changed")

    def _open_root(self) -> int:
        self._verify_ancestry()
        flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.root, flags)
        except OSError as exc:
            raise DiscoveryBatchError("cannot open batch root safely") from exc
        try:
            identity = _private_identity(os.fstat(fd), "batch root", directory=True)
            if self._root_identity is None:
                self._root_identity = identity
            elif identity != self._root_identity:
                raise DiscoveryBatchError("batch root identity changed")
            named = os.lstat(self.root)
            if _private_identity(named, "batch root", directory=True) != identity:
                raise DiscoveryBatchError("batch root pathname identity changed")
            return fd
        except Exception:
            os.close(fd)
            raise

    def _open_journal(self, *, create: bool) -> int:
        root_fd = self._open_root()
        fd = -1
        try:
            try:
                fd = os.open(
                    "journal",
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=root_fd,
                )
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir("journal", mode=0o700, dir_fd=root_fd)
                os.fsync(root_fd)
                fd = os.open(
                    "journal",
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=root_fd,
                )
            identity = _private_identity(os.fstat(fd), "batch journal", directory=True)
            named = os.stat("journal", dir_fd=root_fd, follow_symlinks=False)
            if _private_identity(named, "batch journal", directory=True) != identity:
                raise DiscoveryBatchError("batch journal pathname identity changed")
            if self._journal_identity is None:
                self._journal_identity = identity
            elif identity != self._journal_identity:
                raise DiscoveryBatchError("batch journal identity changed")
            return fd
        except Exception:
            if fd >= 0:
                os.close(fd)
            raise
        finally:
            os.close(root_fd)

    def _verify_journal_fd(self, fd: int) -> None:
        identity = _private_identity(os.fstat(fd), "batch journal", directory=True)
        if self._journal_identity is None:
            self._journal_identity = identity
        elif identity != self._journal_identity:
            raise DiscoveryBatchError("batch journal identity changed")
        root_fd = self._open_root()
        try:
            named = os.stat("journal", dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise DiscoveryBatchError("batch journal pathname identity changed") from exc
        finally:
            os.close(root_fd)
        if _private_identity(named, "batch journal", directory=True) != identity:
            raise DiscoveryBatchError("batch journal pathname identity changed")

    def _verify_lock_fd(self, fd: int) -> None:
        identity = _private_identity(os.fstat(fd), "batch lock", regular=True)
        if self._lock_identity is None:
            self._lock_identity = identity
        elif identity != self._lock_identity:
            raise DiscoveryBatchError("batch lock identity changed")
        root_fd = self._open_root()
        try:
            named = os.stat(".batch.lock", dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise DiscoveryBatchError("batch lock pathname identity changed") from exc
        finally:
            os.close(root_fd)
        if _private_identity(named, "batch lock", regular=True) != identity:
            raise DiscoveryBatchError("batch lock pathname identity changed")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        _safe_root(self.root, allow_temporary=True)
        root_fd = self._open_root()
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(".batch.lock", flags, 0o600, dir_fd=root_fd)
        finally:
            os.close(root_fd)
        verified = False
        try:
            self._verify_lock_fd(fd)
            verified = True
            fcntl.flock(fd, fcntl.LOCK_EX)
            self._verify_lock_fd(fd)
            yield
        finally:
            try:
                if verified:
                    self._verify_lock_fd(fd)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def _read_records(self) -> list[dict[str, Any]]:
        try:
            directory_fd = self._open_journal(create=False)
        except FileNotFoundError:
            return []
        try:
            self._verify_journal_fd(directory_fd)
            names = self._recover_pending_journal(directory_fd, os.listdir(directory_fd))
            names = sorted(names)
            expected = [f"{index:08d}.json" for index in range(1, len(names) + 1)]
            if names != expected:
                raise DiscoveryBatchError("batch journal contains a gap or unexpected entry")
            records: list[dict[str, Any]] = []
            previous = ZERO_SHA256
            for sequence, name in enumerate(names, 1):
                raw = _read_regular_at(
                    directory_fd,
                    name,
                    max_bytes=1024 * 1024,
                    label="batch journal entry",
                )
                try:
                    record = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise DiscoveryBatchError("batch journal entry is not JSON") from exc
                if raw != _canonical(record) + b"\n":
                    raise DiscoveryBatchError("batch journal entry is not canonical JSON")
                keys = {
                    "schema", "sequence", "event", "payload",
                    "previous_sha256", "event_sha256",
                }
                if not isinstance(record, dict) or set(record) != keys:
                    raise DiscoveryBatchError("batch journal entry schema changed")
                body = {key: value for key, value in record.items() if key != "event_sha256"}
                computed = _digest(body)
                if (
                    record["schema"] != EVENT_SCHEMA
                    or record["sequence"] != sequence
                    or record["previous_sha256"] != previous
                    or record["event_sha256"] != computed
                    or not isinstance(record["payload"], dict)
                ):
                    raise DiscoveryBatchError("batch journal sequence or hash chain changed")
                previous = computed
                records.append(record)
            self._verify_journal_fd(directory_fd)
            return records
        finally:
            os.close(directory_fd)

    def _recover_pending_journal(self, directory_fd: int, names: list[str]) -> list[str]:
        changed = False
        for name in sorted(names):
            match = _PENDING_JOURNAL.fullmatch(name)
            if match is None:
                continue
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            ):
                raise DiscoveryBatchError("unsafe pending journal artifact")
            final_name = f"{int(match.group(1)):08d}.json"
            try:
                final = os.stat(final_name, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                if info.st_nlink != 1:
                    raise DiscoveryBatchError("unpublished journal temporary is hard-linked")
                os.unlink(name, dir_fd=directory_fd)
                changed = True
                continue
            if (
                not stat.S_ISREG(final.st_mode)
                or info.st_nlink != 2
                or final.st_nlink != 2
                or (info.st_dev, info.st_ino) != (final.st_dev, final.st_ino)
            ):
                raise DiscoveryBatchError("pending journal artifact conflicts with final entry")
            os.unlink(name, dir_fd=directory_fd)
            changed = True
        if changed:
            os.fsync(directory_fd)
        remaining = os.listdir(directory_fd)
        if any(_PENDING_JOURNAL.fullmatch(name) is not None for name in remaining):
            raise DiscoveryBatchError("pending journal artifact appeared during recovery")
        return remaining

    def _append_record(
        self,
        records: list[dict[str, Any]],
        event: str,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        sequence = len(records) + 1
        body = {
            "schema": EVENT_SCHEMA,
            "sequence": sequence,
            "event": event,
            "payload": payload,
            "previous_sha256": records[-1]["event_sha256"] if records else ZERO_SHA256,
        }
        record = dict(body, event_sha256=_digest(body))
        updated = records + [record]
        # Validate the complete proposed transition before any durable path is
        # created, so an invalid request cannot poison the next sequence slot.
        self._replay(updated)

        directory_fd = self._open_journal(create=True)
        final_name = f"{sequence:08d}.json"
        temporary = f".pending-{sequence:08d}-{os.urandom(16).hex()}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        temporary_identity: tuple[int, int] | None = None
        try:
            self._verify_journal_fd(directory_fd)
            payload_bytes = _canonical(record) + b"\n"
            _write_all(fd, payload_bytes)
            os.fsync(fd)
            info = os.fstat(fd)
            _private_identity(info, "pending journal entry", regular=True)
            if info.st_size != len(payload_bytes):
                raise DiscoveryBatchError("pending journal entry length changed")
            temporary_identity = (info.st_dev, info.st_ino)
            os.close(fd)
            fd = -1
            os.link(
                temporary,
                final_name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            os.fsync(directory_fd)
            os.unlink(temporary, dir_fd=directory_fd)
            temporary_identity = None
            os.fsync(directory_fd)
            observed = _read_regular_at(
                directory_fd,
                final_name,
                max_bytes=1024 * 1024,
                label="published journal entry",
            )
            if observed != payload_bytes:
                raise DiscoveryBatchError("published journal bytes changed")
            self._verify_journal_fd(directory_fd)
        finally:
            if fd >= 0:
                os.close(fd)
            if temporary_identity is not None:
                try:
                    pending = os.stat(
                        temporary, dir_fd=directory_fd, follow_symlinks=False
                    )
                except FileNotFoundError:
                    pass
                else:
                    if (pending.st_dev, pending.st_ino) != temporary_identity:
                        raise DiscoveryBatchError("pending journal pathname changed")
                    os.unlink(temporary, dir_fd=directory_fd)
                    os.fsync(directory_fd)
            os.close(directory_fd)
        return updated

    def _empty_state(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "initialized": False,
            "batch_id": None,
            "start_utc": None,
            "deadline_utc": None,
            "max_attempts": None,
            "boundary_flags": None,
            "attempts_claimed": 0,
            "failed_attempts": 0,
            "stopped_reason": None,
            "active_attempt_id": None,
            "branches": [],
            "incumbent": None,
            "incumbent_history": [],
            "journal_length": 0,
            "journal_head_sha256": ZERO_SHA256,
        }

    @staticmethod
    def _branch(state: dict[str, Any], attempt_id: str) -> dict[str, Any]:
        for branch in state["branches"]:
            if branch["attempt_id"] == attempt_id:
                return branch
        raise DiscoveryBatchError("unknown Discovery attempt")

    @staticmethod
    def _is_v2(state: Mapping[str, Any]) -> bool:
        # v3 retains the v2 pool protocol, with an explicit final-slot policy.
        return state.get("scheduling_version") in {2, 3, 4}

    @staticmethod
    def _singleton_allowed(state: Mapping[str, Any]) -> bool:
        return (state.get("scheduling_version") in {3, 4}
                and state["max_attempts"] - state["attempts_claimed"] == 1)

    @classmethod
    def _eligible_parent_records(cls, state: dict[str, Any]) -> list[dict[str, Any]]:
        if state.get("scheduling_version") == 4:
            ranked = []
            seen = set()
            sources = [(p, p["candidate_sha256"], p["source_batch_id"], p["source_attempt_id"])
                       for p in state["initial_archived_parents"]]
            sources += [(b, b.get("runner_sha256"), state["batch_id"], b["attempt_id"])
                        for b in reversed(state["branches"]) if b.get("learning_checkpoint") is not None]
            for source, candidate, batch_id, attempt_id in sources:
                assessment = source["learning_checkpoint"]
                allowance = assessment["exploration"]["allowance_id_sha256"]
                remaining = (1 - state["bounded_followups_consumed"].get(allowance, 0)
                             if allowance is not None else None)
                record = {"candidate_id": source["candidate_id"], "candidate_sha256": candidate,
                          "source_batch_id": batch_id, "source_attempt_id": attempt_id,
                          "research_credit": source["research_credit"], "research_outcome": source["research_outcome"],
                          "route_action": source["route_action"], "followups_remaining": remaining,
                          "learning_checkpoint": assessment, "question_digest_sha256": source["question_digest_sha256"],
                          "execution_outcome": source.get("execution_outcome", "succeeded"),
                          "independently_reviewed": source.get("independently_reviewed", True),
                          "review_sha256": source.get("review_sha256", source.get("independent_review_sha256"))}
                if candidate is not None and candidate not in seen and parent_eligibility(record, 4):
                    seen.add(candidate)
                    ranked.append(record)
            baseline = state["incumbent_history"][0]
            if baseline["candidate_sha256"] not in seen:
                ranked.append({"candidate_id": baseline["candidate_id"], "candidate_sha256": baseline["candidate_sha256"],
                               "source_batch_id": state["batch_id"], "source_attempt_id": None, "research_credit": 0,
                               "research_outcome": "baseline", "route_action": "batch_start", "followups_remaining": None})
            return sorted(ranked, key=lambda p: (-p["research_credit"], p["candidate_sha256"]))
        ranked: list[dict[str, Any]] = []
        seen: set[str] = set()
        for archived in state.get("initial_archived_parents", []):
            followups = sum(
                branch.get("research_parent_sha256") == archived["candidate_sha256"]
                for branch in state["branches"]
            )
            if archived["research_credit"] == 1 and followups >= 1:
                continue
            seen.add(archived["candidate_sha256"])
            ranked.append(
                {
                    "candidate_id": archived["candidate_id"],
                    "candidate_sha256": archived["candidate_sha256"],
                    "source_batch_id": archived["source_batch_id"],
                    "source_attempt_id": archived["source_attempt_id"],
                    "research_credit": archived["research_credit"],
                    "research_outcome": archived["research_outcome"],
                    "route_action": archived["route_action"],
                    "followups_remaining": (
                        1 - followups
                        if archived["research_credit"] == 1
                        else None
                    ),
                }
            )
        for branch in reversed(state["branches"]):
            candidate_sha = branch.get("runner_sha256")
            credit = branch.get("research_credit")
            outcome = branch.get("research_outcome")
            action = branch.get("route_action")
            followups = sum(
                child.get("research_parent_sha256") == candidate_sha
                for child in state["branches"]
            )
            route_is_eligible = (
                credit == 2 and outcome == "support" and action == "continue"
            ) or (
                state.get("scheduling_version") == 3
                and credit == 2 and outcome == "refute" and action == "branch"
            ) or (
                credit == 1
                and outcome == "inconclusive"
                and action == "bounded_followup"
                and followups < 1
            )
            if (
                branch.get("stage") not in {"result_reviewed", TERMINAL_STAGE}
                or branch.get("execution_outcome") != "succeeded"
                or branch.get("independently_reviewed") is not True
                or not route_is_eligible
                or candidate_sha is None
                or candidate_sha in seen
            ):
                continue
            seen.add(candidate_sha)
            ranked.append(
                {
                    "candidate_id": branch["candidate_id"],
                    "candidate_sha256": candidate_sha,
                    "source_batch_id": state["batch_id"],
                    "source_attempt_id": branch["attempt_id"],
                    "research_credit": credit,
                    "research_outcome": outcome,
                    "route_action": action,
                    "followups_remaining": 1 - followups if credit == 1 else None,
                }
            )
        baseline = state["incumbent_history"][0]
        if baseline["candidate_sha256"] not in seen:
            ranked.append(
                {
                    "candidate_id": baseline["candidate_id"],
                    "candidate_sha256": baseline["candidate_sha256"],
                    "source_batch_id": state["batch_id"],
                    "source_attempt_id": None,
                    "research_credit": 0,
                    "research_outcome": "baseline",
                    "route_action": "batch_start",
                    "followups_remaining": None,
                }
            )
        ranked.sort(
            key=lambda item: (
                -item["research_credit"],
                -next(
                    (
                        index
                        for index, branch in enumerate(state["branches"])
                        if item["source_batch_id"] == state["batch_id"]
                        and branch["attempt_id"] == item["source_attempt_id"]
                    ),
                    -1,
                ),
                item["candidate_sha256"],
            )
        )
        return ranked

    @classmethod
    def _pool_selection_hint(cls, state: dict[str, Any]) -> dict[str, Any]:
        if not cls._is_v2(state):
            raise DiscoveryBatchError("pool scheduling is available only in v2 batches")
        ranked = cls._eligible_parent_records(state)
        remaining = max(0, state["max_attempts"] - state["attempts_claimed"])
        eligible_credits = [
            item["research_credit"]
            for item in ranked
            if item["source_attempt_id"] is not None
        ]
        if not state["research_credit_records"]:
            desired_slots = state["active_pool_capacity"]
        elif 2 in eligible_credits:
            desired_slots = state["active_pool_capacity"]
        else:
            desired_slots = 2
        recommended_slots = min(desired_slots, remaining) if remaining >= 2 else 0
        if cls._singleton_allowed(state):
            recommended_slots = 1
        target_exploration = int(
            (state["attempts_claimed"] + recommended_slots)
            * state["exploration_reserve_fraction"]
            + 0.999999999999
        )
        recommended_exploration = min(
            recommended_slots,
            max(0, target_exploration - state["exploration_consumed_attempts"]),
        )
        actual_fraction = (
            state["exploration_consumed_attempts"] / state["attempts_claimed"]
            if state["attempts_claimed"]
            else 0.0
        )
        return {
            "active_pool_capacity": state["active_pool_capacity"],
            "attempts_remaining": remaining,
            "recommended_active_slots": recommended_slots,
            "recommended_exploration_slots": recommended_exploration,
            "exploration_reserve_fraction": state["exploration_reserve_fraction"],
            "exploration_consumed_attempts": state[
                "exploration_consumed_attempts"
            ],
            "exploitation_consumed_attempts": state[
                "exploitation_consumed_attempts"
            ],
            "actual_exploration_fraction": actual_fraction,
            "ranked_research_parents": ranked,
            "resource_ceiling_bounds": {
                "allowed_resource_classes": sorted(RESOURCE_CLASSES),
                "max_attempts_per_slot": 8,
                "max_time_seconds_per_slot": 7200,
                "max_bytes_per_slot": 10_000_000,
                "max_cost_usd_per_slot": 0.05,
            },
            "selection_policy": "global_pool_with_method_diversity",
            "authority_granted": False,
        }

    def _apply(
        self,
        state: dict[str, Any],
        record: dict[str, Any],
        previous_event_time: datetime | None,
    ) -> datetime | None:
        event = record["event"]
        payload = record["payload"]
        event_time: datetime | None = None
        if event == "initialize":
            keys = {
                "batch_id", "start_utc", "deadline_utc", "max_attempts",
                "boundary_flags", "initial_incumbent",
            }
            item = _exact_mapping(payload, keys, "batch initialization")
            if state["initialized"]:
                raise DiscoveryBatchError("batch initialized more than once")
            start = _utc_text(item["start_utc"], "batch start")
            deadline = _utc_text(item["deadline_utc"], "batch deadline")
            if _utc(start, "batch start") >= _utc(deadline, "batch deadline"):
                raise DiscoveryBatchError("batch deadline must follow batch start")
            event_time = _utc(start, "batch start")
            if type(item["max_attempts"]) is not int or item["max_attempts"] < 1:
                raise DiscoveryBatchError("max_attempts must be a positive integer")
            if item["boundary_flags"] != BOUNDARY_FLAGS:
                raise DiscoveryBatchError("Discovery boundary flags cannot expand")
            incumbent = _initial_incumbent(item["initial_incumbent"])
            state.update(
                initialized=True,
                batch_id=_identifier(item["batch_id"], "batch ID"),
                start_utc=start,
                deadline_utc=deadline,
                max_attempts=item["max_attempts"],
                boundary_flags=dict(BOUNDARY_FLAGS),
                incumbent=incumbent,
                incumbent_history=[incumbent],
            )
        elif event in {"initialize_v2", "initialize_v3", "initialize_v4"}:
            keys = {
                "batch_id", "start_utc", "deadline_utc", "max_attempts",
                "boundary_flags", "initial_incumbent", "active_pool_capacity",
                "exploration_reserve_fraction", "exploration_reserve_reason",
                "initial_archived_parents",
            }
            if event in {"initialize_v3", "initialize_v4"}:
                keys.add("scheduling_policy")
            if event == "initialize_v4":
                keys.add("learning_checkpoint_version")
            item = _exact_mapping(payload, keys, "pool batch initialization")
            if event in {"initialize_v3", "initialize_v4"} and item["scheduling_policy"] != FINAL_SINGLETON_POLICY:
                raise DiscoveryBatchError("unknown scheduling policy")
            if event == "initialize_v4" and (type(item["learning_checkpoint_version"]) is not int or item["learning_checkpoint_version"] != 1):
                raise DiscoveryBatchError("unknown learning checkpoint version")
            if state["initialized"]:
                raise DiscoveryBatchError("batch initialized more than once")
            start = _utc_text(item["start_utc"], "batch start")
            deadline = _utc_text(item["deadline_utc"], "batch deadline")
            if _utc(start, "batch start") >= _utc(deadline, "batch deadline"):
                raise DiscoveryBatchError("batch deadline must follow batch start")
            event_time = _utc(start, "batch start")
            if type(item["max_attempts"]) is not int or item["max_attempts"] < 1:
                raise DiscoveryBatchError("max_attempts must be a positive integer")
            if item["boundary_flags"] != BOUNDARY_FLAGS:
                raise DiscoveryBatchError("Discovery boundary flags cannot expand")
            if type(item["active_pool_capacity"]) is not int or item[
                "active_pool_capacity"
            ] not in {2, 3}:
                raise DiscoveryBatchError("active pool capacity must be 2 or 3")
            reserve = _reserve_fraction(item["exploration_reserve_fraction"])
            reserve_reason = item["exploration_reserve_reason"]
            if reserve == 0.30:
                if reserve_reason is not None:
                    _reason(reserve_reason, "exploration reserve reason")
            elif reserve_reason is None:
                raise DiscoveryBatchError(
                    "non-default exploration reserve requires an append-only reason"
                )
            else:
                _reason(reserve_reason, "exploration reserve reason")
            incumbent = _initial_incumbent(item["initial_incumbent"])
            raw_archived = item["initial_archived_parents"]
            if not isinstance(raw_archived, list):
                raise DiscoveryBatchError("initial archived parents must be a list")
            archive_validator = _archived_parent_v4 if event == "initialize_v4" else _archived_parent
            archived = [archive_validator(parent) for parent in raw_archived]
            for field in (
                "candidate_sha256", "archive_manifest_sha256",
                "question_digest_sha256",
            ):
                values = [parent[field] for parent in archived]
                if len(set(values)) != len(values):
                    raise DiscoveryBatchError("duplicate initial archived parent")
            evidence_keys = {
                (parent["problem_id"], parent["evidence_bundle_sha256"])
                for parent in archived
            }
            source_keys = {
                (parent["source_batch_id"], parent["source_attempt_id"])
                for parent in archived
            }
            if len(evidence_keys) != len(archived) or len(source_keys) != len(archived):
                raise DiscoveryBatchError("duplicate initial archived parent")
            if any(
                parent["candidate_sha256"] == incumbent["candidate_sha256"]
                for parent in archived
            ):
                raise DiscoveryBatchError(
                    "archived research parent must remain separate from incumbent"
                )
            state.update(
                initialized=True,
                batch_id=_identifier(item["batch_id"], "batch ID"),
                start_utc=start,
                deadline_utc=deadline,
                max_attempts=item["max_attempts"],
                boundary_flags=dict(BOUNDARY_FLAGS),
                incumbent=incumbent,
                incumbent_history=[incumbent],
                scheduling_version=2,
                active_pool_capacity=item["active_pool_capacity"],
                exploration_reserve_fraction=reserve,
                exploration_reserve_reason=reserve_reason,
                active_attempt_ids=[],
                pool_generation=0,
                research_credit_records=[],
                exploration_consumed_attempts=0,
                exploitation_consumed_attempts=0,
                initial_archived_parents=archived,
            )
            if event == "initialize_v3":
                state.update(scheduling_version=3, scheduling_policy=FINAL_SINGLETON_POLICY)
            if event == "initialize_v4":
                consumed = {}
                findings = []
                credited_findings = []
                for parent in archived:
                    checkpoint = parent["learning_checkpoint"]
                    allowance = checkpoint["exploration"]["allowance_id_sha256"]
                    if allowance is not None:
                        consumed[allowance] = max(consumed.get(allowance, 0), parent["consumed_followups"])
                    if checkpoint["learning"]["requested_credit"] > 0:
                        findings.append(checkpoint["learning"]["finding_sha256"])
                    if checkpoint["learning"]["credit"] > 0:
                        credited_findings.append(checkpoint["learning"]["finding_sha256"])
                if len(set(credited_findings)) != len(credited_findings):
                    raise DiscoveryBatchError("archive duplicates credited canonical findings")
                state.update(scheduling_version=4, scheduling_policy=FINAL_SINGLETON_POLICY,
                             learning_checkpoint_version=1, learning_checkpoints=[],
                             accepted_finding_sha256s=sorted(set(findings)), bounded_followups_consumed=consumed)
        elif not state["initialized"]:
            raise DiscoveryBatchError("batch event precedes initialization")
        elif event == "micro_evolution":
            item = _exact_mapping(payload, {
                "action", "arguments", "expected_evolution_sha256", "event_time_utc",
            }, "small-step evolution event")
            event_time = _utc(item["event_time_utc"], "evolution time")
            current = state.get("micro_evolution")
            expected = current["record_sha256"] if current else ZERO_SHA256
            if item["expected_evolution_sha256"] != expected:
                raise DiscoveryBatchError("stale evolution state")
            action, arguments = item["action"], item["arguments"]
            if not isinstance(arguments, dict):
                raise DiscoveryBatchError("evolution arguments must be an object")
            if action == "initialize":
                if current is not None or state["branches"] or state.get("scheduling_version") not in {3, 4}:
                    raise DiscoveryBatchError("configure evolution once on a fresh v3 batch")
                operation = lambda: micro_evolution.initialize_micro_evolution(arguments)
            else:
                if current is None:
                    raise DiscoveryBatchError("small-step evolution is not configured")
                operations = {
                    "propose": micro_evolution.propose_micro_evolution,
                    "review": micro_evolution.review_micro_evolution,
                    "rollback": micro_evolution.rollback_micro_evolution,
                }
                if action not in operations:
                    raise DiscoveryBatchError("unknown evolution action")
                if (action == "rollback" or
                        (action == "review" and arguments.get("decision") == "accept")):
                    if state["active_attempt_ids"]:
                        raise DiscoveryBatchError("pair changes require an idle batch")
                operation = lambda: operations[action](current, arguments)
            try:
                state["micro_evolution"] = operation()
            except (ValueError, TypeError, KeyError) as exc:
                raise DiscoveryBatchError(str(exc)) from exc
        elif event == "controller_pool_selected":
            item = _exact_mapping(
                payload,
                {
                    "pool_generation", "comparison_incumbent_sha256",
                    "selection_hint_sha256", "selections", "selected_at_utc",
                },
                "Controller pool selection",
            )
            if not self._is_v2(state):
                raise DiscoveryBatchError("Controller pool selection requires v2")
            selected_at = _utc(item["selected_at_utc"], "selection time")
            if selected_at < _utc(state["start_utc"], "batch start"):
                raise DiscoveryBatchError("Controller selection predates batch start")
            if selected_at >= _utc(state["deadline_utc"], "batch deadline"):
                raise DiscoveryBatchError("Controller selection is at/after the deadline")
            event_time = selected_at
            if state["active_attempt_ids"]:
                raise DiscoveryBatchError("a global Controller pool is already active")
            if item["pool_generation"] != state["pool_generation"] + 1:
                raise DiscoveryBatchError("Controller pool generation changed")
            if item["comparison_incumbent_sha256"] != state["incumbent"][
                "candidate_sha256"
            ]:
                raise DiscoveryBatchError("pool comparison incumbent changed")
            hint = self._pool_selection_hint(state)
            if item["selection_hint_sha256"] != _digest(hint):
                raise DiscoveryBatchError("pool selection hint changed")
            selections = item["selections"]
            if not isinstance(selections, list) or not selections:
                raise DiscoveryBatchError("Controller pool must be a non-empty list")
            if len(selections) < 2 and not self._singleton_allowed(state):
                raise DiscoveryBatchError("active global pool must contain 2 or 3 members")
            if len(selections) > hint["recommended_active_slots"]:
                raise DiscoveryBatchError("Controller pool exceeds its global budget hint")
            if sum(
                selection.get("allocation") == "exploration"
                for selection in selections
                if isinstance(selection, Mapping)
            ) < hint["recommended_exploration_slots"]:
                raise DiscoveryBatchError("Controller pool did not honor exploration reserve")
            eligible_parents = {
                parent["candidate_sha256"]: parent
                for parent in self._eligible_parent_records(state)
            }
            known_parents = set(eligible_parents)
            selected_parent_counts: dict[str, int] = {}
            for selection in selections:
                if isinstance(selection, Mapping):
                    parent_sha = selection.get("research_parent_sha256")
                    selected_parent_counts[parent_sha] = (
                        selected_parent_counts.get(parent_sha, 0) + 1
                    )
            if any(
                count > 1
                and state.get("scheduling_version") != 4
                and eligible_parents.get(parent_sha, {}).get("research_credit") == 1
                for parent_sha, count in selected_parent_counts.items()
            ):
                raise DiscoveryBatchError("credit-1 parent permits one bounded follow-up")
            used_hypotheses = {
                branch.get("hypothesis_digest_sha256") for branch in state["branches"]
            }
            used_questions = {
                branch.get("question_digest_sha256") for branch in state["branches"]
            }
            used_questions.update(
                parent["question_digest_sha256"]
                for parent in state["initial_archived_parents"]
            )
            if state.get("scheduling_version") == 4:
                used_questions.update(q for p in state["initial_archived_parents"] for q in p["consumed_question_sha256s"])
                bounded_parents = {sha: p for sha, p in eligible_parents.items() if p["followups_remaining"] == 1}
                if any(selected_parent_counts.get(sha, 0) > 1 for sha in bounded_parents):
                    raise DiscoveryBatchError("bounded parent permits one distinct follow-up")
                used_allowances = set()
                for selection in selections:
                    parent = bounded_parents.get(selection.get("research_parent_sha256"))
                    if parent is not None:
                        route = parent["learning_checkpoint"]["exploration"]
                        if route["allowance_id_sha256"] in used_allowances:
                            raise DiscoveryBatchError("aliased bounded allowance was selected twice")
                        used_allowances.add(route["allowance_id_sha256"])
                        if route["next_question_sha256"] is not None and selection.get("question_digest_sha256") != route["next_question_sha256"]:
                            raise DiscoveryBatchError("bounded follow-up changed its independently reviewed question")
                        if selection.get("resource_hint", {}).get("max_attempts") != 1:
                            raise DiscoveryBatchError("bounded follow-up permits one small attempt")
            attempt_ids: list[str] = []
            pool_hypotheses: set[str] = set()
            pool_questions: set[str] = set()
            pool_methods: set[str] = set()
            new_branches: list[dict[str, Any]] = []
            existing_attempts = {branch["attempt_id"] for branch in state["branches"]}
            for raw_selection in selections:
                selection = _exact_mapping(
                    raw_selection,
                    {
                        "attempt_id", "candidate_id", "controller_decision_sha256",
                        "research_parent_sha256", "allocation", "method_family",
                        "hypothesis_digest_sha256", "question_id",
                        "question_digest_sha256", "predeclared_rule_sha256",
                        "resource_hint",
                    },
                    "Controller pool member",
                )
                attempt_id = _identifier(selection["attempt_id"], "attempt ID")
                if attempt_id in existing_attempts or attempt_id in attempt_ids:
                    raise DiscoveryBatchError("duplicate Discovery attempt in global pool")
                parent = _sha(selection["research_parent_sha256"], "research parent")
                if parent not in known_parents:
                    raise DiscoveryBatchError("research parent is not an archived branch")
                if selection["allocation"] not in POOL_ALLOCATIONS:
                    raise DiscoveryBatchError("unknown pool allocation")
                method_family = _identifier(selection["method_family"], "method family")
                hypothesis = _sha(
                    selection["hypothesis_digest_sha256"], "hypothesis digest"
                )
                if hypothesis in used_hypotheses or hypothesis in pool_hypotheses:
                    raise DiscoveryBatchError("research hypothesis was already scheduled")
                question_id = _identifier(selection["question_id"], "question ID")
                question_digest = _sha(
                    selection["question_digest_sha256"], "canonical question digest"
                )
                if question_digest in used_questions or question_digest in pool_questions or any(
                    branch.get("question_id") == question_id
                    for branch in state["branches"]
                ):
                    raise DiscoveryBatchError("research question was already scheduled")
                resource = _resource_hint(selection["resource_hint"])
                attempt_ids.append(attempt_id)
                pool_hypotheses.add(hypothesis)
                pool_questions.add(question_digest)
                pool_methods.add(method_family)
                new_branches.append(
                    {
                        "attempt_id": attempt_id,
                        "candidate_id": _identifier(
                            selection["candidate_id"], "candidate ID"
                        ),
                        "controller_decision_sha256": _sha(
                            selection["controller_decision_sha256"],
                            "Controller decision",
                        ),
                        "parent_incumbent_sha256": state["incumbent"][
                            "candidate_sha256"
                        ],
                        "research_parent_sha256": parent,
                        "comparison_incumbent_sha256": state["incumbent"][
                            "candidate_sha256"
                        ],
                        "pool_generation": item["pool_generation"],
                        "allocation": selection["allocation"],
                        "method_family": method_family,
                        "hypothesis_digest_sha256": hypothesis,
                        "question_id": question_id,
                        "question_digest_sha256": question_digest,
                        "predeclared_rule_sha256": _sha(
                            selection["predeclared_rule_sha256"],
                            "predeclared decision rule",
                        ),
                        "resource_hint": resource,
                        "selected_at_utc": _utc_text(selected_at, "selection time"),
                        "stage": "controller_selected",
                        "runner_sha256": None,
                        "spec_sha256": None,
                        "claim_id": None,
                        "attempt_number": None,
                        "claimed_at_utc": None,
                        "execution_outcome": None,
                        "execution_receipt_sha256": None,
                        "terminal_at_utc": None,
                        "scorecard_sha256": None,
                        "review_sha256": None,
                        "review_decision": None,
                        "independently_reviewed": None,
                        "incumbent_before_sha256": None,
                        "incumbent_after_sha256": None,
                        "research_credit": None,
                        "research_credit_evidence_bundle_sha256": None,
                        "research_credit_problem_id": None,
                        "research_credit_reason": None,
                        "authority_snapshot_sha256": None,
                        "research_outcome": None,
                        "route_action": None,
                        "credit_review_sha256": None,
                        "feedback_packet": None,
                        "feedback_packet_sha256": None,
                    }
                )
            if len(new_branches) >= 2 and len(pool_methods) < 2:
                raise DiscoveryBatchError("global pool requires method-family diversity")
            state["branches"].extend(new_branches)
            state["active_attempt_ids"] = attempt_ids
            state["pool_generation"] = item["pool_generation"]
            if state.get("scheduling_version") == 4:
                for selection in selections:
                    parent = bounded_parents.get(selection["research_parent_sha256"])
                    if parent is not None:
                        allowance = parent["learning_checkpoint"]["exploration"]["allowance_id_sha256"]
                        state["bounded_followups_consumed"][allowance] = 1
        elif event == "controller_selected":
            item = _exact_mapping(
                payload,
                {
                    "attempt_id", "candidate_id", "controller_decision_sha256",
                    "parent_incumbent_sha256", "selected_at_utc",
                },
                "controller selection",
            )
            attempt_id = _identifier(item["attempt_id"], "attempt ID")
            selected_at = _utc(item["selected_at_utc"], "selection time")
            if selected_at < _utc(state["start_utc"], "batch start"):
                raise DiscoveryBatchError("Controller selection predates batch start")
            if selected_at >= _utc(state["deadline_utc"], "batch deadline"):
                raise DiscoveryBatchError("Controller selection is at/after the deadline")
            event_time = selected_at
            if state["active_attempt_id"] is not None or any(
                branch["attempt_id"] == attempt_id for branch in state["branches"]
            ):
                raise DiscoveryBatchError("duplicate or overlapping Discovery branch")
            if item["parent_incumbent_sha256"] != state["incumbent"]["candidate_sha256"]:
                raise DiscoveryBatchError("Controller selection is not bound to incumbent")
            branch = {
                "attempt_id": attempt_id,
                "candidate_id": _identifier(item["candidate_id"], "candidate ID"),
                "controller_decision_sha256": _sha(
                    item["controller_decision_sha256"], "Controller decision"
                ),
                "parent_incumbent_sha256": _sha(
                    item["parent_incumbent_sha256"], "parent incumbent"
                ),
                "selected_at_utc": _utc_text(selected_at, "selection time"),
                "stage": "controller_selected",
                "runner_sha256": None,
                "spec_sha256": None,
                "claim_id": None,
                "attempt_number": None,
                "claimed_at_utc": None,
                "execution_outcome": None,
                "execution_receipt_sha256": None,
                "terminal_at_utc": None,
                "scorecard_sha256": None,
                "review_sha256": None,
                "review_decision": None,
                "independently_reviewed": None,
                "incumbent_before_sha256": None,
                "incumbent_after_sha256": None,
                "feedback_packet": None,
                "feedback_packet_sha256": None,
            }
            state["branches"].append(branch)
            state["active_attempt_id"] = attempt_id
        elif event == "implementation_ready":
            item, event_time = _mapping_with_optional_event_time(
                payload,
                {"attempt_id", "runner_sha256", "spec_sha256"},
                "implementation-ready event",
            )
            branch = self._branch(state, _identifier(item["attempt_id"], "attempt ID"))
            if branch["stage"] != "controller_selected":
                raise DiscoveryBatchError("implementation-ready transition is out of order")
            branch["runner_sha256"] = _sha(item["runner_sha256"], "runner")
            branch["spec_sha256"] = _sha(item["spec_sha256"], "experiment spec")
            branch["stage"] = "implementation_ready"
        elif event == "execution_claimed":
            binding_fields = ({"runtime_pair_sha256", "memory_snapshot_sha256"}
                              if "micro_evolution" in state else set())
            item = _exact_mapping(
                payload,
                {
                    "attempt_id", "claim_id", "attempt_number", "claimed_at_utc",
                    "runner_sha256", "spec_sha256",
                } | binding_fields,
                "execution claim",
            )
            branch = self._branch(state, _identifier(item["attempt_id"], "attempt ID"))
            claimed_at = _utc(item["claimed_at_utc"], "claim time")
            if claimed_at < _utc(branch["selected_at_utc"], "selection time"):
                raise DiscoveryBatchError("execution claim predates Controller selection")
            if claimed_at >= _utc(state["deadline_utc"], "batch deadline"):
                raise DiscoveryBatchError("execution claim is at/after the deadline")
            event_time = claimed_at
            if branch["stage"] != "implementation_ready":
                raise DiscoveryBatchError("execution claim is out of order")
            if state["attempts_claimed"] >= state["max_attempts"]:
                raise DiscoveryBatchError("journal exceeds the batch attempt limit")
            if (
                item["runner_sha256"] != branch["runner_sha256"]
                or item["spec_sha256"] != branch["spec_sha256"]
            ):
                raise DiscoveryBatchError("execution claim changed runner/spec bindings")
            expected_number = state["attempts_claimed"] + 1
            if item["attempt_number"] != expected_number:
                raise DiscoveryBatchError("execution attempt number changed")
            if binding_fields:
                if item["runtime_pair_sha256"] != micro_evolution.micro_pair_hash(state["micro_evolution"]):
                    raise DiscoveryBatchError("execution pair differs from active pair")
                _sha(item["memory_snapshot_sha256"], "memory snapshot")
                branch.update({key: item[key] for key in binding_fields})
            branch.update(
                claim_id=_identifier(item["claim_id"], "execution claim ID"),
                attempt_number=expected_number,
                claimed_at_utc=_utc_text(claimed_at, "claim time"),
                stage="execution_claimed",
            )
            state["attempts_claimed"] = expected_number
            if self._is_v2(state):
                counter = (
                    "exploration_consumed_attempts"
                    if branch["allocation"] == "exploration"
                    else "exploitation_consumed_attempts"
                )
                state[counter] += 1
        elif event == "execution_terminal":
            item = _exact_mapping(
                payload,
                {
                    "attempt_id", "claim_id", "outcome",
                    "execution_receipt_sha256", "terminal_at_utc",
                },
                "execution terminal",
            )
            branch = self._branch(state, _identifier(item["attempt_id"], "attempt ID"))
            terminal_at = _utc(item["terminal_at_utc"], "terminal time")
            if terminal_at < _utc(branch["claimed_at_utc"], "claim time"):
                raise DiscoveryBatchError("execution terminal predates its claim")
            event_time = terminal_at
            if branch["stage"] != "execution_claimed" or item["claim_id"] != branch["claim_id"]:
                raise DiscoveryBatchError("execution terminal does not match its claim")
            if item["outcome"] not in EXECUTION_OUTCOMES:
                raise DiscoveryBatchError("unknown execution outcome")
            branch.update(
                execution_outcome=item["outcome"],
                execution_receipt_sha256=_sha(
                    item["execution_receipt_sha256"], "execution receipt"
                ),
                terminal_at_utc=_utc_text(terminal_at, "terminal time"),
                stage="execution_terminal",
            )
            if item["outcome"] != "succeeded":
                state["failed_attempts"] += 1
        elif event == "result_reviewed":
            item, event_time = _mapping_with_optional_event_time(
                payload,
                {
                    "attempt_id", "decision", "scorecard_sha256", "review_sha256",
                    "independently_reviewed",
                } | ({"performance_validity"} if state.get("scheduling_version") == 4 else set()),
                "result review",
            )
            branch = self._branch(state, _identifier(item["attempt_id"], "attempt ID"))
            if branch["stage"] != "execution_terminal":
                raise DiscoveryBatchError("result review is out of order")
            if item["decision"] not in REVIEW_DECISIONS:
                raise DiscoveryBatchError("result review must be KEEP or REVERT")
            if type(item["independently_reviewed"]) is not bool:
                raise DiscoveryBatchError("independent-review flag must be boolean")
            if state.get("scheduling_version") == 4:
                try:
                    validity = validate_validity(item["performance_validity"], {
                        "review_decision": item["decision"], "review_sha256": item["review_sha256"],
                        "execution_outcome": branch["execution_outcome"],
                        "independently_reviewed": item["independently_reviewed"],
                    })
                except (ValueError, TypeError, KeyError) as exc:
                    raise DiscoveryBatchError(str(exc)) from exc
                branch["performance_validity"] = validity
            if item["decision"] == "KEEP" and (
                item["independently_reviewed"] is not True
                or branch["execution_outcome"] != "succeeded"
            ):
                raise DiscoveryBatchError(
                    "KEEP requires a successful execution and independent review"
                )
            if (
                self._is_v2(state)
                and item["decision"] == "KEEP"
                and branch["comparison_incumbent_sha256"]
                != state["incumbent"]["candidate_sha256"]
            ):
                raise DiscoveryBatchError(
                    "KEEP comparison incumbent is stale; review must remain non-promoting"
                )
            before = (
                branch["comparison_incumbent_sha256"]
                if self._is_v2(state)
                else state["incumbent"]["candidate_sha256"]
            )
            after = before
            scorecard = _sha(item["scorecard_sha256"], "scorecard")
            review = _sha(item["review_sha256"], "independent review")
            if item["decision"] == "KEEP":
                after = branch["runner_sha256"]
                incumbent = {
                    "candidate_id": branch["candidate_id"],
                    "candidate_sha256": after,
                    "scorecard_sha256": scorecard,
                    "review_sha256": review,
                    "source": "independently_reviewed_keep",
                    "updated_by_attempt_id": branch["attempt_id"],
                }
                state["incumbent"] = incumbent
                state["incumbent_history"].append(incumbent)
            branch.update(
                scorecard_sha256=scorecard,
                review_sha256=review,
                review_decision=item["decision"],
                independently_reviewed=item["independently_reviewed"],
                incumbent_before_sha256=before,
                incumbent_after_sha256=after,
                stage="result_reviewed",
            )
        elif event == "learning_checkpoint_recorded":
            item, event_time = _mapping_with_optional_event_time(payload, {"attempt_id", "assessment"}, "learning checkpoint")
            if state.get("scheduling_version") != 4:
                raise DiscoveryBatchError("learning checkpoint requires explicit v4 opt-in")
            branch = self._branch(state, _identifier(item["attempt_id"], "attempt ID"))
            if branch["stage"] != "result_reviewed" or branch["research_credit"] is not None:
                raise DiscoveryBatchError("checkpoint requires one unassessed reviewed result")
            try:
                assessment = assess_checkpoint(item["assessment"], branch, set(state["accepted_finding_sha256s"]))
            except (ValueError, TypeError, KeyError) as exc:
                raise DiscoveryBatchError(str(exc)) from exc
            learning = assessment["learning"]
            branch.update(learning_checkpoint=assessment, research_credit=learning["credit"],
                          research_credit_evidence_bundle_sha256=learning["evidence_sha256"],
                          research_credit_problem_id=branch["question_id"], research_credit_reason=learning["reason"],
                          authority_snapshot_sha256=assessment["authority_snapshot_sha256"],
                          research_outcome="invalid" if assessment["validity"]["status"] != "valid" else "inconclusive",
                          route_action=assessment["exploration"]["action"], credit_review_sha256=learning["review_sha256"])
            state["learning_checkpoints"].append({"attempt_id": branch["attempt_id"], "assessment": assessment})
            state["research_credit_records"].append({"attempt_id": branch["attempt_id"], "credit": learning["credit"]})
            if learning["credit"] > 0:
                state["accepted_finding_sha256s"].append(learning["finding_sha256"])
        elif event == "research_credit_recorded":
            if state.get("scheduling_version") == 4:
                raise DiscoveryBatchError("v4 requires separate learning checkpoint assessment")
            item, event_time = _mapping_with_optional_event_time(
                payload,
                {
                    "attempt_id", "credit", "evidence_bundle_sha256", "problem_id",
                    "reason", "question_id", "question_digest_sha256",
                    "authority_snapshot_sha256", "result_review_sha256",
                    "predeclared_rule_sha256", "outcome", "route_action",
                    "credit_review_sha256",
                },
                "research credit",
            )
            if not self._is_v2(state):
                raise DiscoveryBatchError("research credit requires a v2 batch")
            branch = self._branch(state, _identifier(item["attempt_id"], "attempt ID"))
            if branch["stage"] != "result_reviewed":
                raise DiscoveryBatchError("research credit requires a reviewed result")
            if branch["research_credit"] is not None:
                raise DiscoveryBatchError("research credit was already recorded")
            if type(item["credit"]) is not int or item["credit"] not in {0, 1, 2}:
                raise DiscoveryBatchError("research credit must be 0, 1, or 2")
            outcome = item["outcome"]
            action = item["route_action"]
            if outcome not in RESEARCH_OUTCOMES or action not in ROUTE_ACTIONS:
                raise DiscoveryBatchError("invalid research outcome or route action")
            valid_route = (
                item["credit"] == 0
                and outcome == "invalid"
                and action in {"cooldown", "stop"}
            ) or (
                item["credit"] == 1
                and outcome == "inconclusive"
                and action == "bounded_followup"
            ) or (
                item["credit"] == 2
                and outcome == "support"
                and action == "continue"
            ) or (
                item["credit"] == 2
                and outcome == "refute"
                and action in {"cooldown", "stop"}
            ) or (
                state.get("scheduling_version") == 3
                and item["credit"] == 2 and outcome == "refute" and action == "branch"
            )
            if not valid_route:
                raise DiscoveryBatchError("credit/outcome/route action contract changed")
            if item["credit"] > 0 and (
                branch["execution_outcome"] != "succeeded"
                or branch["independently_reviewed"] is not True
            ):
                raise DiscoveryBatchError(
                    "positive research credit requires succeeded, independent evidence"
                )
            result_review = _sha(item["result_review_sha256"], "result review")
            if result_review != branch["review_sha256"]:
                raise DiscoveryBatchError("credit is not bound to the result review")
            evidence = _sha(
                item["evidence_bundle_sha256"], "research-credit evidence bundle"
            )
            problem = _identifier(item["problem_id"], "problem ID")
            question_digest = _sha(
                item["question_digest_sha256"], "canonical question digest"
            )
            question = _identifier(item["question_id"], "question ID")
            predeclared_rule = _sha(
                item["predeclared_rule_sha256"], "predeclared decision rule"
            )
            if (
                question != branch["question_id"]
                or question_digest != branch["question_digest_sha256"]
                or predeclared_rule != branch["predeclared_rule_sha256"]
            ):
                raise DiscoveryBatchError("credit changed the predeclared question")
            if any(
                prior["question_id"] == question
                or prior["question_digest_sha256"] == question_digest
                or (
                    prior["problem_id"] == problem
                    and prior["evidence_bundle_sha256"] == evidence
                )
                for prior in state["research_credit_records"]
            ) or any(
                archived["question_digest_sha256"] == question_digest
                or (
                    archived["problem_id"] == problem
                    and archived["evidence_bundle_sha256"] == evidence
                )
                for archived in state["initial_archived_parents"]
            ):
                raise DiscoveryBatchError("research question or evidence is a duplicate")
            record = {
                "attempt_id": branch["attempt_id"],
                "credit": item["credit"],
                "evidence_bundle_sha256": evidence,
                "problem_id": problem,
                "reason": _reason(item["reason"], "research-credit reason"),
                "question_id": question,
                "question_digest_sha256": question_digest,
                "authority_snapshot_sha256": _sha(
                    item["authority_snapshot_sha256"], "authority snapshot"
                ),
                "result_review_sha256": result_review,
                "predeclared_rule_sha256": predeclared_rule,
                "outcome": outcome,
                "route_action": action,
                "credit_review_sha256": _sha(
                    item["credit_review_sha256"], "independent credit review"
                ),
            }
            branch.update(
                research_credit=record["credit"],
                research_credit_evidence_bundle_sha256=record[
                    "evidence_bundle_sha256"
                ],
                research_credit_problem_id=record["problem_id"],
                research_credit_reason=record["reason"],
                question_id=record["question_id"],
                question_digest_sha256=record["question_digest_sha256"],
                authority_snapshot_sha256=record["authority_snapshot_sha256"],
                predeclared_rule_sha256=record["predeclared_rule_sha256"],
                research_outcome=record["outcome"],
                route_action=record["route_action"],
                credit_review_sha256=record["credit_review_sha256"],
            )
            state["research_credit_records"].append(record)
        elif event == "controller_feedback_ready":
            item, event_time = _mapping_with_optional_event_time(
                payload,
                {"attempt_id", "packet", "packet_sha256"},
                "Controller feedback",
            )
            branch = self._branch(state, _identifier(item["attempt_id"], "attempt ID"))
            if branch["stage"] != "result_reviewed":
                raise DiscoveryBatchError("Controller feedback is out of order")
            if self._is_v2(state) and branch["research_credit"] is None:
                raise DiscoveryBatchError(
                    "v2 Controller feedback requires a research-credit record"
                )
            expected = (
                self._evidence_packet_v2(state, branch)
                if self._is_v2(state)
                else self._evidence_packet(state, branch)
            )
            if item["packet"] != expected or item["packet_sha256"] != _digest(expected):
                raise DiscoveryBatchError("Controller evidence packet changed")
            branch.update(
                feedback_packet=expected,
                feedback_packet_sha256=item["packet_sha256"],
                stage=TERMINAL_STAGE,
            )
            if self._is_v2(state):
                if branch["attempt_id"] not in state["active_attempt_ids"]:
                    raise DiscoveryBatchError("terminal branch is absent from active pool")
                state["active_attempt_ids"].remove(branch["attempt_id"])
            else:
                state["active_attempt_id"] = None
        elif event == "batch_stopped":
            item = _exact_mapping(payload, {"reason", "stopped_at_utc"}, "batch stop")
            if state["stopped_reason"] is not None:
                raise DiscoveryBatchError("batch stopped more than once")
            if item["reason"] not in {"deadline_reached", "max_attempts_reached"}:
                raise DiscoveryBatchError("unknown batch stop reason")
            stopped_at = _utc(item["stopped_at_utc"], "batch stop time")
            if (
                item["reason"] == "deadline_reached"
                and stopped_at < _utc(state["deadline_utc"], "batch deadline")
            ):
                raise DiscoveryBatchError("deadline stop predates the deadline")
            event_time = stopped_at
            state["stopped_reason"] = item["reason"]
        else:
            raise DiscoveryBatchError("unknown continuous-Discovery event")
        event_time = event_time or previous_event_time
        if (
            event_time is not None
            and previous_event_time is not None
            and event_time < previous_event_time
        ):
            raise DiscoveryBatchError("continuous-Discovery event time moved backward")
        return event_time

    def _replay(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        state = self._empty_state()
        event_time: datetime | None = None
        for record in records:
            event_time = self._apply(state, record, event_time)
            state["journal_length"] = record["sequence"]
            state["journal_head_sha256"] = record["event_sha256"]
        if state["initialized"] and state["attempts_claimed"] >= state["max_attempts"]:
            state["stopped_reason"] = state["stopped_reason"] or "max_attempts_reached"
        return _with_state_hash(state)

    def _read_snapshot(self) -> dict[str, Any] | None:
        root_fd = self._open_root()
        try:
            try:
                raw = _read_regular_at(
                    root_fd,
                    "batch.json",
                    max_bytes=8 * 1024 * 1024,
                    label="batch snapshot",
                )
            except DiscoveryBatchError as exc:
                try:
                    os.stat("batch.json", dir_fd=root_fd, follow_symlinks=False)
                except FileNotFoundError:
                    return None
                raise exc
        finally:
            os.close(root_fd)
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DiscoveryBatchError("batch snapshot is corrupt") from exc
        if not isinstance(value, dict) or raw != _canonical(value) + b"\n":
            raise DiscoveryBatchError("batch snapshot is not canonical JSON")
        if value.get("schema") != SCHEMA or value.get("state_sha256") != _state_hash(value):
            raise DiscoveryBatchError("batch snapshot hash changed")
        return value

    def _write_snapshot(self, state: dict[str, Any]) -> None:
        if state.get("state_sha256") != _state_hash(state):
            raise DiscoveryBatchError("refusing to write an invalid batch snapshot")
        fd, temporary = tempfile.mkstemp(prefix=".continuous-discovery-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(_canonical(state) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.snapshot_path)
            directory_fd = self._open_root()
            try:
                os.fsync(directory_fd)
                raw = _read_regular_at(
                    directory_fd,
                    "batch.json",
                    max_bytes=8 * 1024 * 1024,
                    label="batch snapshot",
                )
                if raw != _canonical(state) + b"\n":
                    raise DiscoveryBatchError("published batch snapshot changed")
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _load_locked(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        records = self._read_records()
        replayed = self._replay(records)
        snapshot = self._read_snapshot()
        if snapshot is None:
            if records:
                self._write_snapshot(replayed)
            return records, replayed
        if snapshot == replayed:
            return records, replayed
        length = snapshot.get("journal_length")
        if type(length) is not int or length < 0 or length >= len(records):
            raise DiscoveryBatchError("batch snapshot diverges from its journal")
        prefix = self._replay(records[:length])
        if snapshot != prefix:
            raise DiscoveryBatchError("batch snapshot is not a valid journal prefix")
        self._write_snapshot(replayed)
        return records, replayed

    def _commit(
        self,
        records: list[dict[str, Any]],
        event: str,
        payload: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        updated = self._append_record(records, event, payload)
        state = self._replay(updated)
        self._write_snapshot(state)
        return updated, state

    @staticmethod
    def _public(state: dict[str, Any]) -> dict[str, Any]:
        return json.loads(json.dumps(state))

    @staticmethod
    def _assert_live_batch(state: dict[str, Any], now: datetime) -> None:
        if now < _utc(state["start_utc"], "batch start"):
            raise DiscoveryBatchError("continuous Discovery batch has not started")
        if state["stopped_reason"] is not None:
            raise BatchStoppedError(state["stopped_reason"])
        if state["attempts_claimed"] >= state["max_attempts"]:
            raise BatchStoppedError("max_attempts_reached")
        if now >= _utc(state["deadline_utc"], "batch deadline"):
            raise BatchStoppedError("deadline_reached")

    @staticmethod
    def _evidence_packet(
        state: dict[str, Any], branch: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "schema": EVIDENCE_SCHEMA,
            "batch_id": state["batch_id"],
            "attempt_id": branch["attempt_id"],
            "attempt_number": branch["attempt_number"],
            "candidate_id": branch["candidate_id"],
            "execution_outcome": branch["execution_outcome"],
            "review_decision": branch["review_decision"],
            "independently_reviewed": branch["independently_reviewed"],
            "runner_sha256": branch["runner_sha256"],
            "spec_sha256": branch["spec_sha256"],
            "execution_receipt_sha256": branch["execution_receipt_sha256"],
            "scorecard_sha256": branch["scorecard_sha256"],
            "review_sha256": branch["review_sha256"],
            "incumbent_before_sha256": branch["incumbent_before_sha256"],
            "incumbent_after_sha256": branch["incumbent_after_sha256"],
            "attempts_claimed": state["attempts_claimed"],
            "attempts_remaining": state["max_attempts"] - state["attempts_claimed"],
            "evidence_scope": "reused_opened_train_discovery_only",
            "authority_granted": False,
        }

    @classmethod
    def _evidence_packet_v2(
        cls, state: dict[str, Any], branch: dict[str, Any]
    ) -> dict[str, Any]:
        packet = {
            "schema": EVIDENCE_SCHEMA_V2,
            "batch_id": state["batch_id"],
            "pool_generation": branch["pool_generation"],
            "attempt_id": branch["attempt_id"],
            "attempt_number": branch["attempt_number"],
            "candidate_id": branch["candidate_id"],
            "research_parent_sha256": branch["research_parent_sha256"],
            "comparison_incumbent_sha256": branch[
                "comparison_incumbent_sha256"
            ],
            "allocation": branch["allocation"],
            "method_family": branch["method_family"],
            "hypothesis_digest_sha256": branch["hypothesis_digest_sha256"],
            "resource_hint": branch["resource_hint"],
            "execution_outcome": branch["execution_outcome"],
            "review_decision": branch["review_decision"],
            "independently_reviewed": branch["independently_reviewed"],
            "runner_sha256": branch["runner_sha256"],
            "spec_sha256": branch["spec_sha256"],
            "execution_receipt_sha256": branch["execution_receipt_sha256"],
            "scorecard_sha256": branch["scorecard_sha256"],
            "review_sha256": branch["review_sha256"],
            "incumbent_before_sha256": branch["incumbent_before_sha256"],
            "incumbent_after_sha256": branch["incumbent_after_sha256"],
            "research_credit": {
                "value": branch["research_credit"],
                "evidence_bundle_sha256": branch[
                    "research_credit_evidence_bundle_sha256"
                ],
                "problem_id": branch["research_credit_problem_id"],
                "reason": branch["research_credit_reason"],
                "question_id": branch["question_id"],
                "question_digest_sha256": branch["question_digest_sha256"],
                "authority_snapshot_sha256": branch[
                    "authority_snapshot_sha256"
                ],
                "result_review_sha256": branch["review_sha256"],
                "predeclared_rule_sha256": branch["predeclared_rule_sha256"],
                "outcome": branch["research_outcome"],
                "route_action": branch["route_action"],
                "credit_review_sha256": branch["credit_review_sha256"],
            },
            "next_pool_selection_hint": cls._pool_selection_hint(state),
            "attempts_claimed": state["attempts_claimed"],
            "attempts_remaining": state["max_attempts"] - state["attempts_claimed"],
            "evidence_scope": "reused_opened_train_discovery_only",
            "authority_granted": False,
        }
        if "micro_evolution" in state:
            packet["research_system"] = {
                "runtime_pair_sha256": branch.get("runtime_pair_sha256"),
                "memory_snapshot_sha256": branch.get("memory_snapshot_sha256"),
            }
        if state.get("scheduling_version") == 4:
            packet.update(schema=EVIDENCE_SCHEMA_V4, protocol_version=4,
                          learning_checkpoint=branch["learning_checkpoint"])
        return packet

    def initialize(
        self,
        *,
        batch_id: str,
        start_utc: str | datetime,
        deadline_utc: str | datetime,
        max_attempts: int,
        initial_incumbent: Mapping[str, Any],
        boundary_flags: Mapping[str, bool] = BOUNDARY_FLAGS,
        active_pool_capacity: int | None = None,
        exploration_reserve_fraction: float = 0.30,
        exploration_reserve_reason: str | None = None,
        initial_archived_parents: list[Mapping[str, Any]] | None = None,
        scheduling_policy: str | None = None,
        learning_checkpoint_version: int | None = None,
    ) -> dict[str, Any]:
        start = _utc_text(start_utc, "batch start")
        deadline = _utc_text(deadline_utc, "batch deadline")
        if _utc(start, "batch start") >= _utc(deadline, "batch deadline"):
            raise DiscoveryBatchError("batch deadline must follow batch start")
        if type(max_attempts) is not int or max_attempts < 1:
            raise DiscoveryBatchError("max_attempts must be a positive integer")
        if dict(boundary_flags) != BOUNDARY_FLAGS:
            raise DiscoveryBatchError("Discovery boundary flags cannot expand")
        if active_pool_capacity is not None and (
            type(active_pool_capacity) is not int or active_pool_capacity not in {2, 3}
        ):
            raise DiscoveryBatchError("active pool capacity must be 2 or 3")
        if scheduling_policy is not None and (
            scheduling_policy != FINAL_SINGLETON_POLICY or active_pool_capacity is None
        ):
            raise DiscoveryBatchError("known scheduling policy requires an active pool")
        if learning_checkpoint_version is not None:
            if type(learning_checkpoint_version) is not int or learning_checkpoint_version != 1 or active_pool_capacity is None:
                raise DiscoveryBatchError("learning checkpoint version 1 requires an explicit active pool")
            scheduling_policy = FINAL_SINGLETON_POLICY
        reserve = _reserve_fraction(exploration_reserve_fraction)
        if active_pool_capacity is None and reserve != 0.30:
            raise DiscoveryBatchError(
                "exploration reserve requires an active v2 pool declaration"
            )
        if active_pool_capacity is None and exploration_reserve_reason is not None:
            raise DiscoveryBatchError(
                "exploration reserve reason requires an active v2 pool declaration"
            )
        if initial_archived_parents is None:
            checked_archived: list[dict[str, Any]] = []
        elif not isinstance(initial_archived_parents, list):
            raise DiscoveryBatchError("initial archived parents must be a list")
        else:
            checked_archived = [
                (_archived_parent_v4 if learning_checkpoint_version is not None else _archived_parent)(parent)
                for parent in initial_archived_parents
            ]
        if active_pool_capacity is None and checked_archived:
            raise DiscoveryBatchError("archived parents require an active v2 pool")
        for field in (
            "candidate_sha256", "archive_manifest_sha256", "question_digest_sha256"
        ):
            values = [parent[field] for parent in checked_archived]
            if len(set(values)) != len(values):
                raise DiscoveryBatchError("duplicate initial archived parent")
        if len(
            {
                (parent["problem_id"], parent["evidence_bundle_sha256"])
                for parent in checked_archived
            }
        ) != len(checked_archived) or len(
            {
                (parent["source_batch_id"], parent["source_attempt_id"])
                for parent in checked_archived
            }
        ) != len(checked_archived):
            raise DiscoveryBatchError("duplicate initial archived parent")
        if active_pool_capacity is not None:
            if reserve != 0.30 and exploration_reserve_reason is None:
                raise DiscoveryBatchError(
                    "non-default exploration reserve requires an append-only reason"
                )
            if exploration_reserve_reason is not None:
                exploration_reserve_reason = _reason(
                    exploration_reserve_reason, "exploration reserve reason"
                )
        checked_incumbent = _initial_incumbent(initial_incumbent)
        if any(
            parent["candidate_sha256"] == checked_incumbent["candidate_sha256"]
            for parent in checked_archived
        ):
            raise DiscoveryBatchError(
                "archived research parent must remain separate from incumbent"
            )
        payload = {
            "batch_id": _identifier(batch_id, "batch ID"),
            "start_utc": start,
            "deadline_utc": deadline,
            "max_attempts": max_attempts,
            "boundary_flags": dict(boundary_flags),
            "initial_incumbent": {
                key: checked_incumbent[key]
                for key in (
                    "candidate_id", "candidate_sha256",
                    "scorecard_sha256", "review_sha256",
                )
            },
        }
        event = "initialize"
        if active_pool_capacity is not None:
            event = "initialize_v2"
            payload.update(
                active_pool_capacity=active_pool_capacity,
                exploration_reserve_fraction=reserve,
                exploration_reserve_reason=exploration_reserve_reason,
                initial_archived_parents=checked_archived,
            )
            if scheduling_policy is not None:
                event = "initialize_v3"
                payload["scheduling_policy"] = scheduling_policy
            if learning_checkpoint_version is not None:
                event = "initialize_v4"
                payload["learning_checkpoint_version"] = learning_checkpoint_version
        with self._locked():
            records, state = self._load_locked()
            if records or state["initialized"]:
                raise FileExistsError("continuous Discovery batch already initialized")
            _, state = self._commit(records, event, payload)
            return self._public(state)

    def snapshot(self) -> dict[str, Any]:
        with self._locked():
            _, state = self._load_locked()
            if not state["initialized"]:
                raise DiscoveryBatchError("continuous Discovery batch is not initialized")
            return self._public(state)

    def record_micro_evolution(
        self, action: str, arguments: Mapping[str, Any], *,
        expected_state_sha256: str, now: str | datetime | None = None,
    ) -> dict[str, Any]:
        """Supervisor-only evidence recording, not permission or code deployment.

        Uses the existing lock/journal. The caller must independently verify
        review receipts and actual source/runtime identity outside the candidate.
        A pending proposal does not prevent ordinary parent-pair research.
        """
        expected = _sha(expected_state_sha256, "expected batch state")
        moment = self._trusted_now(now, "evolution time")
        with self._locked():
            records, state = self._load_locked()
            if state["state_sha256"] != expected:
                raise DiscoveryBatchError("stale batch state")
            if not state["initialized"]:
                raise DiscoveryBatchError("batch is not initialized")
            if moment < _utc(state["start_utc"], "batch start"):
                raise DiscoveryBatchError("evolution event predates batch start")
            current = state.get("micro_evolution")
            _, state = self._commit(records, "micro_evolution", {
                "action": action, "arguments": dict(arguments),
                "expected_evolution_sha256": current["record_sha256"] if current else ZERO_SHA256,
                "event_time_utc": _utc_text(moment, "evolution time"),
            })
            return self._public(state)

    def _stop_locked(
        self,
        records: list[dict[str, Any]],
        state: dict[str, Any],
        now: datetime,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        reason = None
        if state["attempts_claimed"] >= state["max_attempts"]:
            reason = "max_attempts_reached"
        elif now >= _utc(state["deadline_utc"], "batch deadline"):
            reason = "deadline_reached"
        if reason is None or state["stopped_reason"] is not None:
            return records, state
        return self._commit(
            records,
            "batch_stopped",
            {"reason": reason, "stopped_at_utc": _utc_text(now, "stop time")},
        )

    def stop_if_due(self, *, now: str | datetime | None = None) -> dict[str, Any]:
        moment = self._trusted_now(now, "stop time")
        with self._locked():
            records, state = self._load_locked()
            records, state = self._stop_locked(records, state, moment)
            return self._public(state)

    def select_controller_candidate(
        self,
        attempt_id: str,
        *,
        candidate_id: str,
        controller_decision_sha256: str,
        now: str | datetime | None = None,
    ) -> dict[str, Any]:
        attempt_id = _identifier(attempt_id, "attempt ID")
        candidate_id = _identifier(candidate_id, "candidate ID")
        decision = _sha(controller_decision_sha256, "Controller decision")
        moment = self._trusted_now(now, "selection time")
        with self._locked():
            records, state = self._load_locked()
            if self._is_v2(state):
                raise DiscoveryBatchError(
                    "v2 batches require one global select_controller_pool call"
                )
            existing = next(
                (item for item in state["branches"] if item["attempt_id"] == attempt_id),
                None,
            )
            if existing is not None:
                if (
                    existing["candidate_id"] == candidate_id
                    and existing["controller_decision_sha256"] == decision
                ):
                    return self._public(state)
                raise DiscoveryBatchError("attempt ID was reused with different selection")
            records, state = self._stop_locked(records, state, moment)
            self._assert_live_batch(state, moment)
            if state["active_attempt_id"] is not None:
                raise DiscoveryBatchError("another exploratory branch is active")
            _, state = self._commit(
                records,
                "controller_selected",
                {
                    "attempt_id": attempt_id,
                    "candidate_id": candidate_id,
                    "controller_decision_sha256": decision,
                    "parent_incumbent_sha256": state["incumbent"]["candidate_sha256"],
                    "selected_at_utc": _utc_text(moment, "selection time"),
                },
            )
            return self._public(state)

    def pool_selection_hint(self) -> dict[str, Any]:
        with self._locked():
            _, state = self._load_locked()
            return self._public(self._pool_selection_hint(state))

    def select_controller_pool(
        self,
        selections: list[Mapping[str, Any]],
        *,
        now: str | datetime | None = None,
    ) -> dict[str, Any]:
        if not isinstance(selections, list) or not selections:
            raise DiscoveryBatchError("Controller pool must be a non-empty list")
        checked: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in selections:
            item = _exact_mapping(
                raw,
                {
                    "attempt_id", "candidate_id", "controller_decision_sha256",
                    "research_parent_sha256", "allocation", "method_family",
                    "hypothesis_digest_sha256", "question_id",
                    "question_digest_sha256", "predeclared_rule_sha256",
                    "resource_hint",
                },
                "Controller pool member",
            )
            attempt_id = _identifier(item["attempt_id"], "attempt ID")
            if attempt_id in seen:
                raise DiscoveryBatchError("duplicate Discovery attempt in global pool")
            seen.add(attempt_id)
            allocation = item["allocation"]
            if allocation not in POOL_ALLOCATIONS:
                raise DiscoveryBatchError("unknown pool allocation")
            checked.append(
                {
                    "attempt_id": attempt_id,
                    "candidate_id": _identifier(item["candidate_id"], "candidate ID"),
                    "controller_decision_sha256": _sha(
                        item["controller_decision_sha256"], "Controller decision"
                    ),
                    "research_parent_sha256": _sha(
                        item["research_parent_sha256"], "research parent"
                    ),
                    "allocation": allocation,
                    "method_family": _identifier(
                        item["method_family"], "method family"
                    ),
                    "hypothesis_digest_sha256": _sha(
                        item["hypothesis_digest_sha256"], "hypothesis digest"
                    ),
                    "question_id": _identifier(item["question_id"], "question ID"),
                    "question_digest_sha256": _sha(
                        item["question_digest_sha256"], "canonical question digest"
                    ),
                    "predeclared_rule_sha256": _sha(
                        item["predeclared_rule_sha256"],
                        "predeclared decision rule",
                    ),
                    "resource_hint": _resource_hint(item["resource_hint"]),
                }
            )
        moment = self._trusted_now(now, "selection time")
        with self._locked():
            records, state = self._load_locked()
            if not self._is_v2(state):
                raise DiscoveryBatchError("global Controller pools require a v2 batch")
            existing = {
                branch["attempt_id"]: branch
                for branch in state["branches"]
                if branch["attempt_id"] in seen
            }
            if existing:
                if set(existing) == seen and state["active_attempt_ids"] == [
                    item["attempt_id"] for item in checked
                ] and all(
                    existing[item["attempt_id"]][field] == item[field]
                    for item in checked
                    for field in (
                        "candidate_id", "controller_decision_sha256",
                        "research_parent_sha256", "allocation", "method_family",
                        "hypothesis_digest_sha256", "question_id",
                        "question_digest_sha256", "predeclared_rule_sha256",
                        "resource_hint",
                    )
                ):
                    return self._public(state)
                raise DiscoveryBatchError("attempt ID was reused with different selection")
            records, state = self._stop_locked(records, state, moment)
            self._assert_live_batch(state, moment)
            if state["active_attempt_ids"]:
                raise DiscoveryBatchError("a global Controller pool is already active")
            hint = self._pool_selection_hint(state)
            if len(checked) < 2 and not self._singleton_allowed(state):
                raise DiscoveryBatchError("active global pool must contain 2 or 3 members")
            if len(checked) > hint["recommended_active_slots"]:
                raise DiscoveryBatchError("Controller pool exceeds its global budget hint")
            if sum(
                item["allocation"] == "exploration" for item in checked
            ) < hint["recommended_exploration_slots"]:
                raise DiscoveryBatchError("Controller pool did not honor exploration reserve")
            if len(checked) >= 2 and len(
                {item["method_family"] for item in checked}
            ) < 2:
                raise DiscoveryBatchError("global pool requires method-family diversity")
            prior_hypotheses = {
                branch.get("hypothesis_digest_sha256") for branch in state["branches"]
            }
            hypotheses = [item["hypothesis_digest_sha256"] for item in checked]
            if len(set(hypotheses)) != len(hypotheses) or any(
                hypothesis in prior_hypotheses for hypothesis in hypotheses
            ):
                raise DiscoveryBatchError("research hypothesis was already scheduled")
            prior_question_ids = {
                branch.get("question_id") for branch in state["branches"]
            }
            prior_questions = {
                branch.get("question_digest_sha256") for branch in state["branches"]
            }
            prior_questions.update(
                parent["question_digest_sha256"]
                for parent in state["initial_archived_parents"]
            )
            question_ids = [item["question_id"] for item in checked]
            questions = [item["question_digest_sha256"] for item in checked]
            if (
                len(set(question_ids)) != len(question_ids)
                or len(set(questions)) != len(questions)
                or any(question_id in prior_question_ids for question_id in question_ids)
                or any(question in prior_questions for question in questions)
            ):
                raise DiscoveryBatchError("research question was already scheduled")
            eligible_parents = {
                parent["candidate_sha256"]: parent
                for parent in self._eligible_parent_records(state)
            }
            known_parents = set(eligible_parents)
            selected_parent_counts: dict[str, int] = {}
            for item in checked:
                parent_sha = item["research_parent_sha256"]
                selected_parent_counts[parent_sha] = (
                    selected_parent_counts.get(parent_sha, 0) + 1
                )
            if any(
                count > 1
                and state.get("scheduling_version") != 4
                and eligible_parents.get(parent_sha, {}).get("research_credit") == 1
                for parent_sha, count in selected_parent_counts.items()
            ):
                raise DiscoveryBatchError("credit-1 parent permits one bounded follow-up")
            if any(
                item["research_parent_sha256"] not in known_parents for item in checked
            ):
                raise DiscoveryBatchError("research parent is not an archived branch")
            _, state = self._commit(
                records,
                "controller_pool_selected",
                {
                    "pool_generation": state["pool_generation"] + 1,
                    "comparison_incumbent_sha256": state["incumbent"][
                        "candidate_sha256"
                    ],
                    "selection_hint_sha256": _digest(hint),
                    "selections": checked,
                    "selected_at_utc": _utc_text(moment, "selection time"),
                },
            )
            return self._public(state)

    def mark_implementation_ready(
        self,
        attempt_id: str,
        *,
        runner_sha256: str,
        spec_sha256: str,
        now: str | datetime | None = None,
    ) -> dict[str, Any]:
        attempt_id = _identifier(attempt_id, "attempt ID")
        runner = _sha(runner_sha256, "runner")
        spec = _sha(spec_sha256, "experiment spec")
        moment = self._trusted_now(now, "implementation-ready time")
        with self._locked():
            records, state = self._load_locked()
            branch = self._branch(state, attempt_id)
            if branch["stage"] != "controller_selected":
                if branch["runner_sha256"] == runner and branch["spec_sha256"] == spec:
                    return self._public(state)
                raise DiscoveryBatchError("implementation bindings changed or branch is terminal")
            _, state = self._commit(
                records,
                "implementation_ready",
                {
                    "attempt_id": attempt_id,
                    "runner_sha256": runner,
                    "spec_sha256": spec,
                    "event_time_utc": _utc_text(moment, "implementation-ready time"),
                },
            )
            return self._public(state)

    def claim_execution(
        self,
        attempt_id: str,
        *,
        claim_id: str,
        runtime_pair_sha256: str | None = None,
        memory_snapshot_sha256: str | None = None,
        now: str | datetime | None = None,
    ) -> dict[str, Any]:
        attempt_id = _identifier(attempt_id, "attempt ID")
        claim_id = _identifier(claim_id, "execution claim ID")
        moment = self._trusted_now(now, "claim time")
        with self._locked():
            records, state = self._load_locked()
            branch = self._branch(state, attempt_id)
            binding = {}
            if "micro_evolution" in state:
                pair = _sha(runtime_pair_sha256, "runtime pair")
                memory = _sha(memory_snapshot_sha256, "memory snapshot")
                expected_pair = (branch.get("runtime_pair_sha256") or
                    micro_evolution.micro_pair_hash(state["micro_evolution"]))
                if pair != expected_pair:
                    raise DiscoveryBatchError("execution pair differs from active pair")
                if branch.get("memory_snapshot_sha256", memory) != memory:
                    raise DiscoveryBatchError("claimed memory snapshot changed")
                binding = {"runtime_pair_sha256": pair, "memory_snapshot_sha256": memory}
            elif runtime_pair_sha256 is not None or memory_snapshot_sha256 is not None:
                raise DiscoveryBatchError("runtime pair binding requires configured evolution")
            if branch["claim_id"] is not None:
                if branch["claim_id"] == claim_id:
                    return self._public(state)
                raise DiscoveryBatchError("execution was already claimed with a different ID")
            if branch["stage"] != "implementation_ready":
                raise DiscoveryBatchError("execution claim requires implementation_ready")
            records, state = self._stop_locked(records, state, moment)
            self._assert_live_batch(state, moment)
            branch = self._branch(state, attempt_id)
            _, state = self._commit(
                records,
                "execution_claimed",
                {
                    "attempt_id": attempt_id,
                    "claim_id": claim_id,
                    "attempt_number": state["attempts_claimed"] + 1,
                    "claimed_at_utc": _utc_text(moment, "claim time"),
                    "runner_sha256": branch["runner_sha256"],
                    "spec_sha256": branch["spec_sha256"],
                    **binding,
                },
            )
            return self._public(state)

    def mark_execution_terminal(
        self,
        attempt_id: str,
        *,
        claim_id: str,
        outcome: str,
        execution_receipt_sha256: str,
        now: str | datetime | None = None,
    ) -> dict[str, Any]:
        attempt_id = _identifier(attempt_id, "attempt ID")
        claim_id = _identifier(claim_id, "execution claim ID")
        receipt = _sha(execution_receipt_sha256, "execution receipt")
        terminal_time = _utc_text(
            self._trusted_now(now, "terminal time"), "terminal time"
        )
        if outcome not in EXECUTION_OUTCOMES:
            raise DiscoveryBatchError("unknown execution outcome")
        with self._locked():
            records, state = self._load_locked()
            branch = self._branch(state, attempt_id)
            if branch["stage"] != "execution_claimed":
                if (
                    branch["claim_id"] == claim_id
                    and branch["execution_outcome"] == outcome
                    and branch["execution_receipt_sha256"] == receipt
                ):
                    return self._public(state)
                raise DiscoveryBatchError("terminal execution evidence changed")
            if branch["claim_id"] != claim_id:
                raise DiscoveryBatchError("terminal execution does not match its claim")
            _, state = self._commit(
                records,
                "execution_terminal",
                {
                    "attempt_id": attempt_id,
                    "claim_id": claim_id,
                    "outcome": outcome,
                    "execution_receipt_sha256": receipt,
                    "terminal_at_utc": terminal_time,
                },
            )
            return self._public(state)

    def record_result_review(
        self,
        attempt_id: str,
        *,
        decision: str,
        scorecard_sha256: str,
        review_sha256: str,
        independently_reviewed: bool,
        now: str | datetime | None = None,
        performance_validity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        attempt_id = _identifier(attempt_id, "attempt ID")
        scorecard = _sha(scorecard_sha256, "scorecard")
        review = _sha(review_sha256, "independent review")
        if decision not in REVIEW_DECISIONS:
            raise DiscoveryBatchError("result review must be KEEP or REVERT")
        if type(independently_reviewed) is not bool:
            raise DiscoveryBatchError("independent-review flag must be boolean")
        moment = self._trusted_now(now, "result-review time")
        with self._locked():
            records, state = self._load_locked()
            branch = self._branch(state, attempt_id)
            extra = {}
            if state.get("scheduling_version") == 4:
                extra["performance_validity"] = performance_validity
            elif performance_validity is not None:
                raise DiscoveryBatchError("performance validity requires explicit v4 opt-in")
            if branch["stage"] != "execution_terminal":
                if (
                    branch["review_decision"] == decision
                    and branch["scorecard_sha256"] == scorecard
                    and branch["review_sha256"] == review
                    and branch["independently_reviewed"] is independently_reviewed
                    and (not extra or branch["performance_validity"] == performance_validity)
                ):
                    return self._public(state)
                raise DiscoveryBatchError("review evidence changed or branch is terminal")
            if decision == "KEEP" and (
                independently_reviewed is not True
                or branch["execution_outcome"] != "succeeded"
            ):
                raise DiscoveryBatchError(
                    "KEEP requires a successful execution and independent review"
                )
            if (
                self._is_v2(state)
                and decision == "KEEP"
                and branch["comparison_incumbent_sha256"]
                != state["incumbent"]["candidate_sha256"]
            ):
                raise DiscoveryBatchError(
                    "KEEP comparison incumbent is stale; review must remain non-promoting"
                )
            _, state = self._commit(
                records,
                "result_reviewed",
                {
                    "attempt_id": attempt_id,
                    "decision": decision,
                    "scorecard_sha256": scorecard,
                    "review_sha256": review,
                    "independently_reviewed": independently_reviewed,
                    "event_time_utc": _utc_text(moment, "result-review time"),
                    **extra,
                },
            )
            return self._public(state)

    def mark_controller_feedback_ready(
        self,
        attempt_id: str,
        *,
        now: str | datetime | None = None,
    ) -> dict[str, Any]:
        attempt_id = _identifier(attempt_id, "attempt ID")
        moment = self._trusted_now(now, "Controller-feedback time")
        with self._locked():
            records, state = self._load_locked()
            branch = self._branch(state, attempt_id)
            if branch["stage"] == TERMINAL_STAGE:
                return self._public(state)
            if branch["stage"] != "result_reviewed":
                raise DiscoveryBatchError("Controller feedback requires reviewed result")
            if self._is_v2(state) and branch["research_credit"] is None:
                raise DiscoveryBatchError(
                    "v2 Controller feedback requires a research-credit record"
                )
            packet = (
                self._evidence_packet_v2(state, branch)
                if self._is_v2(state)
                else self._evidence_packet(state, branch)
            )
            _, state = self._commit(
                records,
                "controller_feedback_ready",
                {
                    "attempt_id": attempt_id,
                    "packet": packet,
                    "packet_sha256": _digest(packet),
                    "event_time_utc": _utc_text(moment, "Controller-feedback time"),
                },
            )
            return self._public(state)

    def record_research_credit(
        self,
        attempt_id: str,
        *,
        credit: int,
        evidence_bundle_sha256: str,
        problem_id: str,
        question_id: str,
        question_digest_sha256: str,
        authority_snapshot_sha256: str,
        predeclared_rule_sha256: str,
        outcome: str,
        route_action: str,
        credit_review_sha256: str,
        reason: str,
        now: str | datetime | None = None,
    ) -> dict[str, Any]:
        attempt_id = _identifier(attempt_id, "attempt ID")
        if type(credit) is not int or credit not in {0, 1, 2}:
            raise DiscoveryBatchError("research credit must be 0, 1, or 2")
        evidence = _sha(
            evidence_bundle_sha256, "research-credit evidence bundle"
        )
        problem = _identifier(problem_id, "problem ID")
        question = _identifier(question_id, "question ID")
        question_digest = _sha(question_digest_sha256, "canonical question digest")
        authority_snapshot = _sha(authority_snapshot_sha256, "authority snapshot")
        predeclared_rule = _sha(predeclared_rule_sha256, "predeclared decision rule")
        credit_review = _sha(credit_review_sha256, "independent credit review")
        if outcome not in RESEARCH_OUTCOMES or route_action not in ROUTE_ACTIONS:
            raise DiscoveryBatchError("invalid research outcome or route action")
        valid_route = (
            credit == 0 and outcome == "invalid" and route_action in {"cooldown", "stop"}
        ) or (
            credit == 1
            and outcome == "inconclusive"
            and route_action == "bounded_followup"
        ) or (
            credit == 2 and outcome == "support" and route_action == "continue"
        ) or (
            credit == 2
            and outcome == "refute"
            and route_action in {"cooldown", "stop"}
        ) or (
            credit == 2 and outcome == "refute" and route_action == "branch"
            and self.snapshot().get("scheduling_version") == 3
        )
        if not valid_route:
            raise DiscoveryBatchError("credit/outcome/route action contract changed")
        checked_reason = _reason(reason, "research-credit reason")
        moment = self._trusted_now(now, "research-credit time")
        with self._locked():
            records, state = self._load_locked()
            if not self._is_v2(state):
                raise DiscoveryBatchError("research credit requires a v2 batch")
            branch = self._branch(state, attempt_id)
            if branch["research_credit"] is not None:
                raise DiscoveryBatchError("research credit was already recorded")
            if branch["stage"] != "result_reviewed":
                raise DiscoveryBatchError("research credit requires a reviewed result")
            if (
                question != branch["question_id"]
                or question_digest != branch["question_digest_sha256"]
                or predeclared_rule != branch["predeclared_rule_sha256"]
            ):
                raise DiscoveryBatchError("credit changed the predeclared question")
            if credit > 0 and (
                branch["execution_outcome"] != "succeeded"
                or branch["independently_reviewed"] is not True
            ):
                raise DiscoveryBatchError(
                    "positive research credit requires succeeded, independent evidence"
                )
            if any(
                prior["question_id"] == question
                or prior["question_digest_sha256"] == question_digest
                or (
                    prior["problem_id"] == problem
                    and prior["evidence_bundle_sha256"] == evidence
                )
                for prior in state["research_credit_records"]
            ) or any(
                archived["question_digest_sha256"] == question_digest
                or (
                    archived["problem_id"] == problem
                    and archived["evidence_bundle_sha256"] == evidence
                )
                for archived in state["initial_archived_parents"]
            ):
                raise DiscoveryBatchError("research question or evidence is a duplicate")
            _, state = self._commit(
                records,
                "research_credit_recorded",
                {
                    "attempt_id": attempt_id,
                    "credit": credit,
                    "evidence_bundle_sha256": evidence,
                    "problem_id": problem,
                    "question_id": question,
                    "question_digest_sha256": question_digest,
                    "authority_snapshot_sha256": authority_snapshot,
                    "result_review_sha256": branch["review_sha256"],
                    "predeclared_rule_sha256": predeclared_rule,
                    "outcome": outcome,
                    "route_action": route_action,
                    "credit_review_sha256": credit_review,
                    "reason": checked_reason,
                    "event_time_utc": _utc_text(moment, "research-credit time"),
                },
            )
            return self._public(state)

    def record_learning_checkpoint(self, attempt_id: str, assessment: Mapping[str, Any], *,
                                   now: str | datetime | None = None) -> dict[str, Any]:
        """Persist one prospective assessment; judge and incumbent are unchanged."""
        attempt_id = _identifier(attempt_id, "attempt ID")
        moment = self._trusted_now(now, "learning checkpoint time")
        with self._locked():
            records, state = self._load_locked()
            if state.get("scheduling_version") != 4:
                raise DiscoveryBatchError("learning checkpoint requires explicit v4 opt-in")
            branch = self._branch(state, attempt_id)
            previous = next((r for r in records if r["event"] == "learning_checkpoint_recorded" and r["payload"]["attempt_id"] == attempt_id), None)
            if previous is not None:
                if previous["payload"]["assessment"] != assessment:
                    raise DiscoveryBatchError("checkpoint attempt reused with different evidence")
                return self._public(state)
            _, state = self._commit(records, "learning_checkpoint_recorded",
                                    {"attempt_id": attempt_id, "assessment": dict(assessment),
                                     "event_time_utc": _utc_text(moment, "learning checkpoint time")})
            return self._public(state)


__all__ = [
    "BOUNDARY_FLAGS",
    "BatchStoppedError",
    "ContinuousDiscoveryBatch",
    "DiscoveryBatchError",
    "EVIDENCE_SCHEMA",
    "EVIDENCE_SCHEMA_V2",
    "EVIDENCE_SCHEMA_V4",
    "parent_eligibility",
    "EXECUTION_OUTCOMES",
    "SCHEMA",
    "STAGES",
    "TERMINAL_STAGE",
    "ZERO_SHA256",
]
