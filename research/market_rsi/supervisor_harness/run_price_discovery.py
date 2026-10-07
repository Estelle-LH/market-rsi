"""One real price Discovery entry: preflight or two feedback-linked rounds.

Inputs are a source-bound batch configuration and five-role initial feedback.
No mock services, model-selected commands, authority creation or same-ID retries.
"""
import argparse
import fcntl
import json
from pathlib import Path
import time

from supervisor_harness import feedback_loop_runtime as r
from supervisor_harness import price_loop_services as s
from supervisor_harness.price_loop_handoff import initialize_micro_evolution

FIELDS = {"schema", "repo", "root", "authorization", "configuration", "role_authorization",
          "base_spec", "source_files", "service_sources", "max_rounds"}


class LivePriceServices(s.PriceLoopServices):
    def identity(self):
        from supervisor_harness import price_account_roles as roles
        identity = super().identity()
        for value in identity.values():
            value["source_dependencies"] += [r.pin(__file__), r.pin(roles.__file__)]
            if getattr(self, "recovery_binding", None):
                value["completed_prefix_recovery"] = self.recovery_binding
        return identity

    def handlers(self):
        def timed(stage, callback):
            def handle(context):
                started = time.monotonic()
                directory = getattr(self, "recovery_directory", "price-loop-admission-v2" if getattr(self, "recovery_binding", None) else "price-loop")
                path = self.runtime.root / directory / f"round-{context['round_index']:04d}-{stage}.timing.json"
                try:
                    output = callback(context)
                except BaseException as error:
                    r.t.c.save(path, {"wall_seconds": time.monotonic() - started,
                        "completed": False, "error_type": type(error).__name__})
                    raise
                r.t.c.save(path, {"wall_seconds": time.monotonic() - started, "completed": True})
                return output
            return handle
        handlers = super().handlers()
        for stage, output in getattr(self, "completed_prefix", {}).items():
            original = handlers[stage]
            def restored(context, *, output=output, original=original):
                return output if context["round_index"] == 1 else original(context)
            handlers[stage] = restored
        for stage in s.loop.STAGES:
            original = handlers[stage]
            def restored_round(context, *, stage=stage, original=original):
                saved = getattr(self, "restored_stages", {}).get((context["round_index"], stage))
                if saved is None:
                    return original(context)
                if r.t.c._digest(context) != saved["context_sha256"]:
                    raise ValueError("completed restoration context drift")
                return saved["output"]
            handlers[stage] = restored_round
        return {stage: timed(stage, callback) for stage, callback in handlers.items()}

    def run(self, seed, *, max_rounds):
        if getattr(self, "recovery_binding", None):
            if max_rounds != 2 or r.t.c._digest(seed) != self.recovered_seed_sha256:
                raise ValueError("original recovered seed/two-round bound drift")
            def admit(context):
                saved = getattr(self, "restored_stages", {}).get((context["round_index"], context["stage"]))
                if saved is not None:
                    plain = {k: v for k, v in context.items() if k != "stage"}
                    if r.t.c._digest(plain) != saved["context_sha256"]:
                        raise ValueError("completed restoration admission drift")
                    return True  # Only verified completed artifacts; never a new role or fit.
                return self.runtime.admit(context)
            return s.loop.run(self.runtime.root / getattr(self, "recovery_directory", "price-loop-admission-v2"), self.handlers(),
                seed=seed, admit=admit, max_rounds=2, handler_identity=self.identity)
        return super().run(seed, max_rounds=max_rounds)


