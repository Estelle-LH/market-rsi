"""Fail-closed commitments for the prospective PredictionMarketBench checkout.

This module deliberately performs no git or network operation.  A successful
result proves only that caller-supplied local bytes match a prospective lock;
it never admits the checkout as a Market RSI runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping
import weakref


UPSTREAM_LOCK_SCHEMA = "market_rsi_pmb_upstream_lock_v1"
OFFICIAL_UPSTREAM_URL = "https://github.com/oddpool/PredictionMarketBench.git"
PROSPECTIVE_UPSTREAM_COMMIT = "611d66941717310858683278940df21c33c406f2"
_HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_MODULE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\Z")


class UpstreamLockError(ValueError):
    """Raised when a prospective upstream commitment fails closed."""


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise UpstreamLockError(
            f"{label} fields mismatch: missing={missing}, unknown={unknown}"
        )


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise UpstreamLockError(f"{label} must be exactly 64 lowercase hex characters")
    return value


def _commit_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or _HEX_40.fullmatch(value) is None:
        raise UpstreamLockError(f"{label} must be exactly 40 lowercase hex characters")
    return value


def _safe_relative_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise UpstreamLockError(f"{label} must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if (
        path.as_posix() == "."
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise UpstreamLockError(f"{label} must not be absolute or contain dot segments")
    canonical = path.as_posix()
    if canonical != value:
        raise UpstreamLockError(f"{label} is not canonical: {value!r}")
    return canonical


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise UpstreamLockError(f"{label} must be a non-negative integer")
    return value


@dataclass(frozen=True, order=True)
class TreeFileCommitment:
    path: str
    sha256: str
    length: int

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TreeFileCommitment":
        if not isinstance(value, Mapping):
            raise UpstreamLockError("tree entry must be an object")
        _exact_keys(value, {"path", "sha256", "length"}, "tree entry")
        return cls(
            path=_safe_relative_path(value["path"], "tree entry path"),
            sha256=_sha256(value["sha256"], "tree entry sha256"),
            length=_nonnegative_int(value["length"], "tree entry length"),
        )

    def as_dict(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.sha256, "length": self.length}


@dataclass(frozen=True, order=True)
class ImportOriginCommitment:
    module: str
    path: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ImportOriginCommitment":
        if not isinstance(value, Mapping):
            raise UpstreamLockError("import-origin entry must be an object")
        _exact_keys(value, {"module", "path"}, "import-origin entry")
        module = value["module"]
        if not isinstance(module, str) or _MODULE.fullmatch(module) is None:
            raise UpstreamLockError("import-origin module is not a canonical Python module")
        return cls(
            module=module,
            path=_safe_relative_path(value["path"], "import-origin path"),
        )

    def as_dict(self) -> dict[str, str]:
        return {"module": self.module, "path": self.path}


@dataclass(frozen=True)
class UpstreamLock:
    source_url: str
    commit_sha: str
    tree: tuple[TreeFileCommitment, ...]
    license_path: str
    license_sha256: str
    license_length: int
    license_spdx: str
    import_origins: tuple[ImportOriginCommitment, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "UpstreamLock":
        if not isinstance(value, Mapping):
            raise UpstreamLockError("upstream lock must be an object")
        _exact_keys(
            value,
            {
                "schema",
                "source_url",
                "commit_sha",
                "tree",
                "license",
                "import_origins",
            },
            "upstream lock",
        )
        if value["schema"] != UPSTREAM_LOCK_SCHEMA:
            raise UpstreamLockError("unsupported upstream lock schema")
        if value["source_url"] != OFFICIAL_UPSTREAM_URL:
            raise UpstreamLockError("source_url is not the exact official PMB URL")
        commit_sha = _commit_sha(value["commit_sha"], "commit_sha")
        if commit_sha != PROSPECTIVE_UPSTREAM_COMMIT:
            raise UpstreamLockError("commit_sha is not the reviewed prospective PMB commit")

        raw_tree = value["tree"]
        if not isinstance(raw_tree, list) or not raw_tree:
            raise UpstreamLockError("tree must be a non-empty list")
        tree = tuple(sorted(TreeFileCommitment.from_mapping(item) for item in raw_tree))
        tree_paths = [item.path for item in tree]
        if len(tree_paths) != len(set(tree_paths)):
            raise UpstreamLockError("tree contains a duplicate path")

        raw_license = value["license"]
        if not isinstance(raw_license, Mapping):
            raise UpstreamLockError("license must be an object")
        _exact_keys(raw_license, {"path", "sha256", "length", "spdx"}, "license")
        license_path = _safe_relative_path(raw_license["path"], "license path")
        license_sha256 = _sha256(raw_license["sha256"], "license sha256")
        license_length = _nonnegative_int(raw_license["length"], "license length")
        if raw_license["spdx"] != "MIT":
            raise UpstreamLockError("PMB license commitment must be SPDX MIT")
        tree_by_path = {item.path: item for item in tree}
        tree_license = tree_by_path.get(license_path)
        if tree_license is None:
            raise UpstreamLockError("license path is absent from the exact tree")
        if (tree_license.sha256, tree_license.length) != (
            license_sha256,
            license_length,
        ):
            raise UpstreamLockError("license commitment disagrees with its tree entry")

        raw_origins = value["import_origins"]
        if not isinstance(raw_origins, list) or not raw_origins:
            raise UpstreamLockError("import_origins must be a non-empty list")
        origins = tuple(
            sorted(ImportOriginCommitment.from_mapping(item) for item in raw_origins)
        )
        modules = [item.module for item in origins]
        if len(modules) != len(set(modules)):
            raise UpstreamLockError("import_origins contains a duplicate module")
        for origin in origins:
            if origin.path not in tree_by_path:
                raise UpstreamLockError(
                    f"import-origin path is absent from the exact tree: {origin.path}"
                )

        return cls(
            source_url=OFFICIAL_UPSTREAM_URL,
            commit_sha=commit_sha,
            tree=tree,
            license_path=license_path,
            license_sha256=license_sha256,
            license_length=license_length,
            license_spdx="MIT",
            import_origins=origins,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": UPSTREAM_LOCK_SCHEMA,
            "source_url": self.source_url,
            "commit_sha": self.commit_sha,
            "tree": [item.as_dict() for item in self.tree],
            "license": {
                "path": self.license_path,
                "sha256": self.license_sha256,
                "length": self.license_length,
                "spdx": self.license_spdx,
            },
            "import_origins": [item.as_dict() for item in self.import_origins],
        }

    @property
    def sha256(self) -> str:
        encoded = json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


_VERIFICATION_RECEIPT_TOKEN = object()


@dataclass(frozen=True, init=False, eq=False)
class ProspectiveUpstreamVerification:
    lock_sha256: str
    tree_file_count: int
    import_origin_count: int
    evidence_scope: str = "local_synthetic_commitment_only"
    runtime_admitted: bool = False

    def __init__(
        self,
        lock_sha256: str,
        tree_file_count: int,
        import_origin_count: int,
        evidence_scope: str = "local_synthetic_commitment_only",
        runtime_admitted: bool = False,
        *,
        _validation_token: object | None = None,
    ) -> None:
        if _validation_token is not _VERIFICATION_RECEIPT_TOKEN:
            raise UpstreamLockError(
                "prospective upstream verification receipts can only be created by "
                "verify_prospective_upstream"
            )
        object.__setattr__(self, "lock_sha256", lock_sha256)
        object.__setattr__(self, "tree_file_count", tree_file_count)
        object.__setattr__(self, "import_origin_count", import_origin_count)
        object.__setattr__(self, "evidence_scope", evidence_scope)
        object.__setattr__(self, "runtime_admitted", runtime_admitted)
        object.__setattr__(self, "_validation_token", _validation_token)


_ISSUED_UPSTREAM_VERIFICATIONS: weakref.WeakKeyDictionary[
    ProspectiveUpstreamVerification, tuple[object, ...]
] = weakref.WeakKeyDictionary()


def _upstream_verification_snapshot(
    value: ProspectiveUpstreamVerification,
) -> tuple[object, ...]:
    """Return every receipt field, including the non-authority issuance token."""

    return (
        value.lock_sha256,
        value.tree_file_count,
        value.import_origin_count,
        value.evidence_scope,
        value.runtime_admitted,
        getattr(value, "_validation_token", None),
    )


def require_validated_upstream_verification(
    value: object,
) -> ProspectiveUpstreamVerification:
    """Return an authentic verifier receipt or fail closed.

    Consumers must call this instead of treating a dataclass-shaped value as
    proof that :func:`verify_prospective_upstream` completed.
    """

    if type(value) is not ProspectiveUpstreamVerification:
        raise UpstreamLockError("authentic prospective upstream verification required")
    try:
        issued_snapshot = _ISSUED_UPSTREAM_VERIFICATIONS.get(value)
        current_snapshot = _upstream_verification_snapshot(value)
    except (AttributeError, TypeError):
        raise UpstreamLockError(
            "authentic prospective upstream verification required"
        ) from None
    if (
        issued_snapshot is None
        or type(value.lock_sha256) is not str
        or _HEX_64.fullmatch(value.lock_sha256) is None
        or type(value.tree_file_count) is not int
        or value.tree_file_count < 1
        or type(value.import_origin_count) is not int
        or value.import_origin_count < 1
        or type(value.evidence_scope) is not str
        or value.evidence_scope != "local_synthetic_commitment_only"
        or type(value.runtime_admitted) is not bool
        or value.runtime_admitted is not False
        or current_snapshot[:-1] != issued_snapshot[:-1]
        or current_snapshot[-1] is not issued_snapshot[-1]
        or current_snapshot[-1] is not _VERIFICATION_RECEIPT_TOKEN
    ):
        raise UpstreamLockError("authentic prospective upstream verification required")
    return value


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _reject_symlink_below(root: Path, candidate: Path, label: str) -> None:
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise UpstreamLockError(f"{label} escapes checkout root") from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise UpstreamLockError(f"{label} traverses a symlink: {relative.as_posix()}")


def _checkout_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for candidate in root.rglob("*"):
        relative = candidate.relative_to(root)
        if relative.parts and relative.parts[0] == ".git":
            if len(relative.parts) == 1 and candidate.is_symlink():
                raise UpstreamLockError("checkout .git entry must not be a symlink")
            continue
        _reject_symlink_below(root, candidate, "checkout tree")
        if candidate.is_file():
            files[relative.as_posix()] = candidate
        elif not candidate.is_dir():
            raise UpstreamLockError(f"unsupported checkout entry: {relative.as_posix()}")
    return files


def verify_prospective_upstream(
    lock_document: Mapping[str, Any] | UpstreamLock,
    checkout_root: str | os.PathLike[str],
    *,
    observed_source_url: str,
    observed_commit_sha: str,
    dirty: bool,
    observed_import_origins: Mapping[str, str | os.PathLike[str]],
) -> ProspectiveUpstreamVerification:
    """Verify synthetic local evidence without granting runtime admission.

    The caller supplies observed git identity and dirtiness; this function does
    not invoke git and therefore cannot establish provenance on its own.
    """

    if isinstance(lock_document, UpstreamLock):
        try:
            lock_mapping = lock_document.as_dict()
        except Exception as exc:
            raise UpstreamLockError(
                "upstream lock instance failed canonical serialization"
            ) from exc
        lock = UpstreamLock.from_mapping(lock_mapping)
    else:
        lock = UpstreamLock.from_mapping(lock_document)
    if observed_source_url != lock.source_url:
        raise UpstreamLockError("observed source URL does not match the exact lock")
    if _commit_sha(observed_commit_sha, "observed_commit_sha") != lock.commit_sha:
        raise UpstreamLockError("observed commit does not match the exact lock")
    if not isinstance(dirty, bool):
        raise UpstreamLockError("dirty must be a boolean observation")
    if dirty:
        raise UpstreamLockError("prospective upstream checkout is dirty")

    root = Path(checkout_root)
    if not root.is_absolute():
        raise UpstreamLockError("checkout_root must be absolute")
    if root.is_symlink() or not root.is_dir():
        raise UpstreamLockError("checkout_root must be a real directory, not a symlink")
    root = root.resolve(strict=True)

    observed_files = _checkout_files(root)
    expected = {item.path: item for item in lock.tree}
    if set(observed_files) != set(expected):
        raise UpstreamLockError(
            "checkout tree paths differ from lock: "
            f"missing={sorted(set(expected) - set(observed_files))}, "
            f"unexpected={sorted(set(observed_files) - set(expected))}"
        )
    for relative, commitment in expected.items():
        digest, length = _hash_file(observed_files[relative])
        if (digest, length) != (commitment.sha256, commitment.length):
            raise UpstreamLockError(f"checkout tree bytes differ at {relative}")

    if not isinstance(observed_import_origins, Mapping):
        raise UpstreamLockError("observed_import_origins must be a mapping")
    expected_origins = {item.module: item.path for item in lock.import_origins}
    if set(observed_import_origins) != set(expected_origins):
        raise UpstreamLockError("observed import module set differs from the lock")
    for module, raw_origin in observed_import_origins.items():
        origin = Path(raw_origin)
        if not origin.is_absolute():
            raise UpstreamLockError(f"import origin for {module} must be absolute")
        _reject_symlink_below(root, origin, f"import origin for {module}")
        try:
            resolved = origin.resolve(strict=True)
            relative = resolved.relative_to(root).as_posix()
        except (OSError, ValueError) as exc:
            raise UpstreamLockError(f"import origin for {module} escapes checkout") from exc
        if relative != expected_origins[module]:
            raise UpstreamLockError(
                f"import origin for {module} is {relative}, expected {expected_origins[module]}"
            )

    # Receipt construction is deliberately inlined at the validator's only
    # successful exit.  Do not factor this into a value-accepting helper: such
    # a callable would let a caller register evidence that this validator did
    # not derive.
    receipt = ProspectiveUpstreamVerification(
        lock_sha256=lock.sha256,
        tree_file_count=len(lock.tree),
        import_origin_count=len(lock.import_origins),
        _validation_token=_VERIFICATION_RECEIPT_TOKEN,
    )
    _ISSUED_UPSTREAM_VERIFICATIONS[receipt] = _upstream_verification_snapshot(receipt)
    return receipt
