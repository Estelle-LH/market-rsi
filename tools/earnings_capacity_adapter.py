"""Earnings R/H profiles on existing native activation; no model-code execution.

Candidate source is a single literal PROFILE assignment, not arbitrary Python.
The existing activation owns proposal/review/idle/rollback/history checks.
"""
import ast
from copy import deepcopy
import hashlib
import re

from supervisor_harness import research_capacity_activation as activation
from supervisor_harness import research_capacity_identity as identity
from market_rsi import digest
from earnings_http import strict_json

COMPONENTS = {"R": {"research_instructions": "research_policy", "reuse_facts": "memory_policy"},
              "H": {"read_chunk_limit": "tool_interface", "search_hit_limit": "tool_interface"}}


def _literal_assignment(text, name):
    tree = ast.parse(text)
    if (len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign)
            or len(tree.body[0].targets) != 1 or not isinstance(tree.body[0].targets[0], ast.Name)
            or tree.body[0].targets[0].id != name):
        raise ValueError("Only one plain literal assignment is admitted; never execute model code")
    try:
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = [ast.literal_eval(key) for key in node.keys]
                if len(set(keys)) != len(keys):
                    raise ValueError("Duplicate literal dictionary key")
        return ast.literal_eval(tree.body[0].value)
    except TypeError as error:
        raise ValueError("Hashable literal dictionary keys required") from error


def _profile_value(value, axis):
    if type(value) is not dict or set(value) != set(COMPONENTS[axis]) | {"axis"} or value["axis"] != axis:
        raise ValueError("Exact axis profile fields required; no authority or tool expansion")
    if axis == "R":
        text = value["research_instructions"]
        if (type(text) is not str or len(text) > 2200 or len(text.encode()) > 4096
                or type(value["reuse_facts"]) is not bool):
            raise ValueError("Bounded research policy required")
    elif (type(value["read_chunk_limit"]) is not int or not 256 <= value["read_chunk_limit"] <= 20000
          or type(value["search_hit_limit"]) is not int or not 1 <= value["search_hit_limit"] <= 50):
        raise ValueError("H cannot expand original tool bounds")
    return deepcopy(value)


def profile(data, axis):
    if type(axis) is not str or axis not in COMPONENTS or type(data) is not bytes or len(data) > 8192:
        raise ValueError("Bounded literal R/H profile required")
    return _profile_value(_literal_assignment(data.decode(), "PROFILE"), axis)


def micro_delta(before, after, axis):
    """Explicit pilot drift policy; default literal/legacy limits stay intact."""
    if type(axis) is not str or axis not in COMPONENTS:
        raise ValueError("Micro policy requires R or H")
    before, after = _profile_value(before, axis), _profile_value(after, axis)
    changed = [field for field in COMPONENTS[axis] if before[field] != after[field]]
    field = "research_instructions" if axis == "R" else "read_chunk_limit"
    if changed != [field]:
        raise ValueError("Micro policy changes only the single declared pilot field")
    if axis == "R":
        old, new = before[field], after[field]
        if not new.startswith(old):
            raise ValueError("Micro R preserves the complete parent instruction prefix")
        added = new[len(old):]
        if (old and not old.endswith('\n') and not added.startswith('\n')
                or not added.strip() or len(added) > 200 or len(added.encode()) > 512
                or len(added.strip().splitlines()) != 1):
            raise ValueError("Micro R appends one nonblank rule within 200 characters/512 bytes")
    elif 10 * abs(after[field] - before[field]) > before[field]:
        raise ValueError("Micro H relative step exceeds ten percent")
    return {"policy": "earnings_micro_v1", "axis": axis, "field": field,
            "before": before[field], "after": after[field]}


