"""Thin measured before/after adapter around existing micro activation/review."""
from pathlib import Path
import time

from supervisor_harness import price_capacity_services as cs
from supervisor_harness import price_capacity_replay as replay

t, r, w = cs.t, cs.r, cs.w
CASES = {"success", "failure", "restart", "historical_replay"}


def source_scope(runtime, implementation, static_review, reviewer):
    expected, account, _ = reviewer._capacity_source(implementation)
    receipt = t.c._read(static_review)
    if (receipt.get("passed") is not True or receipt.get("account_role") != "source_review"
            or any(receipt.get(k) != v for k, v in expected.items())
            or receipt.get("reviewer_source_sha256") != w.sha(Path(reviewer.review.__code__.co_filename))):
        raise ValueError("exact separate capacity source verdict required")
    smoke = t.c._read(receipt["generated_test_receipt"])
    if (smoke.get("exit_code") != 0 or smoke.get("stop_reason") is not None
            or smoke.get("source") != implementation["source"] or smoke.get("test") != implementation["test"]):
        raise ValueError("reviewed generated smoke must bind actual source/test")
    return account


def prepare(runtime, implementation, static_review, reviewer, adapter):
    account = source_scope(runtime, implementation, static_review, reviewer)
    decision = account["original_controller_response"]; cap = decision["capacity"]
    author = t.c._read(implementation["author_receipt"])
    packet = t.c._read(author["original_input"])
    cases = packet["source_context"].get("capacity_replay_cases")
    if (type(cases) is not dict or set(cases) != CASES
            or any(type(case) is not dict for case in cases.values())):
        raise ValueError("four frozen JSON replay contexts required in original input before execution")
    before, after = account["before_identity"], account["after_identity"]
    state = adapter.batch.snapshot()
    if adapter._selected(state)["manifest"] != before:
        raise ValueError("trial parent differs from selected capacity version")
    proposal = {"candidate_id": cap["change_id"], "proposer_id": "controller-" + t.c._digest(decision)[:20],
        "axis": cap["axis"], "component": cap["component"], "behavior_change": cap["expected_effect"],
        "problem_evidence_sha256": t.c._digest(cap["evidence_used"]), "parent_pair_sha256": cap["parent_pair_sha256"],
        "pair": cs.activation.pair(after), "fixed_context": packet["action_context"]["identity_configuration"]["fixed_context"],
        "write_paths": cap["write_paths"], "patch_sha256": cs.activation.patch_digest(before, after)}
    directory = runtime.root / ("capacity-trial-" + t.c._digest(decision)[:20])
    directory.mkdir()  # No implicit continuation/retry of a partially claimed operation.
    adapter.propose(after, proposal, account["entrypoints"], static_review=static_review,
        expected_state_sha256=state["state_sha256"])
    pending = adapter.batch.snapshot()["micro_evolution"]["pending"]
    request = {"implementation": implementation, "source_review": static_review, "decision": decision,
        "cases": cases, "before": before, "after": after, "entrypoints": account["entrypoints"],
        "binding": {"proposal_sha256": pending["record_sha256"], "before_identity_sha256": t.c._digest(before),
            "after_identity_sha256": t.c._digest(after), "tested_pair_sha256": t.c._digest(pending["pair"]),
            "anchor_pair_sha256": t.c._digest(state["micro_evolution"]["anchor_pair"])}}
    return {"kind": "capacity_trial", "request": replay.save(directory / "request.json", request)}


