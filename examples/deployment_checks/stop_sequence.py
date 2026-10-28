"""Stop sequencing only; original closure verification and exclusion are trusted adapters.

No cloud client, research reader, default lease or default verifier is supplied.
The verifier must independently enforce the real protocol and return its pinned
receipt bindings. These local orchestration checks never certify that protocol.
"""
from dataclasses import dataclass
import hashlib
import json
import re

import command_journal


class StopBlocked(ValueError):
    pass


class StopReleaseFailed(RuntimeError):
    """Stop was acknowledged; recovery must use this exact acknowledgement."""
    def __init__(self, acknowledgement):
        super().__init__('stop acknowledged, but dispatch exclusion release failed')
        self.acknowledgement = dict(acknowledgement)


@dataclass(frozen=True)
class Snapshot:
    run_id: str
    owner_epoch: str
    boot_id: str
    target: str
    terminal_exit_code: int
    workers: int
    containers: int
    pending_requests: int


@dataclass(frozen=True)
class Closure:
    run_id: str
    owner_epoch: str
    bindings: tuple


REQUIRED = frozenset({'terminal', 'finance', 'requests', 'cleanup', 'private_seal', 'memory'})


def _snapshot(value):
    if type(value) is not Snapshot:
        raise StopBlocked('typed observation from trusted adapter required')
    if any(type(getattr(value, k)) is not str or not 1 <= len(getattr(value, k)) <= 128
           for k in ('run_id', 'owner_epoch', 'boot_id', 'target')):
        raise StopBlocked('bounded execution identity required')
    if type(value.terminal_exit_code) is not int or not -255 <= value.terminal_exit_code <= 255:
        raise StopBlocked('actual terminal exit code required')
    if any(type(getattr(value, k)) is not int or getattr(value, k) != 0
           for k in ('workers', 'containers', 'pending_requests')):
        raise StopBlocked('workers, containers and pending requests must be zero')
    return value


def _closure(value, snapshot):
    if (type(value) is not Closure or value.run_id != snapshot.run_id
            or value.owner_epoch != snapshot.owner_epoch or type(value.bindings) is not tuple
            or len(value.bindings) != len(REQUIRED)):
        raise StopBlocked('original closure identity and complete receipt bindings required')
    found = set()
    for item in value.bindings:
        if (type(item) is not tuple or len(item) != 2 or type(item[0]) is not str
                or item[0] not in REQUIRED or item[0] in found or type(item[1]) is not str
                or re.fullmatch('[0-9a-f]{64}', item[1]) is None):
            raise StopBlocked('one exact digest per original closure facet required')
        found.add(item[0])
    if found != REQUIRED:
        raise StopBlocked('incomplete original closure facets')
    return value


def guarded_stop(root, key, *, quiesce, observe, verify_original_closure, stop):
    """Hold caller's real dispatch exclusion throughout checks and submission.

    verify_original_closure must run original validators, not trust JSON flags.
    Nonzero terminal exit is allowed when the original protocol verifies closure.
    Existing journal intent blocks another submission even after lost ACK.
    Adapter exception text is suppressed because it may contain private paths.
    A late release failure preserves a known acknowledgement; it cannot undo stop.
    """
    acknowledgement = None
    submission_started = False
    try:
        with quiesce() as lease:
            first = _snapshot(observe(lease))
            closure = _closure(verify_original_closure(lease, first), first)
            second = _snapshot(observe(lease))
            if second != first:
                raise StopBlocked('execution identity or terminal observation changed')
            payload = {'schema': 'guarded-stop-intent-v1', 'snapshot': first.__dict__,
                       'bindings': sorted(closure.bindings)}
            pin = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

            def submit():
                nonlocal submission_started
                submission_started = True
                # Journal intent is durable before the callback can act.
                identity = stop(lease, second, closure)
                if (type(identity) is not dict or identity.get('target') != first.target):
                    raise StopBlocked('stop acknowledgement target changed')
                return identity

            acknowledgement = command_journal.submit_once(root, key, pin, submit)
        # A context manager may suppress an exception. Never turn that into success.
        if acknowledgement is None:
            if submission_started:
                raise command_journal.DispatchUnknown('stop acknowledgement unknown; do not resubmit')
            raise StopBlocked('no stop acknowledgement')
        return acknowledgement
    except Exception as error:
        if acknowledgement is not None:
            raise StopReleaseFailed(acknowledgement) from None
        if submission_started:
            raise command_journal.DispatchUnknown('stop acknowledgement unknown; do not resubmit') from None
        raise StopBlocked('stop blocked: ' + type(error).__name__) from None
