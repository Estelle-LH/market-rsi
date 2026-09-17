"""Supervisor-owned global decision state for recursive research entry.

The human-readable RESEARCH_STATE.md remains the decision record. This
append-only journal pins its exact bytes and serializes cycle claims. It is
an operational consistency gate, not evidence of model authorship or an
empirical result. The journal hash chain detects accidental edits, not an
adversary with write access to the trusted host.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import fcntl
import json

from market_rsi import Journal, file_hash, identifier


ZERO = "0" * 64
EVENTS = {"initialize", "decision_revision", "cycle_claim", "cycle_close"}


def _sha(value: str, label: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise ValueError(f"{label} must be a lowercase SHA256")
    return value


class SupervisorGlobalState:
    def __init__(self, root: Path, decision_doc: Path):
        self.root = Path(root).resolve()
        self.decision_doc = Path(decision_doc).absolute()
        self.journal = Journal(self.root)

    def _document_hash(self) -> str:
        path = self.decision_doc
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 256 * 1024:
            raise ValueError("supervisor decision document missing or unsafe")
        return file_hash(path)

    def _replay(self) -> dict:
        records = self.journal.read()
        if not records or records[0]["event"] != "initialize":
            raise ValueError("supervisor global state is not initialized")
        state = {"decision_doc_sha256": None, "active_cycle": None,
                 "last_review_sha256": ZERO, "completed_cycles": [],
                 "claimed_cycles": []}
        for index, record in enumerate(records):
            event, payload = record["event"], record["payload"]
            if event not in EVENTS or not isinstance(payload, dict):
                raise ValueError("invalid supervisor global-state event")
            if event == "initialize":
                if index or set(payload) != {"decision_doc_sha256"}:
                    raise ValueError("invalid global-state initialization")
                state["decision_doc_sha256"] = _sha(payload["decision_doc_sha256"], "decision document")
            elif event == "decision_revision":
                if (set(payload) != {"previous_sha256", "decision_doc_sha256", "reason"}
                        or state["active_cycle"] is not None
                        or payload["previous_sha256"] != state["decision_doc_sha256"]
                        or not isinstance(payload["reason"], str) or not payload["reason"].strip()):
                    raise ValueError("invalid global decision revision")
                state["decision_doc_sha256"] = _sha(payload["decision_doc_sha256"], "decision document")
            elif event == "cycle_claim":
                if (set(payload) != {"cycle_id", "decision_doc_sha256", "source_sha256",
                                    "prior_canary_sha256"}
                        or state["active_cycle"] is not None
                        or payload["decision_doc_sha256"] != state["decision_doc_sha256"]):
                    raise ValueError("invalid or overlapping cycle claim")
                cycle_id = identifier(payload["cycle_id"])
                if cycle_id in state["claimed_cycles"]:
                    raise ValueError("reused cycle ID")
                _sha(payload["source_sha256"], "source")
                _sha(payload["prior_canary_sha256"], "prior canary")
                state["active_cycle"] = cycle_id
                state["claimed_cycles"].append(cycle_id)
            else:
                if (set(payload) != {"cycle_id", "outcome", "review_sha256"}
                        or payload["cycle_id"] != state["active_cycle"]
                        or payload["outcome"] not in {"passed", "failed"}):
                    raise ValueError("cycle close does not match active claim")
                review_hash = _sha(payload["review_sha256"], "review")
                if payload["outcome"] == "passed" and review_hash == ZERO:
                    raise ValueError("passed cycle has no review")
                state["active_cycle"] = None
                state["last_review_sha256"] = review_hash
                state["completed_cycles"].append(payload["cycle_id"])
        state["head_sha256"] = records[-1]["hash"]
        return state

    def initialize(self) -> dict:
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        with self.journal.locked():
            if self.journal.path.exists():
                raise FileExistsError("global state already initialized")
            self.journal.append("initialize", {"decision_doc_sha256": self._document_hash()})
            return self._replay()

    def snapshot(self) -> dict:
        if not self.root.is_dir():
            raise ValueError("supervisor global state is not initialized")
        lock_path = self.root / ".lock"
        if lock_path.is_symlink() or not lock_path.is_file():
            raise ValueError("supervisor global-state lock missing or unsafe")
        with lock_path.open("r") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH)
            try:
                state = self._replay()
                if self._document_hash() != state["decision_doc_sha256"]:
                    raise ValueError("supervisor decision document changed without a recorded revision")
                return state
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def revise_decision(self, reason: str) -> dict:
        with self.journal.locked():
            state = self._replay()
            if state["active_cycle"] is not None:
                raise ValueError("cannot revise global decision during an active cycle")
            current = self._document_hash()
            if current == state["decision_doc_sha256"]:
                raise ValueError("decision document did not change")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("decision revision needs a reason")
            self.journal.append("decision_revision", {
                "previous_sha256": state["decision_doc_sha256"],
                "decision_doc_sha256": current, "reason": reason.strip()})
            return self._replay()

    def claim(self, cycle_id: str, *, expected_head_sha256: str,
              source_sha256: str, prior_canary_sha256: str) -> dict:
        with self.journal.locked():
            state = self._replay()
            if (state["head_sha256"] != _sha(expected_head_sha256, "expected head")
                    or state["active_cycle"] is not None
                    or self._document_hash() != state["decision_doc_sha256"]):
                raise ValueError("global state stale, changed or already active")
            identifier(cycle_id)
            if cycle_id in state["claimed_cycles"]:
                raise ValueError("cycle ID was already used")
            self.journal.append("cycle_claim", {
                "cycle_id": cycle_id,
                "decision_doc_sha256": state["decision_doc_sha256"],
                "source_sha256": _sha(source_sha256, "source"),
                "prior_canary_sha256": _sha(prior_canary_sha256, "prior canary")})
            return self._replay()

    def close(self, cycle_id: str, *, outcome: str, review_sha256: str = ZERO) -> dict:
        with self.journal.locked():
            state = self._replay()
            if state["active_cycle"] != cycle_id or outcome not in {"passed", "failed"}:
                raise ValueError("global-state close does not match active cycle")
            _sha(review_sha256, "review")
            if outcome == "passed" and review_sha256 == ZERO:
                raise ValueError("passed cycle requires a review hash")
            self.journal.append("cycle_close", {
                "cycle_id": cycle_id, "outcome": outcome,
                "review_sha256": review_sha256})
            return self._replay()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or explicitly advance supervisor global state")
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--decision-doc", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--initialize", action="store_true")
    mode.add_argument("--snapshot", action="store_true")
    mode.add_argument("--revise-decision", metavar="REASON")
    args = parser.parse_args()
    state = SupervisorGlobalState(args.state_root, args.decision_doc)
    if args.initialize:
        result = state.initialize()
    elif args.snapshot:
        result = state.snapshot()
    else:
        result = state.revise_decision(args.revise_decision)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