def execute(runtime, prepared, adapter):
    request = t.c._read(prepared["request"]); state = adapter.batch.snapshot()
    pending = state["micro_evolution"]["pending"]; binding = request["binding"]
    if (pending is None or pending["record_sha256"] != binding["proposal_sha256"]
            or cs.activation.pair(request["before"]) != state["micro_evolution"]["active_pair"]
            or adapter._version(pending["pair"])["manifest"] != request["after"]):
        raise ValueError("pending/source/parent pair drift before matched replay")
    directory = Path(prepared["request"]["path"]).parent
    replay.save(directory / "execution-claim.json", {"request": prepared["request"], "retry_allowed": False})
    cap = request["decision"]["capacity"]; axis = {"researcher": "R", "harness": "H"}[cap["axis"]]
    before_entries = adapter._selected(state)["entrypoints"]
    sources = {"before": {"path": str(runtime.repo / before_entries[axis]),
                    "sha256": request["before"]["components"][axis]["sources"][before_entries[axis]]},
               "after": request["implementation"]["source"]}
    started = time.monotonic()
    seconds = min(cap["resources"]["seconds"],
        (t.c._time(runtime.fixed_grant["deadline_utc"]) - t.datetime.now(t.timezone.utc)).total_seconds())
    outputs = {}
    def call(name, phase, context):
        remaining = seconds - (time.monotonic() - started)
        if remaining <= 0: raise TimeoutError("original total capacity replay budget exhausted")
        value = replay.invoke(sources[phase], request["before"]["runtime"]["python"], context,
            directory / name, seconds=min(30, remaining), rss_bytes=cap["resources"]["rss_bytes"])
        outputs[name] = value
        if not value["succeeded"]: raise RuntimeError("bounded capacity call failed; not scientific refutation")
        return value["output"]
    checks = {name: False for name in cs.activation.micro.MICRO_CHECKS}
    error = None
    try:
        for name, context in sorted(request["cases"].items()):
            for phase in ("before", "after"): call(name + "-" + phase, phase, context)
        checks.update(success_replay=True, failure_feedback=True, historical_replay=True)
        checks["restart"] = all(call("cold-restart-" + phase, phase, request["cases"]["restart"])
            == outputs["restart-" + phase]["output"] for phase in ("before", "after"))
        checks["rollback"] = call("rollback-before", "before", request["cases"]["success"]) == outputs["success-before"]["output"]
        # Immutable unchanged-axis sources verify compatibility with the anchor;
        # restart/rollback here are cold function replay, not driver-crash recovery.
        other = "H" if axis == "R" else "R"
        adapter._verify_files(request["before"]); adapter._verify_files(request["after"])
        checks["anchor_compatibility"] = request["before"]["components"][other] == request["after"]["components"][other]
        checks["protected_boundaries"] = cs.identity.change_axis(request["before"], request["after"]) == axis
        checks["bounded_trial"] = all(value["succeeded"] for value in outputs.values())
    except Exception as diagnostic:
        error = type(diagnostic).__name__
    evidence = {"schema": "price_capacity_matched_replay_v1", "binding": binding, "checks": checks,
        "request": prepared["request"], "cases_sha256": t.c._digest(request["cases"]), "outputs": outputs,
        "wall_seconds": time.monotonic() - started, "error_type": error,
        "train_fits": 0, "account_calls": 0, "evidence_level": "L2",
        "limits": cap["resources"], "automatic_retry": False,
        "claim_boundary": "Frozen supplied-context function replay, not generalization, full-driver crash recovery, prediction gain or process superiority"}
    return {"kind": "capacity_result", "request": prepared["request"],
        "measurement": replay.save(directory / "measurement.json", evidence),
        "execution_outcome": "succeeded" if error is None else "failed"}


def result_material(runtime, material, reviewer):
    if set(material) != {"kind", "request", "measurement", "execution_outcome"}:
        raise ValueError("exact capacity result material required")
    request, evidence = t.c._read(material["request"]), t.c._read(material["measurement"])
    account = source_scope(runtime, request["implementation"], request["source_review"], reviewer)
    author = t.c._read(request["implementation"]["author_receipt"])
    original_cases = t.c._read(author["original_input"])["source_context"]["capacity_replay_cases"]
    if (account["before_identity"] != request["before"] or account["after_identity"] != request["after"]
            or account["original_controller_response"] != request["decision"]
            or evidence.get("request") != material["request"] or evidence.get("binding") != request["binding"]
            or request["cases"] != original_cases or evidence.get("cases_sha256") != t.c._digest(original_cases)
            or material["execution_outcome"] != ("succeeded" if evidence["error_type"] is None else "failed")):
        raise ValueError("measured replay/source/original binding drift")
    for name, output in evidence["outputs"].items():
        receipt = t.c._read(output["receipt"])
        call_input = t.c._read(receipt["request"])
        case = name.removeprefix("cold-restart-").removeprefix("rollback-").rsplit("-", 1)[0]
        case = "restart" if name.startswith("cold-restart-") else "success" if name.startswith("rollback-") else case
        phase = name.rsplit("-", 1)[1]
        entries = t.c._read(request["implementation"]["author_receipt"])["parent_entrypoints"]
        source = request["implementation"]["source"] if phase == "after" else {
            "path": str(runtime.repo / entries[{"researcher": "R", "harness": "H"}[request["decision"]["action"]]]),
            "sha256": request["before"]["components"][{"researcher": "R", "harness": "H"}[request["decision"]["action"]]]["sources"][entries[{"researcher": "R", "harness": "H"}[request["decision"]["action"]]]]}
        if (call_input["context"] != request["cases"][case] or receipt["source"] != source
                or receipt["succeeded"] != output["succeeded"] or receipt["process_reaped"] is not True
                or receipt["python"] != request["before"]["runtime"]["python"]
                or call_input["adapter"] != replay.pin(Path(replay.__file__).resolve())
                or call_input["guard"] != replay.pin(Path(cs.guard.__file__).resolve())
                or output["output"] != (t.c._read(receipt["output"]) if receipt["output"] else None)):
            raise ValueError("actual measured child differs from submitted output")
    if all(evidence["checks"].values()):
        required = {name + "-" + phase for name in CASES for phase in ("before", "after")} | {
            "cold-restart-before", "cold-restart-after", "rollback-before"}
        outputs = evidence["outputs"]
        if (set(outputs) != required or any(not output["succeeded"] for output in outputs.values())
                or any(outputs["cold-restart-" + phase]["output"] != outputs["restart-" + phase]["output"]
                    for phase in ("before", "after"))
                or outputs["rollback-before"]["output"] != outputs["success-before"]["output"]):
            raise ValueError("claimed compatibility lacks complete actual replay evidence")
    expected = {"authorization_sha256": runtime.authority["sha256"], "request": material["request"],
        "measurement": material["measurement"], "execution_outcome": material["execution_outcome"]}
    return expected, {**account, "measurement": evidence,
        "original_matched_test": request["decision"]["capacity"]["matched_test"],
        "named_expected_effect": request["decision"]["capacity"]["expected_effect"]}, evidence["checks"]
