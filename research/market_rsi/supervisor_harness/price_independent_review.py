"""Actual independent price reviews: local checks plus a distinct account role.

The model receives compact aggregates/source, never forecast rows or raw Train.
Tests may inject synthetic transport; the formal entry injects real role_call.
This is human-requested H integration, not researcher/harness self-evolution.
"""
import ast
import json
import os
from pathlib import Path
import subprocess
import time

from supervisor_harness import price_loop_services as services

h, t, r, w = services.h, services.t, services.r, services.w
SCHEMA = t.c._object({
    "schema": {"type": "string", "const": "market_rsi_independent_price_verdict_v1"},
    "input_sha256": t.c.TEXT,
    "stage": {"type": "string", "enum": ["input", "source", "result"]},
    "verdict": {"type": "string", "enum": ["PASS", "REJECT"]},
    "finding": t.c.TEXT,
    "evidence": {"type": "array", "items": t.c.TEXT, "minItems": 1},
    "research_credit": {"type": "integer", "minimum": 0, "maximum": 2},
    "research_outcome": {"type": "string", "enum": ["support", "refute", "inconclusive", "not_applicable"]},
    "route_action": {"type": "string", "enum": ["continue", "branch", "stop", "not_applicable"]},
})


def fit_budget_checks(source):
    """Conservative explicit-fit/thread check, not a general code sandbox."""
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    fit_calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == "fit"]
    if len(fit_calls) > 1:
        raise ValueError("one explicit candidate model fit per frozen fold required")
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "n_jobs" and (
                not isinstance(node.value, ast.Constant) or type(node.value.value) is not int or node.value.value != 1):
            raise ValueError("candidate n_jobs must be literal integer1")
    fit_functions = set()
    for node in fit_calls:
        parent = parents.get(node)
        while parent is not None:
            if isinstance(parent, (ast.For, ast.While, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                raise ValueError("candidate model fit inside loop/comprehension not admitted")
            if isinstance(parent, ast.FunctionDef):
                fit_functions.add(parent.name); break
            parent = parents.get(parent)
    for name in fit_functions:
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == name]
        if len(calls) > 1 or name == "fit_predict" and calls:
            raise ValueError("repeated/recursive model-fit helper not admitted")
        for node in calls:
            parent = parents.get(node)
            while parent is not None:
                if isinstance(parent, (ast.For, ast.While, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                    raise ValueError("model-fit helper inside loop/comprehension not admitted")
                parent = parents.get(parent)
    return {"explicit_model_fit_calls": len(fit_calls), "n_jobs_literal_one": True,
            "explicit_fit_loops_rejected": True, "general_program_fit_bound_proven": False}


class IndependentPriceReviewer:
    """Bind review(stage, material) once; no scientific recipe authorship here."""
    def __init__(self, runtime, role_call, *, role_grant_binding=None):
        if not callable(role_call):
            raise ValueError("actual independent account role transport required")
        self.runtime, self.role_call = runtime, role_call
        self.grant = role_grant_binding or runtime.authority
        h._binding(self.grant)

    def _input(self, material):
        if set(material) != {"input", "authorization", "configuration"}:
            raise ValueError("exact input review material required")
        if (material["authorization"] != self.runtime.authority
                or material["configuration"] != self.runtime.configuration):
            raise ValueError("input review authority/configuration drift")
        for binding in material.values():
            h._binding(binding)
        packet = t.c._read(material["input"])
        fields = {"schema", "bindings", "feedback", "memory", "history", "source_context", "pool",
                  "authority", "provided_parents", "provided_source_sha256", "overhead"}
        typed = packet.get("schema") == "controller_price_feedback_input_v2"
        if typed:
            fields.add("action_context")
        if (len(Path(material["input"]["path"]).read_bytes()) > t.input_limit(self.runtime.fixed_grant)
                or packet.get("authority") != self.runtime.fixed_grant
                or packet.get("schema") not in {"controller_price_feedback_input_v1", "controller_price_feedback_input_v2"}
                or set(packet) != fields
                or set(packet.get("bindings", {})) != services.ROLES):
            raise ValueError("compact tools-closed aggregate input required")
        if (type(packet["provided_parents"]) is not list or not packet["provided_parents"]
                or type(packet["provided_source_sha256"]) is not list
                or any(type(item) is not str or t.c._hashes(item) != {item}
                    for item in packet["provided_parents"] + packet["provided_source_sha256"])
                or w.sha(t.c.CLI) != t.c.CLI_SHA):
            raise ValueError("original parent/source/runtime commitments required before account input")
        for role, binding in packet["bindings"].items():
            h._binding(binding)
            if role != "pool" and packet.get(role) != t.c._read(binding):
                raise ValueError("input material differs from exact saved binding")
        pool = t.c._read(packet["bindings"]["pool"])
        if (packet["pool"]["incumbent"] != pool["incumbent"]
                or packet["pool"]["active_pool"] != pool["active_pool"]
                or packet["feedback"]["comparison_incumbent_sha256"] != pool["incumbent"]["candidate_sha256"]):
            raise ValueError("input incumbent/active branches drift")
        if self.runtime.fixed_grant != t.c._read(self.runtime.authority):
            raise ValueError("original authorization mutated")
        expected = {"authorization_sha256": self.runtime.authority["sha256"],
            "input_sha256": material["input"]["sha256"],
            "transaction_source_sha256": w.sha(t.__file__),
            "consumer_source_sha256": w.sha(t.c.__file__), "cli_sha256": t.c.CLI_SHA,
            "requested_model": t.c.MODEL, "configuration_sha256": self.runtime.configuration["sha256"]}
        account = {"bound_controller_input": packet}
        checks = {"aggregate_bindings_checked": True, "unchanged_authority": True, "raw_rows_transferred": False}
        if typed:
            context = t.action_context(packet)
            fixed = context["identity_configuration"]["fixed_context"]
            if (packet["source_context"].get("controller_action_context") != context
                    or fixed["authority_sha256"] != self.runtime.authority["sha256"]
                    or fixed["resource_policy_sha256"] != self.runtime.configuration["sha256"]):
                raise ValueError("typed action scope differs from bound Supervisor context/authority")
            # Versioned research-side sources only, never mutable trusted runner/kernel.
            namespace = "research/market_rsi/research_capacities/" + self.runtime.fixed_grant["batch_id"] + "/"
            if any(not name.startswith(namespace) for names in
                    context["identity_configuration"]["allowed_write_paths"].values() for name in names):
                raise ValueError("typed capacity scope must use this batch's versioned research namespace")
            expected.update(action_context_sha256=t.c._digest(context), decision_schema_sha256=t.c._digest(t.SCHEMA_V2))
            account["reviewed_decision_schema"] = t.SCHEMA_V2
            checks.update(typed_scope_and_schema_bound=True, capacity_execution_authorized=False)
        if self.runtime.fixed_grant.get("account_roles", {}).get("approved") is True:
            from supervisor_harness import price_account_roles as roles
            contract = roles.transport_contract()
            proof_binding = r.pin(self.runtime.root / "account-runtime-preflight.json")
            proof = t.c._read(proof_binding)
            if (proof.get("authorization") != self.runtime.authority or proof.get("transport_contract") != contract
                    or proof.get("operational_ready") is not True or proof.get("model_calls") != 0
                    or proof.get("private_payload_transfer") is not False):
                raise ValueError("actual native no-environment preflight differs from reviewed grant/source")
            for path, digest in proof["evidence"].items():
                h._binding({"path": path, "sha256": digest})
            policy_path = self.runtime.root / "account-runtime-preflight/runtime-policy.json"
            policy_binding = {"path": str(policy_path), "sha256": proof["evidence"].get(str(policy_path))}
            policy = t.c._read(policy_binding)
            acknowledgement = policy.get("thread_start_result", {})
            if (policy.get("contract") != contract or policy.get("environment_acknowledged") is not True
                    or acknowledgement.get("thread", {}).get("environments") != []
                    or acknowledgement.get("model") != t.c.MODEL
                    or acknowledgement.get("instructionSources") != []):
                raise ValueError("actual no-environment/model/instruction acknowledgement missing")
            expected["controller_transport"] = contract
            account.update(runtime_policy=proof_binding, reviewed_controller_transport=contract)
            checks["actual_native_no_environment_preflight"] = True
        return expected, account, checks

    def _source(self, material):
        if material.get("kind") == "capacity":
            return self._capacity_source(material)
        for key in ("request", "selection", "operation_core", "specification", "response"):
            h._binding(material[key])
        if (material["authorization"] != self.runtime.authority
                or material["configuration"] != self.runtime.configuration):
            raise ValueError("source review authority drift")
        native = h._native(self.runtime, material["native_name"])
        if t._file(native / "prepared.json") != material:
            raise ValueError("saved native preparation drift")
        spec, response = t.c._read(material["specification"]), t.c._read(material["response"])
        _, core, request, selection = h._validate(self.runtime, response, spec)
        if any(t.c._read(material[key]) != value for key, value in
                (("request", request), ("selection", selection), ("operation_core", core))):
            raise ValueError("compiled source request/core/selection drift")
        state = h.b.ContinuousDiscoveryBatch(native).snapshot()
        if state["state_sha256"] != material["state_sha256"] or state["branches"]:
            raise ValueError("native parent initialization changed before source review")
        from supervisor_harness.price_candidate_author import validate_source
        candidate = h._binding(spec["candidate_binding"])
        test = candidate.parent / "test_candidate.py"
        relative = str(test.relative_to(self.runtime.repo))
        if spec["files"].get(relative) != w.sha(test):
            raise ValueError("generated test absent from exact source commitment")
        source, test_source = candidate.read_text(), test.read_text()
        author_path = candidate.parent / "author_receipt.json"
        if spec["files"].get(str(author_path.relative_to(self.runtime.repo))) != w.sha(author_path):
            raise ValueError("original author receipt absent from source commitment")
        author = t._file(author_path)
        if (author.get("schema") != "price_candidate_author_receipt_v1"
                or author.get("original_decision_sha256") != t.c._digest(response)
                or author.get("candidate_id") != response["candidate"]["candidate_id"]
                or author.get("candidate") != spec["candidate_binding"] or author.get("test") != r.pin(test)
                or author.get("generated_tests_executed") is not False
                or author.get("awaiting_independent_source_review") is not True):
            raise ValueError("author provenance differs from original decision/source/test")
        for key in ("input_binding", "response_binding", "process_binding", "completion_binding"):
            h._binding(author["role_call"][key])
        author_input = t.c._read(author["role_call"]["input_binding"])
        author_response = t.c._read(author["role_call"]["response_binding"])
        if (author_input.get("role") != "author" or author_input.get("role_id") != author["role_call"].get("call_id")
                or author_input.get("payload", {}).get("original_controller_decision") != response
                or author_response.get("decision_sha256") != t.c._digest(response)
                or author_response.get("candidate_id") != response["candidate"]["candidate_id"]
                or author_response.get("candidate_source") != source or author_response.get("test_source") != test_source
                or author_response.get("method_family") != spec["method_family"]):
            raise ValueError("original separate author account call required")
        checks = {"candidate_ast": validate_source(source),
            "test_ast": validate_source(test_source, is_test=True),
            "fit_budget": fit_budget_checks(source),
            "native_exact": True, "actual_parent_and_comparator_separate": True}
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"],
            cwd=self.runtime.repo, text=True, timeout=10).strip()
        if commit != spec["source_commit"]:
            raise ValueError("candidate source checkpoint differs from current source")
        expected = {"authorization_sha256": self.runtime.authority["sha256"],
            "request_sha256": material["request"]["sha256"], "execution_source_sha256": w.sha(r.__file__),
            "operation_core_sha256": h.operation_commitment(core)}
        account = {"candidate_source": source, "candidate_test_source": test_source,
            "candidate": spec["candidate_binding"], "test": r.pin(test),
            "source_commit": commit, "original_controller_response": response,
            "author_receipt": r.pin(author_path), "authored_by_call_id": author["role_call"]["call_id"],
            "request": {key: value for key, value in request.items() if key != "files"},
            "source_files_count": len(request["files"]), "source_files_sha256": t.c._digest(request["files"]),
            "request_binding": material["request"], "operation_core": core, "selection": selection}
        return expected, account, checks

    def _capacity_source(self, material):
        from supervisor_harness import price_capacity_services as cs
        from supervisor_harness import price_account_roles as roles
        if (set(material) != {"kind", "author_receipt", "source", "test", "source_commit", "files"}
                or self.grant != self.runtime.authority
                or self.runtime.fixed_grant.get("account_roles", {}).get("capacity_changes_approved") is not True):
            raise ValueError("exact authorized capacity implementation required")
        receipt = t.c._read(material["author_receipt"])
        if (receipt.get("schema") != "price_capacity_author_receipt_v1"
                or receipt.get("authorization") != self.runtime.authority or receipt.get("configuration") != self.runtime.configuration
                or receipt.get("source") != material["source"] or receipt.get("test") != material["test"]
                or receipt.get("generated_tests_executed") is not False or receipt.get("activation_performed") is not False
                or receipt.get("awaiting_independent_source_review") is not True):
            raise ValueError("capacity author provenance/source drift")
        packet = t.c._read(receipt["original_input"])
        decision = t._file(self.runtime.root / "decisions" / packet["bindings"]["feedback"]["sha256"] / "response.json")
        ctx = {"outputs": {"input": {"input": receipt["original_input"], "review": receipt["original_review"],
            "authorization": self.runtime.authority, "configuration": self.runtime.configuration}, "controller": {"decision": decision}}}
        before, entries = receipt["parent_identity"], receipt["parent_entrypoints"]
        cs.original(self.runtime, ctx, before, entries)
        axis = {"researcher": "R", "harness": "H"}[decision["action"]]
        if receipt.get("axis") != axis or receipt.get("original_decision_sha256") != t.c._digest(decision):
            raise ValueError("capacity receipt differs from actual original")
        source, test = h._binding(material["source"]), h._binding(material["test"])
        names = [str(path.relative_to(self.runtime.repo)) for path in (source, test)]
        if (set(names) != set(decision["capacity"]["write_paths"]) or len(set(names)) != 2
                or any(material["files"].get(name) != w.sha(self.runtime.repo / name) for name in names)):
            raise ValueError("capacity code delta differs from original approved paths")
        for name, token in material["files"].items():
            cs.identity.path(name); h._binding({"path": str(self.runtime.repo / name), "sha256": token})
            if cs.hashlib.sha256(subprocess.check_output(["git", "show", material["source_commit"] + ":" + name],
                    cwd=self.runtime.repo)).hexdigest() != token:
                raise ValueError("capacity source checkpoint bytes differ")
        if any(material["files"].get(name) != token for component in before["components"].values()
                for name, token in component["sources"].items()):
            raise ValueError("inherited capacity manifest missing/drifted")
        if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.runtime.repo, text=True).strip() != material["source_commit"]:
            raise ValueError("capacity source checkpoint is not current source")
        checks = {"capacity_ast": cs.guard.validate_source(source.read_text()),
            "capacity_test_ast": cs.guard.validate_source(test.read_text(), is_test=True, module_name=source.stem),
            "exact_original_and_scope": True, "capacity_activation_performed": False, "raw_rows_transferred": False}
        author = receipt["role_call"]
        directory = self.runtime.root / "role_calls/author" / author["call_id"]
        if directory.resolve() != directory:
            raise ValueError("capacity author role directory symlink")
        claim = t._file(directory / "claim.json")
        if (claim.get("authorization") != self.runtime.authority or claim.get("role") != "author"
                or claim.get("role_id") != author["call_id"]
                or claim.get("schema_sha256") != t.c._digest(t._file(directory / "schema.json"))):
            raise ValueError("capacity original author claim drift")
        replayed = roles._recover(directory, claim, t._file(directory / "schema.json"))
        if any(author.get(key) != value for key, value in replayed.items() if key != "response"):
            raise ValueError("capacity receipt differs from actual separate author completion")
        author_input, response = t.c._read(author["input_binding"]), replayed["response"]
        body = t._file(Path(material["author_receipt"]["path"]).parent / "input.json")
        if (author_input.get("payload") != body or body.get("original_controller_decision") != decision
                or response.get("decision_sha256") != t.c._digest(decision)
                or response.get("source_path") != names[0] or response.get("test_path") != names[1]
                or response.get("capacity_source") != source.read_text() or response.get("test_source") != test.read_text()):
            raise ValueError("capacity source does not match original separate author output")
        after = cs.deepcopy(before)
        after["components"][axis]["sources"].update({name: material["files"][name] for name in names})
        after = cs.identity.manifest(kernel=after["components"]["K"], model=after["model"], predictor=after["components"]["C"],
            harness=after["components"]["H"], researcher=after["components"]["R"], memory=after["memory_sha256"], runtime=after["runtime"])
        if cs.identity.change_axis(before, after) != axis:
            raise ValueError("capacity implementation changes more than its one declared axis")
        entries = {**entries, axis: names[0]}
        expected = {"authorization_sha256": self.runtime.authority["sha256"], "implementation_sha256": t.c._digest(material),
            "original_decision_sha256": t.c._digest(decision), "identity_sha256": t.c._digest(after), "entrypoints": entries,
            "reviewer_id": packet["action_context"]["identity_configuration"]["reviewer_id"],
            "proposer_id": "controller-" + t.c._digest(decision)[:20]}
        account = {"candidate_source": source.read_text(), "candidate_test_source": test.read_text(),
            "authored_by_call_id": author["call_id"], "original_controller_response": decision,
            "before_identity": before, "after_identity": after, "entrypoints": entries, "source_commit": material["source_commit"],
            "author_receipt": material["author_receipt"], "claim_boundary": "Static source/smoke review only; no matched benefit or activation"}
        return expected, account, checks

    def _result(self, material):
        if material.get("kind") == "capacity_result":
            from supervisor_harness.price_capacity_trial import result_material
            return result_material(self.runtime, material, self)
        choice = material["original_candidate_proposal"]
        expected = {key: material[key] for key in ("candidate_sha256", "execution_outcome", "manifest", "comparison",
            "question_digest_sha256", "source_batch_id", "source_attempt_id")}
        expected.update(authorization_sha256=self.runtime.authority["sha256"],
            evidence_bundle_sha256=material["comparison"]["sha256"] if material["comparison"] else None)
        if material["source_batch_id"] != self.runtime.fixed_grant["batch_id"]:
            raise ValueError("result belongs to a different batch")
        ledger = t._file(self.runtime.root / "ledger.json")
        matches = [entry for entry in ledger["attempts"] if entry["attempt_id"] == material["source_attempt_id"]]
        if len(matches) != 1 or matches[0]["status"] != material["execution_outcome"]:
            raise ValueError("result differs from once-only execution accounting")
        if material["execution_outcome"] != "succeeded":
            if material["manifest"] is not None or material["comparison"] is not None or material["decision"] != "UNCHANGED":
                raise ValueError("failed execution cannot contain performance evidence")
            return expected, {"outcome": material["execution_outcome"], "original_candidate_proposal": choice,
                "attempt": matches[0], "performance_evidence": None}, {"failed_execution_has_no_score": True}
        for key in ("manifest", "comparison"):
            h._binding(material[key])
        packets = [t._file(path) for path in self.runtime.root.glob("price-round-*-input.json")]
        packets = [packet for packet in packets if t.c._digest(packet) == choice["input_sha256"]]
        if len(packets) != 1:
            raise ValueError("result must bind one exact original Controller input")
        pool = t.c._read(packets[0]["bindings"]["pool"])
        records = {item["candidate_sha256"]: item for item in pool["archive"]}
        ordinary = next(item for item in records.values() if item["model_column"] == "B1-FixedHGBRegressor")
        computed = services.paired_comparison(material["record"], records[choice["actual_parent_sha256"]],
            records[choice["comparison_incumbent_sha256"]], ordinary)
        if computed != t.c._read(material["comparison"]) or computed["decision"] != material["decision"]:
            raise ValueError("independent frozen-scorer re-run differs from submitted result")
        account = {"outcome": material["execution_outcome"], "original_candidate_proposal": choice,
            "manifest": material["manifest"], "comparison": material["comparison"],
            "metrics": {key: computed[key] for key in ("equal_game_mse", "equal_game_mae", "equal_game_weighted_pearson",
                "paired", "per_fold", "per_week", "bootstrap", "decision")},
            "coverage": {key: computed["coverage"][key] for key in ("full_population", "checks")}}
        return expected, account, {"independent_local_scorer_rerun": True,
            "identical_paired_rows_labels_and_clocks": True, "raw_rows_transferred": False,
            "full_population_retained": True}

    def _tests(self, material, directory):
        wall_limit = 30
        if material.get("kind") == "capacity":
            spec = {"candidate_binding": material["source"], "files": material["files"],
                "python_binding": t.c._read(material["author_receipt"])["parent_identity"]["runtime"]["python"]}
            candidate, test = h._binding(material["source"]), h._binding(material["test"])
            receipt = t.c._read(material["author_receipt"])
            packet = t.c._read(receipt["original_input"])
            decision = t._file(self.runtime.root / "decisions" / packet["bindings"]["feedback"]["sha256"] / "response.json")
            wall_limit = min(wall_limit, decision["capacity"]["resources"]["seconds"],
                (t.c._time(self.runtime.fixed_grant["deadline_utc"]) - t.datetime.now(t.timezone.utc)).total_seconds())
            if wall_limit <= 0:
                raise ValueError("capacity test window already closed; no launch")
        else:
            spec = t.c._read(material["specification"])
            candidate = h._binding(spec["candidate_binding"])
            test = candidate.parent / "test_candidate.py"
        if spec["files"].get(str(test.relative_to(self.runtime.repo))) != w.sha(test):
            raise ValueError("reviewed synthetic test drift before import/execution")
        python, _ = h._python_launch(spec["python_binding"])
        environment = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", **{key: "1" for key in
            ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}}
        command = [python, "-B", str(test)]
        start = time.monotonic()
        with (directory / "candidate-test.stdout").open("xb") as stdout, (directory / "candidate-test.stderr").open("xb") as stderr:
            child = subprocess.Popen(command, cwd=candidate.parent, env=environment, stdout=stdout, stderr=stderr,
                start_new_session=True)
            peak, stopped, diagnostic_error = 0, None, None
            try:
                while child.poll() is None:
                    peak = max(peak, 1024 * w.sample_rss(child))
                    if time.monotonic() - start > wall_limit or peak > self.runtime.fixed_grant["limits"]["sampled_rss_bytes"]:
                        import signal
                        stopped = "timeout" if time.monotonic() - start > wall_limit else "sampled_rss_cap"
                        os.killpg(child.pid, signal.SIGKILL)
                        break
                    if sum((directory / name).stat().st_size for name in ("candidate-test.stdout", "candidate-test.stderr")) > 1048576:
                        import signal
                        stopped = "output_cap"; os.killpg(child.pid, signal.SIGKILL); break
                    time.sleep(.05)
            except BaseException as error:
                diagnostic_error = error
            finally:
                if child.poll() is None:
                    import signal
                    try: os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                status = child.wait(timeout=5)
        receipt = {"command": command, "exit_code": status, "stop_reason": stopped,
            "wall_seconds": time.monotonic() - start, "sampled_peak_rss_bytes": peak,
            "source": spec["candidate_binding"], "test": r.pin(test),
            "stdout": r.pin(directory / "candidate-test.stdout"), "stderr": r.pin(directory / "candidate-test.stderr"),
            "synthetic_inputs_only": True, "train_fits": 0, "arbitrary_code_containment_claim": False}
        if diagnostic_error is not None:
            receipt.update(diagnostic_error_type=type(diagnostic_error).__name__, process_reaped=True,
                sampled_peak_rss_bytes=None)  # Unavailable sampling is not measured zero.
        w.save(directory / "candidate-test.json", receipt)
        if diagnostic_error is not None:
            raise diagnostic_error
        if status != 0 or stopped is not None:
            raise RuntimeError("independently reviewed generated test failed; preserve without automatic retry")
        return r.pin(directory / "candidate-test.json")

    def review(self, stage, material):
        if stage not in {"input", "source", "result"}:
            raise ValueError("unknown independent review stage")
        expected, account, checks = getattr(self, "_" + stage)(material)
        capacity_result = stage == "result" and material.get("kind") == "capacity_result"
        packet = {"schema": "market_rsi_independent_price_review_input_v1", "stage": stage,
            "question": "Independently PASS or REJECT the supplied material. Judge consistency, leakage, boundary and evidence; do not author source or choose the next candidate.",
            "trusted_checks": checks, "material": account,
            "limitations": "Repeated historical Train Discovery; no untouched OOS, executable fills/profit or researcher superiority. Research credit is evidence quality, never added to MSE. Failed execution is not scientific refutation."}
        if capacity_result:
            packet["question"] = "Independently judge the predeclared named capacity benefit on actual matched outputs. PASS is not acceptance: benefit and compatibility must both be demonstrated. Reject unsupported claims; a valid no-benefit result is useful negative evidence, not a prediction failure. No requirement of MSE gain. Replay fixtures do not establish researcher superiority or full-driver recovery."
        if len((json.dumps(packet, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()) > t.input_limit(t.c._read(self.grant), "account_roles"):
            raise ValueError("review payload exceeds authorized input byte budget before account call")
        role_id = "price-" + stage + "-review-" + t.c._digest(packet)[:20]
        directory = self.runtime.root / "independent-reviews" / role_id
        if directory.exists():
            raise FileExistsError("review operation already exists; inspect without resampling")
        directory.mkdir(parents=True)
        w.save(directory / "material.json", {"stage": stage, "expected": expected, "input": packet})
        schema = json.loads(json.dumps(SCHEMA))
        schema["properties"]["input_sha256"] = {"type": "string", "const": t.c._digest(packet)}
        schema["properties"]["stage"] = {"type": "string", "const": stage}
        if capacity_result:
            schema["properties"].update(benefit_observed={"type": "boolean"},
                compatibility_checks=t.c._object({name: {"type": "boolean"} for name in checks}))
            schema["required"] += ["benefit_observed", "compatibility_checks"]
        # Only a new explicit per-role grant can enlarge this wait; legacy stays120.
        limits = t.c._read(self.grant)["account_roles"].get("call_seconds", {})
        timeout = limits.get(stage + "_review", 120)
        call = self.role_call(stage + "_review", packet, schema, operation_id=role_id, timeout_seconds=timeout)
        response = call["response"]
        t.c._validate(response, schema)
        if (type(response["research_credit"]) is not int or not 0 <= response["research_credit"] <= 2
                or not isinstance(response["finding"], str) or not response["finding"].strip()
                or type(response["evidence"]) is not list or not response["evidence"]
                or any(type(item) is not str or not item.strip() for item in response["evidence"])
                or stage == "source" and call["call_id"] == account["authored_by_call_id"]):
            raise ValueError("independent verdict needs actual role identity and bounded verified metadata")
        if response["input_sha256"] != t.c._digest(packet) or response["stage"] != stage:
            raise ValueError("independent original response does not bind reviewed material")
        if capacity_result and call["call_id"] in {account["authored_by_call_id"],
                t.c._read(t.c._read(material["request"])["source_review"])["original_account_call"]["call_id"]}:
            raise ValueError("capacity benefit needs a distinct original reviewer call")
        if stage != "result" and (response["research_credit"] != 0
                or response["research_outcome"] != "not_applicable" or response["route_action"] != "not_applicable"):
            raise ValueError("input/source review cannot invent scientific research credit")
        if stage == "result" and (material["execution_outcome"] != "succeeded" and response["research_credit"] != 0):
            raise ValueError("failed execution cannot earn scientific performance credit")
        if stage == "result" and response["research_credit"] == 2 and (
                response["research_outcome"], response["route_action"]) not in {("support", "continue"), ("refute", "branch")}:
            raise ValueError("credit2 continuation must bind valid support or useful negative evidence")
        receipt = {**expected, "schema": "market_rsi_independent_price_review_v1",
            "passed": response["verdict"] == "PASS", "verdict": response["verdict"], "finding": response["finding"],
            "research_credit": response["research_credit"], "research_outcome": response["research_outcome"],
            "route_action": response["route_action"], "evidence": response["evidence"], "account_role": stage + "_review",
            "reviewer_source_sha256": w.sha(__file__), "material_sha256": w.sha(directory / "material.json"),
            "original_account_call": {key: call[key] for key in ("call_id", "input_binding", "response_binding",
                "process_binding", "completion_binding", "usage", "serving_snapshot")},
            "independence": "Separate original account reviewer; not candidate author self-signature"}
        if response["verdict"] == "PASS" and stage == "source":
            receipt["generated_test_receipt"] = self._tests(material, directory)
        if capacity_result:
            from supervisor_harness import price_capacity_replay as replay
            request = t.c._read(material["request"]); binding = request["binding"]
            verified = {name: value is True and response["compatibility_checks"][name] is True for name, value in checks.items()}
            observed = response["benefit_observed"] and material["execution_outcome"] == "succeeded"
            accept = response["verdict"] == "PASS" and observed and all(verified.values())
            compatibility = replay.save(directory / "compatibility.json", {"binding": binding, "checks": verified,
                "measurement": material["measurement"], "review_response": call["response_binding"]})
            benefit = replay.save(directory / "benefit.json", {**{k: binding[k] for k in
                ("proposal_sha256", "before_identity_sha256", "after_identity_sha256")},
                "effect": request["decision"]["capacity"]["expected_effect"], "benefit_observed": observed,
                "matched_outputs_sha256": compatibility["sha256"], "measurement": material["measurement"],
                "independent_response": call["response_binding"]})
            native_review = {"reviewer_id": t.c._read(request["source_review"])["reviewer_id"],
                "proposal_sha256": binding["proposal_sha256"], "decision": "accept" if accept else "reject",
                "reason": response["finding"], "tested_pair_sha256": binding["tested_pair_sha256"],
                "anchor_pair_sha256": binding["anchor_pair_sha256"],
                "checks": {name: {"passed": value, "evidence_sha256": compatibility["sha256"]} for name, value in verified.items()},
                "benefit_observed": observed, "benefit_evidence_sha256": benefit["sha256"],
                "actual_write_paths": request["decision"]["capacity"]["write_paths"]}
            receipt["capacity_activation_review"] = replay.save(directory / "activation-review.json", {
                "review": native_review, "evidence": {item["sha256"]: item["path"] for item in (compatibility, benefit)}})
            receipt["capacity_decision"] = native_review["decision"]
        w.save(directory / "review.json", receipt)
        if response["verdict"] != "PASS" and not capacity_result:
            raise RuntimeError("independent reviewer rejected material; preserve original response without retry")
        return r.pin(directory / "review.json")
