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
        return identity

    def handlers(self):
        def timed(stage, callback):
            def handle(context):
                started = time.monotonic()
                path = self.runtime.root / "price-loop" / f"round-{context['round_index']:04d}-{stage}.timing.json"
                try:
                    output = callback(context)
                except BaseException as error:
                    r.t.c.save(path, {"wall_seconds": time.monotonic() - started,
                        "completed": False, "error_type": type(error).__name__})
                    raise
                r.t.c.save(path, {"wall_seconds": time.monotonic() - started, "completed": True})
                return output
            return handle
        return {stage: timed(stage, callback) for stage, callback in super().handlers().items()}


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
        if packet["bindings"]["feedback"]["sha256"] not in {e["sha256"] for e in response["candidate"]["evidence_used"]}:
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
    if (type(config) is not dict or set(config) != FIELDS
            or config["schema"] != "price_discovery_launch_v1"
            or type(config["max_rounds"]) is not int or config["max_rounds"] != 2
            or type(config["source_files"]) is not dict or not config["source_files"]
            or set(config["service_sources"]) != {"author", "reviewer", "roles", "entry"}):
        raise ValueError("exact two-round real launch configuration required")
    repo, root = Path(config["repo"]), Path(config["root"])
    if (not repo.is_absolute() or repo.resolve() != repo or not root.is_absolute()
            or root.resolve() != root or root.parent != r.t.ROOT.parent):
        raise ValueError("existing canonical repository/permanent artifact root required")
    modules = {"author": __import__(CandidateAuthor.__module__, fromlist=["x"]),
               "reviewer": __import__(IndependentPriceReviewer.__module__, fromlist=["x"]),
               "roles": roles}
    for name, binding in config["service_sources"].items():
        path = s.h._binding(binding)
        actual = Path(__file__ if name == "entry" else modules[name].__file__).resolve()
        if path != actual:
            raise ValueError("real service module differs from pinned source")
    runtime = PricePilotRuntime(root, repo, config["authorization"], config["configuration"])
    account = roles.AccountRoles(root, config["role_authorization"])
    author = CandidateAuthor(runtime, config["source_files"], config["role_authorization"])
    reviewer = IndependentPriceReviewer(runtime, account.call,
        role_grant_binding=config["role_authorization"])
    service = LivePriceServices(runtime, config["base_spec"], author=author.author,
        reviewer=reviewer.review, callback_sources={key: config["service_sources"][key]
                                                    for key in ("author", "reviewer")})
    return config, service, account


def preflight(batch_configuration, initial_feedback):
    from supervisor_harness import price_account_roles as roles
    config, service, account = build(batch_configuration)
    seed = r.t.c._read(initial_feedback)
    staged = r.t.c.subprocess.check_output(["git", "diff", "--cached", "--name-only"],
        cwd=service.runtime.repo, text=True, timeout=10)
    if staged.strip():
        raise ValueError("preexisting staged files before account call; preserve and resolve separately")
    before = r.w.sha(service.runtime.root / "ledger.json")
    context = {"round_index": 1, "seed": seed, "previous_result": seed,
               "previous_feedback_sha256": r.t.c._digest(seed), "outputs": {}}
    packet = service.prepare_packet(context)
    prompt_bytes = len(roles._prompt(packet, controller=True).encode("utf-8"))
    if prompt_bytes > roles.MAX_BYTES:
        raise ValueError("full Controller prompt exceeds32KiB before account preflight")
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
    for relative, digest in config["source_files"].items():
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
            "python_launch": launch, "input_bytes": prompt_bytes,
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
            "claim": "Historical Train autonomous predictor iteration only; not R/H evolution or profit"}


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
