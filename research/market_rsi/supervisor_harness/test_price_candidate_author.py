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
        self.author = a.CandidateAuthor(self.runtime, {"fixed.py": a.h.w.sha(self.fixed)}, {"synthetic": True}, role_call=self.call)

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
