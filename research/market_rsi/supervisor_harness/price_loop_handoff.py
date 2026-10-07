"""Compile a reviewed price candidate into existing native handoff artifacts.

Supervisor engineering only: no scientific selection, candidate import, budget
reservation, Controller transport, pool activation or worker execution.
"""
from pathlib import Path

from data_scientist_harness.co_evolution_loop import initialize_micro_evolution, micro_pair_hash
from supervisor_harness import continuous_discovery_batch as b
from supervisor_harness import feedback_loop_runtime as r
from experiments.nfl_ingame_price_change_train_diagnostic import TASK, operation_commitment

t, w = r.t, r.w
MODULE = "experiments.nfl_ingame_price_change_train_diagnostic"
FIELDS = {"native_name", "attempt_id", "candidate_binding", "source_commit", "files",
    "python_binding", "memory_binding", "plan_binding", "ordinary_reference_binding",
    "initial_incumbent", "archived_parents", "identity_configuration", "method_family",
    "max_wall_seconds"}


def _binding(value):
    if type(value) is not dict or set(value) != {"path", "sha256"}:
        raise ValueError("exact file binding required")
    path = Path(value["path"])
    if not path.is_absolute() or path.resolve() != path or w.sha(path) != value["sha256"]:
        raise ValueError("canonical bound file drift")
    return path


def _python_launch(value):
    """Bind binary bytes while preserving a reviewed virtualenv launch path."""
    if type(value) is dict and set(value) == {"path", "sha256"}:
        return str(_binding(value)), value["sha256"]
    if type(value) is not dict or set(value) != {"launch_path", "binary"} or type(value["launch_path"]) is not str:
        raise ValueError("exact virtualenv launch and canonical binary binding required")
    binary = _binding(value["binary"])
    path = Path(value["launch_path"])
    if (not path.is_absolute() or ".." in path.parts or str(path) != value["launch_path"]
            or path.parent.resolve() != path.parent or path.resolve() != binary
            or w.sha(path) != value["binary"]["sha256"]):
        raise ValueError("reviewed virtualenv launch target drift")
    return str(path), value["binary"]["sha256"]


def _native(runtime, name):
    b._identifier(name, "native name")
    path = runtime.root / name
    if runtime.root.resolve() != runtime.root or path.resolve() != path:
        raise ValueError("canonical direct native child required")
    return path


def _prediction_input(runtime, response, input_binding=None):
    """Keep v1 intact; bind typed predictions to the actual saved original."""
    if response.get("schema") != "controller_coevolution_action_v2":
        t.c._validate(response, t.SCHEMA)
        return None
    key = response.get("feedback_sha256")
    if type(key) is not str or t.c._hashes(key) != {key}:
        raise ValueError("exact typed prediction feedback hash required")
    directory = runtime.root / "decisions" / key
    if directory.resolve() != directory:
        raise ValueError("original typed prediction directory drift")
    packet, claim = t._file(directory / "input.json"), t._file(directory / "claim.json")
    t.validate_response(response, packet)
    if response["action"] != "prediction":
        raise ValueError("typed capacity/authority request is not a prediction")
    if (claim.get("authorization") != runtime.authority
            or claim.get("configuration_sha256") != runtime.configuration["sha256"]
            or t.c._read(claim["input_binding"]) != packet
            or input_binding is not None and input_binding != claim["input_binding"]):
        raise ValueError("typed prediction input/authority/configuration drift")
    if runtime.fixed_grant.get("account_roles", {}).get("approved") is True:
        from supervisor_harness import price_account_roles as roles
        if claim.get("controller_transport") != roles.transport_contract():
            raise ValueError("native tools-closed typed prediction original required")
    recovered = t._recover(directory, packet, claim, claim.get("controller_transport"))
    matches = [row for row in t._file(runtime.root / "ledger.json")["controller_decisions"]
        if row.get("status") == "completed" and row.get("decision_sha256") == t.c._digest(response)
        and row.get("input_sha256") == t.c._digest(packet)
        and row.get("completion_sha256") == w.sha(directory / "completion.json")]
    if recovered != response or len(matches) != 1:
        raise ValueError("completed typed prediction original/accounting differs")
    return packet


