"""Supervisor-injected, once-only handoffs; no science or budget authority.

Callbacks are trusted implementations, never model-supplied commands. The
admission callback must enforce the existing authorized ledger and deadlines.
Recorded dependency means feedback was delivered, not that it improved a choice.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

from supervisor_harness import account_controller_feedback_consumer as c

STAGES = ("input", "controller", "implement", "source_review", "execute",
          "result_review", "reconcile")


class LoopHalted(RuntimeError):
    """Inspect preserved evidence; never automatically retry an uncertain stage."""


def _copy(value):
    return c._json(json.dumps(value, sort_keys=True, allow_nan=False))


def _artifacts(value):
    if isinstance(value, dict):
        if set(value) == {"path", "sha256"}:
            c._read(value, binary=True)
            return
        for binding in value.get("artifacts", []):
            c._read(binding, binary=True)
        for item in value.values():
            _artifacts(item)
    elif isinstance(value, list):
        for item in value:
            _artifacts(item)


def _read_pair(path):
    binding = path.with_suffix(".binding.json")
    if not path.exists() or not binding.exists():
        raise LoopHalted("incomplete durable record: " + str(path))
    if any(item.resolve() != item or item.is_symlink() for item in (path, binding)):
        raise LoopHalted("durable record symlink/path drift")
    commitment = c._json(binding.read_bytes())
    if commitment.get("path") != str(path):
        raise LoopHalted("record path drift")
    return c._read(commitment)


def _save_pair(path, value):
    c.save(path, value)
    c.save(path.with_suffix(".binding.json"), {"path": str(path), "sha256": c.sha(path)})


def run(root, handlers, *, seed, admit, max_rounds, handler_identity):
    """Run/resume seven trusted stages; uncertain claims are terminal for this ID.

    ``handler_identity()`` must freshly derive seven source-handler bindings,
    including their common admission contract and dependencies.
    Each handler receives {round_index, seed, previous_result,
    previous_feedback_sha256, outputs}. Outputs are JSON objects; an optional
    ``artifacts`` list contains exact {path, sha256} immutable file bindings.
    ``admit(context + stage) is True`` is required before every new stage claim.
    No reservation is performed here: the existing ledger remains authoritative.
    """
    if (set(handlers) != set(STAGES) or any(not callable(v) for v in handlers.values())
            or not callable(admit) or not callable(handler_identity)
            or type(max_rounds) is not int or max_rounds < 1):
        raise ValueError("exact trusted handlers, admission and positive round bound required")
    seed = _copy(seed)
    _artifacts(seed)
    root = Path(root).absolute()
    if root.is_symlink() or root.resolve() != root:
        raise ValueError("canonical non-symlink loop root required")
    identities = _copy(handler_identity())
    if (type(identities) is not dict or set(identities) != set(STAGES)
            or any(not value for value in identities.values())):
        raise ValueError("exact nonempty handler source identities required")
    _artifacts(identities)
    manifest = {"schema": "feedback_linked_loop_v1", "seed": seed,
        "seed_sha256": c._digest(seed), "handler_identity": identities,
        "driver_source_sha256": c.sha(Path(__file__).resolve()), "max_rounds": max_rounds}
    def context(index, previous, outputs):
        return {"round_index": index, "seed": seed, "previous_result": previous,
            "previous_feedback_sha256": c._digest(previous), "outputs": outputs}
    path = root / "manifest.json"
    existing = path.exists() or path.with_suffix(".binding.json").exists()
    initial = context(1, seed, {})
    if not existing and admit(_copy({**initial, "stage": "input"})) is not True:
        return {"status": "stopped", "completed_rounds": 0, "stage": "input"}
    root.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(root / ".loop.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LoopHalted("another loop owns this root") from exc
        if path.exists() or path.with_suffix(".binding.json").exists():
            if _read_pair(path) != manifest:
                raise LoopHalted("seed, source, handler or bound drift")
        else:
            _save_pair(path, manifest)
        previous = seed
        completed = 0
        for index in range(1, max_rounds + 1):
            outputs = {}
            for stage in STAGES:
                current = context(index, previous, outputs)
                if _copy(handler_identity()) != identities:
                    raise LoopHalted("handler source drift")
                _artifacts(identities)
                _artifacts(current)
                if c.sha(Path(__file__).resolve()) != manifest["driver_source_sha256"]:
                    raise LoopHalted("driver source drift")
                prefix = root / f"round-{index:04d}-{stage}"
                claim = prefix.with_suffix(".claim.json")
                done = prefix.with_suffix(".done.json")
                expected = {"round_index": index, "stage": stage,
                    "context_sha256": c._digest(current),
                    "manifest_sha256": c.sha(path),
                    "previous_feedback_sha256": current["previous_feedback_sha256"]}
                if claim.exists():
                    if claim.is_symlink() or prefix.with_suffix(".failed.json").exists():
                        raise LoopHalted("failed/uncertain stage remains closed to retry")
                    if c._json(claim.read_bytes()) != expected:
                        raise LoopHalted("claim/input dependency drift")
                    result = _read_pair(done)
                    if (result.get("claim_sha256") != c.sha(claim)
                            or result.get("output_sha256") != c._digest(result.get("output"))):
                        raise LoopHalted("completed stage output drift")
                    output = result["output"]
                    _artifacts(output)
                else:
                    if (done.exists() or done.with_suffix(".binding.json").exists()
                            or prefix.with_suffix(".failed.json").exists()):
                        raise LoopHalted("orphaned stage evidence")
                    if admit(_copy({**current, "stage": stage})) is not True:
                        return {"status": "stopped", "completed_rounds": completed,
                                "round_index": index, "stage": stage}
                    if (_copy(handler_identity()) != identities
                            or c.sha(Path(__file__).resolve()) != manifest["driver_source_sha256"]):
                        raise LoopHalted("source drift after admission; no callback")
                    _artifacts(current)
                    _artifacts(identities)
                    c.save(claim, expected)
                    try:
                        output = _copy(handlers[stage](_copy(current)))
                        if type(output) is not dict:
                            raise ValueError("handler output must be a JSON object")
                        if (_copy(handler_identity()) != identities
                                or c.sha(Path(__file__).resolve()) != manifest["driver_source_sha256"]):
                            raise ValueError("handler/driver source changed during callback")
                        _artifacts(output)
                        _save_pair(done, {"claim_sha256": c.sha(claim),
                            "output": output, "output_sha256": c._digest(output)})
                    except BaseException as exc:
                        failure = prefix.with_suffix(".failed.json")
                        if not failure.exists():
                            c.save(failure, {"claim_sha256": c.sha(claim),
                                "exception_type": type(exc).__name__, "retry_allowed": False})
                        raise LoopHalted(f"uncertain/failed round {index} {stage}; no retry") from exc
                outputs[stage] = output
            previous = outputs["reconcile"]
            completed += 1
        return {"status": "completed", "completed_rounds": completed, "result": previous}
