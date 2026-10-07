"""Fail-closed immutable specifications for the PMB simple episode lane.

This module does not execute an experiment.  It commits a complete, synthetic-
safe description of one experiment to canonical JSON and provides a read-only
file boundary that callers can revalidate around every untrusted action.  Its
validators never grant promotion or action authority: ``promotion_eligible``
is always exactly false.  In particular, ``sealed_final`` denotes terminal
evidence and must never become feedback to a controller or tuning loop.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterable, Mapping


SPEC_SCHEMA = "market_rsi_pmb_experiment_spec_v1"
CAUSAL_STAGES = ("raw_data", "raw_signal", "prediction", "objective", "pnl")
EVIDENCE_ROLES = (
    "train",
    "public_diagnostic_train",
    "hidden_dev",
    "sealed_final",
)
TRACKS = ("track_a", "track_b")

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_ONE_SENTENCE_RE = re.compile(r"[^.!?\r\n]+[.!?]")

_FROZEN_OBJECT_FIELDS = (
    "target",
    "horizon",
    "executable_price",
    "max_lateness",
    "row_mask",
    "cadence",
    "baseline",
    "normalizer",
    "trainer",
    "loss",
    "scorer",
    "feature_signs",
    "costs",
    "latency",
    "exclusions",
    "missingness",
    "seeds",
    "source_commitments",
    "runtime_commitments",
    "schema_commitments",
)

_SPEC_KEYS = frozenset(
    (
        "schema",
        "experiment_id",
        "track",
        "problem",
        "evidence_role",
        "promotion_eligible",
        "changed_stage",
        "causal_stage_hashes",
        "track_b",
    )
    + _FROZEN_OBJECT_FIELDS
)

_STAGE_HASH_KEYS = frozenset(("baseline_sha256", "candidate_sha256"))
_TRACK_B_KEYS = frozenset(
    (
        "evaluation_id",
        "track_a_experiment_id",
        "changed_stage",
        "causal_stage_hashes",
        "trading_policy_sha256",
        "frozen_prediction_sha256",
        "precommitted",
        "track_a_feedback_allowed",
    )
)


class ExperimentSpecError(ValueError):
    """The proposed experiment specification is incomplete or unsafe."""


def _plain_json(value: Any, path: str = "$") -> Any:
    """Return a detached JSON value while rejecting ambiguous Python values."""

    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ExperimentSpecError(f"{path} contains a non-finite number")
        return value
    if type(value) is list:
        return [_plain_json(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if type(value) is dict:
        result: dict[str, Any] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise ExperimentSpecError(f"{path} has a non-string key")
            result[key] = _plain_json(item, f"{path}.{key}")
        return result
    raise ExperimentSpecError(f"{path} contains non-JSON type {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON deterministically for hashing and byte-exact storage."""

    plain = _plain_json(value)
    try:
        text = json.dumps(
            plain,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return text.encode("utf-8")
    except (UnicodeEncodeError, ValueError) as exc:
        raise ExperimentSpecError("spec is not canonical UTF-8 JSON") from exc


def canonical_sha256(value: Any) -> str:
    """Return the SHA-256 of :func:`canonical_json_bytes`."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _expect_exact_keys(value: Mapping[str, Any], expected: frozenset[str], path: str) -> None:
    observed = frozenset(value)
    if observed != expected:
        missing = sorted(expected - observed)
        unknown = sorted(observed - expected)
        raise ExperimentSpecError(
            f"{path} keys mismatch; missing={missing!r}, unknown={unknown!r}"
        )


def _expect_sha256(value: Any, path: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ExperimentSpecError(f"{path} must be a lowercase SHA-256")
    return value


def _expect_id(value: Any, path: str) -> str:
    if type(value) is not str or _ID_RE.fullmatch(value) is None:
        raise ExperimentSpecError(f"{path} is not a valid immutable identifier")
    return value


def _validate_causal_stage_hashes(value: Any, path: str) -> str:
    if type(value) is not dict:
        raise ExperimentSpecError(f"{path} must be an object")
    if frozenset(value) != frozenset(CAUSAL_STAGES):
        raise ExperimentSpecError(f"{path} must bind all five causal stages exactly")

    changed: list[str] = []
    for stage in CAUSAL_STAGES:
        pair = value[stage]
        if type(pair) is not dict:
            raise ExperimentSpecError(f"{path}.{stage} must be an object")
        _expect_exact_keys(pair, _STAGE_HASH_KEYS, f"{path}.{stage}")
        baseline = _expect_sha256(
            pair["baseline_sha256"], f"{path}.{stage}.baseline_sha256"
        )
        candidate = _expect_sha256(
            pair["candidate_sha256"], f"{path}.{stage}.candidate_sha256"
        )
        if baseline != candidate:
            changed.append(stage)
    if len(changed) != 1:
        raise ExperimentSpecError(
            f"{path} must change exactly one causal stage; observed={changed!r}"
        )
    return changed[0]


def _validate_track_b(
    value: Any,
    *,
    primary_experiment_id: str,
    primary_prediction_sha256: str,
    used_evaluation_ids: frozenset[str] | None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if type(value) is not dict:
        raise ExperimentSpecError("$.track_b must be null or an object")
    _expect_exact_keys(value, _TRACK_B_KEYS, "$.track_b")

    evaluation_id = _expect_id(value["evaluation_id"], "$.track_b.evaluation_id")
    track_a_id = _expect_id(
        value["track_a_experiment_id"], "$.track_b.track_a_experiment_id"
    )
    if evaluation_id == track_a_id:
        raise ExperimentSpecError("Track B must use an ID separate from Track A")
    if primary_experiment_id not in (evaluation_id, track_a_id):
        raise ExperimentSpecError("Track B contract is not bound to this experiment")
    if used_evaluation_ids is None:
        raise ExperimentSpecError("Track B evaluation-ID freshness ledger is required")
    if evaluation_id in used_evaluation_ids:
        raise ExperimentSpecError("Track B evaluation ID has already been used")

    if value["changed_stage"] != "pnl":
        raise ExperimentSpecError("Track B may change only the pnl stage")
    observed_change = _validate_causal_stage_hashes(
        value["causal_stage_hashes"], "$.track_b.causal_stage_hashes"
    )
    if observed_change != "pnl":
        raise ExperimentSpecError("Track B causal hashes must change only pnl")

    prediction_sha = _expect_sha256(
        value["frozen_prediction_sha256"], "$.track_b.frozen_prediction_sha256"
    )
    policy_sha = _expect_sha256(
        value["trading_policy_sha256"], "$.track_b.trading_policy_sha256"
    )
    prediction_pair = value["causal_stage_hashes"]["prediction"]
    if not (
        prediction_pair["baseline_sha256"]
        == prediction_pair["candidate_sha256"]
        == prediction_sha
        == primary_prediction_sha256
    ):
        raise ExperimentSpecError("Track B must bind the unchanged frozen Track A prediction")
    if value["causal_stage_hashes"]["pnl"]["candidate_sha256"] != policy_sha:
        raise ExperimentSpecError("Track B candidate pnl hash must equal its policy hash")
    if value["precommitted"] is not True:
        raise ExperimentSpecError("Track B policy must be precommitted")
    if value["track_a_feedback_allowed"] is not False:
        raise ExperimentSpecError("Track B output must never feed back into Track A")
    return value


def validate_experiment_spec(
    value: Mapping[str, Any],
    *,
    used_evaluation_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Validate and return a detached complete specification.

    ``used_evaluation_ids`` is mandatory whenever a Track B contract is
    present.  The trusted caller supplies its append-only ID ledger; a
    stateless validator cannot truthfully infer that an ID has never been used.
    """

    plain = _plain_json(value)
    if type(plain) is not dict:
        raise ExperimentSpecError("experiment spec must be an object")
    _expect_exact_keys(plain, _SPEC_KEYS, "$")

    if plain["schema"] != SPEC_SCHEMA:
        raise ExperimentSpecError("unsupported experiment-spec schema")
    experiment_id = _expect_id(plain["experiment_id"], "$.experiment_id")
    if plain["track"] not in TRACKS:
        raise ExperimentSpecError(f"$.track must be one of {TRACKS!r}")

    problem = plain["problem"]
    if (
        type(problem) is not str
        or problem != problem.strip()
        or _ONE_SENTENCE_RE.fullmatch(problem) is None
    ):
        raise ExperimentSpecError("$.problem must be exactly one trimmed sentence")

    if plain["evidence_role"] not in EVIDENCE_ROLES:
        raise ExperimentSpecError(f"unknown evidence role {plain['evidence_role']!r}")
    if plain["promotion_eligible"] is not False:
        raise ExperimentSpecError(
            "$.promotion_eligible must be exactly false; experiment-spec "
            "validation never grants promotion or action authority"
        )

    observed_change = _validate_causal_stage_hashes(
        plain["causal_stage_hashes"], "$.causal_stage_hashes"
    )
    if plain["changed_stage"] not in CAUSAL_STAGES:
        raise ExperimentSpecError("$.changed_stage is not a causal stage")
    if plain["changed_stage"] != observed_change:
        raise ExperimentSpecError("declared changed stage does not match causal hashes")

    for field in _FROZEN_OBJECT_FIELDS:
        if type(plain[field]) is not dict or not plain[field]:
            raise ExperimentSpecError(f"$.{field} must be a non-empty frozen object")

    prediction_sha = plain["causal_stage_hashes"]["prediction"]["candidate_sha256"]
    if used_evaluation_ids is None:
        used_ids = None
    else:
        try:
            used_ids = frozenset(used_evaluation_ids)
        except TypeError as exc:
            raise ExperimentSpecError("used evaluation IDs must be iterable strings") from exc
        for used_id in used_ids:
            _expect_id(used_id, "used_evaluation_ids[]")

    track_b = _validate_track_b(
        plain["track_b"],
        primary_experiment_id=experiment_id,
        primary_prediction_sha256=prediction_sha,
        used_evaluation_ids=used_ids,
    )
    if plain["track"] == "track_a":
        if plain["changed_stage"] == "pnl":
            raise ExperimentSpecError("Track A cannot change the pnl stage")
        if track_b is not None and track_b["track_a_experiment_id"] != experiment_id:
            raise ExperimentSpecError("Track A is not the parent named by Track B")
    else:
        if plain["changed_stage"] != "pnl" or track_b is None:
            raise ExperimentSpecError("Track B specs require a pnl-only Track B contract")
        if track_b["evaluation_id"] != experiment_id:
            raise ExperimentSpecError("Track B experiment ID must equal its evaluation ID")
        if track_b["causal_stage_hashes"] != plain["causal_stage_hashes"]:
            raise ExperimentSpecError("Track B top-level and contract causal hashes differ")

    # Exercise the final canonical encoder now, so accepted values cannot fail
    # only when the trusted owner later tries to freeze them.
    canonical_json_bytes(plain)
    return plain


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExperimentSpecError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _decode_json_bytes(data: bytes) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ExperimentSpecError(f"non-finite JSON token {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExperimentSpecError("experiment spec is not valid UTF-8 JSON") from exc
    if type(value) is not dict:
        raise ExperimentSpecError("experiment spec JSON root must be an object")
    return value


@dataclass(frozen=True, slots=True)
class ExperimentSpec:
    """A sealed immutable commitment, never a promotion/action decision.

    Subclassing is forbidden so callers cannot override stateful commitment
    attributes such as ``sha256`` while still passing an ``isinstance`` check.
    """

    canonical_bytes: bytes
    sha256: str

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("ExperimentSpec is sealed and cannot be subclassed")

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        used_evaluation_ids: Iterable[str] | None = None,
    ) -> "ExperimentSpec":
        validated = validate_experiment_spec(
            value, used_evaluation_ids=used_evaluation_ids
        )
        payload = canonical_json_bytes(validated)
        return cls(payload, hashlib.sha256(payload).hexdigest())

    def __post_init__(self) -> None:
        if type(self) is not ExperimentSpec:
            raise ExperimentSpecError("ExperimentSpec must have the exact sealed type")
        if type(self.canonical_bytes) is not bytes:
            raise ExperimentSpecError("canonical_bytes must be immutable bytes")
        _expect_sha256(self.sha256, "sha256")
        if hashlib.sha256(self.canonical_bytes).hexdigest() != self.sha256:
            raise ExperimentSpecError("experiment-spec bytes do not match SHA-256")

    def to_mapping(self) -> dict[str, Any]:
        """Return a detached copy; mutating it cannot mutate this commitment."""

        return _decode_json_bytes(self.canonical_bytes)


@dataclass(frozen=True, slots=True)
class SpecFileCommitment:
    """Identity returned after durable exclusive creation of a spec file."""

    path: Path
    sha256: str
    size: int
    device: int
    inode: int
    parent_device: int
    parent_inode: int


def write_experiment_spec(path: str | os.PathLike[str], spec: ExperimentSpec) -> SpecFileCommitment:
    """Exclusively create, fsync and make a canonical experiment spec read-only."""

    if type(spec) is not ExperimentSpec:
        raise ExperimentSpecError("spec must have the exact sealed ExperimentSpec type")
    target = Path(os.path.abspath(os.fspath(path)))
    if not target.name:
        raise ExperimentSpecError("experiment-spec path must name a file")
    try:
        parent_before = os.lstat(target.parent)
    except OSError as exc:
        raise ExperimentSpecError(f"cannot stat trusted spec directory: {exc}") from exc
    if stat.S_ISLNK(parent_before.st_mode) or not stat.S_ISDIR(parent_before.st_mode):
        raise ExperimentSpecError("experiment-spec parent must be a non-symlink directory")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(target, flags, 0o400)
    except OSError as exc:
        raise ExperimentSpecError(f"cannot exclusively create experiment spec: {exc}") from exc

    try:
        view = memoryview(spec.canonical_bytes)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise ExperimentSpecError("short write while freezing experiment spec")
            view = view[written:]
        os.fsync(fd)
        os.fchmod(fd, 0o444)
        observed = os.fstat(fd)
    except Exception:
        try:
            os.close(fd)
        finally:
            # The exclusive partial file is deliberately preserved as evidence.
            pass
        raise
    else:
        os.close(fd)

    directory_fd = os.open(target.parent, os.O_RDONLY)
    try:
        parent_open = os.fstat(directory_fd)
        if (parent_open.st_dev, parent_open.st_ino) != (
            parent_before.st_dev,
            parent_before.st_ino,
        ):
            raise ExperimentSpecError("trusted spec directory changed during freeze")
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return SpecFileCommitment(
        path=target,
        sha256=spec.sha256,
        size=observed.st_size,
        device=observed.st_dev,
        inode=observed.st_ino,
        parent_device=parent_open.st_dev,
        parent_inode=parent_open.st_ino,
    )


def revalidate_experiment_spec(
    path: str | os.PathLike[str],
    expected_sha256: str,
    *,
    used_evaluation_ids: Iterable[str] | None = None,
    expected_file_commitment: SpecFileCommitment | None = None,
) -> ExperimentSpec:
    """Read one non-symlink, read-only file and verify exact canonical bytes."""

    expected_sha256 = _expect_sha256(expected_sha256, "expected_sha256")
    target = Path(os.path.abspath(os.fspath(path)))
    if expected_file_commitment is not None:
        if target != expected_file_commitment.path:
            raise ExperimentSpecError("experiment-spec path differs from its file commitment")
        try:
            parent_stat = os.lstat(target.parent)
        except OSError as exc:
            raise ExperimentSpecError(f"cannot stat trusted spec directory: {exc}") from exc
        if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
            raise ExperimentSpecError("experiment-spec parent must be a non-symlink directory")
        if (parent_stat.st_dev, parent_stat.st_ino) != (
            expected_file_commitment.parent_device,
            expected_file_commitment.parent_inode,
        ):
            raise ExperimentSpecError("trusted spec directory identity changed")
    try:
        path_stat = os.lstat(target)
    except OSError as exc:
        raise ExperimentSpecError(f"cannot stat experiment spec: {exc}") from exc
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
        raise ExperimentSpecError("experiment spec must be a regular non-symlink file")
    if path_stat.st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
        raise ExperimentSpecError("experiment spec must be read-only")
    if expected_file_commitment is not None and (
        path_stat.st_dev,
        path_stat.st_ino,
        path_stat.st_size,
    ) != (
        expected_file_commitment.device,
        expected_file_commitment.inode,
        expected_file_commitment.size,
    ):
        raise ExperimentSpecError("experiment-spec file identity changed")

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(target, flags)
    except OSError as exc:
        raise ExperimentSpecError(f"cannot open experiment spec safely: {exc}") from exc
    try:
        before = os.fstat(fd)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
    finally:
        os.close(fd)

    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if identity_before != identity_after:
        raise ExperimentSpecError("experiment spec changed while it was read")
    if (before.st_dev, before.st_ino) != (path_stat.st_dev, path_stat.st_ino):
        raise ExperimentSpecError("experiment-spec path changed before open")
    try:
        path_after = os.lstat(target)
    except OSError as exc:
        raise ExperimentSpecError(f"cannot restat experiment spec: {exc}") from exc
    if (path_after.st_dev, path_after.st_ino) != (before.st_dev, before.st_ino):
        raise ExperimentSpecError("experiment-spec path changed during read")

    payload = b"".join(chunks)
    observed_sha256 = hashlib.sha256(payload).hexdigest()
    if observed_sha256 != expected_sha256:
        raise ExperimentSpecError("experiment-spec SHA-256 changed")
    value = _decode_json_bytes(payload)
    if canonical_json_bytes(value) != payload:
        raise ExperimentSpecError("experiment-spec file is not exact canonical JSON")
    validated = validate_experiment_spec(
        value, used_evaluation_ids=used_evaluation_ids
    )
    return ExperimentSpec.from_mapping(
        validated, used_evaluation_ids=used_evaluation_ids
    )


def assert_experiment_spec_unchanged(
    commitment: SpecFileCommitment,
    *,
    used_evaluation_ids: Iterable[str] | None = None,
) -> ExperimentSpec:
    """Revalidate exact bytes and the durable file/directory identities."""

    return revalidate_experiment_spec(
        commitment.path,
        commitment.sha256,
        used_evaluation_ids=used_evaluation_ids,
        expected_file_commitment=commitment,
    )


__all__ = [
    "CAUSAL_STAGES",
    "EVIDENCE_ROLES",
    "SPEC_SCHEMA",
    "TRACKS",
    "ExperimentSpec",
    "ExperimentSpecError",
    "SpecFileCommitment",
    "assert_experiment_spec_unchanged",
    "canonical_json_bytes",
    "canonical_sha256",
    "revalidate_experiment_spec",
    "validate_experiment_spec",
    "write_experiment_spec",
]
