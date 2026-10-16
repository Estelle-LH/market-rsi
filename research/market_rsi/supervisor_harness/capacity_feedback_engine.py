"""Task-independent R/H handoffs on the existing once-only seven-stage driver.

Task methods supply public inputs, state, candidate parsing, worker and evaluation.
Services are trusted source-bound implementations, never model-supplied commands.
This offline bridge grants no live authority or arbitrary-code containment.
"""
import inspect
from pathlib import Path

from market_rsi import digest
from supervisor_harness import feedback_linked_loop as driver
from supervisor_harness import research_capacity_activation as activation
from supervisor_harness import research_capacity_identity as identity

ROLES = {"controller", "author", "review", "execute"}
METHODS = ("preflight", "sources", "seed", "role_slot", "load_state", "packet",
           "decision", "candidate", "worker", "execution", "feedback")


def pin(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": driver.c.sha(path)}


def save(path, value):
    driver.c.save(path, value)
    return pin(path)


def read(bound):
    return driver.c._read(bound)


def source_of(call):
    return {"module": pin(inspect.getsourcefile(call)), "function": call.__qualname__}


def run(envelope_binding, capacity, task, *, services, pending_handler=None):
    if (type(services) is not dict or set(services) != ROLES
            or any(not callable(f) for f in services.values())
            or any(not callable(getattr(task, name, None)) for name in METHODS)):
        raise ValueError("Explicit trusted task/services required; no paid fallback")
    if pending_handler is not None and not callable(pending_handler):
        raise ValueError("Explicit trusted pending handler required")
    services = dict(services)
    envelope = read(envelope_binding)
    live_admission = None
    if envelope.get("mode") != "offline_replay":
        live_admission = getattr(task, 'admit_live', None)
        if (envelope.get('mode') != 'real_provider' or not callable(live_admission)
                or live_admission(envelope) is not True):
            raise ValueError("Explicit source-bound live task/runtime admission required")
    task.preflight(envelope)
    root = Path(envelope["root"])
    def selected():
        snap = capacity.batch.snapshot()
        return digest(snap["micro_evolution"]["active_pair"]), capacity._selected(snap)
    def profiles(pair):
        return {axis: capacity.resolve(axis, expected_pair_sha256=pair)["profile"] for axis in ("R", "H")}
    def slot(ctx, name):
        return task.role_slot(envelope, ctx["round_index"], name)
    def original(ctx, name, value):
        if value.get("path") != str(Path(slot(ctx, name)) / "response.json"):
            raise ValueError(name + " original outside declared role slot")
        return read(value)
    pair = digest(activation.pair(capacity.baseline))
    seed = dict(task.seed(envelope), pair_sha256=pair)
    task.load_state(seed["state"])

    def packet(ctx):
        current, _ = selected()
        previous = ctx["previous_result"]
        if previous["pair_sha256"] != current:
            raise ValueError("Selected capacity changed outside previous feedback lineage")
        task.load_state(previous["state"])
        value = task.packet(envelope, ctx, profiles(current), current)
        if (value["parent_pair_sha256"] != current
                or value["feedback_sha256"] != ctx["previous_feedback_sha256"]
                or value["feedback"] != previous["feedback"]):
            raise ValueError("Controller packet did not deliver exact parent feedback")
        bound = save(root / f"packet-{ctx['round_index']:02d}.json", value)
        return {"packet": bound, "parent_state": previous["state"], "artifacts": [bound, previous["state"]]}

    def propose(ctx):
        prompt = read(ctx["outputs"]["input"]["packet"])
        bootstrap = getattr(task,'bootstrap_control',None)
        control = bootstrap(envelope,prompt,ctx['round_index']) if live_admission is not None and callable(bootstrap) else None
        if control is not None:
            checked = identity.sha(control['parent_pair_sha256']) == prompt['parent_pair_sha256']
            if (ctx['round_index'] != 1 or control.get('axis') != 'continue' or control.get('component') != 'none'
                    or not checked or control.get('feedback_sha256') != prompt['feedback_sha256']):
                raise ValueError('Exact unchanged first-round bootstrap control required')
            decision = save(root / f"decision-{ctx['round_index']:02d}.json",control)
            return {'decision':decision,'origin':'HUMAN_DECLARED_BASELINE_NO_MODEL_CALL','artifacts':[decision]}
        bound = services["controller"](prompt, slot(ctx, "controller"))
        chosen = task.decision(original(ctx, "controller", bound), prompt)
        if (chosen["axis"] not in {"R", "H", "continue"}
                or chosen["parent_pair_sha256"] != prompt["parent_pair_sha256"]
                or chosen["feedback_sha256"] != prompt["feedback_sha256"]):
            raise ValueError("Decision differs from delivered parent/feedback")
        decision = save(root / f"decision-{ctx['round_index']:02d}.json", chosen)
        return {"decision": decision, "original": bound, "artifacts": [decision, bound]}

    def implement(ctx):
        chosen = read(ctx["outputs"]["controller"]["decision"])
        if chosen["axis"] == "continue": return {"candidate": None, "artifacts": []}
        before = profiles(chosen["parent_pair_sha256"])[chosen["axis"]]
        bound = services["author"](chosen, before, slot(ctx, "author"))
        candidate = task.candidate(original(ctx, "author", bound), before, chosen)
        child = save(root / f"candidate-{ctx['round_index']:02d}.json", candidate)
        return {"candidate": child, "original": bound, "artifacts": [child, bound]}

    def source_review(ctx):
        chosen = read(ctx["outputs"]["controller"]["decision"])
        before_pair, before_body = selected()
        if before_pair != chosen["parent_pair_sha256"]:
            raise ValueError("Capacity drift before source review")
        if chosen["axis"] == "continue":
            return {"verdict": "continue", "pair_sha256": before_pair, "artifacts": []}
        implementation = ctx["outputs"]["implement"]
        snap = capacity.batch.snapshot()
        authored = original(ctx, "author", implementation["original"])
        before = profiles(before_pair)[chosen["axis"]]
        candidate = read(implementation["candidate"])
        if task.candidate(authored, before, chosen) != candidate:
            raise ValueError("Candidate differs from unchanged Author original")
        descriptor = {"schema": "capacity_review_context_v1", "decision_sha256": digest(chosen),
            "author_original": implementation["original"], "candidate": implementation["candidate"],
            "parent_pair_sha256": before_pair, "parent_identity": before_body["manifest"],
            "parent_entrypoints": before_body["entrypoints"], "state_sha256": snap["state_sha256"],
            "micro_evolution": snap["micro_evolution"]}
        spec = services["review"](driver._copy(chosen), driver._copy(authored),
                                    driver._copy(descriptor), slot(ctx, "review"))
        fields = {"schema", "after", "proposal", "entrypoints", "static_review", "review_receipt", "original", "artifacts"}
        if type(spec) is not dict or set(spec) != fields or spec["schema"] != "capacity_review_spec_v1":
            raise ValueError("Exact data-only source review specification required")
        if (type(spec["artifacts"]) is not list or original(ctx, "review", spec["original"]) !=
                {key: spec[key] for key in fields - {"original", "artifacts"}}):
            raise ValueError("Review specification differs from preserved original")
        # Artifacts include authored literal Python as well as typed JSON.
        # Verify every original byte binding; parse only the typed fields above.
        for bound in spec["artifacts"]: driver.c._read(bound, binary=True)
        if (capacity.batch.snapshot()["state_sha256"] != snap["state_sha256"]
                or read(ctx["outputs"]["controller"]["decision"]) != chosen
                or original(ctx, "author", implementation["original"]) != authored
                or read(implementation["candidate"]) != candidate
                or task.candidate(authored, profiles(before_pair)[chosen["axis"]], chosen) != candidate):
            raise ValueError("State or original handoff drift during source review")
        proposed, proposal, entries = spec["after"], spec["proposal"], spec["entrypoints"]
        if (identity.change_axis(before_body["manifest"], proposed) != chosen["axis"]
                or type(proposal) is not dict
                or proposal.get("axis") != {"R": "researcher", "H": "harness"}[chosen["axis"]]
                or proposal.get("component") != chosen["component"]
                or proposal.get("behavior_change") != chosen["expected_effect"]
                or proposal.get("parent_pair_sha256") != before_pair
                or proposal.get("problem_evidence_sha256") != chosen["feedback_sha256"]):
            raise ValueError("Native proposal differs from this Controller/Author handoff")
        if (type(entries) is not dict or set(entries) != {"R", "H"}
                or proposed["components"][chosen["axis"]]["sources"].get(entries[chosen["axis"]]) != candidate["source_sha256"]):
            raise ValueError("Reviewed source is not the unchanged Author original")
        options = {"static_review": spec["static_review"], "expected_state_sha256": snap["state_sha256"]}
        capacity.preview_proposal(proposed, proposal, entries, **options)
        if spec["review_receipt"] is not None:
            capacity.preview_review(proposed, proposal, entries, receipt=spec["review_receipt"], **options)
        before_history = driver._copy(snap["micro_evolution"]["history"])
        capacity.propose(proposed, proposal, entries, **options)
        artifacts = [spec["original"], *spec["artifacts"]]
        if spec["review_receipt"] is None:
            return {"verdict": "pending", "pair_sha256": before_pair, "artifacts": artifacts}
        capacity.review(spec["review_receipt"], expected_state_sha256=capacity.batch.snapshot()["state_sha256"])
        verdict = {"verdict": read(spec["review_receipt"])["review"]["decision"], "artifacts": artifacts}
        after_pair, after_body = selected()
        axis = identity.change_axis(before_body["manifest"], after_body["manifest"])
        if verdict.get("verdict") not in {"accept", "reject"}:
            raise ValueError("Exact native adoption/rejection required")
        if axis != (chosen["axis"] if verdict["verdict"] == "accept" else "UNCHANGED"):
            raise ValueError("Actual selected change differs from decision/review")
        micro = capacity.batch.snapshot()["micro_evolution"]
        latest = micro["history"][-1] if micro["history"] else None
        if (micro["pending"] is not None or latest is None
                or len(micro["history"]) != len(before_history) + 1 or micro["history"][:-1] != before_history
                or latest["review"]["decision"] != verdict["verdict"]
                or latest["proposal"]["problem_evidence_sha256"] != chosen["feedback_sha256"]
                or latest["proposal"]["parent_pair_sha256"] != before_pair):
            raise ValueError("Native review did not close the exact feedback-bound proposal")
        proposal = latest["proposal"]
        if (proposal["axis"] != {"R": "researcher", "H": "harness"}[chosen["axis"]]
                or proposal["component"] != chosen["component"] or proposal["behavior_change"] != chosen["expected_effect"]):
            raise ValueError("Native proposal differs from this Controller/Author handoff")
        proposed = capacity._version(proposal["pair"])
        candidate = read(implementation["candidate"])
        name = proposed["entrypoints"][chosen["axis"]]
        if proposed["manifest"]["components"][chosen["axis"]]["sources"][name] != candidate["source_sha256"]:
            raise ValueError("Reviewed source is not the unchanged Author original")
        return dict(verdict, pair_sha256=after_pair)

    def execute(ctx):
        current = ctx["outputs"]["source_review"]["pair_sha256"]
        if selected()[0] != current: raise ValueError("Capacity drift before worker")
        parent_state = ctx["outputs"]["input"]["parent_state"]
        effect, review_outcome = None, ctx["outputs"]["source_review"]["verdict"]
        if review_outcome == "pending" and pending_handler is not None:
            prior = capacity.batch.snapshot()
            micro, pending = prior["micro_evolution"], prior["micro_evolution"]["pending"]
            if (pending is None or prior["active_attempt_ids"]
                    or prior["max_attempts"] - len(prior.get("capacity_work", [])) < 3):
                raise ValueError("Pending trial needs three idle prospective work items")
            chosen = read(ctx["outputs"]["controller"]["decision"])
            effect = pending_handler(driver._copy(chosen), driver._copy(parent_state), round_index=ctx["round_index"])
            if (type(effect) is not dict or set(effect) != {"schema", "comparison", "review_receipt", "artifacts"}
                    or effect["schema"] != "earnings_pending_effect_result_v1"
                    or type(effect["artifacts"]) is not list
                    or not Path(effect["review_receipt"]["path"]).is_relative_to(root/"effects")):
                raise ValueError("Exact retained pending effect/review result required")
            driver._artifacts(effect)
            fresh = capacity.batch.snapshot()
            if fresh["micro_evolution"] != micro or fresh["active_attempt_ids"]:
                raise ValueError("Pending handler changed selection/proposal/history or left busy work")
            receipt = read(effect["review_receipt"])
            review_outcome = receipt["review"]["decision"]
            capacity.review(effect["review_receipt"], expected_state_sha256=fresh["state_sha256"])
            updated = capacity.batch.snapshot()["micro_evolution"]
            if (updated["pending"] is not None or len(updated["history"]) != len(micro["history"])+1
                    or updated["history"][:-1] != micro["history"]
                    or updated["history"][-1]["proposal"] != pending
                    or updated["history"][-1]["review"] != receipt["review"]
                    or updated["active_pair"] != (pending["pair"] if review_outcome == "accept" else micro["active_pair"])):
                raise ValueError("Root review did not close this exact pending candidate")
            current = selected()[0]
        work_id = "capacity-" + digest({"episode": envelope_binding, "round": ctx["round_index"]})
        snap = capacity.batch.snapshot()
        capacity.batch.record_capacity_work("claim", work_id=work_id, pair_sha256=current,
            evidence_sha256=digest(ctx["outputs"]), expected_state_sha256=snap["state_sha256"])
        worker = task.worker(envelope, capacity, current, parent_state)
        result = services["execute"](worker, slot(ctx, "execute"))
        out = task.execution(result, worker, slot(ctx, "execute"))
        if out.get("consumed") != {"pair_sha256": current, "state_sha256": parent_state["sha256"]}:
            raise ValueError("Worker did not consume the selected pair and exact preceding state")
        task.load_state(out["state"])
        snap = capacity.batch.snapshot()
        capacity.batch.record_capacity_work("complete", work_id=work_id, pair_sha256=current,
            evidence_sha256=digest(out), expected_state_sha256=snap["state_sha256"])
        if effect is not None:
            out = dict(out, artifacts=[*out["artifacts"], *effect["artifacts"]], effect_review=effect)
        return dict(out, pair_sha256=current, parent_state=parent_state, capacity_review=review_outcome)

    def result_review(ctx):
        out = ctx["outputs"]["execute"]
        feedback = task.feedback(out, envelope)
        return {"feedback": feedback, "state": out["state"], "pair_sha256": out["pair_sha256"],
                "artifacts": out["artifacts"], "claims": {"mode": envelope['mode'], "learning": False,
                "live_RH_authorship": False}}

    def reconcile(ctx):
        out = ctx["outputs"]["result_review"]
        if selected()[0] != out["pair_sha256"]: raise ValueError("Capacity drift before next feedback")
        task.load_state(out["state"])
        return out

    def sources():
        common = {"episode": envelope_binding, "sources": task.sources(), "engine": pin(__file__),
                  "native_dependencies": {name: pin(path) for name, path in {
                      "driver": driver.__file__, "driver_io": driver.c.__file__,
                      "activation": activation.__file__, "identity": identity.__file__,
                      "micro_evolution": activation.micro.__file__,
                      "capacity": inspect.getsourcefile(type(capacity)),
                      "batch": inspect.getsourcefile(type(capacity.batch)),
                      "digest": inspect.getsourcefile(digest)}.items()},
                  "services": {n: source_of(f) for n, f in services.items()},
                  "task": {n: source_of(getattr(task, n)) for n in METHODS},
                  "initial_identity_sha256": digest(capacity.baseline)}
        if pending_handler is not None:
            owner = getattr(pending_handler, "__self__", None)
            common["pending_handler"] = {"callback": source_of(pending_handler),
                "sources": owner.sources() if callable(getattr(owner, "sources", None)) else {}}
        if live_admission is not None:
            common['live_admission'] = source_of(live_admission)
            if callable(getattr(task,'bootstrap_control',None)):
                common['bootstrap_control'] = source_of(task.bootstrap_control)
        return {stage: dict(common, handler=stage) for stage in driver.STAGES}
    def admit(ctx):
        read(envelope_binding)
        task.preflight(envelope)
        return True
    callbacks = dict(zip(driver.STAGES, (packet, propose, implement, source_review, execute, result_review, reconcile)))
    result = driver.run(root / "loop", callbacks, seed=seed, admit=admit,
                        max_rounds=envelope["max_rounds"], handler_identity=sources)
    if result["status"] == "completed" and selected()[0] != result["result"]["pair_sha256"]:
        raise ValueError("Completed replay selection differs from retained outcome")
    return result