def completed_prefix(runtime, binding):
    """One certain pre-source admission repair; never reopen the failed loop."""
    from supervisor_harness import price_account_roles as roles
    value = r.t.c._read(binding)
    if (binding["path"] != str(runtime.root / "completed-prefix-recovery.json")
            or set(value) != {"schema", "authorization", "original_manifest", "original_failed_stage",
                              "original_author_recovery", "review"}
            or value["schema"] != "price_certain_completed_prefix_recovery_v1"
            or value["authorization"] != runtime.authority):
        raise ValueError("exact certain-prefix recovery required")
    review = r.t.c._read(value["review"])
    from supervisor_harness import price_candidate_author as author
    if (review.get("passed") is not True or review.get("entry_source_sha256") != r.w.sha(__file__)
            or review.get("author_source_sha256") != r.w.sha(author.__file__)
            or review.get("no_new_model_call") is not True):
        raise ValueError("independent exact recovery source review required")
    old = runtime.root / "price-loop"
    manifest = r.t.c._read(value["original_manifest"])
    if (value["original_manifest"]["path"] != str(old / "manifest.json")
            or s.loop._read_pair(old / "manifest.json") != manifest
            or manifest["max_rounds"] != 2
            or value["original_failed_stage"]["path"] != str(old / "round-0001-implement.failed.json")
            or r.t.c._read(value["original_failed_stage"]).get("retry_allowed") is not False
            or r.t._file(runtime.root / "ledger.json")["attempts"]
                and not (runtime.root / "price-loop-admission-v2/manifest.json").exists()):
        raise ValueError("only pre-source certain failure with zero attempts is recoverable")
    outputs = {}
    previous = manifest["seed"]
    for stage in ("input", "controller"):
        path = old / f"round-0001-{stage}.done.json"
        done = s.loop._read_pair(path)
        claim = r.t._file(old / f"round-0001-{stage}.claim.json")
        context = {"round_index": 1, "seed": previous, "previous_result": previous,
            "previous_feedback_sha256": r.t.c._digest(previous), "outputs": outputs}
        if (done["claim_sha256"] != r.w.sha(old / f"round-0001-{stage}.claim.json")
                or done["output_sha256"] != r.t.c._digest(done["output"])
                or claim != {"round_index": 1, "stage": stage,
                    "context_sha256": r.t.c._digest(context),
                    "manifest_sha256": value["original_manifest"]["sha256"],
                    "previous_feedback_sha256": r.t.c._digest(previous)}):
            raise ValueError("completed original prefix binding drift")
        s.loop._artifacts(done["output"])
        outputs[stage] = done["output"]
    prepared = outputs["input"]
    packet = r.t.c._read(prepared["input"])
    r.t._review(packet, prepared["input"], runtime.authority, prepared["review"], runtime.repo,
        configuration_binding=runtime.configuration, config=runtime.config)
    directory = Path(outputs["controller"]["directory"])
    if directory != runtime.root / "decisions" / packet["bindings"]["feedback"]["sha256"]:
        raise ValueError("original Controller directory drift")
    actual = r.t._recover(directory, packet, r.t._file(directory / "claim.json"), roles.transport_contract())
    if actual != outputs["controller"]["decision"]:
        raise ValueError("completed original Controller response drift")
    ledger = r.t._file(runtime.root / "ledger.json")
    matches = [d for d in ledger["controller_decisions"] if
        d.get("decision_sha256") == r.t.c._digest(actual) and d.get("status") == "completed"]
    if len(matches) != 1 or matches[0]["input_sha256"] != r.t.c._digest(packet):
        raise ValueError("original completed Controller accounting drift")
    author_recovery = r.t.c._read(value["original_author_recovery"])
    if (author_recovery["original_decision_sha256"] != r.t.c._digest(actual)
            or author_recovery["review"] != value["review"]):
        raise ValueError("original author recovery differs from reviewed Controller")
    ident = "author-r0001-" + r.t.c._digest(actual)[:12]
    if author_recovery["original_author_id"] != ident:
        raise ValueError("original author identity drift")
    directory = runtime.root / "role_calls/author" / ident
    original = roles._recover(directory, r.t._file(directory / "claim.json"),
                              r.t._file(directory / "schema.json"))
    if original["response"]["decision_sha256"] != r.t.c._digest(actual):
        raise ValueError("original author output does not bind original Controller")
    failed = r.t.c._read(value["original_failed_stage"])
    claim_path = old / "round-0001-implement.claim.json"
    if (failed["claim_sha256"] != r.w.sha(claim_path)
            or r.t._file(claim_path)["context_sha256"] != r.t.c._digest({
                "round_index": 1, "seed": previous, "previous_result": previous,
                "previous_feedback_sha256": r.t.c._digest(previous), "outputs": outputs})):
        raise ValueError("original failed admission claim drift")
    return outputs, manifest["seed_sha256"], value["original_author_recovery"]


