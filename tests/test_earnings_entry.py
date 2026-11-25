import json
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import earnings_entry as entry
from edgar_forecast_budget import PilotBudget
from edgar_forecast_full_budget import activate, FullBudget
from edgar_forecast_model_pilot import digest
from earnings_night_budget import history_snapshot

TARGETS = [f"T{i:03d}" for i in range(1, 6)]


class EarningsEntryTests(unittest.TestCase):
    def parent_fixture(self, root):
        parent = {"schema": "earnings_research_recipe_v1", "task_id": "fixture-task",
            "parent_feedback_sha256": "b" * 64, "research_instructions": "T001 use the seasonal anchor."}
        current = dict(parent, parent_feedback_sha256="c" * 64,
            research_instructions="Change only T005; retain prior T001 method.")
        packet = {"schema": "earnings_controller_packet_v1", "task_id": "fixture-task",
            "parent_feedback_sha256": "c" * 64, "questions": "Invented questions", "prior_recipe": parent,
            "feedback": {"observation": {"schema": "earnings_aggregate_feedback_v1",
                "task_id": "fixture-task", "cik": "fixture-cik"}}}
        bindings = {}
        for name, value in (("parent", parent), ("current", current), ("packet", packet)):
            path = root / (name + ".json")
            entry.durable_json(path, value)
            bindings[name] = {"path": str(path), "sha256": digest(path.read_bytes())}
        config = {"task_id": "fixture-task", "cik": "fixture-cik", "parent_feedback_sha256": "c" * 64,
            "research_recipe": bindings["current"],
            "parent_plan_context": {"recipe": bindings["parent"], "feedback_packet": bindings["packet"]}}
        return config, parent, current, packet

    def test_parent_loader_strict_lineage_and_bindings_before_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            config, parent, current, packet = self.parent_fixture(Path(directory).resolve())
            self.assertIsNone(entry.load_parent_plan({}, None))
            with patch.object(entry, "credential") as keys:
                self.assertEqual(entry.load_parent_plan(config, current), parent)
                self.assertEqual(entry.load_parent_plan(config, current, questions="Invented questions"), parent)
                with self.assertRaises(ValueError):
                    entry.load_parent_plan(config, current, questions="Other fiscal period questions")
                for context in ({}, [], dict(config["parent_plan_context"], extra=True),
                        dict(config["parent_plan_context"], recipe=dict(config["parent_plan_context"]["recipe"], sha256="0" * 64))):
                    with self.subTest(context=context), self.assertRaises(ValueError):
                        entry.load_parent_plan(dict(config, parent_plan_context=context), current)
                with self.assertRaises(ValueError):
                    entry.load_parent_plan(config, None)
                binding = config["parent_plan_context"]["feedback_packet"]
                path = Path(binding["path"])
                for change in ({"task_id": "other"}, {"parent_feedback_sha256": "d" * 64},
                               {"prior_recipe": None}, {"feedback": []}):
                    path.write_text(json.dumps(dict(packet, **change)))
                    binding["sha256"] = digest(path.read_bytes())
                    with self.subTest(change=change), self.assertRaises(ValueError):
                        entry.load_parent_plan(config, current)
                keys.assert_not_called()

    def test_parent_plan_receipt_precedes_factory_and_reaches_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config, parent, current, _ = self.parent_fixture(root)
            qa = root / "qa.json"
            entry.durable_json(qa, {"fixture": True})
            config.update(ledger="synthetic-only", baseline={}, model="gpt-6.1-sol",
                deadline_utc="2099-01-01T01:00:00Z", new_request_cutoff_utc="2099-01-01T00:30:00Z",
                qa={"path": str(qa), "sha256": digest(qa.read_bytes())},
                runtime_config={"request_timeout_seconds": 1, "company_wall_seconds": 10, "models": {"gpt-6.1-sol": {}}})
            output = root / "child"
            def factory():
                self.assertEqual(json.loads((output / "effective-parent-plan.json").read_text())["recipe"], parent)
                return Mock(timeout=1)
            def worker(*args, **kwargs):
                self.assertEqual(kwargs, {"research_recipe": current, "parent_research_recipe": parent})
                entry.durable_json(args[-1] / "01-response.json", self.response(json.dumps(self.payload())))
                return {"status": "COMPLETED"}
            budget = Mock(monotonic_deadline=time.monotonic() + 100)
            budget.summary.return_value = {"fixture": True}
            with patch.object(entry, "NightBudget", return_value=budget), patch.object(entry, "forecast", side_effect=worker):
                result = entry._claimed_forecast(config, {}, TARGETS, Mock(return_value={"score_out_of_5": 0}), output, factory)
            self.assertEqual(result["status"], "COMPLETED_SCORED")

    def test_standalone_context_uses_original_inherited_clock_before_claim(self):
        import earnings_clock
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config = {"output": str(root / "attempts" / "new-id"),
                "new_request_cutoff_utc": "2099-01-01T00:30:00Z",
                "inherited_clock": {"binding": {"path": str(root / "old-loop" / "clock.json"), "sha256": "a" * 64},
                                    "source_commit": "b" * 40}}
            window = {"cutoff_monotonic": time.monotonic() + 100}
            with patch.object(entry, "ARCHIVE", root), patch.object(entry, "preflight", return_value=({}, TARGETS, Mock())), \
                    patch.object(earnings_clock, "capture_or_load", return_value=(window, {})) as clock, \
                    patch.object(entry, "_claimed_forecast", return_value={"status": "fixture"}) as claimed:
                self.assertEqual(entry.run_one(config), {"status": "fixture"})
                clock.assert_called_once_with(str(root / "old-loop"), config, create=False)
                self.assertIs(claimed.call_args.args[-1], window)
                claimed.reset_mock()
                window["cutoff_monotonic"] = time.monotonic() - 1
                with self.assertRaises(entry.BudgetStop):
                    entry.run_one(config)
                claimed.assert_not_called()

    def test_review_route_preserves_independent_verdict_and_mechanical_child_separation(self):
        import types
        module = types.ModuleType("earnings_loop_policy")
        module.validate_child = Mock()
        config = {"source_commit": "a" * 40, "loop_authorization": {"envelope": {"path": "fixture"}}}
        config["launch_policy_sha256"] = entry.policy_sha(config)
        with patch.dict(sys.modules, {"earnings_loop_policy": module}):
            entry.validate_review(config)
            module.validate_child.assert_called_once_with(config)
            module.validate_child.reset_mock()
            with self.assertRaises(ValueError):
                entry.validate_review(dict(config, source_commit="b" * 40))
            module.validate_child.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "review.json"
            baseline = {"source_commit": "a" * 40}
            baseline["launch_policy_sha256"] = entry.policy_sha(baseline)
            entry.durable_json(path, {"source_commit": "a" * 40,
                "launch_policy_sha256": baseline["launch_policy_sha256"], "verdict": "PASS_FOR_ONE_BOUNDED_FORECAST"})
            baseline["review"] = {"path": str(path), "sha256": entry.digest(path.read_bytes())}
            entry.validate_review(baseline)
            with patch.object(entry, "checked", return_value=json.dumps({"source_commit": "a" * 40,
                    "launch_policy_sha256": baseline["launch_policy_sha256"], "verdict": "MECHANICAL_CHILD_PASS"}).encode()):
                with self.assertRaises(ValueError):
                    entry.validate_review(baseline)

    def response(self, text):
        return {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": text}]}]}

    def payload(self, value=1):
        return {"predictions": [{"target_id": t, "predicted_value": value} for t in TARGETS]}

    def test_five_literal_finite_numbers_pass(self):
        value = self.payload(1.5)
        self.assertEqual(entry.strict_predictions(self.response(json.dumps(value)), TARGETS), value)

    def test_recipe_loader_binding_identity_and_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            recipe = {"schema": "earnings_research_recipe_v1", "task_id": "fixture-task",
                      "parent_feedback_sha256": "a" * 64, "research_instructions": "Inspect units."}
            self.assertIsNone(entry.load_research_recipe({}))
            values = [recipe, dict(recipe, extra=True), dict(recipe, task_id="other"),
                      dict(recipe, parent_feedback_sha256="b" * 64),
                      dict(recipe, research_instructions=""), dict(recipe, research_instructions="x" * 2201),
                      dict(recipe, research_instructions="😀" * 1200)]
            for index, value in enumerate(values):
                path = root / (str(index) + ".json")
                entry.durable_json(path, value)
                config = {"task_id": "fixture-task", "parent_feedback_sha256": "a" * 64,
                          "research_recipe": {"path": str(path), "sha256": digest(path.read_bytes())}}
                if index == 0:
                    self.assertEqual(entry.load_research_recipe(config), recipe)
                    with self.assertRaises(ValueError):
                        entry.load_research_recipe(dict(config, research_recipe=dict(config["research_recipe"], sha256="b" * 64)))
                else:
                    with self.assertRaises(ValueError):
                        entry.load_research_recipe(config)

    def test_claimed_entry_captures_recipe_before_factory_and_rechecks_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            recipe = {"schema": "earnings_research_recipe_v1", "task_id": "fixture-task",
                      "parent_feedback_sha256": "a" * 64, "research_instructions": "Inspect units."}
            path, qa = root / "recipe.json", root / "qa.json"
            entry.durable_json(path, recipe)
            entry.durable_json(qa, {"fixture": True})
            config = {"ledger": "synthetic-only", "baseline": {}, "task_id": "fixture-task",
                      "parent_feedback_sha256": "a" * 64,
                      "research_recipe": {"path": str(path), "sha256": digest(path.read_bytes())},
                      "qa": {"path": str(qa), "sha256": digest(qa.read_bytes())},
                      "deadline_utc": "2099-01-01T01:00:00Z", "new_request_cutoff_utc": "2099-01-01T00:30:00Z",
                      "model": "gpt-6.1-sol", "runtime_config": {"request_timeout_seconds": 1,
                          "company_wall_seconds": 10, "models": {"gpt-6.1-sol": {}}}}
            output = root / "success"
            def factory():
                self.assertEqual(json.loads((output / "effective-recipe.json").read_text())["recipe"], recipe)
                return Mock(timeout=1)
            def worker(*args, **kwargs):
                self.assertEqual(kwargs, {"research_recipe": recipe})
                entry.durable_json(args[-1] / "01-response.json", self.response(json.dumps(self.payload())))
                return {"status": "COMPLETED"}
            budget = Mock(monotonic_deadline=time.monotonic() + 100)
            budget.summary.return_value = {"fixture": True}
            with patch.object(entry, "NightBudget", return_value=budget), patch.object(entry, "forecast", side_effect=worker):
                result = entry._claimed_forecast(config, {}, TARGETS, Mock(return_value={"score_out_of_5": 0}), output, factory)
            self.assertEqual(result["status"], "COMPLETED_SCORED")
            receipt = json.loads((output / "effective-recipe.json").read_text())
            self.assertEqual(receipt["binding"], config["research_recipe"])
            self.assertEqual(receipt["parent_feedback_sha256"], "a" * 64)
            self.assertEqual(entry.load_research_recipe(config), recipe)
            # Mutate only the invented fixture after earlier validation.
            path.write_text("{}")
            with patch.object(entry, "NightBudget") as ledger, patch.object(entry, "forecast") as worker:
                denied_factory = Mock()
                failed = entry._claimed_forecast(config, {}, TARGETS, Mock(), root / "denied", denied_factory)
            self.assertEqual((failed["status"], failed["planned_targets"]), ("FAILED_NO_RETRY", 5))
            denied_factory.assert_not_called()
            ledger.assert_not_called()
            worker.assert_not_called()

    def test_original_finite_numeric_strings_pass_without_conversion(self):
        for value in ("1.5", "-2", "+1", ".25", "1e-3"):
            with self.subTest(value=value):
                payload = self.payload(value)
                self.assertEqual(entry.strict_predictions(self.response(json.dumps(payload)), TARGETS), payload)
                self.assertEqual(entry.strict_single_number(payload, TARGETS), [])

    def test_unsafe_strings_bools_nonfinite_and_overflow_fail(self):
        for value in ("1-2", "1,500", "$1.5", "1.5%", "nan", "1e309", " 1.5 ", True, None,
                      float("nan"), float("inf"), -float("inf"), 1e309):
            with self.subTest(value=value), self.assertRaises(ValueError):
                entry.strict_predictions(self.response(json.dumps(self.payload(value))), TARGETS)

    def test_missing_extra_duplicate_unknown_targets_fail(self):
        for predictions in (self.payload()["predictions"][:-1], self.payload()["predictions"] * 2,
                            [self.payload()["predictions"][0]] * 5,
                            [{"target_id": "UNKNOWN", "predicted_value": 1}] * 5):
            with self.subTest(predictions=predictions), self.assertRaises(ValueError):
                entry.strict_predictions(self.response(json.dumps({"predictions": predictions})), TARGETS)

    def test_duplicate_keys_and_malformed_json_fail(self):
        for text in ('{"predictions":[],"predictions":[]}', '{"predictions":[{"target_id":"T001","predicted_value":1,"predicted_value":2}]}', "not-json"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                entry.strict_predictions(self.response(text), TARGETS)

    def test_extra_schema_fields_fail(self):
        value = self.payload()
        value["extra"] = "not allowed"
        with self.assertRaises(ValueError):
            entry.strict_predictions(self.response(json.dumps(value)), TARGETS)
        value.pop("extra")
        value["predictions"][0]["confidence"] = 1
        with self.assertRaises(ValueError):
            entry.strict_predictions(self.response(json.dumps(value)), TARGETS)

    def test_refusal_mixed_with_valid_predictions_fails(self):
        response = self.response(json.dumps(self.payload()))
        response["output"][0]["content"].append({"type": "refusal", "refusal": "synthetic refusal"})
        with self.assertRaises(ValueError):
            entry.strict_predictions(response, TARGETS)

    def test_incomplete_or_final_tool_call_fail(self):
        response = self.response(json.dumps(self.payload()))
        response["status"] = "incomplete"
        with self.assertRaises(ValueError):
            entry.strict_predictions(response, TARGETS)
        response["status"] = "completed"
        response["output"].append({"type": "function_call"})
        with self.assertRaises(ValueError):
            entry.strict_predictions(response, TARGETS)

    def test_artifact_hash_symlink_and_overwrite_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "receipt.json"
            entry.durable_json(path, {"value": 1})
            binding = {"path": str(path), "sha256": entry.digest(path.read_bytes())}
            self.assertEqual(entry.checked(binding), path.read_bytes())
            with self.assertRaises(FileExistsError):
                entry.durable_json(path, {"value": 2})
            with self.assertRaises(ValueError):
                entry.checked(dict(binding, sha256="a" * 64))
            alias = path.with_name("alias.json")
            alias.symlink_to(path)
            with self.assertRaises(ValueError):
                entry.checked(dict(binding, path=str(alias)))

    def test_launch_policy_binds_actual_not_declared_values(self):
        config = {"source_commit": "a" * 40, "baseline": {"charged": 1}, "review": {"path": "x"}}
        before = entry.policy_sha(config)
        self.assertEqual(before, entry.policy_sha(dict(config, launch_policy_sha256="declared")))
        self.assertNotEqual(before, entry.policy_sha(dict(config, baseline={"charged": 0})))
        self.assertNotEqual(before, entry.policy_sha(dict(config, source_commit="b" * 40)))

    def test_absolute_alarm_interrupts_and_restores_without_retry(self):
        original = signal.getsignal(signal.SIGALRM)
        with self.assertRaises(entry.BudgetStop):
            with entry.absolute_window(0.005):
                time.sleep(0.02)
        self.assertEqual(signal.getsignal(signal.SIGALRM), original)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_invalid_source_refuses_before_credentials_or_transport(self):
        factory = Mock()
        with patch.object(entry, "credential") as keys:
            with self.assertRaises(ValueError):
                entry.run_one({"source_commit": "not-a-commit"}, factory)
            keys.assert_not_called()
        factory.assert_not_called()

    def test_receipt_transport_preserves_failure_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve()
            client = Mock()
            client.post.side_effect = TimeoutError("synthetic")
            transport = entry.ReceiptHTTP(client, output)
            entry.durable_json(output / "01-request.json", {"request_id": "synthetic-reservation",
                                "reserved_nano_usd": 123,
                                "payload": {"input": "visible"}})
            with self.assertRaises(TimeoutError):
                transport.post("/v1/responses", {"input": "visible"})
            client.post.assert_called_once()
            self.assertEqual(len(list(output.glob("*.intent.json"))), 1)
            failure = list(output.glob("*.failed.json"))[0]
            self.assertFalse(json.loads(failure.read_text())["retry_allowed"])
            intent = json.loads(list(output.glob("*.intent.json"))[0].read_text())
            self.assertEqual(intent["complete_reservation"],
                             json.loads((output / "01-request.json").read_text()))
            self.assertEqual(intent["complete_reservation"]["reserved_nano_usd"], 123)

    def test_scoring_cannot_cross_captured_hard_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            qa = root / "qa.json"
            entry.durable_json(qa, {"fixture": True})
            config = {"ledger": "synthetic-only", "baseline": {}, "deadline_utc": entry.DEADLINE,
                      "new_request_cutoff_utc": entry.CUTOFF,
                      "qa": {"path": str(qa), "sha256": digest(qa.read_bytes())},
                      "model": "gpt-6.1-sol", "runtime_config": {"request_timeout_seconds": 1,
                          "company_wall_seconds": 10, "models": {"gpt-6.1-sol": {}}}}
            mono = [1]
            budget = Mock(monotonic_deadline=100)
            budget.summary.return_value = {"synthetic_known_charge": 123, "blocked": False}
            def worker(client, rates, runtime, company, ledger, output):
                entry.durable_json(output / "01-response.json", self.response(json.dumps(self.payload())))
                return {"status": "COMPLETED", "fixture": True}
            def score(**kwargs):
                mono[0] += 2
                return {"score_out_of_5": 0}
            with patch.object(entry, "NightBudget", return_value=budget), \
                    patch.object(entry, "forecast", side_effect=worker) as forecast, \
                    patch.object(entry.time, "time", return_value=entry.utc_epoch(entry.DEADLINE) - 1), \
                    patch.object(entry.time, "monotonic", side_effect=lambda: mono[0]):
                result = entry._claimed_forecast(config, {}, TARGETS, score, root / "attempt", lambda: Mock(timeout=1))
            self.assertEqual((result["status"], result["planned_targets"], result["scored_targets"]),
                             ("FAILED_NO_RETRY", 5, 0))
            self.assertEqual(result["error_type"], "BudgetStop")
            self.assertIn("Late", result["boundary_reason"])
            self.assertEqual(json.loads((root / "attempt" / "budget-summary.json").read_text()),
                             budget.summary.return_value)
            forecast.assert_called_once()
            budget.close.assert_called_once()

    def test_generation_requires_exact_reserved_payload_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            output, client = Path(directory).resolve(), Mock()
            transport = entry.ReceiptHTTP(client, output)
            with self.assertRaises(ValueError):
                transport.post("/v1/responses", {"input": "visible"})
            entry.durable_json(output / "01-request.json", {"request_id": "synthetic-reservation",
                                "payload": {"input": "different"}})
            with self.assertRaises(ValueError):
                transport.post("/v1/responses", {"input": "visible"})
            client.post.assert_not_called()

    def test_original_forecast_budget_receipts_strict_score_and_no_duplicate_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            files = {"questions.md": "\n".join(f"### {t} | synthetic value" for t in TARGETS),
                     "filing_index.tsv": "date_filed\tform_type\taccession\tpath\n2026-01-01\t10-Q\told\tfilings/10-Q_old.md\n",
                     "filings/10-Q_old.md": "synthetic revenue 100"}
            company = {"visible_root": str(root), "cutoff": "2026-02-01",
                       "target_accession": "hidden", "allowed_files": []}
            for name, text in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
                company["allowed_files"].append({"path": name, "bytes": len(text.encode()), "sha256": digest(text.encode())})
            ledger = root / "synthetic.sqlite3"
            initial = PilotBudget(ledger)
            initial.close()
            activate(ledger, "a" * 64, "b" * 40)
            original = FullBudget(ledger)
            baseline = history_snapshot(original.db)
            original.close()
            qa = root / "synthetic-qa.json"
            entry.durable_json(qa, {"synthetic_scoring_fixture": True})
            config = {"source_commit": "a" * 40, "ledger": str(ledger), "baseline": baseline,
                      "deadline_utc": "2099-10-13T15:03:10Z", "new_request_cutoff_utc": "2099-10-13T14:33:10Z",
                      "output": str(root / "attempts" / "run-001"), "model": "gpt-6.1-sol",
                      "qa": {"path": str(qa), "sha256": digest(qa.read_bytes())},
                      "runtime_config": {"max_input_tokens": 100000, "max_output_tokens": 25000,
                          "max_turns_per_company": 24, "company_wall_seconds": 1800, "request_timeout_seconds": 1200,
                          "models": {"gpt-6.1-sol": {"api_model": "gpt-6.1-sol", "effort": "xhigh",
                              "input": "2", "cached": "0.1", "write": "2.5", "output": "10"}}}}
            provider = Mock(timeout=1200)
            generations = []
            def post(endpoint, payload):
                if endpoint.endswith("input_tokens"):
                    return {"input_tokens": 100, "object": "response.input_tokens"}
                generations.append(payload)
                output = ([{"type": "function_call", "call_id": "test-read", "name": "read_file",
                           "arguments": json.dumps({"path": "filing_index.tsv", "offset": 0, "characters": 100})}]
                          if len(generations) == 1 else self.response(json.dumps(self.payload(1.5)))["output"])
                return {"status": "completed", "model": "gpt-6.1-sol", "service_tier": "default", "output": output,
                        "usage": {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110,
                                  "input_tokens_details": {"cached_tokens": 0}}}
            provider.post.side_effect = post
            scorer = Mock(return_value={"score_out_of_5": 0})
            # Only admission/source fixture and scoring are synthetic callbacks.
            # The original forecast, FilingTools, NightBudget and receipts execute.
            with patch.object(entry, "preflight", return_value=(company, TARGETS, scorer)), patch.object(entry, "ARCHIVE", root), patch.object(entry, "credential") as keys:
                result = entry.run_one(config, lambda: provider)
                self.assertEqual((result["status"], result["planned_targets"], result["scored_targets"]),
                                 ("COMPLETED_SCORED", 5, 5))
                keys.assert_not_called()
                before = {p.name: p.read_bytes() for p in Path(config["output"]).glob("*.json")}
                with self.assertRaises(FileExistsError):
                    entry.run_one(config, lambda: provider)
                self.assertEqual(before, {p.name: p.read_bytes() for p in Path(config["output"]).glob("*.json")})
            self.assertEqual(provider.post.call_count, 4)
            self.assertEqual(len(list(Path(config["output"]).glob("http-*.intent.json"))), 4)
            self.assertEqual(scorer.call_args.kwargs["predictions_payload"], self.payload(1.5))
            accounting = json.loads((Path(config["output"]) / "budget-summary.json").read_text())
            self.assertEqual(accounting["generation_requests_reserved"], 2)
            self.assertGreater(accounting["charged_upper_bound_usd"], 0)
            self.assertFalse(accounting["blocked"])

    def test_original_window_and_baseline_rebase_refuse_before_credentials(self):
        base = {"source_commit": "a" * 40, "baseline": entry.BASELINE,
                "deadline_utc": entry.DEADLINE, "new_request_cutoff_utc": entry.CUTOFF,
                "max_forecast_rollouts": 6}
        factory = Mock()
        for field, value in (("baseline", dict(entry.BASELINE, charged_nano_usd=0)),
                             ("deadline_utc", "2099-01-01T00:00:00Z"),
                             ("max_forecast_rollouts", 7)):
            with self.subTest(field=field), patch.object(entry, "credential") as keys:
                with self.assertRaises(ValueError):
                    entry.run_one(dict(base, **{field: value}), factory)
                keys.assert_not_called()
        factory.assert_not_called()

    def test_seventh_attempt_refuses_before_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for index in range(6):
                (root / "attempts" / str(index)).mkdir(parents=True)
            config = {"output": str(root / "attempts" / "seventh"),
                      "new_request_cutoff_utc": "2099-01-01T00:00:00Z"}
            factory = Mock()
            with patch.object(entry, "ARCHIVE", root), patch.object(entry, "preflight", return_value=({}, TARGETS, Mock())), patch.object(entry, "credential") as keys:
                with self.assertRaises(entry.BudgetStop):
                    entry.run_one(config, factory)
                keys.assert_not_called()
            factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
