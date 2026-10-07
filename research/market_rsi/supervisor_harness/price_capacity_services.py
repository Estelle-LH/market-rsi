"""Text-only capacity author: original-bound source/test, no import or activation.

Reuse original transactions, account roles and Git. Formal entry installation,
independent source/benefit review and operational accounting remain separate.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

from supervisor_harness import price_loop_handoff as h
from supervisor_harness import price_capacity_source as guard
from supervisor_harness import research_capacity_identity as identity
from supervisor_harness import research_capacity_activation as activation

t, r, w = h.t, h.r, h.w


def response_schema(decision, repo):
    paths = [path for path in decision["capacity"]["write_paths"] if (repo / path).suffix == ".py"
        and (repo / path).resolve() == repo / path and not (repo / path).exists()]
    sources = [path for path in paths if not Path(path).name.startswith("test_")]
    tests = [path for path in paths if Path(path).name.startswith("test_")]
    if not sources or not tests or not any(Path(a).parent == Path(b).parent for a in sources for b in tests):
        raise ValueError("approved fresh capacity and test paths required before author call")
    return t.c._object({"decision_sha256": {"type": "string", "const": t.c._digest(decision)},
        "change_id": {"type": "string", "const": decision["capacity"]["change_id"]},
        "source_path": {"type": "string", "enum": sources}, "test_path": {"type": "string", "enum": tests},
        **{key: t.c.TEXT for key in ("capacity_source", "test_source", "implementation_notes")}})


def original(runtime, ctx, before, entrypoints):
    prepared = ctx["outputs"]["input"]
    if prepared["authorization"] != runtime.authority or prepared["configuration"] != runtime.configuration:
        raise ValueError("capacity input authority/configuration drift")
    packet = t.c._read(prepared["input"])
    t._review(packet, prepared["input"], runtime.authority, prepared["review"], runtime.repo,
        configuration_binding=runtime.configuration, config=runtime.config)
    decision = t.validate_response(ctx["outputs"]["controller"]["decision"], packet)
    if packet.get("schema") != "controller_price_feedback_input_v2" or decision["action"] not in {"researcher", "harness"}:
        raise ValueError("capacity-only typed original required")
    directory = runtime.root / "decisions" / packet["bindings"]["feedback"]["sha256"]
    if directory.resolve() != directory:
        raise ValueError("original capacity decision directory symlink")
    claim = t._file(directory / "claim.json")
    if runtime.fixed_grant.get("account_roles", {}).get("approved") is True:
        from supervisor_harness import price_account_roles as roles
        if claim.get("controller_transport") != roles.transport_contract():
            raise ValueError("actual native tools-closed Controller original required for capacity author")
    if (claim.get("authorization") != runtime.authority or claim.get("input_binding") != prepared["input"]
            or claim.get("review") != prepared["review"] or claim.get("configuration_sha256") != runtime.configuration["sha256"]
            or t._recover(directory, packet, claim, claim.get("controller_transport")) != decision):
        raise ValueError("actual saved original capacity decision differs")
    ledger = t._file(runtime.root / "ledger.json")
    matches = [row for row in ledger["controller_decisions"] if row.get("status") == "completed"
        and row.get("decision_sha256") == t.c._digest(decision)
        and row.get("completion_sha256") == w.sha(directory / "completion.json")]
    identity.validate(before)
    context = t.action_context(packet)
    if (len(matches) != 1 or context["identity_configuration"]["pair"] != activation.pair(before)
            or context["identity_configuration"]["fixed_context"]["model_sha256"] != before["M"]
            or packet["source_context"].get("capacity_identity") != before
            or packet["source_context"].get("capacity_entrypoints") != entrypoints
            or set(entrypoints) != {"H", "R"}
            or any(entrypoints[axis] not in before["components"][axis]["sources"] for axis in entrypoints)):
        raise ValueError("saved capacity parent/entrypoint/ledger drift")
    return packet, decision


class CapacityAuthor:
    def __init__(self, runtime, inherited_files, grant_binding, *, role_call=None, timeout_seconds=120):
        self.runtime, self.files, self.grant = runtime, dict(inherited_files), grant_binding
        self.call, self.timeout = role_call, timeout_seconds

    def author(self, ctx, before, entrypoints):
        runtime = self.runtime
        if (type(ctx["round_index"]) is not int or ctx["round_index"] < 1
                or not runtime.admit({**ctx, "stage": "implement"})
                or self.grant != runtime.authority or t.c._read(self.grant) != runtime.fixed_grant
                or runtime.fixed_grant.get("account_roles", {}).get("capacity_changes_approved") is not True):
            raise ValueError("fresh capacity implementation authorization/admission required")
        packet, decision = original(runtime, ctx, before, entrypoints)
        if runtime.repo.resolve() != runtime.repo or subprocess.check_output(
                ["git", "diff", "--cached", "--name-only"], cwd=runtime.repo, text=True).strip():
            raise ValueError("canonical repo without unrelated staged source required")
        files = {**self.files, **{name: token for component in before["components"].values()
            for name, token in component["sources"].items()}}
        if any(files[name] != token for name, token in self.files.items()):
            raise ValueError("inherited/parent source commitments conflict")
        for name, token in files.items():
            identity.path(name)
            if h._binding({"path": str(runtime.repo / name), "sha256": token}) != runtime.repo / name:
                raise ValueError("inherited capacity source drift")
            if hashlib.sha256(subprocess.check_output(["git", "show", "HEAD:" + name], cwd=runtime.repo)).hexdigest() != token:
                raise ValueError("inherited capacity source not checkpointed")
        digest = t.c._digest(decision)
        role_id = f"capacity-author-r{ctx['round_index']:04d}-{digest[:12]}"
        directory = runtime.root / role_id
        if directory.exists():
            raise FileExistsError("capacity author already exists; preserve without automatic retry")
        namespace = "research/market_rsi/research_capacities/" + runtime.fixed_grant["batch_id"] + "/"
        if any(not path.startswith(namespace) for path in decision["capacity"]["write_paths"]):
            raise ValueError("capacity writes outside versioned batch namespace")
        schema = response_schema(decision, runtime.repo)
        axis = {"researcher": "R", "harness": "H"}[decision["action"]]
        body = {"schema": "price_capacity_implementation_input_v1", "original_controller_decision": decision,
            "parent_identity": before, "parent_entrypoints": entrypoints,
            "parent_source": {name: h._binding({"path": str(runtime.repo / name), "sha256": token}).read_text()
                for name, token in before["components"][axis]["sources"].items()},
            "context": {key: packet[key] for key in ("feedback", "memory", "history")},
            "instructions": "Implement the exact original capacity proposal, no substituted science. Return source strings only. Pure apply(context) sees supplied JSON aggregates/history, returns JSON research advice or tool results; never changes evaluation, authority, data or budget. Choose two fresh sibling .py paths from write_paths, one module and one test. Preserve parent sources. Combined source/test<=12KiB. Test imports that exact module's apply, defines test_capacity(), synthetic cases only, main guard invokes test_capacity(). No file/network/process/model/fit/dynamic calls. Pure math, JSON-container builtins/control-flow and helpers permitted. No import-time behavior. Source/test unexecuted until independent review; benefit is not author self-certification."}
        if len(json.dumps(body, sort_keys=True, allow_nan=False).encode()) > t.input_limit(runtime.fixed_grant, "account_roles"):
            raise ValueError("capacity author input exceeds authorized input byte budget")
        directory.mkdir()
        try:
            w.save(directory / "input.json", body)
            call = self.call
            if call is None:
                from supervisor_harness.price_account_roles import role_call
                call = role_call
            result = call("author", body, schema, root=runtime.root, grant_binding=self.grant,
                role_id=role_id, timeout_seconds=self.timeout)
            value = result["response"]; t.c._validate(value, schema)
            if len((value["capacity_source"] + value["test_source"]).encode()) > 12288:
                raise ValueError("bounded combined capacity source/test required")
            paths = [runtime.repo / value[key] for key in ("source_path", "test_path")]
            if (paths[0] == paths[1] or paths[0].parent != paths[1].parent
                    or any(path.suffix != ".py" or path.resolve() != path or path.exists() for path in paths)
                    or not paths[1].name.startswith("test_") or paths[0].name.startswith("test_")):
                raise ValueError("two fresh canonical sibling capacity/test paths required")
            checks = {"source": guard.validate_source(value["capacity_source"]),
                "test": guard.validate_source(value["test_source"], is_test=True, module_name=paths[0].stem)}
            paths[0].parent.mkdir(parents=True, exist_ok=True)
            for path, key in zip(paths, ("capacity_source", "test_source")):
                with path.open("x", encoding="utf-8") as stream: stream.write(value[key])
            receipt = {"schema": "price_capacity_author_receipt_v1", "original_decision_sha256": digest,
                "original_input": ctx["outputs"]["input"]["input"], "original_review": ctx["outputs"]["input"]["review"],
                "authorization": runtime.authority, "configuration": runtime.configuration,
                "parent_identity": before, "parent_entrypoints": entrypoints, "axis": axis,
                "source": r.pin(paths[0]), "test": r.pin(paths[1]), "checks": checks,
                "role_call": {key: item for key, item in result.items() if key != "response"},
                "implementation_notes": value["implementation_notes"], "generated_tests_executed": False,
                "awaiting_independent_source_review": True, "activation_performed": False}
            w.save(directory / "author-receipt.json", receipt)
            names = [str(path.relative_to(runtime.repo)) for path in paths]
            subprocess.run(["git", "add", "--", *names], cwd=runtime.repo, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "capacity(" + axis + "): " + decision["capacity"]["change_id"], "--", *names],
                cwd=runtime.repo, check=True, capture_output=True)
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=runtime.repo, text=True).strip()
            output = {"kind": "capacity", "author_receipt": r.pin(directory / "author-receipt.json"),
                "source": receipt["source"], "test": receipt["test"], "source_commit": commit,
                "files": {**files, **{name: w.sha(runtime.repo / name) for name in names}}}
            w.save(directory / "implementation.json", output)
            return output
        except BaseException as error:
            w.save(directory / "failure.json", {"stage": "capacity_implementation", "original_decision_sha256": digest,
                "error_type": type(error).__name__, "retry_allowed": False, "performance_evidence": False})
            raise
