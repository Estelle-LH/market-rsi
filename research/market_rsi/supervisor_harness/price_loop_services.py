"""Concrete price-task handoffs, using the existing once-only loop and ledger.

Author and independent reviewer are trusted, source-pinned services installed
once by Supervisor, not commands from Controller text. This adapter is H repair,
not evidence of live autonomy, researcher improvement or trading profitability.
"""
import csv
import fcntl
import inspect
import json
import math
from pathlib import Path

from experiments import nfl_ingame_price_score as scoring
from supervisor_harness import feedback_linked_loop as loop
from supervisor_harness import price_loop_handoff as h

r, t, w = h.r, h.t, h.w
ROLES = {"feedback", "memory", "history", "pool", "source_context"}
AUTHORED = {"candidate_binding", "source_commit", "files", "method_family"}
RECORD = {"candidate_id", "candidate_sha256", "manifest", "model_column", "review", "native_parent"}
BASE = h.FIELDS - AUTHORED - {"native_name", "attempt_id", "memory_binding", "initial_incumbent", "archived_parents"}
TIMED_STAGES = loop.STAGES[:-1]  # Reconcile timing is not complete while it writes history.


def _timing(binding):
    value = t.c._read(binding)
    if (set(value) != ({"wall_seconds", "completed"} if value.get("completed") is True
                      else {"wall_seconds", "completed", "error_type"})
            or type(value.get("completed")) is not bool
            or type(value.get("wall_seconds")) not in {int, float}
            or not math.isfinite(value["wall_seconds"]) or value["wall_seconds"] < 0
            or (not value["completed"] and (type(value.get("error_type")) is not str
                or not value["error_type"].isidentifier() or len(value["error_type"]) > 128))):
        raise ValueError("bounded factual stage timing required")
    return value


def _process_evidence(value):
    """Recheck immutable measurements; unavailable is never measured zero."""
    if value is None:
        return None
    if (type(value) is not dict or set(value) != {"schema", "round_index", "source_batch_root",
            "stages", "execution", "result_review", "reconcile_timing_included"}
            or value["schema"] != "price_process_feedback_v1"
            or type(value["round_index"]) is not int or value["round_index"] < 1
            or value["reconcile_timing_included"] is not False
            or set(value["stages"]) != set(TIMED_STAGES)):
        raise ValueError("exact prior process feedback required")
    root = Path(value["source_batch_root"])
    if not root.is_absolute() or root.resolve() != root or root.parent != t.ROOT.parent:
        raise ValueError("process evidence must belong to a permanent batch root")
    for stage, observation in value["stages"].items():
        if type(observation) is not dict or set(observation) != {"measurement", "evidence"}:
            raise ValueError("exact stage observation required")
        binding = observation["evidence"]
        if binding is None:
            if observation["measurement"] is not None:
                raise ValueError("measurement without timing evidence")
            continue
        path = Path(binding["path"])
        if (path.parent.parent != root or path.parent.name not in
                {"price-loop", "price-loop-admission-v2", "price-loop-admission-v3"}
                or path.name != f"round-{value['round_index']:04d}-{stage}.timing.json"):
            raise ValueError("stage timing provenance drift")
        h._binding(binding)
        if _timing(binding) != observation["measurement"]:
            raise ValueError("stage timing snapshot drift")
    review = t.c._read(value["result_review"])
    execution = value["execution"]
    if (set(execution) != {"outcome", "fits_reserved", "actual_fits", "valid_fits_completed",
            "worker_wall_seconds", "sampled_peak_rss_kib", "performance_evidence"}
            or review.get("passed") is not True or review.get("execution_outcome") != execution["outcome"]
            or execution["performance_evidence"] != (review.get("manifest") is not None)
            or execution["outcome"] != "succeeded" and execution["performance_evidence"]):
        raise ValueError("process observation must bind independently reviewed execution")
    return value