def _validate(runtime, response, spec):
    if type(spec) is not dict or set(spec) != FIELDS:
        raise ValueError("exact trusted handoff specification required")
    packet = _prediction_input(runtime, response)
    if packet is not None and spec["identity_configuration"] != t.action_context(packet)["identity_configuration"]:
        raise ValueError("typed prediction selected pair/context drift")
    choice = response["candidate"]
    if choice["action"] != "propose_candidate":
        raise ValueError("closed authority request is not executable")
    if not runtime.admit({"stage": "execute"}):
        raise RuntimeError("global admission closed")
    ledger = t._file(runtime.root / "ledger.json")
    matches = [d for d in ledger["controller_decisions"]
        if d.get("status") == "completed" and d.get("decision_sha256") == t.c._digest(response)]
    if len(matches) != 1 or any(a["attempt_id"] == spec["attempt_id"] for a in ledger["attempts"]):
        raise ValueError("completed original required; attempt cannot be reused")
    b._identifier(spec["attempt_id"], "attempt ID")
    b._identifier(choice["candidate_id"], "candidate ID")
    b._identifier(choice["question_id"], "question ID")
    b._identifier(spec["method_family"], "method family")
    native = _native(runtime, spec["native_name"])
    incumbent = b._initial_incumbent(spec["initial_incumbent"])
    if type(spec["archived_parents"]) is not list:
        raise ValueError("trusted archived parents required")
    archived = [b._archived_parent(p) for p in spec["archived_parents"]]
    if any(p["research_credit"] != 2 for p in archived):
        raise ValueError("v3 handoff cannot refresh credit-1 followup consumption")
    for field in ("candidate_sha256", "archive_manifest_sha256", "question_digest_sha256"):
        if len({p[field] for p in archived}) != len(archived):
            raise ValueError("duplicate archived parent")
    for fields in (("problem_id", "evidence_bundle_sha256"), ("source_batch_id", "source_attempt_id")):
        if len({tuple(p[k] for k in fields) for p in archived}) != len(archived):
            raise ValueError("duplicate archived evidence or source attempt")
    if (choice["comparison_incumbent_sha256"] != incumbent["candidate_sha256"]
            or incumbent["candidate_sha256"] in {p["candidate_sha256"] for p in archived}
            or choice["actual_parent_sha256"] not in
                {incumbent["candidate_sha256"], *(p["candidate_sha256"] for p in archived)}):
        raise ValueError("actual parent eligibility or comparison incumbent drift")
    for role in ("candidate_binding", "memory_binding", "plan_binding", "ordinary_reference_binding"):
        _binding(spec[role])
    python, python_sha = _python_launch(spec["python_binding"])
    plan = t.c._read(spec["plan_binding"])
    reference = t.c._read(spec["ordinary_reference_binding"])
    if (plan.get("task_id") != TASK or plan.get("horizon_choice", {}).get("seconds") != 300
            or reference.get("task_id") != TASK or reference.get("complete") is not True
            or type(reference.get("model_fits")) is not int or reference["model_fits"] != 4):
        raise ValueError("frozen price plan or ordinary reference drift")
    identity = initialize_micro_evolution(spec["identity_configuration"])
    fixed = identity["fixed_context"]
    if any(fixed[key] != value for key, value in {
            "authority_sha256": runtime.authority["sha256"],
            "resource_policy_sha256": runtime.configuration["sha256"],
            "evaluation_sha256": spec["plan_binding"]["sha256"]}.items()):
        raise ValueError("fixed identity authority/resource/evaluation drift")
    core = {"schema": "market_trade_price_operation_v1", "task_id": TASK,
        "attempt_id": spec["attempt_id"], "candidate_id": choice["candidate_id"],
        "mode": "candidate", "source_commit": spec["source_commit"],
        "plan": spec["plan_binding"], "deadline_utc": runtime.fixed_grant["deadline_utc"],
        "candidate": spec["candidate_binding"], "ordinary_reference": spec["ordinary_reference_binding"]}
    request = {"attempt_id": spec["attempt_id"], "candidate_id": choice["candidate_id"],
        "module": MODULE, "source_commit": spec["source_commit"], "files": spec["files"],
        "python": python, "python_sha256": python_sha,
        "memory": spec["memory_binding"]["path"], "memory_sha256": spec["memory_binding"]["sha256"],
        "runtime_pair_sha256": micro_pair_hash(identity), "spec_sha256": operation_commitment(core),
        "max_fits": 4, "max_wall_seconds": spec["max_wall_seconds"]}
    if (type(spec["max_wall_seconds"]) is not int or not 1 <= spec["max_wall_seconds"]
            <= min(900, runtime.fixed_grant["limits"]["per_attempt_seconds"])):
        raise ValueError("exact granted per-attempt duration exceeded")
    w.validate(request, runtime.repo)
    candidate = Path(spec["candidate_binding"]["path"])
    relative = str(candidate.relative_to(runtime.repo))
    if spec["files"].get(relative) != spec["candidate_binding"]["sha256"]:
        raise ValueError("candidate missing from source commitment")
    selection = {"attempt_id": spec["attempt_id"], "candidate_id": choice["candidate_id"],
        "controller_decision_sha256": t.c._digest(response),
        "research_parent_sha256": choice["actual_parent_sha256"], "allocation": "exploration",
        "method_family": spec["method_family"], "hypothesis_digest_sha256": t.c._digest(choice["hypothesis"]),
        "question_id": choice["question_id"], "question_digest_sha256": t.c._digest({
            "task_id": TASK, "question_id": choice["question_id"], "hypothesis": choice["hypothesis"]}),
        "predeclared_rule_sha256": spec["plan_binding"]["sha256"], "resource_hint": {
            "resource_class": "small_experiment", "max_attempts": 1, "max_time_seconds": spec["max_wall_seconds"],
            "max_bytes": 0, "max_cost_usd": 0, "authority_granted": False}}
    if selection["question_digest_sha256"] in {p["question_digest_sha256"] for p in archived}:
        raise ValueError("archived question already consumed")
    return native, core, request, selection


