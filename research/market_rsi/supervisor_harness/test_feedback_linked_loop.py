"""Synthetic handoff/forecast fixtures, not model authorship or Train results."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from supervisor_harness import feedback_linked_loop as loop


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.root = self.directory / "loop"
        self.seed = {"forecast": 0.8, "label": 0, "status": "seed"}
        self.identities = {stage: {"trusted_handler": stage, "version": 1} for stage in loop.STAGES}
        self.calls = []
        self.handlers = {stage: self.handler(stage) for stage in loop.STAGES}
        self.admit = lambda context: True

    def handler(self, stage):
        def actual(context):
            self.calls.append((context["round_index"], stage))
            if stage == "input":
                return {"feedback": context["previous_result"]}
            if stage == "controller":
                feedback = context["outputs"]["input"]["feedback"]
                # Negative first result changes the actual next prediction.
                forecast = 0.1 if feedback.get("status") == "REVERT" else 0.8
                return {"forecast": forecast, "received": feedback}
            if stage == "implement":
                return {"forecast": context["outputs"]["controller"]["forecast"]}
            if stage == "execute":
                forecast = context["outputs"]["implement"]["forecast"]
                return {"predictions": [forecast], "brier": forecast ** 2, "status": "succeeded"}
            if stage == "reconcile":
                result = context["outputs"]["execute"]
                return {**result, "status": "REVERT" if result["brier"] > .1 else "KEEP"}
            return {"passed": True}
        return actual

    def run_loop(self, max_rounds=2):
        return loop.run(self.root, self.handlers, seed=self.seed, admit=self.admit,
            max_rounds=max_rounds, handler_identity=lambda: deepcopy(self.identities))

    def test_actual_synthetic_predictions_follow_negative_feedback(self):
        result = self.run_loop()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["completed_rounds"], 2)
        self.assertEqual(self.calls, [(n, stage) for n in (1, 2) for stage in loop.STAGES])
        first = loop._read_pair(self.root / "round-0001-reconcile.done.json")["output"]
        second = loop._read_pair(self.root / "round-0002-input.done.json")["output"]
        self.assertEqual(first["status"], "REVERT")
        self.assertEqual(second["feedback"], first)
        self.assertEqual(result["result"]["predictions"], [.1])
        self.assertLess(result["result"]["brier"], first["brier"])
        claim = loop.c._json((self.root / "round-0002-input.claim.json").read_bytes())
        self.assertEqual(claim["previous_feedback_sha256"], loop.c._digest(first))

    def test_completed_restart_has_no_callback_or_duplicate(self):
        result = self.run_loop()
        self.calls.clear()
        self.assertEqual(self.run_loop(), result)
        self.assertEqual(self.calls, [])

    def test_completed_replay_allowed_after_authority_closed(self):
        result = self.run_loop()
        self.calls.clear()
        self.admit = lambda context: False
        self.assertEqual(self.run_loop(), result)
        self.assertEqual(self.calls, [])

    def test_controller_cap_can_close_without_blocking_remaining_review(self):
        decisions = []
        original = self.handlers["controller"]
        def controller(context):
            decisions.append(context["round_index"])
            return original(context)
        self.handlers["controller"] = controller
        self.admit = lambda context: not (context["stage"] == "controller" and decisions)
        result = self.run_loop()
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["completed_rounds"], 1)
        self.assertEqual(result["round_index"], 2)
        self.assertIn((1, "reconcile"), self.calls)
        self.assertNotIn((2, "controller"), self.calls)

    def test_budget_stop_resumes_only_completed_stages(self):
        self.admit = lambda context: not (context["round_index"] == 1 and context["stage"] == "execute")
        self.assertEqual(self.run_loop()["stage"], "execute")
        self.assertEqual(self.calls, [(1, s) for s in loop.STAGES[:4]])
        self.calls.clear()
        self.admit = lambda context: True
        self.assertEqual(self.run_loop()["completed_rounds"], 2)
        self.assertEqual(self.calls, [(1, s) for s in loop.STAGES[4:]] + [(2, s) for s in loop.STAGES])

    def test_closed_grant_caps_deadline_make_no_handler_calls(self):
        for reason in ("closed_grant", "caps", "deadline"):
            with self.subTest(reason=reason):
                self.admit = lambda context: False
                self.assertEqual(self.run_loop()["status"], "stopped")
                self.assertEqual(self.calls, [])
                self.assertFalse(self.root.exists())

    def test_exception_before_output_preserved_without_retry(self):
        def failed(context):
            self.calls.append((1, "execute"))
            raise RuntimeError("synthetic worker uncertain")
        self.handlers["execute"] = failed
        with self.assertRaises(loop.LoopHalted):
            self.run_loop()
        self.assertTrue((self.root / "round-0001-execute.failed.json").exists())
        self.calls.clear()
        self.handlers["execute"] = self.handler("execute")
        with self.assertRaises(loop.LoopHalted):
            self.run_loop()
        self.assertEqual(self.calls, [])

    def test_output_without_durable_completion_never_retried(self):
        old_save = loop._save_pair
        def crash(path, value):
            if path.name == "round-0001-execute.done.json":
                loop.c.save(path, value)
                raise OSError("simulated crash after output before binding fsync")
            old_save(path, value)
        with patch.object(loop, "_save_pair", side_effect=crash), self.assertRaises(loop.LoopHalted):
            self.run_loop()
        self.calls.clear()
        with self.assertRaises(loop.LoopHalted):
            self.run_loop()
        self.assertEqual(self.calls, [])

    def test_factual_execution_failure_can_enter_review_and_next_input(self):
        observed = []
        def execute(context):
            if context["round_index"] == 1:
                return {"status": "failed", "error": "synthetic fit rejection", "fits_entered": 0}
            return {"status": "succeeded", "predictions": [.2]}
        def review(context):
            observed.append(context["outputs"]["execute"]["status"])
            return {"independently_reviewed": True}
        self.handlers.update(execute=execute, result_review=review,
            reconcile=lambda context: context["outputs"]["execute"],
            controller=lambda context: {"forecast": .2})
        self.assertEqual(self.run_loop()["completed_rounds"], 2)
        self.assertEqual(observed, ["failed", "succeeded"])
        second = loop._read_pair(self.root / "round-0002-input.done.json")["output"]
        self.assertEqual(second["feedback"]["status"], "failed")

    def test_seed_handler_and_round_bound_drift_blocks_resume(self):
        self.run_loop()
        for field in ("seed", "handler", "bound"):
            with self.subTest(field=field):
                self.calls.clear()
                old_seed, old_identity = deepcopy(self.seed), deepcopy(self.identities)
                if field == "seed": self.seed["label"] = 1
                if field == "handler": self.identities["controller"]["version"] = 2
                with self.assertRaises(loop.LoopHalted):
                    self.run_loop(3 if field == "bound" else 2)
                self.assertEqual(self.calls, [])
                self.seed, self.identities = old_seed, old_identity

    def test_output_and_claim_drift_block_resume(self):
        self.run_loop()
        output = self.root / "round-0001-input.done.json"
        original = output.read_bytes()
        value = loop.c._json(original)
        value["output"]["feedback"]["label"] = 1
        # Deliberately tamper only with this disposable synthetic artifact.
        with output.open("w", encoding="utf-8") as stream: json.dump(value, stream)
        self.calls.clear()
        with self.assertRaises((ValueError, loop.LoopHalted)): self.run_loop()
        self.assertEqual(self.calls, [])
        with output.open("wb") as stream: stream.write(original)
        claim = self.root / "round-0001-input.claim.json"
        with patch.object(loop.c, "_json", side_effect=lambda data:
                {"bad": True} if data == claim.read_bytes() else __import__("json").loads(data)):
            self.calls.clear()
            with self.assertRaises(loop.LoopHalted):
                self.run_loop()
            self.assertEqual(self.calls, [])

    def test_external_artifact_drift_is_rechecked(self):
        artifact = self.directory / "synthetic_artifact.json"
        loop.c.save(artifact, {"synthetic": True})
        self.seed["binding"] = {"path": str(artifact), "sha256": loop.c.sha(artifact)}
        self.run_loop()
        self.calls.clear()
        with patch.object(loop.c, "sha", side_effect=lambda path:
                "0" * 64 if Path(path) == artifact else __import__("hashlib").sha256(Path(path).read_bytes()).hexdigest()):
            with self.assertRaises(ValueError): self.run_loop()
        self.assertEqual(self.calls, [])

    def test_source_changed_by_handler_halts_before_completion(self):
        def changed(context):
            self.identities["execute"]["version"] = 2
            return {"status": "succeeded"}
        self.handlers["execute"] = changed
        with self.assertRaises(loop.LoopHalted): self.run_loop()
        self.assertFalse((self.root / "round-0001-execute.done.json").exists())

    def test_driver_source_drift_blocks_completed_replay(self):
        self.run_loop()
        self.calls.clear()
        source = Path(loop.__file__).resolve()
        old_sha = loop.c.sha
        with patch.object(loop.c, "sha", side_effect=lambda path:
                "1" * 64 if Path(path) == source else old_sha(path)):
            with self.assertRaises(loop.LoopHalted): self.run_loop()
        self.assertEqual(self.calls, [])

    def test_saved_output_artifact_drift_blocks_resume(self):
        artifact = self.directory / "saved_output.json"
        loop.c.save(artifact, {"synthetic": True})
        binding = {"path": str(artifact), "sha256": loop.c.sha(artifact)}
        original = self.handlers["source_review"]
        self.handlers["source_review"] = lambda context: {**original(context), "artifacts": [binding]}
        self.run_loop()
        self.calls.clear()
        with artifact.open("w", encoding="utf-8") as stream: json.dump({"synthetic": False}, stream)
        with self.assertRaises(ValueError): self.run_loop()
        self.assertEqual(self.calls, [])

    def test_admission_source_drift_blocks_before_new_claim(self):
        def admit(context):
            if context["stage"] == "controller": self.identities["controller"]["version"] = 2
            return True
        self.admit = admit
        with self.assertRaises(loop.LoopHalted): self.run_loop()
        self.assertEqual(self.calls, [(1, "input")])
        self.assertFalse((self.root / "round-0001-controller.claim.json").exists())

    def test_failed_marker_blocks_even_a_completed_pair(self):
        self.run_loop()
        self.calls.clear()
        loop.c.save(self.root / "round-0001-execute.failed.json", {"retry_allowed": False})
        with self.assertRaises(loop.LoopHalted): self.run_loop()
        self.assertEqual(self.calls, [])

    def test_nonblocking_lock_rejects_concurrent_call(self):
        started, release = threading.Event(), threading.Event()
        errors = []
        def blocked(context):
            started.set()
            if not release.wait(5): raise TimeoutError("test thread not released")
            return {"feedback": context["previous_result"]}
        self.handlers["input"] = blocked
        def first():
            try: self.run_loop(1)
            except BaseException as exc: errors.append(exc)
        thread = threading.Thread(target=first)
        thread.start()
        self.assertTrue(started.wait(5))
        try:
            with self.assertRaisesRegex(loop.LoopHalted, "another loop"):
                self.run_loop(1)
        finally:
            release.set(); thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])

    def test_lock_symlink_is_not_followed(self):
        self.root.mkdir()
        outside = self.directory / "outside.lock"
        (self.root / ".loop.lock").symlink_to(outside)
        with self.assertRaises(OSError): self.run_loop()
        self.assertFalse(outside.exists())
        self.assertEqual(self.calls, [])

    def test_invalid_handler_output_nonfinite_and_bool_bound(self):
        for index, value in enumerate(([], {"bad": float("nan")})):
            with self.subTest(value=value):
                self.root = self.directory / str(index)
                self.handlers["input"] = lambda context, value=value: value
                with self.assertRaises(loop.LoopHalted): self.run_loop()
        with self.assertRaises(ValueError): self.run_loop(True)


if __name__ == "__main__":
    unittest.main()
