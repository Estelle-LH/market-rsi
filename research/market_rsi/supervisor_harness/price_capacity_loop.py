"""Research-side capacity hooks in the existing seven-stage price loop.

This adapter owns no new budget or scientific choices. Supervisor integration,
not autonomous evolution; model authorship/effect require a real granted batch.
"""
from copy import deepcopy
import fcntl
from pathlib import Path

from supervisor_harness import price_capacity_trial as trial
from supervisor_harness import price_capacity_replay as replay
from supervisor_harness import continuous_discovery_batch as native

t, r, w = trial.t, trial.r, trial.w


class PriceCapacityLoop:
    def __init__(self, service, configuration, author, reviewer, *, _test_adapter=None):
        self.service, self.runtime, self.author, self.reviewer = service, service.runtime, author, reviewer
        self.binding, self.config = configuration, t.c._read(configuration)
        value = self.config
        if (set(value) != {"schema", "baseline", "entrypoints", "replay_cases", "hook_seconds"}
                or value["schema"] != "price_capacity_loop_configuration_v1"
                or set(value["replay_cases"]) != trial.CASES
                or any(type(case) is not dict for case in value["replay_cases"].values())
                or type(value["hook_seconds"]) is not int or not 0 < value["hook_seconds"] <= 30
                or self.runtime.fixed_grant.get("account_roles", {}).get("capacity_changes_approved") is not True):
            raise ValueError("explicit reviewed research-capacity configuration and grant required")
        baseline = trial.cs.identity.validate(value["baseline"])
        config = service.base["identity_configuration"]
        if (config["pair"] != trial.cs.activation.pair(baseline)
                or config["fixed_context"]["model_sha256"] != baseline["M"]
                or baseline["runtime"]["python"]["sha256"] != service.base["python_binding"].get(
                    "sha256", service.base["python_binding"].get("binary", {}).get("sha256"))):
            raise ValueError("capacity baseline/model/runtime differs from frozen entry")
        # Existing native micro journal is a version-selection record only;
        # global ledger.json remains the sole operation/fit quota authority.
        if _test_adapter is None:
            batch = native.ContinuousDiscoveryBatch(self.runtime.root / "price-capacity-native")
            if not batch.snapshot_path.exists():
                grant = self.runtime.fixed_grant
                batch.initialize(batch_id=grant["batch_id"], start_utc=grant["start_utc"], deadline_utc=grant["deadline_utc"],
                    max_attempts=grant["limits"]["candidate_attempts"], active_pool_capacity=2, learning_checkpoint_version=1,
                    initial_incumbent={"candidate_id": "capacity-fixed-predictor-anchor", "candidate_sha256": baseline["C"],
                        "scorecard_sha256": t.c._digest(baseline), "review_sha256": "0" * 64})
                batch.record_micro_evolution("initialize", config, expected_state_sha256=batch.snapshot()["state_sha256"])
            self.adapter = trial.cs.activation.CapacityActivation(batch, source_root=self.runtime.repo,
                registry_root=self.runtime.root / "price-capacity-versions", baseline=baseline, entrypoints=value["entrypoints"])
        else:
            self.adapter = _test_adapter  # Tests only; official build never supplies it.
        self.validate()

    def validate(self):
        if t.c._read(self.binding) != self.config: raise ValueError("capacity configuration drift")
        state = self.adapter.batch.snapshot()
        if state["micro_evolution"]["fixed_context"] != self.service.base["identity_configuration"]["fixed_context"]:
            raise ValueError("capacity fixed identities differ from official entry")
        selected = self.adapter._selected(state)
        for axis, name in selected["entrypoints"].items():
            trial.cs.guard.validate_source((self.runtime.repo / name).read_text())
        return selected

    def packet(self, ctx, packet, *, invoke=False):
        selected = self.validate(); manifest = selected["manifest"]
        config = deepcopy(self.service.base["identity_configuration"])
        config["pair"] = trial.cs.activation.pair(manifest)
        source = {**packet["source_context"], "capacity_identity": manifest,
            "capacity_entrypoints": selected["entrypoints"], "capacity_replay_cases": self.config["replay_cases"],
            "controller_action_context": {"schema": "price_controller_action_context_v1",
                "identity_configuration": config, "available_actions": ["prediction", "researcher", "harness"]}}
        packet.update(schema="controller_price_feedback_input_v2", action_context=source["controller_action_context"])
        packet["overhead"].update(configured_research_pair=config["pair"], capacity_hooks_resolved=False)
        if invoke:
            context = {key: packet[key] for key in ("feedback", "memory", "history", "pool")}
            directory = self.runtime.root / f"capacity-hooks-r{ctx['round_index']:04d}"
            directory.mkdir()
            outputs = {}
            for axis, name in selected["entrypoints"].items():
                seconds = min(self.config["hook_seconds"], (t.c._time(self.runtime.fixed_grant["selection_cutoff_utc"])
                    - t.datetime.now(t.timezone.utc)).total_seconds())
                outputs[axis] = replay.invoke({"path": str(self.runtime.repo / name),
                    "sha256": manifest["components"][axis]["sources"][name]}, manifest["runtime"]["python"], context,
                    directory / axis, seconds=seconds, rss_bytes=self.runtime.fixed_grant["limits"]["sampled_rss_bytes"])
                if not outputs[axis]["succeeded"]: raise RuntimeError("selected capacity hook failed; preserve without retry")
            if self.validate() != selected: raise ValueError("selected capacity changed during hook invocation")
            source["capacity_hook_outputs"] = {"selected_pair": config["pair"], "input_sha256": t.c._digest(context),
                "actual_invocations": outputs, "use": "Research advice/tool output only; cannot edit pool, data, scorer or authority"}
            packet["bindings"]["source_context"] = self.service._save(ctx, "hook-source-context", source)
            packet["provided_source_sha256"].append(packet["bindings"]["source_context"]["sha256"])
            packet["overhead"]["capacity_hooks_resolved"] = True
        packet["source_context"] = source
        if len((t.c.json.dumps(packet, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()) > t.input_limit(self.runtime.fixed_grant):
            raise ValueError("effective typed input exceeds original authorized bytes")
        return packet

    def identity(self):
        return {"configuration": self.binding, "source_dependencies": [r.pin(path) for path in
            (__file__, trial.__file__, replay.__file__, trial.cs.__file__, trial.cs.guard.__file__,
             trial.cs.activation.__file__, trial.cs.identity.__file__)]}

    def implement(self, ctx):
        selected = self.validate()
        return self.author.author(ctx, selected["manifest"], selected["entrypoints"])

    def source_review(self, ctx):
        material = ctx["outputs"]["implement"]
        binding = self.reviewer.review("source", material)
        return trial.prepare(self.runtime, material, binding, self.reviewer, self.adapter)

    def execute(self, ctx):
        prepared = ctx["outputs"]["source_review"]
        request = t.c._read(prepared["request"]); decision = request["decision"]
        attempt = "capacity-" + t.c._digest(decision)[:20]
        with (self.runtime.root / ".pilot.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if not self.runtime.admit({**ctx, "stage": "execute"}): raise RuntimeError("capacity execution admission closed")
            ledger = t._file(self.runtime.root / "ledger.json")
            if (any(row["attempt_id"] == attempt for row in ledger["attempts"])
                    or not any(row.get("decision_sha256") == t.c._digest(decision) and row["status"] == "completed"
                        for row in ledger["controller_decisions"])):
                raise ValueError("capacity attempt already consumed or original missing")
            row = {"attempt_id": attempt, "candidate_id": decision["capacity"]["change_id"], "kind": "capacity",
                "fits_reserved": 0, "actual_fits": 0, "valid_fits_completed": 0, "status": "reserved", "no_retry": True,
                "controller_decision_sha256": t.c._digest(decision), "request": prepared["request"],
                "source_commit": request["implementation"]["source_commit"], "source_review_sha256": request["source_review"]["sha256"]}
            ledger["attempts"].append(row); t._ledger(self.runtime.root / "ledger.json", ledger)
            try:
                result = trial.execute(self.runtime, prepared, self.adapter)
                evidence = t.c._read(result["measurement"])
                measurements = [t.c._read(value["receipt"]) for value in evidence["outputs"].values()]
                peaks = [value["sampled_peak_rss_bytes"] for value in measurements if value["sampled_peak_rss_bytes"] is not None]
                row.update(status=result["execution_outcome"], measurement=result["measurement"],
                    worker_wall_seconds=evidence["wall_seconds"], sampled_peak_rss_kib=max(peaks) / 1024 if peaks else None)
                return result
            except BaseException as error:
                # No refund/retry: an incomplete durable operation needs inspection.
                row.update(status="uncertain", error_type=type(error).__name__)
                raise
            finally:
                row["accounted_at_utc"] = t.datetime.now(t.timezone.utc).isoformat()
                if len(ledger["attempts"]) >= self.runtime.fixed_grant["limits"]["candidate_attempts"]:
                    ledger["status"] = "closed_at_attempt_cap"
                t._ledger(self.runtime.root / "ledger.json", ledger)

    def result_review(self, ctx):
        material = ctx["outputs"]["execute"]
        return {"kind": "capacity_result", "material": material, "review": self.reviewer.review("result", material)}

    def reconcile(self, ctx):
        result = ctx["outputs"]["result_review"]; material = result["material"]
        request, review = t.c._read(material["request"]), t.c._read(result["review"])
        if (review.get("authorization_sha256") != self.runtime.authority["sha256"]
                or review.get("request") != material["request"] or review.get("measurement") != material["measurement"]):
            raise ValueError("independent capacity result binding drift")
        previous = ctx["previous_result"]; data = {key: t.c._read(value) for key, value in previous.items()}
        attempt_id = "capacity-" + t.c._digest(request["decision"])[:20]
        with (self.runtime.root / ".pilot.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if not self.runtime.admit({"stage": "reconcile"}): raise RuntimeError("capacity finishing admission closed")
            ledger = t._file(self.runtime.root / "ledger.json")
            row = next(row for row in ledger["attempts"] if row["attempt_id"] == attempt_id)
            if row["status"] != material["execution_outcome"] or "reconciled_feedback_sha256" in row:
                raise ValueError("capacity accounting drift or already reconciled")
            self.adapter.review(review["capacity_activation_review"], expected_state_sha256=self.adapter.batch.snapshot()["state_sha256"])
            selected = self.validate()
            entry = {"axis": request["decision"]["action"], "change_id": request["decision"]["capacity"]["change_id"],
                "controller_decision_sha256": t.c._digest(request["decision"]), "source_commit": request["implementation"]["source_commit"],
                "before_pair": trial.cs.activation.pair(request["before"]), "selected_pair": trial.cs.activation.pair(selected["manifest"]),
                "capacity_decision": review["capacity_decision"], "finding": review["finding"], "measurement": material["measurement"],
                "review": result["review"], "execution_outcome": material["execution_outcome"], "prediction_decision": "UNCHANGED"}
            feedback = {**data["feedback"], **entry, "decision": "UNCHANGED", "task_id": trial.cs.h.TASK}
            memory = {"previous": previous["memory"], "prior": data["memory"], "verified_capacity_finding": entry}
            history = {"previous": previous["history"], "prior": {k: v for k, v in data["history"].items() if k != "process_feedback"},
                "last_capacity_change": entry}
            history["process_feedback"] = self.service.process_feedback(ctx, row, {"execution_outcome": row["status"],
                "manifest": None, "review": result["review"]})
            source = {**data["source_context"], "previous": previous["source_context"],
                "capacity_identity": selected["manifest"], "capacity_entrypoints": selected["entrypoints"]}
            bundle = {key: self.service._save(ctx, key, value) for key, value in
                (("feedback", feedback), ("memory", memory), ("history", history), ("pool", data["pool"]), ("source_context", source))}
            row.update(reconciled_feedback_sha256=bundle["feedback"]["sha256"], result_review_sha256=result["review"]["sha256"])
            t._ledger(self.runtime.root / "ledger.json", ledger)
            return bundle
