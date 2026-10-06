"""Synthetic identity tests; source hashes do not establish research benefit."""
from copy import deepcopy
import hashlib
import unittest

from supervisor_harness import research_capacity_identity as identity


def token(label):
    return hashlib.sha256(label.encode()).hexdigest()


def inputs():
    binding = lambda name: {"sources": {name + ".py": token(name)},
                            "configuration_sha256": token(name + "-config")}
    return dict(kernel=binding("scorer"), predictor=binding("predictor"),
                harness=binding("harness"), researcher=binding("researcher"),
                model={"requested_model": "gpt-6.1-sol", "serving_snapshot": "unknown",
                       "serving_snapshot_verified": False}, memory=token("memory"),
                runtime={"python": {"path": "/pinned/python", "sha256": token("python")},
                         "dependencies": {"numpy": {"version": "1.26.4", "sha256": token("numpy")}}})


class CapacityIdentityTests(unittest.TestCase):
    def test_predictor_does_not_mutate_harness_researcher_model(self):
        args = inputs()
        before = identity.manifest(**args)
        args["predictor"]["sources"]["predictor.py"] = token("new-predictor")
        after = identity.manifest(**args)
        self.assertEqual(identity.change_axis(before, after), "C")
        self.assertEqual([before[k] for k in ("H", "R", "M", "runtime_sha256")],
                         [after[k] for k in ("H", "R", "M", "runtime_sha256")])

    def test_memory_is_not_research_policy(self):
        args = inputs()
        before = identity.manifest(**args)
        args["memory"] = token("more-memory")
        after = identity.manifest(**args)
        self.assertEqual(before["R"], after["R"])
        self.assertEqual(identity.change_axis(before, after), "MEMORY_ACCUMULATION")
        self.assertFalse(after["capacity_improvement_claimed"])

    def test_individual_capacity_and_composite_changes(self):
        for axis, key in (("R", "researcher"), ("H", "harness")):
            args = inputs()
            before = identity.manifest(**args)
            args[key]["configuration_sha256"] = token("new-config")
            after = identity.manifest(**args)
            self.assertEqual(identity.change_axis(before, after), axis)
            args["memory"] = token("new-memory")
            self.assertEqual(identity.change_axis(before, identity.manifest(**args)), "COMPOSITE_UNATTRIBUTABLE")

    def test_kernel_model_and_runtime_are_fixed(self):
        for mutate in (lambda a: a["kernel"].update(configuration_sha256=token("new")),
                       lambda a: a["model"].update(requested_model="different"),
                       lambda a: a["runtime"]["python"].update(sha256=token("new"))):
            args = inputs()
            before = identity.manifest(**args)
            mutate(args)
            with self.assertRaises(ValueError):
                identity.change_axis(before, identity.manifest(**args))

    def test_overlap_protected_invalid_paths_hashes(self):
        for name in ("harness.py", "scorer.py", "artifacts/a.py", "../escape.py", "/absolute.py",
                     "research/market_rsi/supervisor_harness/global_state_gate.py",
                     "research/market_rsi/minimal_prediction_loop/proper_scoring.py",
                     "minimal_prediction_loop/proper_scoring.py"):
            args = inputs()
            args["predictor"]["sources"] = {name: token("x")}
            with self.assertRaises(ValueError):
                identity.manifest(**args)
        for sha in ("0" * 64, "A" * 64, "missing", None):
            args = inputs()
            args["memory"] = sha
            with self.assertRaises(ValueError):
                identity.manifest(**args)

    def test_missing_unknown_and_tampered_identities(self):
        for mutate in (lambda a: a["model"].pop("serving_snapshot"),
                       lambda a: a["model"].update(serving_snapshot="unverified-snapshot"),
                       lambda a: a["runtime"]["python"].pop("sha256"),
                       lambda a: a["harness"].update(sources={})):
            args = inputs()
            mutate(args)
            with self.assertRaises(ValueError):
                identity.manifest(**args)
        before = identity.manifest(**inputs())
        after = deepcopy(before)
        after["H"] = token("lie")
        with self.assertRaises(ValueError):
            identity.change_axis(before, after)
        self.assertEqual(identity.change_axis(before, before), "UNCHANGED")


if __name__ == "__main__":
    unittest.main()
