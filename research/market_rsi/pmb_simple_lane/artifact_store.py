"""Fail-closed, append-only artifacts for the synthetic PMB simple lane.

This module grants no authority to run a model, open an episode, or access a
network.  It only provides durable local commitments.  Every trusted read must
name the hash that was committed when the file was exclusively created.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


ZERO_HASH = "0" * 64
_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
_JOURNAL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}\Z")
_EPHEMERAL_PARTS = {".codex-worktrees", "worktrees"}
_CLOUD_PARTS = {
    "dropbox",
    "google drive",
    "icloud drive",
    "mobile documents",
    "onedrive",
}


class ArtifactIntegrityError(ValueError):
    """An immutable artifact or journal no longer matches its commitment."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return the one accepted JSON representation, including one newline."""

    try:
        text = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("artifact must be canonical finite JSON") from exc
    return text.encode("utf-8") + b"\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_hash(value: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise ValueError("lowercase SHA-256 required")
    return value


def _relative_parts(relative_path: str | os.PathLike[str]) -> tuple[str, ...]:
    if not isinstance(relative_path, (str, os.PathLike)):
        raise ValueError("relative artifact path required")
    raw = os.fspath(relative_path)
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        raise ValueError("safe relative artifact path required")
    path = PurePosixPath(raw)
    raw_parts = raw.split("/")
    if path.is_absolute() or any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError("artifact path must remain inside the store")
    if len(path.parts) > 32 or any(len(part.encode("utf-8")) > 200 for part in path.parts):
        raise ValueError("bounded artifact path required")
    return tuple(path.parts)


def _safe_root(root: str | os.PathLike[str], *, allow_temporary: bool) -> Path:
    raw = Path(root).expanduser()
    if not raw.is_absolute() or any(part == ".." for part in raw.parts):
        raise ValueError("artifact root must be an absolute non-traversing path")

    # macOS exposes /var and /tmp as fixed system aliases into /private.  Tests
    # may explicitly opt into the temporary root, but arbitrary symlinked roots
    # are still rejected during descriptor traversal below.
    if allow_temporary and len(raw.parts) > 1 and raw.parts[1] in {"var", "tmp"}:
        raw = raw.resolve(strict=False)

    folded = {part.casefold() for part in raw.parts}
    if any(
        part == marker
        or part.startswith(marker + " ")
        or part.startswith(marker + " (")
        for part in folded
        for marker in _CLOUD_PARTS
    ):
        raise ValueError("cloud-backed artifact roots are forbidden")
    if ".codex" in folded and folded & _EPHEMERAL_PARTS:
        raise ValueError("disposable worktree artifact roots are forbidden")

    resolved_temp = Path(tempfile.gettempdir()).resolve()
    candidate = raw.resolve(strict=False) if raw.exists() else raw.parent.resolve(strict=False) / raw.name
    in_temp = candidate == resolved_temp or resolved_temp in candidate.parents
    if in_temp and not allow_temporary:
        raise ValueError("temporary artifact root requires explicit test-only allowance")
    return raw


