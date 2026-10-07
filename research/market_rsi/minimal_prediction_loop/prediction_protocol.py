"""Deterministic, label-free, sequential probability prediction protocol.

This module is a protocol-integrity primitive for a trusted local runner.  It
does *not* isolate untrusted code.  In particular, every receipt keeps
``real_isolation_admitted`` false.  A separately authorized container canary
would be required before making a real filesystem or process-isolation claim.

The trusted runner owns the complete ordered list of public as-of rows.  A
candidate receives exactly one :data:`PUBLIC_RELEASE_FIELDS` mapping at a
time.  The next row cannot be released until the preceding probability has
been validated and appended to a hash-chained, fsynced journal.

The candidate-visible schema is deliberately small and closed::

    schema, run_id, sequence, row_id, event_id, market_id, cutoff_ms,
    feature_available_ms, market_probability

Outcomes, labels, evaluator paths, scorer state, future features, and extra
fields are rejected before the first row is released.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


PROTOCOL_SCHEMA = "minimal_label_free_prediction_protocol_v1"
PUBLIC_ROW_SCHEMA = "minimal_prediction_public_as_of_row_v1"
PREDICTION_SCHEMA = "minimal_prediction_submission_v1"
COMMIT_RECEIPT_SCHEMA = "minimal_prediction_commit_receipt_v1"
COMPLETE_RECEIPT_SCHEMA = "minimal_prediction_complete_receipt_v1"
PROBABILITY_EPSILON = 1e-6

# Source rows accepted by the trusted runner.  These are all and only the
# as-of values a candidate may use to form a settlement probability.
PUBLIC_AS_OF_FIELDS = frozenset(
    {
        "event_id",
        "market_id",
        "cutoff_ms",
        "feature_available_ms",
        "market_probability",
    }
)

# Exact flat mapping returned by ``release_next`` and passed to a candidate.
# Protocol identity fields are public; no trusted filesystem path is exposed.
PUBLIC_RELEASE_FIELDS = frozenset(
    {
        "schema",
        "run_id",
        "sequence",
        "row_id",
        *PUBLIC_AS_OF_FIELDS,
    }
)

# Exact candidate response.  Extra diagnostics are intentionally not accepted:
# they could become an accidental channel for labels or evaluator internals.
PREDICTION_SUBMISSION_FIELDS = frozenset(
    {"schema", "run_id", "sequence", "row_id", "probability"}
)

_JOURNAL_FIELDS = frozenset(
    {
        "schema",
        "journal_sequence",
        "event",
        "run_id",
        "sequence",
        "row_id",
        "public_row_sha256",
        "probability",
        "prediction_id",
        "previous_hash",
        "hash",
    }
)
_CLAIM_FIELDS = frozenset(
    {
        "schema",
        "run_key",
        "run_id",
        "candidate_sha256",
        "public_rows_sha256",
        "expected_predictions",
        "row_ids",
        "label_free",
        "scoring_authorized",
        "real_isolation_admitted",
    }
)
_CHECKPOINT_FIELDS = frozenset(
    {
        "schema",
        "run_id",
        "journal_entries",
        "journal_head_sha256",
        "journal_sha256",
        "journal_bytes",
        "real_isolation_admitted",
    }
)
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_RUN_ID = re.compile(r"run-[0-9a-f]{64}\Z")
_PUBLIC_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_ZERO_HASH = "0" * 64


class PredictionProtocolError(ValueError):
    """Raised when a protocol invariant would be violated."""


class PredictionJournalIntegrityError(PredictionProtocolError):
    """Raised when durable state is malformed, rewritten, or incomplete."""


def _encoded(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise PredictionProtocolError("canonical JSON value required") from error


def fingerprint(value: Any) -> str:
    """Return the protocol's deterministic canonical-JSON SHA-256."""

    return hashlib.sha256(_encoded(value)).hexdigest()