def _evidence(record):
    if set(record) != RECORD:
        raise ValueError("exact saved candidate evidence required")
    manifest_path = h._binding(record["manifest"])
    h._binding(record["review"])
    manifest, review = t.c._read(record["manifest"]), t.c._read(record["review"])
    if (manifest.get("task_id") != h.TASK or manifest.get("complete") is not True
            or manifest.get("model_fits") != 4 or review.get("passed") is not True):
        raise ValueError("completed independently reviewed price evidence required")
    files = {}
    for name in ("pre_score_lock", "input_receipts", "exclusions", "predictions", "scorecard"):
        path = manifest_path.parent / (name + (".csv" if name == "predictions" else ".json"))
        files[name] = {"path": str(path), "sha256": manifest[name + "_sha256"]}
        h._binding(files[name])
    with Path(files["predictions"]["path"]).open(newline="") as stream:
        values = list(csv.DictReader(stream))
    if not values or len({row["row_id"] for row in values}) != len(values):
        raise ValueError("empty or duplicate saved prediction IDs")
    return manifest, files, {row["row_id"]: row for row in values}


def paired_comparison(candidate, parent, incumbent, ordinary):
    """Re-score identical immutable forecast rows, never change the full denominator.

    The CSV covers forecastable checks only. Recomputed aggregate/pairs use the
    frozen scorer; population coverage stays the original full-population card.
    """
    _, files, current = _evidence(candidate)
    card = t.c._read(files["scorecard"])
    metadata = ("row_id", "game_id", "game_date", "game_week", "fold", "anchor_s", "p_current", "label")
    predictions = {scoring.B0: {key: 0.0 for key in current}}
    for record in (candidate, parent, incumbent, ordinary):
        _, other_files, other = _evidence(record)
        if (other_files["input_receipts"]["sha256"] != files["input_receipts"]["sha256"]
                or set(other) != set(current) or any(
                    any(other[key][field] != row[field] for field in metadata) for key, row in current.items())):
            raise ValueError("paired parent/incumbent row, label, clock or source drift")
        column = record["model_column"]
        values = {key: float(row[column]) for key, row in other.items()}
        if column in predictions and predictions[column] != values:
            raise ValueError("same model column has different forecasts")
        predictions[column] = values
    rows = [{**{key: row[key] for key in metadata}, "forecastable": True,
             "p_current": float(row["p_current"]), "label": float(row["label"]) if row["label"] else None}
            for row in current.values()]
    computed = scoring.score(rows, predictions, draws=2000, seed=314159)
    if any(abs(value - computed["equal_game_mse"][model]) > 1e-12
           for model, value in card["equal_game_mse"].items()):
        raise ValueError("saved score disagrees with frozen independent re-score")
    computed["coverage"] = card["coverage"]
    computed.update(task_id=h.TASK, coverage_origin=files["scorecard"],
        actual_parent_sha256=parent["candidate_sha256"], comparison_incumbent_sha256=incumbent["candidate_sha256"],
        candidate_sha256=candidate["candidate_sha256"],
        decision="KEEP" if computed["equal_game_mse"][incumbent["model_column"]]
            - computed["equal_game_mse"][candidate["model_column"]] > 1e-12 else "REVERT")
    return computed