def prepare(runtime, response, specification):
    """Validate first, then preserve one fresh unactivated native handoff."""
    native, core, request, selection = _validate(runtime, response, specification)
    if native.exists():
        raise FileExistsError("native preparation already exists; inspect without retry")
    batch = b.ContinuousDiscoveryBatch(native)
    state = batch.initialize(batch_id=runtime.fixed_grant["batch_id"],
        start_utc=runtime.fixed_grant["start_utc"], deadline_utc=runtime.fixed_grant["deadline_utc"],
        max_attempts=1, initial_incumbent=specification["initial_incumbent"],
        active_pool_capacity=2, initial_archived_parents=specification["archived_parents"],
        scheduling_policy="final-singleton-v1")
    state = batch.record_micro_evolution("initialize", specification["identity_configuration"],
        expected_state_sha256=state["state_sha256"])
    objects = {"request": ("ready_request.json", request), "selection": ("selection.json", selection),
        "operation_core": ("operation_core.json", core), "specification": ("specification.json", specification),
        "response": ("original_response.json", response)}
    prepared = {"schema": "price_native_handoff_prepared_v1", "native_name": specification["native_name"],
        "authorization": runtime.authority, "configuration": runtime.configuration,
        "state_sha256": state["state_sha256"]}
    for key, (name, value) in objects.items():
        w.save(native / name, value); prepared[key] = r.pin(native / name)
    w.save(native / "prepared.json", prepared)
    return prepared


def finalize(runtime, prepared, review_binding):
    """Finalize exact independent review without selecting or launching a pool."""
    native = _native(runtime, prepared["native_name"])
    if (t._file(native / "prepared.json") != prepared or prepared["authorization"] != runtime.authority
            or prepared["configuration"] != runtime.configuration):
        raise ValueError("prepared manifest or authority drift")
    for key, name in {"request": "ready_request.json", "selection": "selection.json",
            "operation_core": "operation_core.json", "specification": "specification.json",
            "response": "original_response.json"}.items():
        if prepared[key]["path"] != str(native / name):
            raise ValueError("prepared artifact escaped native root")
        _binding(prepared[key])
    spec, response = t.c._read(prepared["specification"]), t.c._read(prepared["response"])
    _, core, request, selection = _validate(runtime, response, spec)
    if any(t.c._read(prepared[k]) != v for k, v in
            (("request", request), ("selection", selection), ("operation_core", core))):
        raise ValueError("compiled handoff drift")
    state = b.ContinuousDiscoveryBatch(native).snapshot()
    if state["state_sha256"] != prepared["state_sha256"] or state["branches"]:
        raise ValueError("native state changed before finalization")
    _binding(review_binding)
    review = t.c._read(review_binding)
    expected = {"passed": True, "authorization_sha256": runtime.authority["sha256"],
        "request_sha256": prepared["request"]["sha256"], "execution_source_sha256": w.sha(r.__file__),
        "operation_core_sha256": operation_commitment(core)}
    if any(type(review.get(k)) is not type(v) or review.get(k) != v for k, v in expected.items()):
        raise ValueError("exact independent execution/operation review required")
    operation = native / (request["attempt_id"] + ".price_operation.json")
    w.save(operation, {**core, "review": review_binding})
    return {"review": review_binding, "artifacts": [r.pin(operation), prepared["request"], prepared["selection"]]}
