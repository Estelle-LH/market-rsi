"""Real native journals with synthetic immutable modules; no Train/model calls."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from market_rsi import digest
from data_scientist_harness import co_evolution_loop as micro
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
from supervisor_harness import research_capacity_activation as activation
from supervisor_harness import research_capacity_identity as identity

BASE = datetime(2026, 10, 6, 19, 30, tzinfo=timezone.utc)


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class CapacityActivationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.files = {
            "kernel.py": "pass\n", "candidate.py": "pass\n", "python": "synthetic-runtime\n",
            "researcher_v1.py": "def choose(history):\n    return 'a'\n",
            "researcher_v2.py": "def choose(history):\n    return next((x for x in ('a','b') if x not in history), 'stop')\n",
            "harness_v1.py": "def deliver(feedback):\n    return {'score': feedback['score']}\n",
            "harness_v2.py": "def deliver(feedback):\n    return dict(feedback)\n",
        }
        for name, text in self.files.items():
            (self.root / name).write_text(text, encoding="utf-8")
        binding = lambda name: {"sources": {name: sha(self.files[name])},
                                "configuration_sha256": sha("frozen-config")}
        self.args = dict(kernel=binding("kernel.py"), predictor=binding("candidate.py"),
            harness=binding("harness_v1.py"), researcher=binding("researcher_v1.py"), memory=sha("initial-memory"),
            model={"requested_model": "gpt-6.1-sol", "serving_snapshot": "unknown", "serving_snapshot_verified": False},
            runtime={"python": {"path": str(self.root / "python"), "sha256": sha(self.files["python"])}, "dependencies": {}})
        self.before = identity.manifest(**self.args)
        self.entry = {"R": "researcher_v1.py", "H": "harness_v1.py"}
        self.batch = ContinuousDiscoveryBatch(self.root / "batch", allow_temporary=True,
            test_clock=lambda: BASE, allow_test_clock=True)
        self.batch.initialize(batch_id="capacity-code-only", start_utc=BASE,
            deadline_utc=BASE + timedelta(hours=1), max_attempts=3, active_pool_capacity=2,
            learning_checkpoint_version=1,
            initial_incumbent={"candidate_id": "market", "candidate_sha256": self.before["C"],
                "scorecard_sha256": sha("market-card"), "review_sha256": "0" * 64})
        self.config = {"pair": activation.pair(self.before),
            "fixed_context": {"model_sha256": self.before["M"], "evaluation_sha256": self.before["K"],
                "data_scope_sha256": sha("Train-only"), "authority_sha256": sha("code-only"),
                "resource_policy_sha256": sha("no-live-budget")},
            "allowed_write_paths": {"researcher": ["researcher_v1.py", "researcher_v2.py"],
                                    "harness": ["harness_v1.py", "harness_v2.py"]},
            "protected_paths": ["kernel.py", "candidate.py", "python"], "reviewer_id": "independent-auditor"}
        self.batch.record_micro_evolution("initialize", self.config,
            expected_state_sha256=self.batch.snapshot()["state_sha256"])
        self.adapter = self.restore()
        self.count = 0

    def restore(self):
        return activation.CapacityActivation(self.batch, source_root=self.root,
            registry_root=self.root / "versions", baseline=self.before, entrypoints=self.entry)

    def artifact(self, value, label="receipt"):
        self.count += 1
        location = self.root / f"{label}-{self.count}.json"
        data = json.dumps(value, sort_keys=True).encode()
        with location.open("xb") as stream:
            stream.write(data)
        return {"path": str(location), "sha256": hashlib.sha256(data).hexdigest()}

    def propose(self, axis, before=None):
        before = before or self.before
        args = deepcopy(self.args)
        args["harness"] = before["components"]["H"]
        args["researcher"] = before["components"]["R"]
        kind = {"H": "harness", "R": "researcher"}[axis]
        name = kind + "_v2.py"
        args[kind] = {"sources": {name: sha(self.files[name])}, "configuration_sha256": sha("frozen-config")}
        after = identity.manifest(**args)
        entries = {"H": next(iter(after["components"]["H"]["sources"])),
                   "R": next(iter(after["components"]["R"]["sources"]))}
        state = self.batch.snapshot()
        proposal = {"candidate_id": f"{axis}-v2", "proposer_id": "agent-proposer", "axis": kind,
            "component": "research_policy" if axis == "R" else "feedback_delivery",
            "behavior_change": "Avoid repeated failure" if axis == "R" else "Preserve feedback causal identity",
            "problem_evidence_sha256": sha("actual-observed-problem"),
            "parent_pair_sha256": micro.micro_pair_hash(state["micro_evolution"]),
            "pair": activation.pair(after), "fixed_context": self.config["fixed_context"],
            "write_paths": list(before["components"][axis]["sources"]) + [name],
            "patch_sha256": activation.patch_digest(before, after)}
        scope = self.artifact({"passed": True, "reviewer_id": "independent-auditor",
            "proposer_id": proposal["proposer_id"], "identity_sha256": digest(after), "entrypoints": entries})
        self.adapter.propose(after, proposal, entries, static_review=scope,
            expected_state_sha256=state["state_sha256"])
        return before, after

    def review_receipt(self, before, after, *, accept=True, benefit=True, drift=False):
        state = self.batch.snapshot()
        pending = state["micro_evolution"]["pending"]
        fixtures = {"success": ["a"], "failure": ["a"], "restart": ["a"], "historical_replay": ["a", "b"]}
        active_hash = digest(state["micro_evolution"]["active_pair"])
        axis = "R" if pending["axis"] == "researcher" else "H"
        old = self.adapter.resolve(axis, expected_pair_sha256=active_hash)
        new = self.adapter.resolve(axis, expected_pair_sha256=active_hash,
            shadow_proposal_sha256=pending["record_sha256"])
        outputs = {}
        for name, history in fixtures.items():
            if axis == "R":
                outputs[name] = {"before": old.choose(history), "after": new.choose(history),
                    "benefit": old.choose(history) in history and new.choose(history) not in history}
            else:
                feedback = {"score": None if name == "failure" else .5, "parent_id": "revert-parent", "cause": name}
                outputs[name] = {"before": old.deliver(feedback), "after": new.deliver(feedback),
                    "benefit": old.deliver(feedback) != feedback and new.deliver(feedback) == feedback}
        self.assertTrue(all(output["benefit"] for output in outputs.values()))
        evidence = self.artifact({"fixtures": outputs, "synthetic": True, "evidence_level": "L2",
            "binding": {"proposal_sha256":pending["record_sha256"], "before_identity_sha256":digest(before),
                "after_identity_sha256":digest(after), "tested_pair_sha256":digest(pending["pair"]),
                "anchor_pair_sha256":digest(state["micro_evolution"]["anchor_pair"])},
            "checks":{name:True for name in micro.MICRO_CHECKS}})
        measured = self.artifact({"proposal_sha256": pending["record_sha256"],
            "before_identity_sha256": digest(before), "after_identity_sha256": digest(after) if not drift else sha("wrong"),
            "benefit_observed": benefit, "effect": pending["behavior_change"], "matched_outputs_sha256": evidence["sha256"]})
        review = {"reviewer_id": "independent-auditor", "proposal_sha256": pending["record_sha256"],
            "decision": "accept" if accept else "reject", "reason": "Matched synthetic behavior verified",
            "tested_pair_sha256": digest(pending["pair"]), "anchor_pair_sha256": digest(state["micro_evolution"]["anchor_pair"]),
            "checks": {key: {"passed": True, "evidence_sha256": evidence["sha256"]} for key in micro.MICRO_CHECKS},
            "benefit_observed": benefit, "benefit_evidence_sha256": measured["sha256"],
            "actual_write_paths": pending["write_paths"]}
        return self.artifact({"review": review, "evidence": {evidence["sha256"]: evidence["path"],
            measured["sha256"]: measured["path"]}})

    def test_researcher_then_harness_accept_and_downstream_restart(self):
        old, r_new = self.propose("R")
        self.assertEqual(self.adapter.resolve("R", expected_pair_sha256=digest(activation.pair(old))).choose(["a"]), "a")
        review = self.review_receipt(old, r_new)
        self.adapter.review(review, expected_state_sha256=self.batch.snapshot()["state_sha256"])
        self.assertEqual(self.restore().resolve("R", expected_pair_sha256=digest(activation.pair(r_new))).choose(["a"]), "b")
        self.assertEqual(r_new["H"], old["H"])
        _, h_new = self.propose("H", r_new)
        review = self.review_receipt(r_new, h_new)
        self.adapter.review(review, expected_state_sha256=self.batch.snapshot()["state_sha256"])
        self.assertEqual(h_new["R"], r_new["R"])
        module = self.restore().resolve("H", expected_pair_sha256=digest(activation.pair(h_new)))
        self.assertEqual(module.deliver({"score": .5, "parent_id": "p"}), {"score": .5, "parent_id": "p"})
        state = self.batch.snapshot()
        replay = self.artifact({"passed":True, "from_pair":state["micro_evolution"]["active_pair"],
            "to_pair":state["micro_evolution"]["previous_pair"], "before_state_sha256":state["state_sha256"]})
        rollback = self.artifact({"receipt":{"reviewer_id": "independent-auditor", "reason": "Replay rollback",
            "evidence_sha256":replay["sha256"]}, "evidence":replay})
        self.adapter.rollback(rollback, expected_state_sha256=state["state_sha256"])
        restored = self.restore().resolve("H", expected_pair_sha256=digest(activation.pair(r_new)))
        self.assertEqual(restored.deliver({"score": .5, "parent_id": "p"}), {"score": .5})
        self.assertEqual(len(self.batch.snapshot()["micro_evolution"]["history"]), 3)

    def test_reject_preserves_parent_and_history(self):
        old, after = self.propose("R")
        receipt = self.review_receipt(old, after, accept=False, benefit=False)
        self.adapter.review(receipt, expected_state_sha256=self.batch.snapshot()["state_sha256"])
        self.assertEqual(self.batch.snapshot()["micro_evolution"]["active_pair"], activation.pair(old))
        self.assertEqual(self.restore().resolve("R", expected_pair_sha256=digest(activation.pair(old))).choose(["a"]), "a")
        self.assertEqual(len(self.batch.snapshot()["micro_evolution"]["history"]), 1)

    def test_missing_benefit_and_mismatch_cannot_accept(self):
        old, after = self.propose("R")
        for kwargs in ({"benefit": False}, {"drift": True}):
            receipt = self.review_receipt(old, after, **kwargs)
            with self.assertRaises(ValueError):
                self.adapter.review(receipt, expected_state_sha256=self.batch.snapshot()["state_sha256"])
            self.assertEqual(self.batch.snapshot()["micro_evolution"]["active_pair"], activation.pair(old))

    def test_unrelated_check_evidence_and_unread_matched_output_cannot_accept(self):
        old, after = self.propose("R")
        for field in ("proposal_sha256", "before_identity_sha256", "after_identity_sha256",
                      "tested_pair_sha256", "anchor_pair_sha256", "matched_outputs_sha256"):
            original = self.review_receipt(old, after)
            envelope = json.loads(Path(original["path"]).read_text())
            token = envelope["review"]["benefit_evidence_sha256"]
            benefit = json.loads(Path(envelope["evidence"][token]).read_text())
            if field == "matched_outputs_sha256":
                benefit[field] = sha("not-read-or-present")
            else:
                source = next(iter(envelope["review"]["checks"].values()))["evidence_sha256"]
                evidence = json.loads(Path(envelope["evidence"][source]).read_text())
                evidence["binding"][field] = sha("wrong-identity")
                bad = self.artifact(evidence)
                envelope["evidence"][bad["sha256"]] = bad["path"]
                for check in envelope["review"]["checks"].values():
                    check["evidence_sha256"] = bad["sha256"]
                benefit["matched_outputs_sha256"] = bad["sha256"]
            bad = self.artifact(benefit)
            envelope["evidence"][bad["sha256"]] = bad["path"]
            envelope["review"]["benefit_evidence_sha256"] = bad["sha256"]
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.adapter.review(self.artifact(envelope), expected_state_sha256=self.batch.snapshot()["state_sha256"])
            self.assertEqual(self.batch.snapshot()["micro_evolution"]["active_pair"], activation.pair(old))

    def test_rollback_requires_exact_actual_evidence(self):
        old, after = self.propose("R")
        self.adapter.review(self.review_receipt(old, after), expected_state_sha256=self.batch.snapshot()["state_sha256"])
        state = self.batch.snapshot()
        evidence = self.artifact({"passed":True, "from_pair":activation.pair(old),
            "to_pair":activation.pair(old), "before_state_sha256":state["state_sha256"]})
        value = {"receipt":{"reviewer_id":"independent-auditor", "reason":"wrong from-pair",
            "evidence_sha256":evidence["sha256"]}, "evidence":evidence}
        with self.assertRaises(ValueError):
            self.adapter.rollback(self.artifact(value), expected_state_sha256=state["state_sha256"])
        with self.assertRaises(ValueError):
            self.adapter.rollback(self.artifact(value["receipt"]), expected_state_sha256=state["state_sha256"])
        self.assertEqual(self.batch.snapshot()["micro_evolution"]["active_pair"], activation.pair(after))

    def test_drift_stale_snapshot_pair_and_active_execution_block(self):
        old, after = self.propose("R")
        receipt = self.review_receipt(old, after)
        state = self.batch.snapshot()
        active = deepcopy(state)
        active["active_attempt_ids"] = ["running"]
        with mock.patch.object(self.batch, "snapshot", return_value=active), self.assertRaises(ValueError):
            self.adapter.review(receipt, expected_state_sha256=state["state_sha256"])
        active["active_attempt_ids"] = []
        active["branches"] = [{"stage": "implementation_ready"}]
        with mock.patch.object(self.batch, "snapshot", return_value=active), self.assertRaises(ValueError):
            self.adapter.review(receipt, expected_state_sha256=state["state_sha256"])
        with self.assertRaises(ValueError):
            self.adapter.review(receipt, expected_state_sha256=sha("stale"))
        with self.assertRaises(ValueError):
            self.adapter.resolve("R", expected_pair_sha256=digest(activation.pair(after)))
        (self.root / "researcher_v2.py").write_text("raise RuntimeError('must not execute')\n")
        with self.assertRaises(ValueError):
            self.adapter.review(receipt, expected_state_sha256=state["state_sha256"])

    def test_unreviewed_shadow_and_registry_tamper_rejected(self):
        old, after = self.propose("R")
        state = self.batch.snapshot()
        with self.assertRaises(ValueError):
            self.adapter.resolve("R", expected_pair_sha256=digest(activation.pair(old)), shadow_proposal_sha256=sha("wrong"))
        target = self.root / "versions" / (digest(activation.pair(after)) + ".json")
        body = json.loads(target.read_text())
        body["static_review"] = None
        target.write_text(json.dumps(body))
        with self.assertRaises(ValueError):
            self.adapter.resolve("R", expected_pair_sha256=digest(activation.pair(old)),
                shadow_proposal_sha256=state["micro_evolution"]["pending"]["record_sha256"])

    def test_runtime_alias_preserved_but_source_symlink_blocked(self):
        (self.root / "python-alias").symlink_to("python")
        alias = {"path": str(self.root / "python-alias"), "sha256": sha(self.files["python"])}
        self.assertEqual(activation._read(alias, allow_alias=True).decode(), self.files["python"])
        with self.assertRaises(ValueError):
            activation._read(alias)

    def test_static_review_before_shadow_proposal_and_exact_delta(self):
        old, after = self.propose("R")
        state = self.batch.snapshot()
        pending = state["micro_evolution"]["pending"]
        target = self.root / "versions" / (digest(activation.pair(after)) + ".json")
        body = json.loads(target.read_text())
        static = Path(body["static_review"]["path"])
        static.write_text(json.dumps({"passed": False}))
        with self.assertRaises(ValueError):
            self.adapter.resolve("R", expected_pair_sha256=digest(activation.pair(old)),
                shadow_proposal_sha256=pending["record_sha256"])

    def test_drifted_scope_wrong_measured_paths_and_self_review(self):
        state = self.batch.snapshot()
        after = deepcopy(self.before)
        args = deepcopy(self.args)
        args["researcher"]["sources"] = {"researcher_v2.py": sha(self.files["researcher_v2.py"])}
        after = identity.manifest(**args)
        entries = dict(self.entry, R="researcher_v2.py")
        proposal = {"candidate_id": "R-unreviewed", "proposer_id": "agent-proposer", "axis": "researcher",
            "component": "research_policy", "behavior_change": "Avoid failure",
            "problem_evidence_sha256": sha("problem"), "parent_pair_sha256": micro.micro_pair_hash(state["micro_evolution"]),
            "pair": activation.pair(after), "fixed_context": self.config["fixed_context"],
            "write_paths": ["researcher_v2.py"], "patch_sha256": activation.patch_digest(self.before, after)}
        review = self.artifact({"passed": True, "reviewer_id": "agent-proposer", "proposer_id": "agent-proposer",
            "identity_sha256": digest(after), "entrypoints": entries})
        with self.assertRaises(ValueError):
            self.adapter.propose(after, proposal, entries, static_review=review, expected_state_sha256=state["state_sha256"])
        proposal["write_paths"].append("researcher_v1.py")
        with self.assertRaises(ValueError):
            self.adapter.propose(after, proposal, entries, static_review=review, expected_state_sha256=state["state_sha256"])
        self.assertIsNone(self.batch.snapshot()["micro_evolution"]["pending"])


if __name__ == "__main__":
    unittest.main()