class PriceLoopServices:
    def __init__(self, runtime, base_spec, *, author, reviewer, callback_sources):
        if (set(base_spec) != BASE or not callable(author) or not callable(reviewer)
                or set(callback_sources) != {"author", "reviewer"}):
            raise ValueError("fixed base specification and source-pinned trusted services required")
        self.runtime, self.base, self.author, self.reviewer = runtime, base_spec, author, reviewer
        self.callbacks = callback_sources
        for role, callback in (("author", author), ("reviewer", reviewer)):
            if h._binding(callback_sources[role]) != Path(inspect.getsourcefile(callback)).resolve():
                raise ValueError("callback source binding does not identify actual trusted service")

    def _save(self, ctx, role, value):
        path = self.runtime.root / f"price-round-{ctx['round_index']:04d}-{role}.json"
        w.save(path, value)
        return r.pin(path)

    def _bundle(self, ctx):
        bundle = ctx["previous_result"]
        if set(bundle) != ROLES:
            raise ValueError("exact five-role price continuation bundle required")
        for binding in bundle.values():
            h._binding(binding)
        return bundle, {key: t.c._read(binding) for key, binding in bundle.items()}

    def prepare_packet(self, ctx):
        """Pure full-path input validation before any account call/reservation."""
        bindings, data = self._bundle(ctx)
        pool = data["pool"]
        records = {item["candidate_sha256"]: item for item in pool["archive"]}
        if len(records) != len(pool["archive"]) or pool["incumbent"]["candidate_sha256"] not in records:
            raise ValueError("unique archive with current incumbent evidence required")
        eligible = [key for key, item in records.items() if key == pool["incumbent"]["candidate_sha256"]
                    or (item["native_parent"] is not None and item["native_parent"]["research_credit"] == 2)]
        active = pool["active_pool"]
        if (not 2 <= len(active) <= 3 or len({p["parent_sha256"] for p in active}) != len(active)
                or any(p["parent_sha256"] not in eligible for p in active)):
            raise ValueError("global active pool must contain 2–3 distinct eligible branches")
        for item in records.values():
            if item["manifest"] is not None:
                _, _, forecasts = _evidence(item)
                if any(item["model_column"] not in row for row in forecasts.values()):
                    raise ValueError("saved parent forecast column missing before original call")
            if item["native_parent"] is not None:
                imported = h.b._archived_parent(item["native_parent"])
                original_review = t.c._read(item["review"])
                if (imported["candidate_id"] != item["candidate_id"]
                        or imported["candidate_sha256"] != item["candidate_sha256"]
                        or imported["archive_manifest_sha256"] != item["manifest"]["sha256"]
                        or imported["independent_review_sha256"] != item["review"]["sha256"]
                        or imported["authority_snapshot_sha256"] != original_review.get("authorization_sha256")
                        or any(imported[k] != original_review.get(k) for k in
                            ("source_batch_id", "source_attempt_id", "question_digest_sha256", "evidence_bundle_sha256",
                             "research_credit", "research_outcome", "route_action"))):
                    raise ValueError("archive eligibility does not bind actual reviewed evidence")
        if any(records[p["parent_sha256"]]["native_parent"] is None for p in active):
            raise ValueError("active branch needs original reviewed continuation provenance before starting")
        ledger = t._file(self.runtime.root / "ledger.json")
        process = _process_evidence(data["history"].get("process_feedback"))
        from supervisor_harness import price_candidate_author as numeric_author
        capability = {"schema": "price_numeric_capability_snapshot_v1",
            "source": r.pin(numeric_author.__file__),
            "imports": {key: sorted(symbols) if symbols is not None else "numeric module"
                        for key, symbols in numeric_author.IMPORTS.items()},
            "numpy_attributes": sorted(numeric_author.NP),
            "limit": "Static admission snapshot, not arbitrary-code containment or extra authority"}
        packet = {"schema": "controller_price_feedback_input_v1", "bindings": bindings,
            **{key: data[key] for key in ("feedback", "memory", "history", "source_context")},
            "pool": {"incumbent": pool["incumbent"], "active_pool": active,
                     "archive": [{k: item[k] for k in ("candidate_id", "candidate_sha256")}
                                 for item in pool["archive"]]},
            "authority": self.runtime.fixed_grant, "provided_parents": eligible,
            "provided_source_sha256": list(dict.fromkeys([*eligible, *(b["sha256"] for b in bindings.values())])),
            "overhead": {"attempts_consumed": len(ledger["attempts"]),
                "fits_reserved": sum(a["fits_reserved"] for a in ledger["attempts"]),
                "original_decisions_consumed": len(ledger["controller_decisions"]),
                "last_process_feedback_sha256": t.c._digest(process) if process is not None else None,
                "process_feedback_location": "history.process_feedback" if process is not None else None,
                "configured_research_pair": self.base["identity_configuration"]["pair"],
                "capacity_hooks_resolved": False,  # F4 must supply actual invocation evidence, not this config.
                "implementation_capabilities": capability}}
        if packet["feedback"]["comparison_incumbent_sha256"] != pool["incumbent"]["candidate_sha256"]:
            raise ValueError("feedback comparison incumbent drift")
        if len((json.dumps(packet, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")) > 32768:
            raise ValueError("compact aggregate input exceeds authorized 32KiB")
        return packet

    def input(self, ctx):
        packet = self.prepare_packet(ctx)
        binding = self._save(ctx, "input", packet)
        review = self.reviewer("input", {"input": binding, "authorization": self.runtime.authority,
            "configuration": self.runtime.configuration})
        t._review(packet, binding, self.runtime.authority, review, self.runtime.repo,
                  configuration_binding=self.runtime.configuration, config=self.runtime.config)
        return {"input": binding, "review": review, "authorization": self.runtime.authority,
                "configuration": self.runtime.configuration}

    def implement(self, ctx):
        _, data = self._bundle(ctx)
        choice = ctx["outputs"]["controller"]["decision"]
        if choice["candidate"]["action"] != "propose_candidate":
            raise ValueError("closed authority request is not an implementation instruction")
        authored = self.author(ctx)
        if type(authored) is not dict or set(authored) != AUTHORED:
            raise ValueError("trusted author returns only versioned candidate/source/family bindings")
        suffix = f"r{ctx['round_index']:04d}-{t.c._digest(choice)[:12]}"
        incumbent = data["pool"]["incumbent"]
        actual_parent = choice["candidate"]["actual_parent_sha256"]
        # Native journal is one execution, not the global research pool. Import
        # only this parent; alias baselines may share one original experiment.
        parents = [item["native_parent"] for item in data["pool"]["archive"]
            if item["candidate_sha256"] == actual_parent and actual_parent != incumbent["candidate_sha256"]
            and item["native_parent"] is not None]
        return h.prepare(self.runtime, choice, {**self.base, **authored, "native_name": "price-native-" + suffix,
            "attempt_id": "price-attempt-" + suffix, "memory_binding": ctx["previous_result"]["memory"],
            "initial_incumbent": incumbent, "archived_parents": parents})

    def source_review(self, ctx):
        prepared = ctx["outputs"]["implement"]
        return h.finalize(self.runtime, prepared, self.reviewer("source", prepared))

    def process_feedback(self, ctx, attempt, result):
        directory = getattr(self, "recovery_directory", "price-loop")
        if directory not in {"price-loop", "price-loop-admission-v2", "price-loop-admission-v3"}:
            raise ValueError("known timing namespace required")
        stages = {}
        for stage in TIMED_STAGES:
            path = self.runtime.root / directory / f"round-{ctx['round_index']:04d}-{stage}.timing.json"
            if path.is_symlink() or path.resolve() != path:
                raise ValueError("stage timing symlink/path drift")
            if path.exists():
                if not path.is_file() or path.stat().st_size > 1024:
                    raise ValueError("small stage timing file required")
                binding = r.pin(path)
                stages[stage] = {"measurement": _timing(binding), "evidence": binding}
            else:
                stages[stage] = {"measurement": None, "evidence": None}
        observation = {"schema": "price_process_feedback_v1", "round_index": ctx["round_index"],
            "source_batch_root": str(self.runtime.root), "stages": stages,
            "execution": {"outcome": result["execution_outcome"],
                **{key: attempt.get(key) for key in ("fits_reserved", "actual_fits", "valid_fits_completed",
                                                    "worker_wall_seconds", "sampled_peak_rss_kib")},
                "performance_evidence": result["manifest"] is not None},
            "result_review": result["review"], "reconcile_timing_included": False}
        return _process_evidence(observation)

    def result_review(self, ctx):
        prepared, receipt = ctx["outputs"]["implement"], ctx["outputs"]["execute"]["receipt"]
        spec = t.c._read(prepared["specification"])
        _, data = self._bundle(ctx)
        choice = ctx["outputs"]["controller"]["decision"]["candidate"]
        selection = t.c._read(prepared["selection"])
        result = {"execution_outcome": receipt["outcome"], "decision": "UNCHANGED", "comparison": None,
            "manifest": None, "candidate_sha256": spec["candidate_binding"]["sha256"],
            "question_digest_sha256": selection["question_digest_sha256"],
            "source_batch_id": self.runtime.fixed_grant["batch_id"], "source_attempt_id": spec["attempt_id"],
            "original_candidate_proposal": choice}
        if receipt["outcome"] == "succeeded":
            output = self.runtime.root / prepared["native_name"] / "runs" / spec["attempt_id"]
            if receipt["output"] != str(output) or output.resolve() != output:
                raise ValueError("worker output escaped exact candidate run")
            manifest = r.pin(output / "manifest.json")
            record = {"candidate_id": choice["candidate_id"], "candidate_sha256": result["candidate_sha256"],
                "manifest": manifest, "model_column": choice["candidate_id"],
                "review": ctx["outputs"]["source_review"]["review"], "native_parent": None}
            saved = t.c._read(manifest)
            card = t._file(output / "scorecard.json")
            if (saved.get("source_commit") != spec["source_commit"] or card.get("task_id") != h.TASK
                    or card.get("source_commit") != spec["source_commit"]
                    or card.get("candidate_id") != choice["candidate_id"]
                    or any(card.get(k) is not False for k in t.c.FLAGS)
                    or card.get("prices_executable") is not False):
                raise ValueError("result source checkpoint drift")
            records = {item["candidate_sha256"]: item for item in data["pool"]["archive"]}
            reference = next(item for item in records.values() if item["manifest"] == self.base["ordinary_reference_binding"]
                             and item["model_column"] != scoring.B0)
            comparison = paired_comparison(record, records[choice["actual_parent_sha256"]],
                records[choice["comparison_incumbent_sha256"]], reference)
            result.update(manifest=manifest, comparison=self._save(ctx, "comparison", comparison),
                decision=comparison["decision"], record=record)
        binding = self.reviewer("result", result)
        review = t.c._read(binding)
        expected = {"passed": True, "authorization_sha256": self.runtime.authority["sha256"],
            "candidate_sha256": result["candidate_sha256"], "execution_outcome": result["execution_outcome"],
            "manifest": result["manifest"], "comparison": result["comparison"],
            "question_digest_sha256": selection["question_digest_sha256"],
            "source_batch_id": result["source_batch_id"], "source_attempt_id": result["source_attempt_id"],
            "evidence_bundle_sha256": result["comparison"]["sha256"] if result["comparison"] else None}
        if (any(type(review.get(k)) is not type(v) or review.get(k) != v for k, v in expected.items())
                or type(review.get("research_credit")) is not int or not 0 <= review["research_credit"] <= 2
                or not isinstance(review.get("finding"), str) or not review["finding"].strip()
                or (receipt["outcome"] != "succeeded" and review["research_credit"] != 0)
                or (review["research_credit"] == 2 and (review.get("research_outcome"), review.get("route_action"))
                    not in {("support", "continue"), ("refute", "branch")})):
            raise ValueError("exact independent result/finding/credit review required")
        return {**result, "review": binding}

    def reconcile(self, ctx):
        bindings, data = self._bundle(ctx)
        result = ctx["outputs"]["result_review"]
        choice = ctx["outputs"]["controller"]["decision"]["candidate"]
        prepared = ctx["outputs"]["implement"]
        selection = t.c._read(prepared["selection"])
        review = t.c._read(result["review"])
        pool = data["pool"]
        record = {"candidate_id": choice["candidate_id"], "candidate_sha256": result["candidate_sha256"],
            "manifest": result["manifest"], "model_column": choice["candidate_id"],
            "review": result["review"], "native_parent": None}
        if any(item["candidate_sha256"] == record["candidate_sha256"] for item in pool["archive"]):
            raise ValueError("candidate source already archived; no duplicate research credit")
        if result["manifest"] is not None:
            if review["research_credit"] == 2:
                record["native_parent"] = {"candidate_id": record["candidate_id"], "candidate_sha256": record["candidate_sha256"],
                    "source_batch_id": self.runtime.fixed_grant["batch_id"], "source_attempt_id": selection["attempt_id"],
                    "archive_manifest_sha256": result["manifest"]["sha256"], "independent_review_sha256": result["review"]["sha256"],
                    "authority_snapshot_sha256": self.runtime.authority["sha256"], "problem_id": choice["question_id"],
                    "question_digest_sha256": selection["question_digest_sha256"], "evidence_bundle_sha256": result["comparison"]["sha256"],
                    "research_credit": 2, "research_outcome": review["research_outcome"],
                    "route_action": review["route_action"], "authority_granted": False}
            if result["decision"] == "KEEP":
                pool["incumbent"] = {"candidate_id": record["candidate_id"], "candidate_sha256": record["candidate_sha256"],
                    "scorecard_sha256": result["comparison"]["sha256"], "review_sha256": result["review"]["sha256"]}
        pool["archive"].append(record)  # Failed code retained too, never eligible performance evidence.
        pool["active_pool"] = choice["active_pool"]  # Scientific selection, never a score-ranked Supervisor menu.
        entry = {"candidate_id": choice["candidate_id"], "actual_parent_sha256": choice["actual_parent_sha256"],
            "comparison_incumbent_sha256": choice["comparison_incumbent_sha256"], "decision": result["decision"],
            "execution_outcome": result["execution_outcome"], "research_credit": review["research_credit"],
            "finding": review["finding"], "review": result["review"], "comparison": result["comparison"],
            "controller_decision_sha256": t.c._digest(ctx["outputs"]["controller"]["decision"])}
        feedback = {**entry, "task_id": h.TASK, "comparison_incumbent_sha256": pool["incumbent"]["candidate_sha256"],
            "previous_comparator_sha256": choice["comparison_incumbent_sha256"],
            "interpretation": "reused Train Discovery, not untouched OOS or executable profit",
            "exploration_eligible": result["manifest"] is not None and review["research_credit"] == 2}
        if result["comparison"]:
            comparison = t.c._read(result["comparison"])
            feedback.update({key: comparison[key] for key in ("equal_game_mse", "equal_game_mae", "equal_game_weighted_pearson",
                                                            "paired", "per_fold", "bootstrap")})
            feedback["coverage"] = {key: comparison["coverage"][key] for key in ("full_population", "checks")}
        memory = {"previous": bindings["memory"], "prior": data["memory"],
            "verified_finding": entry, "controller_memory_additions": choice["memory_additions"],
            "stopped_exact_recipes": choice["stopped_exact_recipes"]}
        # Keep full prior bytes via the immutable previous binding, but do not
        # duplicate every old timing snapshot in the next compact account input.
        history = {"previous": bindings["history"],
            "prior": {key: value for key, value in data["history"].items() if key != "process_feedback"},
            "last_experiment": entry}
        spec = t.c._read(prepared["specification"])
        source = {"previous": bindings["source_context"], "candidate_sha256": result["candidate_sha256"],
            "source_commit": spec["source_commit"], "candidate_source": h._binding(spec["candidate_binding"]).read_text()}
        with (self.runtime.root / ".pilot.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if not self.runtime.admit({"stage": "reconcile"}):
                raise RuntimeError("global finishing admission closed")
            ledger = t._file(self.runtime.root / "ledger.json")
            attempt = next(a for a in ledger["attempts"] if a["attempt_id"] == selection["attempt_id"])
            if attempt["status"] != result["execution_outcome"] or "reconciled_feedback_sha256" in attempt:
                raise ValueError("attempt accounting drift or already reconciled; no retry")
            history["process_feedback"] = self.process_feedback(ctx, attempt, result)
            bundle = {key: self._save(ctx, key, value) for key, value in
                (("feedback", feedback), ("memory", memory), ("history", history), ("pool", pool), ("source_context", source))}
            attempt.update(reconciled_feedback_sha256=bundle["feedback"]["sha256"], result_review_sha256=result["review"]["sha256"])
            ledger.update(incumbent=pool["incumbent"], research_pool_sha256=bundle["pool"]["sha256"])
            t._ledger(self.runtime.root / "ledger.json", ledger)
        return bundle

    def handlers(self):
        return self.runtime.handlers(**{key: getattr(self, key) for key in
            ("input", "implement", "source_review", "result_review", "reconcile")})

    def identity(self):
        h._python_launch(self.base["python_binding"])
        from experiments import nfl_ingame_price_data as price_data
        from experiments import nfl_ingame_price_change_train_diagnostic as price_runner
        from data_scientist_harness import co_evolution_loop as micro
        from supervisor_harness import price_candidate_author as numeric_author
        files = [r.pin(path) for path in (__file__, h.__file__, r.__file__, t.__file__, t.c.__file__, w.__file__,
            h.b.__file__, scoring.__file__, price_data.__file__, price_runner.__file__, micro.__file__, numeric_author.__file__)]
        for binding in self.callbacks.values():
            h._binding(binding)
        return {stage: {"source_dependencies": files + list(self.callbacks.values()), "fixed_base": self.base,
                        "authority": self.runtime.authority, "configuration": self.runtime.configuration}
                for stage in loop.STAGES}

    def run(self, seed, *, max_rounds):
        if max_rounds > self.runtime.fixed_grant["limits"]["original_controller_decisions"]:
            raise ValueError("loop round bound exceeds original decision cap")
        return loop.run(self.runtime.root / "price-loop", self.handlers(), seed=seed,
            admit=self.runtime.admit, max_rounds=max_rounds, handler_identity=self.identity)
