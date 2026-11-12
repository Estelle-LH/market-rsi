"""Isolated synthetic diagnostic candidate, not a live-runner patch.

Observers receive timeout_seconds=8. Injected callbacks do not prove OS deadlines:
production transport remains out of scope and must retain its actual eight-second
subprocess limits. A healthy check covers only its observation instant, not
long-duration stability. This module has no Docker transport or container creation.
"""

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from subprocess import TimeoutExpired


TIMEOUT_SECONDS = 8


def _digest(value):
    if type(value) is not str:
        raise TypeError("identity must be a string")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FrozenHashes:
    cli: str
    context: str
    daemon: str


class IdentityCheckError(RuntimeError):
    def __init__(self, codes, receipt_path):
        self.codes = tuple(codes)
        self.receipt_path = receipt_path
        super().__init__("identity check failed: " + ", ".join(self.codes))


class ReceiptPersistenceError(RuntimeError):
    pass


def _persist_receipt(directory, receipt):
    """Publish a complete unique file without replacing any existing receipt."""
    fd, temporary_name = tempfile.mkstemp(
        prefix=".identity-receipt-", suffix=".tmp", dir=directory)
    temporary = Path(temporary_name)
    final = temporary.with_name(temporary.name[1:-4] + ".json")
    try:
        with os.fdopen(fd, "w", encoding="ascii") as stream:
            json.dump(receipt, stream, sort_keys=True, ensure_ascii=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link publication is atomic and fails rather than overwriting a name.
        os.link(temporary, final)
        temporary.unlink()
        directory_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return final
    finally:
        if temporary.exists():
            temporary.unlink()


class IdentityDiagnostic:
    def __init__(self, initial_cli, initial_context, initial_daemon,
                 observe_context, observe_daemon, receipt_directory):
        self._initial = FrozenHashes(_digest(initial_cli), _digest(initial_context),
                                     _digest(initial_daemon))
        self._observe_context = observe_context
        self._observe_daemon = observe_daemon
        self._receipt_directory = Path(receipt_directory)

    @property
    def initial_hashes(self):
        return self._initial

    def before_create(self):
        initial = asdict(self._initial)
        observed = {"cli": None, "context": None, "daemon": None}
        states = {"cli": "NOT_OBSERVED"}
        failures = []
        for label, observer in (("context", self._observe_context),
                                ("daemon", self._observe_daemon)):
            try:
                observed[label] = _digest(observer(timeout_seconds=TIMEOUT_SECONDS))
            except (TimeoutError, TimeoutExpired):
                states[label] = "TIMEOUT"
                failures.append(label.upper() + "_TIMEOUT")
            except Exception:
                # Do not persist exception text, reprs, or raw identity values.
                states[label] = "ERROR"
                failures.append(label.upper() + "_OBSERVER_ERROR")
            else:
                if observed[label] != initial[label]:
                    states[label] = "DRIFT"
                    failures.append(label.upper() + "_DRIFT")
                else:
                    states[label] = "MATCH"
        if not failures:
            result = "STABLE"
        elif failures == ["CONTEXT_DRIFT", "DAEMON_DRIFT"]:
            result = "CONTEXT_AND_DAEMON_DRIFT"
        elif len(failures) == 1:
            result = failures[0]
        else:
            result = "MULTIPLE_FAILURES"
        receipt = {
            "schema_version": 1,
            "timeout_seconds": TIMEOUT_SECONDS,
            "initial_hashes": initial,
            "observed_hashes": observed,
            "observations": states,
            "failures": failures,
            "result": result,
            "passed": not failures,
        }
        try:
            path = _persist_receipt(self._receipt_directory, receipt)
        except Exception:
            # Even a matching observation cannot authorize create without durability.
            raise ReceiptPersistenceError("receipt persistence failed; creation blocked") from None
        if failures:
            raise IdentityCheckError(failures, path)
        return path

    def guarded_create(self, fake_create):
        """Demonstrate ordering only; the caller supplies a synthetic callable."""
        self.before_create()
        return fake_create()
