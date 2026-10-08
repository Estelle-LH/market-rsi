"""Thin measured before/after adapter around existing micro activation/review."""
from pathlib import Path
import time

from supervisor_harness import price_capacity_services as cs
from supervisor_harness import price_capacity_replay as replay

t, r, w = cs.t, cs.r, cs.w
CASES = {"success", "failure", "restart", "historical_replay"}


def probe_schema(effect):
    path = {"type": "array", "items": t.c.TEXT, "minItems": 1, "maxItems": 16}
    return t.c._object({"metric_name": {"type": "string", "const": "exact_evidence_match_fraction"},
        "expected_effect": {"type": "string", "const": effect},
        "cases": t.c._object({name: t.c._object({"context_path": path,
            "before_output_path": path, "after_output_path": path}) for name in sorted(CASES)})})


def lookup(value, path):
    for key in path:
        if type(value) is list and key.isdecimal(): value = value[int(key)]
        elif type(value) is dict: value = value[key]
        else: raise ValueError("probe path does not resolve")
    return value


def validate_probe(probe, effect, cases):
    # Only evidence-correctness proposals opt into this narrow metric. Other
    # named effects retain actual matched replay + independent effect review.
    if probe is None: return None
    t.c._validate(probe, probe_schema(effect))
    if type(cases) is not dict or set(cases) != CASES:
        raise ValueError("probe requires four original supplied cases")
    for name, paths in probe['cases'].items():
        if paths['context_path'][0] in {'replay_case', 'interpretation'}:
            raise ValueError("scenario labels are not factual benefit evidence")
        try: lookup(cases[name], paths['context_path'])
        except (KeyError, IndexError, ValueError) as error:
            raise ValueError("frozen benefit truth path does not resolve: " + name) from error
    return probe


def measure_probe(probe, cases, outputs):
    if probe is None:
        return {'status': 'independent_named_effect_review_only', 'metric_name': None, 'probe_sha256': None,
            'claim_boundary': 'No built-in deterministic probe for this named effect. Actual matched outputs require independent benefit review; no evidence-accuracy gain is claimed.'}
    rows = {}
    for name, paths in sorted(probe['cases'].items()):
        expected = lookup(cases[name], paths['context_path'])
        row = {'expected_sha256': t.c._digest(expected), 'direct_lookup_reference_correct': True}
        for phase in ('before', 'after'):
            actual = outputs.get(name + '-' + phase)
            try:
                value = lookup(actual['output'], paths[phase + '_output_path']) if actual and actual['succeeded'] else None
                correct = bool(actual and actual['succeeded'] and t.c._digest(value) == row['expected_sha256'])
            except (KeyError, IndexError, ValueError): correct = False
            row[phase + '_correct'] = correct
        rows[name] = row
    before = sum(row['before_correct'] for row in rows.values()) / len(rows)
    after = sum(row['after_correct'] for row in rows.values()) / len(rows)
    return {'status': 'measured_paired_evidence_return', 'metric_name': probe['metric_name'], 'probe_sha256': t.c._digest(probe),
        'cases': rows, 'parent': before, 'candidate': after, 'candidate_minus_parent': after - before,
        'direct_lookup_reference': 1.0, 'candidate_minus_reference': after - 1.0,
        'claim_boundary': 'Supplied-case evidence return only. Direct lookup is a competent retrieval ceiling, not a research-process benchmark.'}


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
    reviewed = t.c._read(static_review)
    original_review = t.c._read(reviewed['original_account_call']['response_binding'])
    if 'benefit_probe' not in reviewed or 'benefit_probe' not in original_review:
        raise ValueError("source review must explicitly freeze a benefit probe or null")
    probe = validate_probe(reviewed['benefit_probe'], cap['expected_effect'], cases)
    if original_review['benefit_probe'] != probe:
        raise ValueError("benefit probe differs from original independent source response")
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
        "cases": cases, "benefit_probe": probe,
        "downstream_context": {key: packet[key] for key in ("feedback", "memory", "history", "pool")},
        "before": before, "after": after, "entrypoints": account["entrypoints"],
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
        for phase in ("before", "after"): call("current_input-" + phase, phase, request["downstream_context"])
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
    evidence['benefit_measurement'] = measure_probe(request['benefit_probe'], request['cases'], outputs)
    return {"kind": "capacity_result", "request": prepared["request"],
        "measurement": replay.save(directory / "measurement.json", evidence),
        "execution_outcome": "succeeded" if error is None else "failed"}


def result_material(runtime, material, reviewer):
    if set(material) != {"kind", "request", "measurement", "execution_outcome"}:
        raise ValueError("exact capacity result material required")
    request, evidence = t.c._read(material["request"]), t.c._read(material["measurement"])
    account = source_scope(runtime, request["implementation"], request["source_review"], reviewer)
    author = t.c._read(request["implementation"]["author_receipt"])
    original_packet = t.c._read(author["original_input"])
    original_cases = original_packet["source_context"]["capacity_replay_cases"]
    if (account["before_identity"] != request["before"] or account["after_identity"] != request["after"]
            or account["original_controller_response"] != request["decision"]
            or evidence.get("request") != material["request"] or evidence.get("binding") != request["binding"]
            or request["cases"] != original_cases or evidence.get("cases_sha256") != t.c._digest(original_cases)
            or 'benefit_probe' not in request
            or request.get('benefit_probe') != t.c._read(request['source_review']).get('benefit_probe')
            or request["downstream_context"] != {key: original_packet[key] for key in ("feedback", "memory", "history", "pool")}
            or material["execution_outcome"] != ("succeeded" if evidence["error_type"] is None else "failed")):
        raise ValueError("measured replay/source/original binding drift")
    validate_probe(request['benefit_probe'], request['decision']['capacity']['expected_effect'], original_cases)
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
        context = request["downstream_context"] if case == "current_input" else request["cases"][case]
        if (call_input["context"] != context or receipt["source"] != source
                or receipt["succeeded"] != output["succeeded"] or receipt["process_reaped"] is not True
                or receipt["python"] != request["before"]["runtime"]["python"]
                or call_input["adapter"] != replay.pin(Path(replay.__file__).resolve())
                or call_input["guard"] != replay.pin(Path(cs.guard.__file__).resolve())
                or output["output"] != (t.c._read(receipt["output"]) if receipt["output"] else None)):
            raise ValueError("actual measured child differs from submitted output")
    if all(evidence["checks"].values()):
        required = {name + "-" + phase for name in CASES for phase in ("before", "after")} | {
            "current_input-before", "current_input-after", "cold-restart-before", "cold-restart-after", "rollback-before"}
        outputs = evidence["outputs"]
        if (set(outputs) != required or any(not output["succeeded"] for output in outputs.values())
                or any(outputs["cold-restart-" + phase]["output"] != outputs["restart-" + phase]["output"]
                    for phase in ("before", "after"))
                or outputs["rollback-before"]["output"] != outputs["success-before"]["output"]):
            raise ValueError("claimed compatibility lacks complete actual replay evidence")
    if evidence.get('benefit_measurement') != measure_probe(request['benefit_probe'], original_cases, evidence['outputs']):
        raise ValueError("named benefit measurement differs from actual matched outputs")
    expected = {"authorization_sha256": runtime.authority["sha256"], "request": material["request"],
        "measurement": material["measurement"], "execution_outcome": material["execution_outcome"]}
    return expected, {**account, "measurement": evidence,
        "original_matched_test": request["decision"]["capacity"]["matched_test"],
        "named_expected_effect": request["decision"]["capacity"]["expected_effect"]}, evidence["checks"]