def _require_hash(value: Any, name: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise PredictionProtocolError(f"{name} must be a lowercase SHA-256")
    return value


def _require_identifier(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 200
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise PredictionProtocolError(f"bounded printable {name} required")
    return value


def _probability(value: Any) -> float | int:
    if type(value) not in {int, float} or not math.isfinite(value):
        raise PredictionProtocolError("finite numeric probability required")
    result = float(value)
    if not PROBABILITY_EPSILON <= result <= 1 - PROBABILITY_EPSILON:
        raise PredictionProtocolError(
            "probability violates the frozen open-endpoint epsilon policy"
        )
    return result


def _integer_timestamp(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise PredictionProtocolError(f"{name} must be a nonnegative integer")
    return value


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_once(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("xb") as output:
        output.write(_encoded(dict(value)) + b"\n")
        output.flush()
        os.fsync(output.fileno())
    _fsync_directory(path.parent)


def _replace_json(path: Path, value: Mapping[str, Any]) -> None:
    """Durably replace a small trusted checkpoint without in-place rewriting."""

    pending = path.with_name(path.name + ".next")
    with pending.open("xb") as output:
        output.write(_encoded(dict(value)) + b"\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(pending, path)
    _fsync_directory(path.parent)


def _read_one_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PredictionJournalIntegrityError(
            f"unreadable durable protocol file: {path.name}"
        ) from error
    if not isinstance(value, dict):
        raise PredictionJournalIntegrityError(
            f"durable protocol file is not an object: {path.name}"
        )
    return value


def validate_public_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Validate and freeze the exact candidate-visible as-of row sequence.

    Rows must be in deterministic chronological/composite-identity order.  A
    feature timestamp after its cutoff is a future feature and is rejected.
    Exact field equality is intentional: label aliases, outcomes, evaluator
    paths, internal fields, and any other additions all fail closed.
    """

    if not isinstance(rows, (list, tuple)) or not rows:
        raise PredictionProtocolError("nonempty ordered public rows required")
    frozen: list[dict[str, Any]] = []
    identities: set[tuple[str, str, int]] = set()
    previous_order: tuple[int, str, str] | None = None
    for row in rows:
        if not isinstance(row, dict) or set(row) != PUBLIC_AS_OF_FIELDS:
            raise PredictionProtocolError(
                "public row schema mismatch; labels, outcomes, paths, and internal fields are forbidden"
            )
        event_id = _require_identifier(row["event_id"], "event_id")
        market_id = _require_identifier(row["market_id"], "market_id")
        if _PUBLIC_IDENTIFIER.fullmatch(event_id) is None:
            raise PredictionProtocolError("conservative public event_id required")
        if _PUBLIC_IDENTIFIER.fullmatch(market_id) is None:
            raise PredictionProtocolError("conservative public market_id required")
        cutoff_ms = _integer_timestamp(row["cutoff_ms"], "cutoff_ms")
        feature_available_ms = _integer_timestamp(
            row["feature_available_ms"], "feature_available_ms"
        )
        if feature_available_ms > cutoff_ms:
            raise PredictionProtocolError("future row feature is not public at cutoff")
        market_probability = _probability(row["market_probability"])
        identity = (event_id, market_id, cutoff_ms)
        if identity in identities:
            raise PredictionProtocolError("duplicate public row identity")
        identities.add(identity)
        order = (cutoff_ms, event_id, market_id)
        if previous_order is not None and order <= previous_order:
            raise PredictionProtocolError(
                "public rows must be strictly ordered by cutoff/event/market"
            )
        previous_order = order
        frozen.append(
            {
                "event_id": event_id,
                "market_id": market_id,
                "cutoff_ms": cutoff_ms,
                "feature_available_ms": feature_available_ms,
                "market_probability": market_probability,
            }
        )
    return tuple(frozen)


def _row_id(row: Mapping[str, Any]) -> str:
    # Bind the ID to the entire released as-of content, not a caller-controlled
    # ordinal.  Any content rewrite therefore changes the expected row ID.
    return "row-" + fingerprint({"schema": PUBLIC_ROW_SCHEMA, "row": dict(row)})


def deterministic_run_id(
    *, run_key: str, candidate_sha256: str, public_rows: Sequence[Mapping[str, Any]]
) -> str:
    """Derive a stable run ID from its caller key and immutable commitments."""

    run_key = _require_identifier(run_key, "run_key")
    candidate_sha256 = _require_hash(candidate_sha256, "candidate_sha256")
    rows = validate_public_rows(public_rows)
    rows_sha256 = fingerprint(list(rows))
    return "run-" + fingerprint(
        {
            "schema": PROTOCOL_SCHEMA,
            "run_key": run_key,
            "candidate_sha256": candidate_sha256,
            "public_rows_sha256": rows_sha256,
        }
    )


class LabelFreePredictionProtocol:
    """Runner-owned durable state machine for one ordered prediction run.

    Use :meth:`create` once, then :meth:`resume` after a clean process restart.
    Creation is exclusive and deterministic, so recreating a used run is a
    replay.  Resume validates the complete claim and journal before exposing
    state.  A crash with a released-but-uncommitted row remains fail-closed;
    the row is never silently re-released to a fresh candidate process.
    """

    def __init__(
        self,
        directory: Path,
        claim: dict[str, Any],
        rows: tuple[dict[str, Any], ...],
        lock_file: Any,
        *,
        resumed: bool,
    ) -> None:
        self.directory = directory
        self.claim = claim
        self.rows = rows
        self.journal_path = directory / "journal.jsonl"
        self.checkpoint_path = directory / "journal-head.json"
        self.complete_path = directory / "complete.json"
        self._lock_file = lock_file
        self._closed = False
        self._poisoned = False
        self._resumed = resumed
        self._restart_blocked_pending = False
        self._committed = 0
        self._pending: dict[str, Any] | None = None
        self._journal_entries = 0
        self._journal_head = _ZERO_HASH
        self._complete_receipt: dict[str, Any] | None = None
        self._recover()
        self._restart_blocked_pending = resumed and self._pending is not None

    @staticmethod
    def _open_lock(directory: Path) -> Any:
        lock_path = directory / "run.lock"
        lock_file = lock_path.open("a+b")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as error:
            lock_file.close()
            raise PredictionProtocolError("prediction run already has an active owner") from error
        return lock_file

    @classmethod
    def create(
        cls,
        root: str | os.PathLike[str],
        *,
        run_key: str,
        candidate_sha256: str,
        public_rows: Sequence[Mapping[str, Any]],
    ) -> "LabelFreePredictionProtocol":
        """Create a never-before-used run; an existing deterministic ID fails."""

        run_key = _require_identifier(run_key, "run_key")
        candidate_sha256 = _require_hash(candidate_sha256, "candidate_sha256")
        rows = validate_public_rows(public_rows)
        rows_sha256 = fingerprint(list(rows))
        run_id = deterministic_run_id(
            run_key=run_key,
            candidate_sha256=candidate_sha256,
            public_rows=rows,
        )
        row_ids = [_row_id(row) for row in rows]
        root_path = Path(root)
        root_path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root_path.is_symlink() or not root_path.is_dir():
            raise PredictionProtocolError("real protocol state directory required")
        directory = root_path / run_id
        try:
            directory.mkdir(mode=0o700, exist_ok=False)
        except FileExistsError as error:
            raise PredictionProtocolError(
                "deterministic run ID already exists; run replay rejected"
            ) from error
        _fsync_directory(root_path)
        claim = {
            "schema": PROTOCOL_SCHEMA,
            "run_key": run_key,
            "run_id": run_id,
            "candidate_sha256": candidate_sha256,
            "public_rows_sha256": rows_sha256,
            "expected_predictions": len(rows),
            "row_ids": row_ids,
            "label_free": True,
            "scoring_authorized": False,
            "real_isolation_admitted": False,
        }
        try:
            _write_once(directory / "claim.json", claim)
            with (directory / "journal.jsonl").open("xb") as journal:
                journal.flush()
                os.fsync(journal.fileno())
            _write_once(
                directory / "journal-head.json",
                {
                    "schema": PROTOCOL_SCHEMA,
                    "run_id": run_id,
                    "journal_entries": 0,
                    "journal_head_sha256": _ZERO_HASH,
                    "journal_sha256": hashlib.sha256(b"").hexdigest(),
                    "journal_bytes": 0,
                    "real_isolation_admitted": False,
                },
            )
            _fsync_directory(directory)
            lock_file = cls._open_lock(directory)
            return cls(directory, claim, rows, lock_file, resumed=False)
        except Exception:
            # Keep any partial deterministic directory as replay evidence.  It
            # must not be removed and silently retried under the same run ID.
            raise

    @classmethod
    def resume(
        cls,
        root: str | os.PathLike[str],
        *,
        candidate_sha256: str,
        public_rows: Sequence[Mapping[str, Any]],
        run_id: str | None = None,
        run_key: str | None = None,
    ) -> "LabelFreePredictionProtocol":
        """Resume exact durable state, never substituting candidate or rows."""

        candidate_sha256 = _require_hash(candidate_sha256, "candidate_sha256")
        rows = validate_public_rows(public_rows)
        if run_id is None:
            if run_key is None:
                raise PredictionProtocolError("run_id or run_key required for resume")
            run_id = deterministic_run_id(
                run_key=run_key,
                candidate_sha256=candidate_sha256,
                public_rows=rows,
            )
        elif run_key is not None:
            expected = deterministic_run_id(
                run_key=run_key,
                candidate_sha256=candidate_sha256,
                public_rows=rows,
            )
            if run_id != expected:
                raise PredictionProtocolError("run ID does not match run key commitments")
        if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
            raise PredictionProtocolError("valid deterministic run_id required")
        directory = Path(root) / run_id
        if directory.is_symlink() or not directory.is_dir():
            raise PredictionProtocolError("durable prediction run not found")
        claim = _read_one_json(directory / "claim.json")
        cls._validate_claim(claim, rows, candidate_sha256, run_id)
        lock_file = cls._open_lock(directory)
        try:
            return cls(directory, claim, rows, lock_file, resumed=True)
        except Exception:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
            raise

    @staticmethod
    def _validate_claim(
        claim: Mapping[str, Any],
        rows: tuple[dict[str, Any], ...],
        candidate_sha256: str,
        run_id: str,
    ) -> None:
        expected_rows_hash = fingerprint(list(rows))
        if set(claim) != _CLAIM_FIELDS:
            raise PredictionJournalIntegrityError("claim schema changed")
        expected_run_id = deterministic_run_id(
            run_key=claim.get("run_key"),
            candidate_sha256=candidate_sha256,
            public_rows=rows,
        )
        if (
            claim.get("schema") != PROTOCOL_SCHEMA
            or claim.get("run_id") != run_id
            or expected_run_id != run_id
            or claim.get("candidate_sha256") != candidate_sha256
            or claim.get("public_rows_sha256") != expected_rows_hash
            or claim.get("expected_predictions") != len(rows)
            or claim.get("row_ids") != [_row_id(row) for row in rows]
            or claim.get("label_free") is not True
            or claim.get("scoring_authorized") is not False
            or claim.get("real_isolation_admitted") is not False
        ):
            raise PredictionJournalIntegrityError("claim commitments do not match resume input")

    @property
    def run_id(self) -> str:
        return self.claim["run_id"]

    @property
    def committed_predictions(self) -> int:
        return self._committed

    @property
    def completed(self) -> bool:
        return self._complete_receipt is not None

    def _ensure_open(self) -> None:
        if self._closed:
            raise PredictionProtocolError("prediction protocol owner is closed")
        if self._poisoned:
            raise PredictionProtocolError(
                "prediction protocol durability is uncertain; owner is fail-closed"
            )

    def _release(self, sequence: int) -> dict[str, Any]:
        row = self.rows[sequence]
        return {
            "schema": PUBLIC_ROW_SCHEMA,
            "run_id": self.run_id,
            "sequence": sequence,
            "row_id": self.claim["row_ids"][sequence],
            **row,
        }

    def _expected_prediction_id(
        self, release: Mapping[str, Any], probability: float | int
    ) -> str:
        return "prediction-" + fingerprint(
            {
                "schema": PREDICTION_SCHEMA,
                "run_id": self.run_id,
                "sequence": release["sequence"],
                "row_id": release["row_id"],
                "probability": probability,
            }
        )

    def _validate_journal_record(
        self,
        record: Any,
        *,
        journal_sequence: int,
        previous_hash: str,
        committed: int,
        pending: dict[str, Any] | None,
    ) -> tuple[int, dict[str, Any] | None, str]:
        if not isinstance(record, dict) or set(record) != _JOURNAL_FIELDS:
            raise PredictionJournalIntegrityError("journal record schema changed")
        body = {key: value for key, value in record.items() if key != "hash"}
        if (
            record["schema"] != PROTOCOL_SCHEMA
            or type(record["journal_sequence"]) is not int
            or record["journal_sequence"] != journal_sequence
            or record["run_id"] != self.run_id
            or record["previous_hash"] != previous_hash
            or record["hash"] != fingerprint(body)
        ):
            raise PredictionJournalIntegrityError("journal sequence or hash-chain mismatch")
        event = record["event"]
        if event == "row_released":
            if pending is not None or committed >= len(self.rows):
                raise PredictionJournalIntegrityError("duplicate or out-of-order row release")
            expected = self._release(committed)
            if (
                record["sequence"] != committed
                or record["row_id"] != expected["row_id"]
                or record["public_row_sha256"] != fingerprint(expected)
                or record["probability"] is not None
                or record["prediction_id"] is not None
            ):
                raise PredictionJournalIntegrityError("released row was skipped or substituted")
            pending = expected
        elif event == "prediction_committed":
            if pending is None:
                raise PredictionJournalIntegrityError("prediction replay or commit without release")
            try:
                probability = _probability(record["probability"])
            except PredictionProtocolError as error:
                raise PredictionJournalIntegrityError(str(error)) from error
            expected_prediction_id = self._expected_prediction_id(pending, probability)
            if (
                record["sequence"] != pending["sequence"]
                or record["row_id"] != pending["row_id"]
                or record["public_row_sha256"] != fingerprint(pending)
                or record["prediction_id"] != expected_prediction_id
            ):
                raise PredictionJournalIntegrityError("prediction row binding mismatch")
            committed += 1
            pending = None
        else:
            raise PredictionJournalIntegrityError("unknown journal event")
        return committed, pending, record["hash"]

    def _recover(self) -> None:
        self._ensure_open()
        committed = 0
        pending: dict[str, Any] | None = None
        previous_hash = _ZERO_HASH
        entries = 0
        try:
            journal_bytes = self.journal_path.read_bytes()
        except OSError as error:
            raise PredictionJournalIntegrityError("prediction journal missing") from error
        for line in journal_bytes.splitlines(keepends=True):
            if not line.endswith(b"\n"):
                raise PredictionJournalIntegrityError("torn journal line")
            try:
                record = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise PredictionJournalIntegrityError("malformed journal line") from error
            committed, pending, previous_hash = self._validate_journal_record(
                record,
                journal_sequence=entries,
                previous_hash=previous_hash,
                committed=committed,
                pending=pending,
            )
            entries += 1
        checkpoint = _read_one_json(self.checkpoint_path)
        if (
            set(checkpoint) != _CHECKPOINT_FIELDS
            or checkpoint.get("schema") != PROTOCOL_SCHEMA
            or checkpoint.get("run_id") != self.run_id
            or checkpoint.get("journal_entries") != entries
            or checkpoint.get("journal_head_sha256") != previous_hash
            or checkpoint.get("journal_sha256")
            != hashlib.sha256(journal_bytes).hexdigest()
            or checkpoint.get("journal_bytes") != len(journal_bytes)
            or checkpoint.get("real_isolation_admitted") is not False
        ):
            raise PredictionJournalIntegrityError(
                "journal differs from its durable head checkpoint"
            )
        self._committed = committed
        self._pending = pending
        self._journal_entries = entries
        self._journal_head = previous_hash
        self._complete_receipt = None
        if self.complete_path.exists():
            receipt = _read_one_json(self.complete_path)
            self._validate_complete_receipt(receipt)
            self._complete_receipt = receipt

    def _append_event(
        self,
        *,
        event: str,
        release: Mapping[str, Any],
        probability: float | int | None,
        prediction_id: str | None,
    ) -> None:
        body = {
            "schema": PROTOCOL_SCHEMA,
            "journal_sequence": self._journal_entries,
            "event": event,
            "run_id": self.run_id,
            "sequence": release["sequence"],
            "row_id": release["row_id"],
            "public_row_sha256": fingerprint(release),
            "probability": probability,
            "prediction_id": prediction_id,
            "previous_hash": self._journal_head,
        }
        record = {**body, "hash": fingerprint(body)}
        try:
            with self.journal_path.open("ab") as journal:
                journal.write(_encoded(record) + b"\n")
                journal.flush()
                # release_next and commit_prediction return only after this fsync.
                os.fsync(journal.fileno())
            journal_bytes = self.journal_path.read_bytes()
            _replace_json(
                self.checkpoint_path,
                {
                    "schema": PROTOCOL_SCHEMA,
                    "run_id": self.run_id,
                    "journal_entries": self._journal_entries + 1,
                    "journal_head_sha256": record["hash"],
                    "journal_sha256": hashlib.sha256(journal_bytes).hexdigest(),
                    "journal_bytes": len(journal_bytes),
                    "real_isolation_admitted": False,
                },
            )
            self._recover()
        except Exception:
            # The caller cannot know whether a failed fsync reached stable
            # storage.  Never release another row from this process.
            self._poisoned = True
            raise

    def release_next(self) -> dict[str, Any] | None:
        """Durably release one row, or return ``None`` after all commits.

        A pending row blocks another release.  On restart, a dangling release
        remains blocked instead of being replayed to a fresh process.
        """

        self._ensure_open()
        self._recover()
        if self.completed:
            raise PredictionProtocolError("completed run cannot be replayed")
        if self._restart_blocked_pending:
            raise PredictionProtocolError(
                "restart found a released-but-uncommitted row; replay rejected"
            )
        if self._pending is not None:
            raise PredictionProtocolError(
                "previously released row has no durable prediction; replay rejected"
            )
        if self._committed == len(self.rows):
            return None
        release = self._release(self._committed)
        self._append_event(
            event="row_released",
            release=release,
            probability=None,
            prediction_id=None,
        )
        return dict(release)

    def commit_prediction(self, submission: Mapping[str, Any]) -> dict[str, Any]:
        """Validate and fsync the current row's probability before returning."""

        self._ensure_open()
        self._recover()
        if self.completed:
            raise PredictionProtocolError("completed run cannot accept replayed predictions")
        if self._restart_blocked_pending:
            raise PredictionProtocolError(
                "restart found a released-but-uncommitted row; prediction replay rejected"
            )
        if self._pending is None:
            raise PredictionProtocolError("prediction without one current released row")
        if not isinstance(submission, dict) or set(submission) != PREDICTION_SUBMISSION_FIELDS:
            raise PredictionProtocolError(
                "prediction submission schema mismatch; labels, outcomes, paths, and internals are forbidden"
            )
        if (
            submission["schema"] != PREDICTION_SCHEMA
            or submission["run_id"] != self.run_id
            or type(submission["sequence"]) is not int
            or submission["sequence"] != self._pending["sequence"]
            or submission["row_id"] != self._pending["row_id"]
        ):
            raise PredictionProtocolError("prediction run/row sequence mismatch")
        probability = _probability(submission["probability"])
        release = dict(self._pending)
        prediction_id = self._expected_prediction_id(release, probability)
        self._append_event(
            event="prediction_committed",
            release=release,
            probability=probability,
            prediction_id=prediction_id,
        )
        return {
            "schema": COMMIT_RECEIPT_SCHEMA,
            "run_id": self.run_id,
            "sequence": release["sequence"],
            "row_id": release["row_id"],
            "prediction_id": prediction_id,
            "probability": probability,
            "journal_head_sha256": self._journal_head,
            "predictions_committed": self._committed,
            "label_free": True,
            "scored": False,
            "real_isolation_admitted": False,
        }

    def finish(self) -> dict[str, Any]:
        """Write one immutable completion receipt after an exact read-back."""

        self._ensure_open()
        self._recover()
        if self.completed:
            raise PredictionProtocolError("completion receipt already exists; replay rejected")
        if self._pending is not None or self._committed != len(self.rows):
            raise PredictionProtocolError("all released rows must be durably predicted")
        journal_sha256 = hashlib.sha256(self.journal_path.read_bytes()).hexdigest()
        body = {
            "schema": COMPLETE_RECEIPT_SCHEMA,
            "run_id": self.run_id,
            "candidate_sha256": self.claim["candidate_sha256"],
            "public_rows_sha256": self.claim["public_rows_sha256"],
            "predictions": self._committed,
            "journal_entries": self._journal_entries,
            "journal_head_sha256": self._journal_head,
            "journal_sha256": journal_sha256,
            "label_free": True,
            "scored": False,
            "real_isolation_admitted": False,
        }
        receipt = {**body, "receipt_sha256": fingerprint(body)}
        _write_once(self.complete_path, receipt)
        self._recover()
        return dict(receipt)

    def _validate_complete_receipt(self, receipt: Mapping[str, Any]) -> None:
        expected_fields = {
            "schema",
            "run_id",
            "candidate_sha256",
            "public_rows_sha256",
            "predictions",
            "journal_entries",
            "journal_head_sha256",
            "journal_sha256",
            "label_free",
            "scored",
            "real_isolation_admitted",
            "receipt_sha256",
        }
        body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        if (
            set(receipt) != expected_fields
            or receipt.get("schema") != COMPLETE_RECEIPT_SCHEMA
            or receipt.get("run_id") != self.run_id
            or receipt.get("candidate_sha256") != self.claim["candidate_sha256"]
            or receipt.get("public_rows_sha256") != self.claim["public_rows_sha256"]
            or receipt.get("predictions") != self._committed
            or receipt.get("journal_entries") != self._journal_entries
            or receipt.get("journal_head_sha256") != self._journal_head
            or receipt.get("journal_sha256")
            != hashlib.sha256(self.journal_path.read_bytes()).hexdigest()
            or receipt.get("label_free") is not True
            or receipt.get("scored") is not False
            or receipt.get("real_isolation_admitted") is not False
            or receipt.get("receipt_sha256") != fingerprint(body)
        ):
            raise PredictionJournalIntegrityError("completion receipt integrity failure")
        if self._pending is not None or self._committed != len(self.rows):
            raise PredictionJournalIntegrityError("completion receipt covers incomplete journal")

    def completion_receipt(self) -> dict[str, Any]:
        """Return a verified existing completion receipt without reopening work."""

        self._ensure_open()
        self._recover()
        if self._complete_receipt is None:
            raise PredictionProtocolError("prediction run is not complete")
        return dict(self._complete_receipt)

    def prediction_records(self) -> list[dict[str, Any]]:
        """Extract scorer records only from a fully verified completed journal."""

        self._ensure_open()
        self._recover()
        if self._complete_receipt is None:
            raise PredictionProtocolError("prediction run is not complete")
        records: list[dict[str, Any]] = []
        for line in self.journal_path.read_bytes().splitlines():
            record = json.loads(line)
            if record["event"] != "prediction_committed":
                continue
            row = self.rows[record["sequence"]]
            records.append({
                "event_id": row["event_id"],
                "market_id": row["market_id"],
                "cutoff_ms": row["cutoff_ms"],
                "probability": record["probability"],
            })
        if len(records) != len(self.rows):
            raise PredictionJournalIntegrityError(
                "completed journal does not yield the exact prediction mask"
            )
        return records

    def close(self) -> None:
        if not self._closed:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            self._lock_file.close()
            self._closed = True

    def __enter__(self) -> "LabelFreePredictionProtocol":
        self._ensure_open()
        return self

    def __exit__(self, *_error: Any) -> None:
        self.close()


# Short alias for integration code while retaining the boundary in the primary
# class name.
PredictionProtocol = LabelFreePredictionProtocol


def prediction_submission(
    release: Mapping[str, Any], probability: float | int
) -> dict[str, Any]:
    """Build an exact candidate response for a released public row."""

    if not isinstance(release, dict) or set(release) != PUBLIC_RELEASE_FIELDS:
        raise PredictionProtocolError("exact public release required")
    return {
        "schema": PREDICTION_SCHEMA,
        "run_id": release["run_id"],
        "sequence": release["sequence"],
        "row_id": release["row_id"],
        "probability": _probability(probability),
    }


def run_label_free_protocol(
    root: str | os.PathLike[str],
    *,
    run_key: str,
    candidate_sha256: str,
    public_rows: Sequence[Mapping[str, Any]],
    predict: Callable[[dict[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    """Run a trusted fixture callback through the one-row protocol.

    This helper is appropriate for deterministic tests and orchestration.  It
    does not make the callback untrusted or isolated, and its final receipt
    states that explicitly.
    """

    if not callable(predict):
        raise PredictionProtocolError("prediction callback required")
    with LabelFreePredictionProtocol.create(
        root,
        run_key=run_key,
        candidate_sha256=candidate_sha256,
        public_rows=public_rows,
    ) as protocol:
        while True:
            release = protocol.release_next()
            if release is None:
                break
            submission = predict(dict(release))
            protocol.commit_prediction(submission)
        return protocol.finish()


__all__ = [
    "COMMIT_RECEIPT_SCHEMA",
    "COMPLETE_RECEIPT_SCHEMA",
    "LabelFreePredictionProtocol",
    "PREDICTION_SCHEMA",
    "PREDICTION_SUBMISSION_FIELDS",
    "PROBABILITY_EPSILON",
    "PROTOCOL_SCHEMA",
    "PUBLIC_AS_OF_FIELDS",
    "PUBLIC_RELEASE_FIELDS",
    "PUBLIC_ROW_SCHEMA",
    "PredictionJournalIntegrityError",
    "PredictionProtocol",
    "PredictionProtocolError",
    "deterministic_run_id",
    "fingerprint",
    "prediction_submission",
    "run_label_free_protocol",
    "validate_public_rows",
]
