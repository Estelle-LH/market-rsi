"""Implementation adapter fixtures; mock account only, no resident Train access."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import Mock, patch

from supervisor_harness import price_candidate_author as a

SOURCE = """import numpy as np
from sklearn.linear_model import Ridge
def fit_predict(x, y, weights, xc, history, check_history, *, seed):
    model = Ridge(alpha=10)
    model.fit(x, y, sample_weight=weights)
    return model.predict(xc)
"""
TEST = """import numpy as np
from candidate import fit_predict
def test_candidate():
    x = np.zeros((20, 13))
    y = np.zeros(20)
    xc = np.ones((2, 13))
    result = fit_predict(x, y, np.ones(20), xc, [[] for i in range(20)], [[], []], seed=314159)
    assert result.shape == (2,)
    assert np.isfinite(result).all()
if __name__ == '__main__':
    test_candidate()
"""


def synthetic_value(schema):
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    if schema["type"] == "object":
        return {k: synthetic_value(v) for k, v in schema["properties"].items()}
    if schema["type"] == "array":
        return [synthetic_value(schema["items"]) for _ in range(schema.get("minItems", 1))]
    return "SYNTHETIC-NOT-MODEL"


class SourceGuardTests(TestCase):
    def test_numeric_candidate_and_synthetic_test_not_imported(self):
        with patch("importlib.util.spec_from_file_location") as imported:
            self.assertTrue(a.validate_source(SOURCE)["passed"])
            self.assertTrue(a.validate_source(TEST, is_test=True)["passed"])
        self.assertFalse(imported.called)

    def test_closed_file_network_process_dynamic_and_private_paths(self):
        snippets = ("import os", "import subprocess", "from sklearn.datasets import fetch_openml",
            "import socket", "from pathlib import Path", "np.load('file')", "np.save('file', x)",
            "open('file')", "eval('x')", "getattr(np, 'load')", "np.__dict__", "globals()",
            "np.ctypeslib.load_library('x', 'y')", "np.random.default_rng(seed)")
        for text in snippets:
            with self.subTest(text=text), self.assertRaises(ValueError):
                a.validate_source(SOURCE.replace("    model = Ridge(alpha=10)", "    " + text))
        with self.assertRaises(ValueError):
            a.validate_source(SOURCE.replace("Ridge(alpha=10)", "Ridge(alpha=10, n_jobs=-1)"))

    def test_import_behavior_api_defaults_and_fake_test_invocation_rejected(self):
        bad = (SOURCE + "\nnp.zeros(2)\n", SOURCE.replace("*, seed", "*, seed=np.zeros(2)"),
            SOURCE.replace("check_history, *, seed", "check_labels, *, seed"),
            SOURCE.replace("def fit_predict", "@np.zeros(1)\ndef fit_predict"),
            SOURCE.replace("import numpy as np", "from numpy import *"))
        for source in bad:
            with self.subTest(source=source), self.assertRaises(ValueError):
                a.validate_source(source)
        with self.assertRaises(ValueError):
            a.validate_source(TEST.split("if __name__")[0], is_test=True)

    def test_sources_cannot_exceed_payload_bounds(self):
        with self.assertRaises(ValueError):
            a.validate_source("#" * 24577)

    def test_numeric_all_any_and_test_only_literal_object_dtype(self):
        reduction = SOURCE.replace("    model = Ridge(alpha=10)", "    assert np.all(np.isfinite(x)) or np.any(x == 0)\n    model = Ridge(alpha=10)")
        self.assertTrue(a.validate_source(reduction)["passed"])
        typed_test = TEST.replace("np.zeros((20, 13))", "np.zeros((20, 13), dtype=object)")
        self.assertTrue(a.validate_source(typed_test, is_test=True)["passed"])
        for source, is_test in ((SOURCE.replace("Ridge(alpha=10)", "object()"), False),
                (SOURCE.replace("model = Ridge(alpha=10)", "model = np.zeros((2, 13), dtype=object)"), False),
                (TEST.replace("np.zeros((20, 13))", "np.zeros((20, 13), dtype=object())"), True),
                (TEST.replace("np.zeros((20, 13))", "np.zeros((20, 13), dtype=type)"), True),
                (TEST.replace("np.zeros((20, 13))", "np.asarray(object)"), True)):
            with self.subTest(source=source), self.assertRaises(ValueError):
                a.validate_source(source, is_test=is_test)

    def test_actual_preserved_completed_author_response_ast(self):
        path = Path('/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/market-rsi-price-auto-loop-20261006-01/role_calls/author/author-r0001-64dda21a4401/response.json')
        if not path.exists(): self.skipTest('immutable local completed-author evidence not installed')
        self.assertEqual(a.h.w.sha(path), '9c4a41d8495ebfd4a4739d1c682192e1d97ff7da3f52a6b2d600e1858f8ad2a5')
        response = json.loads(path.read_text())
        self.assertEqual(a.validate_source(response['candidate_source'])['ast_nodes'], 422)
        self.assertEqual(a.validate_source(response['test_source'], is_test=True)['ast_nodes'], 813)

    def test_actual_preserved_round2_completed_author_response_ast(self):
        path = Path('/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/market-rsi-price-auto-loop-20261006-01/role_calls/author/author-r0002-5918dea0ccc1/response.json')
        if not path.exists(): self.skipTest('immutable local completed-author evidence not installed')
        self.assertEqual(a.h.w.sha(path), '329a34d10076a2eb40bad763bad95bb813bd9a5ed6f23c3c0f9f3f6d54caf2cd')
        response = json.loads(path.read_text())
        self.assertEqual(a.validate_source(response['candidate_source'])['ast_nodes'], 608)
        self.assertEqual(a.validate_source(response['test_source'], is_test=True)['ast_nodes'], 1266)


class AuthorServiceTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()
        self.repo = self.directory / "repo"; self.repo.mkdir()
        self.root = self.directory / "permanent-fixture"; self.root.mkdir()
        for command in (["git", "init", "-q"], ["git", "config", "user.name", "SyntheticFixture"],
                        ["git", "config", "user.email", "fixture@invalid.test"]):
            subprocess.run(command, cwd=self.repo, check=True, capture_output=True)
        self.fixed = self.repo / "fixed.py"; self.fixed.write_text("# inert protected fixture\n")
        subprocess.run(["git", "add", "fixed.py"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "synthetic starting point"], cwd=self.repo, check=True, capture_output=True)
        self.runtime = SimpleNamespace(root=self.root, repo=self.repo,
            fixed_grant={"batch_id": "SYNTHETIC-AUTHOR-FIXTURE"}, admit=Mock(return_value=True))
        self.decision = synthetic_value(a.h.t.SCHEMA)
        self.decision["candidate"].update(candidate_id="SyntheticRidge-v1", recipe="Fit one Ridge alpha10; no invented science")
        self.digest = a.h.t.c._digest(self.decision)
        a.h.w.save(self.root / "ledger.json", {"controller_decisions": [{"status": "completed", "decision_sha256": self.digest}]})
        previous = {}
        for role in ("feedback", "memory", "source_context"):
            a.h.w.save(self.root / (role + ".json"), {"synthetic": True, "role": role})
            previous[role] = a.h.r.pin(self.root / (role + ".json"))
        self.ctx = {"round_index": 1, "previous_result": previous, "outputs": {"controller": {"decision": self.decision}}}
        self.calls = []
        self.call = Mock(side_effect=self.transport)
        a.h.w.save(self.root / 'synthetic-role-grant.json', {'account_roles': {'max_input_bytes': 32768}})
        self.author = a.CandidateAuthor(self.runtime, {"fixed.py": a.h.w.sha(self.fixed)},
            a.h.r.pin(self.root / 'synthetic-role-grant.json'), role_call=self.call)

    def transport(self, role, packet, schema, **keywords):
        self.calls.append((role, deepcopy(packet), keywords))
        response = {"candidate_id": self.decision["candidate"]["candidate_id"], "decision_sha256": self.digest,
            "method_family": "synthetic-ridge", "candidate_source": SOURCE, "test_source": TEST,
            "implementation_notes": "Implements synthetic recipe only; no scientific claim"}
        return {"response": response, "call_id": "SYNTHETIC-NOT-ACCOUNT", "usage": {}, "serving_snapshot": "unknown"}

    def test_original_recipe_versioned_source_and_static_checks_then_independent_review(self):
        before = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
        with patch("importlib.util.spec_from_file_location") as imported:
            authored = self.author.author(self.ctx)
        self.assertFalse(imported.called)
        self.assertEqual(set(authored), {"candidate_binding", "source_commit", "files", "method_family"})
        self.assertNotEqual(authored["source_commit"], before)
        self.assertEqual(self.calls[0][1]["original_controller_decision"], self.decision)
        candidate = Path(authored["candidate_binding"]["path"])
        receipt = json.loads((candidate.parent / "author_receipt.json").read_text())
        self.assertFalse(receipt["generated_tests_executed"])
        self.assertTrue(receipt["awaiting_independent_source_review"])
        self.assertEqual(receipt["original_decision_sha256"], self.digest)
        self.assertTrue((candidate.parent / "test_candidate.py").exists())
        for path, digest in authored["files"].items():
            original = subprocess.check_output(["git", "show", authored["source_commit"] + ":" + path], cwd=self.repo)
            self.assertEqual(a.h.t.c.hashlib.sha256(original).hexdigest(), digest)
        with self.assertRaises(FileExistsError):
            self.author.author(self.ctx)
        self.assertEqual(len(self.calls), 1)

    def test_author_larger_context_is_supported_by_its_bound_role_budget(self):
        a.h.w.save(self.root / 'larger-role-grant.json', {'account_roles': {'max_input_bytes': 262144}})
        self.author.grant = a.h.r.pin(self.root / 'larger-role-grant.json')
        a.h.w.save(self.root / 'large-memory.json', {'synthetic_memory': 'x' * 40000})
        self.ctx['previous_result']['memory'] = a.h.r.pin(self.root / 'large-memory.json')
        authored = self.author.author(self.ctx)
        self.assertTrue(Path(authored['candidate_binding']['path']).exists())
        self.assertGreater(len(json.dumps(self.calls[0][1]).encode()), 32768)
        self.assertEqual(len(self.calls), 1)  # Mock role, no actual model.

    def test_typed_original_author_consumes_actual_hook_context_without_legacy_rewrap(self):
        from supervisor_harness.test_coevo_pilot_transaction import TypedActionTests
        fixture = TypedActionTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        fixture.action = 'prediction'
        fixture.packet['source_context'] = {'capacity_hook_outputs': {'verified_synthetic_finding': 'avoid repeated recipe'}}
        fixture.packet['bindings']['source_context'] = fixture.h.write('typed-source', fixture.packet['source_context'])
        fixture.bind(); decision = fixture.h.call()
        self.decision, self.digest = decision, a.h.t.c._digest(decision)
        self.runtime.root = fixture.h.root
        self.runtime.fixed_grant = fixture.h.authorization
        self.runtime.authority, self.runtime.configuration = fixture.h.authorization_binding, fixture.h.configuration_binding
        self.ctx['outputs'] = {'controller': {'decision': decision}, 'input': {
            'input': fixture.h.input_binding, 'authorization': self.runtime.authority,
            'configuration': self.runtime.configuration, 'review': fixture.h.review_binding}}
        self.author.author(self.ctx)
        self.assertEqual(self.calls[0][1]['original_controller_decision'], decision)
        self.assertEqual(self.calls[0][1]['context']['source_context'], fixture.packet['source_context'])
        self.assertEqual(fixture.h.calls, 1)

    def test_typed_author_rejects_substituted_input_before_account_call(self):
        from supervisor_harness.test_coevo_pilot_transaction import TypedActionTests
        fixture = TypedActionTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        fixture.action = 'prediction'; fixture.bind(); decision = fixture.h.call()
        self.runtime.root = fixture.h.root
        self.runtime.fixed_grant = fixture.h.authorization
        self.runtime.authority, self.runtime.configuration = fixture.h.authorization_binding, fixture.h.configuration_binding
        substituted = fixture.h.write('substituted-input', fixture.packet)
        self.ctx['outputs'] = {'controller': {'decision': decision}, 'input': {
            'input': substituted, 'authorization': self.runtime.authority,
            'configuration': self.runtime.configuration, 'review': fixture.h.review_binding}}
        with self.assertRaisesRegex(ValueError, 'input/authority/configuration'): self.author.author(self.ctx)
        self.assertFalse(self.call.called)

    def test_author_old_32k_budget_rejects_large_context_without_role_call(self):
        a.h.w.save(self.root / 'large-memory.json', {'synthetic_memory': 'x' * 40000})
        self.ctx['previous_result']['memory'] = a.h.r.pin(self.root / 'large-memory.json')
        with self.assertRaisesRegex(ValueError, 'input byte budget'): self.author.author(self.ctx)
        self.assertFalse(self.call.called)

    def test_unsafe_original_response_preserved_failure_never_imported_or_retried(self):
        original = self.transport
        def unsafe(*args, **kwargs):
            result = original(*args, **kwargs)
            result["response"]["candidate_source"] = SOURCE + "\nimport os\n"
            return result
        self.call.side_effect = unsafe
        with self.assertRaises(ValueError):
            self.author.author(self.ctx)
        failure = json.loads(next(self.root.glob("author-*/failure.json")).read_text())
        self.assertFalse(failure["retry_allowed"])
        self.assertFalse(failure["scientific_evidence"])
        with self.assertRaises(FileExistsError):
            self.author.author(self.ctx)
        self.assertEqual(len(self.calls), 1)

    def test_uncertain_transport_and_generated_method_family_failure_are_durable(self):
        self.call.side_effect = RuntimeError("synthetic uncertain completion")
        with self.assertRaises(RuntimeError):
            self.author.author(self.ctx)
        with self.assertRaises(FileExistsError):
            self.author.author(self.ctx)
        self.assertEqual(self.call.call_count, 1)

    def test_closed_admission_unbound_original_wrong_types_and_source_drift_before_call(self):
        self.runtime.admit.return_value = False
        with self.assertRaises(ValueError): self.author.author(self.ctx)
        self.runtime.admit.return_value = True
        wrong = deepcopy(self.ctx); wrong["round_index"] = True
        with self.assertRaises(ValueError): self.author.author(wrong)
        self.fixed.write_text("# drift\n")
        with self.assertRaises(ValueError): self.author.author(self.ctx)
        self.assertFalse(self.call.called)


class CompletedAuthorRecoveryTests(AuthorServiceTests):
    def recovery_fixture(self, *, round_index=1):
        self.ctx['round_index'] = round_index
        self.original_id = f"author-r{round_index:04d}-" + self.digest[:12]
        role = self.root / "role_calls/author" / self.original_id
        role.mkdir(parents=True)
        original = self.transport
        def completed(role_name, packet, schema, **keywords):
            result = original(role_name, packet, schema, **keywords)
            a.h.w.save(role / "input.json", {"role": "author", "role_id": self.original_id, "payload": packet})
            a.h.w.save(role / "response.json", result["response"])
            a.h.w.save(role / "completion.json", {"exit_code": 0, "timed_out": False,
                "hashes": {"response.json": a.h.w.sha(role / "response.json")}})
            result.update(input_binding=a.h.r.pin(role / "input.json"), response_binding=a.h.r.pin(role / "response.json"),
                completion_binding=a.h.r.pin(role / "completion.json"), call_id=self.original_id)
            self.completed_result, self.original_packet = result, deepcopy(packet)
            return result
        self.call.side_effect = completed
        with patch.object(a, "validate_source", side_effect=ValueError("non-numeric NumPy call")), self.assertRaises(ValueError):
            self.author.author(self.ctx)
        failure = a.h.r.pin(self.root / self.original_id / "failure.json")
        completion = a.h.r.pin(role / "completion.json")
        a.h.w.save(self.root / "independent-admission-review.json", {"passed": True,
            "author_source_sha256": a.h.w.sha(a.__file__), "original_failure_sha256": failure["sha256"],
            "original_completion_sha256": completion["sha256"], "original_decision_sha256": self.digest})
        recovery = {"schema": "price_completed_author_admission_recovery_v1", "round_index": round_index,
            "original_decision_sha256": self.digest, "original_author_id": self.original_id,
            "fresh_local_id": self.original_id + {1: '-admission-v2', 2: '-admission-v3'}[round_index], "original_failure": failure,
            "original_input": a.h.r.pin(role / "input.json"), "original_response": a.h.r.pin(role / "response.json"),
            "original_completion": completion, "review": a.h.r.pin(self.root / "independent-admission-review.json")}
        a.h.w.save(self.root / "admission-recovery.json", recovery)
        self.author.recovery = a.h.r.pin(self.root / "admission-recovery.json")
        def replay(role_name, packet, schema, **keywords):
            self.assertEqual(keywords["role_id"], self.original_id)
            self.assertEqual(packet, self.original_packet)
            return self.completed_result
        self.call.side_effect = replay
        return recovery

    def test_completed_response_consumed_with_fresh_local_id_without_second_sampling(self):
        recovery = self.recovery_fixture()
        failure_before = Path(recovery["original_failure"]["path"]).read_bytes()
        authored = self.author.author(self.ctx)
        self.assertIn(self.original_id + "-admission-v2", authored["candidate_binding"]["path"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(Path(recovery["original_failure"]["path"]).read_bytes(), failure_before)
        receipt = json.loads((Path(authored["candidate_binding"]["path"]).parent / "author_receipt.json").read_text())
        self.assertEqual(receipt["role_call"]["call_id"], self.original_id)
        with self.assertRaises(FileExistsError): self.author.author(self.ctx)
        self.assertEqual(len(self.calls), 1)

    def test_round2_completed_recovery_is_distinct_and_rejects_wrong_round(self):
        recovery = self.recovery_fixture(round_index=2)
        failure_before = Path(recovery["original_failure"]["path"]).read_bytes()
        source = self.repo / "research/market_rsi/experiments/price_candidates" / self.runtime.fixed_grant["batch_id"] / self.original_id
        with self.assertRaises(ValueError):
            a._completed_recovery(self.runtime, self.author.recovery, self.digest, self.original_id, source, round_index=1)
        authored = self.author.author(self.ctx)
        self.assertIn('author-r0002-', authored['candidate_binding']['path'])
        self.assertIn('-admission-v3', authored['candidate_binding']['path'])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(Path(recovery["original_failure"]["path"]).read_bytes(), failure_before)
        receipt = json.loads((Path(authored["candidate_binding"]["path"]).parent / "author_receipt.json").read_text())
        self.assertEqual(receipt["role_call"]["call_id"], self.original_id)
        with self.assertRaises(FileExistsError): self.author.author(self.ctx)
        self.assertEqual(len(self.calls), 1)

    def test_missing_completion_rejects_before_replay(self):
        recovery = self.recovery_fixture()
        Path(recovery["original_completion"]["path"]).unlink()
        self.call.reset_mock()
        with self.assertRaises(FileNotFoundError): self.author.author(self.ctx)
        self.assertFalse(self.call.called)

    def test_recovery_rejects_different_decision_review_or_existing_source(self):
        recovery = self.recovery_fixture()
        source = self.repo / "research/market_rsi/experiments/price_candidates" / self.runtime.fixed_grant["batch_id"] / self.original_id
        for changed in ({**recovery, "round_index": 2}, {**recovery, "original_decision_sha256": "f" * 64},
                {**recovery, "fresh_local_id": "arbitrary-retry"}):
            path = self.root / (a.h.t.c._digest(changed) + ".json")
            a.h.w.save(path, changed)
            with self.assertRaises(ValueError):
                a._completed_recovery(self.runtime, a.h.r.pin(path), self.digest, self.original_id, source)
        source.mkdir(parents=True)
        with self.assertRaises(ValueError): self.author.author(self.ctx)

    def test_unrelated_staged_source_blocks_checkpoint_without_committing_it(self):
        other = self.repo / "user.py"; other.write_text("# unrelated work\n")
        subprocess.run(["git", "add", "user.py"], cwd=self.repo, check=True)
        before = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True)
        with self.assertRaisesRegex(ValueError, "unrelated staged"):
            self.author.author(self.ctx)
        after = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True)
        self.assertEqual(before, after)
        self.assertEqual(subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=self.repo, text=True).strip(), "user.py")
        self.assertFalse(self.call.called)


if __name__ == "__main__": main()
