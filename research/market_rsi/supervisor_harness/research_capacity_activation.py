"""Idle version selection around the existing journal; never executes patches.

Root keeps its existing serial admission lock across selection and downstream
use. This caller verifies reviewed source bytes, not OS containment or review
truth. Immutable registry records are prepared before native journal acceptance.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

from market_rsi import digest
from data_scientist_harness import co_evolution_loop as micro
from supervisor_harness import research_capacity_identity as identity


def pair(manifest):
    return {"harness_sha256": manifest["H"], "researcher_sha256": manifest["R"]}


def patch_digest(before, after):
    return digest({"before": before["components"], "after": after["components"]})


def _read(binding, *, allow_alias=False):
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError("exact artifact binding required")
    location = Path(binding["path"])
    if not location.is_absolute() or not location.is_file() or (location.is_symlink() and not allow_alias):
        raise ValueError("regular absolute artifact path required")
    data = location.read_bytes()
    if hashlib.sha256(data).hexdigest() != identity.sha(binding["sha256"]):
        raise ValueError("artifact bytes drifted")
    return data


class CapacityActivation:
    def __init__(self, batch, *, source_root, registry_root, baseline, entrypoints):
        self.batch, self.source_root = batch, Path(source_root)
        self.registry = Path(registry_root)
        if (not self.source_root.is_absolute() or self.source_root.resolve(strict=True) != self.source_root
                or not self.registry.is_absolute() or self.registry.resolve() != self.registry
                or any(part in {".git", ".codex", ".agents"} for part in self.registry.parts)):
            raise ValueError("canonical absolute source/registry roots required")
        self.registry.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.baseline = identity.validate(baseline)
        self.initial_entrypoints = dict(entrypoints)
        self._store(baseline, entrypoints)
        self._selected(batch.snapshot())

    def _verify_files(self, value):
        identity.validate(value)
        for binding in value["components"].values():
            for name, token in binding["sources"].items():
                location = self.source_root / name
                if location.resolve(strict=True) != location or location.is_symlink():
                    raise ValueError("source must be an immutable in-root regular file")
                _read({"path": str(location), "sha256": token})
        _read(value["runtime"]["python"], allow_alias=True)

    def _scope(self, binding, value, entrypoints, proposer=None):
        receipt = json.loads(_read(binding))
        if (receipt.get("passed") is not True or receipt.get("reviewer_id") != self.batch.snapshot()["micro_evolution"]["reviewer_id"]
                or receipt.get("reviewer_id") == receipt.get("proposer_id")
                or (proposer is not None and receipt.get("proposer_id") != proposer)
                or receipt.get("identity_sha256") != digest(value) or receipt.get("entrypoints") != entrypoints):
            raise ValueError("independent exact source/scope review required before shadow use")

    def _store(self, value, entrypoints, static_review=None):
        self._verify_files(value)
        if set(entrypoints) != {"H", "R"} or any(
                name not in value["components"][axis]["sources"] or not name.endswith(".py")
                for axis, name in entrypoints.items()):
            raise ValueError("entrypoints must belong to exact reviewed H/R sources")
        body = {"manifest": value, "entrypoints": entrypoints, "static_review": static_review}
        target = self.registry / (digest(pair(value)) + ".json")
        data = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        try:
            with target.open("x", encoding="utf-8") as stream:
                stream.write(data)
        except FileExistsError:
            if target.read_text(encoding="utf-8") != data:
                raise ValueError("immutable version record conflicts") from None

    def _version(self, selected):
        location = self.registry / (digest(selected) + ".json")
        if location.is_symlink():
            raise ValueError("version record must not be a symlink")
        body = json.loads(location.read_text(encoding="utf-8"))
        if set(body) != {"manifest", "entrypoints", "static_review"}:
            raise ValueError("exact immutable version record required")
        self._verify_files(body["manifest"])
        if body["static_review"] is None:
            if body["manifest"] != self.baseline or body["entrypoints"] != self.initial_entrypoints:
                raise ValueError("unreviewed non-baseline version")
        else:
            self._scope(body["static_review"], body["manifest"], body["entrypoints"])
        if pair(body["manifest"]) != selected:
            raise ValueError("registry version differs from selected native pair")
        if any(self.baseline[k] != body["manifest"][k]
               for k in ("K", "M", "C", "memory_sha256", "runtime_sha256")):
            raise ValueError("activation changed protected context or predictor/memory")
        return body

    def _selected(self, state):
        return self._version(state["micro_evolution"]["active_pair"])

    def _state(self, expected, *, idle=False):
        state = self.batch.snapshot()
        if state["state_sha256"] != expected:
            raise ValueError("stale activation snapshot")
        if idle and (state.get("active_attempt_ids") or any(
                branch["stage"] in {"implementation_ready", "execution_claimed"}
                for branch in state["branches"])):
            raise ValueError("capacity activation and rollback require idle execution")
        self._selected(state)
        return state

    def propose(self, after, proposal, entrypoints, *, static_review, expected_state_sha256):
        state = self._state(expected_state_sha256)
        before = self._selected(state)["manifest"]
        axis = identity.change_axis(before, after)
        if axis not in {"H", "R"} or proposal["axis"] != {"H": "harness", "R": "researcher"}[axis]:
            raise ValueError("one capacity policy may change; predictor/memory must stay fixed")
        old, new = before["components"][axis]["sources"], after["components"][axis]["sources"]
        changed = {name for name in set(old) | set(new) if old.get(name) != new.get(name)}
        if (changed != set(proposal["write_paths"]) or not changed
                or proposal["patch_sha256"] != patch_digest(before, after)
                or proposal["pair"] != pair(after)):
            raise ValueError("proposal differs from measured exact file delta")
        self._scope(static_review, after, entrypoints, proposal["proposer_id"])
        self._store(after, entrypoints, static_review)
        return self.batch.record_micro_evolution("propose", proposal,
                    expected_state_sha256=expected_state_sha256)

    def review(self, receipt, *, expected_state_sha256):
        state = self._state(expected_state_sha256, idle=True)
        envelope = json.loads(_read(receipt))
        if set(envelope) != {"review", "evidence"}:
            raise ValueError("exact independent review/evidence envelope required")
        review, pending = envelope["review"], state["micro_evolution"]["pending"]
        if pending is None:
            raise ValueError("no pending proposal")
        if review["decision"] == "accept":
            after = self._version(pending["pair"])["manifest"]
            before = self._selected(state)["manifest"]
            for check in review["checks"].values():
                _read({"path": envelope["evidence"][check["evidence_sha256"]],
                       "sha256": check["evidence_sha256"]})
            token = review["benefit_evidence_sha256"]
            benefit = json.loads(_read({"path": envelope["evidence"][token], "sha256": token}))
            if (benefit.get("proposal_sha256") != pending["record_sha256"]
                    or benefit.get("before_identity_sha256") != digest(before)
                    or benefit.get("after_identity_sha256") != digest(after)
                    or benefit.get("effect") != pending["behavior_change"]
                    or benefit.get("benefit_observed") is not True):
                raise ValueError("measured benefit does not bind exact before/after proposal")
        return self.batch.record_micro_evolution("review", review,
                    expected_state_sha256=expected_state_sha256)

    def rollback(self, receipt, *, expected_state_sha256):
        state = self._state(expected_state_sha256, idle=True)
        previous = state["micro_evolution"]["previous_pair"]
        if previous is None:
            raise ValueError("no accepted previous version")
        self._version(previous)
        value = json.loads(_read(receipt))
        return self.batch.record_micro_evolution("rollback", value,
                    expected_state_sha256=expected_state_sha256)

    def resolve(self, axis, *, expected_pair_sha256, shadow_proposal_sha256=None):
        """Import only the reviewed selected version; shadow tests never activate."""
        if axis not in {"H", "R"}:
            raise ValueError("only H/R entrypoints can be resolved")
        state = self.batch.snapshot()
        current = state["micro_evolution"]
        if digest(current["active_pair"]) != expected_pair_sha256:
            raise ValueError("stale downstream selected pair")
        selected = current["active_pair"]
        if shadow_proposal_sha256 is not None:
            if not current["pending"] or current["pending"]["record_sha256"] != shadow_proposal_sha256:
                raise ValueError("shadow use must bind the pending proposal")
            selected = current["pending"]["pair"]
        body = self._version(selected)
        name = body["entrypoints"][axis]
        location = self.source_root / name
        data = _read({"path": str(location), "sha256": body["manifest"]["components"][axis]["sources"][name]})
        spec = importlib.util.spec_from_file_location("capacity_" + selected[{"H": "harness_sha256", "R": "researcher_sha256"}[axis]], location)
        module = importlib.util.module_from_spec(spec)
        exec(compile(data, str(location), "exec"), module.__dict__)
        if self.batch.snapshot()["state_sha256"] != state["state_sha256"]:
            raise ValueError("capacity state changed during downstream resolution")
        return module
