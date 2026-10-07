"""Zero-authority integration boundary for the PMB simple lane.

The package composes prospective source, episode-manifest and experiment-spec
commitments.  Binding them proves only that their local synthetic commitments
agree.  It does not admit source or data and cannot authorize execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
import weakref
from typing import Iterable

from .artifact_store import ArtifactIntegrityError, ArtifactStore
from .episode_lease import EpisodeLease
from .episode_manifest import (
    EPISODE_ROLES,
    ManifestSetValidation,
    require_validated_manifest_set,
)
from .experiment_spec import (
    ExperimentSpec,
    canonical_json_bytes as canonical_experiment_json_bytes,
    validate_experiment_spec,
)
from .upstream_lock import (
    ProspectiveUpstreamVerification,
    require_validated_upstream_verification,
)


FOUNDATION_SCHEMA = "market_rsi_pmb_synthetic_foundation_v1"
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_FOUNDATION_RECEIPT_TOKEN = object()


class SyntheticFoundationError(ValueError):
    """The synthetic commitments disagree or attempt to grant authority."""


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise SyntheticFoundationError(f"{label} must be a lowercase SHA-256")
    return value


@dataclass(frozen=True, slots=True, weakref_slot=True, init=False, eq=False)
class SyntheticFoundationCommitment:
    """Canonical cross-component receipt whose authority bits are always false."""

    upstream_lock_sha256: str
    episode_manifest_set_sha256: str
    experiment_spec_sha256: str
    evidence_role: str
    schema: str = FOUNDATION_SCHEMA
    evidence_scope: str = "local_synthetic_commitment_only"
    runtime_admitted: bool = False
    data_admitted: bool = False
    execution_authorized: bool = False
    _validation_token: object = field(init=False, repr=False, compare=False)

    def __init__(
        self,
        upstream_lock_sha256: str,
        episode_manifest_set_sha256: str,
        experiment_spec_sha256: str,
        evidence_role: str,
        schema: str = FOUNDATION_SCHEMA,
        evidence_scope: str = "local_synthetic_commitment_only",
        runtime_admitted: bool = False,
        data_admitted: bool = False,
        execution_authorized: bool = False,
        *,
        _validation_token: object | None = None,
    ) -> None:
        if _validation_token is not _FOUNDATION_RECEIPT_TOKEN:
            raise SyntheticFoundationError(
                "synthetic-foundation receipts can only be created by "
                "bind_synthetic_foundation"
            )
        object.__setattr__(self, "upstream_lock_sha256", upstream_lock_sha256)
        object.__setattr__(
            self, "episode_manifest_set_sha256", episode_manifest_set_sha256
        )
        object.__setattr__(self, "experiment_spec_sha256", experiment_spec_sha256)
        object.__setattr__(self, "evidence_role", evidence_role)
        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "evidence_scope", evidence_scope)
        object.__setattr__(self, "runtime_admitted", runtime_admitted)
        object.__setattr__(self, "data_admitted", data_admitted)
        object.__setattr__(self, "execution_authorized", execution_authorized)
        object.__setattr__(self, "_validation_token", _validation_token)
        self.__post_init__()

    def __post_init__(self) -> None:
        if self.schema != FOUNDATION_SCHEMA:
            raise SyntheticFoundationError("unsupported synthetic-foundation schema")
        _sha256(self.upstream_lock_sha256, "upstream_lock_sha256")
        _sha256(self.episode_manifest_set_sha256, "episode_manifest_set_sha256")
        _sha256(self.experiment_spec_sha256, "experiment_spec_sha256")
        if self.evidence_role not in EPISODE_ROLES:
            raise SyntheticFoundationError("unknown evidence role")
        if self.evidence_scope != "local_synthetic_commitment_only":
            raise SyntheticFoundationError("synthetic evidence scope cannot expand")
        if any(
            value is not False
            for value in (
                self.runtime_admitted,
                self.data_admitted,
                self.execution_authorized,
            )
        ):
            raise SyntheticFoundationError("synthetic foundation cannot grant authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "upstream_lock_sha256": self.upstream_lock_sha256,
            "episode_manifest_set_sha256": self.episode_manifest_set_sha256,
            "experiment_spec_sha256": self.experiment_spec_sha256,
            "evidence_role": self.evidence_role,
            "evidence_scope": self.evidence_scope,
            "runtime_admitted": self.runtime_admitted,
            "data_admitted": self.data_admitted,
            "execution_authorized": self.execution_authorized,
        }

    @property
    def sha256(self) -> str:
        payload = json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


_ISSUED_FOUNDATION_RECEIPTS: weakref.WeakKeyDictionary[
    SyntheticFoundationCommitment, tuple[object, ...]
] = weakref.WeakKeyDictionary()


def _foundation_snapshot(
    value: SyntheticFoundationCommitment,
) -> tuple[object, ...]:
    return (
        value.upstream_lock_sha256,
        value.episode_manifest_set_sha256,
        value.experiment_spec_sha256,
        value.evidence_role,
        value.schema,
        value.evidence_scope,
        value.runtime_admitted,
        value.data_admitted,
        value.execution_authorized,
        getattr(value, "_validation_token", None),
    )


def require_validated_synthetic_foundation(
    value: object,
) -> SyntheticFoundationCommitment:
    """Return an authentic binder receipt or reject a dataclass-shaped value."""

    if type(value) is not SyntheticFoundationCommitment:
        raise SyntheticFoundationError("authentic synthetic-foundation receipt required")
    try:
        issued_snapshot = _ISSUED_FOUNDATION_RECEIPTS.get(value)
        current_snapshot = _foundation_snapshot(value)
    except (AttributeError, TypeError):
        raise SyntheticFoundationError(
            "authentic synthetic-foundation receipt required"
        ) from None
    if (
        issued_snapshot is None
        or current_snapshot[:-1] != issued_snapshot[:-1]
        or current_snapshot[-1] is not issued_snapshot[-1]
        or current_snapshot[-1] is not _FOUNDATION_RECEIPT_TOKEN
    ):
        raise SyntheticFoundationError("authentic synthetic-foundation receipt required")
    value.__post_init__()
    return value


def bind_synthetic_foundation(
    upstream: ProspectiveUpstreamVerification,
    manifests: ManifestSetValidation,
    experiment: ExperimentSpec,
    *,
    used_evaluation_ids: Iterable[str] | None = None,
) -> SyntheticFoundationCommitment:
    """Fail closed unless three validated, non-admitting components agree.

    The original manifests and upstream checkout remain outside this boundary;
    this function binds their already-computed commitments and deliberately
    returns no path, bytes, process runner or authorization token.
    """

    if type(experiment) is not ExperimentSpec:
        raise SyntheticFoundationError("exact sealed ExperimentSpec required")

    # Capture the complete experiment identity once. All subsequent parsing,
    # validation and receipt construction uses only these immutable locals.
    experiment_bytes = experiment.canonical_bytes
    declared_experiment_sha = experiment.sha256
    if type(experiment_bytes) is not bytes:
        raise SyntheticFoundationError("experiment-spec bytes must be immutable bytes")
    declared_experiment_sha = _sha256(
        declared_experiment_sha, "declared experiment spec"
    )
    computed_experiment_sha = hashlib.sha256(experiment_bytes).hexdigest()
    if declared_experiment_sha != computed_experiment_sha:
        raise SyntheticFoundationError("experiment-spec bytes changed")
    local_experiment = ExperimentSpec(experiment_bytes, computed_experiment_sha)

    try:
        upstream = require_validated_upstream_verification(upstream)
        manifests = require_validated_manifest_set(manifests)
    except ValueError as exc:
        raise SyntheticFoundationError("authentic validator receipts required") from exc

    upstream_sha = _sha256(upstream.lock_sha256, "upstream lock")
    manifest_sha = _sha256(manifests.manifest_set_sha256, "manifest set")
    if (
        upstream.evidence_scope != "local_synthetic_commitment_only"
        or upstream.runtime_admitted is not False
    ):
        raise SyntheticFoundationError("prospective upstream must remain non-admitted")
    if upstream.tree_file_count < 1 or upstream.import_origin_count < 1:
        raise SyntheticFoundationError("prospective upstream commitment is empty")
    if (
        manifests.preopen_commitments_valid is not True
        or manifests.data_opened is not False
        or manifests.admission_granted is not False
    ):
        raise SyntheticFoundationError("manifest validation must remain pre-open and non-admitting")
    if manifests.episode_count < 1 or not manifests.roles:
        raise SyntheticFoundationError("manifest-set commitment is empty")
    if len(set(manifests.roles)) != len(manifests.roles) or any(
        role not in EPISODE_ROLES for role in manifests.roles
    ):
        raise SyntheticFoundationError("manifest roles are invalid")
    if "sealed_final" in manifests.roles:
        if manifests.sealed_final_distinct_dates < 20:
            raise SyntheticFoundationError("sealed Final requires at least 20 untouched dates")
    elif manifests.sealed_final_distinct_dates != 0:
        raise SyntheticFoundationError("sealed-Final date count has no sealed-Final role")

    spec = validate_experiment_spec(
        local_experiment.to_mapping(), used_evaluation_ids=used_evaluation_ids
    )
    if experiment_bytes != canonical_experiment_json_bytes(spec):
        raise SyntheticFoundationError("experiment-spec bytes are not canonical")
    evidence_role = spec["evidence_role"]
    if evidence_role not in manifests.roles:
        raise SyntheticFoundationError("experiment evidence role is absent from manifest set")
    sources = spec["source_commitments"]
    if sources.get("upstream_sha256") != upstream_sha:
        raise SyntheticFoundationError("experiment does not bind the upstream lock")
    if sources.get("episode_manifest_sha256") != manifest_sha:
        raise SyntheticFoundationError("experiment does not bind the manifest set")

    receipt = SyntheticFoundationCommitment(
        upstream_lock_sha256=upstream_sha,
        episode_manifest_set_sha256=manifest_sha,
        experiment_spec_sha256=computed_experiment_sha,
        evidence_role=evidence_role,
        _validation_token=_FOUNDATION_RECEIPT_TOKEN,
    )
    _ISSUED_FOUNDATION_RECEIPTS[receipt] = _foundation_snapshot(receipt)
    return receipt


__all__ = [
    "ArtifactIntegrityError",
    "ArtifactStore",
    "EpisodeLease",
    "FOUNDATION_SCHEMA",
    "SyntheticFoundationCommitment",
    "SyntheticFoundationError",
    "bind_synthetic_foundation",
    "require_validated_synthetic_foundation",
]