def completed_round2_prefix(runtime, binding):
    """Restore a certain completed C1/C2 prefix, never retry its failed admission."""
    from supervisor_harness import price_account_roles as roles
    from supervisor_harness import price_candidate_author as author
    value = r.t.c._read(binding)
    if (binding["path"] != str(runtime.root / "completed-round2-prefix-recovery.json")
            or set(value) != {"schema", "authorization", "original_manifest", "original_failed_stage",
                              "original_author_recovery", "previous_recovery", "review"}
            or value["schema"] != "price_certain_completed_round2_prefix_recovery_v1"
            or value["authorization"] != runtime.authority):
        raise ValueError("exact completed round2 recovery required")
    review = r.t.c._read(value["review"])
    if (review.get("passed") is not True or review.get("entry_source_sha256") != r.w.sha(__file__)
            or review.get("author_source_sha256") != r.w.sha(author.__file__)
            or review.get("no_new_model_call") is not True):
        raise ValueError("independent exact round2 recovery source review required")
    old = runtime.root / "price-loop-admission-v2"
    manifest = s.loop._read_pair(old / "manifest.json")
    if (value["original_manifest"] != r.pin(old / "manifest.json") or manifest["max_rounds"] != 2
            or value["original_failed_stage"]["path"] != str(old / "round-0002-implement.failed.json")
            or value["previous_recovery"]["path"] != str(runtime.root / "completed-prefix-recovery.json")):
        raise ValueError("original round2 prefix identity drift")
    r.t.c._read(value["previous_recovery"])
    if any(v.get("completed_prefix_recovery") != value["previous_recovery"] for v in manifest["handler_identity"].values()):
        raise ValueError("round1 recovery history drift")
    ledger = r.t._file(runtime.root / "ledger.json")
    if (len(ledger["controller_decisions"]) != 2 or any(d["status"] != "completed" for d in ledger["controller_decisions"])
            or any(a["status"] in {"reserved", "uncertain"} for a in ledger["attempts"])
            or len(ledger["attempts"]) != 1 and not (runtime.root / "price-loop-admission-v3/manifest.json").exists()):
        raise ValueError("only certain round2 pre-source failure is recoverable")
    restored, previous, seed = {}, manifest["seed"], manifest["seed"]
    for index, stages in ((1, s.loop.STAGES), (2, ("input", "controller"))):
        outputs = {}
        for stage in stages:
            done = s.loop._read_pair(old / f"round-{index:04d}-{stage}.done.json")
            claim_path = old / f"round-{index:04d}-{stage}.claim.json"
            context = {"round_index": index, "seed": seed, "previous_result": previous,
                "previous_feedback_sha256": r.t.c._digest(previous), "outputs": outputs}
            expected = {"round_index": index, "stage": stage, "context_sha256": r.t.c._digest(context),
                "manifest_sha256": value["original_manifest"]["sha256"], "previous_feedback_sha256": r.t.c._digest(previous)}
            if (r.t._file(claim_path) != expected or done["claim_sha256"] != r.w.sha(claim_path)
                    or done["output_sha256"] != r.t.c._digest(done["output"])):
                raise ValueError("original completed round2 prefix binding drift")
            s.loop._artifacts(done["output"])
            restored[index, stage] = {"context_sha256": r.t.c._digest(context), "output": done["output"]}
            outputs[stage] = done["output"]
        prepared = outputs["input"]
        packet = r.t.c._read(prepared["input"])
        r.t._review(packet, prepared["input"], runtime.authority, prepared["review"], runtime.repo,
            configuration_binding=runtime.configuration, config=runtime.config)
        directory = Path(outputs["controller"]["directory"])
        if directory != runtime.root / "decisions" / packet["bindings"]["feedback"]["sha256"]:
            raise ValueError("original Controller path drift")
        decision = r.t._recover(directory, packet, r.t._file(directory / "claim.json"), roles.transport_contract())
        if decision != outputs["controller"]["decision"] or not any(d.get("decision_sha256") == r.t.c._digest(decision) and d.get("input_sha256") == r.t.c._digest(packet) for d in ledger["controller_decisions"]):
            raise ValueError("original Controller completion/accounting drift")
        if index == 1:
            previous = outputs["reconcile"]
            if not any(a.get("reconciled_feedback_sha256") == previous["feedback"]["sha256"] and a.get("status") == "succeeded" for a in ledger["attempts"]):
                raise ValueError("original accepted first-round accounting drift")
    failed = r.t.c._read(value["original_failed_stage"])
    failed_claim = old / "round-0002-implement.claim.json"
    context["outputs"] = outputs
    if (failed.get("retry_allowed") is not False or failed["claim_sha256"] != r.w.sha(failed_claim)
            or r.t._file(failed_claim)["context_sha256"] != r.t.c._digest(context)):
        raise ValueError("original failed round2 admission drift")
    recovered = r.t.c._read(value["original_author_recovery"])
    ident = "author-r0002-" + r.t.c._digest(decision)[:12]
    directory = runtime.root / "role_calls/author" / ident
    original = roles._recover(directory, r.t._file(directory / "claim.json"), r.t._file(directory / "schema.json"))
    if (recovered["original_author_id"] != ident or recovered["original_decision_sha256"] != r.t.c._digest(decision)
            or recovered["review"] != value["review"] or original["response"]["decision_sha256"] != r.t.c._digest(decision)):
        raise ValueError("original round2 author drift")
    return restored, manifest["seed_sha256"], value["original_author_recovery"]


