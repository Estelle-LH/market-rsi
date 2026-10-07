"""Role-separated PredictionMarketBench episode commitments.

Validation is intentionally admission-neutral: it checks immutable metadata and
pre-open split invariants, but it neither discovers nor opens hidden episodes.
Materialized-file verification is an explicit, caller-directed operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable, Mapping
import weakref


EPISODE_MANIFEST_SCHEMA = "market_rsi_pmb_episode_manifest_v1"
EPISODE_ROLES = frozenset(
    {"public_diagnostic_train", "train", "hidden_dev", "sealed_final"}
)
PUBLIC_DIAGNOSTIC_EPISODES = frozenset(
    {
        "KXBTCD-26JAN2017",
        "KXHIGHNY-26JAN20",
        "KXNCAAF-26",
        "KXNFLGAME-26JAN11BUFJAC",
    }
)
REQUIRED_EPISODE_FILES = frozenset(
    {"metadata.json", "orderbook.parquet", "trades.parquet", "settlement.json"}
)
VENUES = frozenset({"kalshi", "polymarket"})
DOMAINS = frozenset({"crypto", "weather", "sports"})
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_EPISODE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}\Z")


class EpisodeManifestError(ValueError):
    """Raised when episode commitments or split invariants fail closed."""


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise EpisodeManifestError(
            f"{label} fields mismatch: missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def _parse_date(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise EpisodeManifestError(f"{label} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise EpisodeManifestError(f"{label} must be a real YYYY-MM-DD date") from exc
    if parsed.isoformat() != value:
        raise EpisodeManifestError(f"{label} is not canonical YYYY-MM-DD")
    return parsed


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise EpisodeManifestError(f"{label} must be exactly 64 lowercase hex characters")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EpisodeManifestError(f"{label} must be a non-negative integer")
    return value


def _safe_relative_directory(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise EpisodeManifestError("relative_directory must be a POSIX relative path")
    path = PurePosixPath(value)
    if (
        path.as_posix() == "."
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise EpisodeManifestError("relative_directory contains an unsafe path segment")
    canonical = path.as_posix()
    if canonical != value:
        raise EpisodeManifestError("relative_directory is not canonical")
    return canonical


@dataclass(frozen=True, order=True)
class EpisodeFileCommitment:
    name: str
    sha256: str
    length: int

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EpisodeFileCommitment":
        if not isinstance(value, Mapping):
            raise EpisodeManifestError("episode file commitment must be an object")
        _exact_keys(value, {"name", "sha256", "length"}, "episode file")
        name = value["name"]
        if name not in REQUIRED_EPISODE_FILES:
            raise EpisodeManifestError(f"unexpected episode filename: {name!r}")
        return cls(
            name=name,
            sha256=_sha256(value["sha256"], f"{name} sha256"),
            length=_nonnegative_int(value["length"], f"{name} length"),
        )

    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "sha256": self.sha256, "length": self.length}


@dataclass(frozen=True)
class EpisodeManifest:
    episode_id: str
    venue: str
    domain: str
    utc_date: date
    role: str
    relative_directory: str
    files: tuple[EpisodeFileCommitment, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EpisodeManifest":
        if not isinstance(value, Mapping):
            raise EpisodeManifestError("episode manifest must be an object")
        _exact_keys(
            value,
            {
                "schema",
                "episode_id",
                "venue",
                "domain",
                "utc_date",
                "role",
                "relative_directory",
                "files",
            },
            "episode manifest",
        )
        if value["schema"] != EPISODE_MANIFEST_SCHEMA:
            raise EpisodeManifestError("unsupported episode manifest schema")
        episode_id = value["episode_id"]
        if not isinstance(episode_id, str) or _EPISODE_ID.fullmatch(episode_id) is None:
            raise EpisodeManifestError("episode_id is not canonical")
        if value["venue"] not in VENUES:
            raise EpisodeManifestError("venue must be kalshi or polymarket")
        if value["domain"] not in DOMAINS:
            raise EpisodeManifestError("domain must be crypto, weather or sports")
        if value["role"] not in EPISODE_ROLES:
            raise EpisodeManifestError("unknown episode role")
        relative_directory = _safe_relative_directory(value["relative_directory"])
        if relative_directory != episode_id:
            raise EpisodeManifestError("relative_directory must exactly equal episode_id")
        raw_files = value["files"]
        if not isinstance(raw_files, list):
            raise EpisodeManifestError("files must be a list")
        files = tuple(sorted(EpisodeFileCommitment.from_mapping(item) for item in raw_files))
        names = [item.name for item in files]
        if set(names) != REQUIRED_EPISODE_FILES or len(names) != len(REQUIRED_EPISODE_FILES):
            raise EpisodeManifestError(
                "files must contain each required PMB episode file exactly once"
            )
        if episode_id in PUBLIC_DIAGNOSTIC_EPISODES and value["role"] != "public_diagnostic_train":
            raise EpisodeManifestError(
                "a public January 2026 PMB episode is permanently diagnostic"
            )
        return cls(
            episode_id=episode_id,
            venue=value["venue"],
            domain=value["domain"],
            utc_date=_parse_date(value["utc_date"], "utc_date"),
            role=value["role"],
            relative_directory=relative_directory,
            files=files,
        )

    @property
    def promotion_eligible(self) -> bool:
        """Return false because a manifest role never grants promotion authority.

        Even a sealed-Final manifest is only a pre-open data commitment.  Any
        later promotion is a separate, independently reviewed supervisor
        decision and cannot be inferred from this object.
        """

        return False

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": EPISODE_MANIFEST_SCHEMA,
            "episode_id": self.episode_id,
            "venue": self.venue,
            "domain": self.domain,
            "utc_date": self.utc_date.isoformat(),
            "role": self.role,
            "relative_directory": self.relative_directory,
            "files": [item.as_dict() for item in self.files],
        }

    @property
    def sha256(self) -> str:
        encoded = json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ExposureRecord:
    episode_id: str
    utc_date: date
    role: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExposureRecord":
        if not isinstance(value, Mapping):
            raise EpisodeManifestError("exposure record must be an object")
        _exact_keys(value, {"episode_id", "utc_date", "role"}, "exposure record")
        episode_id = value["episode_id"]
        if not isinstance(episode_id, str) or _EPISODE_ID.fullmatch(episode_id) is None:
            raise EpisodeManifestError("exposure episode_id is not canonical")
        if value["role"] not in EPISODE_ROLES:
            raise EpisodeManifestError("exposure role is unknown")
        return cls(
            episode_id=episode_id,
            utc_date=_parse_date(value["utc_date"], "exposure utc_date"),
            role=value["role"],
        )


_MANIFEST_VALIDATION_RECEIPT_TOKEN = object()


@dataclass(frozen=True, init=False, eq=False)
class ManifestSetValidation:
    manifest_set_sha256: str
    episode_count: int
    roles: tuple[str, ...]
    sealed_final_distinct_dates: int
    preopen_commitments_valid: bool = True
    data_opened: bool = False
    admission_granted: bool = False

    def __init__(
        self,
        manifest_set_sha256: str,
        episode_count: int,
        roles: tuple[str, ...],
        sealed_final_distinct_dates: int,
        preopen_commitments_valid: bool = True,
        data_opened: bool = False,
        admission_granted: bool = False,
        *,
        _validation_token: object | None = None,
    ) -> None:
        if _validation_token is not _MANIFEST_VALIDATION_RECEIPT_TOKEN:
            raise EpisodeManifestError(
                "manifest-set validation receipts can only be created by "
                "validate_episode_manifests"
            )
        object.__setattr__(self, "manifest_set_sha256", manifest_set_sha256)
        object.__setattr__(self, "episode_count", episode_count)
        object.__setattr__(self, "roles", roles)
        object.__setattr__(
            self, "sealed_final_distinct_dates", sealed_final_distinct_dates
        )
        object.__setattr__(self, "preopen_commitments_valid", preopen_commitments_valid)
        object.__setattr__(self, "data_opened", data_opened)
        object.__setattr__(self, "admission_granted", admission_granted)
        object.__setattr__(self, "_validation_token", _validation_token)


_ISSUED_MANIFEST_SET_VALIDATIONS: weakref.WeakKeyDictionary[
    ManifestSetValidation, tuple[object, ...]
] = weakref.WeakKeyDictionary()


def _manifest_set_validation_snapshot(
    value: ManifestSetValidation,
) -> tuple[object, ...]:
    """Return every receipt field, including the non-authority issuance token."""

    return (
        value.manifest_set_sha256,
        value.episode_count,
        value.roles,
        value.sealed_final_distinct_dates,
        value.preopen_commitments_valid,
        value.data_opened,
        value.admission_granted,
        getattr(value, "_validation_token", None),
    )


def require_validated_manifest_set(value: object) -> ManifestSetValidation:
    """Return an authentic manifest-validator receipt or fail closed."""

    if type(value) is not ManifestSetValidation:
        raise EpisodeManifestError("authentic manifest-set validation required")
    try:
        issued_snapshot = _ISSUED_MANIFEST_SET_VALIDATIONS.get(value)
        current_snapshot = _manifest_set_validation_snapshot(value)
    except (AttributeError, TypeError):
        raise EpisodeManifestError(
            "authentic manifest-set validation required"
        ) from None
    if (
        issued_snapshot is None
        or type(value.manifest_set_sha256) is not str
        or _HEX_64.fullmatch(value.manifest_set_sha256) is None
        or type(value.episode_count) is not int
        or value.episode_count < 1
        or type(value.roles) is not tuple
        or not value.roles
        or any(type(role) is not str for role in value.roles)
        or tuple(sorted(set(value.roles))) != value.roles
        or any(role not in EPISODE_ROLES for role in value.roles)
        or type(value.sealed_final_distinct_dates) is not int
        or value.sealed_final_distinct_dates < 0
        or type(value.preopen_commitments_valid) is not bool
        or value.preopen_commitments_valid is not True
        or type(value.data_opened) is not bool
        or value.data_opened is not False
        or type(value.admission_granted) is not bool
        or value.admission_granted is not False
        or (
            "sealed_final" in value.roles
            and value.sealed_final_distinct_dates < 20
        )
        or (
            "sealed_final" not in value.roles
            and value.sealed_final_distinct_dates != 0
        )
        or current_snapshot[:-1] != issued_snapshot[:-1]
        or current_snapshot[-1] is not issued_snapshot[-1]
        or current_snapshot[-1] is not _MANIFEST_VALIDATION_RECEIPT_TOKEN
    ):
        raise EpisodeManifestError("authentic manifest-set validation required")
    return value


def _coerce_manifest(value: EpisodeManifest | Mapping[str, Any]) -> EpisodeManifest:
    if isinstance(value, EpisodeManifest):
        try:
            mapping = value.as_dict()
        except Exception as exc:
            raise EpisodeManifestError(
                "episode manifest instance failed canonical serialization"
            ) from exc
        return EpisodeManifest.from_mapping(mapping)
    return EpisodeManifest.from_mapping(value)


def _coerce_exposure(value: ExposureRecord | Mapping[str, Any]) -> ExposureRecord:
    if isinstance(value, ExposureRecord):
        try:
            mapping = {
                "episode_id": value.episode_id,
                "utc_date": value.utc_date.isoformat(),
                "role": value.role,
            }
        except Exception as exc:
            raise EpisodeManifestError(
                "exposure record instance failed canonical serialization"
            ) from exc
        return ExposureRecord.from_mapping(mapping)
    return ExposureRecord.from_mapping(value)


def validate_role_roots(role_roots: Mapping[str, str | os.PathLike[str]]) -> None:
    """Validate four absolute, pairwise non-nested role roots without opening data."""

    if set(role_roots) != EPISODE_ROLES:
        raise EpisodeManifestError("role_roots must name exactly the four episode roles")
    normalized: dict[str, Path] = {}
    for role, raw_path in role_roots.items():
        path = Path(raw_path)
        if not path.is_absolute() or ".." in path.parts:
            raise EpisodeManifestError(f"role root for {role} must be absolute and canonical")
        if path.is_symlink():
            raise EpisodeManifestError(f"role root for {role} must not be a symlink")
        normalized[role] = Path(os.path.abspath(os.path.normpath(path)))
    for left_role, left in normalized.items():
        for right_role, right in normalized.items():
            if left_role >= right_role:
                continue
            try:
                common = Path(os.path.commonpath([left, right]))
            except ValueError as exc:
                raise EpisodeManifestError("role roots do not share a valid filesystem") from exc
            if common in {left, right}:
                raise EpisodeManifestError(
                    f"role roots must be disjoint, not nested: {left_role}, {right_role}"
                )


def validate_episode_manifests(
    manifests: Iterable[EpisodeManifest | Mapping[str, Any]],
    *,
    prior_exposures: Iterable[ExposureRecord | Mapping[str, Any]] = (),
    role_roots: Mapping[str, str | os.PathLike[str]] | None = None,
    enforce_chronology: bool = True,
) -> ManifestSetValidation:
    """Check role/date/file commitments without resolving or opening episode paths."""

    items = tuple(_coerce_manifest(item) for item in manifests)
    if not items:
        raise EpisodeManifestError("at least one episode manifest is required")
    exposures = tuple(_coerce_exposure(item) for item in prior_exposures)
    if role_roots is not None:
        validate_role_roots(role_roots)

    episode_ids: set[str] = set()
    role_by_date: dict[date, str] = {}
    file_role: dict[tuple[str, int], str] = {}
    exposed_ids = {item.episode_id for item in exposures}
    exposed_dates = {item.utc_date for item in exposures}
    dates_by_role: dict[str, set[date]] = {role: set() for role in EPISODE_ROLES}

    for manifest in items:
        if manifest.episode_id in episode_ids:
            raise EpisodeManifestError(f"duplicate episode_id: {manifest.episode_id}")
        episode_ids.add(manifest.episode_id)
        if manifest.episode_id in exposed_ids or manifest.utc_date in exposed_dates:
            raise EpisodeManifestError(
                "prior exposure permanently taints an episode/date regardless of relabeling or bytes"
            )
        previous_role = role_by_date.setdefault(manifest.utc_date, manifest.role)
        if previous_role != manifest.role:
            raise EpisodeManifestError(
                f"UTC date appears in more than one role: {manifest.utc_date.isoformat()}"
            )
        dates_by_role[manifest.role].add(manifest.utc_date)
        for commitment in manifest.files:
            fingerprint = (commitment.sha256, commitment.length)
            previous_file_role = file_role.setdefault(fingerprint, manifest.role)
            if previous_file_role != manifest.role:
                raise EpisodeManifestError("identical episode file bytes appear in multiple roles")

    final_dates = dates_by_role["sealed_final"]
    if final_dates and len(final_dates) < 20:
        raise EpisodeManifestError(
            "sealed_final pre-open requires at least 20 distinct untouched UTC dates"
        )

    if enforce_chronology:
        development_dates = dates_by_role["public_diagnostic_train"] | dates_by_role["train"]
        hidden_dates = dates_by_role["hidden_dev"]
        if development_dates and hidden_dates and max(development_dates) >= min(hidden_dates):
            raise EpisodeManifestError("Train/diagnostic dates must precede hidden_dev dates")
        if hidden_dates and final_dates and max(hidden_dates) >= min(final_dates):
            raise EpisodeManifestError("hidden_dev dates must precede sealed_final dates")
        if not hidden_dates and development_dates and final_dates:
            if max(development_dates) >= min(final_dates):
                raise EpisodeManifestError("Train/diagnostic dates must precede sealed_final dates")

    canonical = [item.as_dict() for item in sorted(items, key=lambda item: item.episode_id)]
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    # Receipt construction is deliberately inlined at the validator's only
    # successful exit.  Do not factor this into a value-accepting helper: such
    # a callable would let a caller register evidence that this validator did
    # not derive.
    receipt = ManifestSetValidation(
        manifest_set_sha256=hashlib.sha256(encoded).hexdigest(),
        episode_count=len(items),
        roles=tuple(sorted({item.role for item in items})),
        sealed_final_distinct_dates=len(final_dates),
        _validation_token=_MANIFEST_VALIDATION_RECEIPT_TOKEN,
    )
    _ISSUED_MANIFEST_SET_VALIDATIONS[
        receipt
    ] = _manifest_set_validation_snapshot(receipt)
    return receipt


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    length = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            length += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), length


def verify_materialized_episode_files(
    manifest: EpisodeManifest | Mapping[str, Any],
    role_root: str | os.PathLike[str],
) -> str:
    """Verify an explicitly supplied materialization and return its manifest hash.

    This function does not discover paths, assign roles or grant authorization.
    Callers must complete the role/exposure pre-open gate before using it on any
    non-synthetic materialization.
    """

    item = _coerce_manifest(manifest)
    root = Path(role_root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise EpisodeManifestError("role_root must be an absolute real directory")
    root = root.resolve(strict=True)
    episode_dir = root / item.relative_directory
    if episode_dir.is_symlink() or not episode_dir.is_dir():
        raise EpisodeManifestError("episode directory is absent or is a symlink")
    try:
        resolved_episode = episode_dir.resolve(strict=True)
        resolved_episode.relative_to(root)
    except (OSError, ValueError) as exc:
        raise EpisodeManifestError("episode directory escapes role_root") from exc

    observed_names: set[str] = set()
    observed_paths: dict[str, Path] = {}
    for candidate in episode_dir.iterdir():
        if candidate.is_symlink():
            raise EpisodeManifestError("episode file must not be a symlink")
        if not candidate.is_file():
            raise EpisodeManifestError("episode directory contains a non-file entry")
        try:
            candidate.resolve(strict=True).relative_to(root)
        except (OSError, ValueError) as exc:
            raise EpisodeManifestError("episode file escapes role_root") from exc
        observed_names.add(candidate.name)
        observed_paths[candidate.name] = candidate
    if observed_names != REQUIRED_EPISODE_FILES:
        raise EpisodeManifestError("materialized episode file set is not exact")

    for commitment in item.files:
        digest, length = _hash_file(observed_paths[commitment.name])
        if (digest, length) != (commitment.sha256, commitment.length):
            raise EpisodeManifestError(
                f"materialized episode bytes differ for {commitment.name}"
            )
    return item.sha256