class ArtifactStore:
    """A local store whose files can only be created once through this API.

    ``allow_temporary`` exists solely for synthetic tests.  Production callers
    must select a non-cloud, non-temporary, non-worktree durable root.
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        allow_temporary: bool = False,
        max_read_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        if type(max_read_bytes) is not int or max_read_bytes <= 0:
            raise ValueError("positive artifact read bound required")
        self.root = _safe_root(root, allow_temporary=allow_temporary)
        self.max_read_bytes = max_read_bytes
        fd = self._create_and_open_root()
        try:
            root_stat = os.fstat(fd)
            self._root_identity = (root_stat.st_dev, root_stat.st_ino)
        finally:
            os.close(fd)

    def _create_and_open_root(self) -> int:
        fd = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in self.root.parts[1:]:
                try:
                    child = os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=fd,
                    )
                except FileNotFoundError:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                    os.fsync(fd)
                    child = os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=fd,
                    )
                os.close(fd)
                fd = child
            return fd
        except Exception:
            os.close(fd)
            raise

    def _open_root(self) -> int:
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        root_stat = os.fstat(fd)
        if (root_stat.st_dev, root_stat.st_ino) != self._root_identity:
            os.close(fd)
            raise ArtifactIntegrityError("artifact root identity changed")
        return fd

    def _open_dir(self, parts: tuple[str, ...], *, create: bool) -> int:
        fd = self._open_root()
        try:
            for part in parts:
                try:
                    child = os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=fd,
                    )
                except FileNotFoundError:
                    if not create:
                        raise
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                    os.fsync(fd)
                    child = os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=fd,
                    )
                os.close(fd)
                fd = child
            return fd
        except Exception:
            os.close(fd)
            raise

    @staticmethod
    def _receipt(path: str, data: bytes) -> dict[str, Any]:
        return {"bytes": len(data), "path": path, "sha256": sha256_bytes(data)}

    def write_bytes_once(
        self, relative_path: str | os.PathLike[str], data: bytes
    ) -> dict[str, Any]:
        """Exclusively create and fsync one bounded artifact."""

        if not isinstance(data, bytes) or len(data) > self.max_read_bytes:
            raise ValueError("bounded artifact bytes required")
        parts = _relative_parts(relative_path)
        parent_fd = self._open_dir(parts[:-1], create=True)
        fd: int | None = None
        try:
            fd = os.open(
                parts[-1],
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent_fd,
            )
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("artifact write made no progress")
                view = view[written:]
            os.fsync(fd)
            file_stat = os.fstat(fd)
            if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1:
                raise ArtifactIntegrityError("artifact is not one regular file")
            os.close(fd)
            fd = None
            os.fsync(parent_fd)
        finally:
            if fd is not None:
                os.close(fd)
            os.close(parent_fd)
        return self._receipt("/".join(parts), data)

    def write_json_once(
        self, relative_path: str | os.PathLike[str], value: Any
    ) -> dict[str, Any]:
        return self.write_bytes_once(relative_path, canonical_json_bytes(value))

    def read_bytes_verified(
        self,
        relative_path: str | os.PathLike[str],
        *,
        expected_sha256: str,
        expected_bytes: int | None = None,
    ) -> bytes:
        """Read one file only if its identity and exact commitment still match."""

        expected_sha256 = _validate_hash(expected_sha256)
        if expected_bytes is not None and (
            type(expected_bytes) is not int or expected_bytes < 0
        ):
            raise ValueError("nonnegative expected byte count required")
        parts = _relative_parts(relative_path)
        parent_fd = self._open_dir(parts[:-1], create=False)
        try:
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
        try:
            file_stat = os.fstat(fd)
            if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1:
                raise ArtifactIntegrityError("artifact is not one regular file")
            if file_stat.st_size > self.max_read_bytes:
                raise ArtifactIntegrityError("artifact exceeds frozen read bound")
            if expected_bytes is not None and file_stat.st_size != expected_bytes:
                raise ArtifactIntegrityError("artifact length changed")
            chunks: list[bytes] = []
            remaining = self.max_read_bytes + 1
            while remaining:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            if len(data) > self.max_read_bytes:
                raise ArtifactIntegrityError("artifact exceeds frozen read bound")
        finally:
            os.close(fd)
        if sha256_bytes(data) != expected_sha256:
            raise ArtifactIntegrityError("artifact SHA-256 changed")
        return data

    def verify_receipt(self, receipt: dict[str, Any]) -> bytes:
        if not isinstance(receipt, dict) or set(receipt) != {"bytes", "path", "sha256"}:
            raise ValueError("exact artifact receipt required")
        return self.read_bytes_verified(
            receipt["path"],
            expected_sha256=receipt["sha256"],
            expected_bytes=receipt["bytes"],
        )

    def observe_uncommitted_receipt(
        self, relative_path: str | os.PathLike[str]
    ) -> dict[str, Any]:
        """Hash an existing file so recovery can quarantine an orphan.

        This does not make the file trusted.  The receipt becomes immutable only
        when a terminal unresolved journal event commits it.
        """

        parts = _relative_parts(relative_path)
        parent_fd = self._open_dir(parts[:-1], create=False)
        try:
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_size > self.max_read_bytes
            ):
                raise ArtifactIntegrityError("uncommitted artifact is not one bounded file")
            chunks: list[bytes] = []
            total = 0
            while total <= self.max_read_bytes:
                chunk = os.read(fd, min(65536, self.max_read_bytes + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            if total > self.max_read_bytes:
                raise ArtifactIntegrityError("uncommitted artifact exceeds read bound")
        finally:
            os.close(fd)
        return self._receipt("/".join(parts), b"".join(chunks))

    def read_json_verified(self, receipt: dict[str, Any]) -> Any:
        data = self.verify_receipt(receipt)
        try:
            value = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactIntegrityError("artifact is not valid JSON") from exc
        if canonical_json_bytes(value) != data:
            raise ArtifactIntegrityError("artifact is not canonical JSON")
        return value

    def _journal_dir(self, name: str) -> tuple[str, ...]:
        if not isinstance(name, str) or _JOURNAL_RE.fullmatch(name) is None:
            raise ValueError("bounded journal name required")
        return ("journals", name)

    def verify_journal(
        self, name: str, *, expected_head: str | None = None
    ) -> dict[str, Any]:
        """Replay the complete journal and reject gaps, additions, or mutation."""

        directory = self._journal_dir(name)
        try:
            dir_fd = self._open_dir(directory, create=False)
        except FileNotFoundError:
            summary = {"entries": [], "head_sha256": ZERO_HASH, "length": 0}
            if expected_head is not None and _validate_hash(expected_head) != ZERO_HASH:
                raise ArtifactIntegrityError("journal head changed")
            return summary
        try:
            names = sorted(os.listdir(dir_fd))
            expected_names = [f"{index:08d}.json" for index in range(len(names))]
            if names != expected_names:
                raise ArtifactIntegrityError("journal has a gap or unexpected entry")
            entries: list[dict[str, Any]] = []
            previous = ZERO_HASH
            for index, filename in enumerate(names):
                fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
                try:
                    file_stat = os.fstat(fd)
                    if (
                        not stat.S_ISREG(file_stat.st_mode)
                        or file_stat.st_nlink != 1
                        or file_stat.st_size > self.max_read_bytes
                    ):
                        raise ArtifactIntegrityError("invalid journal entry file")
                    data = b""
                    while len(data) <= self.max_read_bytes:
                        chunk = os.read(fd, min(65536, self.max_read_bytes + 1 - len(data)))
                        if not chunk:
                            break
                        data += chunk
                    if len(data) > self.max_read_bytes:
                        raise ArtifactIntegrityError("journal entry exceeds read bound")
                finally:
                    os.close(fd)
                try:
                    record = json.loads(data)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ArtifactIntegrityError("journal entry is invalid JSON") from exc
                required = {
                    "entry_sha256",
                    "event",
                    "journal",
                    "previous_sha256",
                    "schema",
                    "sequence",
                }
                if not isinstance(record, dict) or set(record) != required:
                    raise ArtifactIntegrityError("journal entry schema changed")
                if canonical_json_bytes(record) != data:
                    raise ArtifactIntegrityError("journal entry is not canonical JSON")
                body = {key: value for key, value in record.items() if key != "entry_sha256"}
                computed = sha256_bytes(canonical_json_bytes(body))
                if (
                    record["schema"] != "append_only_hash_chain_v1"
                    or record["journal"] != name
                    or type(record["sequence"]) is not int
                    or record["sequence"] != index
                    or record["previous_sha256"] != previous
                    or record["entry_sha256"] != computed
                    or not isinstance(record["event"], dict)
                ):
                    raise ArtifactIntegrityError("journal sequence or hash chain changed")
                previous = computed
                entries.append(record)
        finally:
            os.close(dir_fd)
        if expected_head is not None and _validate_hash(expected_head) != previous:
            raise ArtifactIntegrityError("journal head changed")
        return {"entries": entries, "head_sha256": previous, "length": len(entries)}

    def append_journal(self, name: str, event: dict[str, Any]) -> dict[str, Any]:
        """Append one immutable, hash-chained record; concurrent writers fail."""

        if not isinstance(event, dict):
            raise ValueError("journal event object required")
        # Validate serializability before creating any filesystem entry.
        canonical_json_bytes(event)
        current = self.verify_journal(name)
        sequence = current["length"]
        body = {
            "event": event,
            "journal": name,
            "previous_sha256": current["head_sha256"],
            "schema": "append_only_hash_chain_v1",
            "sequence": sequence,
        }
        entry_sha256 = sha256_bytes(canonical_json_bytes(body))
        record = dict(body, entry_sha256=entry_sha256)
        path = f"journals/{name}/{sequence:08d}.json"
        receipt = self.write_json_once(path, record)
        verified = self.verify_journal(name, expected_head=entry_sha256)
        if verified["length"] != sequence + 1:
            raise ArtifactIntegrityError("journal append was not exclusive")
        return {
            "artifact": receipt,
            "head_sha256": entry_sha256,
            "sequence": sequence,
        }

    def list_files(self, relative_directory: str | os.PathLike[str]) -> list[str]:
        """List regular files without following any symlink in the subtree."""

        base = _relative_parts(relative_directory)
        try:
            fd = self._open_dir(base, create=False)
        except FileNotFoundError:
            return []
        found: list[str] = []

        def visit(directory_fd: int, prefix: tuple[str, ...]) -> None:
            for name in sorted(os.listdir(directory_fd)):
                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    raise ArtifactIntegrityError("symlink inside artifact tree")
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(
                        name,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=directory_fd,
                    )
                    try:
                        visit(child, prefix + (name,))
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                    found.append("/".join(prefix + (name,)))
                else:
                    raise ArtifactIntegrityError("non-regular artifact tree entry")

        try:
            visit(fd, base)
        finally:
            os.close(fd)
        return found