class PricePilotRuntime(r.PilotRuntime):
    """Only the real text-only Controller transport differs from old pilots."""
    def controller(self, context):
        from supervisor_harness import price_account_roles as roles
        prepared = context["outputs"]["input"]
        if prepared["authorization"] != self.authority or prepared["configuration"] != self.configuration:
            raise ValueError("input attempted to change grant")
        account = roles.AccountRoles(self.root, self.authority)
        contract = roles.transport_contract()
        response = r.t.call(self.root, prepared["input"], self.authority, prepared["review"], self.repo,
            configuration_binding=self.configuration, transport=account.controller_transport,
            transport_contract=contract)
        packet = r.t.c._read(prepared["input"])
        selected = response["candidate"] if response["candidate"] is not None else response.get("capacity")
        if selected is None or packet["bindings"]["feedback"]["sha256"] not in {e["sha256"] for e in selected["evidence_used"]}:
            raise ValueError("original Controller did not cite current verified feedback")
        directory = self.root / "decisions" / packet["bindings"]["feedback"]["sha256"]
        return {"decision": response, "directory": str(directory), "artifacts": [r.pin(directory / name) for name in
            ("input.json", "claim.json", "response.json", "completion.json", "ack.json", "native-events.jsonl", "runtime-policy.json")]}


def _bound(path):
    path = Path(path).absolute()
    if path.resolve() != path or path.is_symlink():
        raise ValueError("canonical launch input required")
    return r.pin(path)