def decision(value, *, parent_pair_sha256, feedback_sha256):
    fields = {"schema", "axis", "component", "parent_pair_sha256", "feedback_sha256", "hypothesis", "expected_effect"}
    if (type(value) is not dict or set(value) != fields or value["schema"] != "earnings_capacity_decision_v1"
            or type(value["axis"]) is not str or value["axis"] not in {"R", "H", "continue"}
            or value["parent_pair_sha256"] != identity.sha(parent_pair_sha256)
            or value["feedback_sha256"] != identity.sha(feedback_sha256)
            or any(type(value[k]) is not str or not 1 <= len(value[k]) <= 1000 for k in ("hypothesis", "expected_effect"))):
        raise ValueError("Typed bounded decision must bind current selected parent and feedback")
    allowed = {"none"} if value["axis"] == "continue" else set(COMPONENTS[value["axis"]].values())
    if type(value["component"]) is not str or value["component"] not in allowed:
        raise ValueError("Unsupported capacity component; preserve proposal, no execution")
    return deepcopy(value)


def author_payload(original):
    """Retain the original envelope; return only its strict business object."""
    fields = {"decision_sha256", "source_text", "test_text"}
    if type(original) is dict and set(original) == fields:
        return deepcopy(original)  # Historical offline fixtures, not transport proof.
    if (type(original) is not dict or original.get("status") != "completed"
            or original.get("error") is not None or type(original.get("output")) is not list
            or any(type(item) is not dict or type(item.get("type")) is not str
                   or item["type"] not in {"reasoning", "message"}
                   for item in original["output"])):
        raise ValueError("Completed no-tool Author envelope required")
    messages = [item for item in original["output"] if item["type"] == "message"]
    if len(messages) != 1:
        raise ValueError("Exactly one final Author message required")
    message = messages[0]
    content = message.get("content")
    if (message.get("role", "assistant") != "assistant" or message.get("status", "completed") != "completed"
            or type(content) is not list or not content
            or any(type(part) is not dict or part.get("type") != "output_text"
                   or type(part.get("text")) is not str or not part["text"] for part in content)):
        raise ValueError("Only nonempty final Author text fragments required")
    value = strict_json("".join(part["text"] for part in content))
    if type(value) is not dict or set(value) != fields:
        raise ValueError("Exact Author business fields required")
    return value


def author_candidate(value, before_profile, chosen):
    """Decode actual Author text and literal test cases; do not write/activate it."""
    if type(chosen) is not dict:
        raise ValueError("Typed Author decision required")
    chosen = decision(chosen, parent_pair_sha256=chosen.get("parent_pair_sha256"),
                      feedback_sha256=chosen.get("feedback_sha256"))
    if chosen["axis"] == "continue":
        raise ValueError("Continue cannot author a child")
    before_profile = _profile_value(before_profile, chosen["axis"])
    value = author_payload(value)
    if (type(value) is not dict or set(value) != {"decision_sha256", "source_text", "test_text"}
            or value["decision_sha256"] != digest(chosen) or chosen["axis"] == "continue"
            or any(type(value[k]) is not str or len(value[k].encode()) > 8192 for k in ("source_text", "test_text"))):
        raise ValueError("Exact Author/source/test attribution required")
    axis = chosen["axis"]
    after = profile(value["source_text"].encode(), axis)
    changed = [k for k in COMPONENTS[axis] if before_profile[k] != after[k]]
    if len(changed) != 1 or COMPONENTS[axis][changed[0]] != chosen["component"]:
        raise ValueError("One named profile component changes per child")
    cases = _literal_assignment(value["test_text"], "CASES")
    if (type(cases) is not list or not 1 <= len(cases) <= 8
            or any(type(c) is not dict or set(c) != {"field", "expected"}
                   or c["field"] != changed[0] or type(c["expected"]) != type(after[changed[0]])
                   or c["expected"] != after[changed[0]] for c in cases)):
        raise ValueError("Nonempty exact Author profile checks required")
    return {"profile": after, "cases": cases, "author_sha256": digest(value),
            "source_sha256": hashlib.sha256(value["source_text"].encode()).hexdigest(),
            "tests_executed": False, "claim": "Configuration/policy child, not arbitrary-code capability"}