def build(batch_configuration):
    """No calls or fits; instantiate the actual production services once."""
    from supervisor_harness import price_account_roles as roles
    from supervisor_harness.price_candidate_author import CandidateAuthor
    from supervisor_harness.price_independent_review import IndependentPriceReviewer
    config = r.t.c._read(batch_configuration)
    capacity = type(config) is dict and config.get("schema") == "price_discovery_launch_v2"
    expected_fields = (FIELDS | {"capacity_configuration"},) if capacity else (FIELDS, FIELDS | {"recovery"})
    expected_services = {"author", "reviewer", "roles", "entry"} | ({"capacity_author", "capacity_loop"} if capacity else set())
    if (type(config) is not dict or set(config) not in expected_fields
            or config["schema"] not in {"price_discovery_launch_v1", "price_discovery_launch_v2"}
            or type(config["max_rounds"]) is not int or config["max_rounds"] != 2
            or type(config["source_files"]) is not dict or not config["source_files"]
            or set(config["service_sources"]) != expected_services):
        raise ValueError("exact two-round real launch configuration required")
    repo, root = Path(config["repo"]), Path(config["root"])
    if (not repo.is_absolute() or repo.resolve() != repo or not root.is_absolute()
            or root.resolve() != root or root.parent != r.t.ROOT.parent):
        raise ValueError("existing canonical repository/permanent artifact root required")
    if config["role_authorization"] != config["authorization"]:
        raise ValueError("all roles must bind the same exact original batch authorization")
    modules = {"author": __import__(CandidateAuthor.__module__, fromlist=["x"]),
               "reviewer": __import__(IndependentPriceReviewer.__module__, fromlist=["x"]),
               "roles": roles}
    if capacity:
        from supervisor_harness import price_capacity_services, price_capacity_loop
        modules.update(capacity_author=price_capacity_services, capacity_loop=price_capacity_loop)
    for name, binding in config["service_sources"].items():
        path = s.h._binding(binding)
        actual = Path(__file__ if name == "entry" else modules[name].__file__).resolve()
        if path != actual:
            raise ValueError("real service module differs from pinned source")
    runtime = PricePilotRuntime(root, repo, config["authorization"], config["configuration"])
    account = roles.AccountRoles(root, config["role_authorization"])
    author_timeout = roles.call_limits(runtime.fixed_grant["account_roles"])["author"]
    round2 = "recovery" in config and r.t.c._read(config["recovery"]).get("schema") == "price_certain_completed_round2_prefix_recovery_v1"
    if round2:
        restored, seed_hash, author_recovery = completed_round2_prefix(runtime, config["recovery"])
        prefix = {}
    else:
        prefix, seed_hash, author_recovery = (completed_prefix(runtime, config["recovery"])
            if "recovery" in config else ({}, None, None))
        restored = {}
    author = CandidateAuthor(runtime, config["source_files"], config["role_authorization"],
        completed_author_recovery=author_recovery, timeout_seconds=author_timeout)
    reviewer = IndependentPriceReviewer(runtime, account.call,
        role_grant_binding=config["role_authorization"])
    service = LivePriceServices(runtime, config["base_spec"], author=author.author,
        reviewer=reviewer.review, callback_sources={key: config["service_sources"][key]
                                                    for key in ("author", "reviewer")})
    if capacity:
        capacity_author = price_capacity_services.CapacityAuthor(runtime, config["source_files"], config["role_authorization"],
            timeout_seconds=author_timeout)
        service.capacity = price_capacity_loop.PriceCapacityLoop(service, config["capacity_configuration"], capacity_author, reviewer)
    service.completed_prefix, service.recovered_seed_sha256 = prefix, seed_hash
    service.restored_stages = restored
    service.recovery_directory = "price-loop-admission-v3" if round2 else "price-loop-admission-v2" if "recovery" in config else "price-loop"
    service.recovery_binding = config.get("recovery")
    return config, service, account


def preflight(batch_configuration, initial_feedback):
    from supervisor_harness import price_account_roles as roles
    config, service, account = build(batch_configuration)
    grant = service.runtime.fixed_grant
    if grant.get("account_roles", {}).get("approved") is True:
        if any(grant["account_roles"]["caps"][role] < config["max_rounds"] for role in roles.ROLES):
            raise ValueError("whole-batch role caps cannot complete the declared rounds before account preflight")
    seed = r.t.c._read(initial_feedback)
    staged = r.t.c.subprocess.check_output(["git", "diff", "--cached", "--name-only"],
        cwd=service.runtime.repo, text=True, timeout=10)
    if staged.strip():
        raise ValueError("preexisting staged files before account call; preserve and resolve separately")
    before = r.w.sha(service.runtime.root / "ledger.json")
    context = {"round_index": 1, "seed": seed, "previous_result": seed,
               "previous_feedback_sha256": r.t.c._digest(seed), "outputs": {}}
    packet = service.prepare_packet(context)
    if getattr(service, "capacity", None):
        scope = r.t.action_context(packet)["identity_configuration"]["allowed_write_paths"]
        namespace = "research/market_rsi/research_capacities/" + grant["batch_id"] + "/"
        if any(not name.startswith(namespace) for names in scope.values() for name in names):
            raise ValueError("capacity writes must use this batch's versioned namespace before account preflight")
    prompt_bytes = len(roles._prompt(packet, controller=True).encode("utf-8"))
    input_limit = r.t.input_limit(service.runtime.fixed_grant)
    if prompt_bytes > input_limit:
        raise ValueError("full Controller prompt exceeds authorized input byte budget before account preflight")
    base = config["base_spec"]
    if type(base) is not dict or set(base) != s.BASE:
        raise ValueError("exact frozen base specification required")
    launch, _ = s.h._python_launch(base["python_binding"])
    identity = initialize_micro_evolution(base["identity_configuration"])
    fixed = identity["fixed_context"]
    for key, digest in {"authority_sha256": service.runtime.authority["sha256"],
                        "resource_policy_sha256": service.runtime.configuration["sha256"],
                        "evaluation_sha256": base["plan_binding"]["sha256"]}.items():
        if fixed[key] != digest:
            raise ValueError("native initialization fixed identity drift")
    plan = r.t.c._read(base["plan_binding"])
    reference = r.t.c._read(base["ordinary_reference_binding"])
    if (plan.get("task_id") != s.h.TASK or plan.get("horizon_choice", {}).get("seconds") != 300
            or reference.get("task_id") != s.h.TASK or reference.get("model_fits") != 4
            or reference.get("complete") is not True):
        raise ValueError("frozen task/reference drift before account call")
    head = r.t.c.subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=service.runtime.repo,
        text=True, timeout=10).strip()
    runner = "research/market_rsi/" + s.h.MODULE.replace(".", "/") + ".py"
    if runner not in config["source_files"]:
        raise ValueError("frozen runner missing before account call")
    frozen = dict(config["source_files"])
    if getattr(service, "capacity", None):
        for component in service.capacity.config["baseline"]["components"].values():
            for name, token in component["sources"].items():
                if name in frozen and frozen[name] != token:
                    raise ValueError("capacity and frozen source commitments conflict before account preflight")
                frozen[name] = token
    for relative, digest in frozen.items():
        path = service.runtime.repo / relative
        if (Path(relative).is_absolute() or ".." in Path(relative).parts
                or path.resolve() != path or r.w.sha(path) != digest):
            raise ValueError("frozen source file drift")
        raw = r.t.c.subprocess.check_output(["git", "show", head + ":" + relative],
                                           cwd=service.runtime.repo, timeout=10)
        if r.t.c.hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("source file is not versioned at actual checkpoint")
    identity_bindings = service.identity()
    if before != r.w.sha(service.runtime.root / "ledger.json"):
        raise ValueError("preflight unexpectedly mutated scientific accounting")
    policy = account.preflight()
    if policy.get("operational_ready") is not True:
        raise ValueError("actual runtime text-only policy not verified before science")
    return {"passed": True, "task": s.h.TASK, "source_commit": head, "runtime_policy": policy,
            "python_launch": launch, "input_bytes": prompt_bytes, "authorized_input_bytes": input_limit,
            "parent_branches": len(packet["pool"]["active_pool"]),
            "handler_identity_sha256": r.t.c._digest(identity_bindings),
            "batch_configuration": batch_configuration, "initial_feedback": initial_feedback,
            "model_calls": 0, "fits": 0, "scientific_reservations": 0}


def run(batch_configuration, initial_feedback, *, preflight_only=False):
    started = time.monotonic()
    receipt = preflight(batch_configuration, initial_feedback)
    if preflight_only:
        return {"status": "PREFLIGHT_ONLY_NOT_REAL_CLOSURE", **receipt}
    config, service, account = build(batch_configuration)
    # These locks are coordination, not additional budget authorities.
    with (service.runtime.root / ".entry.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = service.run(r.t.c._read(initial_feedback), max_rounds=config["max_rounds"])
    return {"preflight": receipt, "loop": result, "wall_seconds": time.monotonic() - started,
            "complete": result.get("status") == "completed" and result.get("completed_rounds") == 2,
            "claim": "Pipeline execution only; prediction and capacity effects require their saved evidence. Not profit or research-process superiority"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-config", required=True)
    parser.add_argument("--initial-feedback", required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    try:
        result = run(_bound(args.batch_config), _bound(args.initial_feedback),
                     preflight_only=args.preflight)
    except Exception as error:
        print(json.dumps({"complete": False, "status": "NOT_COMPLETE", "error": str(error),
                          "retry_allowed": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if args.preflight or result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