class EarningsCapacity(activation.CapacityActivation):
    def propose(self, after, proposal, entrypoints, *, static_review, expected_state_sha256):
        state = self._state(expected_state_sha256)
        before = self._selected(state)
        axis = identity.change_axis(before["manifest"], after)
        if axis not in COMPONENTS:
            raise ValueError("One earnings R/H axis must change")
        def read(value, entries):
            name = entries[axis]
            return profile(activation._read({"path": str(self.source_root / name),
                "sha256": value["components"][axis]["sources"][name]}), axis)
        old, new = read(before["manifest"], before["entrypoints"]), read(after, entrypoints)
        changed = [k for k in COMPONENTS[axis] if old[k] != new[k]]
        if len(changed) != 1 or proposal["component"] != COMPONENTS[axis][changed[0]]:
            raise ValueError("One named earnings profile field per candidate")
        return super().propose(after, proposal, entrypoints, static_review=static_review,
                               expected_state_sha256=expected_state_sha256)

    def _store(self, value, entrypoints, static_review=None):
        for axis, name in entrypoints.items():
            profile(activation._read({"path": str(self.source_root / name),
                                      "sha256": value["components"][axis]["sources"][name]}), axis)
        return super()._store(value, entrypoints, static_review)

    def resolve(self, axis, *, expected_pair_sha256, shadow_proposal_sha256=None):
        if axis not in COMPONENTS:
            raise ValueError("Only earnings R/H profiles may resolve")
        state = self.batch.snapshot()
        current = state["micro_evolution"]
        if digest(current["active_pair"]) != expected_pair_sha256:
            raise ValueError("Stale downstream selected pair")
        selected = current["active_pair"]
        if shadow_proposal_sha256 is not None:
            pending = current["pending"]
            if pending is None or pending["record_sha256"] != shadow_proposal_sha256:
                raise ValueError("Shadow must bind current pending proposal")
            selected = pending["pair"]
        body = self._version(selected)
        name = body["entrypoints"][axis]
        binding = {"path": str(self.source_root / name), "sha256": body["manifest"]["components"][axis]["sources"][name]}
        value = profile(activation._read(binding), axis)
        if self.batch.snapshot()["state_sha256"] != state["state_sha256"]:
            raise ValueError("Capacity state drift during literal resolution")
        return {"profile": value, "receipt": {"axis": axis, "source": binding,
            "selected_pair_sha256": digest(selected), "active_pair_sha256": expected_pair_sha256,
            "shadow": shadow_proposal_sha256 is not None, "model_code_executed": False}}

    def prepare(self, *, expected_pair_sha256, questions, state_message=None, shadow_proposal_sha256=None):
        """Actual bounded R/H hook consumed by a trusted worker; still no send."""
        if shadow_proposal_sha256 is not None:
            snapshot = self.batch.snapshot()
            if digest(snapshot["micro_evolution"]["active_pair"]) != expected_pair_sha256:
                raise ValueError("Stale shadow active parent")
            self._selected(snapshot)  # The active parent still owns the trial.
        options = {"expected_pair_sha256": expected_pair_sha256,
                   "shadow_proposal_sha256": shadow_proposal_sha256}
        r = self.resolve("R", **options)
        h = self.resolve("H", **options)
        messages = [{"role": "user", "content": questions}]
        if r["profile"]["research_instructions"]:
            messages.append({"role": "user", "content": r["profile"]["research_instructions"]})
        if r["profile"]["reuse_facts"] and state_message is not None:
            messages.append(deepcopy(state_message))
        context = {"messages": messages, "tool_bounds": h["profile"], "receipts": [r["receipt"], h["receipt"]],
                   "payload_sha256": digest(messages), "live_dispatch": False}
        if shadow_proposal_sha256 is not None:
            context["shadow_proposal_sha256"] = shadow_proposal_sha256
        return context
